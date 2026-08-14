# Sprint 12 — `services/reporting-service` PoC (validation-audit HTML report generation + retrieval), explicit trigger override

Sprint goal: a `"validation_audit"` HTML report can be generated for a `validation-service` run —
either synchronously via a manual endpoint or automatically on that run's `run.completed` Redis
Streams event — and retrieved afterward through a tenant-isolated endpoint, as a real, tested,
running `services/reporting-service`, built deliberately ahead of `implementation-plan.md`'s trigger
#7 (no pilot audit has been requested) at explicit user request.

Backlog source: `docs/product/backlog-reporting-service.md` (RS-001 through RS-009, RS-101-106,
RS-GAP).

## Pre-planning checks performed (stated explicitly, not assumed)

- `docs/sprints/` currently ends at `sprint-11.md` (Sprint 11, closed, all 8 in-scope
  `dashboard-web` stories done, zero regressions per its own Outcome section: 47/47 combined unit +
  E2E). No carried-over/incomplete story exists anywhere in that file.
- Checked immediately, per this task's explicit instruction, whether `sprint-12.md` was already
  claimed by a parallel PM task (e.g. sequencing `economic-service`): confirmed **no**
  `docs/sprints/sprint-12.md` exists yet (`docs/sprints/*.md` glob returns only `sprint-01.md`
  through `sprint-11.md`). This sprint is therefore **Sprint 12**, not Sprint 13.
- `docs/product/backlog-reporting-service.md` read in full this session, including its "Explicit
  trigger override" section and its seven numbered "Explicit scope/dependency decisions."
- `docs/implementation-plan.md` section 6 (trigger table) and section 2 (module boundary map) read
  directly. Row 32: `services/reporting-service` "Owns `reporting.*` schema + report object storage
  prefix; triggered by `run.completed`." Row 123: trigger #7 condition is "as soon as a validation
  run needs to produce a client-facing artifact instead of raw JSON — i.e. right after the first
  pilot audit is requested." No pilot client or pilot audit request exists anywhere in this repo's
  docs (confirmed again this session, unchanged since Sprint 10/11's own equivalent checks). This
  sprint is a **deliberate, disclosed trigger override**, the same category already used for
  `gateway-api` (trigger #5, Sprint 05), `ingestion-service`'s connectors (trigger #6/#10, Sprint 10),
  and `dashboard-web` (trigger #8, Sprint 11) — carried forward explicitly here, not silently treated
  as normal trigger-driven sequencing. Unlike `services/economic-service`'s own pending override
  (trigger #11), this one carries no comparable ethical constraint — the backlog's own scope decision
  1 already states this is a build-order override only, so this sprint is scoped as a full
  functional build, not scaffolding-only.
- Section 7 (design patterns) confirmed directly: the Factory pattern is named explicitly for
  `reporting-service`'s report-kind selection (row 140), and Observer/pub-sub is named explicitly for
  `run.completed -> reporting-service` (row 141) — both patterns already anticipated at the
  architecture-doc level, not invented by this sprint's sequencing.
- No team size/velocity given for this sprint. Sized against the established precedent of Sprints
  06-11 (2-9 self-contained stories each). This sprint's 9 in-scope stories (RS-001 through RS-009 —
  6 Must + 3 Should) sit at the upper end of that range, closer to Sprint 06's larger-debt-sprint
  shape and Sprint 11's own 8-story `dashboard-web` shape than a small 2-4 story sprint — matching
  the pattern of "a new service built end-to-end in one sprint" already set by Sprint 05
  (`gateway-api`, trigger-#5 override) and Sprint 11 (`dashboard-web`, trigger-#8 override), not a
  small independent-item pool like Sprint 09/10. All 9 stories form one dependency chain plus a
  Should-priority tail within a single new service, the same shape as Sprint 11's own sizing
  reasoning, rather than an unrelated pool.

## RS-GAP scheduling decision (stated explicitly, mirroring Sprint 11's `DASH-005-GAP` precedent)

**Decision: RS-GAP is explicitly out of this sprint's scope**, same as `DASH-005-GAP` was excluded
from Sprint 11. This sprint does **not** touch `services/gateway-api` routing (no new proxy route for
`POST /reports/generate` or `GET /reports/{id}`) and does **not** touch `infra/docker-compose.yml`
(no service wiring for `reporting-service`).

Reasoning:
- RS-GAP's own text is explicit that the fix belongs as new tickets in
  `docs/product/backlog-gateway-api.md` (a new `GW-0NN`) and `docs/product/backlog-infra.md` (a new
  `INF-0NN`) — not authored in the reporting-service backlog, "since this module owns neither
  `gateway-api`'s routing table nor `infra/`'s compose file." The task brief confirms these two
  tickets are being separately authored into those backlogs by a parallel Product Owner task right
  now — not yet approved, and not this sprint's to schedule.
- This role's mandate is to sequence already-prioritized, already-approved stories, not invent or
  pre-approve scope for a different module's backlog. Scheduling `GW-0NN`/`INF-0NN` here — even just
  as placeholders — would mean scheduling stories the Product Owner has not yet written or approved
  for `gateway-api`/`infra`.
- This sprint's own minimum-scope requirement (backlog's requester-stated items: manual generate
  endpoint, event-driven generation, retrieval endpoint) is fully satisfiable without either gap being
  closed — RS-004/RS-005/RS-006 are directly callable (curl / a test client hitting
  `reporting-service` on its own port) even though no public-facing proxy route or Compose wiring
  exists yet, mirroring exactly how `dashboard-web`'s own Sprint 11 stories shipped and were verified
  before `DASH-005-GAP` was resolved.

**Follow-up flagged for the requester/Product Owner, not silently dropped**: once `GW-0NN`
(gateway-api proxy routes for `POST /reports/generate` / `GET /reports/{id}`) and `INF-0NN`
(`reporting-service` compose wiring) are authored and approved in their own backlogs, a future sprint
should schedule `INF-0NN -> GW-0NN` (or the reverse, whichever the Product Owner's own dependency
statement says) so this service becomes reachable end-to-end through the platform's one public-facing
surface. Until then, `reporting-service` is built and tested as a standalone service, not yet wired
into the platform's request path — the same disclosed, non-blocking gap `dashboard-web` carried after
Sprint 11.

## Sequencing decision (stated explicitly, dependency-first, verified against each story's own `Depends on:` line)

All in-scope stories are Must or Should priority; none is silently reordered ahead of a
higher-priority item it doesn't depend on. The chain is dictated by the backlog's own stated
dependencies and file lists, not by priority alone:

1. `RS-001` — no dependency; scaffolding (`pyproject.toml`, `src/app/{routers,dependencies,
   repositories,renderers,templates}` skeleton, `Dockerfile`, README) everything else needs.
2. `RS-002` and `RS-003` — **verified genuinely parallel-safe**, not assumed. `RS-002`'s own
   "Depends on:" line is `RS-001` only, and its file list is entirely `src/app/repositories/`,
   `src/app/models.py`, and the Alembic `migrations/` tree. `RS-003`'s own "Depends on:" line is also
   `RS-001` only, and its file list is entirely `src/app/renderers/` and `src/app/templates/`. No
   file overlap, no acceptance criterion in either story references the other's output (RS-003's
   renderer interface takes `RunDetailResponse`/`SplitResultResponse` from `libs/common`'s existing
   contracts, not from RS-002's repository layer). Scheduled as one parallel round once `RS-001`
   lands, matching this sprint's own equivalent of Sprint 10's "verified independent, not assumed"
   standard.
3. `RS-004` — depends on `RS-002` (repository, to persist) and `RS-003` (Factory, to render), per its
   own stated `Depends on: RS-002, RS-003`. Runs after both land.
4. `RS-005` — its own stated `Depends on:` line is `RS-002` only (repository read path); it does not
   reference `RS-003` or `RS-004`. **Verified parallel-safe with `RS-004`**: `RS-005` is a pure
   retrieval endpoint (`GET /reports/{id}` reading an existing `reports` row) with no file overlap
   against `RS-004`'s generation endpoint beyond the shared `RS-002` repository interface, which is
   already frozen by the time both start. Scheduled alongside `RS-004`, not strictly after it,
   correcting a naive "priority-order-only" reading that would have placed it after `RS-004` for no
   dependency reason.
5. `RS-006` — depends on `RS-002`, `RS-003`, and explicitly `RS-004` per its own stated
   `Depends on: RS-002, RS-003, RS-004 (shares its generation code path)` — this is a real code-reuse
   dependency (DRY within the module boundary), not just a priority ordering, so `RS-006` runs strictly
   after `RS-004`, not in parallel with it.
6. `RS-007` — Should, depends on `RS-002` only (health check against the `reporting` schema). Its own
   dependency is already satisfied once step 2 lands; scheduled in the sprint's tail alongside
   `RS-008`/`RS-009` rather than gating anything ahead of it, since it is Should-priority and adds no
   capability the Must stories rely on.
7. `RS-008` — Should, depends on `RS-004`, `RS-005` per its own stated line ("routes must exist
   first") — runs after both.
8. `RS-009` — Should, depends on `RS-001` through `RS-006` per its own stated line ("test suite must
   exist") — runs last, once every story with its own test suite exists.

No Must-priority story is blocked on a Could/Should-priority story's output in this backlog (this
backlog has no Could items, and no Should item is a dependency of a Must item) — the priority order
and the dependency order agree throughout, so no explicit priority-vs-dependency conflict exists to
call out beyond the RS-004/RS-005 parallel-safety correction above.

## Stories in scope, in execution order

1. `RS-001` [Must] — Service scaffolding. No dependency; nothing else can be built without it.
2. `RS-002` [Must] — `reporting.reports` Postgres schema + Repository pattern with RLS. Depends on
   `RS-001`. Runs in parallel with `RS-003` (disjoint files, verified above).
3. `RS-003` [Must] — Report Factory + `ValidationAuditRenderer`. Depends on `RS-001`. Runs in
   parallel with `RS-002` (disjoint files, verified above).
4. `RS-004` [Must] — Manual `POST /reports/generate` endpoint. Depends on `RS-002`, `RS-003`. Runs
   in parallel with `RS-005`.
5. `RS-005` [Must] — `GET /reports/{id}` retrieval endpoint. Depends on `RS-002` only (verified). Runs
   in parallel with `RS-004`.
6. `RS-006` [Must] — Redis Streams subscriber for `run.completed`. Depends on `RS-002`, `RS-003`,
   `RS-004` (shares its generation code path — a real DRY dependency, not priority ordering). Runs
   strictly after `RS-004`.
7. `RS-007` [Should] — `GET /health` endpoint. Depends on `RS-002`. Scheduled in the tail; its own
   dependency is satisfied well before this point.
8. `RS-008` [Should] — OpenAPI/README doc-sync check. Depends on `RS-004`, `RS-005`.
9. `RS-009` [Should] — CI wiring (`ci.yml` + README Coverage/Dependency-upgrades pointers). Depends
   on `RS-001` through `RS-006`. Runs last.

## Stories explicitly deferred

- `RS-101` through `RS-106` (Won't, this backlog) — not proposed by the Product Owner; not
  reconsidered here (`dashboard-web` report-viewer UI, automatic distribution, PDF export, real
  object storage/MinIO, a second report kind, and `gateway-api` proxy routes are each correctly out
  of scope per the backlog's own reasoning, tied to an unfired trigger, a deliberate scope decision,
  or another module's ownership boundary).
- `RS-GAP` (not a reporting-service story) — flagged for the Product Owner's two parallel-in-progress
  tickets (`GW-0NN` in `backlog-gateway-api.md`, `INF-0NN` in `backlog-infra.md`) to resolve; not
  scheduled here since `reporting-service` owns neither `gateway-api`'s routing table nor `infra/`'s
  compose file. See "RS-GAP scheduling decision" above for full reasoning.

No story in this backlog is deferred purely on priority grounds — all 9 Must/Should stories fit
within this sprint's scope per the sizing reasoning above; none was cut for capacity reasons.

## Definition of done for this sprint

- Every acceptance-criteria checkbox in `RS-001` through `RS-009`'s backlog entries is checked, not
  left implicitly assumed satisfied.
- `services/reporting-service/README.md`'s status line reflects the real built state (planned ->
  implemented), states the trigger-#7 override explicitly (no pilot audit request exists), and
  documents that `reporting-service` is not yet reachable through `gateway-api` and not yet wired
  into `infra/docker-compose.yml`, pointing at RS-GAP and its two pending, separately-authored
  follow-up tickets.
- `uv run pytest` passes with zero failures for `RS-001` through `RS-009`'s own test coverage,
  including RS-002's non-vacuous RLS cross-tenant proof (run as a non-superuser role) and RS-006's
  real-Redis integration test (skip-guarded if Redis is unreachable, matching VS-014's precedent).
- No language anywhere in `reporting-service`'s templates/README implies price prediction or a
  trading signal (`CLAUDE.md` positioning constraint); the mandatory statistical-accuracy-vs-
  economic-value disclaimer (RS-003's own acceptance criterion) is present in every rendered report,
  and a "did not beat naive" outcome renders plainly, with no softening or omission.
- No DM statistic, p-value, or verdict is recomputed or reinterpreted by the renderer — RS-003's
  verbatim-passthrough acceptance criterion verified against the real diff, not just the tests.
- `docs/tickets/README.md` gains a new `services/reporting-service (RS-*)` section for this sprint's
  nine tickets, and `docs/product/backlog-reporting-service.md`'s own story statuses are left
  accurate.
- `.github/workflows/ci.yml` runs `reporting-service`'s suite alongside the existing five modules
  (RS-009), with zero regressions in any other module's suite.

## Handoff to Tech Lead

- **Sprint file**: `docs/sprints/sprint-12.md`
- **Sprint goal**: a `"validation_audit"` HTML report can be generated for a `validation-service` run
  — either synchronously via a manual endpoint or automatically on that run's `run.completed` Redis
  Streams event — and retrieved afterward through a tenant-isolated endpoint, as a real, tested,
  running `services/reporting-service`, built deliberately ahead of trigger #7 (no pilot audit
  request exists) at explicit user request.
- **Ordered story list**:
  1. `RS-001` — service scaffolding, no dependency.
  2. `RS-002` — `reporting.reports` schema + Repository + RLS. Depends on `RS-001`. Parallel-safe
     with `RS-003` (disjoint files: `repositories/`, `models.py`, `migrations/` vs. `renderers/`,
     `templates/`) — safe to delegate to two dev agents concurrently if useful.
  3. `RS-003` — Report Factory + `ValidationAuditRenderer`. Depends on `RS-001`. Parallel-safe with
     `RS-002`, as above.
  4. `RS-004` — manual `POST /reports/generate`. Depends on `RS-002` **and** `RS-003` — do not start
     until both land.
  5. `RS-005` — `GET /reports/{id}`. Depends on `RS-002` only — parallel-safe with `RS-004`, since it
     shares no file with `RS-004` beyond the already-frozen `RS-002` repository interface.
  6. `RS-006` — Redis Streams subscriber for `run.completed`. Depends on `RS-002`, `RS-003`, **and**
     `RS-004` specifically — the backlog requires it to reuse `RS-004`'s generation code path (no
     duplicated logic between the manual and event-triggered paths). Do not let this story hand-roll
     its own copy of the fetch-render-persist sequence; it must call the same internal function
     `RS-004`'s route handler calls.
  7. `RS-007` — `GET /health`. Depends on `RS-002` only; low-risk, schedulable any time after step 2.
  8. `RS-008` — doc-sync check. Depends on `RS-004`, `RS-005` (routes must exist to introspect).
  9. `RS-009` — CI wiring. Depends on `RS-001` through `RS-006` (test suite must exist); runs last.
- **Dependency/risk notes**:
  - This entire sprint is a disclosed trigger-#7 override (no pilot audit request exists) — carry
    that framing into `services/reporting-service/README.md`'s status line, the same way
    `gateway-api`'s and `dashboard-web`'s READMEs disclose their own trigger overrides.
  - **RS-GAP is explicitly out of this sprint.** Do not add any `gateway-api` proxy route and do not
    touch `infra/docker-compose.yml` for this service. Two follow-up tickets (`GW-0NN`, `INF-0NN`)
    are being authored separately in their own backlogs by a parallel Product Owner task right now —
    not yet approved, and not this sprint's to build toward or work around. `reporting-service` is
    verified standalone this sprint (direct port access / test client), the same way `dashboard-web`
    shipped in Sprint 11 before its own analogous gap was closed.
  - RS-002's RLS proof must be run as a genuine non-superuser role (the `naive_first_app` role INF-014
    already established) — a `BYPASSRLS` or superuser test would pass vacuously and must be rejected
    on review, per VS-013/GW-012's exact precedent already proven in this repo.
  - RS-003's renderer is the story most tied to this platform's core, non-negotiable positioning
    (`CLAUDE.md`): DM verdicts must pass through verbatim (the Harvey et al. 1997 long-run variance
    correction already applied upstream in `naive_first_engine`, per NFE-012), a "did not beat naive"
    outcome must render plainly with no softening, and the statistical-accuracy-vs-economic-value
    disclaimer must be present in every report. Recommend the same extra-scrutiny review treatment
    this repo gave `GW-006`/`GW-007` (Sprint 05) and `DASH-002` (Sprint 11) for security-sensitive
    stories — this is this sprint's equivalent for positioning-sensitive content.
  - RS-002 and RS-003 are genuinely parallel-safe (verified against each story's own `Depends on:`
    line and file list, not assumed from the backlog's general framing) — safe to delegate
    concurrently if that's useful for throughput, but RS-004 must not start until both are actually
    done, not just started.
  - RS-006 must reuse RS-004's own internal generation function, not a duplicate implementation — this
    is a backlog-stated DRY requirement (implementation-plan.md section 9), not a suggestion; flag it
    in code review if a second copy of the fetch-validation-service -> render -> persist sequence
    appears anywhere in RS-006's diff.
  - RS-002's Postgres-only decision (no SQLite backend, unlike `validation-service`/`gateway-api`'s
    original build order) means RS-002's tests need real Postgres reachable (skip-guarded if not) from
    the start — flag this to whichever dev agent picks up RS-002 so they don't attempt a throwaway
    SQLite implementation that isn't actually requested.
  - Once `GW-0NN`/`INF-0NN` are approved in their own backlogs (a follow-up outside this sprint), a
    future sprint should schedule them so this service becomes reachable end-to-end through
    `gateway-api` — flagged for the Product Owner/PM, not silently dropped.
