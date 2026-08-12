# Sprint 08 — Operability: CI pipeline, coverage, dependency cadence, health-check depth

Sprint goal: Every one of the platform's five shipped modules runs its own test suite (including `naive_first_engine`'s NFE-015/016 regression gate and NFE-018 doc-sync check) automatically on every push instead of only when a human happens to run it by hand, with a coverage number attached, a documented dependency-upgrade cadence on top of it, and both FastAPI services' `/health` endpoints reporting real database connectivity instead of a hardcoded constant.

Backlog source: `docs/product/backlog-operability.md` — OPS-001, OPS-002, OPS-003, OPS-005.

## Pre-planning checks performed (stated explicitly, not assumed)

- **Sprint 07 status**: read `docs/sprints/sprint-07.md` and all three of its tickets (`docs/tickets/INF-014.md`, `INF-015.md`, `INF-016.md`) directly. All three are still `Status: todo` with empty `## Outcome` sections — Sprint 07 is **in flight, not complete**. Confirmed independently by directory/file state: `infra/postgres-init/02-create-app-role.sh` exists (untracked) but INF-014's own Implementation AC requires the same grants to also be applied directly against the *live* running Postgres container (not just the fresh-volume init script) — unconfirmed done. `infra/migrate.sh`/`.ps1` (INF-016) and `infra/bootstrap.sh`/`.ps1` (INF-015) do not exist on disk yet. Sprint 08 is planned to not conflict with or duplicate this in-flight work — see the OPS-004 deferral below for the one place a real coupling was found.
- **Backlog status re-check**: read `docs/product/backlog-libs-common.md`, `docs/product/backlog-gateway-api.md`, `docs/product/backlog-validation-service.md`, `docs/product/backlog-infra.md`, and `docs/product/backlog-technical-upgrades.md` in full rather than trusting the requester's list at face value. One correction found: **GW-012 is already done** (shipped in Sprint 06, per `docs/tickets/README.md`'s gateway-api section) — it was not in the requester's "still open" list and is not re-proposed here. Everything else in the requester's older-pool list (`LC-005`, `GW-010/011/013/014`, `VS-016/017`, `INF-008/009/010`, `ARCH-005/007/008`) is confirmed still open (Should/Could/tracking, none marked done).
- **`infra/docker-compose.yml` read directly** (not assumed from the backlog's prose): it already declares `healthcheck` blocks for `postgres`/`redis` and `depends_on: condition: service_healthy` for both app services — this looks like it substantially satisfies `INF-009`'s stated acceptance criteria already, evidently added as a byproduct of Sprint 07's in-flight bootstrap-script work (`INF-015`'s design explicitly reuses "the container's own healthcheck"). **Not claimed as done here** — `INF-009` has no ticket, no Outcome, and no Review-verified confirmation, and it belongs to Sprint 07's infra track, not this sprint's Operability track. Flagged for whoever closes out Sprint 07 to formally verify and either close `INF-009` or explain the gap, rather than left as a silent, undocumented byproduct.
- The same file also shows `validation-service`'s and `gateway-api`'s runtime `DATABASE_URL` already pointed at `naive_first_app` (INF-014's new non-superuser role) — this is the concrete finding behind the OPS-004 deferral below.

## Sequencing decision (stated explicitly)

**Order: OPS-001, then (OPS-005 in parallel) → OPS-002 and OPS-003.**

1. **OPS-001 runs first.** It is Must-priority, has no dependency, and is the one gap `implementation-plan.md` section 8 already committed the platform to closing "once the first lib ships" — a trigger that fired back in Sprint 01/02 and has sat unactioned since. It is also the formal, backlog-stated dependency of OPS-002 and the practical (not formal) enabler of OPS-003's automated-Dependabot-PR option.
2. **OPS-005 runs in parallel with OPS-001**, not after it. It has no dependency on OPS-001 (deepening `/health` is pure application code in each service's `main.py`, unrelated to the new CI workflow file), touches an entirely disjoint set of files, and there's no reason to leave it idle waiting on OPS-001 to land — same "front-load independent work" reasoning Sprint 06 applied to ARCH-003.
3. **OPS-002 runs after OPS-001**, per the backlog's own explicit `Depends on: OPS-001` — it adds coverage reporting *into* the CI workflow OPS-001 creates, so it cannot be written first.
4. **OPS-003 runs after OPS-001 too**, though not a formal dependency (the backlog states "the manual-cadence option does not require it"). Sequenced last anyway because: (a) OPS-003's own acceptance criteria explicitly asks it to state whether the automated-Dependabot-PR route is viable, which is only true once OPS-001's CI exists to gate those PRs — writing OPS-003 before OPS-001 lands would force it to hedge on an open question that OPS-001 answers for free by the time OPS-003 starts; (b) it is the smallest, lowest-risk story in scope (a documented policy, not new tooling), so there's no cost to running it last.

## Stories in scope, in execution order

1. **OPS-001** [Must] — Wire an automated CI pipeline running every module's test suite, including `naive_first_engine`'s NFE-015/016 regression gate and NFE-018 doc-sync check. Runs first: no dependency, and both OPS-002 and OPS-003 are more coherent (formally or practically) once it exists. Depends on: none.
2. **OPS-005** [Should] — Deepen `validation-service`'s and `gateway-api`'s `/health` endpoints to check real DB connectivity instead of returning a hardcoded `{"status": "ok"}`. Runs alongside OPS-001: no dependency either direction, disjoint files (`main.py` in each service vs. a new `.github/workflows/` file), front-loaded rather than left idle. Depends on: none.
3. **OPS-002** [Should] — Add `pytest-cov` to all five modules and surface coverage in OPS-001's CI run. Runs after OPS-001 per the backlog's own stated `Depends on: OPS-001` — it extends the CI workflow OPS-001 creates. Depends on: OPS-001.
4. **OPS-003** [Should] — Document a dependency-upgrade cadence/policy across the platform's five independently-lockfiled modules. Runs last: no formal dependency, but its own acceptance criteria (stating whether the automated-Dependabot-PR route is viable) is answered cleanly once OPS-001's CI exists rather than left as an open question; smallest/lowest-risk story in scope, no cost to sequencing it last. Depends on: none (soft dependency on OPS-001 per the backlog's own text).

## Stories explicitly deferred

- **OPS-004** [Must] — **Deferred, with justification, not silently dropped.** OPS-004's own acceptance criteria requires actually running `docker compose -f infra/docker-compose.yml up -d` (full stack) and confirming both services' `/health` endpoints respond `200`. Reading `infra/docker-compose.yml` directly (see pre-planning checks above) shows both services' runtime `DATABASE_URL` is **already** wired to `naive_first_app` — the new non-superuser role Sprint 07's `INF-014` introduces — but `INF-014`'s own Implementation acceptance criteria (applying those grants against the *live* running Postgres container, not just the fresh-volume init script) is unconfirmed done (ticket status `todo`, no Outcome recorded). Running OPS-004's full-stack `docker compose up` right now would very likely fail with an authentication/permission error against `naive_first_app` — a Sprint 07 (`INF-014`) completeness problem, not the non-root/port-binding correctness problem OPS-004 exists to verify. Executing OPS-004 before Sprint 07 lands would produce a false-negative result and conflate two unrelated stories' verification. **Revisit trigger**: as soon as Sprint 07's `INF-014` is confirmed done (live-container grants applied, containers reconnect successfully) — schedule OPS-004 immediately after, ideally as the first story of Sprint 09, not left indefinitely.
- **OPS-006** [Could] — Deferred per the backlog's own priority rationale: no live pilot client and no incident on record that structured logging would have shortened. Worth doing before real concurrent traffic exists, but nothing in this sprint's scope or Sprint 07 is blocked by its absence.
- **OPS-007** [Won't] — Not scheduled. Already a deliberate Product Owner decline (no deployed, always-on instance exists yet); no action needed unless its stated revisit trigger (first continuously-running deployment, or an external pilot client's SLA) becomes true.
- **LC-005** (README doc-sync, `libs/common`), **GW-010/011/013/014** (key revocation, JWT session auth, rate limiting, audit logging — `gateway-api`), **VS-016/017** (OpenAPI/README sync, client-prediction Strategy — `validation-service`), **INF-008/010** (MinIO, TimescaleDB hypertables), **ARCH-005/007/008** (tenant-header tracking story, service-naming convention, `Security()` auth-pattern doc) — **deferred as a block, not individually contested.** All are Should/Could, none blocking or blocked by this sprint's OPS scope, and none has a stated urgency trigger that has fired (no pilot client for GW-011/013/014, no second `libs/common` consumer for LC-005/schemas, no time-series query pattern for INF-010). Mixing this pool into an Operability-focused sprint would blur the single sprint goal above without a coherent reason to bundle them — they belong to a future "doc-sync + auth-hardening mop-up" sprint, not this one. Not silently dropped: this list is exhaustive of the requester-named older pool minus GW-012 (see correction above).
- **INF-009** (Compose healthchecks/startup ordering) — **not scheduled here**, and explicitly not claimed done despite the finding above that `infra/docker-compose.yml` already appears to satisfy its acceptance criteria. It is infra-track work coupled to Sprint 07's in-flight bootstrap script, not this sprint's Operability track; whoever closes out Sprint 07 should formally verify and close it then, rather than have this sprint claim credit for an unverified byproduct.

## Definition of done for this sprint

- A CI workflow exists (e.g. `.github/workflows/ci.yml`) that runs on every push/PR and executes each of the five modules' own documented test commands independently, with per-module pass/fail visibility (not one opaque monorepo-wide result); `naive_first_engine`'s NFE-015 regression gate is confirmed running in CI, not skipped; the workflow's existence is documented from a single authoritative pointer (root doc or each module's README).
- `pytest-cov` (or equivalent) is a dev dependency of all five modules; OPS-001's CI workflow runs tests with coverage enabled and prints the report; no hard coverage-percentage gate is enforced (explicitly out of scope per OPS-002's own acceptance criteria); each module's README states how to run its own tests with coverage locally.
- A documented dependency-upgrade policy exists (automated or explicitly manual) covering all five modules' independently-lockfiled dependency sets, explicitly states whether `services/ingestion-service/requirements.txt`'s unpinned floors move to a lockfile or stay as-is, and is referenced from each of the five modules' own READMEs.
- `validation-service`'s and `gateway-api`'s `/health` endpoints perform a real, cheap connectivity check against their own DB backend and return a non-`200`/distinguishable-failure body when that check fails, while still returning the existing `200 {"status":"ok"}` shape in the healthy case (additive, not a breaking contract change); each service has a test proving the failure case using its existing dependency-override/fake pattern.
- All five modules' full test suites pass with zero regressions, verified directly (not merely trusted from a green CI checkmark) before this sprint is marked done.
- Every touched module's README states current status/ownership/contract, per CLAUDE.md's own standing convention.

## Handoff to Tech Lead

- Sprint file: `docs/sprints/sprint-08.md`
- Sprint goal: see above — CI-enforced test execution across all five modules (with coverage), a documented dependency-upgrade cadence, and honest `/health` connectivity checks in both FastAPI services.
- Ordered story list: **OPS-001** (Must) and **OPS-005** (Should) in parallel first (no dependency between them, disjoint files) → **OPS-002** (Should, depends on OPS-001) → **OPS-003** (Should, sequenced last for coherence, not a hard dependency).
- Dependency/risk notes:
  - OPS-002 has a **formal** `Depends on: OPS-001` per the backlog — do not start it before OPS-001's workflow file exists to extend.
  - OPS-003 has no formal dependency but is more coherent after OPS-001 exists (its own acceptance criteria asks it to state whether the automated-Dependabot-PR route is viable — trivially true once CI exists, open otherwise).
  - OPS-005 is safe to run fully in parallel with OPS-001 — verify this stays true at ticket-breakdown time (no shared file touched).
  - **OPS-004 (Must) is deliberately not in this sprint** — it is blocked in practice (not formally) on Sprint 07's `INF-014` finishing (live-container role-grant application), because `infra/docker-compose.yml` already points both services' runtime `DATABASE_URL` at the not-yet-fully-provisioned `naive_first_app` role. Do not schedule OPS-004 until Sprint 07 is confirmed complete — running it earlier will produce a misleading failure unrelated to what OPS-004 tests.
  - This sprint's stories touch application code and CI/tooling config only (`main.py` in both services, `pyproject.toml`/`requirements.txt` dev-dependencies, a new `.github/workflows/` file, READMEs). None of them touch `infra/postgres-init/`, `infra/migrate.*`, or `infra/bootstrap.*` — zero file overlap with Sprint 07's in-flight scope, confirmed during planning.
  - `INF-009` appears substantially already satisfied by `infra/docker-compose.yml`'s current (uncommitted) state — flagged for whoever closes Sprint 07 to verify formally, not assumed done by this sprint.

## Sprint 08 outcome

All 4 in-scope stories (OPS-005-01, OPS-005-02, OPS-002, OPS-003) done, alongside OPS-001 (already
done entering this session). Sequencing followed exactly as planned above: OPS-001 + OPS-005-01 +
OPS-005-02 in parallel, then OPS-002, then OPS-003. Every ticket's Review acceptance criteria were
personally verified by the Tech Lead against the actual code/doc diffs (not the dev agents' own
outcome notes alone) — see `docs/tickets/README.md`'s Sprint 08 outcome paragraph for the full
verification detail, including the exact CI/coverage/health-check/policy-doc confirmations and the
two full-suite re-runs (`gateway-api` 68/68, `validation-service` 65/65, zero regressions).

**Definition of done, checked against this sprint file's own list**: CI workflow exists and runs all
five modules independently with per-module pass/fail visibility, NFE-015 confirmed running in CI, not
skipped — met. `pytest-cov` is a dev dependency of all five modules, CI prints coverage with no hard
gate, each README documents the local coverage command — met. A documented dependency-upgrade policy
exists (`docs/dependency-upgrade-policy.md`), states the `ingestion-service` unpinned-floors decision
explicitly, referenced from all five READMEs — met. Both services' `/health` endpoints perform a real
`SELECT 1` connectivity check, return `200`/`503` distinctly, preserve the existing healthy-case shape,
and each has a non-tautological failure-path test — met. All five modules' full suites pass with zero
regressions, verified directly — met for the two modules this sprint's code touched
(`validation-service`, `gateway-api`); `naive_first_engine`/`libs/common` were untouched by code this
sprint (README-only) and were not re-run in full (OPS-002's own recorded run earlier in the session
already covers them). Every touched module's README states current status/ownership/contract — met.

**OPS-004 (deferred in this sprint's own planning) is now unblocked**: Sprint 07's `INF-014` is
confirmed `done` per its own ticket file's Status/Outcome (live-container `naive_first_app` role
verified, both services reconnect, DB-level RLS enforcement proven). Per this sprint's own stated
revisit trigger, OPS-004 should be scheduled as Sprint 09's first story. One caveat to carry into that
scheduling: INF-014's Outcome discloses a real, not-yet-ticketed `services/validation-service` bug
(`POST /runs`'s Postgres-backed `create_run` returns `500` under real RLS enforcement, root-caused to
a post-commit `session.refresh()` losing the `app.tenant_id` scope) that would make OPS-004's own
full-stack smoke test fail on an unrelated cause unless fixed first or explicitly worked around.
