# INGEST-022 — Cooperative cancellation signal threaded through the fetch loop

Sprint: docs/sprints/sprint-23.md. Backlog: docs/product/backlog-crawl-lifecycle-control.md.
Status: **done**
Depends on: INGEST-021 (done first; this ticket's own fetch-loop code is independently testable even
before INGEST-021 lands, but sequence after per the sprint plan).

## Analysis

Covers the backlog's INGEST-022 story. Read directly (not assumed) from
`services/ingestion-service/connectors/base.py`, `binance_price.py`, `blockchain_onchain.py`,
`reddit_sentiment.py`:

- `IngestionSource.fetch(since)` is the one abstract method every connector implements (Adapter pattern,
  implementation-plan.md section 7).
- `BinancePriceConnector.fetch` already loops (`while cursor < end_ms: batch = self._fetch_batch(...)`) —
  a real, already-existing per-page checkpoint.
- `RedditSentimentConnector.fetch` iterates `subreddit.new(limit=...)` per subreddit, nested in a loop
  over `self.subreddits` — a real per-submission checkpoint (finer than Binance's per-page one).
- `BlockchainInfoConnector.fetch` makes exactly one blocking `self._session.get(...)` call with no loop
  at all — confirmed, not assumed: there is no natural mid-fetch checkpoint in this method.

This is the mechanism that makes cancellation real, not cosmetic (CLAUDE.md/backlog decision #1:
"stops it mid-flight," not "marks it as if it stopped"). No leakage/naive-first-engine concern here —
this only touches raw-zone connector fetch loops, never a dataset/split/baseline concept.

## Design

**Files touched** (one connector's own file each, plus `base.py` for the shared interface — four files
total, all within `services/ingestion-service/connectors/`):
- `connectors/base.py` — `IngestionSource.fetch`'s abstract signature gains two new optional params:
  `should_cancel: Callable[[], bool] | None = None`, `on_progress: Callable[[int], None] | None = None`
  (the `on_progress` param is INGEST-025/026's own AC, not this ticket's — declared here only so the
  interface is defined once, not twice; this ticket does not wire any real `on_progress` callback body
  anywhere, that is INGEST-025/026's scope). `FetchResult` (the frozen dataclass) gains one new field:
  `cancelled: bool = False` — this is what lets a connector tell the caller "I stopped early because
  `should_cancel()` returned `True` at a checkpoint I actually evaluated," as opposed to a caller
  post-hoc re-checking a registry flag that may have flipped `True` *after* the fetch had already run to
  natural completion (the exact race INGEST-024 must resolve correctly for `blockchain_info_*` sources
  specifically — a call that starts and finishes without ever checking `should_cancel()` again must
  report `cancelled=False` regardless of the registry's state by the time it returns).
- `connectors/binance_price.py` — `BinancePriceConnector.fetch` accepts both new params. After each
  batch is appended to `all_rows` (immediately after the existing `all_rows.extend(batch)` line, before
  the existing `next_cursor`/full-page checks), call `on_progress(len(all_rows))` if supplied, then call
  `should_cancel()` if supplied; if it returns `True`, stop the loop and build the returned
  `FetchResult` from whatever is in `all_rows` so far, with `cancelled=True`.
- `connectors/reddit_sentiment.py` — `RedditSentimentConnector.fetch` accepts both new params. Checkpoint
  is **per submission actually scored and appended to `rows`** (Tech Lead's call, stated here explicitly
  per the story's own instruction not to leave this ambiguous): immediately after each submission's row
  is appended, call `on_progress(len(rows))` if supplied, then `should_cancel()` if supplied; if `True`,
  stop both the inner submission loop and the outer subreddit loop, and build the returned `FetchResult`
  from whatever is in `rows` so far, with `cancelled=True`. Per-submission (not per-subreddit) is chosen
  because it is the actual boundary the existing loop already evaluates one row at a time, and it gives
  the cancel signal a chance to take effect mid-subreddit rather than only between the two subreddits —
  document this choice in this connector's own docstring, since INGEST-026 (progress reporting) reuses
  the same boundary and must not silently assume a different one.
- `connectors/blockchain_onchain.py` — `BlockchainInfoConnector.fetch` accepts both new params for
  interface uniformity. `on_progress` is never called (no loop exists to call it from). `should_cancel`
  is checked exactly once, at the very top of the method, **before** the one blocking `GET` is issued —
  if `True`, return a `FetchResult` with empty records and `cancelled=True` without making the HTTP call
  at all. If `should_cancel` is absent or returns `False` at that one checkpoint, the method proceeds
  exactly as today and always returns `cancelled=False`, regardless of what `should_cancel()` might
  return if it were (it never is) checked again mid-request. Document this ceiling explicitly in the
  method's own docstring (this is also INGEST-027's documentation subject, but the code-level docstring
  belongs to this ticket since it is the code that carries the actual behavior).

**DRY check**: `should_cancel`/`on_progress` are declared once on the shared `IngestionSource.fetch`
abstract signature (`base.py`), not redeclared ad hoc per connector — every subclass's concrete
`fetch(...)` signature must match it exactly (same param names/defaults), the same discipline the
existing `since` parameter already follows across all three connectors. No second cancellation/progress
mechanism is introduced anywhere else in this module.

**Non-goal, stated per the story's own AC**: no story here authorizes fitting/writing partial rows
outside the existing append-only, immutable-raw-zone write contract — a cancelled crawl only ever
contains rows it actually and completely fetched (this falls out for free from the design above: the
returned `FetchResult.records` is always built from `all_rows`/`rows`, never a placeholder/partial row).

## Implementation acceptance criteria

- [x] `IngestionSource.fetch(since)`'s abstract signature gains `should_cancel: Callable[[], bool] | None
      = None` and `on_progress: Callable[[int], None] | None = None`, both additive/optional — no
      existing caller (`connectors/base.py::run_incremental`, which calls `connector.fetch(since=since)`
      with no other args) needs to change or breaks.
- [x] `FetchResult` gains `cancelled: bool = False`.
- [x] `BinancePriceConnector.fetch`'s pagination loop calls `should_cancel()` once per page (after
      appending that page's rows, before requesting the next page); a `True` result stops further pages
      and returns a `FetchResult` built from the rows already accumulated, `cancelled=True`.
- [x] `RedditSentimentConnector.fetch`'s submission loop calls `should_cancel()` once per submission
      scored (documented choice, per-submission not per-subreddit); a `True` result stops both loops and
      returns a `FetchResult` built from the rows already accumulated, `cancelled=True`.
- [x] `BlockchainInfoConnector.fetch` checks `should_cancel()` exactly once, before its one blocking
      `GET`; documented in its own docstring as unable to honor cancellation once that request has
      started.
- [x] A natural (non-cancelled) completion of any of the three connectors' `fetch()` returns
      `cancelled=False`.

## Test acceptance criteria

- [x] `tests/test_binance_price.py` (or wherever this connector's existing fetch tests live): a fake
      multi-page `_fetch_batch`/session sequence proves `should_cancel` returning `True` after the first
      page stops further pages from being requested, and the returned `FetchResult.records`/`cancelled`
      reflect only the first page's rows / `True`.
- [x] `tests/test_reddit_sentiment.py`: a fake multi-submission/multi-subreddit sequence proves the same
      for `should_cancel` returning `True` after the first submission scored.
- [x] `tests/test_blockchain_onchain.py` (or equivalent): one test proves `should_cancel` returning
      `True` before the call prevents the HTTP `GET` from being issued at all (assert on the fake
      session's call count, not just the returned records) and returns `cancelled=True`; a second test
      proves `should_cancel` returning `False` (or omitted) behaves exactly as before this ticket,
      `cancelled=False`.
- [x] A test proves each connector's natural, non-cancelled completion still returns `cancelled=False`
      (regression coverage for the new field's default behavior).

## Review acceptance criteria (Tech Lead verifies personally)

- [x] Read the actual diff: `should_cancel`/`on_progress` declared identically across all three
      connectors' concrete `fetch` signatures and the abstract one in `base.py` — confirmed, no drift.
- [x] Confirmed no partial/corrupt row can ever be written: `FetchResult.records` in every cancelled-early
      case is a slice of `all_rows`/`rows`, fully-constructed entries only, never a placeholder.
- [x] Confirmed `run_incremental`'s existing call site (`connector.fetch(since=since)`) is unchanged.
- [x] Full `services/ingestion-service` test suite re-run by the Tech Lead: `123 passed, 1 skipped`
      (pre-existing unrelated skip), zero regressions.

## Documentation acceptance criteria

- [x] Each connector's own module/class docstring states its actual cancellation checkpoint granularity
      (Binance: per page; Reddit: per submission; blockchain.info: only before the request starts, never
      during) — this is the ticket's own code-level documentation; `services/ingestion-service/README.md`'s
      equivalent summary is INGEST-024's/027's documentation acceptance criterion, not duplicated here.
