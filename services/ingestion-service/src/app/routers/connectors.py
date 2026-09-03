"""INGEST-008/INGEST-015: `POST /connectors/{source}/run` -- tenant-authenticated,
lock-gated, asynchronous crawl trigger.

Single responsibility: adapt an HTTP request into the exact same DB-write
sequence `connectors/base.py`'s `run_incremental` already encodes for its
`tenant_id`/`repository` branch (`latest_watermark_from_db` -> `connector.
fetch` -> `repository.add_{record_kind}_records` -> `repository.
record_crawl_run`) -- no second, divergent "run a crawl" implementation. The
primitives themselves (`latest_watermark_from_db`, the repository's own
write/record methods) are imported and called directly rather than through
`run_incremental` only because `run_incremental` itself returns `None`; this
handler needs the resolved `since` value in hand to answer the request and to
hand off to the background task.

INGEST-015 (QA-reproduced timeout + race-condition fix): the crawl itself no
longer runs synchronously inside the request -- `run_connector` acquires a
per-`(tenant_id, source)` lock (`app.crawl_registry.CrawlRegistry`, INGEST-014)
immediately after validation, resolves `since`, writes a `"queued"`
`crawl_runs` row, schedules `_execute_crawl` via `BackgroundTasks`, and
returns `202` with `ConnectorRunAcceptedResponse` -- not the crawl's outcome,
which isn't known yet. A second request for the same `(tenant_id, source)`
while one is in flight gets an immediate `409`, before any DB read/write,
closing the race where two concurrent requests each resolved the same
`since` and both attempted to write the same rows (reproduced live as an
unhandled `500` `UniqueViolation`). `_execute_crawl` runs in the background
thread FastAPI's `BackgroundTasks` uses and is solely responsible for
releasing the lock (`finally: registry.release(...)`, unconditionally) --
this is what prevents a `fetch()`/write exception from permanently locking a
source out of future crawls.

`source` -> connector mapping: the exact `connector.name` strings each
`IngestionSource` subclass sets, not invented route-level names --
`binance_price_btcusdt_1h` (`BinancePriceConnector`'s only configured
symbol/interval so far), `blockchain_info_hash-rate`/
`blockchain_info_n-unique-addresses` (`BlockchainInfoConnector`, one entry
per `blockchain_onchain.SEED_WATERMARKS` key), and `reddit_vader_sentiment`
(`RedditSentimentConnector`). An unrecognized `source` is a `404`, resolved
before any tenant-scoped I/O runs.

Reddit credentials (INGEST-004): checked explicitly via `CredentialRepository.
get_credentials` before `fetch()` is called, so a tenant with no stored
credentials gets a clean `422` naming the missing connector rather than the
`RuntimeError` `RedditSentimentConnector._client()` would otherwise raise
mid-`fetch()` (which would surface as an unhandled `500`).

Tenant resolution: `naive_first_common.get_tenant_context`, the same
`Depends()` seam every other service in this platform already uses -- no
bespoke header parsing here.

`GET /connectors/credentials-status` (`INGEST-012`, live-UAT-driven: the
downstream endpoint `GW-021`'s operator proxy pointed at was never actually
built) reuses this router rather than a new file, since it's a
connector-scoped read alongside `POST /connectors/{source}/run` above.
`REDDIT_SOURCE_NAME` (already defined below) is reused as the one entry in
`_CREDENTIALED_SOURCES` rather than a second, hand-typed literal -- today
Reddit is the only connector with a credentials concept at all.
`CredentialRepository.get_credential_status` (not `get_credentials`) is the
only method called here -- it never decrypts `client_id`/`client_secret`,
so this handler has no plaintext/ciphertext value in hand to leak even by
accident. An unset tenant/source is a valid `200` entry
(`credential_set=False, last_set_at=None`), never a `404` -- matching this
service's existing "empty is a valid answer" convention (`GET /datasets`).

`since` override (INGEST-013): honored only on a tenant's first-ever crawl of
a `(tenant_id, source)` -- resolved inline in `run_connector` via its `since_override` local,
consulted only inside its `since is None` branch. `_resolve_connector`'s
tuple grew a 5th element, `since_floor`, the optional real-data-availability
boundary an override must not predate (binance/onchain only; `None` for
reddit, which has no such boundary). Validation (`_parse_since_override`)
always runs when `since` is supplied, even on a non-first crawl where the
parsed value ends up unused -- fails fast on bad input rather than silently
accepting garbage that happens to be ignored.

`POST /connectors/{source}/cancel` (`INGEST-024`): requests cancellation of
an in-flight crawl via `CrawlRegistry.request_cancel` (`INGEST-023`) --
`404` for an unknown `source` (checked against `_KNOWN_SOURCES`, reused from
`_resolve_connector`'s own constants), `409` if nothing is in flight, `202`
+ a `"cancelling"` `crawl_runs` row on success. `_execute_crawl`'s terminal
write resolves `"cancelled"` vs `"completed"` from `result.cancelled`
(`FetchResult`'s own field, INGEST-022) rather than re-querying
`registry.should_cancel(...)` after `fetch()` returns -- this is what
correctly handles the race where a crawl finishes normally after a cancel
was requested but before any checkpoint observed it (must resolve to
`"completed"`, not `"cancelled"`).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from naive_first_common import TenantContext, get_tenant_context

from connectors.base import latest_watermark_from_db, utcnow
from connectors.binance_price import BinancePriceConnector, default_backfill_start as binance_backfill_start
from connectors.blockchain_onchain import (
    SEED_WATERMARKS as ONCHAIN_SEED_WATERMARKS,
    BlockchainInfoConnector,
    default_backfill_start as onchain_backfill_start,
)
from connectors.reddit_sentiment import RedditSentimentConnector, default_backfill_start as reddit_backfill_start

from app.crawl_registry import CrawlRegistry
from app.dependencies.repositories import ConnectorRecordRepositoryDep, CredentialRepositoryDep, CrawlRegistryDep
from app.repositories.interfaces import ConnectorRecordRepository, CredentialRepository

router = APIRouter()


class ConnectorRunAcceptedResponse(BaseModel):
    """`POST /connectors/{source}/run`'s `202` body (INGEST-015) -- an
    acceptance acknowledgement, not the crawl's outcome (which is not known
    at response time, since the fetch-and-write work now happens in the
    background). `since` is the watermark this crawl will run from, already
    resolved before responding; `queued_at` is when the request was
    accepted. There is deliberately no `row_count`/`fetched_at` here -- see
    `GET /connectors/{source}/status` (INGEST-009) for the eventual outcome,
    keyed by the same `(tenant_id, source)` pair this response is scoped to.
    """

    source: str
    status: str
    since: datetime | None
    queued_at: datetime


def _binance_source():
    connector = BinancePriceConnector()
    default_start = binance_backfill_start()
    return connector, default_start, "price", False, default_start


def _onchain_source(chart_name: str):
    def _factory():
        connector = BlockchainInfoConnector(chart_name)
        default_start = onchain_backfill_start()
        return connector, default_start, "onchain", False, default_start

    return _factory


def _reddit_source(tenant: TenantContext, credential_repository: CredentialRepository):
    connector = RedditSentimentConnector(tenant_id=tenant.tenant_id, credential_repository=credential_repository)
    return connector, reddit_backfill_start(), "sentiment", True, None


_ONCHAIN_FACTORIES = {
    f"blockchain_info_{chart_name}": _onchain_source(chart_name) for chart_name in ONCHAIN_SEED_WATERMARKS
}

REDDIT_SOURCE_NAME = "reddit_vader_sentiment"
BINANCE_SOURCE_NAME = "binance_price_btcusdt_1h"

# Every connector with a credentials concept at all (INGEST-012) -- Reddit
# only, today. Reuses REDDIT_SOURCE_NAME above rather than a second literal.
_CREDENTIALED_SOURCES: tuple[str, ...] = (REDDIT_SOURCE_NAME,)

# INGEST-024: every known `source` value `POST /connectors/{source}/cancel`
# accepts -- built from the same constants `_resolve_connector` already
# checks, not a fourth hand-typed list.
_KNOWN_SOURCES: frozenset[str] = frozenset({BINANCE_SOURCE_NAME, REDDIT_SOURCE_NAME, *_ONCHAIN_FACTORIES.keys()})


class ConnectorCancelResponse(BaseModel):
    """`POST /connectors/{source}/cancel`'s `202` body (INGEST-024) -- an
    acknowledgement that the cancel request was received, not proof the
    crawl has actually stopped yet (poll `GET /connectors/{source}/status`
    for the eventual outcome)."""

    source: str
    status: str


class CredentialStatusItem(BaseModel):
    """One entry of `GET /connectors/credentials-status`'s response --
    presence-only, never the credential value (INGEST-012)."""

    source: str
    credential_set: bool
    last_set_at: datetime | None


class CredentialsStatusResponse(BaseModel):
    items: list[CredentialStatusItem]


def _resolve_connector(source: str, tenant: TenantContext, credential_repository: CredentialRepository):
    """Returns `(connector, default_start, record_kind, requires_credentials,
    since_floor)` for a known `source`, or `None` for an unknown one -- the
    caller maps `None` to a `404`. `default_start` is the connector's
    `default_backfill_start()` value (INGEST-013), used as the tenant-DB-path
    fallback on a first crawl; `since_floor` is the optional verified
    availability boundary an explicit `since` override must not predate
    (`None` when no such boundary exists, e.g. Reddit).
    """
    if source == BINANCE_SOURCE_NAME:
        return _binance_source()
    if source in _ONCHAIN_FACTORIES:
        return _ONCHAIN_FACTORIES[source]()
    if source == REDDIT_SOURCE_NAME:
        return _reddit_source(tenant, credential_repository)
    return None


def _parse_since_override(raw: str, floor: datetime | None) -> datetime:
    """Parses and validates a `since` query-param override (INGEST-013).

    Raises `HTTPException(422, ...)` (never a silent clamp or a `500`) for a
    malformed value, a future timestamp, or (when `floor` is given) a value
    predating the connector's verified earliest-available date.
    """
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"since={raw!r} is not a valid ISO 8601 date/datetime")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    if parsed > utcnow():
        raise HTTPException(status_code=422, detail=f"since={raw!r} is in the future")

    if floor is not None and parsed < floor:
        raise HTTPException(
            status_code=422,
            detail=f"since={raw!r} predates this connector's verified earliest-available date {floor.isoformat()!r}",
        )

    return parsed


@router.post("/connectors/{source}/run", response_model=ConnectorRunAcceptedResponse, status_code=202)
def run_connector(
    source: str,
    background_tasks: BackgroundTasks,
    connector_repository: ConnectorRecordRepositoryDep,
    credential_repository: CredentialRepositoryDep,
    registry: CrawlRegistryDep,
    tenant: TenantContext = Depends(get_tenant_context),
    since: str | None = Query(
        default=None,
        description=(
            "Optional ISO 8601 date/datetime, honored only on this tenant's "
            "first-ever crawl of this source; ignored on any later crawl."
        ),
    ),
) -> ConnectorRunAcceptedResponse:
    resolved = _resolve_connector(source, tenant, credential_repository)
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"unknown connector source {source!r}")

    connector, default_start, record_kind, requires_credentials, since_floor = resolved

    since_override: datetime | None = None
    if since is not None:
        since_override = _parse_since_override(since, since_floor)

    if requires_credentials:
        credentials = credential_repository.get_credentials(tenant.tenant_id, source)
        if credentials is None:
            raise HTTPException(
                status_code=422,
                detail=f"no credentials stored for connector {source!r} and this tenant",
            )

    # Lock-then-validate ordering (INGEST-015 Design): every validation above
    # (unknown source, malformed/out-of-range `since`, missing credentials)
    # has already passed by this point -- a bad request fails the same way
    # whether or not a crawl happens to be in flight for this source. Only
    # now, immediately before the watermark is resolved, is the lock touched
    # -- this is what closes the actual race (both requests resolving the
    # same `since` before either held the lock).
    if not registry.try_acquire(tenant.tenant_id, connector.name):
        raise HTTPException(
            status_code=409, detail=f"crawl already in progress for connector {source!r}"
        )

    try:
        resolved_since = latest_watermark_from_db(connector_repository, tenant.tenant_id, connector.name)
        if resolved_since is None:
            resolved_since = since_override if since_override is not None else default_start

        queued_at = utcnow()
        connector_repository.record_crawl_run(
            tenant.tenant_id, connector.name, resolved_since, queued_at, 0, "queued"
        )
        background_tasks.add_task(
            _execute_crawl,
            connector_repository,
            registry,
            tenant.tenant_id,
            connector,
            record_kind,
            resolved_since,
        )
    except Exception:
        # The lock must never be left held on a path that failed to reach
        # `_execute_crawl` -- that function is the only other place `release`
        # is called, and it will never run if scheduling itself failed.
        registry.release(tenant.tenant_id, connector.name)
        raise

    return ConnectorRunAcceptedResponse(
        source=connector.name, status="queued", since=resolved_since, queued_at=queued_at
    )


@router.post("/connectors/{source}/cancel", response_model=ConnectorCancelResponse, status_code=202)
def cancel_connector(
    source: str,
    connector_repository: ConnectorRecordRepositoryDep,
    registry: CrawlRegistryDep,
    tenant: TenantContext = Depends(get_tenant_context),
) -> ConnectorCancelResponse:
    """`INGEST-024`: requests cancellation of an in-flight crawl for
    `(tenant.tenant_id, source)`.

    No credential check and no connector instantiation -- cancelling never
    calls `fetch()` or touches credentials, so `source` is validated against
    `_KNOWN_SOURCES` alone (unknown -> `404`, resolved before any registry/DB
    call). `registry.request_cancel(...)` returning `False` means nothing is
    in flight for this `(tenant_id, source)` -> `409` (mirrors
    `run_connector`'s own `409` framing, inverted). On success, writes one
    plain-insert `"cancelling"` `crawl_runs` row (matching this router's
    existing insert-only convention for status-transition writes;
    `since_watermark=None` since this write isn't a fetch outcome) and
    returns `202`.
    """
    if source not in _KNOWN_SOURCES:
        raise HTTPException(status_code=404, detail=f"unknown connector source {source!r}")

    if not registry.request_cancel(tenant.tenant_id, source):
        raise HTTPException(
            status_code=409, detail=f"no crawl in progress for connector {source!r}"
        )

    connector_repository.record_crawl_run(tenant.tenant_id, source, None, utcnow(), 0, "cancelling")

    return ConnectorCancelResponse(source=source, status="cancelling")


def _execute_crawl(
    repository: ConnectorRecordRepository,
    registry: CrawlRegistry,
    tenant_id: str,
    connector,
    record_kind: str,
    since: datetime | None,
) -> None:
    """Background-task body (INGEST-015): the actual fetch-and-write work,
    scheduled via `BackgroundTasks.add_task` rather than awaited inline.
    Mirrors `connectors/base.py`'s `run_incremental` DB-write branch (same
    primitives, same order) -- the only reason this isn't a plain call to
    `run_incremental` is that `since` is already resolved by the caller
    (under the lock), not re-resolved here.

    Writes a `status="running"` `crawl_runs` row (INGEST-021) immediately
    before `connector.fetch(...)` is called -- a bookkeeping row marking the
    crawl as actually in flight, not just accepted (`"queued"`, written by
    `run_connector` before scheduling this task). Uses `utcnow()` for both
    `fetched_at` and `row_count=0`, same as the `"failed"` write below, since
    this row records an event, not a fetch outcome.

    Catches *any* exception from `fetch()` or the write step alike (a
    deliberate improvement over the old synchronous handler, which only
    caught write-step exceptions -- a `fetch()`-raised exception used to
    surface as an unhandled `500` with no `crawl_runs` row at all) and
    records it as `status="failed"` instead of leaving the row `"queued"`
    forever. The `finally` block's `registry.release` is the single most
    important line here -- it must run on every exit path, or a background
    exception would permanently lock this `(tenant_id, source)` out of
    future crawls.
    """
    try:
        repository.record_crawl_run(tenant_id, connector.name, since, utcnow(), 0, "running")

        result = connector.fetch(
            since=since,
            should_cancel=lambda: registry.should_cancel(tenant_id, connector.name),
            on_progress=lambda n: repository.record_crawl_progress(tenant_id, connector.name, n),
        )

        if not result.is_empty():
            records = result.records.copy()
            records["fetched_at"] = result.fetched_at
            write_method = getattr(repository, f"add_{record_kind}_records")
            row_count = write_method(tenant_id, connector.name, records)
        else:
            row_count = 0

        # INGEST-024: `result.cancelled` (set by the connector itself at
        # whatever checkpoint it observed `should_cancel()==True`), never a
        # fresh `registry.should_cancel(...)` query here -- this is what
        # correctly resolves the documented race: a crawl that finishes
        # normally after a cancel was requested but before any checkpoint
        # observed it must still resolve to "completed", not "cancelled".
        terminal_status = "cancelled" if result.cancelled else "completed"
        repository.record_crawl_run(tenant_id, connector.name, since, result.fetched_at, row_count, terminal_status)
    except Exception:
        repository.record_crawl_run(tenant_id, connector.name, since, utcnow(), 0, "failed")
    finally:
        registry.release(tenant_id, connector.name)


@router.get("/connectors/credentials-status", response_model=CredentialsStatusResponse)
def get_credentials_status(
    credential_repository: CredentialRepositoryDep,
    tenant: TenantContext = Depends(get_tenant_context),
) -> CredentialsStatusResponse:
    statuses = [
        credential_repository.get_credential_status(tenant.tenant_id, source)
        for source in _CREDENTIALED_SOURCES
    ]
    items = [
        CredentialStatusItem(
            source=status.source, credential_set=status.credential_set, last_set_at=status.last_set_at
        )
        for status in statuses
    ]
    return CredentialsStatusResponse(items=items)
