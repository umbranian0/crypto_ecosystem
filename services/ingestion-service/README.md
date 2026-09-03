# ingestion-service

**Status: partially scaffolded, ahead of schedule.** The service's REST API/upload endpoint (trigger #6) and market/sentiment connectors (originally trigger #10) were both formally deferred — but the connectors and a raw-zone archive were pulled forward on 2026-08-05 at explicit user request, independent of the FastAPI service wrapper. `INGEST-007` is a further, explicitly disclosed override of the same trigger #6: no pilot client has requested an upload API yet, but the bare FastAPI app (`src/app/main.py`, `GET /health`) was built anyway to unblock `INGEST-009`/`VS-023`/`DASH-108`, which each need a running `ingestion-service` process to build against. What exists: `connectors/` (runnable standalone Python, no HTTP layer yet), `data/raw/_platform/` (seeded historical archive + incremental drop zones), the `ingestion` Postgres schema (`INGEST-002`, see below), and now a bare FastAPI app skeleton (`INGEST-007`: `GET /health` only, wired into `infra/docker-compose.yml` on port 8003 — see the "FastAPI app" note below). What's still not built: the upload API and the data-quality gate.

Formerly `data-pipeline/`. See [../../docs/solution-design.md](../../docs/solution-design.md) section 3.1/8 and [../../docs/implementation-plan.md](../../docs/implementation-plan.md).

**Owns**: the `ingestion` Postgres schema (`INGEST-002`, built: `price_ohlcv`, `onchain_metric`, `sentiment_score`, `connector_credentials`, `crawl_runs` — see solution-design.md section 8.2, `migrations/`), the raw and processed object-storage zones (`raw/{tenant_id}/...`, `processed/{tenant_id}/...` — currently a local-disk stand-in at `data/raw/_platform/`, see `data/raw/_platform/PROVENANCE.md`), the upload API (not yet built), market/sentiment connectors (built: price, hash-rate, unique-addresses, Reddit sentiment), and the data-quality gate (not yet built).

**Does not own**: anything downstream of "processed dataset ready" — validation and reporting are separate services. Also does not own feature engineering / technical indicators (see the raw/processed boundary caveat in `data/raw/_platform/PROVENANCE.md` for the price connector specifically) — that belongs to the processing layer (solution-design.md section 3.3).

**Design notes**:
- Each external data source (client upload, exchange API, sentiment/on-chain API) implements a common `IngestionSource` interface (`fetch(since) -> FetchResult`, in `connectors/base.py`) — the Adapter pattern referenced in implementation-plan.md section 7. Adding a new source means one new adapter class, nothing else in the service changes. Implemented so far: `BinancePriceConnector`, `BlockchainInfoConnector` (parameterized for hash-rate and n-unique-addresses), `RedditSentimentConnector`.
- The causal-lag requirement (recording *when data became known*, not just when it happened) is enforced in this interface via `FetchResult.fetched_at`, not left to each adapter's discretion — this is the exact leakage failure mode one layer up from the validation engine (docs section 1.6).
- Connectors are currently run standalone (`python -m connectors.binance_price` etc. from this directory) — no scheduler wired up yet. Scheduling (cron or a Prefect flow) is a follow-up once `infra/` exists (trigger #4).
- **Accepted tradeoff — N× external API load** (`INGEST-005`): each tenant's crawler runs independently against the same public upstream endpoint (Binance, blockchain.info) with its own watermark (`latest_watermark_from_db`, resolved per `(tenant_id, source)`). With N tenants configured for the same `source`, that source is fetched N times per scheduling interval — no cross-tenant dedup or shared response cache is built. This is a deliberate per-tenant-crawler design decision (tenant isolation and independent watermarks/credentials are simpler to reason about without a shared-fetch layer in between), not an oversight to silently fix later; it should be revisited explicitly if/when pilot-scale tenant counts against a single free-tier public API start to matter for rate limits, not patched around quietly in a connector.

**`ingestion` Postgres schema** (`INGEST-002`, `src/app/models.py` + `migrations/`): five tables, column-for-column per solution-design.md section 8.2 — `price_ohlcv`, `onchain_metric`, `sentiment_score` (each a TimescaleDB hypertable, partitioned on `open_time`/`timestamp`/`created_utc` respectively, primary key widened to include that column per the same TimescaleDB constraint `validation-service`'s `INF-010` hit), `connector_credentials` (ciphertext-only `bytea` columns — `INGEST-011` owns the actual encrypt/decrypt code), `crawl_runs`. Row-level security (`ENABLE`/`FORCE ROW LEVEL SECURITY` + a `tenant_isolation` policy) is on all five, byte-identical in shape to `validation-service`/`gateway-api`'s own RLS migrations. Alembic environment scoped to the `ingestion` schema (`version_table_schema="ingestion"`, the same `INF-005` fix `validation-service`/`gateway-api` already apply) so this service's `alembic_version` bookkeeping never collides with the other services sharing the same Postgres instance. `migrations/env.py` also issues `CREATE SCHEMA IF NOT EXISTS ingestion` itself (unlike its sibling services, whose schemas are pre-created by `infra/postgres-init/01-create-schemas.sql`) because that script does not yet list `ingestion` — folding it in there for consistency is a disclosed follow-up, out of this ticket's file scope (`services/ingestion-service/` only).

**Hypertable `(tenant_id, source, fetched_at)` composite indexes** (`INGEST-018`/`DBOPT-007`,
`migrations/versions/0006_add_hypertables_tenant_source_fetched_at_index.py`): `price_ohlcv`,
`onchain_metric`, `sentiment_score` each gained `ix_<table>_tenant_source_fetched_at`, a composite
btree on `(tenant_id, source, fetched_at)` (`fetched_at` trailing, not leading -- deliberate, see the
migration's own docstring), issued against each hypertable's root table. Serves
`PostgresConnectorRecordRepository.latest_fetched_at`'s `SELECT max(fetched_at) FROM <table> WHERE
tenant_id = :tenant_id AND source = :source` query, called by `connectors/base.py`'s incremental-fetch
path on every scheduled crawl -- `fetched_at` is not the partitioning column, so TimescaleDB chunk
exclusion could not help this query before this index existed. Live-verified against the real Compose
Postgres container: propagation to all pre-existing chunks confirmed for both `price_ohlcv` (472/472)
and `onchain_metric` (922/922), and the query plan now uses a backward `Index Only Scan` per chunk
instead of a full per-chunk `Seq Scan`/`Partial Aggregate`.

**`crawl_runs` composite index** (`INGEST-017`/`DBOPT-006`,
`migrations/versions/0005_add_crawl_runs_tenant_source_fetched_at_index.py`): `ingestion.crawl_runs`
gained `ix_crawl_runs_tenant_source_fetched_at`, a composite btree on `(tenant_id, source,
fetched_at DESC)`, Postgres-only-guarded like every other index/DDL migration in this service. Serves
`PostgresConnectorRecordRepository.latest_crawl_run`'s `WHERE tenant_id = :tenant_id AND source =
:source ORDER BY fetched_at DESC LIMIT 1` query (backing the connector/dataset status surface) and
doubles as the RLS `tenant_id` index this table was also missing. The real table has only 8 rows this
session -- too small to show a measurable timing delta -- so this was verified structurally rather than
by speedup: live `EXPLAIN (ANALYZE, BUFFERS)` against the real container still shows a `Seq Scan`
(expected, honest small-table planner behavior, same disclosed pattern as `GW-025`), but forcing `SET
enable_seqscan = off` confirms the planner switches cleanly to `Index Scan using
ix_crawl_runs_tenant_source_fetched_at`, proving the index is real and usable.

**Hypertable chunk sizing** (`INGEST-016`/`DBOPT-004`, `migrations/versions/0004_retune_hypertable_chunk_intervals.py`): `0003_convert_to_hypertables.py`'s `create_hypertable` calls used TimescaleDB's 7-day default `chunk_time_interval`, which against 9-17 years of real backfilled history produced hundreds of undersized chunks (`price_ohlcv`: 472 chunks, ~258 rows/chunk; `onchain_metric`: 922 chunks, ~21 rows/chunk), hurting every query against these tables on chunk-count-driven planning cost. `INGEST-016` retunes all three hypertables' (`price_ohlcv`/`onchain_metric`/`sentiment_score`) `chunk_time_interval` to 90 days via `set_chunk_time_interval`. **This only affects chunks created after the change** -- the existing 472/922 chunks on `price_ohlcv`/`onchain_metric` are not retroactively resized or merged; only chunks created from this point forward span 90 days instead of 7. See VS-027 for the `validation-service` half of the same DBOPT-004 story.

**Compression policy -- blocked, not implemented (`INGEST-020`/`DBOPT-008`, ingestion half)**:
`DBOPT-008` planned `ALTER TABLE ... SET (timescaledb.compress, ...)` +
`add_compression_policy` (90-day threshold, `compress_segmentby = 'tenant_id,
source'`, matching the same query shape `read_series`/`list_datasets`/
`latest_fetched_at` already filter on) on `price_ohlcv`/`onchain_metric`/
`sentiment_score`. **Live-verified against this repo's real Compose Postgres
container (TimescaleDB 2.29.1) before writing any migration**:
`ALTER TABLE ... SET (timescaledb.compress, ...)` fails outright --
`ERROR: columnstore cannot be used on table with row security` -- the moment
`ENABLE ROW LEVEL SECURITY` is set on the target table, **with or without
`FORCE`**, and independent of whether any policy actually exists yet. This
was reproduced against a disposable scratch hypertable
(`scratch_ingest020.probe`/`probe2`/`probe3`, created and fully dropped in
the same session -- no trace left in the real `ingestion`/`naive_first`
schema): `FORCE ROW LEVEL SECURITY` + a real policy fails, plain `ENABLE ROW
LEVEL SECURITY` + a real policy fails identically, and the same
`ALTER TABLE ... SET (timescaledb.compress, ...)` on an otherwise-identical
hypertable with no RLS at all succeeds cleanly -- isolating the cause to the
`rowsecurity` reloption itself, not to `FORCE` specifically or to policy
evaluation. `price_ohlcv`/`onchain_metric`/`sentiment_score` all carry
`FORCE ROW LEVEL SECURITY` (`INGEST-002`), a locked-in multi-tenant
isolation invariant not relaxed for this ticket, and this session's own
execution safeguards refuse to run any migration that disables RLS even
transiently (the same refusal `INGEST-019`'s continuous-aggregate work hit
and treated as authoritative) -- so unlike `INGEST-019`/`DBOPT-009`, which
had a materialize-a-separate-view substitute available, there is no
equivalent substitute here: compression is a physical storage transform on
the hypertable itself, not something that can be read through a side view
instead. **No `0008` migration was written** -- writing one that calls
`SET (timescaledb.compress, ...)` directly against these three real tables
would fail identically against the real container, failing AC1 outright
rather than partially satisfying it. This is escalated to the Tech Lead as a
design-level blocker (same category as `INGEST-019`'s RLS-vs-continuous-
aggregate finding, this time with no available workaround) rather than
routed around silently. Zero rows/schema objects were added to or left
behind in the real `ingestion`/`naive_first` database by this
investigation -- see `docs/tickets/INGEST-020.md`'s Outcome notes for the
full reproduction transcript.

Setup/run (no live app yet, migrations only):
```
uv venv && uv pip install -e .
DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:5432/<db> uv run alembic upgrade head
```
Live-verified against this repo's real Compose Postgres (`timescale/timescaledb:latest-pg16`): schema/hypertables/RLS all confirmed via `psql`, and RLS cross-tenant isolation confirmed by connecting as the non-superuser `naive_first_app` role (INF-014's own verification method) with `SET app.tenant_id = ...` set to each of two tenants in turn.

**FastAPI app** (`INGEST-007`, `src/app/main.py` + `src/app/dependencies/repositories.py`): a bare app skeleton, mirroring `validation-service`'s/`reporting-service`'s own `main.py` shape exactly — `naive_first_common.configure_structured_logging()` + `CorrelationIdMiddleware` wired at import time (OPS-006), `GET /health` doing a real `SELECT 1` against the `ingestion` schema's engine (OPS-005-01: `200` on success, `503` with a fixed generic body on failure, no connection details leaked). No upload/data-quality routers exist yet (`INGEST-008`/`INGEST-009`). `Dockerfile` mirrors `reporting-service`'s exactly (uv-managed, non-root `appuser`, `libs` additional build context); `infra/docker-compose.yml` runs it as `ingestion-service` on host port 8003 (`INGESTION_SERVICE_PORT`, `127.0.0.1`-bound like every other internal-only service), `DATABASE_URL` using the non-superuser `naive_first_app` role. Port 8003 was already committed by `GW-021`'s `INGESTION_SERVICE_URL` client default before this ticket — this Dockerfile/Compose entry matches that existing wiring rather than picking a fresh port.

**Contract**: FastAPI service. Built so far: `GET /health` (`INGEST-007`); `POST /connectors/{source}/run` (`INGEST-008`, tenant-authenticated crawl trigger — see below); `GET /datasets`, `GET /datasets/{source}/series`, `GET /connectors/{source}/status` (`INGEST-009` revised — see below); `GET /connectors/credentials-status` (`INGEST-012`, tenant-authenticated credential-presence check — see below). Still planned: the upload API and the data-quality gate. See solution-design.md section 8.3 for the fuller planned REST surface. **There is deliberately no `GET /datasets/{id}` static-lookup endpoint** — the backlog's original sketch is superseded, see the `INGEST-009` note below.

**`POST /connectors/{source}/run`** (`INGEST-008`, lock-gated and asynchronous since `INGEST-015`,
`src/app/routers/connectors.py`): tenant-authenticated (`Depends(naive_first_common.get_tenant_context)`,
`X-Tenant-Id`) crawl trigger for one connector. `source` is the connector's own `connector.name` value,
not an invented route-level name: `binance_price_btcusdt_1h`, `blockchain_info_hash-rate`,
`blockchain_info_n-unique-addresses`, `reddit_vader_sentiment`. An unknown `source` is a `404`; a
malformed/out-of-range `since` override is a `422` (three cases, see below); for the Reddit source
only, missing stored credentials (`CredentialRepository.get_credentials`) is also a `422`, rather than
the `RuntimeError` that would otherwise surface mid-`fetch()` as an unhandled `500`. All of this
validation happens *before* the per-`(tenant_id, source)` lock below is touched, so a bad request fails
the same way whether or not a crawl happens to be in flight for that source.

**Asynchronous, lock-gated execution** (`INGEST-015`, fixing two QA-reproduced bugs: a real ~70s/
79,127-row Binance backfill blocking the request that long, and two concurrent requests for the same
`(tenant_id, source)` independently resolving the same `since` watermark and both attempting to write
the same rows — reproduced live as an unhandled `500` Postgres `UniqueViolation`). Once validation
passes, the handler calls `registry.try_acquire(tenant_id, connector.name)`
(`app.crawl_registry.CrawlRegistry`, `INGEST-014`); if a crawl for that `(tenant_id, source)` is already
in flight, this returns `False` and the request gets an immediate `409` (`"crawl already in progress for
connector <source>"`) with no DB read/write at all. If the lock is acquired, the handler resolves the
watermark (`connectors/base.py`'s `latest_watermark_from_db`, falling back to the `since` override or
each connector's `default_backfill_start()` on a first crawl — unchanged logic, now run under the lock,
which is what actually closes the race), writes one `"queued"` `crawl_runs` row via the existing
`record_crawl_run(...)` (a third status value alongside `"completed"`/`"failed"`, needing no schema
change since `status` is a plain `String` column), schedules the fetch-and-write work as a
`BackgroundTasks.add_task(_execute_crawl, ...)`, and returns `202` immediately with
`ConnectorRunAcceptedResponse` — `{source, status: "queued", since, queued_at}`. This is a **breaking
response-shape change**: the crawl's outcome (`row_count`/`fetched_at`/final `status`) is not known at
response time and is no longer in this body — poll `GET /connectors/{source}/status` (`INGEST-009`,
unchanged) for the outcome, keyed by the same `(tenant_id, source)` pair. If anything raises between a
successful `try_acquire` and successfully scheduling the background task (e.g. the "queued" write
itself failing), the lock is released before the exception propagates — no code path leaves
`try_acquire` succeeding without a matching `release`.

`_execute_crawl` (the background task body) calls `connector.fetch(since=since)`, writes rows through
the same `add_{price,onchain,sentiment}_records` dispatch `connectors/base.py`'s `run_incremental`
DB-write branch already uses, then calls `record_crawl_run(..., status="completed")`
(`row_count=0` for an empty-but-successful fetch, same as before this ticket). On *any* exception —
including one raised by `fetch()` itself, not only a subsequent write failure as before this ticket —
it instead writes `record_crawl_run(..., status="failed")`. A `finally` block calls
`registry.release(tenant_id, connector.name)` unconditionally, on every exit path, so a background-task
exception never leaves a `(tenant_id, source)` permanently locked out of future crawls.
`app.dependencies.repositories.get_connector_record_repository`/`get_credential_repository` currently
only resolve to the Postgres-backed repositories (`INGEST-003`/`INGEST-004`) — there is no SQLite
fallback yet (tenant-scoped RLS session setup is Postgres-specific), so a real `DATABASE_URL` is
required to exercise this route outside of tests. `gateway-api`'s proxy (`GW-024`) and
`dashboard-web`'s trigger-result fragment (`DASH-115`) are follow-up tickets sequenced after this one,
since they consume the new `202` response shape.

**Crawl mutual-exclusion primitive** (`INGEST-014`, `src/app/crawl_registry.py`, wired into
`POST /connectors/{source}/run` by `INGEST-015` above): a per-`(tenant_id, source)` in-process lock
(`CrawlRegistry.try_acquire`/`release`, backed by a single `threading.Lock` + `set[tuple[str, str]]`,
exposed as a `get_crawl_registry()`/`CrawlRegistryDep` module-level singleton alongside
`app/dependencies/repositories.py`'s existing `Engine` one). **Disclosed limitation**: this lock is
process-local only, not shared across multiple `ingestion-service` replicas/processes — a known gap if
this service is ever scaled horizontally, the same kind of disclosed limitation as the
encryption-key-rotation gap noted above.

`since` query parameter (`INGEST-013`): an optional ISO 8601 date/datetime, honored **only** on a
tenant's first-ever crawl of `(tenant_id, source)` (`latest_watermark_from_db` returns `None`); on any
later crawl of that same source it has zero effect, the existing "continue from the latest stored
watermark" behavior is unchanged. When omitted on a first crawl, each connector's new
`default_backfill_start()` is used instead of the old CSV-seed-derived fallback: Binance
(`2017-08-17 00:00:00 UTC`) and both on-chain charts (`2009-01-03 00:00:00 UTC`, the Bitcoin genesis
block date) are real, verified earliest-available dates confirmed against those sources' own public
APIs; Reddit's default (`utcnow() - 5 years`) is an unverified convention, not a real data boundary —
`praw`'s `.new()` only ever returns each subreddit's most recent ~1000 submissions regardless of how
far back `since` is set, so no genuine "earliest available" concept exists for it to verify against.
A supplied `since` is validated eagerly (even on a non-first crawl, where it's simply not used
afterward) and rejected with `422` in three cases, never a silent clamp or an unhandled `500`:
malformed (fails `datetime.fromisoformat`), in the future, or — for Binance/on-chain only, where a
verified floor exists — earlier than that connector's `default_backfill_start()` date. Reddit has no
such floor check, since no genuine lower bound exists for it to enforce.

**`GET /datasets`, `GET /datasets/{source}/series`, `GET /connectors/{source}/status`**
(`INGEST-009` revised, `src/app/routers/datasets.py`): tenant-authenticated
(`Depends(naive_first_common.get_tenant_context)`, `X-Tenant-Id`), per
[../../docs/adr/0005-dataset-is-a-continuous-tenant-source-table.md](../../docs/adr/0005-dataset-is-a-continuous-tenant-source-table.md)
and solution-design.md section 8.1/8.3: a dataset is `{tenant_id, source}` —
the ongoing table a tenant's connector appends to — not a static per-crawl-run
snapshot, so there is **no `GET /datasets/{id}`** lookup-by-id endpoint
anywhere in this service; the backlog's original sketch of one is superseded
by the range-read shape below.

- `GET /datasets` — one entry per distinct `source` this tenant has rows for,
  across all three tables (`price_ohlcv`/`onchain_metric`/`sentiment_score`):
  `source`, `earliest_timestamp`, `latest_timestamp`, `row_count`. Discovery
  only, no values. An empty-history tenant gets `200 {"items": []}`, never a
  `404` — an empty list is a valid, successful answer.

  **Eventual consistency, not always-current (`INGEST-019`/`DBOPT-009`)**:
  `list_datasets` (`PostgresConnectorRecordRepository`) reads three
  `<table>_daily_source_summary` materialized views (migration 0007,
  `price_ohlcv_daily_source_summary`/`onchain_metric_daily_source_summary`/
  `sentiment_score_daily_source_summary`) instead of scanning the raw
  hypertables directly — a per-tenant, all-chunks `GROUP BY` on every
  `GET /datasets` call was the DBA-evidenced cost this closes (see
  `docs/product/backlog-db-optimization.md` DBOPT-009). This is a deliberate,
  user-approved tradeoff, not a regression: the user explicitly accepted a
  few minutes of staleness on `GET /datasets` in exchange for a much cheaper
  query. **Observed staleness window: up to ~5 minutes** (the scheduled
  refresh's `schedule_interval`; live-measured full-refresh execution time
  for all three views against this session's real backfilled data was
  under 2 seconds combined, negligible next to the 5-minute interval) — a
  row written to a hypertable can take up to that long to appear in
  `GET /datasets`, though `GET /datasets/{source}/series` (which reads the
  raw hypertable directly, unchanged by this ticket) reflects it
  immediately. Design note: these are plain Postgres materialized views
  refreshed via a TimescaleDB-scheduled job (`add_job`, every 5 minutes),
  not true TimescaleDB continuous aggregates as this ticket's Design
  section originally specified — TimescaleDB 2.29.1 refuses to create a
  continuous aggregate on any hypertable with row-level security enabled
  (live-reproduced against a scratch hypertable before concluding this),
  and `price_ohlcv`/`onchain_metric`/`sentiment_score` all have `FORCE ROW
  LEVEL SECURITY` (`INGEST-002`) — a locked-in multi-tenant isolation
  invariant not relaxed for this ticket. See migration 0007's own docstring
  for the full finding and the substituted design, which is functionally
  equivalent (same view shape/naming, same `list_datasets` query, same
  ~5-minute staleness target) and does not change `GET /datasets`'
  response shape at all.
- `GET /datasets/{source}/series?start=&end=&field=` — `{"timestamps": [...],
  "values": [...]}` for the tenant's `source` table, sliced to `[start,
  end]`. `start`/`end` are ISO-8601 and both optional — an omitted `start`
  means "earliest row", an omitted `end` means "latest row", the same code
  path as the fully-bounded case, not a special-cased branch. `field` selects
  the value column for multi-column sources; the table below is this
  ticket's documented default mapping, **flagged for product confirmation**
  per solution-design.md 8.3/8.11's own open question #2 — implemented as the
  working default in the meantime, not presented as final:

  | table (real model, `src/app/models.py`) | event-time column | default `field` |
  |---|---|---|
  | `price_ohlcv` (`PriceOhlcv`) | `open_time` | `close` |
  | `onchain_metric` (`OnchainMetric`) | `timestamp` | `value` |
  | `sentiment_score` (`SentimentScore`) | `created_utc` | `reddit_sid_com` |

  **Live-UAT finding, methodological, not a code bug (see docs/sprints/sprint-18.md's UAT addendum
  section)**: every field this table names is a raw level (a price, an on-chain metric value, a
  sentiment score) -- none of them is a returns series. CLAUDE.md's core positioning and the
  naive-first methodology this whole platform exists to validate are built around forecasting
  *returns*, not raw price levels. Validating a model against a raw level makes Naive0 (which always
  predicts 0) nonsensically wrong by construction, producing a "better than naive" verdict that is an
  artifact of the field choice, not a real finding. This service does not currently offer any
  returns-computation step between ingestion and a `dataset_reference` -- computing a returns series
  before validating is the caller's responsibility today. Whether that transform belongs in this
  service (a new endpoint/field), in `validation-service`, or stays the caller's job is an open product
  question, not resolved by this sprint.

  A nonexistent `source` and a `source` that exists only for a different
  tenant both return the same `404` (collapsed, no distinguishing response
  shape — the same convention as `validation-service`'s `GET /runs/{id}`):
  `ConnectorRecordRepository.read_series` scopes every query to the calling
  `tenant_id` and returns `None` for both cases, so the router has no branch
  that could tell them apart. An unrecognized `field` (not a real column on
  the resolved table) is a `400`.
- `GET /connectors/{source}/status` — this tenant's most recent `crawl_runs`
  row for `source` (`status`, `timestamp`, `row_count`), feeding the
  (currently blocked) `DASH-109` panel. No matching row (unknown source, or a
  source that only has runs for a different tenant) is a `404`.

**`GET /connectors/credentials-status`** (`INGEST-012`, `src/app/routers/connectors.py`,
live-UAT-driven: `GW-021`'s operator proxy had been pointed at `GET /connectors/{source}/status`
above, a different resource — crawl-run status, not credential presence — that gap is what this
ticket closes): tenant-authenticated (`Depends(naive_first_common.get_tenant_context)`,
`X-Tenant-Id`), returns `{"items": [{"source": str, "credential_set": bool, "last_set_at":
datetime | null}]}`, one entry per known credentialed source (`reddit_vader_sentiment` only,
today). Calls `CredentialRepository.get_credential_status` — never `get_credentials` — so no
`client_id`/`client_secret` value is ever decrypted or held in-process to answer this presence-only
check. An unset tenant/source is a valid `200` entry (`credential_set: false, last_set_at: null`),
never a `404` — this service's existing "empty is a valid answer" convention (`GET /datasets`).
`PostgresCredentialRepository.get_credential_status` selects only the `connector_credentials.updated_at`
column (never `client_id`/`client_secret`); `FakeCredentialRepository`'s test double tracks the same
per-`(tenant_id, source)` `updated_at` value set by `set_credentials`.

Repository (`app/repositories/interfaces.py`'s `ConnectorRecordRepository`,
extended, not a new sibling Protocol — same "which of the three tables holds
this `(tenant_id, source)`" knowledge `latest_fetched_at` already
encapsulates): `list_datasets`/`read_series`/`latest_crawl_run`.
`postgres_repository.py`'s `_TABLE_SPECS` is the single place the
table/event-time-column/default-field mapping above lives; both new query
methods iterate it rather than each re-deriving "which table, which column."
`tests/fake_repository.py`'s `FakeConnectorRecordRepository` gained the same
three methods (`_FAKE_TABLE_SPECS`, the same defaults) so
`tests/test_datasets_router.py` can exercise empty-tenant listing, multi-field
selection, cross-tenant `404` collapsing, and all three `start`/`end`
presence combinations without a live Postgres — this service's existing
"fake the client" test convention (`tests/test_credential_repository.py`'s
own precedent).

**Testing (added 2026-08-09, previously absent)**: `tests/` covers `connectors/base.py` (`latest_watermark`, `run_incremental`) and all three connectors' `fetch()` methods, using a fake `requests.Session`/fake `praw` client injected via each connector's existing constructor parameter rather than hitting real APIs. `tests/test_health.py` (`INGEST-007`) covers `GET /health`'s healthy/unhealthy-DB cases and `CorrelationIdMiddleware` wiring, against the now-installed-editable `src/app` package (`uv pip install -e .`) rather than a `sys.path` insert. Setup:
```
uv venv && uv sync
.venv/Scripts/python.exe -m pytest tests/ -q
```
(`requirements.txt` still exists for the older, plain-venv connector-only setup — both work side by side; `pyproject.toml` is the FastAPI app's own dependency surface, per its `[project] dependencies` list.)

**CI**: `.github/workflows/ci.yml` runs this module's test suite on every push/PR.

**Coverage**: run tests with coverage locally via `.venv/Scripts/python.exe -m pytest tests/ -q --cov=connectors --cov-report=term-missing` (no coverage threshold is enforced — CI prints the report, it never fails the build on a percentage).

**Dependency upgrades**: see [../../docs/dependency-upgrade-policy.md](../../docs/dependency-upgrade-policy.md) for this platform's cadence.

**Credential encryption** (`src/app/credential_crypto.py`, `INGEST-011`): tenant crawler credentials
(e.g. Reddit client secret) are encrypted at rest with `cryptography`'s `Fernet` (AES-128-CBC + HMAC),
key read from the `INGESTION_CREDENTIAL_ENCRYPTION_KEY` env var at call time. This is the primitive
only — `INGEST-004` wires it into the credential repository/connectors. Disclosed limitation (see
[../../docs/adr/0004-tenant-credential-encryption-at-rest.md](../../docs/adr/0004-tenant-credential-encryption-at-rest.md)):
losing the key makes every previously-stored credential permanently undecryptable; no key-rotation or
recovery tooling exists yet. `infra/docker-compose.yml`'s `ingestion-service` entry (`INGEST-007`)
passes this as `INGESTION_CREDENTIAL_ENCRYPTION_KEY` (env var reference, not a literal secret in the
Compose file itself — the default there and in `infra/.env.example` is an insecure, disclosed dev-only
key, same convention as `POSTGRES_APP_PASSWORD`).

**Credential repository wiring** (`src/app/repositories/interfaces.py`'s `CredentialRepository`/
`Credentials`, `postgres_repository.py`'s `PostgresCredentialRepository`, `INGEST-004`, see
[../../docs/adr/0004-tenant-credential-encryption-at-rest.md](../../docs/adr/0004-tenant-credential-encryption-at-rest.md)):
a `connector_credentials` repository sibling to `INGEST-003`'s `ConnectorRecordRepository`, following
the same Repository pattern and encrypting every field via `credential_crypto.encrypt`/decrypting via
`credential_crypto.decrypt` (`INGEST-011`'s primitive; no second crypto implementation). No column in
`connector_credentials` is ever written or returned as plaintext. `RedditSentimentConnector` now
resolves `client_id`/`client_secret` from this repository when both `tenant_id` and
`credential_repository` are supplied to its constructor (mirroring `connectors/base.py`'s
`run_incremental` "both supplied → DB path" convention) — the plain `os.environ` path
(`REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`) remains fully intact as the standalone/no-tenant CLI
fallback. `REDDIT_USER_AGENT` is not a secret and has no `connector_credentials` column, so it is
always read from `os.environ` in both modes. `Binance`/`BlockchainInfo` connectors need no credential
row and gained no new required constructor parameter.

**Crawl-run tracking** (`ConnectorRecordRepository.record_crawl_run`, `PostgresConnectorRecordRepository`,
`INGEST-005`): one `crawl_runs` row per `fetch()` outcome in `connectors/base.py`'s DB-write path
(`run_incremental`, when both `tenant_id`/`repository` are supplied) — success, empty-but-successful
(`row_count=0`, `status="completed"`, not silently skipped), and failure (`status="failed"`, written
before the original write exception is re-raised unchanged, so `run_incremental`'s existing
exception-propagation behavior is untouched). Same `_tenant_scoped_session`/`naive_first_common.db.
tenant_scope` mechanism as every other `PostgresConnectorRecordRepository` method — no second
tenant-scoping implementation. `tests/fake_repository.py`'s `FakeConnectorRecordRepository.crawl_runs`
is the in-memory equivalent used by `tests/test_base.py`'s crawl-run/cross-tenant-isolation tests.
