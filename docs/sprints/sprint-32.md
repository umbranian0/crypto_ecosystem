# Sprint 32 — Tenant management UI (Epic B) and remaining Monitoring gaps (Epic C)

Sprint goal: an operator can create, list, and revoke tenants entirely through `dashboard-web`'s
Settings area (no `docker compose exec` script step), and the Monitoring page gains recent-error
visibility and basic run-throughput signal on top of the per-service health view that already exists.

Backlog source: `docs/product/backlog-first-run-setup-and-ops.md` — Epic B (`SETUP-011`, `SETUP-012`,
`SETUP-015`) and Epic C (`SETUP-020`, `SETUP-021`, `SETUP-022`).

## Finding: SETUP-020 is already fully satisfied — not build scope this sprint

`SETUP-020`'s backlog entry shows all four acceptance-criteria boxes unchecked, but that reflects the
backlog file being stale, not missing functionality. A prior sprint (Sprint 18, sequenced from a
sibling backlog) built the exact scope `SETUP-020` describes as three explicitly-disclosed minimal
slices: `GW-022` ("Aggregate `GET /system/health` (slice of sibling backlog's SETUP-020)"), `DASH-113`
("Minimal `/monitoring` page + operator-session gate (slice of SETUP-012/020)"), and `DASH-109`
("Monitoring: ingestion-service 4th health row"). All three are marked `done` in
`docs/tickets/README.md`. I read the actual current source, not just the ticket titles, to verify:

- **AC1** ("`gateway-api` exposes an aggregate endpoint... proxies... `validation-service`'s and
  `reporting-service`'s existing `/health`"): confirmed in
  `services/gateway-api/src/app/routers/system.py` — `GET /system/health` checks its own DB, plus
  proxies `validation-service`/`reporting-service`/`ingestion-service` (a superset of the AC's named
  two, harmless), each via `GW-009`'s existing `_call_downstream` transport-error handling per the
  ticket's own DRY note — no new transport-error pattern invented.
- **AC2** ("`/monitoring` page renders one row per service... reusing the existing 502/504-to-
  `error.html` convention... for the case where the aggregate call itself fails entirely"): confirmed
  in `services/dashboard-web/src/app/routers/operator.py`'s `monitoring()` — it calls `_call_downstream`
  against `/system/health` and returns `_render_error_for_status(request, transport_status)` on a
  transport failure, exactly the AC's stated fallback path. `monitoring.html` renders one `<tr>` per
  key in the generic `{% for name, status in services.items() %}` loop (confirmed by reading the
  template directly).
- **AC3** ("reuses `OPS-005`'s existing real dependency-connectivity checks... rather than
  re-implementing a second shallow probe"): confirmed — `_own_health_status`/`_downstream_health_status`
  in `system.py` call each service's existing `/health` endpoint rather than a new probe; those
  endpoints are the ones `OPS-005` already built out with real Postgres/Redis connectivity checks.
- **AC4** ("a test mocks... all-healthy / one-degraded / unreachable-transport cases"): confirmed
  present in `services/dashboard-web/tests/test_monitoring.py` and `services/gateway-api`'s `GW-022`
  test coverage per that ticket file's own Test acceptance criteria.

**Conclusion: SETUP-020's stated acceptance criteria are fully satisfied by GW-022 + DASH-113 +
DASH-109 combined, verified against real source, not just ticket titles.** This sprint marks
`SETUP-020` done in `docs/product/backlog-first-run-setup-and-ops.md` (cross-referencing `GW-022`/
`DASH-113`/`DASH-109` as the tickets that closed it) and does not schedule any build work for it. This
also resolves `SETUP-022`'s stated dependency on `SETUP-020` — that dependency is satisfied, not
blocking.

## Stories in scope, in execution order

1. **SETUP-011** — `gateway-api`: `GET /tenants` / `POST /tenants` / revoke endpoints, operator-auth
   gated. No dependency on anything in this sprint (its named dependency, `SETUP-010`, shipped in
   Sprint 29). Sequenced first: `SETUP-012` cannot be built or meaningfully tested against a real
   backend without it.
2. **SETUP-012** — `dashboard-web`: Settings → Tenants page. Depends on `SETUP-011` (calls its
   endpoints). Sequenced second, directly after.
3. **SETUP-015** — `dashboard-web`: read-only Environment panel. No dependency on `SETUP-011`/`012` or
   anything else in this sprint. Parallel-eligible with the `SETUP-011`→`012` chain (different Settings
   sub-page; see file-overlap note below on the one shared file to watch).
4. **SETUP-021** — Recent-errors visibility (ring buffer). Depends on `SETUP-010` (done, Sprint 29) and
   `OPS-006` (done). No dependency on `SETUP-011`/`012`/`015` or on `SETUP-020` (confirmed done above).
   Parallel-eligible with the whole Epic B chain — touches each service's logging setup plus a new
   `/diagnostics/recent-errors` endpoint and a `/monitoring` page addition, not Settings.
5. **SETUP-022** — Run throughput/failure rate on `/monitoring`. Depends on `SETUP-020`, now confirmed
   satisfied (see finding above) — this dependency is not a blocker. Sequenced last only because it's
   the remaining, lowest-risk story with no other dependency and because it shares `/monitoring`'s
   template with `SETUP-021`'s addition (see file-overlap note): land `SETUP-021`'s panel first, then
   `SETUP-022`'s, to avoid both touching `monitoring.html` at once.

## Stories explicitly deferred

- **SETUP-020** — not deferred for capacity/priority reasons; confirmed already fully done (see
  finding above). Marked done this sprint, not carried as open scope.
- **SETUP-013, SETUP-014, SETUP-023** — `Won't, this backlog`, per the backlog's own prior decision;
  not reopened here.
- **SETUP-031, SETUP-032, SETUP-033** (Epic D remainder — portability audit, fresh-machine dry run, CI
  smoke test) — not pulled into this sprint. No team size/velocity figure has been given for this
  planning pass; rather than guess a story-point capacity, this plan takes Epic B (the tenant-management
  UI, the task's most concretely named remaining gap) plus Epic C's two genuinely-open stories as the
  minimum coherent, dependency-correct slice, and stops there. If the requester confirms capacity
  supports more, Epic D has no dependency on anything in this sprint and could run in parallel.

## Dependency/sequencing note (module boundaries, implementation-plan.md sections 2 and 6)

All five in-scope stories are within already-fired triggers: `gateway-api` (#5) and `dashboard-web`
(#8) are both live and own every file these stories touch. No `libs/naive_first_engine` change is in
scope. `SETUP-011`'s three endpoints must call the same shared `provision()`/`revoke()` functions
`provision_tenant.py`/`revoke_api_key.py`/`SETUP-002` already use — one function per action, three
callers (CLI, setup wizard, this endpoint), never a duplicate code path, per implementation-plan.md
section 9's DRY rule. `SETUP-021`'s ring buffer is one additional `logging.Handler` per service reusing
`OPS-006`'s existing JSON formatter/correlation-id convention — not a second logging system. `SETUP-022`
reuses `validation-service`'s/`gateway-api`'s existing `GET /runs` endpoint and `status` field, extended
minimally if needed, not a new parallel endpoint. No service imports another service's code; all
cross-service calls stay HTTP-only, matching the pattern `GW-022`'s own design already established for
this same epic.

## File-overlap / concurrent-work risk

- `services/gateway-api/src/app/main.py` — `SETUP-011`'s new `/tenants` router registration is the only
  in-scope change here this sprint; low risk on its own, but confirm current committed state before
  starting (this file has been a repeated multi-ticket collision point in prior sprints, e.g. Sprint 29's
  own note on `SETUP-001`/`002`/`010`).
- `services/gateway-api/README.md` — `SETUP-011` adds its own Routes section entry; low risk, single
  story touching it this sprint.
- `services/dashboard-web/src/app/templates/settings.html` (or equivalent Settings shell/nav, whatever
  the current committed template structure is) — likely touched by both `SETUP-012` (Tenants page nav
  entry) and `SETUP-015` (Environment panel nav entry) if either adds a shared Settings-area navigation
  element. Confirm actual current file structure before assigning both stories to run fully in
  parallel; if they share one nav partial, sequence the nav-edit half or assign to one implementer.
- `services/dashboard-web/src/app/templates/monitoring.html` and
  `services/dashboard-web/src/app/routers/operator.py` (the file housing the `monitoring()` route,
  confirmed above) — touched by both `SETUP-021` (recent-errors panel) and `SETUP-022`
  (throughput/failure-rate panel). This file already carries several prior sprints' additions (crawl
  status panel, report-generation form) — land `SETUP-021` first, confirm it merges cleanly, then start
  `SETUP-022` against the post-`SETUP-021` state, rather than parallelizing both against the same
  template.
- `services/dashboard-web/src/app/dependencies/downstream.py` — houses `OptionalDownstreamHeadersDep`/
  `DownstreamHeadersDep`, used by the existing `/monitoring` route and likely reused (not duplicated)
  by `SETUP-021`/`SETUP-022`'s own auth needs. Read this file's current state before either story
  invents a second dependency doing the same thing.
- `docs/product/backlog-first-run-setup-and-ops.md` — this sprint's own doc-update work (marking
  `SETUP-011/012/015/020/021/022` done or updated) should land as each story's own ticket closes, not
  as one big end-of-sprint edit competing with itself across five tickets.
- No ticket this sprint touches `libs/naive_first_engine`, `services/ingestion-service`,
  `services/reporting-service`, or `services/validation-service`'s dataset/split logic — confirm via
  `git status` scoped to those paths before and after, same discipline prior sprints have held to.
  (`SETUP-022` may touch `validation-service`'s `GET /runs` endpoint only if a summary parameter needs
  adding — confirm at implementation time whether the existing endpoint already answers "count by
  status" cheaply enough to avoid this.)

## Definition of done for this sprint

- `SETUP-011`: `GET /tenants` (never returns `key_hash`/raw keys), `POST /tenants` (via shared
  `provision()`), and the revoke endpoint (via shared `revoke()`) all operator-auth gated; CLI scripts
  kept, documented as "two front doors to the same function"; tests cover list/create/revoke plus the
  already-revoked-is-a-no-op guarantee.
- `SETUP-012`: `/settings/tenants` requires the operator credential, not a tenant session; lists
  tenants/keys as metadata only; "create tenant" reuses `SETUP-003`'s one-time-reveal
  component/partial (not a second near-identical page); "revoke" re-renders without a manual refresh;
  no trading/prediction-implying copy.
- `SETUP-015`: shows only non-secret connectivity facts, explicitly labeled read-only with the
  restart-to-change instruction; no `DATABASE_URL`/password/API-key/`OPERATOR_TOKEN` value ever sent to
  the template; structurally no POST/edit route exists.
- `SETUP-020`: marked done in the backlog file this sprint, cross-referencing `GW-022`/`DASH-113`/
  `DASH-109` as the tickets that closed it — no code change.
- `SETUP-021`: each service adds an in-process ring-buffer log handler (last 50 `WARNING`+ records,
  reusing `OPS-006`'s formatter); a new operator-authenticated `/diagnostics/recent-errors` endpoint per
  service returns the buffer without ever including a raw traceback/body/secret; `/monitoring` renders
  these per service, most-recent first; explicitly no cross-restart persistence and no cross-service
  search UI, stated as disclosed limitations, not silently missing.
- `SETUP-022`: `/monitoring` shows total runs/% failed/% completed/% running over a recent window,
  labeled explicitly "validation-run throughput" — never "model performance" or anything implying a
  trading/prediction signal; reuses the existing `GET /runs` endpoint/`status` field, extended minimally
  only if genuinely needed; no alerting/threshold behavior added.
- Positioning/banned-word discipline held across every story (CLAUDE.md) — explicit check on
  `SETUP-012`'s and `SETUP-022`'s copy in particular, since both are new user-facing text.
- `services/gateway-api/README.md` and `services/dashboard-web/README.md` updated for each story's new
  behavior/contract as part of the same ticket that ships it, not a separate pass.
- Full `services/gateway-api` and `services/dashboard-web` test suites re-run with zero regressions;
  `libs/common`/`libs/naive_first_engine` confirmed untouched and not re-run if genuinely out of scope.
- `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-011/012/015/020/021/022` entries marked
  done with acceptance-criteria boxes checked (`SETUP-020` marked done via the reconciliation above,
  not new code); `SETUP-031/032/033` left unchanged, noted here as "next" for the Epic D sprint that
  follows.
- QA gate run (`qa` subagent / `/qa-validation`) after all tickets are implementation-complete, before
  production sign-off, per this platform's standing process.
