"""Price connector: Binance public klines REST API.

Deliberately fetches raw OHLCV only (open_time, open, high, low, close,
volume, close_time, quote_volume, trades, taker_buy_base, taker_buy_quote) —
NOT the ~200 `ta`-library technical indicators baked into the historical seed
file (jupyter_notebooks/data/btc1h_usdt_part*.csv, copied into this service's
raw zone at data/raw/_platform/price/binance_btcusdt_1h/seed/).

That seed file blurs raw and processed data together. Going forward, this
connector keeps the raw zone honestly raw; indicator computation belongs to
the feature-engineering step in services/data-pipeline processing
(docs/solution-design.md section 3.3), not the ingestion connector. See
data/raw/_platform/PROVENANCE.md for the full note on this seed caveat.

No API key required — Binance's public market-data endpoints are unauthenticated.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from .base import FetchResult, IngestionSource, latest_watermark, utcnow

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
MAX_KLINES_PER_REQUEST = 1000  # Binance's per-request cap

RAW_COLUMNS = [
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
    "ignore",
]


class BinancePriceConnector(IngestionSource):
    """Fetches OHLCV klines for one symbol/interval pair, e.g. BTCUSDT @ 1h."""

    def __init__(self, symbol: str = "BTCUSDT", interval: str = "1h", session: requests.Session | None = None):
        self.symbol = symbol
        self.interval = interval
        self.name = f"binance_price_{symbol.lower()}_{interval}"
        self._session = session or requests.Session()

    def fetch(self, since: datetime) -> FetchResult:
        start_ms = int(since.timestamp() * 1000) + 1  # strictly after `since`
        end_ms = int(utcnow().timestamp() * 1000)

        all_rows: list[list] = []
        cursor = start_ms
        while cursor < end_ms:
            batch = self._fetch_batch(cursor, end_ms)
            if not batch:
                break
            all_rows.extend(batch)
            last_open_time = batch[-1][0]
            next_cursor = last_open_time + 1
            if next_cursor <= cursor:
                break  # safety: avoid infinite loop if the API returns no forward progress
            cursor = next_cursor
            if len(batch) < MAX_KLINES_PER_REQUEST:
                break  # fewer than a full page means we've caught up
            time.sleep(0.2)  # stay well under Binance's public rate limit

        df = pd.DataFrame(all_rows, columns=RAW_COLUMNS)
        if not df.empty:
            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
            df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
            df = df.drop(columns=["ignore"])
            df.insert(0, "symbol", self.symbol)

        return FetchResult(source=self.name, fetched_at=utcnow(), records=df)

    def _fetch_batch(self, start_ms: int, end_ms: int) -> list[list]:
        params = {
            "symbol": self.symbol,
            "interval": self.interval,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": MAX_KLINES_PER_REQUEST,
        }
        response = self._session.get(BINANCE_KLINES_URL, params=params, timeout=30)
        response.raise_for_status()
        return response.json()


def default_seed_watermark() -> datetime:
    """Last timestamp covered by the historical seed file, per PROVENANCE.md."""
    return datetime(2025, 1, 9, 17, 0, 0, tzinfo=timezone.utc)


if __name__ == "__main__":
    incremental_dir = "data/raw/_platform/price/binance_btcusdt_1h/incremental"
    since = latest_watermark(incremental_dir, "open_time", default_seed_watermark())

    connector = BinancePriceConnector()
    result = connector.fetch(since=since)
    print(f"{connector.name}: fetched {len(result.records)} rows since {since}")
    if not result.is_empty():
        out_path = f"{incremental_dir}/{result.fetched_at:%Y-%m-%d}.csv"
        result.records.to_csv(out_path, index=False)
        print(f"wrote {out_path}")
    else:
        print("no new rows, nothing written")
