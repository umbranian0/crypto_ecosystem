# Sprint 14 — Close `DASH-005-GAP` and `RS-GAP`: `validation-service` runs-list endpoint, and `gateway-api`/`infra` reachability for `reporting-service`

Sprint goal: `dashboard-web`'s `DASH-005` and `reporting-service`'s end-to-end reachability both become
unblockable by a future sprint — `validation-service` gains a real tenant-scoped `GET /runs` list
endpoint proxied through `gateway-api`, and `reporting-service` becomes a real, running container
reachable through `gateway-api`'s public surface — closing both disclosed capability gaps
(`DASH-005-GAP`, `RS-GAP`) at the ticket level. (Neither `DASH-005` itself nor any new
`reporting-service` client integration is built this sprint — see Definition of Done.)

Backlog source: `docs/product/backlog-validation-service.md` (`VS-022`), `docs/product/backlog-gateway-api.md`
(`GW-016`, `GW-018`), `docs/product/backlog-infra.md` (`INF-018`).

## Pre-planning checks performed (stated explicitly, not assumed)

- `docs/sprints/` directory listing confirms files through `sprint-13.md` only; no `sprint-14.md`
  exists yet. `sprint-13.md` (`economic-service`) has a completed Outcome section (all 6 stories done,
  full verification writeup) — genuinely closed. `sprint-12.md` (`reporting-service`) does **not**
  have a completed Outcome section (its own text reads "Tech Lead fills in after verification — see
  this sprint's own final report"), but `docs/tickets/README.md`'s `services/reporting-service (RS-*)`
  table shows `RS-001`, `RS-002`, `RS-003`, `RS-004`, `RS-005`, `RS-007` already `done`, and only
  `RS-006`, `RS-008`, `RS-009` still `todo` — checked directly, not assumed from either file's prose
  alone. This sprint is therefore correctly **Sprint 14**, sequenced after both, and does not wait on
  Sprint 12's remaining three tickets (see the `GW-018` readiness note below for why that's safe).
- Each of the four tickets' own `Depends on:` line and acceptance-criteria/file-list read directly from
  its source backlog file this session — not inferred from priority, ticket number, or this task's own
  framing.
- `docs/sprints/sprint-11.md` read in full: confirms `DASH-005` is deferred, blocked specifically on
  `VS-0NN`/`GW-016` not existing yet in their own backlogs at that time. Those tickets now exist as
  `VS-022`/`GW-016`, approved and in scope of this backlog read — this sprint is the first opportunity
  to schedule them.
- `docs/product/backlog-reporting-service.md`'s `RS-GAP` entry read directly: confirms the gap is
  explicitly two-sided (`gateway-api` proxy routes + `infra` Compose wiring), explicitly not
  `reporting-service`'s own story to resolve, and explicitly names the same two follow-up tickets
  (`GW-0NN`, `INF-0NN`) this sprint now schedules as `GW-018`/`INF-018`.
- `docs/implementation-plan.md` sections 2 and 6 read directly: `services/gateway-api` "routes to all
  other services over HTTP" (section 2) and its trigger (#5) already fired (Sprint 05); none of this
  sprint's four stories require scaffolding a new module or crossing an unfired trigger — all four
  extend already-built, already-triggered services (`validation-service`, `gateway-api`, `infra`).
  No module-boundary violation: `VS-022` stays inside `validation-service`'s own schema/API surface;
  `GW-016`/`GW-018` stay inside `gateway-api`'s stated "routes to all other services" boundary with no
  business logic reimplemented; `INF-018` is packaging/wiring only, touching no `services/*/src/` code
  (explicitly forbidden by its own acceptance criteria).
- No team size/velocity given. Sized against precedent: 4 self-contained stories, two independent
  two-story chains — smaller and tighter than Sprint 05/11/12's full-service builds, closer to Sprint
  04's (4 sequential `libs/common` stories) or Sprint 09's (2 stories, one dependency pair) shape.

## `GW-018` readiness note (stated explicitly, since Sprint 12 hasn't fully closed)

`GW-018`'s own `Depends on:` line names `reporting-service`'s `RS-004`/`RS-005` "existing as real,
running routes" — not RS-006/RS-008/RS-009, and not Sprint 12's own closure as a whole. Checked
directly against `docs/tickets/README.md`: `RS-004` and `RS-005` are both `done`. `GW-018`'s own
acceptance criteria also state it "does not require RS-001 through RS-006 to be done first" for the
Compose-wiring counterpart (INF-018) and that its own tests are `httpx.MockTransport`-based, not a
real running `reporting-service` call. This sprint proceeds with `GW-018` on that basis, with one
caveat carried forward explicitly, not silently assumed away: `RS-006` (the event-driven generation
path) is still `todo`, so a full "submit a run → automatic report → retrieve through gateway-api" flow
is **not** exercisable end-to-end after this sprint — only the manual `POST /reports/generate` →
`GET /reports/{id}` flow (RS-004/RS-005, both done) is. This sprint's own end-to-end verification
(Definition of Done) is scoped to that manual flow accordingly, and this caveat should be restated to
whoever verifies `GW-018` so a missing RS-006 path isn't mistaken for a `GW-018` defect.

## Sequencing decision (stated explicitly, dependency-first)

Two independent chains exist here, confirmed by reading each story's own `Depends on:` line, not
assumed from the task framing:

1. **`VS-022 → GW-016`** (closes `DASH-005-GAP`). `GW-016`'s own line: "Depends on: VS-022 (...must
   expose the real endpoint before this proxy has anything to forward to), GW-007, GW-009" — both
   `GW-007`/`GW-009` already done (Sprint 05). `VS-022` has no dependency on anything in this sprint;
   its own line is "Depends on: VS-003, VS-004, VS-013 (all done)."
2. **`GW-018` and `INF-018`** (together close `RS-GAP`) — verified genuinely independent of each
   other, not assumed. `GW-018`'s own line names `reporting-service`'s RS-004/RS-005 (already done),
   `GW-007`, `GW-009` — it does not name `INF-018`, and its acceptance criteria explicitly state its
   own mocked-transport tests "don't strictly require" INF-018, only noting Compose wiring is wanted
   for realistic end-to-end testing. `INF-018`'s own line names `INF-001`, `INF-002`, `INF-014`,
   `reporting-service`'s `RS-001`/`RS-002` — it does not name `GW-018`. Different files entirely
   (`services/gateway-api/src/app/routers/*.py` + README vs. `infra/docker-compose.yml` +
   `services/reporting-service/Dockerfile` + `infra/README.md`) — no collision risk between this pair,
   and no ordering constraint between them either.
3. **File-collision risk within `gateway-api`, checked directly**: `GW-016` and `GW-018` both add a
   proxied route to `gateway-api`'s router layer and both document a new endpoint in
   `services/gateway-api/README.md`'s Contract section — the same shape of risk this repo flagged
   before for `VS-006`/`VS-007`/`VS-009` all touching `runs.py` in Sprint 03. Unlike `GW-016`'s two
   list-endpoint fields being additive to an existing router file, `GW-018` also needs a new
   `REPORTING_SERVICE_URL` env var and (per its own acceptance criteria) plausibly a new router module
   for `reporting-service` proxying — the two stories' router-file targets may or may not be the same
   file depending on how the Tech Lead's ticket breakdown structures `gateway-api`'s routers, and both
   definitely touch the same README section. **Decision: sequence `GW-016` and `GW-018` strictly
   sequentially, not in parallel**, even though neither formally depends on the other — mirroring
   Sprint 03's own precedent of serializing same-file-risk stories rather than trusting two concurrent
   dev agents not to collide. `GW-016` runs first (it completes the older-disclosed, longer-blocked
   gap — `DASH-005-GAP` has been open since Sprint 11; `RS-GAP` since Sprint 12), `GW-018` second.
4. **`INF-018`** has no file overlap with any other story in this sprint (`infra/` and
   `services/reporting-service/Dockerfile` only) — safe to run in parallel with `VS-022` from the very
   start of the sprint, and safe to run any time relative to `GW-016`/`GW-018` since neither depends on
   it and it depends on neither.

Net order: `VS-022` and `INF-018` in parallel (Round 1) → `GW-016` (Round 2, depends on `VS-022`) →
`GW-018` (Round 3, sequenced after `GW-016` purely for same-file collision avoidance in
`gateway-api`, not a real dependency).

No Must-priority story here is silently reordered around a lower-priority story's output — all four
stories are Must priority in their own backlogs; the only reordering applied is the file-collision
serialization of `GW-016`/`GW-018`, stated explicitly above rather than left implicit.

## Stories in scope, in execution order

1. `VS-022` [Must, `validation-service`] — Tenant-scoped `GET /runs` list endpoint (`limit`/`offset`,
   `created_at DESC`, hard-scoped via `Depends(get_tenant_context)`). Depends on `VS-003`, `VS-004`,
   `VS-013` (all done). Runs in parallel with `INF-018` — disjoint services/files.
2. `INF-018` [Must, `infra`] — `reporting-service` wired into `infra/docker-compose.yml` as a real,
   runnable, non-superuser-RLS-role container (packaging/wiring only, no `services/reporting-service/src/`
   change). Depends on `INF-001`, `INF-002`, `INF-014`, `reporting-service`'s `RS-001`/`RS-002` (all
   done). Runs in parallel with `VS-022`.
3. `GW-016` [Must, `gateway-api`] — Proxy route for `validation-service`'s new `GET /runs` list
   endpoint, reusing the `RunSummaryResponse` envelope `VS-022` adds to `naive_first_common.contracts`.
   Depends on `VS-022` (this sprint, must land first), `GW-007`, `GW-009` (both done). Runs after
   `VS-022`.
4. `GW-018` [Must, `gateway-api`] — Proxy routes for `reporting-service`'s `POST /reports/generate` /
   `GET /reports/{id}` (`RS-004`/`RS-005`, both already done). Depends on those two routes existing
   (done), `GW-007`, `GW-009` (done); practically wants `INF-018` (this sprint, for realistic
   end-to-end testing) though its own mocked-transport tests don't strictly require it. Sequenced
   after `GW-016` purely to avoid two dev agents editing `gateway-api`'s router layer and README
   Contract section concurrently — not a formal dependency on `GW-016`.

## Stories explicitly deferred

None of the four in-scope stories are deferred — all four fit this sprint's scope per the sizing
reasoning above. Stories from either source backlog **not** in this sprint (not reconsidered here,
carried forward from their own backlogs' existing decisions):
- `DASH-005` itself (`dashboard-web` backlog) — this sprint unblocks it (via `VS-022`/`GW-016`) but
  does not build it; that remains a future `dashboard-web` sprint's own story, sequenced by this
  role only once the Product Owner/Tech Lead schedule it.
- `RS-006`, `RS-008`, `RS-009` (`reporting-service` backlog, Sprint 12's still-`todo` items) — not
  reopened or absorbed into this sprint; this sprint's scope is the two disclosed gap-closure tickets
  only, not finishing Sprint 12's remaining work, which belongs to that sprint's own closure.
- `GW-017` (Locust load-test suite) — remains deferred per Sprint 11's own scheduling decision;
  unrelated to either gap this sprint closes.

## Definition of done for this sprint

- Every acceptance-criteria checkbox in `VS-022`, `GW-016`, `GW-018`, `INF-018`'s backlog entries is
  checked, not left implicitly assumed satisfied.
- `services/validation-service/README.md`'s Routes section gains `GET /runs`; `VS-016`'s doc-sync
  check (`check_doc_sync.py`) still passes after the addition, re-run directly, not assumed.
- `services/gateway-api/README.md`'s Contract section gains all three new proxied endpoints (`GET /runs`,
  `POST /reports/generate`, `GET /reports/{id}`) plus the new `REPORTING_SERVICE_URL` env var,
  cross-referencing `DASH-005`/`DASH-005-GAP` and `RS-GAP` respectively as the reason each exists.
- `infra/README.md` no longer lists `reporting-service` under "not yet wired into compose"
  (INF-007's prior statement); states this was closed as `RS-GAP`'s infra half, cross-referencing
  `GW-018` as the other half needed for actual reachability from outside the Docker network.
- Cross-tenant isolation proven the same way this repo already proves it for every prior proxy route:
  tenant A's authenticated request never sees tenant B's runs (`GW-016`) or tenant B's reports
  (`GW-018`) — non-tautological tests asserting by id/content, not merely by count or status code.
- `uv run pytest` passes with zero regressions in `validation-service` and `gateway-api`; `INF-018`'s
  acceptance is verified against the real, live Compose stack (`docker compose up reporting-service`
  succeeds, `POST /reports/generate` / `GET /reports/{id}` respond over the container's exposed port),
  not merely a config-file review.
- The `GW-018` readiness caveat above is restated in `services/gateway-api/README.md` or the ticket
  itself: the manual `POST /reports/generate` → `GET /reports/{id}` flow is reachable end-to-end
  through `gateway-api` after this sprint; the automatic `run.completed`-triggered flow (`RS-006`) is
  not, since that ticket remains `todo` in Sprint 12.
- `docs/tickets/README.md` gains this sprint's four tickets under their respective existing module
  sections (`services/validation-service (VS-*)`, `services/gateway-api (GW-*)`, `infra (INF-*)`);
  each source backlog's own story statuses are left accurate.
- **Explicitly, what this sprint does NOT do, stated so it isn't silently assumed by a future
  sprint**: it does not build `DASH-005` itself (the `dashboard-web` runs-list page), does not build
  any `dashboard-web` integration against the new `GET /runs` proxy route, and does not finish Sprint
  12's remaining `RS-006`/`RS-008`/`RS-009`. It only makes both of those future efforts unblockable —
  the actual unblocking (scheduling and building `DASH-005`, and any client using `reporting-service`
  end-to-end through `gateway-api`) is a future sprint's work.

## Handoff to Tech Lead

- **Sprint file**: `docs/sprints/sprint-14.md`
- **Sprint goal**: `validation-service` gains a real tenant-scoped `GET /runs` list endpoint proxied
  through `gateway-api` (closing `DASH-005-GAP`), and `reporting-service` becomes a real, running
  container wired into Compose and reachable through `gateway-api`'s public surface for its already-
  built manual generate/retrieve flow (closing `RS-GAP`) — making `dashboard-web`'s `DASH-005` and
  `reporting-service`'s end-to-end reachability both unblockable by a future sprint, though neither is
  itself built this sprint.
- **Ordered story list**:
  1. `VS-022` — `validation-service`, tenant-scoped `GET /runs` list endpoint. No dependency on
     anything else in this sprint. Runs in parallel with `INF-018`.
  2. `INF-018` — `infra`, `reporting-service` Compose wiring (packaging/wiring only, no
     `services/reporting-service/src/` change permitted). No dependency on anything else in this
     sprint. Runs in parallel with `VS-022`.
  3. `GW-016` — `gateway-api`, proxy route for `VS-022`'s new endpoint. Depends on `VS-022` landing
     first (real dependency, not just sequencing convenience).
  4. `GW-018` — `gateway-api`, proxy routes for `reporting-service`'s already-built `RS-004`/`RS-005`.
     No formal dependency on `GW-016`, but sequenced after it to avoid two dev agents concurrently
     editing `gateway-api`'s router layer and `README.md`'s Contract section — treat this as a firm
     "do not parallelize with `GW-016`" instruction, not a suggestion.
- **Dependency/risk notes**:
  - `GW-016` and `GW-018` both touch `services/gateway-api`'s files (router registration, likely
    `main.py`, and `README.md`'s Contract section). Do not delegate both to separate dev agents
    concurrently — same category of risk this repo flagged for `VS-006`/`VS-007`/`VS-009` all touching
    `runs.py` in Sprint 03. Run `GW-016` to completion (diff verified) before starting `GW-018`.
  - `GW-018`'s own dependency is `reporting-service`'s `RS-004`/`RS-005`, both already `done` per
    `docs/tickets/README.md` — this sprint does not need to wait on Sprint 12's still-`todo`
    `RS-006`/`RS-008`/`RS-009`. But flag explicitly to whoever verifies `GW-018`: the automatic
    `run.completed`-triggered report flow (`RS-006`) is not yet built, so only the manual
    generate/retrieve flow is exercisable end-to-end through `gateway-api` after this sprint — a gap
    in `RS-006`, not a `GW-018` defect, if a full auto-generate-then-retrieve test is attempted and
    fails.
  - `INF-018` is explicitly packaging/wiring only — its own acceptance criteria forbid touching any
    file under `services/reporting-service/src/`. If a ticket for this story starts adding
    application code, that's out of scope and should be caught in review.
  - `INF-018`'s `DATABASE_URL` for the new container must use the existing non-superuser
    `NOBYPASSRLS` application role `INF-014` already established — this story does not reintroduce
    the superuser-bypasses-RLS gap `INF-014` closed for `validation-service`/`gateway-api`. Recommend
    the same direct-`psql`-as-runtime-role verification this repo already did for `INF-014` be
    repeated for `reporting-service` once its own `RS-002` RLS policies are live.
  - `VS-022`'s hard server-side `limit` ceiling (max 100, `422` on out-of-range, not silently clamped)
    and its cross-tenant non-tautological test (asserts by id, not just count) are this story's two
    most easily under-tested acceptance criteria — worth explicit review scrutiny, same category this
    repo already applies to pagination/list-endpoint stories elsewhere.
  - This sprint closes two previously-disclosed, cross-sprint-tracked gaps
    (`DASH-005-GAP` since Sprint 11, `RS-GAP` since Sprint 12) — once both close, flag back to the
    Product Owner/PM that a future sprint can now schedule `DASH-005` itself against the real
    `GET /runs` proxy route, and that `reporting-service`'s manual flow is reachable end-to-end for
    any future client integration work.
