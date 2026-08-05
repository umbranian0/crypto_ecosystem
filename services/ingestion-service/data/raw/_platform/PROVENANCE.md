# Raw-zone provenance — `_platform` archive

This is the local-disk stand-in for the raw zone's `_platform` prefix (docs/solution-design.md section 3.2's path scheme `raw/{tenant_id}/{source}/{date}/...`, adapted: `_platform` instead of a real `tenant_id`, since this data is sourced by the platform itself — market/on-chain/sentiment connectors — not uploaded by a client). Once `infra/` (trigger #4) stands up MinIO/S3, this directory's contents migrate there unchanged in structure, only in location.

Every source folder below has `seed/` (historical data copied in on 2026-08-05, one-time) and `incremental/` (where each connector's future runs append new files, one per fetch, named `{fetched_at:%Y-%m-%d}.csv`).

## price/binance_btcusdt_1h

- **Seed source**: `jupyter_notebooks/data/btc1h_usdt_part1.csv` + `part2.csv` (copied, not moved — the notebooks remain self-contained research artifacts and don't depend on this location).
- **Seed coverage**: 2018-01-01 → **2025-01-09 17:00:00 UTC** (last row of `seed_part2.csv`).
- **Connector**: `connectors/binance_price.py`, `BinancePriceConnector`. Public Binance REST API, no key required.
- **⚠️ Raw/processed boundary caveat**: the seed file is NOT purely raw — it already carries ~200 `ta`-library technical indicators (volatility bands, volume indicators, etc.) computed in the original thesis pipeline. That blurs the raw/processed distinction this architecture otherwise enforces. The connector going forward fetches **pure OHLCV only** (`open_time, open, high, low, close, volume, close_time, quote_volume, trades, taker_buy_base, taker_buy_quote`) — indicator computation belongs to the processing/feature-engineering layer (solution-design.md section 3.3), not this connector. Anyone consuming the seed file directly for feature work should be aware its later columns won't exist in `incremental/` files.
- **Watermark for next fetch**: `connectors/binance_price.py:default_seed_watermark()` — update this if/when the seed file changes.

## onchain/blockchain_info_hash-rate

- **Seed source**: `jupyter_notebooks/data/hash_rate.csv`.
- **Seed coverage**: 2009-01-10 → **2025-07-05** (irregular daily-ish granularity, matches blockchain.info's own reporting cadence — gaps in the seed are the source's actual behavior, not a bug).
- **Connector**: `connectors/blockchain_onchain.py`, `BlockchainInfoConnector(chart_name="hash-rate")`. Public blockchain.info charts API, no key required.

## onchain/blockchain_info_n-unique-addresses

- **Seed source**: `jupyter_notebooks/data/n-unique-addresses.csv`.
- **Seed coverage**: 2009-01-03 → **2025-07-19**.
- **Connector**: same class, `BlockchainInfoConnector(chart_name="n-unique-addresses")`.

## sentiment/kaggle_bitcoin_sentiments_21_24

- **Seed source**: `jupyter_notebooks/data/bitcoin_sentiments_21_24.csv`. Per `jupyter_notebooks/data/bibliografia.txt`, originally a Kaggle dataset (news headlines + precomputed sentiment score), **not a live-crawlable API** — this is a frozen historical dump, seed-only, no `incremental/` folder for this specific source.
- **Seed coverage**: 2021-11-05 → **2024-09-12**.
- **Live replacement going forward**: `sentiment/reddit_vader/` (see below) — a different underlying data source (Reddit posts, not news headlines), chosen because there's no equivalent free ongoing news-sentiment API without a paid tier. If the two sentiment series are ever combined for feature engineering, document that discontinuity explicitly — don't let a report imply one continuous sentiment signal across the boundary.

## sentiment/reddit_vader

- **Seed**: none — this source starts fresh.
- **Connector**: `connectors/reddit_sentiment.py`, `RedditSentimentConnector`. Requires Reddit API credentials via environment variables (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`) — see the connector's module docstring. Default subreddits: r/Bitcoin, r/CryptoCurrency, matching the `reddit_*` feature naming already used in `jupyter_notebooks/data/crypto_data_news_reddit_final.csv`.
- **Watermark for first fetch**: 2024-09-12 (the Kaggle seed's end date) — chosen as the earliest reasonable overlap point, not because Reddit was ever the source of that seed. See `connectors/reddit_sentiment.py:default_seed_watermark()`.

## Running the connectors

Each connector module is runnable standalone for now (`python -m connectors.binance_price` etc. from `services/ingestion-service/`) — this predates the service's own trigger (#6, per implementation-plan.md) having fully fired for a REST API wrapper, so there's no `ingestion-service` HTTP endpoint yet. Scheduling (cron, or a Prefect flow per solution-design.md section 3.3) is a follow-up once `infra/` exists.
