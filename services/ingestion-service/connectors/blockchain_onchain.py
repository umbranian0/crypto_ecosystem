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

import pandas as pd
import requests

from .base import FetchResult, IngestionSource, utcnow

BLOCKCHAIN_INFO_CHARTS_URL = "https://api.blockchain.info/charts/{chart_name}"


class BlockchainInfoConnector(IngestionSource):
    """Fetches one blockchain.info chart series, e.g. 'hash-rate' or 'n-unique-addresses'."""

    def __init__(self, chart_name: str, session: requests.Session | None = None):
        self.chart_name = chart_name
        self.name = f"blockchain_info_{chart_name}"
        self._session = session or requests.Session()

    def fetch(self, since: datetime) -> FetchResult:
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


if __name__ == "__main__":
    for chart_name, watermark in SEED_WATERMARKS.items():
        connector = BlockchainInfoConnector(chart_name)
        result = connector.fetch(since=watermark)
        print(f"{connector.name}: fetched {len(result.records)} rows since {watermark}")
        if not result.is_empty():
            out_path = (
                f"data/raw/_platform/onchain/blockchain_info_{chart_name}/incremental/"
                f"{result.fetched_at:%Y-%m-%d}.csv"
            )
            result.records.to_csv(out_path, index=False)
            print(f"wrote {out_path}")
