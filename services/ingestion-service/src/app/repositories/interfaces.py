"""Repository interfaces (implementation-plan.md section 7): `ConnectorRecordRepository`
and `CredentialRepository`.

Single responsibility: declare the data-access seam between `connectors/base.py`'s
`run_incremental` and storage, mirroring `validation-service`'s
`ValidationRunRepository`/`SplitResultRepository` interface-naming convention
(`app.repositories.interfaces`, `typing.Protocol`, `tenant_id` as the first
parameter after `self`). Implementation is this ticket's own
`postgres_repository.py`; this module only defines the shape, and stays
importable with zero storage-driver dependencies (only `pandas`), matching
`validation-service/src/app/repositories/interfaces.py`'s own "no storage-driver
import" property.

One method per table family (`INGEST-002`'s `price_ohlcv`, `onchain_metric`,
`sentiment_score`) rather than one generic `add_records(table, ...)` method --
each table has a distinct row shape, and a generic method would just push the
per-table `DataFrame` column mapping into every caller instead of owning it
once per method here.

`latest_fetched_at` is not one of this ticket's three headline methods but is
needed to implement `connectors/base.py`'s `latest_watermark_from_db` (this
ticket's own AC) without `base.py` reaching around the Repository pattern to
run raw SQL against three different tables itself -- the repository is the
only thing that should know which physical table(s) `MAX(fetched_at)` must be
read from for a given `source`.

`CredentialRepository` (INGEST-004) is a separate Protocol, not a method added
to `ConnectorRecordRepository`, since it reads/writes a different table
(`connector_credentials`) with a different shape (encrypted fields, not
append-only fetch records) -- callers that only need record storage (the
three `add_*_records` methods) shouldn't have to satisfy a credentials
contract too. `Credentials` is a plain frozen dataclass carrying only
plaintext field values -- it never crosses this repository's own boundary
except as `get_credentials`'s return value / `set_credentials`'s encrypted
write, per ADR-0004 ("no endpoint, log line, or dashboard response ever
returns a decrypted value"); callers are responsible for not logging it.
`app.credential_crypto.encrypt`/`decrypt` (`INGEST-011`) is the only
encryption primitive this repository is allowed to call, per this ticket's
DRY check -- no second crypto implementation here.

`get_credential_status` (`INGEST-012`, UAT-driven: `GW-021`'s proxy route
pointed at an endpoint that was never built) is a presence-only check --
it must never decrypt `client_id`/`client_secret` to answer "is a
credential set", unlike `get_credentials` above. `CredentialStatus` is a
separate frozen dataclass rather than reusing `Credentials`, since it never
carries a plaintext field value at all (only `source`/`credential_set`/
`last_set_at`) -- collapsing the two into one type would risk a caller
accidentally treating an unset optional plaintext field as "no value was
decrypted" rather than "no value exists to decrypt".

`INGEST-009` (revised, `docs/adr/0005-dataset-is-a-continuous-tenant-source-table.md`):
`list_datasets`/`read_series`/`latest_crawl_run` are three read-only query
methods added to `ConnectorRecordRepository` rather than a new sibling
Protocol -- they need exactly the same "which of the three tables holds this
`(tenant_id, source)`" knowledge `latest_fetched_at` above already
encapsulates, so extending this Protocol reuses that knowledge instead of
duplicating it behind a second interface. `DatasetSummary`/`SeriesResult`/
`CrawlRunSummary` are plain frozen dataclasses, not Pydantic models -- this
module has zero HTTP/FastAPI dependency (see the module docstring above), and
stays that way; `app.routers.datasets` (this ticket's own router) is
responsible for mapping these into its own response models.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass
from datetime import datetime

import pandas as pd


@typing.runtime_checkable
class ConnectorRecordRepository(typing.Protocol):
    """Repository for the `ingestion` schema's three per-connector tables."""

    def add_price_records(self, tenant_id: str, source: str, records: pd.DataFrame) -> int:
        """Writes `records` (the shape returned by `BinancePriceConnector.fetch`,
        with a `fetched_at` column added) to `price_ohlcv`. Returns rows written.
        """
        ...

    def add_onchain_records(self, tenant_id: str, source: str, records: pd.DataFrame) -> int:
        """Writes `records` (the shape returned by `BlockchainInfoConnector.fetch`,
        with a `fetched_at` column added) to `onchain_metric`. Returns rows written.
        """
        ...

    def add_sentiment_records(self, tenant_id: str, source: str, records: pd.DataFrame) -> int:
        """Writes `records` (the shape returned by `RedditSentimentConnector.fetch`,
        with a `fetched_at` column added) to `sentiment_score`. Returns rows written.
        """
        ...

    def latest_fetched_at(self, tenant_id: str, source: str) -> datetime | None:
        """Max `fetched_at` across whichever of the three tables holds rows for
        `(tenant_id, source)`, or `None` if none exist yet.
        """
        ...

    def record_crawl_run(
        self,
        tenant_id: str,
        source: str,
        since_watermark: datetime | None,
        fetched_at: datetime,
        row_count: int,
        status: str,
    ) -> None:
        """Writes one `crawl_runs` row (INGEST-005) for a single `fetch()`
        outcome -- `since_watermark` is whatever `run_incremental` resolved
        before calling `fetch` (`None` only if no prior watermark existed),
        `row_count`/`status` describe the outcome (0/"completed" for an
        empty-but-successful fetch, "failed" if the subsequent write attempt
        raised). Callers must call this after every `fetch()` attempt, not
        only the happy path with rows written.
        """
        ...

    def list_datasets(self, tenant_id: str) -> list["DatasetSummary"]:
        """One `DatasetSummary` per distinct `source` this tenant has rows for,
        across all three tables (`INGEST-009` revised, ADR-0005: a dataset is
        `{tenant_id, source}`, not a per-crawl-run snapshot). Empty history
        returns `[]`, never raises -- the router maps that to `200 {"items":
        []}`, never a `404`.
        """
        ...

    def read_series(
        self,
        tenant_id: str,
        source: str,
        start: datetime | None,
        end: datetime | None,
        field: str | None,
    ) -> "SeriesResult | None":
        """Timestamps/values for `(tenant_id, source)`, sliced to
        `[start, end]` (either or both `None` meaning "earliest row"/"latest
        row" -- the same code path as the fully-bounded case, not a special
        case). `field` selects the value column for multi-column sources,
        defaulting per-table (see `postgres_repository._TABLE_SPECS`'s
        `default_field`, documented in README.md). Returns `None` when
        `source` has no rows for `tenant_id` -- the router collapses this,
        and the cross-tenant case (also `None`, since the query is always
        scoped to `tenant_id`), into the same `404`.
        """
        ...

    def latest_crawl_run(self, tenant_id: str, source: str) -> "CrawlRunSummary | None":
        """This tenant's most recent `crawl_runs` row for `source` (by
        `fetched_at`), or `None` if none exists yet.
        """
        ...


@dataclass(frozen=True)
class DatasetSummary:
    """One row of `GET /datasets`'s response (solution-design.md 8.3):
    discovery only, no values."""

    source: str
    earliest_timestamp: datetime
    latest_timestamp: datetime
    row_count: int


@dataclass(frozen=True)
class SeriesResult:
    """`GET /datasets/{source}/series`'s response payload
    (solution-design.md 8.3), pre-mapping into the router's own Pydantic
    response model. `timestamps`/`values` are the same length and
    index-aligned, ordered by event time ascending."""

    timestamps: list[datetime]
    values: list[float]


@dataclass(frozen=True)
class CrawlRunSummary:
    """`GET /connectors/{source}/status`'s response payload
    (solution-design.md 8.3): status/timestamp/row_count of this tenant's
    most recent `crawl_runs` row for one source."""

    status: str
    fetched_at: datetime
    row_count: int


@dataclass(frozen=True)
class Credentials:
    """Decrypted, in-process-only credential fields for one `(tenant_id, source)`
    row in `connector_credentials`. Field names match `app.models.
    ConnectorCredentials`'s ciphertext columns (`client_id`, `client_secret`)
    -- callers must never log or otherwise persist an instance of this type.
    """

    client_id: str
    client_secret: str


@dataclass(frozen=True)
class CredentialStatus:
    """`GET /connectors/credentials-status`'s per-source response payload
    (`INGEST-012`): presence-only, never a decrypted field value.
    `credential_set` is `False`/`last_set_at` is `None` for a
    `(tenant_id, source)` with no stored row -- a valid, successful answer,
    not an error the caller maps to a `404`.
    """

    source: str
    credential_set: bool
    last_set_at: datetime | None


@typing.runtime_checkable
class CredentialRepository(typing.Protocol):
    """Repository for the `ingestion` schema's `connector_credentials` table
    (INGEST-004, ADR-0004). Every implementation must encrypt on write and
    decrypt on read via `app.credential_crypto` -- never store or return a
    plaintext column value directly.
    """

    def get_credentials(self, tenant_id: str, source: str) -> Credentials | None:
        """Decrypted credentials for `(tenant_id, source)`, or `None` if no
        row exists yet. Decryption happens in-process, immediately before
        returning -- the return value must never be logged by any caller.
        """
        ...

    def set_credentials(self, tenant_id: str, source: str, **fields: str) -> None:
        """Encrypts each of `fields` (`client_id`/`client_secret`) via
        `app.credential_crypto.encrypt` before writing/upserting the
        `(tenant_id, source)` row. No plaintext value is ever written to a
        `connector_credentials` column.
        """
        ...

    def get_credential_status(self, tenant_id: str, source: str) -> CredentialStatus:
        """Presence-only check for `(tenant_id, source)` -- never decrypts
        `client_id`/`client_secret` (INGEST-012). Always returns a
        `CredentialStatus`, never `None`/raises: an unset tenant/source is
        `credential_set=False, last_set_at=None`, itself a valid answer.
        """
        ...
