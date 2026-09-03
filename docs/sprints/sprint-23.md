# Sprint 23 — Crawl lifecycle control, part 1 (backend: cancellation + live progress)

Sprint goal: a tenant's in-flight crawl for one `(tenant, source)` can be genuinely cancelled mid-fetch
(not merely marked as if it stopped) and its real-time progress (where the connector's fetch shape
allows it) is readable through `gateway-api`, with no dashboard-facing change yet.

Backlog source: docs/product/backlog-crawl-lifecycle-control.md (Epic 1 — Cancellable crawls; Epic 2 —
Live progress reporting). Epic 3 (dashboard controls) is explicitly deferred to Sprint 24 — see below.

Stories in scope, in execution order:

1. INGEST-021 — `crawl_runs` status vocabulary gains `running`/`cancelling`/`cancelled` [Must]. First:
   no dependency, and every other Epic 1/2 story needs these states to write into or report against.
2. INGEST-022 — Cooperative cancellation signal threaded through the fetch loop [Must]. Depends on
   INGEST-021 (needs the `running`/`cancelling` states to report against). This is the mechanism that
   makes cancellation real rather than cosmetic.
3. INGEST-023 — `CrawlRegistry` gains a per-crawl cancellation flag [Must]. Depends on INGEST-022 (the
   flag is meaningless without a fetch loop that reads it); extends the existing `INGEST-014` registry
   rather than introducing a second coordination mechanism.
4. INGEST-024 — `POST /connectors/{source}/cancel` endpoint + `crawl_runs` progress columns [Must].
   Depends on INGEST-021/022/023 — this is the endpoint the epic exists to deliver.
5. INGEST-025 — Binance connector: per-page progress checkpoints [Must]. Depends on INGEST-022 (shares
   the same loop-modification work) and INGEST-024 (the write-back method). Highest-value, lowest-risk
   progress story — Binance/BTC price is the platform's core dataset and already has the most natural
   checkpoint of the three connectors.
6. INGEST-026 — Reddit connector: per-submission/per-subreddit progress checkpoints [Should]. Depends on
   INGEST-024; can proceed in parallel with INGEST-025 (disjoint files). Sequenced after INGEST-025 in
   this list only because it is Should vs. Must, not because of a hard technical block.
7. INGEST-027 — Blockchain.info connector: document the before/after-only progress ceiling [Should].
   Depends on INGEST-024's contract shape; can run in parallel with 5–6. This story is a documentation/
   contract-shape guard for the platform's non-negotiable honesty posture (per CLAUDE.md), not new
   capability — do not let it slip past this sprint even though it's lowest engineering cost.
8. GW-027 — Proxy: `POST /ingestion/connectors/{source}/cancel` [Must]. Depends on INGEST-024. Thin,
   low-risk, single-file addition; Epic 3's stop button (Sprint 24) has nothing to call without it.
9. GW-028 — Confirm cancel/progress fields pass through the existing status proxy unmodified [Should].
   Depends on INGEST-024/INGEST-025. Verification-only unless the test fails, in which case the minimal
   fix is scoped inside this same ticket (mirrors `GW-024`'s own "confirm, don't assume" precedent).

Stories explicitly deferred: DASH-116, DASH-117, DASH-118 — all three are frontend dashboard controls
that call endpoints this sprint builds. DASH-116 hard-depends on GW-027; DASH-118 hard-depends on the
full Epic 2 backend chain plus GW-028. Scheduling any of them in this sprint would mean building UI
against endpoints that don't exist yet at ticket-breakdown time — deferred to Sprint 24, not dropped.
(Note: DASH-117 technically has no new dependency beyond already-shipped DASH-110/INGEST-021, and could
in principle ship early or even in this sprint — deliberately kept with its two sibling stories in
Sprint 24 instead, since it shares the same `_crawl_status_panel.html` template file as DASH-116/118 and
splitting one epic's UI work across two sprints for a two-line early win isn't worth the file-collision
risk or the review fragmentation. Tech Lead may reconsider this if Sprint 24 turns out to need an early
low-risk win.)

Definition of done for this sprint:
- All 6 Must stories (INGEST-021/022/023/024/025, GW-027) complete; both Should stories in scope
  (INGEST-026/027, GW-028) complete or explicitly re-flagged with reason if not.
- Every acceptance criterion in each story checked off against the actual diff, not self-reported.
- Unit tests proving: cancellation actually stops further pages/submissions (Binance/Reddit), is a
  documented no-op for blockchain.info; progress is reported incrementally for Binance/Reddit and
  absent (not zero, not fabricated) for blockchain.info; `crawl_runs` correctly resolves to
  `"cancelled"` vs. `"completed"` per the documented race condition in INGEST-024.
- `services/ingestion-service/README.md` updated: full six-value status vocabulary, per-connector
  cancellation/progress behavior including blockchain.info's documented ceiling.
- `services/gateway-api/README.md` updated where the new proxy route/contract changes are documented.
- Each touched service's existing test suite re-run with zero regressions.
- No story in this sprint touches `naive_first_engine`'s splitting/baseline/metric/DM-test code or
  redefines what a dataset is (ADR-0005 stands unchanged) — confirmed via `git status` scoped to
  `libs/naive_first_engine/`.
