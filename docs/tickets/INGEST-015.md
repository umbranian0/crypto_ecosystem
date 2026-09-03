# INGEST-015 — `POST /connectors/{source}/run` becomes truly async + lock-gated

## Analysis

Depends on `INGEST-014` (the `CrawlRegistry` primitive, built and unit-tested in isolation). This
ticket is the actual fix for both QA-reproduced bugs:

1. **Timeout**: the handler currently `await`s (synchronously runs) the full crawl before responding
   — a real ~70s/79,127-row Binance backfill blocks the request that long. `gateway-api`'s
   `GATEWAY_API_DOWNSTREAM_TIMEOUT_SECONDS` was bumped to 240s as a band-aid (already committed by
   the QA sweep, in `infra/docker-compose.yml` — do not touch that file in this ticket; once this
   ticket lands the long timeout stops being load-bearing, since the ingestion-service response no
   longer depends on crawl duration, but reverting the compose value is a separate, low-risk config
   change left to the requester, not bundled here).
2. **Concurrency race**: two requests for the same `(tenant_id, source)` independently resolve the
   same `since` watermark and both attempt to write the same rows — reproduced live as an unhandled
   `500` (Postgres `UniqueViolation`).

Design direction from the requester (binding): (a) per-`(tenant_id, source)` locking — a second
trigger while one is in flight gets an immediate, clean `409`, never a `500`; (b) the crawl itself
becomes asynchronous — `POST /connectors/{source}/run` returns `202` immediately with a
queued/running status, the actual fetch-and-write work happens in the background, and the caller
polls `GET /connectors/{source}/status` (`INGEST-009`, unchanged by this ticket) for the outcome.

`crawl_runs`' status vocabulary (`INGEST-005`) is currently `"completed"`/`"failed"` only (per
README's own documented vocabulary) — this ticket adds a third value, `"queued"`, covering the whole
window from "accepted" through "still fetching" (a disclosed simplification: this ticket does not
add a fourth, more granular `"running"` state distinguishing "waiting for a thread-pool slot" from
"actively calling `connector.fetch()`" — `"queued"` covers both, since nothing in this platform reads
that distinction today and a second in-flight status write would need an update-in-place the
`crawl_runs` table doesn't currently support, out of this ticket's scope). `status` is a plain
`String` column (`app/models.py`'s `CrawlRun.status`, no `CheckConstraint`), so this needs no schema
migration — only a documentation/convention change.

## Design

**Files touched** (all `services/ingestion-service/`, one module):
`src/app/routers/connectors.py` (the actual fix), `src/app/dependencies/repositories.py` (import
only — `CrawlRegistryDep` already added by `INGEST-014`), `tests/test_connectors_router.py`
(extended), `tests/fake_repository.py` (only if a gap is found — expected none, since
`record_crawl_run`'s signature is unchanged), README.md.

**DRY check**: `record_crawl_run(tenant_id, source, since_watermark, fetched_at, row_count, status)`
(`app/repositories/interfaces.py`) is reused unmodified for both the new "queued" write and the
existing "completed"/"failed" writes — no new repository method is added, no second status-tracking
mechanism invented (the ticket's own binding instruction: extend `crawl_runs`' vocabulary, don't
invent a second store). `latest_watermark_from_db`/`_resolve_connector`/`_parse_since_override`
(all pre-existing in this file) are reused unchanged. The old `_run_and_record` function is replaced
by `_execute_crawl` (background-task shape) rather than kept alongside it — grepped this file and
`tests/` first to confirm `_run_and_record` has no other caller before removing it (it is private,
`_`-prefixed, router-file-local).

**No design pattern from section 7 is forced onto the locking/background-dispatch mechanism itself**
(same note as `INGEST-014`) — FastAPI's `BackgroundTasks` is the built-in seam for "respond now, do
the work after," and is used exactly as FastAPI intends (added via `Depends`-free
`BackgroundTasks` parameter injection, not a hand-rolled thread spawn). This keeps the fix inside
"a single-process service, no message queue" per the requester's explicit non-goal.

**New response shape** (breaking change to `POST /connectors/{source}/run`'s `202` body — flagged,
not silently absorbed): the old `ConnectorRunResponse` (`{source, status, row_count, since,
fetched_at}`) described the crawl's *final outcome*, which is no longer known at response time. New
`ConnectorRunAcceptedResponse`: `{source, status: "queued", since, queued_at}` — `since` is the
watermark this crawl will run from (already resolved before responding, since it's a fast DB read
done under the lock), `queued_at` is when the request was accepted. The caller's own
`(tenant_id, source)` pair (already required on every call, via `X-Tenant-Id` + the route's own
`source`) is deliberately the "job identifier" — there is no separate `crawl_run_id` returned,
since the only existing status-read path (`GET /connectors/{source}/status`, `INGEST-009`) is itself
keyed by `(tenant_id, source)`, not by a per-attempt id; inventing an id nobody can look anything up
by would be dead surface. `gateway-api`'s proxy (`GW-024`) and `dashboard-web`'s trigger-result
fragment (`DASH-115`) are sequenced after this ticket precisely because they consume this new shape.

**Lock-then-validate ordering** (explicit, since it affects which error a bad request gets): request
validation (unknown `source` → `404`; malformed/out-of-range `since` → `422`; missing Reddit
credentials → `422`) all happens *before* the lock is touched — a bad request must fail the same way
whether or not a crawl happens to be in flight for that source. The lock is only acquired after all
of that passes, immediately before the watermark is resolved and the "queued" row is written — this
closes the actual race (both requests resolving the same `since` before either one holds the lock).

## Implementation acceptance criteria

- [ ] `run_connector` gains a `background_tasks: BackgroundTasks` parameter and a `registry:
      CrawlRegistryDep` parameter (from `INGEST-014`).
- [ ] Validation order preserved exactly as today (`404` unknown source → `_parse_since_override`'s
      three `422` cases → credentials-missing `422`), unchanged in this ticket.
- [ ] After validation passes: `registry.try_acquire(tenant.tenant_id, connector.name)`; if `False`,
      raise `HTTPException(409, detail="crawl already in progress for connector <source>")`
      immediately — no DB read/write happens on this path.
- [ ] If acquired: resolve `since` via `latest_watermark_from_db` + the existing
      "`since is None` → `since_override` or `default_start`" fallback (moved here from the old
      `_run_and_record`, logic unchanged); write one `crawl_runs` row via `record_crawl_run(...,
      row_count=0, status="queued")`; schedule `_execute_crawl` via `background_tasks.add_task(...)`;
      return `202` with `ConnectorRunAcceptedResponse`.
- [ ] If any exception occurs between a successful `try_acquire` and successfully scheduling the
      background task (e.g. the "queued" DB write itself fails), the lock must still be released
      before the exception propagates — no code path exists where `try_acquire` succeeds but
      `release` is never reachable.
- [ ] `_execute_crawl(repository, registry, tenant_id, connector, record_kind, since)`: calls
      `connector.fetch(since=since)`, writes rows via the existing `add_{record_kind}_records`
      dispatch, then `record_crawl_run(..., status="completed")` (empty-but-successful fetch
      included, `row_count=0`, exactly as today). On *any* exception — from `fetch()` itself, not
      only from the write step as the old code handled — writes `record_crawl_run(..., status=
      "failed")` instead (a disclosed improvement over the old behavior, where a `fetch()`-raised
      exception surfaced as an unhandled `500` with no `crawl_runs` row at all). A `finally` block
      calls `registry.release(tenant_id, connector.name)` unconditionally — this is the single most
      important line in the ticket: a background-task exception must never leave a `(tenant_id,
      source)` permanently locked out of future crawls.
- [ ] Old `_run_and_record` removed (superseded by the above); `ConnectorRunResponse` removed if no
      longer referenced anywhere (confirm via grep before deleting).

## Test acceptance criteria

- [ ] Existing `tests/test_connectors_router.py` cases updated for the new response shape
      (`status="queued"`, no `row_count`/`fetched_at` in the accept-time body) — no regression in
      the unknown-source `404`, malformed-`since` `422`, missing-credentials `422` cases.
- [ ] A completed background crawl is observable via `GET /connectors/{source}/status` after the
      background task has run to completion (test drains/waits for the scheduled background task
      the same way FastAPI's own `TestClient` does — `TestClient` runs `BackgroundTasks` synchronously
      before returning the response in the common case, or the test explicitly waits on a
      `threading.Event` the fake connector sets after `fetch()` returns, whichever the dev agent
      finds actually reflects this app's real `BackgroundTasks` execution timing — do not assert
      "completed" is visible with no synchronization at all, since that would be a flaky, timing-
      dependent test, not a real assertion).
- [ ] A failing `fetch()` (fake connector raises) is recorded as `status="failed"` in `crawl_runs`,
      not left as `"queued"` forever, and does not leave the lock held afterward (a subsequent
      request for the same source succeeds with `202`, not `409`).
- [ ] **The required real, reproduced-before-fixed race condition test** — this is the ticket's
      headline acceptance criterion, not optional:
  - **Before-fix reproduction** (a permanent regression test, not a throwaway manual step): call the
    *old*, now-removed synchronous write logic's equivalent — i.e., call the low-level sequence
    (`latest_watermark_from_db` → `connector.fetch` → `add_price_records`) **twice, directly and
    concurrently, with no lock involved at all**, against a `FakeConnectorRecordRepository` whose
    `add_price_records` is configured to raise (simulating Postgres's real `UniqueViolation`) if
    called a second time with overlapping rows for the same `(tenant_id, source)` — proving, in code
    that will keep running in CI, exactly the failure mode this ticket fixes (both callers resolve
    the same `since`, both attempt to write, the second raises unhandled). This test's name and
    docstring must say plainly that it demonstrates the pre-fix bug mechanism, not exercise the new
    lock.
  - **After-fix proof, at the real HTTP layer**: a fake connector whose `fetch()` blocks on a
    `threading.Event` until released (simulating the real ~70s crawl); two real `threading.Thread`s,
    synchronized via a `threading.Barrier(2)`, each issue `client.post("/connectors/{source}/run")`
    against the FastAPI `TestClient` for the *same* `(tenant_id, source)` at effectively the same
    time. Assert: **exactly one** thread's response is `202`, the other's is `409` with the
    "crawl already in progress" detail; after releasing the blocked `fetch()` and letting the
    background task finish, `len(repository.price) == 1` (exactly one write, never two) and exactly
    one `crawl_runs` row reaches `"completed"` — no `500`, no duplicate insert, no corrupted state.
  - A third case for completeness: the same two-thread setup but for *different* `source` values
    (same tenant) — both must succeed with `202` (proves the lock doesn't over-serialize unrelated
    crawls).

## Review acceptance criteria (Tech Lead verifies personally)

- [ ] Read the diff directly: confirm the lock is acquired strictly after all validation and strictly
      before the watermark is resolved/the "queued" row is written (the actual TOCTOU fix).
- [ ] Confirm `registry.release` is reachable from every exit path of `_execute_crawl` (structural
      `finally`, not scattered `release()` calls that a new exception path could bypass).
- [ ] Re-run the full concurrency reproduction test personally (not trust the dev agent's report),
      including watching it actually demonstrate the pre-fix failure mode in the "before" test and a
      clean `409`/single-write outcome in the "after" test.
- [ ] Confirm the response body a client actually receives on `202` no longer implies a finished
      crawl (`status` is `"queued"`, not `"completed"`) — this is the exact shape gateway-api/
      dashboard-web's own follow-up tickets are keyed to.
- [ ] Run `services/ingestion-service`'s full suite; zero regressions in any pre-existing test file.

## Documentation acceptance criteria

- [ ] `services/ingestion-service/README.md`'s `POST /connectors/{source}/run` section rewritten:
      no longer says "Synchronous execution ... returns `202` once the crawl has actually run" — now
      documents the queued/background-execution behavior, the `409` rejection, the new
      `ConnectorRunAcceptedResponse` shape, and the `"queued"` addition to `crawl_runs`' status
      vocabulary (updating the field-default/status-vocabulary table wherever it's stated).
  the accepted-interim-tradeoff language this ticket removes cross-references `validation-service`'s
  own still-synchronous `POST /runs` — leave that comparison out or correct it, since it no longer
  describes this endpoint's actual behavior.
