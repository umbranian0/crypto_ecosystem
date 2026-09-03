# Sprint 24 — Crawl lifecycle control, part 2 (dashboard controls)

Sprint goal: a tenant can stop an in-flight crawl, restart a stopped one, and see real (or honestly
absent) live progress, entirely from the `/monitoring` dashboard — no `curl` required.

Backlog source: docs/product/backlog-crawl-lifecycle-control.md (Epic 3 — Dashboard controls). Hard
prerequisite: Sprint 23 (docs/sprints/sprint-23.md) — Epics 1 and 2's backend/proxy work — must be
complete and verified before this sprint starts; every story below calls an endpoint Sprint 23 builds.

Stories in scope, in execution order:

1. DASH-117 — Restart button once a crawl is stopped/completed/failed [Must]. Sequenced first even
   though it's numbered after DASH-116: it depends on nothing new beyond already-shipped DASH-110/
   INGEST-021 (from Sprint 23), reuses the existing `POST /monitoring/connectors/{source}/run` route
   unmodified, and is the cheapest, lowest-risk story in the whole backlog (UI-only, no new backend/
   proxy code). Banking it first gives an early, low-risk win before the two riskier stories below.
2. DASH-116 — Stop/cancel button on the crawl-status panel [Must]. Depends on GW-027 (Sprint 23).
   This is the literal, named ask ("stop it mid-flight... from the frontend, not just via curl").
3. DASH-118 — Richer progress display, replacing the three-state badge [Should]. Depends on the full
   Epic 2 backend chain (INGEST-024/025/026/027, GW-028 — all Sprint 23) and on DASH-116, sequenced
   last so it doesn't concurrently edit `_crawl_status_panel.html` alongside DASH-116. This is why it
   is scheduled after a Must-priority story it doesn't outrank on priority alone — a dependency/
   file-collision-avoidance order, not a silent re-prioritization.

Stories explicitly deferred: none — this sprint closes out the backlog's full 13-story scope (combined
with Sprint 23). No Epic-3 story is pushed further; all three land here.

Definition of done for this sprint:
- All 2 Must stories (DASH-117, DASH-116) complete; DASH-118 (Should) complete or explicitly
  re-flagged with reason if not.
- Every acceptance criterion checked off against the actual diff, including: stop button only appears
  for `queued`/`running`/`cancelling` rows and is disabled (not re-clickable) while `"cancelling"`;
  restart button only appears for `completed`/`failed`/`cancelled` rows and is mutually exclusive with
  the stop button on the same row; restart button's copy makes clear it continues from the last saved
  watermark, not from scratch; progress column shows a plain "no live progress for this source" string
  for blockchain.info sources rather than a blank cell or fabricated zero; no progress-display copy
  implies a prediction/forecast of remaining time or rows (CLAUDE.md's "never imply prediction" rule
  applies here even though this is an operational, not modeling, surface).
- Existing 5-second HTMX polling fragment continues to work unmodified in mechanism — only what it
  renders changes.
- `services/dashboard-web/README.md` updated to describe the new stop/restart/progress UI and its
  exact backend/proxy call sites.
- Full `services/dashboard-web` test suite re-run with zero regressions.
- `docs/product/backlog-crawl-lifecycle-control.md` closed out (all 13 stories done) after this sprint,
  matching this repo's own convention of marking a backlog file complete once its last story ships.
