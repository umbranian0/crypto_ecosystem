"""INGEST-008: `POST /connectors/{source}/run` -- tenant-authenticated crawl trigger.

Single responsibility: adapt an HTTP request into the exact same DB-write
sequence `connectors/base.py`'s `run_incremental` already encodes for its
`tenant_id`/`repository` branch (`latest_watermark_from_db` -> `connector.
fetch` -> `repository.add_{record_kind}_records` -> `repository.
record_crawl_run`) -- no second, divergent "run a crawl" implementation. The
primitives themselves (`latest_watermark_from_db`, the repository's own
write/record methods) are imported and called directly rather than through
`run_incremental` only because `run_incremental` itself returns `None`; this
handler needs the resolved `since`/`row_count`/`status`/`fetched_at` values
in hand to answer the request with a reference to the `crawl_runs` row it
just wrote (`ConnectorRecordRepository` exposes no read-back method for that
row, and adding one is out of this ticket's scope -- ticket Implementation
acceptance criteria's disclosed simplification).

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
a `(tenant_id, source)` -- see `_run_and_record`'s `since_override` parameter,
consulted only inside its `since is None` branch. `_resolve_connector`'s
tuple grew a 5th element, `since_floor`, the optional real-data-availability
boundary an override must not predate (binance/onchain only; `None` for
reddit, which has no such boundary). Validation (`_parse_since_override`)
always runs when `since` is supplied, even on a non-first crawl where the
parsed value ends up unused -- fails fast on bad input rather than silently
accepting garbage that happens to be ignored.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
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

from app.dependencies.repositories import ConnectorRecordRepositoryDep, CredentialRepositoryDep
from app.repositories.interfaces import ConnectorRecordRepository, CredentialRepository

router = APIRouter()


class ConnectorRunResponse(BaseModel):
    """Reference to the `crawl_runs` row this request's `fetch()` attempt
    produced -- the values `record_crawl_run` was just called with, since
    `ConnectorRecordRepository` exposes no way to read that row back.
    """

    source: str
    status: str
    row_count: int
    since: datetime | None
    fetched_at: datetime


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


@router.post("/connectors/{source}/run", response_model=ConnectorRunResponse, status_code=202)
def run_connector(
    source: str,
    connector_repository: ConnectorRecordRepositoryDep,
    credential_repository: CredentialRepositoryDep,
    tenant: TenantContext = Depends(get_tenant_context),
    since: str | None = Query(
        default=None,
        description=(
            "Optional ISO 8601 date/datetime, honored only on this tenant's "
            "first-ever crawl of this source; ignored on any later crawl."
        ),
    ),
) -> ConnectorRunResponse:
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

    return _run_and_record(
        connector_repository, tenant.tenant_id, connector, default_start, record_kind, since_override
    )


def _run_and_record(
    repository: ConnectorRecordRepository,
    tenant_id: str,
    connector,
    default_start: datetime,
    record_kind: str,
    since_override: datetime | None = None,
) -> ConnectorRunResponse:
    # Mirrors `connectors/base.py`'s `run_incremental` DB-write branch
    # exactly (same primitives, same order, same failure handling) -- the
    # only reason this isn't a plain call to `run_incremental` is that this
    # handler needs the resolved values back to answer the request.
    since = latest_watermark_from_db(repository, tenant_id, connector.name)
    if since is None:
        since = since_override if since_override is not None else default_start
    result = connector.fetch(since=since)

    if not result.is_empty():
        records = result.records.copy()
        records["fetched_at"] = result.fetched_at
        write_method = getattr(repository, f"add_{record_kind}_records")
        try:
            row_count = write_method(tenant_id, connector.name, records)
        except Exception:
            repository.record_crawl_run(tenant_id, connector.name, since, result.fetched_at, 0, "failed")
            raise
        status = "completed"
    else:
        row_count = 0
        status = "completed"

    repository.record_crawl_run(tenant_id, connector.name, since, result.fetched_at, row_count, status)

    return ConnectorRunResponse(
        source=connector.name,
        status=status,
        row_count=row_count,
        since=since,
        fetched_at=result.fetched_at,
    )


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
