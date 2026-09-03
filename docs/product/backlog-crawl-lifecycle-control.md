# Backlog — Crawl lifecycle control (stop / live progress / restart-from-checkpoint)

Source: `CLAUDE.md` (root — non-negotiable positioning: validation/audit infrastructure, never a
trading/prediction product; no service reads another service's DB schema directly; `dashboard-web`
calls `gateway-api` only); `docs/solution-design.md` section 8 (ingestion pipeline: per-tenant
TimescaleDB hypertables, `crawl_runs` as an *event* distinct from the *dataset*, the REST surface each
service owns); `docs/adr/0005-dataset-is-a-continuous-tenant-source-table.md` (a dataset is
`{tenant_id, source}`'s ongoing table; a crawl run is one connector execution appending to it — this
backlog only ever touches the crawl-run event, never reshapes the dataset concept); code read in full:
`services/ingestion-service/connectors/base.py` (`IngestionSource.fetch(since)`, `run_incremental`),
`services/ingestion-service/connectors/binance_price.py`, `blockchain_onchain.py`, `reddit_sentiment.py`
(the three connectors' actual fetch-loop shapes — read individually, not assumed uniform, see the
granularity finding below), `services/ingestion-service/src/app/crawl_registry.py` (the existing
per-`(tenant_id, source)` `threading.Lock`-based mutual-exclusion registry, `INGEST-014`),
`services/ingestion-service/src/app/routers/connectors.py` (`POST /connectors/{source}/run`,
`GET /connectors/{source}/status`, `_execute_crawl` background-task body), `services/ingestion-service/
README.md` (owns/does-not-own), `services/gateway-api/src/app/routers/ingestion.py` (the proxy layer,
`GW-019`/`GW-020`/`GW-023`/`GW-024`), `services/dashboard-web/src/app/routers/operator.py` and
`templates/monitoring.html`/`templates/_crawl_status_panel.html` (the existing trigger-a-crawl UI,
5-second HTMX polling, `DASH-109`/`110`/`114`/`115`); `docs/tickets/README.md` (next free ID per
prefix, confirmed by reading the actual index rather than assumed: `INGEST-020`, `GW-026`, `DASH-115`
are the highest shipped so far).

## Scope

**In scope**: per-`(tenant, source)` crawl cancellation (backend + proxy + UI button), per-`(tenant,
source)` live progress reporting during an in-flight crawl (backend + UI display), and a restart
control that is explicitly just a normal new-crawl trigger (reusing the existing incremental-fetch/
watermark mechanism, not a second "resume" code path).

**Out of scope, stated rather than silently assumed**:
- True pause/freeze-and-resume mid-fetch (the user's decision #1 — "restart" always means "run a new
  crawl that continues from the last saved watermark," never resuming a suspended in-process fetch).
- Any global/cross-tenant job queue or scheduler (decision #3 — this stays exactly as granular as the
  existing per-`(tenant, source)` model, no more, no less).
- Any change to `naive_first_engine`'s splitting/baseline/metric/DM-test code, or to how a *dataset* is
  defined (ADR-0005 stands unchanged) — this backlog only touches the crawl-run *event* lifecycle.
- A write UI for connector credentials (`DASH-112`'s deferred write form, unrelated to this request).

## Trigger-override disclosure

`ingestion-service`'s connector/API surface was already twice-disclosed as ahead of its original
trigger #10/#6 (see `docs/product/backlog-ingestion-pipeline-integration.md`'s own disclosure
paragraph, and `INGEST-001`'s retroactive tracking ticket). This backlog is a **third** extension of
that same already-overridden surface — it adds cancellation/progress to connectors and an endpoint that
already exist ahead of schedule, not a fresh trigger decision of its own. Recorded here per the same
disclosure discipline `docs/adr/0003-disclosed-trigger-override-pattern.md` establishes, so nobody has
to go looking for a trigger-table row this work doesn't have one against.

## Design finding that shapes Epic 2 (read before grooming — do not assume uniform progress granularity)

Reading each connector's actual `fetch()` loop shows three genuinely different shapes, not one:

- **`BinancePriceConnector.fetch`** (`binance_price.py`) already loops over paginated `_fetch_batch`
  calls (up to 1000 klines/page) with a `cursor` that advances every iteration — this is a natural,
  already-existing checkpoint boundary. Reporting "N rows fetched so far" between pages is close to
  free.
- **`RedditSentimentConnector.fetch`** (`reddit_sentiment.py`) iterates `subreddit.new(limit=...)`,
  which `praw` yields lazily one submission at a time across (by default) two subreddits — also a real,
  naturally-occurring per-item checkpoint, just finer-grained (per submission, or per subreddit as a
  coarser option) rather than per network page.
- **`BlockchainInfoConnector.fetch`** (`blockchain_onchain.py`) makes **one single blocking HTTP `GET`**
  per crawl and only slices/parses the response after it returns — there is no loop, no page, no
  natural mid-fetch checkpoint at all. Genuine live progress for this connector is not achievable
  without either (a) self-chunking the date range into multiple smaller requests (a real behavior
  change to the connector, not just instrumentation) or (b) accepting "before" (queued/running) and
  "after" (completed/failed) as the only two states this source can ever honestly report. This backlog
  does not propose (a) — it is out of scope unless the founder decides the extra API calls against a
  free public endpoint are worth it — and requires the dashboard copy to say so plainly rather than
  imply a live counter that isn't real (see `INGEST-027`, `DASH-118`).

## Prioritization scheme

MoSCoW, same convention as this repo's other backlogs. Sequencing is a hard dependency chain, stated
per story: status-vocabulary + cancellation-signal plumbing (backend) must land before the cancel
endpoint, which must land before the gateway proxy, which must land before any dashboard button has
something real to call — the same "backend before frontend controls" ordering the requester already
named.

---

## Sprint 23 close-out (Epic 1 + Epic 2, backend — done)

**INGEST-021 through INGEST-027 and GW-027/GW-028 are all done** — see `docs/tickets/README.md`'s
"Sprint 23" section and each ticket's own file for the full Analysis/Design/Implementation/Test/Review/
Documentation record. Summary of what is now real, live-verified capability (not merely coded):

- A tenant's in-flight crawl for one `(tenant, source)` can be genuinely cancelled mid-fetch via
  `POST /connectors/{source}/cancel` (`ingestion-service`, `INGEST-024`) and, identically, via
  `POST /ingestion/connectors/{source}/cancel` (`gateway-api` proxy, `GW-027`) — live-proven end to end,
  including the correct `404`/`409` outcomes and the documented "finishes before any checkpoint observed
  the cancel" race resolving to `"completed"`, not `"cancelled"`.
- Live progress (`rows_fetched_so_far`, `updated_at`) is readable through both
  `GET /connectors/{source}/status` and `GET /ingestion/connectors/{source}/status` for Binance
  (per-page, `INGEST-025`) and Reddit (per-submission, `INGEST-026`); `blockchain_info_*` sources
  honestly report `null`/absent progress (`INGEST-027`), never a fabricated `0` — live-verified through
  both surfaces.
- `crawl_runs`' status vocabulary is six values (`queued`/`running`/`cancelling`/`cancelled`/
  `completed`/`failed`, `INGEST-021`), and the progress columns update **in place** on the crawl's own
  `"running"` row rather than growing one row per checkpoint (`INGEST-024`'s own design decision,
  disclosed for Sprint 24: a future dashboard sparkline would need a richer per-checkpoint-history shape
  from the start, not a bolt-on migration of this simpler single-counter one).

**What Sprint 24 (Epic 3, dashboard controls) still needs to build against this now-complete backend**:
`DASH-116` (stop button, calls `GW-027`), `DASH-117` (restart button, reuses the existing
`POST /monitoring/connectors/{source}/run` route unchanged — no new backend/proxy work needed for this
one), `DASH-118` (richer progress display, reads `GW-028`'s confirmed pass-through of the progress/
`updated_at` fields and must render blockchain.info's `null` case as an explicit "no live progress for
this source" string, never a blank cell or a spinner that never resolves). All three of Epic 3's
hard dependencies (`GW-027`, the six-value status vocabulary, the progress/`updated_at` fields via
`GW-028`) are done and live-verified as of this sprint — Sprint 24 has a real, proven backend to build
against, not an assumed one.

## Epic 1 — Cancellable crawls (backend)

### INGEST-021 — `crawl_runs` status vocabulary gains `running`/`cancelling`/`cancelled` [Must]

**As** `ingestion-service`'s own crawl-run bookkeeping **I want** the `status` column's vocabulary
extended beyond today's `queued`/`completed`/`failed` (`INGEST-005`) to also include `running`,
`cancelling`, and `cancelled` **so that** a request to stop a crawl, and a crawl actually being in
flight rather than merely accepted, both have a real, distinct, queryable state — not an overloaded
reuse of `queued`.

Acceptance criteria:
- [ ] `record_crawl_run`'s `status` parameter accepts `"running"`, `"cancelling"`, `"cancelled"` in
      addition to the three existing values; no existing caller's behavior changes for the three
      existing values.
- [ ] `_execute_crawl` writes a `"running"` row immediately before calling `connector.fetch(...)`, not
      just at completion — this is what makes `GET /connectors/{source}/status` able to report
      "actually in progress" instead of only "queued" or "done" (ties directly into `INGEST-024` below).
- [ ] A migration adds no new column for this story (status stays a plain string/enum column per
      `INGEST-002`'s existing shape) — this is a vocabulary extension, not a schema shape change.
- [ ] `services/ingestion-service/README.md`'s `crawl_runs` status description is updated to list all
      six values and what each means.

Rationale for priority: every other story in Epic 1 needs a state to write into; this is the
foundation, and it is small and isolated (one column's accepted values), matching `ingestion-service`'s
own "owns the `ingestion` schema" boundary.
Depends on: none.

### INGEST-022 — Cooperative cancellation signal threaded through the fetch loop [Must]

**As** the background task executing a tenant's crawl **I want** a way to signal "stop at your next
safe checkpoint" into `IngestionSource.fetch()` and have `BinancePriceConnector`/`RedditSentimentConnector`
honor it between pages/submissions **so that** cancelling a crawl actually stops new work soon, rather
than only being a UI-side illusion that the backend ignores until natural completion.

Acceptance criteria:
- [ ] `IngestionSource.fetch(since)`'s signature gains an optional `should_cancel: Callable[[], bool] |
      None = None` parameter (default `None`, so this is additive, not a breaking change to any
      existing caller that doesn't pass it) — checked, not polled by a separate thread, honoring the
      existing single-threaded-per-crawl execution model `crawl_registry.py` already assumes.
- [ ] `BinancePriceConnector.fetch`'s pagination loop calls `should_cancel()` once per page, immediately
      after appending a batch's rows and before requesting the next page; if `True`, returns a
      `FetchResult` built from whatever rows were already accumulated (not empty, not the full
      unfetched range) rather than raising.
- [ ] `RedditSentimentConnector.fetch`'s per-submission loop calls `should_cancel()` at a similarly
      natural boundary (per submission or per subreddit, Tech Lead's call at ticket time) with the same
      "return what's accumulated so far" contract.
- [ ] `BlockchainInfoConnector.fetch` accepts the same parameter for interface uniformity but is
      documented, in its own docstring, as unable to honor it mid-request — cancellation for this
      connector can only take effect *before* its one blocking `GET` starts, never during it. This is
      the honest consequence of the granularity finding above, not silently glossed over.
- [ ] A unit test per connector proves `should_cancel` returning `True` after the first page/submission
      stops further pages/submissions from being fetched (Binance/Reddit) or is a documented no-op
      (blockchain.info).
- [ ] No story here authorizes fitting/writing partial rows outside the existing append-only,
      immutable-raw-zone write contract (`connectors/base.py`'s own docstring) — a cancelled crawl still
      only ever writes rows it actually and completely fetched, never a partial/corrupt row.

Rationale for priority: this is the actual mechanism that makes cancellation real rather than cosmetic
— without it, `INGEST-023`'s endpoint could only ever mark a row `"cancelling"` and then watch it
finish anyway. Must, per the user's own decision #1 framing ("stops it mid-flight," not "marks it as if
it stopped").
Depends on: INGEST-021 (needs the `running`/`cancelling` states to report against, though the fetch-loop
code change itself is independently testable).

### INGEST-023 — `CrawlRegistry` gains a per-crawl cancellation flag [Must]

**As** `_execute_crawl`'s background task **I want** `CrawlRegistry` to hold a cancellation flag per
`(tenant_id, source)` alongside its existing in-flight lock **so that** a separate request (the cancel
endpoint, `INGEST-024`) can signal into an already-running background task without the two needing any
shared state beyond the registry that already exists for exactly this kind of per-crawl coordination.

Acceptance criteria:
- [ ] `CrawlRegistry` gains `request_cancel(tenant_id, source) -> bool` (returns `True` only if a
      matching in-flight entry exists — mirrors `try_acquire`'s own "no key, no effect" precedent) and
      `should_cancel(tenant_id, source) -> bool`, both guarded by the existing `threading.Lock` — no
      second synchronization primitive introduced for what is the same one registry's job.
      `release(tenant_id, source)` clears any pending cancellation flag for that key, so a slot is never
      pre-cancelled by a stale flag from a prior crawl of the same `(tenant_id, source)`.
- [ ] `_execute_crawl` passes `lambda: registry.should_cancel(tenant_id, connector.name)` as `fetch`'s
      new `should_cancel` argument (`INGEST-022`).
- [ ] A unit test proves: acquire → request_cancel → should_cancel returns `True` for that exact key
      only (not for a different tenant or a different source) → release clears it → a fresh acquire of
      the same key starts with `should_cancel` reporting `False` again.

Rationale for priority: `INGEST-014`'s registry is explicitly named as "don't reinvent" in the request
— this story extends it rather than introducing a second coordination mechanism, staying inside
`ingestion-service`'s existing module boundary and this repo's own DRY convention (extract/extend on
reuse, not duplicate).
Depends on: INGEST-022 (the flag is meaningless without a fetch loop that reads it).

### INGEST-024 — `POST /connectors/{source}/cancel` and `crawl_runs` progress columns [Must]

**As** a tenant (via the dashboard, eventually) **I want** an endpoint that actually stops my in-flight
crawl for one source, and a `crawl_runs` row that reflects real in-flight progress **so that** "stop"
and "how's it going" are both true, current facts the API can answer — not just a status string frozen
at `"queued"` until the crawl happens to finish.

Acceptance criteria:
- [ ] `crawl_runs` gains two additional columns (or a documented equivalent shape — Tech Lead's call):
      a progress counter (e.g. `rows_fetched_so_far`) and `updated_at` (last time this row's progress
      was refreshed) — additive migration, no existing column removed or renamed, matching
      `INGEST-016`/`017`/`018`'s own precedent of additive, backward-compatible ingestion-schema
      migrations.
- [ ] `_execute_crawl`'s call into `fetch()` is wrapped so that Binance's/Reddit's per-checkpoint
      progress (`INGEST-022`) is written back to the row's progress counter via the repository — a new
      `record_crawl_progress(tenant_id, source, rows_fetched_so_far)` method on
      `ConnectorRecordRepository`, called from inside the `should_cancel` callback closure (one call
      site serves both "check if I should stop" and "report how far I've gotten," not two separate
      callbacks threaded through `fetch()`).
- [ ] `POST /connectors/{source}/cancel` (tenant-authenticated, same `get_tenant_context` seam every
      other route in this router uses): returns `404` for an unknown `source` (same convention as
      `POST /connectors/{source}/run`); returns `409` if no crawl is currently in flight for this
      `(tenant, source)` (nothing to cancel — mirrors `run_connector`'s own `409` "already in progress"
      framing, inverted); on success, calls `registry.request_cancel(...)`, writes a `"cancelling"`
      `crawl_runs` row immediately, and returns `202` with `{source, status: "cancelling"}` — the actual
      transition to `"cancelled"` happens asynchronously in `_execute_crawl` once the fetch loop honors
      the signal, exactly mirroring `POST .../run`'s own "202 now, poll status for the real outcome"
      shape (`INGEST-015`'s precedent).
- [ ] `_execute_crawl`'s own completion logic: if `should_cancel` was ever observed `True` during the
      fetch, the final `record_crawl_run` call writes `"cancelled"` (with whatever partial row count was
      actually written) instead of `"completed"` — a crawl that finishes normally after cancellation was
      requested but before any checkpoint observed it still legitimately writes `"completed"` (an honest
      race, not a bug to paper over).
- [ ] `GET /connectors/{source}/status`'s response gains the progress counter and `updated_at` fields,
      alongside the existing `status`/`timestamp`/`row_count`.
- [ ] For `blockchain_info_*` sources specifically: a cancel request received while that connector's one
      blocking `GET` is already in flight writes `"cancelling"` immediately (honest acknowledgment of
      the request) but the row only ever resolves to `"cancelled"` if the cancel lands *before* `fetch`
      starts its request (registry check happens first); once the request is in flight, the crawl runs
      to natural completion/failure regardless of the cancel request — documented in this connector's
      own docstring and in `services/ingestion-service/README.md`, not silently assumed identical to
      Binance/Reddit's behavior.

Rationale for priority: this is the endpoint the entire epic exists to deliver — the previous three
stories are its prerequisites. Must, directly answering the request's core ask ("stop it mid-flight").
Depends on: INGEST-021, INGEST-022, INGEST-023.

### GW-027 — Proxy: `POST /ingestion/connectors/{source}/cancel` [Must]

**As** `dashboard-web` **I want** a thin, tenant-authenticated `gateway-api` proxy route forwarding to
`ingestion-service`'s new cancel endpoint **so that** the dashboard never calls `ingestion-service`
directly, matching this platform's own "no service talks to another except through `gateway-api`'s
public contract, and `dashboard-web` calls `gateway-api` only" rule.

Acceptance criteria:
- [ ] `POST /ingestion/connectors/{source}/cancel` added to `services/gateway-api/src/app/routers/
      ingestion.py`, reusing `get_authenticated_tenant`/`build_downstream_headers`/`_call_downstream`/
      `_raise_for_error` exactly as every other route in this file already does — no new auth mechanism,
      no new transport-error pattern (this repo's own DRY convention, and the same precedent `GW-019`/
      `GW-024` already established for this exact router).
- [ ] The downstream response body/status code (`202`/`404`/`409`) is forwarded unmodified, matching
      this file's existing pass-through-dict precedent for `run_connector`/`connector_status` — no local
      Pydantic model invented for a one-shot action response.
- [ ] A test proves the `409` "nothing to cancel" case is forwarded unmodified (same style as
      `GW-024`'s own `test_run_connector_conflict_returns_409_forwarded_unmodified`).

Rationale for priority: Must — the dashboard button (Epic 3) has nothing to call without this, and it
is a thin, low-risk, single-file addition once `INGEST-024` exists.
Depends on: INGEST-024.

---

## Epic 2 — Live progress reporting (backend)

### INGEST-025 — Binance connector: per-page progress checkpoints [Must]

**As** a tenant polling their own crawl's status **I want** the Binance price connector to report
"N rows fetched so far" after each paginated batch, not only at final completion **so that** a
long-running historical backfill (`default_backfill_start()` goes back to 2017) shows real, moving
progress rather than a static "queued" for however long the full fetch takes.

Acceptance criteria:
- [ ] `BinancePriceConnector.fetch`'s existing pagination loop calls a new optional
      `on_progress: Callable[[int], None] | None = None` argument once per page with the cumulative row
      count fetched so far (same call site the `should_cancel` check from `INGEST-022` already sits at —
      one loop iteration, two optional callbacks, not two separately-threaded loops).
  parity note: this callback is separate from `should_cancel` because progress-reporting and
  cancel-checking are logically distinct concerns even though `INGEST-024`'s implementation may choose
  to serve both from one closure at the call site in `_execute_crawl`.
- [ ] `_execute_crawl` wires `on_progress` to `repository.record_crawl_progress(...)` (`INGEST-024`).
- [ ] A unit test with a fake multi-page response sequence proves `on_progress` is called once per page
      with a monotonically increasing cumulative count, and not called at all when the source has no new
      rows since `since`.

Rationale for priority: Must — Binance/BTC price is the platform's core dataset (per
`da-tese-ao-produto.md`'s own thesis scope) and already has the most natural, cheapest-to-implement
checkpoint of the three connectors; this is the highest-value, lowest-risk progress story.
Depends on: INGEST-022 (shares the same loop-modification work), INGEST-024 (the write-back method).

### INGEST-026 — Reddit connector: per-submission (or per-subreddit) progress checkpoints [Should]

**As** a tenant polling their own crawl's status **I want** the Reddit sentiment connector to report
progress as it scores new submissions, not only at the end **so that** a crawl across two subreddits
and up to 500 submissions each shows real progress rather than one long silent wait.

Acceptance criteria:
- [ ] `RedditSentimentConnector.fetch`'s submission loop calls the same `on_progress` shape
      (`INGEST-025`'s signature, reused unmodified — one callback shape across connectors, not a
      per-connector bespoke one) at a natural boundary: per submission scored, or per subreddit
      completed (Tech Lead's call, stated explicitly in the ticket rather than left ambiguous).
- [ ] A unit test with a fake multi-subreddit submission list proves progress is reported incrementally,
      not only once at the end.
- [ ] Explicitly documented (docstring + README): this connector's progress granularity is coarser or
      finer than Binance's depending on the chosen checkpoint boundary — the dashboard must not assume
      identical update frequency across sources (feeds `DASH-118`'s own honesty requirement).

Rationale for priority: Should, not Must — real value, but Reddit sentiment is the platform's secondary
data source (per `solution-design.md`'s own "phase 2" framing for sentiment/on-chain), so it can land
after the core price-connector story without blocking the epic's main value.
Depends on: INGEST-024 (the write-back method), can proceed in parallel with INGEST-025 (disjoint files).

### INGEST-027 — Blockchain.info connector: document the before/after-only progress ceiling [Should]

**As** the platform's own honesty obligation about what this system actually measures (`CLAUDE.md`:
never imply a capability the code doesn't have) **I want** `BlockchainInfoConnector`'s single-request
fetch shape to be explicitly documented as unable to produce genuine mid-fetch progress, with its status
endpoint responding accordingly **so that** neither the API contract nor the dashboard ever implies a
live counter that isn't real for this specific connector.

Acceptance criteria:
- [ ] `BlockchainInfoConnector.fetch`'s docstring states plainly (per the granularity finding above) that
      it makes one blocking HTTP call and has no natural checkpoint; `on_progress`/`should_cancel` are
      accepted for interface uniformity but only ever called 0 or 1 times (never incrementally).
- [ ] `GET /connectors/{source}/status` for a `blockchain_info_*` source, while a crawl is `"running"`,
      returns the progress counter as `null`/absent rather than a stale or fabricated number — the
      response schema allows this field to be optional, not defaulted to `0` in a way that could be
      misread as "zero rows so far" (a factually different claim than "unknown").
- [ ] `services/ingestion-service/README.md` gains a short, explicit note under this connector's
      existing description: "no live progress; status reports only queued/running/completed/failed/
      cancelled, no incremental row count."
- [ ] No story anywhere in this backlog proposes self-chunking blockchain.info's date range into
      multiple requests to manufacture progress — that would be a real behavior/API-load change,
      explicitly out of scope per this backlog's own scope section, flagged to the founder as a
      possible future story rather than silently bundled in here.

Rationale for priority: Should — this is mostly a documentation/contract-shape story (small, low
engineering cost) but it directly protects the platform's non-negotiable honesty posture, so it should
not slip indefinitely even though it unlocks no new capability by itself.
Depends on: INGEST-024 (the schema/contract it documents against).

### GW-028 — Confirm cancel/progress fields pass through the existing status proxy unmodified [Should]

**As** `dashboard-web` **I want** confirmation (not a code rewrite) that `GET /ingestion/connectors/
{source}/status`'s existing generic dict pass-through already forwards `INGEST-024`'s new progress
fields and `INGEST-021`'s new status values **so that** no gateway-api change is silently required
without being checked, the same way `GW-024` confirmed `INGEST-015`'s async contract needed no
`connector_status` code change.

Acceptance criteria:
- [ ] A test proves `GET /ingestion/connectors/{source}/status` forwards a `"running"`/`"cancelling"`/
      `"cancelled"` status value and the new progress/`updated_at` fields unmodified, exactly as
      `GW-024`'s own regression test did for the `queued`/`202`/`409` contract change.
- [ ] If (and only if) that test fails, the minimal fix is scoped and added as part of this same ticket
      — not a separate one, per this file's own "extend the same handler flow" precedent.

Rationale for priority: Should — cheap to verify, protects against a silent contract drift, but is not
itself new capability (mirrors `GW-024`'s own "confirm, don't assume" framing exactly).
Depends on: INGEST-024, INGEST-025.

---

## Epic 3 — Dashboard controls (frontend)

### DASH-116 — Stop/cancel button on the crawl-status panel [Must]

**As** a tenant watching their own crawl in `/monitoring` **I want** a "stop this crawl" button that
only appears while a crawl for that source is actually running **so that** I can interrupt a
long-running or mistakenly-triggered crawl without needing `curl`.

Acceptance criteria:
- [ ] `_crawl_status_panel.html`'s per-source row renders a stop button only when `entry.status` is one
      of `queued`/`running`/`cancelling` (extending the same `{% for entry in crawl_statuses %}` loop
      already there, not a new panel) — a `completed`/`failed`/`cancelled` row shows no stop button.
      While `status == "cancelling"`, the button is disabled/replaced with a "stopping…" label rather
      than re-clickable (avoids firing a second, redundant cancel request).
- [ ] The button posts (HTMX `hx-post`, matching `trigger_crawl`'s existing pattern) to a new
      `POST /monitoring/connectors/{source}/cancel` route in `app/routers/operator.py`, which calls
      `GW-027`'s proxy via the same `DownstreamHeadersDep`/`_call_downstream` seam every other action
      route in this file already uses — no new transport mechanism, no container/OS-level control
      surface (this module's own established structural boundary, unchanged).
- [ ] A small result fragment (`_crawl_cancel_result.html`, matching `_crawl_trigger_result.html`'s
      existing convention) confirms the stop request was accepted (`202`) or shows the forwarded `404`/
      `409` via the existing `_render_error_for_status` (no new error-handling pattern, per this file's
      own DRY discipline).
- [ ] The existing 5-second polling fragment (`crawl_status_fragment`, `DASH-115`'s route) naturally
      reflects the transition to `"cancelling"` → `"cancelled"` without any change to the polling
      mechanism itself — reuses, does not replace, the existing HTMX polling loop.

Rationale for priority: Must — this is the literal, named ask ("stop it mid-flight... from the
frontend, not just via curl").
Depends on: GW-027.

### DASH-117 — Restart button once a crawl is stopped/completed/failed [Must]

**As** a tenant whose crawl has stopped (cancelled, completed, or failed) **I want** a "restart" button
in the same row **so that** I can trigger a fresh crawl that naturally continues from the last saved
watermark, without needing to understand that this is "just" the existing trigger-crawl action under a
different label.

Acceptance criteria:
- [ ] `_crawl_status_panel.html`'s per-source row renders a restart button when `entry.status` is one of
      `completed`/`failed`/`cancelled` (mutually exclusive with `DASH-116`'s stop button — a row never
      shows both at once).
- [ ] The restart button posts to the **existing** `POST /monitoring/connectors/{source}/run` route
      (`DASH-110`, unchanged) — no new backend endpoint, no new proxy route, per the user's decision #1
      that restart is "just a normal new crawl trigger," and per `ingestion-service`'s own
      `latest_watermark_from_db`-first resolution order (`run_connector`'s existing logic already
      prefers the DB watermark over any `since` override on every crawl after the first) which is what
      makes "continues from the last checkpoint" true automatically — no new code is needed for the
      continuation behavior itself, only for exposing the button.
- [ ] A test confirms clicking restart after a `"cancelled"` status reuses the exact same route/handler
      `trigger_crawl` already has test coverage for — not a new, parallel "restart" handler function.
- [ ] UI copy on the button/label makes clear this restarts from the last saved point, not from scratch
      (a plain-language honesty requirement, not a technical one — e.g. "Restart (continues from last
      checkpoint)" rather than an unqualified "Restart").

Rationale for priority: Must — the second literal, named ask, and it is the cheapest story in this
entire backlog (no new backend/proxy work, UI-only), so there's no reason to defer it once `DASH-116`'s
status-vocabulary display work is in place.
Depends on: none beyond existing `DASH-110`/`INGEST-021` (for the `cancelled` status value to trigger
the button's visibility condition).

### DASH-118 — Richer progress display, replacing the three-state badge [Should]

**As** a tenant watching `/monitoring` **I want** the crawl-status panel to show a real progress
indicator (e.g. "run 143,000 rows fetched so far, updated 3s ago") when the backend has one, and an
honest "no live progress available for this source" message when it doesn't (blockchain.info,
`INGEST-027`) **so that** the panel is more informative than today's `queued`/`completed`/`failed`
badge without ever implying more precision than the underlying connector actually provides.

Acceptance criteria:
- [ ] `_crawl_status_panel.html`'s table gains a "Progress" column, populated from `GET /connectors/
      {source}/status`'s new progress/`updated_at` fields (`INGEST-024`, forwarded per `GW-028`).
- [ ] When the progress field is present (Binance/Reddit, `INGEST-025`/`026`), the column shows the row
      count and a relative "updated Ns ago" derived from `updated_at`.
- [ ] When the progress field is absent (blockchain.info, `INGEST-027`), the column shows a plain,
      explicit "no live progress for this source" string — never a blank cell that could be misread as
      "0 rows" or a loading spinner that never resolves.
- [ ] The existing three status values' visual treatment (`queued`/`completed`/`failed`) is unchanged in
      meaning; `running`/`cancelling`/`cancelled` (`INGEST-021`) get their own equally clear labels, not
      folded into an ambiguous reuse of an existing one.
- [ ] No copy anywhere on this panel implies the progress figure is a prediction, forecast, or estimate
      of remaining time/rows — it is a plain count of what has already been fetched, consistent with
      `CLAUDE.md`'s "never imply prediction" rule even though this is an operational, not a modeling,
      surface (an easy rule to think doesn't apply here — stated explicitly so it isn't skipped).

Rationale for priority: Should — real, requested value ("richer progress display... more informative
than the current three-state badge"), but strictly depends on Epic 2's backend work being real first;
sequenced after the Must-priority stop/restart buttons since a plain status-string upgrade (already
partially true today) is lower risk than the new progress numbers this story surfaces.
Depends on: INGEST-024, INGEST-025, INGEST-026, INGEST-027, GW-028, DASH-116 (shares the same panel
template file — sequenced after to avoid two stories mid-editing the same partial concurrently).

---

## Sequencing summary for the PM/Tech Lead

Strictly layered, backend before proxy before frontend, matching this repo's own established pattern
for every prior ingestion-adjacent backlog:

1. `INGEST-021` (status vocabulary) — no dependency, start first.
2. `INGEST-022` (cancellation signal in fetch loops) → `INGEST-023` (registry flag) — sequential, same
   reasoning chain.
3. `INGEST-024` (cancel endpoint + progress columns) — depends on 1–2.
4. `INGEST-025` (Binance progress) and `INGEST-026` (Reddit progress) — parallel, disjoint files, both
   depend on `INGEST-024`'s write-back method.
5. `INGEST-027` (blockchain.info documentation) — depends on `INGEST-024`'s contract shape; can run in
   parallel with 4.
6. `GW-027` (cancel proxy) — depends on `INGEST-024`. `GW-028` (status-proxy confirmation) — depends on
   `INGEST-024`/`INGEST-025`. Parallel with each other.
7. `DASH-116` (stop button) — depends on `GW-027`. `DASH-117` (restart button) — depends on nothing new
   beyond already-shipped `DASH-110`/`INGEST-021`, so it can actually ship *before* `DASH-116` if the PM
   wants an early, low-risk win. `DASH-118` (progress display) — depends on the full Epic 2 backend
   chain plus `GW-028`, and should be sequenced after `DASH-116` to avoid two stories concurrently
   editing `_crawl_status_panel.html`.

## Open questions for the founder/Tech Lead, flagged rather than silently assumed

1. **Reddit checkpoint granularity** (`INGEST-026`): per-submission vs. per-subreddit progress updates —
   left as the Tech Lead's call in the story, but worth the founder's opinion if dashboard "freshness"
   expectations are specific (per-submission is finer but means more DB writes per crawl).
2. **Blockchain.info self-chunking** (`INGEST-027`): explicitly out of scope here (would add real API
   load against a free public endpoint to manufacture progress that doesn't naturally exist) — confirm
   this is acceptable permanently, or worth a future story if tenants specifically complain about this
   one connector's silence during long fetches.
3. **`crawl_runs` progress-column shape** (`INGEST-024`): a single running counter vs. richer
   per-checkpoint history (e.g. a JSON array of `{at, rows}` samples) — the acceptance criteria assume
   the simpler single-counter shape; flag if the dashboard eventually wants a sparkline/rate display,
   since that would need the richer shape from the start rather than a later migration.
