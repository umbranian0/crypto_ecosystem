"""INGEST-010: platform-wide historical CSV archive backfill, importable
(not a CLI -- `scripts/seed_tenant.py` is the thin argparse wrapper around
this module, mirroring `gateway-api/src/app/provisioning.py`'s own
`scripts/provision_tenant.py` split, for the identical reason: `scripts/` is
not part of this service's packaged wheel (`pyproject.toml`'s
`[tool.hatch.build.targets.wheel]` only packages `src/app`), and `INGEST-030`
(next ticket in this chain) needs to import this module's functions directly
from inside the running FastAPI process.

DRY check (per ticket Design section): the actual DB write happens through
`ConnectorRecordRepository.add_price_records`/`add_onchain_records`/
`add_sentiment_records` (`app/repositories/interfaces.py`) -- the exact same
methods `connectors/base.py::run_incremental`'s DB-write branch already
calls. This module does its own CSV parsing (the platform archive's seed
files are a different, pre-DB-era shape than a connector's live `fetch()`
output -- see each `_load_*_csv` function's own docstring for the mapping),
but never reimplements the write path itself.

Idempotency ("skip-then-append", not a literal SQL UPSERT -- see README.md's
backfill section for the full rationale): `add_*_records` do a plain
`session.add_all` with no `ON CONFLICT` (confirmed against
`postgres_repository.py`), so this module achieves idempotency by reading
`ConnectorRecordRepository.latest_event_time(tenant_id, source)` first and
filtering the loaded records to event-time strictly greater than that
watermark before writing. Running the same CSV range twice against the same
tenant is then a no-op on the second run.

Source -> table/record-kind mapping (read from each connector's own `self.name`
and PROVENANCE.md directly, not guessed): see `SOURCE_SPECS` below.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TYPE_CHECKING

import httpx
import pandas as pd

if TYPE_CHECKING:  # pragma: no cover - import-time only.
    from app.repositories.interfaces import ConnectorRecordRepository

# services/ingestion-service/ -- three parents up from this file
# (src/app/seed_platform_history.py -> src/app -> src -> ingestion-service).
_SERVICE_ROOT = Path(__file__).resolve().parents[2]
_PLATFORM_ROOT = _SERVICE_ROOT / "data" / "raw" / "_platform"

PLATFORM_CSV_SENTINEL = "platform-csv"


# Leading columns of `seed_part1.csv`'s own header -- reused as a fallback
# for `seed_part2.csv`, which ships with no header row at all (a pre-existing
# data-quality gap in the raw archive, confirmed by inspecting both files
# directly, not introduced by this ticket). Only these leading columns are
# ever read; the ~200 `ta`-library indicator columns that follow (in either
# file) are dropped by the `keep` filter below regardless of file/column name.
_PRICE_HEADER_COLUMNS = [
    "_index",
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_vol",
    "trades",
    "taker_buy_base",
    "taker_buy_quote",
    "ignore",
    "symbol",
]


def _price_loader(path: Path) -> pd.DataFrame:
    """Maps the price seed/incremental CSV shape (PROVENANCE.md: the seed
    file also carries ~200 `ta`-library indicator columns, an `Unnamed: 0`
    pandas index artifact, and `quote_vol` instead of the connector's own
    `quote_volume` name) down to exactly the columns
    `postgres_repository._price_rows` reads. Indicator columns are dropped
    here, not written to the DB -- the raw/processed boundary caveat
    PROVENANCE.md documents for this source (README.md's backfill section
    carries the same caveat forward).
    """
    df = pd.read_csv(path)
    if "open_time" not in df.columns:
        # `seed_part2.csv` has no header row -- reload assigning
        # `seed_part1.csv`'s own leading column names positionally.
        df = pd.read_csv(path, header=None)
        names = list(_PRICE_HEADER_COLUMNS)
        if len(df.columns) > len(names):
            names += [f"_extra_{i}" for i in range(len(df.columns) - len(names))]
        df.columns = names[: len(df.columns)]
    df = df.rename(columns={"quote_vol": "quote_volume"})
    keep = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_volume",
        "trades",
        "taker_buy_base",
        "taker_buy_quote",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    return df


def _onchain_loader(chart_name: str) -> Callable[[Path], pd.DataFrame]:
    def _load(path: Path) -> pd.DataFrame:
        """Maps a blockchain.info seed/incremental CSV (`timestamp, date,
        <chart_name>`) down to `date` + `<chart_name>` -- the same two-column
        (plus `fetched_at`) shape `postgres_repository._onchain_value_column`
        expects (it picks whichever column isn't `timestamp_unix`/`date`/
        `fetched_at`), matching the live connector's own renamed `fetch()`
        output shape rather than the seed's raw `timestamp` column name.
        """
        df = pd.read_csv(path)
        df["date"] = pd.to_datetime(df["date"], utc=True)
        return df[["date", chart_name]].copy()

    return _load


def _sentiment_loader(path: Path) -> pd.DataFrame:
    """Maps the Kaggle seed CSV (`Date, Short Description, Accurate
    Sentiments` -- a news-headline dataset, not Reddit) onto
    `postgres_repository._sentiment_rows`'s required columns. Only a
    compound score exists in the source data, so `reddit_sid_pos`/`neg`/
    `neu` are written as `0.0` (there is no finer-grained score to recover
    from this dataset) -- disclosed in README.md's backfill section, not a
    silent fabrication. `post_id` (required, no DB default) is synthesized
    as `kaggle_<row index within this file>` since the source has no post
    identifier of its own; uniqueness only needs to hold within one seed
    file, since this source is seed-only (PROVENANCE.md: "no `incremental/`
    folder for this specific source").
    """
    df = pd.read_csv(path)
    df = df.rename(
        columns={
            "Date": "created_utc",
            "Short Description": "title",
            "Accurate Sentiments": "reddit_sid_com",
        }
    )
    df["created_utc"] = pd.to_datetime(df["created_utc"], utc=True)
    df["reddit_sid_pos"] = 0.0
    df["reddit_sid_neg"] = 0.0
    df["reddit_sid_neu"] = 0.0
    df["post_id"] = [f"kaggle_{i}" for i in range(len(df))]
    return df[
        [
            "created_utc",
            "title",
            "post_id",
            "reddit_sid_pos",
            "reddit_sid_neg",
            "reddit_sid_neu",
            "reddit_sid_com",
        ]
    ].copy()


@dataclasses.dataclass(frozen=True)
class SourceSpec:
    """One CSV-backed platform source: its DB `source` identity, which
    `add_*_records` method writes it, its own event-time column (matches
    `postgres_repository._TABLE_SPECS`), where its CSVs live under
    `data/raw/_platform/`, and how to parse one CSV file into the shape
    `add_*_records` expects.
    """

    source: str
    record_kind: str  # "price" | "onchain" | "sentiment"
    event_time_column: str
    csv_subdir: str  # relative to _PLATFORM_ROOT
    loader: Callable[[Path], pd.DataFrame]


# Kept as the distinct, non-continuous source name `PROVENANCE.md` itself
# recommends ("If the two sentiment series are ever combined for feature
# engineering, document that discontinuity explicitly -- don't let a report
# imply one continuous sentiment signal across the boundary") -- not merged
# into `reddit_vader_sentiment`'s own source identity. See README.md's
# backfill section for the full reasoning.
SOURCE_SPECS: tuple[SourceSpec, ...] = (
    SourceSpec(
        source="binance_price_btcusdt_1h",
        record_kind="price",
        event_time_column="open_time",
        csv_subdir="price/binance_btcusdt_1h",
        loader=_price_loader,
    ),
    SourceSpec(
        source="blockchain_info_hash-rate",
        record_kind="onchain",
        event_time_column="date",
        csv_subdir="onchain/blockchain_info_hash-rate",
        loader=_onchain_loader("hash-rate"),
    ),
    SourceSpec(
        source="blockchain_info_n-unique-addresses",
        record_kind="onchain",
        event_time_column="date",
        csv_subdir="onchain/blockchain_info_n-unique-addresses",
        loader=_onchain_loader("n-unique-addresses"),
    ),
    SourceSpec(
        source="kaggle_bitcoin_sentiments_21_24",
        record_kind="sentiment",
        event_time_column="created_utc",
        csv_subdir="sentiment/kaggle_bitcoin_sentiments_21_24",
        loader=_sentiment_loader,
    ),
)

_SOURCE_SPECS_BY_NAME = {spec.source: spec for spec in SOURCE_SPECS}


def resolve_source_spec(source: str) -> SourceSpec:
    """Looks up one `SourceSpec` by its DB `source` value. Raises `ValueError`
    (not a silent `None`) for an unrecognized source -- the CLI surfaces this
    as a clear, fatal argument error.
    """
    try:
        return _SOURCE_SPECS_BY_NAME[source]
    except KeyError:
        known = ", ".join(sorted(_SOURCE_SPECS_BY_NAME))
        raise ValueError(f"unknown source {source!r}; known sources: {known}") from None


def _load_platform_csvs(spec: SourceSpec) -> pd.DataFrame:
    """Reads every CSV under this source's `seed/` and `incremental/`
    directories (PROVENANCE.md's documented layout, reused verbatim), in
    that order, concatenated and sorted by event time. Raises
    `FileNotFoundError` if no CSV exists at all -- never a silent empty read.
    """
    csv_dir = _PLATFORM_ROOT / spec.csv_subdir
    paths = sorted((csv_dir / "seed").glob("*.csv")) + sorted(
        (csv_dir / "incremental").glob("*.csv")
    )
    if not paths:
        raise FileNotFoundError(f"no CSV files found under {csv_dir}/(seed|incremental)")
    frames = [spec.loader(path) for path in paths]
    combined = pd.concat(frames, ignore_index=True)
    return combined.sort_values(spec.event_time_column).reset_index(drop=True)


def load_records(spec: SourceSpec, from_path: str) -> pd.DataFrame:
    """Resolves `--from`: `"platform-csv"` reads every seed/incremental CSV
    for this source under `data/raw/_platform/`; any other value is treated
    as a single arbitrary CSV path (single-tenant mode only, per the
    ticket's original CLI shape).
    """
    if from_path == PLATFORM_CSV_SENTINEL:
        return _load_platform_csvs(spec)
    df = spec.loader(Path(from_path))
    return df.sort_values(spec.event_time_column).reset_index(drop=True)


def _as_utc_timestamp(value: datetime) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def seed_source_for_tenant(
    tenant_id: str,
    spec: SourceSpec,
    records: pd.DataFrame,
    repository: "ConnectorRecordRepository",
    *,
    dry_run: bool = False,
) -> int:
    """Writes `records` for one `(tenant_id, spec.source)` via the matching
    `add_*_records` method -- the skip-then-append idempotency mechanism
    (ticket Design section): reads `repository.latest_event_time(tenant_id,
    spec.source)` first and filters `records` to event-time strictly greater
    than that watermark (or keeps every row, if no watermark exists yet)
    before writing. Returns the row count that qualified -- rows actually
    written, or rows that *would* be written, when `dry_run=True` (which
    makes zero calls to any `add_*_records` method).
    """
    watermark = repository.latest_event_time(tenant_id, spec.source)
    if watermark is not None:
        cutoff = _as_utc_timestamp(watermark)
        records = records[records[spec.event_time_column] > cutoff]

    if records.empty:
        return 0
    if dry_run:
        return len(records)

    records = records.copy()
    records["fetched_at"] = datetime.now(timezone.utc)
    write_method = getattr(repository, f"add_{spec.record_kind}_records")
    return write_method(tenant_id, spec.source, records)


def seed_single_source(
    tenant_id: str,
    source: str,
    from_path: str,
    repository: "ConnectorRecordRepository",
    *,
    dry_run: bool = False,
) -> int:
    """Base single-tenant mode: `--tenant-id <id> --source <source> --from
    <path-or-"platform-csv">`. Returns the row count written (or that would
    be written under `--dry-run`).
    """
    spec = resolve_source_spec(source)
    records = load_records(spec, from_path)
    return seed_source_for_tenant(tenant_id, spec, records, repository, dry_run=dry_run)


def seed_tenant_platform_history(
    tenant_id: str,
    repository: "ConnectorRecordRepository",
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """Seeds all four CSV-backed platform sources (`SOURCE_SPECS`) for one
    tenant from `data/raw/_platform/`, independently per source. Returns
    `{source: row_count}` -- rows written (or that would be written under
    `--dry-run`) per source, for CLI reporting.
    """
    return {
        spec.source: seed_source_for_tenant(
            tenant_id, spec, _load_platform_csvs(spec), repository, dry_run=dry_run
        )
        for spec in SOURCE_SPECS
    }


def fetch_all_tenant_ids(
    gateway_api_url: str,
    operator_token: str,
    *,
    client: "httpx.Client | None" = None,
) -> list[str]:
    """Enumerates every tenant via `gateway-api`'s operator-authenticated
    `GET /tenants` (`SETUP-011`) -- never a direct read of the `identity`
    schema (CLAUDE.md: "no service reads another service's DB schema
    directly"). Raises whatever `httpx` raises on a connection failure
    (e.g. `httpx.ConnectError`) or a non-2xx response (`httpx.HTTPStatusError`
    via `raise_for_status`) -- the caller (the CLI) must treat both as a
    fatal, non-zero-exit error, never a silent empty-tenant no-op.
    """
    owns_client = client is None
    http_client = client if client is not None else httpx.Client(base_url=gateway_api_url, timeout=30.0)
    try:
        response = http_client.get("/tenants", headers={"X-Operator-Token": operator_token})
        response.raise_for_status()
        payload = response.json()
        return [item["id"] for item in payload["items"]]
    finally:
        if owns_client:
            http_client.close()


def seed_all_existing_tenants(
    gateway_api_url: str,
    operator_token: str,
    repository: "ConnectorRecordRepository",
    *,
    dry_run: bool = False,
    client: "httpx.Client | None" = None,
) -> dict[str, dict[str, int]]:
    """`--all-existing-tenants` mode: enumerates every tenant via
    `fetch_all_tenant_ids`, then writes a full, independent copy of every row
    from all four CSV-backed sources into each tenant's own rows (no tenant
    special-cased as "the" demo tenant -- the founder's resolved
    tenant-attachment decision, see README.md). Returns
    `{tenant_id: {source: row_count}}`. Propagates any exception
    `fetch_all_tenant_ids` raises unchanged -- `gateway-api` unreachable must
    fail this whole call before any tenant is written to, not degrade to a
    partial silent success.
    """
    tenant_ids = fetch_all_tenant_ids(gateway_api_url, operator_token, client=client)
    return {
        tenant_id: seed_tenant_platform_history(tenant_id, repository, dry_run=dry_run)
        for tenant_id in tenant_ids
    }
