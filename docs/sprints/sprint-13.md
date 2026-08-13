# Sprint 13 — `services/economic-service` scaffolding, structural eligibility gate, disclosed trigger-#11 override

Sprint goal: `services/economic-service` exists as a scaffolded, tested skeleton with an inputs-only
schema, typed contracts, a mock-only upstream integration, and a structural, code-enforced eligibility
gate that makes it impossible for the running service to return a real profitability/return/P&L figure
today — proving in code, not just in prose, that this scaffold is inert until a real client model
demonstrates outperformance that does not yet exist anywhere on this platform.

Backlog source: `docs/product/backlog-economic-service.md` (6 Must-priority stories: ECON-001 through
ECON-006; ECON-007–011 are Won'ts, not in scope, not reconsidered here).

## Pre-planning checks performed (stated explicitly, not assumed)

- `docs/sprints/` currently ends at `sprint-11.md` (Sprint 11, `dashboard-web`, closed, all 8 in-scope
  stories done). `docs/sprints/sprint-13.md` did not exist at the time this file was written — confirmed
  by directory listing immediately before writing this file, per the explicit instruction to re-check
  rather than assume. This is **Sprint 13**.
- `docs/implementation-plan.md` section 2 (module boundary map, line 34) and section 6 (trigger table,
  line 127) read directly. Trigger #11 for `services/economic-service` reads: "Only once a specific
  client model has already demonstrated stable outperformance in `validation-service` — never before,
  per the ethical boundary in docs section 2.7." This trigger has **not** fired.
- `docs/product/backlog-economic-service.md` read in full this session, including its "Override note"
  section (lines 7–18) and its five "Explicit scope/dependency decisions." This backlog's own override
  note draws a distinction this plan carries forward without softening (see dedicated section below).
- Each of the 6 Must stories' own `Depends on:` line and acceptance-criteria file list read directly to
  build the sequencing below — not inferred from priority or story number alone.
- No team size/velocity given for this sprint. Sized against established precedent: this backlog has
  exactly 6 Must stories and zero Should/Could stories (only Won'ts beyond the Musts) — a smaller,
  tighter shape than Sprint 05's 9-story `gateway-api` chain or Sprint 11's 8-story `dashboard-web`
  chain, and closest in shape to Sprint 04 (4 Must `libs/common` stories + 1 cross-backlog wiring
  story, fully sequential, no independent branches). Like Sprint 04, this sprint schedules its entire
  Must set in one pass rather than holding any of it back for a follow-on sprint, since there is no
  Should/Could tier here to defer and the six stories form a single dependency chain with one
  parallelizable pair, not an unrelated pool (Sprint 06's shape) or a multi-branch backlog (Sprint 05's
  shape).

## The ethical-boundary distinction — restated verbatim in spirit for whoever picks this up next

This is **not** a routine trigger override like `gateway-api` (trigger #5), `dashboard-web` (trigger
#8), or `ingestion-service` connectors (trigger #6/#10). Those triggers were all soft build-order
conditions — "no pilot client yet" — a scheduling convenience with no normative weight of its own.
Trigger #11 is different in kind: `docs/implementation-plan.md` states it exists "per the ethical
boundary in docs section 2.7," and `docs/da-tese-ao-produto.md` section 2.7 states plainly that any
extension toward trading claims *requires* the economic module (costs, slippage) *before* any
profitability claim, and requires the platform to keep statistical accuracy and economic value visibly
separate. Section 2.3.5 states the module is "only activated after a model passes Subsystem 1." This is
tied directly to this platform's own core finding: no model has ever beaten Naive0 in a stable,
statistically significant way at any horizon (CLAUDE.md; da-tese-ao-produto.md section 1.4/1.5).

The backlog's own override note goes further than a policy citation — it states two verified facts,
carried forward here rather than re-derived: (1) every real run on this platform to date compares
Naive0 against NaiveLast, never a real client-supplied model, per `validation-service/README.md`'s data
model and `VS-011`'s own regression-fixture framing; (2) `VS-017` ("client-supplied prediction
baseline"), the precondition for a real client-model DM verdict to even exist, is itself deferred and
unbuilt (`docs/tickets/README.md`, Sprint 03's own deferral list). This means there is currently **no
gate to fail or pass** — the capability the gate would check does not exist upstream yet. Every story
in this sprint is scaffolding whose only defensible justification is that none of it can produce an
externally-observable capability: no endpoint built this sprint can ever return a real profitability
number, by construction, because ECON-004 makes the only upstream integration a disclosed mock fixture,
and ECON-005 is the code-level proof of that inertness, not just a documented promise of it.

If any story in this sprint could produce a reachable code path returning a real number outside that
single, isolated positive-control test case, or if this sprint were proceeding without the user's own
explicit, informed sign-off on this distinction, it should not be built. That sign-off is what
authorizes this sprint to exist ahead of trigger #11 — it is not this plan's own decision to make
unilaterally, and it is restated here so the Tech Lead does not have to re-derive it from the backlog
alone.

## Sequencing decision (stated explicitly, dependency-first)

All six in-scope stories are Must priority, so execution order here is governed entirely by each
story's own stated `Depends on:` line, not by priority (there is no priority tier to resolve conflicts
between):

1. `ECON-001` — no dependency; scaffolding everything else needs (`Depends on: none`).
2. `ECON-002` and `ECON-003` — both depend on `ECON-001` only (`ECON-002`: "Depends on: ECON-001`;
   `ECON-003`: "Depends on: ECON-001"). These two are genuinely independent of each other — `ECON-002`
   is the Postgres schema/repository layer, `ECON-003` is the Pydantic contract layer, and neither
   story's acceptance criteria or file list names the other as a precondition. They can run in
   parallel once `ECON-001` lands. Sequenced here as 2a/2b for clarity, not as a forced serial order.
3. `ECON-004` — depends on `ECON-001` and `ECON-003` (its own stated `Depends on:` line), **not** on
   `ECON-002`. It needs `ECON-003`'s `UpstreamValidationResult`-shaped contract to mock against, but has
   no dependency on the Postgres schema. Sequenced after both 2a and 2b land, even though it only
   strictly needs 2b, to keep the chain simple and because nothing is gained by racing it ahead of
   `ECON-002`'s completion in a single-pass sprint of this size.
4. `ECON-005` — depends on `ECON-002`, `ECON-003`, `ECON-004` (its own stated `Depends on:` line) — the
   first story that needs all three prior branches complete. This is the sprint's highest-stakes story;
   see the dedicated flag below.
5. `ECON-006` — depends on `ECON-001` and `ECON-005` (its own stated `Depends on:` line) — its doc-sync
   grep check needs `ECON-005`'s guard/route code to actually exist to scan for stray profitability
   language outside the one gated success path. Runs last.

No Must-priority story here is blocked on a lower-priority story's output (there is no Could/Should
tier in this backlog to check against) — the only ordering constraint this sprint has to respect is the
dependency chain above.

## Stories in scope, in execution order

1. `ECON-001` [Must] — Service scaffolding (`uv`-managed FastAPI skeleton, `src/app/{routers,
   dependencies,repositories}`, `GET /health`, working `pytest` config). Depends on: none.
2. `ECON-002` [Must] — `economic.*` Postgres schema (`fee_schedules`, `slippage_models`,
   `simulation_configs`) + Repository-pattern interfaces for cost/slippage **inputs only** — no
   `economic_results`/`pnl`/`profit` table or column, enforced by its own schema-level regression test.
   Depends on: `ECON-001`. Runs in parallel with `ECON-003`.
3. `ECON-003` [Must] — Contracts: `SimulationRequest`, and two structurally disjoint response models
   (`EligibleSimulationResult` with numeric fields, `NotEligibleForSimulation` with none) — kept local
   to `economic-service`, not promoted to `libs/common` this backlog (only one consumer exists today).
   Depends on: `ECON-001`. Runs in parallel with `ECON-002`.
4. `ECON-004` [Must] — Mocked-upstream-only integration: a `MockValidationResultClient` returning
   hardcoded fixture data tagged `source: Literal["mock_fixture"]`, never a real `httpx` call to
   `validation-service`, with a test proving it is the *only* implementation wired into DI anywhere in
   the codebase. Depends on: `ECON-001`, `ECON-003`.
5. `ECON-005` [Must] — **The structural eligibility gate.** `POST /simulations`, a single named guard
   function (`check_economic_eligibility`) as the only authorized path to the profitability-computation
   function, refusing unless `source == "live"` **and** the DM verdict shows a Harvey-corrected,
   statistically significant Naive0-beating result. Refusal returns `409`/`422`
   `NotEligibleForSimulation` with no numeric field; success returns `200` `EligibleSimulationResult`.
   Requires all four negative/positive-control tests specified in the backlog (see flag below).
   Depends on: `ECON-002`, `ECON-003`, `ECON-004`.
6. `ECON-006` [Must] — No profitability language outside the gated success path: README rewrite
   (not just a status-line edit) stating "statistical accuracy ≠ economic value" in CLAUDE.md's own
   language, a grep-style doc-sync check scanning docstrings/README/log messages for profitability
   language outside `ECON-005`'s own gated module, and OpenAPI `summary`/`description` strings on
   `POST /simulations` stating the eligibility precondition in plain language. Depends on: `ECON-001`,
   `ECON-005`.

## Stories explicitly deferred

- `ECON-007` (real `validation-service` integration) — Won't, this backlog. Requires `VS-017` shipping
  (currently deferred, unbuilt in `validation-service`'s own backlog) **and** a real client model
  producing a genuine outperformance verdict. Neither exists. Not reconsidered here; revisiting this is
  its own future, separately-authorized ticket per `ECON-004`'s own hard rule.
- `ECON-008` (UI / `dashboard-web` integration) — Won't, this backlog. `dashboard-web`'s own backlog
  doesn't reach economic-simulation views; a UI surface for a service that cannot yet return a real
  number would itself risk implying eligibility that doesn't exist.
- `ECON-009` (real report/output distribution) — Won't, this backlog. `reporting-service` (trigger #7,
  also not fired) doesn't render economic-simulation output; this sprint produces no artifact meant to
  be distributed to a client.
- `ECON-010` (`economic_results`/persisted profitability output table) — Won't, this backlog,
  deliberately called out separately from `ECON-002`'s own scope decision: persisting a computed result
  implies one has legitimately been computed. If `ECON-005`'s gate is ever satisfied for real, this is a
  new, separately-authorized story reviewed with the same scrutiny as `ECON-005` — not an incidental
  addition to a later "add persistence" ticket.
- `ECON-011` (JWT/session auth beyond scaffold-minimum) — Won't, this backlog. Matches `dashboard-web`'s
  own `DASH-107` precedent — a full auth build-out is out of scope for a service returning no real data.

None of these five are reconsidered or reopened here — they are the Product Owner's own Won't calls,
carried forward, not revisited by this sprint plan.

## Highest-stakes story flag: `ECON-005`

`ECON-005` gets this repo's "extra scrutiny" treatment — the same category this repo already applies to
`GW-006`/`GW-007` (Sprint 05, API-key auth) and `DASH-002` (Sprint 11, raw-API-key handling), because a
mistake here is not a bug, it's a business-honesty failure with the platform's core positioning claim at
stake. Its four required test cases, as specified in the backlog, are **not** to be compressed,
paraphrased, or treated as satisfied by a partial subset when tickets are cut from this story:

- **Test 1**: `ECON-004`'s real mock fixture (`source="mock_fixture"`) submitted → `409`/`422`
  `NotEligibleForSimulation`, response body contains no numeric field, asserted by iterating the actual
  parsed response JSON's keys/types — not merely checking the status code.
- **Test 2**: a hand-constructed `UpstreamValidationResult` with `source="live"` but a DM verdict
  indicating the model did *not* beat Naive0 → same refusal shape as Test 1.
- **Test 3** (positive control): a hand-constructed `UpstreamValidationResult` with `source="live"`
  *and* a real, significant, Harvey-corrected outperformance verdict → `200` `EligibleSimulationResult`
  with a real computed numeric value. Reachable *only* via direct construction inside the test suite in
  this sprint's scope (per `ECON-004`, no code path in the running service can produce `source="live"`
  today) — the test's own docstring must say so explicitly.
- **Test 4**: confirms that, as currently wired end-to-end through `ECON-004`'s mock-only client,
  *every real HTTP call to `POST /simulations` in this service, as actually deployed*, returns the
  refusal shape — proving Test 3's positive path is reachable in isolation but never reachable through
  the service's real running configuration in this sprint's scope. This is the test that makes the
  backlog's own core claim ("this scaffold cannot return a profitability number today, structurally")
  independently verifiable, not merely asserted.

The guard-function structural check (a single named function as the only authorized path to the
computation function, proven by call-graph inspection or an unreachable-without-guard test, not just a
happy-path integration test) is likewise not optional or reducible to a simpler behavioral test.

## Definition of done for this sprint

- Every acceptance-criteria checkbox in `ECON-001` through `ECON-006`'s backlog entries is checked, not
  left implicitly assumed satisfied.
- `uv run pytest` passes in `services/economic-service` with zero failures, including: `ECON-002`'s
  repository round-trip, tenant-isolation, and no-profitability-column-name regression tests;
  `ECON-003`'s disjoint-response-model validation and JSON-schema-shape tests; `ECON-004`'s
  only-mock-implementation-wired-in-DI test; `ECON-005`'s full four-test suite (below); `ECON-006`'s
  grep-style doc-sync check.
- `economic.*` schema contains no table or column matching a profitability-output naming pattern
  (`pnl`, `net_return`, `profit`, or equivalent) anywhere — verified by `ECON-002`'s own regression test
  passing, not by inspection alone.
- No code path anywhere in the shipped service, as actually deployed, can return a real numeric
  profitability figure outside `ECON-005`'s Test 3 positive-control construction — see the dedicated
  verification subsection below.
- `services/economic-service/README.md` reflects real built state: scaffolded → implemented, discloses
  the trigger-#11 override and the override note's own two verified facts (no model has ever beaten
  naive on this platform; `VS-017` is unbuilt), states `ECON-004`'s hard mock-only rule for future
  tickets, and carries `ECON-006`'s "statistical accuracy ≠ economic value" framing.
- `docs/tickets/README.md` gains a new `services/economic-service (ECON-*)` section for this sprint's
  six tickets; `docs/product/backlog-economic-service.md`'s own story statuses are left accurate.
- No code in this sprint touches `libs/naive_first_engine`, `libs/common`, `services/validation-service`,
  `services/gateway-api`, `services/ingestion-service`, `services/reporting-service`, or
  `services/dashboard-web` — all out of scope; `ECON-004`'s mock-only rule means no real network call to
  `validation-service` is ever wired in this sprint.
- `ECON-007` through `ECON-011` remain unscheduled/unbuilt as stated above — this sprint does not start
  any of them.

### Non-negotiable verification requirement — `ECON-005` re-run and code inspection

Before this sprint can be marked complete, **the Tech Lead must personally re-run `ECON-005`'s full
four-test negative/positive-control suite** (Test 1 through Test 4, exactly as specified above and in
the backlog — no subset, no substitution) **and confirm by direct code inspection — not by trusting a
green checkmark** — that:

1. The only code path anywhere in the shipped service capable of constructing a real, non-mock
   `EligibleSimulationResult` with a genuine numeric field is the one success branch downstream of
   `check_economic_eligibility`'s guard, and that branch is provably unreachable through any real
   request the running service can currently receive (Test 4's own point — the guard-refused branch is
   the *only* one reachable end-to-end today).
2. Test 3's positive-control path — the one case that *does* produce a real number — is reachable
   **only** via direct, in-test construction of a hand-built `UpstreamValidationResult`, and that no
   route, dependency-injection wiring, environment variable, or config flag anywhere in the shipped code
   can cause the real running service to construct or receive a `source="live"` result today (this is
   what `ECON-004`'s own DI-introspection test is supposed to prove — the Tech Lead confirms this by
   reading that test and the DI wiring directly, not by re-running it and trusting the result alone).
3. No route handler in `economic-service` calls the profitability-computation function directly,
   bypassing `check_economic_eligibility` — confirmed by reading every route handler in
   `src/app/routers/` directly, not merely by the existence of a passing test asserting this.

This verification is not routine QA and must not be folded into a general "tests passed" checkbox. It
is the one concrete, falsifiable check that the override note's central claim — this scaffold cannot
return a profitability number today, structurally, not just by policy — is actually true of the shipped
code, not merely asserted by it.

## Handoff to Tech Lead

- **Sprint file**: `docs/sprints/sprint-13.md`
- **Sprint goal**: `services/economic-service` exists as a scaffolded, tested skeleton with an
  inputs-only schema, typed contracts, a mock-only upstream integration, and a structural, code-enforced
  eligibility gate that makes it impossible for the running service to return a real
  profitability/return/P&L figure today.
- **Ordered story list**:
  1. `ECON-001` — scaffolding, no dependency.
  2. `ECON-002` and `ECON-003` — both depend on `ECON-001` only; independent of each other, can run in
     parallel.
  3. `ECON-004` — depends on `ECON-001`, `ECON-003` (not `ECON-002`); sequenced after both prior
     branches land for simplicity in a chain this size.
  4. `ECON-005` — depends on `ECON-002`, `ECON-003`, `ECON-004`; the sprint's highest-stakes story, flag
     above.
  5. `ECON-006` — depends on `ECON-001`, `ECON-005`; runs last, needs `ECON-005`'s code to exist to scan.
- **Dependency/risk notes**:
  - This entire sprint is a disclosed trigger-#11 override, and unlike every other trigger override in
    this repo's history, trigger #11 is an ethical/business-honesty boundary from CLAUDE.md and
    da-tese-ao-produto.md section 2.7, not a scheduling convenience — see the dedicated section above.
    Do not let this framing get lost or softened when this sprint is broken into tickets.
  - `ECON-005`'s four negative/positive-control tests, as specified in the backlog and restated in full
    above, are this sprint's actual deliverable. Do not compress, drop, or treat any of the four as
    optional or as covered by a simpler happy-path test when writing tickets.
  - `ECON-004`'s mock-only rule is a hard architectural rule for this backlog, not a temporary stub —
    no ticket in this sprint may wire a real `httpx` call to `validation-service`'s real base URL, and
    no `VALIDATION_SERVICE_URL`-style env var may be read anywhere in this sprint's code.
  - `ECON-002`'s schema is inputs-only by design (`fee_schedules`, `slippage_models`,
    `simulation_configs`) — no `economic_results`/`pnl`/`profit` table exists or should be added this
    sprint; this is enforced by a permanent regression test, not left as a one-time review note.
  - The non-negotiable Tech-Lead verification subsection above (personal re-run of `ECON-005`'s suite +
    direct code inspection of the guard, the DI wiring, and every route handler) is this sprint's own
    definition-of-done gate — it cannot be satisfied by a dev agent's self-report or a passing CI badge
    alone.
