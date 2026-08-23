# Sprint 16 — `services/economic-service` backtesting extension (inert scaffolding, unchanged gate)

Sprint goal: `economic-service` gains a batch backtest endpoint (`POST /backtests`) and an
eligible-only results table that reuse `ECON-005`'s existing, unmodified `check_economic_eligibility`
gate across a bounded set of historical run ids — extending the same inert-scaffolding posture Sprint
13 established, never adding new eligibility logic, exchange integration, or automated-execution
capability.

Backlog source: `docs/product/backlog-economic-service.md`'s "## Backtesting / historical simulation
(new)" section — `ECON-012`, `ECON-013`, `ECON-014` in scope; `ECON-015`–`ECON-018` (Won'ts) not in
scope, not reconsidered here.

## Pre-planning checks performed (stated explicitly, not assumed)

- `docs/sprints/` directory listing confirmed files through `sprint-14.md` only at the time of the
  original check (Sprint 14, closed, all four stories done, full Outcome section present). No
  `sprint-15.md` existed at that time. This sprint was originally sequenced as Sprint 15; a
  file-collision in the shared planning scratchpad was subsequently reported — a parallel PM task
  sequencing `DASH-005` also wrote to the same shared scratchpad filename `sprint-15.md` at nearly the
  same time, and its content is what ended up there. Per the coordinator's explicit instruction, **this
  file is renumbered to Sprint 16** throughout (title, sprint-goal self-reference, file-path
  self-references, and the Handoff section) — `DASH-005` retains Sprint 15. This renumbering is a
  scratchpad/collision-avoidance correction only; nothing about scope, sequencing, or dependency
  reasoning below changed as a result.
- `docs/product/backlog-economic-service.md`'s "Backtesting / historical simulation (new)" section
  read in full this session, including its own "Hard constraints carried into every story below" list
  (five items: no exchange integration, gated behind ECON-005 unmodified, no automation/robo/risk-tier
  language, retrospective/research-only framing, no fund custody) and its declined-request paragraph
  (a full automated trading system against a real exchange, explicitly declined outright, not narrowed
  into this backlog in any form).
- `docs/adr/0001-economic-service-scaffolding-only.md` and
  `docs/adr/0002-declined-automated-trading-product.md` read in full — both confirm this section is a
  narrow, deliberately-scoped extension of Sprint 13's already-closed inert-scaffolding posture, not a
  step toward a working trading tool. This framing is carried forward below unchanged, not softened.
- `services/economic-service/README.md` read in full (current, post-Sprint-13 state): confirms
  `check_economic_eligibility(result: UpstreamValidationResult, request: SimulationRequest) ->
  EligibilityDecision` is the real, live guard signature (not the ticket's original shorthand),
  `MockValidationResultClient` (`source="mock_fixture"` always) is the only DI-wired upstream client,
  and `UpstreamValidationResult.dm_verdict` is the real `DmVerdict = Literal["better", "worse", "no
  significant difference"]` type — corrected post-`ECON-005` per `docs/tickets/ECON-005.md`'s "Post-
  verification correction" section, which was also read directly. This sprint's stories reference
  `check_economic_eligibility`, `UpstreamValidationResult`, and `DmVerdict` by these real, current
  names/shapes, not the ticket's original (superseded) description.
- `docs/tickets/README.md`'s `services/economic-service (ECON-*)` section and `docs/sprints/
  sprint-13.md`'s Outcome section both confirm `ECON-001`–`ECON-006` are done, closed, Tech-Lead-
  verified — the precondition this new section's own source line states.
- Each of `ECON-012`/`ECON-013`/`ECON-014`'s own `Depends on:` line read directly, not inferred from
  priority or story number:
  - `ECON-012`: "Depends on: ECON-003, ECON-004, ECON-005." All three done (Sprint 13).
  - `ECON-013`: "Depends on: ECON-002, ECON-012." `ECON-002` done (Sprint 13); `ECON-012` is this
    sprint — `ECON-013` cannot start until `ECON-012` lands within this sprint.
  - `ECON-014`: "Depends on: ECON-006, ECON-012." `ECON-006` done (Sprint 13); `ECON-012` is this
    sprint, for the same reason stated in the backlog itself — "its doc-sync extension needs
    `ECON-012`'s files to exist to scan." `ECON-014` cannot start until `ECON-012` lands.
- File-overlap check between `ECON-013` and `ECON-014`, performed directly against each story's own
  acceptance criteria, not assumed from the task framing: `ECON-013` touches `src/app/models.py` (new
  `backtest_results` table), `src/app/repositories/` (new `BacktestResultRepository` Protocol +
  implementation), and a schema-level regression-test extension of `ECON-002`'s
  `test_no_profitability_columns.py`. `ECON-014` touches `README.md` (new "Backtesting (ECON-012/013)"
  section) and `scripts/check_profitability_language.py` (scanned-file-set extension to cover
  `ECON-012`'s router/contracts files and `ECON-013`'s model/repository files). No shared file target
  between the two: `ECON-014` only *names* `ECON-013`'s files as scan targets, it does not edit them.
  **Confirmed safe to parallelize once `ECON-012` lands.**
- No team size/velocity given. Sized against precedent: three stories, one strict two-stage dependency
  chain (`ECON-012` first) followed by one genuinely parallel pair — smaller and simpler than Sprint
  13's six-story build, closer in shape to Sprint 09's two-story dependency pair.

## Sequencing decision (stated explicitly, dependency-first, not by priority)

`ECON-012` is Should priority and `ECON-014` is Must priority — a naive priority-first read would put
`ECON-014` ahead of `ECON-012`. That would be wrong and is called out explicitly here, per this role's
own standing instruction to sequence by dependency, not silently reorder around priority: `ECON-014`'s
own `Depends on:` line names `ECON-012` directly, and its acceptance criteria require scanning files
(`ECON-012`'s batch router and contracts) that do not exist until `ECON-012` is built. `ECON-014`
cannot be pulled forward ahead of a Should-priority story it is blocked on. The reverse is not true:
nothing in `ECON-012`'s own acceptance criteria depends on `ECON-013` or `ECON-014`.

1. **`ECON-012`** [Should] — must run first; both `ECON-013` and `ECON-014` are blocked on it by their
   own stated dependencies, not merely by convenience sequencing.
2. **`ECON-013`** [Should] and **`ECON-014`** [Must] — both depend only on `ECON-012` (plus
   already-done `ECON-002`/`ECON-006`), are mutually independent per each one's own `Depends on:` line,
   and touch disjoint files per the file-overlap check above. **Run in parallel once `ECON-012` lands.**

Net order: `ECON-012` (Round 1, solo) → `ECON-013` and `ECON-014` in parallel (Round 2).

## Stories in scope, in execution order

1. `ECON-012` [Should, `economic-service`] — `POST /backtests`: bounded batch (`run_ids: list[str]`,
   `max_length=50`) applying `ECON-005`'s exact, unmodified `check_economic_eligibility` guard
   independently per run id, returning an ordered list of `EligibleSimulationResult`/
   `NotEligibleForSimulation` entries (both from `ECON-003`, unmodified), each tagged with its
   originating `run_id`. Batched equivalents of `ECON-005`'s four required tests (all-refused,
   live-but-not-significant refused, one-eligible-among-refused positive control, and the
   "every real call through the real running service returns an all-refused batch" proof). Depends
   on: `ECON-003`, `ECON-004`, `ECON-005` (all done, Sprint 13). Runs first; nothing else in this
   sprint can start before it.
2. `ECON-013` [Should, `economic-service`] — new `economic.backtest_results` table, storing exactly
   and only `ECON-012`'s eligible-branch rows, tagged `result_kind="retrospective_backtest"`; insert
   path reachable exclusively from inside `ECON-012`'s eligible branch (structural test, mirroring
   `ECON-005`'s "only reachable through the guard" discipline); extends (does not duplicate)
   `ECON-002`'s `test_no_profitability_columns.py` regression guard to cover the new table. Depends
   on: `ECON-002` (done), `ECON-012` (this sprint). Runs in parallel with `ECON-014` once `ECON-012`
   lands.
3. `ECON-014` [Must, `economic-service`] — README "Backtesting (ECON-012/013)" section stating the
   feature is inert today for the same two reasons the rest of the service is (`VS-017` unbuilt, no
   live outperformance result has ever existed); extends `ECON-006`'s
   `scripts/check_profitability_language.py` scanned-file set to cover `ECON-012`'s router/contracts
   files and `ECON-013`'s model/repository files; confirms `POST /backtests`'s OpenAPI `summary`/
   `description` use retrospective/hypothetical/research-only language by scanning the actual generated
   `/openapi.json`, not just docstring source. Depends on: `ECON-006` (done), `ECON-012` (this sprint).
   Runs in parallel with `ECON-013` once `ECON-012` lands.

## Stories explicitly deferred

- `ECON-015` (real exchange integration) — Won't, this backlog. Explicitly and permanently declined
  per `docs/adr/0002-declined-automated-trading-product.md` — not a scheduling deferral, a drawn line.
- `ECON-016` (automated, recurring, or "robo" execution) — Won't, this backlog. Every backtest in this
  section is a single, on-demand, manually-triggered call; no scheduler/daemon/background job is
  proposed or authorized by any story in scope.
- `ECON-017` (risk tiering or user-facing "investment" framing) — Won't, this backlog. Developer/
  analyst tooling only, matching `ECON-011`'s own precedent.
- `ECON-018` (mocked-wallet bookkeeping data structure) — Won't, this backlog, explicitly considered
  and declined even as a pure no-I/O data structure, per the backlog's own reasoning: it would read as
  the first piece of exchange-integration scaffolding once it exists alongside `ECON-012`'s run-id-
  driven batch iteration.

None of these four are reconsidered or reopened here — they are the Product Owner's own Won't calls,
recorded in the backlog and in `docs/adr/0002-declined-automated-trading-product.md`, carried forward
unchanged.

## Hard constraints carried into every story in this sprint (non-negotiable, restated from the
backlog, not softened)

1. **No real exchange integration, ever, in this sprint.** No Binance/crypto.com/any-venue API client,
   no order-placement logic, no wallet-connection code — mocked or otherwise.
2. **Gated behind `ECON-005`'s existing eligibility check, unmodified.** `check_economic_eligibility`
   is imported and called by `ECON-012`, never reimplemented, never altered. No eligible input exists
   anywhere on this platform today (`VS-017` unbuilt, per Sprint 13's own override note) — this
   sprint's feature is inert scaffolding today, not a working tool, exactly like Sprint 13's own
   deliverable.
3. **No "automatic," "robo," "risk tier," or "invest and win" language anywhere.** Single-run, on-
   demand, manually-triggered inspection only.
4. **Framing.** Every story's README/API-doc language states this computes a hypothetical,
   retrospective, cost/slippage-adjusted result for research purposes — never "returns," "profit," or
   "win" in a forward-looking or promotional sense.
5. **No custody of real or simulated user funds, no real wallet connection, nothing resembling a
   retail-facing financial product.** Developer/analyst tooling only.

## Definition of done for this sprint

- Every acceptance-criteria checkbox in `ECON-012`, `ECON-013`, `ECON-014`'s backlog entries is
  checked, not left implicitly assumed satisfied.
- `uv run pytest` (or this service's documented `.venv\Scripts\python.exe -m pytest -q` workaround,
  per its OneDrive-sync note) passes in `services/economic-service` with zero failures and zero
  regressions on the 50 tests already passing at Sprint 13's close, including: `ECON-012`'s four
  batched-equivalent tests (all-refused, live-but-not-significant-refused, one-eligible-among-refused
  positive control, all-real-calls-refused-through-the-real-service proof), `ECON-013`'s
  insert-path-unreachable-without-the-eligible-branch test and extended
  `test_no_profitability_columns.py`, and `ECON-014`'s extended `check_profitability_language.py`
  drift-detection test (fails when a forbidden word is injected into a new `ECON-012`/`ECON-013` file,
  passes once removed).
- `economic.*` schema, including the new `backtest_results` table, contains no column matching a
  live/forward-looking-claim naming pattern (`profit`, `win`, `expected_return`, `forecast_*`) anywhere
  — verified by the extended regression test passing, not by inspection alone.
- `services/economic-service/README.md` gains the "Backtesting (ECON-012/013)" section stating
  plainly: single-run/on-demand/manual, gated by the unmodified `check_economic_eligibility`, inert
  today for the same two reasons as the rest of the service, and no exchange integration/custody/
  investment-product framing anywhere in the feature.
- `docs/tickets/README.md`'s `services/economic-service (ECON-*)` section gains this sprint's three
  tickets; `docs/product/backlog-economic-service.md`'s own story statuses are left accurate.
- No code in this sprint touches `libs/naive_first_engine`, `libs/common`, `services/validation-service`,
  `services/gateway-api`, `services/ingestion-service`, `services/reporting-service`, or
  `services/dashboard-web` — all out of scope, exactly as Sprint 13 scoped itself.
- `ECON-015` through `ECON-018` remain unscheduled/unbuilt as stated above — this sprint does not
  start any of them.

### Non-negotiable verification requirement — restated from Sprint 13's own precedent, not diluted

Before this sprint can be marked complete, **the Tech Lead must personally confirm, by direct code
inspection — not by trusting a green checkmark or a dev agent's self-report** — that every one of this
backlog section's own five hard constraints still holds after this sprint's changes land:

1. **No exchange integration of any kind was added.** Grep the entire `services/economic-service/`
   tree (including this sprint's new files) for any Binance/crypto.com/venue-API-client import,
   order-placement logic, or wallet-connection code, mocked or real — confirm zero hits.
2. **`ECON-005`'s gate is unmodified.** Diff `src/app/eligibility.py`'s `check_economic_eligibility`
   against its Sprint-13-close state and confirm byte-for-byte (or semantically, if a mechanical
   refactor was genuinely necessary and separately justified) identical two-condition logic; confirm
   `ECON-012`'s batch handler imports and calls that exact function object per-run-id, never a parallel
   reimplementation.
3. **No automation language anywhere.** Re-run `ECON-014`'s extended
   `scripts/check_profitability_language.py` (or its automation-language equivalent, if a separate
   check was built) directly and confirm it passes against the actual shipped files, not a stale or
   partial file list.
4. **Correct framing preserved.** Read the new "Backtesting (ECON-012/013)" README section and
   `POST /backtests`'s actual generated `/openapi.json` output directly, confirming "hypothetical,"
   "retrospective," "research purposes" language is present and "returns"/"profit"/"win" in a
   forward-looking or promotional sense is absent.
5. **No fund custody.** Confirm no new file in this sprint's scope introduces a balance, position,
   wallet, or custody-shaped data structure of any kind — this was explicitly considered and declined
   as `ECON-018`; the Tech Lead confirms it was not quietly introduced under a different name inside
   `ECON-012`/`ECON-013`.

This verification is not routine QA and must not be folded into a general "tests passed" checkbox — it
is the same category of non-negotiable, personally-performed check Sprint 13 required for `ECON-005`,
applied here to this extension's own hard constraints.

## Handoff to Tech Lead

- **Sprint file**: `docs/sprints/sprint-16.md` (renumbered from an originally-sequenced Sprint 15 to
  Sprint 16 due to a shared-scratchpad file-collision with a parallel PM task's `DASH-005` sequencing,
  which retains Sprint 15 — place this content at `docs/sprints/sprint-16.md` in the repo).
- **Sprint goal**: `economic-service` gains a batch backtest endpoint (`POST /backtests`) and an
  eligible-only results table that reuse `ECON-005`'s existing, unmodified `check_economic_eligibility`
  gate across a bounded set of historical run ids — extending Sprint 13's inert-scaffolding posture,
  never adding new eligibility logic, exchange integration, or automated-execution capability.
- **Ordered story list**:
  1. `ECON-012` [Should] — batch backtest endpoint. Depends on `ECON-003`/`ECON-004`/`ECON-005` (all
     done). Runs first; blocks both stories below.
  2. `ECON-013` [Should] — eligible-only `backtest_results` persistence. Depends on `ECON-002` (done),
     `ECON-012` (this sprint). Runs in parallel with `ECON-014` once `ECON-012` lands.
  3. `ECON-014` [Must] — README/doc-sync extension. Depends on `ECON-006` (done), `ECON-012` (this
     sprint). Runs in parallel with `ECON-013` once `ECON-012` lands.
- **Dependency/risk notes**:
  - `ECON-014` is Must and `ECON-012` is Should, but `ECON-014` is hard-blocked on `ECON-012` by its
    own stated dependency and by needing `ECON-012`'s files to exist to scan — do not let priority
    tempt a reorder; `ECON-012` must land first regardless of priority label.
  - `ECON-013`/`ECON-014` file-overlap checked directly: `ECON-013` touches `models.py`/
    `repositories/`; `ECON-014` touches `README.md`/`scripts/check_profitability_language.py` and only
    *names* `ECON-013`'s files as scan targets, never edits them. Safe to delegate to two concurrent
    dev agents once `ECON-012` is done and verified — unlike Sprint 14's `GW-016`/`GW-018` pair, which
    this role deliberately serialized due to genuine same-file risk, no such risk exists here.
  - This entire section is an extension of Sprint 13's disclosed trigger-#11 override, not a new one —
    the same "inert until `VS-017` ships and a real outperformance verdict exists" framing applies
    unchanged. Do not let this get softened or reframed as "backtesting now works" anywhere in tickets.
  - The five hard constraints (no exchange integration, gate unmodified, no automation language,
    correct framing, no fund custody) are this sprint's own definition-of-done gate, restated above in
    full — treat the non-negotiable verification subsection as binding, not as boilerplate carried over
    from Sprint 13 for form's sake.
  - `ECON-012`'s four batched-equivalent tests are this sprint's `ECON-005`-equivalent highest-stakes
    deliverable — do not compress or treat any as satisfied by a partial subset when cutting tickets.
  - **Note on the renumbering itself**: this sprint's number changed (15 → 16) purely due to a
    scratchpad-write collision with a parallel PM task, resolved per the coordinator's explicit
    instruction. No scope, dependency, or sequencing content changed as a result — only the number and
    self-references to it.
