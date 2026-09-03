# Sprint 21 — DB optimization (indexes + TimescaleDB chunk sizing across gateway-api/validation-service/ingestion-service)

Sprint goal: gateway-api's API-key authentication and validation-service's tenant-scoped run/split queries no longer perform full sequential table scans on their hot paths, and the remaining non-tradeoff DBA-flagged index/chunk-sizing gaps (split_results, crawl_runs, ingestion watermark lookups, hypertable chunk intervals) are closed, leaving only the three explicitly-flagged open tradeoff decisions for the user.

Backlog source: docs/product/backlog-db-optimization.md (DBOPT-001 through DBOPT-010).

Stories in scope (execution order):

1. DBOPT-001 - identity.api_keys: unique index on key_hash (gateway-api). First - live-verified full sequential scan on the hottest query path in the platform (every authenticated request). Cheap, safe, single-index, no schema-shape risk.
2. DBOPT-002 - validation.runs: composite index on (tenant_id, created_at DESC) (validation-service). Second, same urgency class as DBOPT-001 - live-verified full scan on the RLS tenant filter backing GET /runs / count_runs. Ordered second only because DBOPT-001 is the authentication path (every request) and DBOPT-002 is a list/count path; both are equally cheap/safe and could run in parallel - no dependency between them.
3. DBOPT-003 - validation.split_results: composite index on (tenant_id, run_id), issued against the hypertable root (validation-service). Third - same Must priority/safety as 001/002, closes the RLS gap on a second table plus a real 130ms planning-time cost on every run-detail view. No dependency on 001/002; sequenced after them since it's a hypertable (root-table CREATE INDEX propagation to existing/future chunks — worth verifying in isolation).
4. DBOPT-004 - Hypertable chunk_time_interval retuning for ingestion.price_ohlcv, ingestion.onchain_metric, ingestion.sentiment_score (ingestion-service) and validation.split_results (validation-service). Fourth - Must priority, safe (only affects future chunks, no query-surface change), sequenced after the index items and benefits from DBOPT-003 already being in place on split_results.
5. DBOPT-006 - ingestion.crawl_runs: composite index on (tenant_id, source, fetched_at DESC) (ingestion-service). Fifth - Should priority, no dependency on anything above, no tradeoff; pulled in on the same zero-risk grounds this repo used for prior Should-priority pure-index/doc items (LC-005/ARCH-007/008, Sprint 10).
6. DBOPT-007 - Composite (tenant_id, source, fetched_at) index on ingestion.price_ohlcv / onchain_metric / sentiment_score (ingestion-service). Sixth - Should priority, grouped after DBOPT-006 (same repository layer), complementary to (not blocked by) DBOPT-004's chunk-interval fix on the same tables.

Stories explicitly deferred:

- DBOPT-005 (identity.users: index on email) - blocked on user decision (UNIQUE vs. not — global vs. per-tenant uniqueness is a product/data-integrity call). Scheduling even the plain non-unique index would implicitly pre-empt that decision, so the whole story stays out.
- DBOPT-008 (compression policy for old ingestion/validation hypertable chunks) - blocked on user decision (is old price/on-chain data ever queried, or write-once/never-read?).
- DBOPT-009 (continuous aggregate for list_datasets' per-source min/max/count) - blocked on user decision (is exact freshness load-bearing for any workflow, or is staleness acceptable?). DBA also recommends deferring until list_datasets is called often enough to matter.
- DBOPT-010 (reporting.reports: no index beyond PK) - not scheduled, not a deferral. Already resolved "Won't (for now)" by the DBA with a concrete revisit trigger (a future list_reports endpoint) — not an open question or a priority call for the PM.

Definition of done for this sprint: all six in-scope migrations applied and verified against the real running Postgres/TimescaleDB container — for each index item, a live EXPLAIN (ANALYZE, BUFFERS) re-run on the same query shape the DBA originally measured, confirming an index scan/index-only scan replaces the prior sequential scan; for DBOPT-004, confirmation via timescaledb_information.dimensions that new chunks created after the change use the new interval; each touched service's existing test suite re-run with zero regressions; each touched service's README updated where it documents schema/performance detail; docs/product/backlog-db-optimization.md updated to mark DBOPT-001/002/003/004/006/007 done, with DBOPT-005/008/009 left explicitly open and DBOPT-010 left as-is.
