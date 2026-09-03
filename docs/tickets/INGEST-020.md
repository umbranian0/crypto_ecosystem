# INGEST-020 — Compression policy for `price_ohlcv`/`onchain_metric`/`sentiment_score` old chunks (DBOPT-008, ingestion half)

**Module**: `services/ingestion-service` only. This is the ingestion half of DBOPT-008 — `validation.split_results`' compression is a separate ticket (`VS-028`), touching a different service/schema, per the Tech Lead's module-boundary ticket-splitting rule (implementation-plan.md sections 2/9).
**Depends on**: `INGEST-019` (same service — sequential migration numbering, and this ticket's correctness testing exercises `list_datasets`-shaped access patterns against the new continuous aggregate per the sprint plan's own sequencing note). Can run in parallel with `VS-028` (different service, no shared file).

## Analysis

Covers `docs/product/backlog-db-optimization.md` DBOPT-008 for `ingestion.price_ohlcv`/`onchain_metric`/`sentiment_score`, now unblocked: the user has explicitly decided old crawled data **is** actively queried (compression is approved, but must be validated for query correctness, not just "compression enabled" — a hard, non-negotiable acceptance criterion per the sprint plan, not optional polish).

**Real data context** (`backlog-db-optimization.md`, live-verified): `price_ohlcv` 121,895 rows / 472 chunks (2017-08-17 → today), `onchain_metric` 19,291 rows / 922 chunks (2009-01-01 → today), `sentiment_score` 0 rows. `INGEST-016` already retuned these hypertables' `chunk_time_interval` to 90 days going forward — this ticket does not change chunking, only adds compression on top of it.

**The DBA's own documented tradeoff, now a binding test requirement, not a discussion point** (`backlog-db-optimization.md` DBOPT-008 "Against"): a compressed chunk must decompress before any row-level write; TimescaleDB (per this container's actual version, `timescaledb 2.29.1`, confirmed live) supports transparent insert-into-compressed-chunk without a manual decompress step first, but this must be **proven against the real running container**, not assumed from documentation — the sprint's explicit instruction is "don't assume this away, actually exercise it."

## Design

**Pattern**: none from implementation-plan.md section 7 apply (schema-tuning, not a new extension point).

**DRY check**: `_TABLE_SPECS`/the three-table order (`postgres_repository.py`) is the existing single source of truth for "which three tables" — this migration's own `_HYPERTABLES`-shaped tuple (mirroring `0003_convert_to_hypertables.py`/`0004_retune_hypertable_chunk_intervals.py`/`0006`'s own precedent of a local three-tuple matching that same order) must use the same three tables in the same order, not a fourth ad hoc list. Zero repository/router code changes are expected for this ticket — compression is transparent to `SELECT`/`INSERT` at the SQL level; if anything in `postgres_repository.py`/`connectors/base.py` needs to change to make the write-path test pass, that is itself a finding to escalate, not silently work around.

**Migration** (new file `services/ingestion-service/migrations/versions/0008_add_compression_policy.py`, chained after `0007` — INGEST-019 — Postgres-only-guarded like every prior migration in this service):
```sql
ALTER TABLE ingestion.price_ohlcv SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'tenant_id, source',
    timescaledb.compress_orderby = 'open_time DESC'
);
SELECT add_compression_policy('ingestion.price_ohlcv', INTERVAL '90 days');
-- analogous for onchain_metric (compress_orderby = 'timestamp DESC')
-- and sentiment_score (compress_orderby = 'created_utc DESC')
```
`compress_segmentby = 'tenant_id, source'` (not a different column choice): matches every query shape this table is actually read by (`read_series`/`list_datasets`/`latest_fetched_at` all filter on `tenant_id`+`source` first) — segmenting by the same columns a compressed chunk's queries filter on lets Postgres skip whole compressed segments without decompressing them, the same principle as choosing an index's leading columns. `compress_orderby` matches each table's own event-time column (the same column each hypertable is partitioned on), preserving each table's natural time ordering inside a compressed chunk.
`INTERVAL '90 days'` as the compression-policy age threshold: matches `INGEST-016`'s own 90-day `chunk_time_interval` retuning (a chunk becomes eligible for compression once it's a full interval old under the new chunking, avoiding compressing a chunk that's still actively being written to).

## Implementation acceptance criteria

- AC1: compression enabled (`timescaledb.compress` + `compress_segmentby`/`compress_orderby`) and a compression policy (90-day threshold) added on all three tables, Postgres-only-guarded, no-op against the SQLite schema-parity test.
- AC2: zero changes to `src/app/repositories/postgres_repository.py`, `src/app/routers/`, or `connectors/*.py` unless a real write-path failure is found during testing (see below) — compression is meant to be transparent to existing read/write call sites.

## Test acceptance criteria (hard, non-negotiable per the sprint's explicit instruction — not satisfied by "no error was raised")

- **Compressed-chunk read correctness (the hard AC)**: after the migration, manually compress at least one real, pre-existing chunk with actual historical data on `price_ohlcv` (via `SELECT compress_chunk(<a real chunk name from timescaledb_information.chunks>);` — do not wait for the background policy job, since that would make this test's timing unpredictable) for a real seeded tenant/source. Then run `read_series`/`list_datasets`-shaped queries (the actual repository methods, not raw SQL bypassing the application code) against that tenant/source and assert the returned rows/aggregates are **identical** to a captured "before compression" baseline for the same tenant/source/date range — not merely "the query didn't error." Repeat for `onchain_metric` (real data exists); `sentiment_score` has 0 rows in this environment today — insert a small number of synthetic test rows with an old `created_utc` first so this table's own compression-correctness path is genuinely exercised, not skipped for lack of data.
- **Write/backfill-path correctness against a compressed chunk (the DBA's flagged "against" tradeoff, hard AC)**: with the same chunk still compressed, attempt a real write into it — e.g. call `add_price_records`/`add_onchain_records` with a record whose event-time timestamp falls inside the already-compressed chunk's date range (simulating `INGEST-013`'s first-crawl-backfill `since` override landing in old, already-compressed territory). Document the actual observed outcome precisely: does the insert succeed transparently (this container's TimescaleDB version may support insert-into-compressed-chunk natively), does it require an explicit `decompress_chunk` first, or does it fail outright? Whichever is true, write it down as a real, tested fact in this ticket's Outcome notes and the README (Documentation AC below) — do not report "no regression" without having actually attempted the write.
- Re-verify compression policy exists live via `timescaledb_information.compression_settings`/`jobs` after `alembic upgrade head`.
- Full `services/ingestion-service` suite re-run with zero regressions.

## Review acceptance criteria (Tech Lead verifies personally)

- Personally re-run the compressed-chunk read-correctness and write-path tests against the real running Compose Postgres container — read the actual before/after query result values, don't trust a boolean "passed" from the dev agent's report.
- Confirm `compress_chunk`/write-attempt test rows are cleaned up (or clearly marked as fixture data) so this doesn't silently corrupt the real UAT dataset's row counts for other services' verification steps this sprint.
- Confirm no application code changed unless the write-path test surfaced a real, disclosed failure requiring one — if it did, confirm the fix is minimal and the failure is documented, not silently patched without a trace.

## Documentation acceptance criteria

- `services/ingestion-service/README.md` gains a compression section (mirroring the existing `INGEST-016/17/18` migration-documentation style): what's compressed, the segmentby/orderby choice and why, the 90-day threshold, and — critically — the **actual observed write-path behavior** against a compressed chunk (transparent / requires decompress / fails), stated as a tested fact, plus the read-correctness proof's real numbers (or a pointer to the ticket's Outcome section for the full before/after capture).
- `docs/product/backlog-db-optimization.md`'s DBOPT-008 entry updated to "Done", pointing at this ticket + `VS-028`.


## Outcome (Sprint 22, 2026-09-03) — BLOCKED, not implemented, escalated to the user

**Status: blocked (architectural incompatibility), not done.** No `0008` migration was written. This is not an implementation failure — it is a real, live-verified conflict between two locked-in platform invariants: RLS-based tenant isolation (`FORCE ROW LEVEL SECURITY` on `price_ohlcv`/`onchain_metric`/`sentiment_score`, `INGEST-002`) and TimescaleDB's native compression feature (`ALTER TABLE ... SET (timescaledb.compress, ...)`).

**Live finding** (reproduced independently by both the dev agent and the Tech Lead, against the real running `naive-first-postgres` container, TimescaleDB 2.29.1, via disposable scratch hypertables — fully cleaned up, zero trace left in the real `ingestion`/`naive_first` schema):
```
ERROR:  columnstore cannot be used on table with row security
```
This fires the moment `ALTER TABLE ... SET (timescaledb.compress, ...)` is attempted against any table with row security enabled — confirmed to be triggered by the `rowsecurity` reloption itself, not specifically by `FORCE`:
- `ENABLE ROW LEVEL SECURITY` (no `FORCE`) + compress → fails, same error.
- `ENABLE` + `FORCE ROW LEVEL SECURITY` + compress → fails, same error (this platform's actual configuration on all three tables).
- No RLS at all + compress → **succeeds**.

**Why this could not be routed around the way `INGEST-019` was**: `INGEST-019` hit a related but narrower restriction (continuous aggregates specifically refuse RLS-enabled source hypertables) and had a workable substitute — a plain materialized view refreshed on a schedule, since a *view* can carry its own independent (or absent) RLS without touching the underlying hypertable's RLS at all. Compression has no equivalent substitute: it is a physical, in-place storage transform on the hypertable's own chunks, not something that can be read through a side object instead. There is no "compressed view" concept.

**What was NOT done, on purpose**: RLS was not relaxed, disabled, or worked around on `price_ohlcv`/`onchain_metric`/`sentiment_score`, even transiently — this is a locked-in multi-tenant isolation invariant (`INGEST-002`, `implementation-plan.md` section 5, `CLAUDE.md`'s "no service reads another service's schema"/tenant-isolation posture) that neither the dev agent nor the Tech Lead is authorized to relax to satisfy a Could-priority storage optimization.

**Real options for the user/PM to choose between** (not decided here):
1. **Accept the gap.** Close DBOPT-008 as "Won't (for now)" for the two RLS-protected TimescaleDB tables affected (`ingestion`'s three hypertables here; `validation.split_results` likely the same, see `VS-028`), same disclosed-limitation posture this backlog already uses for other accepted tradeoffs (e.g. `INGEST-014`'s process-local lock). Old data stays uncompressed; the storage-savings motivation for DBOPT-008 goes unrealized for these tables.
2. **A materially larger redesign**: archive old chunks (older than some threshold) into a separate table/schema without per-row RLS (e.g. an admin-only, non-multi-tenant "cold storage" schema, tenant isolation enforced by application-layer filtering or a per-tenant partition instead of Postgres RLS), then compress that separate table. This is not a variant of this ticket's scope — it changes the data-ownership/access-pattern model for old data (would need its own story/design review against `implementation-plan.md` section 5's schema-per-service and `CLAUDE.md`'s isolation rules), and is explicitly not undertaken here.
3. Re-evaluate on a future TimescaleDB version, if a later release lifts this restriction (this is a product limitation of TimescaleDB 2.29.1 as tested, not necessarily permanent upstream).

**Test acceptance criteria**: not applicable — no migration exists to test. The live reproduction above (both success and failure paths, and isolation of the exact cause) is this ticket's actual delivered evidence.

**Full suite**: `services/ingestion-service` 114 passed, 1 skipped — unchanged from `INGEST-019`'s baseline, since no application code changed for this ticket.

**Files changed**: `services/ingestion-service/README.md` only (compression section documenting this blocked finding). No migration, no repository/router code change.
