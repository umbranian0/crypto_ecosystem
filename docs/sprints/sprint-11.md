# Sprint 11 — `services/dashboard-web` PoC (login, run detail, submit-a-run), explicit trigger override

Sprint goal: a tenant can log in to `services/dashboard-web` with their gateway-api API key, submit a
new validation run through a form, and view that run's status and per-split results — the minimum
submit -> view loop exists as a real, tested, running service, built deliberately ahead of
implementation-plan.md's trigger #8 (no pilot client exists yet) at explicit user request.

Backlog source: `docs/product/backlog-dashboard-web.md` (DASH-001 through DASH-009, DASH-005-GAP,
DASH-101-107). Also read directly: `GW-017` (`docs/product/backlog-gateway-api.md`) and its
cross-reference note in `docs/product/backlog-validation-service.md` — considered for this sprint,
not included (see "GW-017 scheduling decision" below).

## Pre-planning checks performed (stated explicitly, not assumed)

- `docs/sprints/` currently ends at `sprint-10.md` (Sprint 10, closed, all 5 stories done, zero
  regressions per its own Outcome section). No carried-over/incomplete story exists anywhere in that
  file. This is confirmed to be **Sprint 11**, not a later number.
- `docs/product/backlog-dashboard-web.md` read in full this session, including its "Explicit trigger
  override" section and its six numbered "Explicit scope/dependency decisions."
- `docs/implementation-plan.md` section 6 (trigger table) and section 2 (module boundary map) read
  directly. `services/dashboard-web`'s trigger #8 ("a second pilot client, or the first pilot client
  says 'I don't want to curl this'") has **not** fired — no pilot client exists anywhere in this
  repo's docs. This sprint is a **deliberate, disclosed trigger override**, the same category as
  `gateway-api` building ahead of trigger #5 (Sprint 05) and `ingestion-service`'s connectors being
  pulled forward ahead of trigger #6 (`INGEST-001`, Sprint 10). It is carried forward explicitly here,
  not silently treated as normal trigger-driven sequencing.
- `docs/tickets/README.md` read in full: confirms `gateway-api`'s real, shipped route set (`GW-008`:
  exactly `POST /runs`, `GET /runs/{id}`, `GET /runs/{id}/splits`, nothing else) and
  `validation-service`'s real, shipped route set (`VS-006/007/008`, same three routes). Both READMEs'
  own Contract/Routes sections were also read directly and independently confirm the same thing:
  `services/validation-service/README.md`'s `## Routes` section lists exactly
  `POST /runs`, `GET /runs/{run_id}`, `GET /runs/{run_id}/splits` — **no list endpoint exists on
  either service today.** This confirms DASH-005-GAP's claim rather than assuming it from the
  backlog's own prose.
- No team size/velocity given for this sprint. Sized against the established precedent of Sprints
  06-10 (2-9 self-contained stories each). This sprint's 8 in-scope stories (DASH-001 through
  DASH-004, DASH-006 through DASH-009) sit inside that range, and — unlike Sprint 06's explicit
  larger-debt-sprint outlier — form one tight dependency chain within a single new service rather
  than an unrelated pool, matching Sprint 05's (`gateway-api` scaffolding) shape more closely than
  Sprint 10's (independent parallel-round) shape.

## DASH-005 / DASH-005-GAP scheduling decision (stated explicitly, with reasoning)

**Decision: (b) — defer `DASH-005` out of this sprint.** `DASH-001/002/003/004/006/007/008/009` ship
without a runs-list page; `DASH-004` (run detail, by id) and `DASH-006` (submit-a-run, which redirects
to the new run's detail page on success) already satisfy the requested minimum "submit -> view" loop
without needing to enumerate a tenant's runs. `DASH-005` and `DASH-005-GAP` are flagged for a future
sprint, pending the enabling work below.

Reasoning:
- `DASH-005-GAP` itself is explicit that the fix belongs as **new tickets** in
  `docs/product/backlog-validation-service.md` (a new `VS-0NN`) and `docs/product/backlog-gateway-api.md`
  (a new `GW-016`) — not authored in the dashboard-web backlog, "since dashboard-web owns no data
  access." Those two tickets **do not exist yet** in either backlog today (verified by reading both
  files directly this session) — they are a flagged capability gap, not an approved, prioritized
  backlog story.
- This role's own mandate is to sequence **already-prioritized, already-approved** stories, not to
  invent or silently pre-approve new scope for a different module's backlog. Authoring `VS-0NN`/`GW-016`
  myself here — even just to schedule them — would mean scheduling stories the Product Owner has not
  yet written, prioritized, or approved for `validation-service`/`gateway-api`. That decision belongs
  to the Product Owner, not to this sprint plan.
- Option (a) (schedule the two enabling tickets inside this sprint anyway) was considered and
  rejected on that basis, not on cost or dependency-ordering grounds — the ordering itself would be
  trivial (`VS-0NN` before `GW-016` before `DASH-005`, all before `DASH-009`'s E2E suite, mirroring
  `INF-014`-style cross-service ticket sequencing) if those tickets already existed as approved backlog
  items.
- This sprint's minimum-scope requirement (backlog decision list, `DASH-006`'s rationale line: "the
  PoC demonstrates submit -> running/complete -> view results, not just read-only viewing") is fully
  satisfiable via `DASH-004` + `DASH-006` alone, so deferring `DASH-005` does not leave the sprint
  goal unmet.

**Follow-up flagged for the requester/Product Owner, not silently dropped**: get `VS-0NN` (validation-
service tenant-scoped `GET /runs` list endpoint) and `GW-016` (matching gateway-api proxy route)
authored and approved in their own backlogs, so a future sprint can schedule
`VS-0NN -> GW-016 -> DASH-005 -> DASH-009`. `DASH-009`'s own acceptance criteria already say its
third flow "view a completed run" can be satisfied via `DASH-005 (or its DASH-005-GAP fallback)" —
this sprint uses that fallback explicitly (a known run id reached via `DASH-006`'s redirect), not a
silent workaround.

## GW-017 scheduling decision (stated explicitly, with reasoning)

**Decision: keep `GW-017` (Locust load-test suite) out of this sprint**, deferred to a separate future
sprint against `docs/product/backlog-gateway-api.md`.

Reasoning: `GW-017` touches a completely disjoint file set (`services/gateway-api/loadtest/`) from
every dashboard-web story in this sprint, and there is no dependency in either direction — bundling
it would cost nothing in sequencing terms. But this sprint's single stated goal is the dashboard-web
submit -> view PoC existing; `GW-017` is unrelated tooling scope against a different, already-shipped
service. Matches this repo's own precedent from Sprint 08 (`docs/sprints/sprint-08.md`), which kept
its OPS-focused sprint scoped to `OPS-001/002/003/005` and explicitly deferred a block of
zero-dependency-conflict, technically-schedulable items (`LC-005`, `GW-010-014`, `VS-016/017`,
`INF-008/010`, `ARCH-005/007/008`) rather than let an available-but-unrelated item blur a sprint's
single goal. `GW-017` is exactly that shape here: available, zero-conflict, but unrelated to this
sprint's one sentence of intent. It is left for the Tech Lead/PM to schedule in its own sprint
against `gateway-api`'s backlog whenever that's next prioritized.

## Sequencing decision (stated explicitly, dependency-first)

All in-scope stories are Must or Should priority; none is reordered ahead of a higher-priority item
it doesn't depend on. The chain is dictated by the backlog's own stated dependencies, not by priority
alone:

1. `DASH-001` — no dependency; scaffolding everything else needs.
2. `DASH-002` — depends on `DASH-001`; login screen.
3. `DASH-003` — depends on `DASH-002`; the DI seam every downstream-call route must share (DRY).
4. `DASH-004` and `DASH-006` — both depend on `DASH-003`'s seam; `DASH-006` additionally formally
   depends on `DASH-004` (its redirect-on-201 target), so `DASH-004` runs first, then `DASH-006`
   immediately after, rather than truly in parallel with it (correcting the general "parallel once
   DASH-003 lands" framing to `DASH-006`'s own stated `Depends on: DASH-003, DASH-004`).
5. `DASH-007` and `DASH-008` — Should priority, low-risk, single dependency each already satisfied
   by this point (`DASH-007` on `DASH-002`+`DASH-003`; `DASH-008` on `DASH-001` only) — scheduled
   alongside the tail of the chain rather than gating on anything after `DASH-004`/`DASH-006`.
6. `DASH-009` — depends on `DASH-002`, `DASH-004`, `DASH-005` (or its disclosed `DASH-005-GAP`
   fallback — used here since `DASH-005` is deferred), `DASH-006`. Runs last: it exercises
   functionality that must already exist, per its own rationale.

`DASH-005` (Must, blocked) is explicitly **not** silently reordered around its priority — it would
otherwise sit before `DASH-007`/`DASH-008` (Should) on priority alone, but it is deferred out of this
sprint entirely per the scheduling decision above, not reordered past lower-priority work within this
sprint.

## Stories in scope, in execution order

1. `DASH-001` [Must] — Service scaffolding. No dependency; nothing else can be built without it.
2. `DASH-002` [Must] — Login screen (API key -> server-side session). Depends on `DASH-001`.
3. `DASH-003` [Must] — Session-to-downstream-header DI seam. Depends on `DASH-002`.
4. `DASH-004` [Must] — Run detail view (`GET /runs/{id}`, `GET /runs/{id}/splits`). Depends on
   `DASH-003`.
5. `DASH-006` [Must] — Submit-a-run form (`POST /runs`, redirect to `DASH-004`'s detail page on
   201). Depends on `DASH-003` and `DASH-004` (redirect target).
6. `DASH-007` [Should] — Logout/session invalidation. Depends on `DASH-002`, `DASH-003`.
7. `DASH-008` [Should] — Health check endpoint (`GET /health` against real gateway-api
   connectivity). Depends on `DASH-001`.
8. `DASH-009` [Should] — Selenium E2E suite (login, submit-run, view-completed-run flows, each with
   one negative/edge case). Depends on `DASH-002`, `DASH-004`, `DASH-005`'s disclosed
   `DASH-005-GAP` fallback (a known run id reached via `DASH-006`'s own redirect, not `DASH-005`'s
   list page), `DASH-006`. Runs last.

## Stories explicitly deferred

- `DASH-005` (Must, blocked) — cannot be built as specified: no `GET /runs` list endpoint exists on
  `gateway-api` or `validation-service` today (confirmed by reading both READMEs' Contract/Routes
  sections directly this session). Blocked on `DASH-005-GAP`, which requires new, not-yet-authored
  backlog tickets (`VS-0NN`, `GW-016`) in their own modules' backlogs — outside this sprint's and
  this role's authority to schedule until the Product Owner authors and approves them. See the
  "DASH-005 / DASH-005-GAP scheduling decision" section above for full reasoning.
- `DASH-005-GAP` (not a dashboard-web story) — flagged for the Product Owner to turn into real
  `VS-0NN` (validation-service) and `GW-016` (gateway-api) backlog tickets; not scheduled here since
  dashboard-web owns no data access and cannot resolve this gap itself.
- `GW-017` (Should, `gateway-api` backlog) — technically zero-dependency-conflict with this sprint,
  but deliberately kept out to preserve this sprint's single coherent goal (the dashboard-web PoC),
  matching Sprint 08's own precedent of deferring available-but-unrelated items rather than blurring
  a sprint's stated goal. See "GW-017 scheduling decision" above.
- `DASH-101` through `DASH-107` (Won't, this backlog) — not proposed by the Product Owner; not
  reconsidered here (reporting/monitoring/upload-UI/multi-tenant-switching/admin-panel/`libs/sdk`
  wrapping/JWT-session-auth all correctly out of scope per the backlog's own reasoning, each tied to
  an unfired trigger or an already-made design decision).

## Definition of done for this sprint

- Every acceptance-criteria checkbox in `DASH-001`, `DASH-002`, `DASH-003`, `DASH-004`, `DASH-006`,
  `DASH-007`, `DASH-008`, `DASH-009`'s backlog entries is checked, not left implicitly assumed
  satisfied.
- `services/dashboard-web/README.md`'s status line reflects the real built state (scaffolded ->
  implemented), states the trigger-#8 override explicitly (no pilot client exists), and documents
  that `DASH-005` (runs list) is deliberately not built this sprint, pending `DASH-005-GAP`'s
  resolution in `validation-service`'s and `gateway-api`'s own backlogs.
- `uv run pytest` (route-handler unit tests, mocked gateway-api) passes with zero failures for
  `DASH-001` through `DASH-008`'s own test coverage; `DASH-009`'s Selenium suite is documented as
  run separately (e.g. `pytest -m e2e` or an equivalent script), not folded into the default unit
  run, and passes against a real running `dashboard-web` instance plus a fixture/stub `gateway-api`.
- No raw API key is ever rendered, logged, or placed in a URL anywhere in the shipped code
  (`DASH-002`'s explicit acceptance criterion) — verified by the Tech Lead reading the actual diff,
  not merely trusting a green test run.
- No language anywhere in `dashboard-web`'s templates/README implies price prediction or a trading
  signal (`CLAUDE.md` positioning constraint) — validation/audit framing only, checked directly.
- `docs/tickets/README.md` gains a new `services/dashboard-web (DASH-*)` section for this sprint's
  eight tickets, and `docs/product/backlog-dashboard-web.md`'s own story statuses are left accurate
  (DASH-005 still marked blocked, not silently closed or half-implemented).

## Handoff to Tech Lead

- **Sprint file**: `docs/sprints/sprint-11.md`
- **Sprint goal**: a tenant can log in to `services/dashboard-web` with their gateway-api API key,
  submit a new validation run through a form, and view that run's status and per-split results — the
  minimum submit -> view loop exists as a real, tested, running service, built deliberately ahead of
  trigger #8 (no pilot client exists) at explicit user request.
- **Ordered story list**:
  1. `DASH-001` — scaffolding, no dependency.
  2. `DASH-002` — login screen, depends on `DASH-001`.
  3. `DASH-003` — DI seam (session -> downstream headers), depends on `DASH-002`. Every route from
     here on must go through this one dependency — do not let `DASH-004`/`DASH-006` hand-roll their
     own header logic.
  4. `DASH-004` — run detail view, depends on `DASH-003`.
  5. `DASH-006` — submit-a-run form, depends on `DASH-003` **and** `DASH-004` (redirects to
     `DASH-004`'s detail page on success — sequence `DASH-004` fully before starting `DASH-006`, not
     in parallel, despite both only formally sharing `DASH-003` as a common ancestor).
  6. `DASH-007` — logout, depends on `DASH-002`+`DASH-003`.
  7. `DASH-008` — health check, depends on `DASH-001` only; safe to run in parallel with anything
     from step 2 onward if useful, since it touches no shared file with the login/session/DI chain.
  8. `DASH-009` — Selenium E2E suite, last. Exercises `DASH-002`/`DASH-004`/`DASH-006` plus
     `DASH-005-GAP`'s fallback (a known run id from `DASH-006`'s own redirect, since `DASH-005`'s
     list page is not being built this sprint — do not let this ticket quietly reintroduce a runs-
     list page to make its own third flow easier; use the redirect-returned id instead, exactly as
     the backlog's own fallback describes).
- **Dependency/risk notes**:
  - `DASH-005` and `DASH-005-GAP` are **not in this sprint**. Do not let any story informally grow
    a client-side runs-list substitute (local record-keeping, scraping, etc.) to compensate — the
    backlog explicitly forbids that (`DASH-005`'s own acceptance criteria), and it's the reason
    `DASH-005` is deferred rather than reinterpreted.
  - `DASH-002`'s raw-API-key handling (never rendered/logged/in a URL, HttpOnly cookie only) is this
    sprint's most security-sensitive story — recommend the same extra-scrutiny treatment this repo
    gave `GW-006`/`GW-007` in Sprint 05.
  - `DASH-003` is a DRY-enabling seam every later route depends on — get its header shape and
    unauthenticated-rejection-before-route-logic behavior right before starting `DASH-004`/`DASH-006`,
    since both are built directly on top of it.
  - `DASH-006`'s form must exactly match `gateway-api`'s real `POST /runs` request shape (GW-008) —
    no new default/shortcut that could let a submitted run skip the purge gap or naive baselines
    (backlog's own explicit constraint, tying back to this platform's core leakage-avoidance
    positioning).
  - This entire sprint is a disclosed trigger-#8 override (no pilot client exists) — carry that
    framing into `services/dashboard-web/README.md`'s status line and into `DASH-001`'s own
    acceptance criterion for it, the same way `gateway-api`'s README discloses its own trigger-#5
    override.
  - Follow-up for a future sprint, not this one: once the Product Owner authors and approves `VS-0NN`
    (validation-service tenant-scoped `GET /runs` list) and `GW-016` (matching gateway-api proxy
    route) in their own backlogs, `DASH-005` unblocks and `DASH-009` can be extended to use it instead
    of the redirect-id fallback.
  - `GW-017` (Locust load-test suite) was deliberately left out of this sprint for goal-coherence
    reasons, not a dependency conflict — it's available to schedule in its own future sprint against
    `gateway-api`'s backlog whenever next prioritized.
