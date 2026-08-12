# ingestion-service

**Status: partially scaffolded, ahead of schedule.** The service's REST API/upload endpoint (trigger #6) and market/sentiment connectors (originally trigger #10) were both formally deferred — but the connectors and a raw-zone archive were pulled forward on 2026-08-05 at explicit user request, independent of the FastAPI service wrapper. What exists: `connectors/` (runnable standalone Python, no HTTP layer yet) and `data/raw/_platform/` (seeded historical archive + incremental drop zones). What's still not built: the FastAPI app, the `ingestion` Postgres schema, the upload API, and the data-quality gate.

Formerly `data-pipeline/`. See [../../docs/solution-design.md](../../docs/solution-design.md) section 3.1 and [../../docs/implementation-plan.md](../../docs/implementation-plan.md).

**Owns**: the `ingestion` Postgres schema (`datasets`, not yet built), the raw and processed object-storage zones (`raw/{tenant_id}/...`, `processed/{tenant_id}/...` — currently a local-disk stand-in at `data/raw/_platform/`, see `data/raw/_platform/PROVENANCE.md`), the upload API (not yet built), market/sentiment connectors (built: price, hash-rate, unique-addresses, Reddit sentiment), and the data-quality gate (not yet built).

**Does not own**: anything downstream of "processed dataset ready" — validation and reporting are separate services. Also does not own feature engineering / technical indicators (see the raw/processed boundary caveat in `data/raw/_platform/PROVENANCE.md` for the price connector specifically) — that belongs to the processing layer (solution-design.md section 3.3).

**Design notes**:
- Each external data source (client upload, exchange API, sentiment/on-chain API) implements a common `IngestionSource` interface (`fetch(since) -> FetchResult`, in `connectors/base.py`) — the Adapter pattern referenced in implementation-plan.md section 7. Adding a new source means one new adapter class, nothing else in the service changes. Implemented so far: `BinancePriceConnector`, `BlockchainInfoConnector` (parameterized for hash-rate and n-unique-addresses), `RedditSentimentConnector`.
- The causal-lag requirement (recording *when data became known*, not just when it happened) is enforced in this interface via `FetchResult.fetched_at`, not left to each adapter's discretion — this is the exact leakage failure mode one layer up from the validation engine (docs section 1.6).
- Connectors are currently run standalone (`python -m connectors.binance_price` etc. from this directory) — no scheduler wired up yet. Scheduling (cron or a Prefect flow) is a follow-up once `infra/` exists (trigger #4).

**Contract**: FastAPI service, not yet built. Expected endpoints once built: `POST /datasets` (upload), `GET /datasets/{id}`, `GET /datasets/{id}/quality-report`.

**Testing (added 2026-08-09, previously absent)**: `tests/` covers `connectors/base.py` (`latest_watermark`, `run_incremental`) and all three connectors' `fetch()` methods, using a fake `requests.Session`/fake `praw` client injected via each connector's existing constructor parameter rather than hitting real APIs. Setup (no `pyproject.toml` yet, plain `requirements.txt`):
```
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt pytest pytest-cov
.venv/Scripts/python.exe -m pytest tests/ -q
```

**CI**: `.github/workflows/ci.yml` runs this module's test suite on every push/PR.

**Coverage**: run tests with coverage locally via `.venv/Scripts/python.exe -m pytest tests/ -q --cov=connectors --cov-report=term-missing` (no coverage threshold is enforced — CI prints the report, it never fails the build on a percentage).

**Dependency upgrades**: see [../../docs/dependency-upgrade-policy.md](../../docs/dependency-upgrade-policy.md) for this platform's cadence.
