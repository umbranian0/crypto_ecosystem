# Sprint 15 — `services/dashboard-web`: build `DASH-005` (runs list view), now that `DASH-005-GAP` is closed

Sprint goal: a tenant can open a runs-list page in `services/dashboard-web` that calls the real,
tenant-scoped `GET /runs` proxy route and lists their runs newest-first, linking to each run's detail
page — closing the one gap left open from Sprint 11's PoC (`DASH-005`, blocked since Sprint 11 on
`DASH-005-GAP`, which Sprint 14 closed at the `validation-service`/`gateway-api` level).

Backlog source: `docs/product/backlog-dashboard-web.md` (`DASH-005`, `DASH-005-GAP`, `DASH-009`).
Confirming inputs read directly, not assumed: `docs/sprints/sprint-11.md` (`DASH-005`'s original
deferral reasoning and scheduling decision), `docs/sprints/sprint-14.md`'s Outcome section (`VS-022`
and `GW-016` both done, 87/87 and 72/72 tests passing against real Postgres/Redis containers),
`services/gateway-api/README.md`'s Contract section (`GET /runs` (GW-016) real response shape),
`docs/tickets/DASH-009.md` (Outcome section, done in Sprint 11 with a disclosed fallback).

## Pre-planning checks performed (stated explicitly, not assumed)

- `docs/sprints/` currently ends at `sprint-14.md` (closed, full Outcome section present, all four
  in-scope stories done). No `sprint-15.md` exists yet and no earlier sprint file has an incomplete
  Outcome section that would need to be carried forward. This is confirmed to be **Sprint 15**.
- **`DASH-005-GAP` verified closed directly, not trusted from this task's own summary**:
  - `docs/sprints/sprint-14.md`'s Outcome section states `VS-022` (tenant-scoped, paginated
    `GET /runs` on `validation-service`) and `GW-016` (its `gateway-api` proxy) are both done, with
    real, personally-re-run test results: `87 passed` (validation-service) and `72 passed`
    (gateway-api), against real Postgres/Redis containers, not mocks alone.
  - `services/gateway-api/README.md`'s Contract section, read directly this session, confirms the
    route is live and documents its exact real shape: `GET /runs` (GW-016) is tenant-scoped and
    paginated (`limit`/`offset` forwarded to `validation-service` unmodified, out-of-range `422`
    forwarded as-is), returning `RunListResponse` — `{items: list[RunSummaryResponse], limit: int,
    offset: int, total: int}` — where `RunSummaryResponse` (`{id, dataset_id, horizon, status,
    created_at, completed_at}`) is imported from `naive_first_common.contracts` (ARCH-003 shared
    definition, not redefined locally). This is the real shape `DASH-005`'s own implementation must
    consume — not the shape guessed in the original `DASH-005-GAP` write-up.
  - Conclusion: the gap is genuinely closed at the ticket level, not merely claimed closed. `DASH-005`
    is unblocked.
- `docs/implementation-plan.md` sections 2 and 6 read directly: this sprint adds one page to an
  already-triggered, already-built service (`services/dashboard-web`, standing trigger-#8 override
  first recorded in Sprint 11) and consumes an already-live route on an already-triggered service
  (`gateway-api`). No new module is scaffolded, no unfired trigger is crossed, no service-boundary
  violation (`dashboard-web` calls `gateway-api`'s HTTP API only, never `validation-service` directly
  or any DB schema — matches DASH-003's existing DI seam pattern).
- `docs/tickets/DASH-009.md` read in full (Outcome section): `DASH-009` (Selenium E2E suite) is done,
  5/5 e2e tests passing, but its flow 3 ("view a completed run") uses a disclosed fallback — navigating
  directly to the run id returned by flow 2's own submit-and-redirect, specifically because no list
  page existed at the time. Both Sprint 11's and Sprint 14's own handoff notes already flagged this as
  a named future follow-up once `DASH-005` ships. See the dedicated decision section below for whether
  that follow-up belongs in this sprint.
- No team size/velocity given for this sprint. Sized against precedent: this is a small, single-page
  addition plus one existing test file's internal update — closer in shape to Sprint 09 (2 stories, one
  dependency pair) than to a full-service build like Sprint 05/11.

## Stories in scope, and the `DASH-009` scope decision (stated explicitly, with reasoning)

**In scope: `DASH-005`, and `DASH-009`'s flow-3 update, in that order.**

1. `DASH-005` [Must, `dashboard-web`] — runs list view, previously blocked, now unblockable.
   - Depends on: `DASH-005-GAP` (closed by Sprint 14's `VS-022`/`GW-016`), `DASH-003` (the DI seam,
     already built and done in Sprint 11).
   - Implementation must consume the real `RunListResponse`/`RunSummaryResponse` envelope documented
     above (`items`/`limit`/`offset`/`total`, `RunSummaryResponse` fields `id, dataset_id, horizon,
     status, created_at, completed_at`) — not a guessed shape. Its own backlog acceptance criteria
     (one row per run: id/status/dataset_id/horizon/created_at/completed_at, linking to `DASH-004`,
     most-recent-first) map directly onto this real envelope with no gaps.
   - No client-side pagination/sorting invention beyond what `GET /runs`'s own `limit`/`offset`/
     `created_at DESC` ordering already provides — matches the backlog's own "no client-side substitute"
     constraint that originally blocked this story.

2. `DASH-009` extension (flow 3, "view a completed run") — **decision: in scope, same story ID, not a
   new invented backlog item.**

   Reasoning, stated explicitly since this is a judgment call and not a distinct new ticket:
   - This PM role's mandate is to pull only from already-approved, already-prioritized backlog scope,
     not invent new stories. I am treating this as *finishing* `DASH-009`'s own already-approved
     acceptance criteria, not as new scope, for a specific reason: `DASH-009`'s own backlog `Depends
     on:` line reads "`DASH-005` (or its `DASH-005-GAP` fallback)" — the fallback was explicitly named
     in the backlog itself as a stand-in for `DASH-005`, used "since `DASH-005` is deferred" (Sprint
     11's and the ticket's own words), not as a permanent, equally-valid alternative implementation.
     Once `DASH-005` exists, the condition that justified the fallback ("no list page existed")
     disappears, and completing the story against its originally-preferred dependency is closing out a
     disclosed, already-flagged gap in a shipped ticket — not adding capability the Product Owner
     hasn't seen.
   - Both Sprint 11's and Sprint 14's own handoff/follow-up notes independently name this exact
     follow-up ("extend `DASH-009` to use the real list page instead of the redirect-id fallback") as
     future work once `DASH-005-GAP` closes — this sprint is that named moment, not a scope
     surprise.
   - Scope is narrow and low-risk: it touches only `services/dashboard-web/tests/e2e/
     test_core_loop.py`'s flow-3 navigation step (use `DASH-005`'s list page to find/click into the
     completed run, instead of reusing flow 2's redirect id directly) and, if flow 3's negative/edge
     case needs a matching update, `conftest.py`. It adds no new page, route, or acceptance criterion
     beyond what `DASH-009`'s backlog entry already specifies — no new template, no new router.
   - **Explicit dissent flag for the requester**: this is a defensible call, not a certainty. If the
     requester or Product Owner would rather treat any change to an already-`done`, previously-verified
     ticket as requiring its own fresh approval regardless of how it's framed, the correct action is to
     pull this second item out of this sprint and re-file it as a distinct, PO-approved follow-up
     ticket before scheduling it. I am proceeding with it in-scope here because it is bounded, was
     already twice-flagged in writing by prior sprints, and changes no externally-visible behavior or
     contract — but flagging the reasoning explicitly rather than silently bundling it.

## Sequencing decision (stated explicitly, dependency-first)

Strictly sequential, not parallel — `DASH-009`'s update cannot be built or verified before `DASH-005`'s
real list page exists to navigate.

1. `DASH-005` — build and verify first. Its own dependency (`GET /runs` via `GW-016`) is already live;
   nothing in this sprint blocks it from starting immediately.
2. `DASH-009` (flow-3 update) — runs second, strictly after `DASH-005` is verified working, since its
   own test needs a real, rendered list page to navigate through rather than the redirect-id fallback.

No Must-priority story is reordered around a lower-priority one here: `DASH-005` is Must and runs
first; the `DASH-009` update (Should, in its original backlog entry) runs second purely because it is
dependent on `DASH-005`'s output, not because of a priority judgment.

## Stories explicitly deferred

- None from this sprint's own two-item scope. Stories not reconsidered here, carried forward from
  their own backlogs' existing decisions:
  - `GW-017` (Locust load-test suite, `gateway-api` backlog) — remains deferred per Sprint 11's own
    scheduling decision; unrelated to this sprint's goal.
  - `RS-006`, `RS-008`, `RS-009` (`reporting-service` backlog, still `todo` per Sprint 14's own
    checks) — not this sprint's scope, no dependency relationship to `DASH-005`.
  - Any new `dashboard-web` scope beyond `DASH-005` and `DASH-009`'s narrow flow-3 update (e.g. any
    reporting-service report-viewer integration, DASH-101) — not proposed by the Product Owner, not
    reconsidered here.

## Definition of done for this sprint

- Every acceptance-criteria checkbox in `DASH-005`'s backlog entry is checked, not left implicitly
  assumed satisfied — including "no client-side substitute" and "most-recent-first, linking to
  `DASH-004`."
- `DASH-005`'s implementation is verified against the real `RunListResponse`/`RunSummaryResponse`
  envelope (not a mock guessed independently of `gateway-api`'s actual Contract section) — ideally
  proven with at least one test against the real running `gateway-api` + `validation-service` stack,
  or, at minimum, a mock built directly from the documented envelope shape with a code comment citing
  `services/gateway-api/README.md`'s Contract section.
- `services/dashboard-web/README.md`'s status line and Known-gaps note about `DASH-005` being
  deferred is updated to reflect it as built, no longer listed as a known gap.
- `docs/product/backlog-dashboard-web.md`'s `DASH-005` entry status is updated from blocked to done.
- `DASH-009`'s flow-3 test is updated to navigate via `DASH-005`'s real list page; its own disclosed
  fallback note (redirect-id navigation) is either removed or explicitly marked historical in the
  ticket's Outcome section, not left implying the fallback is still the live mechanism.
- `uv run pytest` (default unit loop) and `uv run pytest -m e2e` both re-run with zero regressions
  after both changes — not merely trusted from a dev agent's own report.
- No language anywhere in the new list page or its README updates implies price prediction or a
  trading signal (CLAUDE.md positioning constraint) — validation/audit framing only, checked directly.
- `docs/tickets/README.md`'s `services/dashboard-web (DASH-*)` section is updated: `DASH-005` moves to
  done, and `DASH-009`'s entry notes this sprint's flow-3 update in its own Outcome section (append,
  don't silently overwrite the Sprint 11 history).

## Handoff to Tech Lead

- **Sprint file**: `docs/sprints/sprint-15.md`
- **Sprint goal**: a tenant can open a runs-list page in `services/dashboard-web`, backed by the real
  tenant-scoped `GET /runs` proxy route, listing runs newest-first and linking into `DASH-004`'s detail
  page — closing the one gap left open from Sprint 11's PoC.
- **Ordered story list**:
  1. `DASH-005` — runs list view. Depends on `DASH-005-GAP` (closed, Sprint 14: `VS-022` +
     `GW-016`, both done and re-verified — `87`/`72` tests passing against real Postgres/Redis). No
     remaining blocker; safe to start immediately.
  2. `DASH-009` (flow-3 update, same story ID) — extends the existing Selenium E2E suite's "view a
     completed run" flow to navigate via `DASH-005`'s real list page instead of its Sprint 11 fallback
     (redirect-id navigation from `DASH-006`'s submit flow). Strictly sequenced after `DASH-005`
     because it needs the real page to exist and be working before its own test can be rewritten
     against it.
- **Dependency/risk notes**:
  - `DASH-005`'s implementation must be built against the **real** `GET /runs` response envelope:
    `RunListResponse` = `{items: list[RunSummaryResponse], limit: int, offset: int, total: int}`,
    `RunSummaryResponse` = `{id, dataset_id, horizon, status, created_at, completed_at}` (from
    `naive_first_common.contracts`, per `services/gateway-api/README.md`'s Contract section, `GW-016`
    entry). Do not let the implementation guess a different envelope shape from the original
    `DASH-005-GAP` write-up, which predates the real implementation.
  - `limit`/`offset` are forwarded by `gateway-api` to `validation-service` **unmodified** — an
    out-of-range value's `422` is `validation-service`'s own response, passed through as-is. If
    `DASH-005` adds any pagination controls (e.g. "next page" links), they should respect this
    upstream constraint (max `limit` of 100 per `VS-022`) rather than silently clamping or hiding it.
  - The backlog's own `DASH-005` acceptance criteria explicitly forbid any client-side substitute
    (local record-keeping, scraping) — that constraint no longer needs a workaround now that the real
    endpoint exists, so there's no reason for the implementation to reach for one; flag it in review if
    one appears anyway.
  - `DASH-009`'s flow-3 update is scoped narrowly (this sprint's own reasoning above) — it should not
    grow into new page/route work. If, once started, it turns out the real list page's DOM structure
    makes flow-3's navigation meaningfully harder than expected (e.g. requires new selectors/waits),
    that's still in scope; if it surfaces a need for new `dashboard-web` capability beyond what
    `DASH-005`/`DASH-009`'s existing acceptance criteria already specify, stop and flag it back rather
    than silently expanding scope.
  - This is the second-to-last disclosed capability gap on the `dashboard-web` side (after Sprint 14
    closed `DASH-005-GAP` at the `validation-service`/`gateway-api` level); once this sprint closes, the
    original Sprint 11 PoC scope (login, run detail, submit-a-run, runs list, E2E coverage of all of
    it) is fully complete with no more disclosed gaps in this service.
