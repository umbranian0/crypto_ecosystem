# INGEST-026 — Reddit connector: per-submission progress checkpoints

Sprint: docs/sprints/sprint-23.md. Backlog: docs/product/backlog-crawl-lifecycle-control.md.
Status: **done**
Depends on: INGEST-024 (`record_crawl_progress` write-back method). Runs in **parallel** with INGEST-025
— disjoint files (`reddit_sentiment.py` vs `binance_price.py`), no shared data.

## Analysis

Covers the backlog's INGEST-026 story. **Tech Lead's granularity call, stated explicitly per the
story's own instruction not to leave this ambiguous**: per-submission, not per-subreddit — this matches
the same boundary INGEST-022 already chose for `should_cancel` on this connector (one checkpoint serving
both concerns, per that ticket's own Design section), and gives the dashboard (Sprint 24) meaningfully
more frequent updates than a coarser per-subreddit checkpoint would (only 2 updates per crawl at the
default `DEFAULT_SUBREDDITS` configuration). Tradeoff disclosed, not silently accepted: up to
`limit_per_subreddit * len(subreddits)` (default 500 × 2 = 1000) `record_crawl_progress` calls per
crawl in the worst case — each is a single-row `UPDATE` against an already-indexed `(tenant_id, source,
status)` row (INGEST-024's design), not an `INSERT`, so this does not scale `crawl_runs`' row count with
submission count the way a naive per-checkpoint-insert design would have.

## Design

**File touched**: `services/ingestion-service/connectors/reddit_sentiment.py` only. If INGEST-022 already
added the `on_progress` call at the correct point (per that ticket's own Design section), confirm this
by reading the actual merged file before writing new code — this ticket's remaining scope may be purely
the test proving the incremental-progress contract.

**DRY check**: reuses `IngestionSource.fetch`'s shared `on_progress: Callable[[int], None] | None`
signature (`base.py`, INGEST-022) unmodified — the same callback shape as `BinancePriceConnector`
(INGEST-025), not a bespoke per-connector shape.

## Implementation acceptance criteria

- [x] `RedditSentimentConnector.fetch`'s submission loop calls `on_progress(len(rows))` once per
      submission actually appended to `rows` — already correct as merged by INGEST-022, confirmed by the
      dev agent, no production code change needed.
- [x] `_execute_crawl` correctly reaches this connector's `on_progress` calls generically (already true
      per INGEST-024's wiring).

## Test acceptance criteria

- [x] `test_fetch_calls_on_progress_cumulatively_across_subreddit_boundary` (`tests/test_reddit_sentiment.py`).
- [x] `test_fetch_does_not_call_on_progress_for_submissions_filtered_by_since` (`tests/test_reddit_sentiment.py`).

## Review acceptance criteria (Tech Lead verifies personally)

- [x] Read the actual diff (identical to INGEST-022's own merged code, confirmed via `git diff`): the
      cumulative count spans both subreddits correctly (`len(rows)`, not reset per subreddit).
- [x] Confirmed `RedditSentimentConnector.fetch`'s docstring and `services/ingestion-service/README.md`
      both state the per-submission granularity and explicitly contrast it with Binance's per-page
      granularity.
- [x] Isolated full-suite re-run performed by the Tech Lead (with INGEST-025/027 already landed and no
      concurrent DB activity): `142 passed, 1 skipped, 0 failed` — definitively confirming the earlier
      cross-agent `DeadlockDetected` failures were transient contention on the shared Postgres container,
      not a real regression.

## Documentation acceptance criteria

- [x] `RedditSentimentConnector`'s docstring states the per-submission granularity (already landed by
      INGEST-022; confirmed accurate).
- [x] `services/ingestion-service/README.md`'s Reddit connector description gains the granularity-contrast
      note (added by this ticket's dev agent).
