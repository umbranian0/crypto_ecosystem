"""On-chain connector: blockchain.info public charts API.

Covers both series used in the thesis (docs/da-tese-ao-produto.md section
1.2's "hash-rate" exogenous feature) and available as a bonus on-chain proxy
("n-unique-addresses"). Same connector class, parameterized by chart name —
one new on-chain metric from this API is a one-line instantiation, not a new
class, since blockchain.info's chart endpoints all share one response shape.

No API key required — blockchain.info's chart endpoints are public.
Data is daily-granularity and reported with several days of lag/irregular
spacing in practice (visible in the seed file), so "since" filtering is done
by requesting from blockchain.info's `start` parameter and then filtering
client-side for anything at or before the watermark, since the API's `start`
boundary is inclusive-but-approximate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import pandas as pd
import requests

from .base import FetchResult, IngestionSource, run_incremental, utcnow

BLOCKCHAIN_INFO_CHARTS_URL = "https://api.blockchain.info/charts/{chart_name}"


class BlockchainInfoConnector(IngestionSource):
    """Fetches one blockchain.info chart series, e.g. 'hash-rate' or 'n-unique-addresses'."""

    def __init__(self, chart_name: str, session: requests.Session | None = None):
        self.chart_name = chart_name
        self.name = f"blockchain_info_{chart_name}"
        self._session = session or requests.Session()

    def fetch(
        self,
        since: datetime,
        should_cancel: "Callable[[], bool] | None" = None,
        on_progress: "Callable[[int], None] | None" = None,
    ) -> FetchResult:
        """Cancellation ceiling (INGEST-022): this method makes exactly one
        blocking `GET`, with no loop, so `should_cancel()` is checked exactly
        once, before that call is issued -- if it returns `True`, the `GET` is
        never made and an empty, `cancelled=True` `FetchResult` is returned
        immediately. `on_progress` is never called; there is no mid-fetch
        checkpoint to report from. Once the request has started, cancellation
        cannot take effect: a call that begins and completes normally always
        reports `cancelled=False`, regardless of what `should_cancel()` might
        return if it were checked again after this point (it never is).
        Both `should_cancel` and `on_progress` are accepted here only for
        interface uniformity with `IngestionSource.fetch`'s signature (every
        connector takes both parameters) -- this connector's own shape gives
        `on_progress` nothing to report and `should_cancel` only one point at
        which to matter.
        """
        if should_cancel is not None and should_cancel():
            return FetchResult(source=self.name, fetched_at=utcnow(), records=pd.DataFrame(), cancelled=True)

        # blockchain.info requires a non-empty `timespan` even when `start` is given;
        # it does NOT extend the window beyond "now", so a generous span (comfortably
        # longer than any realistic gap between connector runs) plus client-side
        # filtering below is what actually bounds the result to `since`.
        span_days = max((utcnow() - since).days + 30, 90)
        params = {
            "start": since.strftime("%Y-%m-%d"),
            "format": "json",
            "sampled": "false",
            "timespan": f"{span_days}days",
        }
        response = self._session.get(
            BLOCKCHAIN_INFO_CHARTS_URL.format(chart_name=self.chart_name),
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        values = payload.get("values", [])
        df = pd.DataFrame(values)
        if not df.empty:
            df = df.rename(columns={"x": "timestamp_unix", "y": self.chart_name})
            df["date"] = pd.to_datetime(df["timestamp_unix"], unit="s", utc=True)
            df = df[df["date"] > pd.Timestamp(since)]
            df = df[["timestamp_unix", "date", self.chart_name]].reset_index(drop=True)

        return FetchResult(source=self.name, fetched_at=utcnow(), records=df)


# Watermarks: last timestamp covered by each historical seed file, per PROVENANCE.md.
SEED_WATERMARKS = {
    "hash-rate": datetime(2025, 7, 5, tzinfo=timezone.utc),
    "n-unique-addresses": datetime(2025, 7, 19, tzinfo=timezone.utc),
}

# Bitcoin genesis block date -- verified as the real earliest-available
# `values` entry (`x=1230940800`) for both `hash-rate` and `n-unique-addresses`
# via `GET https://api.blockchain.info/charts/{chart_name}?start=2009-01-01
# &format=json&sampled=false&timespan=6000days` (INGEST-013). Chart-name
# independent -- confirmed true for both charts this connector serves.
BITCOIN_GENESIS_DATE = datetime(2009, 1, 3, tzinfo=timezone.utc)


def default_backfill_start() -> datetime:
    """Default backfill depth for a brand-new tenant's first DB crawl
    (INGEST-013) -- distinct from `SEED_WATERMARKS` above, which is only the
    CSV historical-seed-file cutoff used by this module's own `__main__`
    block, unrelated to a tenant's own per-tenant DB history. Returns the
    verified Bitcoin genesis block date (see `BITCOIN_GENESIS_DATE`), not a
    per-chart value, since it holds for both charts this connector serves.
    """
    return BITCOIN_GENESIS_DATE


if __name__ == "__main__":
    for chart_name, seed_watermark in SEED_WATERMARKS.items():
        run_incremental(
            BlockchainInfoConnector(chart_name),
            incremental_dir=f"data/raw/_platform/onchain/blockchain_info_{chart_name}/incremental",
            timestamp_column="date",
            seed_watermark=seed_watermark,
        )
