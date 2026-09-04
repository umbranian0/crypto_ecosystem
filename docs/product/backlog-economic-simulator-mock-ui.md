# Backlog — economic simulator mock UI (deposit / wallet-connect / staking, mock-only)

Source: `CLAUDE.md` (Product positioning; `services/economic-service` folder-layout bullet — deferred,
trigger #11, "never claim profitability before that"), `docs/da-tese-ao-produto.md` sections 1.5/2.3.5/2.6/2.7,
`docs/adr/0001-economic-service-scaffolding-only.md`, `docs/adr/0002-declined-automated-trading-product.md`,
`services/economic-service/src/app/eligibility.py` (`check_economic_eligibility`, the real code gate),
`services/economic-service/src/app/contracts.py` / `upstream_client.py` (`UpstreamValidationResult`,
`DmVerdict = Literal["better", "worse", "no significant difference"]`), `services/economic-service/README.md`
(current scope/status — scaffolded, inert, trigger #11 not fired), `docs/product/backlog-economic-service.md`
(prior stories ECON-001–ECON-017, and specifically **ECON-008** and **ECON-018**, both read in full — see
"Reconciliation" below, this is not a fresh read of an empty slate), `services/dashboard-web/README.md`
(existing session-gated, downstream-proxying UI pattern this backlog's UI stories reuse rather than invent).

Scope: a mock deposit/wallet-connection/staking presentation layer, sitting on top of
`economic-service`'s **existing, unmodified** `check_economic_eligibility` gate, surfaced through
`dashboard-web` (this platform's one existing tenant-facing UI, session-gated, HTMX/Jinja2, proxying
downstream services via `gateway-api` — no new UI service invented). Out of scope, permanently, not
just for this backlog: any real payment rail, any real wallet-connection protocol (WalletConnect,
MetaMask, or equivalent), any real exchange API integration, any change to `check_economic_eligibility`
itself, and any "preview" or "simulate anyway" path that executes a mock trade without that gate's
real `source == "live"` and `dm_verdict == "better"` conjunction passing first.

## Reconciliation with `docs/product/backlog-economic-service.md` — read before sequencing this

This request is not a green-field addition. Two stories in the existing `economic-service` backlog
directly precede it and must be explicitly reconciled, not silently overridden:

1. **ECON-018 — "Won't (explicitly considered and declined): mocked-wallet bookkeeping data
   structure."** That story considered, on essentially identical terms, a *pure bookkeeping* record
   (starting balance, position size over simulated time) and declined it — not because bookkeeping
   itself is unsafe, but because "even a purely internal, no-I/O data structure risks reading, to a
   future contributor, as the first piece of exchange-integration scaffolding," especially once it
   sits next to `ECON-012`'s run-id-driven batch iteration. ECON-018's own text is explicit about how
   to reopen it: *"If a future ticket genuinely needs this, it should be proposed and reviewed on its
   own terms, with the 'pure bookkeeping, not integration surface' distinction re-stated and
   re-confirmed at that time by whoever authorizes it — not introduced quietly inside this narrower
   extension."* This backlog **is** that future ticket, proposed openly, not quietly folded into
   `ECON-012`'s scope. Every mock-balance/mock-wallet/mock-position story below carries the same
   "pure bookkeeping, zero I/O, zero real-venue reachability" discipline ECON-018 asked for, and I am
   flagging — not silently deciding — that this requires an explicit re-authorization from whoever
   owns that boundary before PM sequencing, exactly as ECON-018 itself instructs.
2. **ECON-008 — "Won't: UI / `dashboard-web` integration."** Declined at the time because
   "a UI surface for a service that cannot yet return a real number would itself risk implying
   eligibility that doesn't exist." That risk has not gone away — `economic-service` is exactly as
   inert today as it was when ECON-008 was written (no `VS-017`, no live outperformance result,
   `MockValidationResultClient` is still the only DI-wired upstream client). What has changed is the
   request itself now specifies, in detail, how to build the UI so the inert/eligible split is the
   centerpiece of the UX rather than something the UI glosses over (Epic C below). I am treating this
   backlog as a proposal to reopen ECON-008 under that narrower, honesty-first framing, not as
   evidence the original objection was wrong — same flag as above.
3. **ECON-017 — "Won't: risk tiering or user-facing 'investment' framing... no signup flow through
   which a retail user could hand this platform money or a wallet connection."** This backlog's
   scope is explicitly narrower than what ECON-017 declined: no signup flow, no real money, no real
   wallet connection ever — every story below is mock bookkeeping behind a `dashboard-web` session
   that already requires authentication for other reasons (run submission, monitoring). It does not
   reopen ECON-017's actual concern (a retail product where a real user hands over real money or a
   real wallet), and no story here should be read as doing so.

**None of the above blocks writing this backlog** — the requester asked for it explicitly, in detail,
having read ADR-0002 and framed this as ADR-0002's own accepted narrower alternative. But ADR-0002's
accepted alternative was `ECON-012`–`ECON-014` (batch backtesting behind the existing gate) — it did
**not** include a wallet/deposit UI; that piece (ECON-018) was separately proposed and separately
declined in the same sprint. This backlog is therefore best understood as a **new, explicit
reauthorization request against ECON-018 and ECON-008 specifically**, not a restatement of an already-
settled decision. **I am flagging this plainly for the requester/PM to confirm before sequencing**,
per ECON-018's own re-opening instructions — see "Open questions" at the end of this document.

## Transaction-cost/slippage modeling — checked in code, not assumed

`services/economic-service/src/app/eligibility.py`'s `compute_economic_simulation` today implements
**placeholder arithmetic only**: a hardcoded `total_cost_bps = 10.0` flat constant, subtracted once
from `result.dm_statistic`. Its own docstring says this outright: *"The cost/slippage computation
itself is intentionally trivial placeholder arithmetic — this ticket's scope is the structural gate,
not a real cost/slippage model (that is Strategy-shaped future work per the Design section)."* There
is no fee-schedule-driven, slippage-curve-driven, or turnover-sensitive computation anywhere in the
running code today, even though `ECON-002`'s schema already has `fee_schedules`/`slippage_models`
input tables waiting for one. **This materially scopes Epic C below**: the UI must disclose the
current cost/slippage figure as a fixed, documented simplification (flat 10bps), not as a realistic
cost model — anything stronger would misrepresent what the backend actually computes.

## Where this UI lives (architecture note, not a story — PM/Tech Lead confirms placement)

`dashboard-web` is this platform's one existing tenant-facing, session-gated UI (FastAPI + HTMX/Jinja2,
proxying downstream services through `gateway-api`, never importing another service's code directly —
`CLAUDE.md`'s module-boundary rule). Every story below assumes new `dashboard-web` routes/templates
that call `economic-service`'s existing `POST /simulations` / `POST /backtests` (via `gateway-api`,
matching `runs.py`'s established `_call_downstream` pattern) for the eligibility-gated pieces, and a
new, `dashboard-web`-owned (or a new small `economic-service`-owned — implementer's call, not
prejudged here) bookkeeping store for the purely mock deposit/wallet/stake records that have no
upstream counterpart at all. No story below re-implements or approximates `check_economic_eligibility`
anywhere in this new surface — every eligibility-dependent screen calls the real endpoint and renders
its real response.

## Priority scheme

MoSCoW, same as this repo's other module backlogs, paired with a one-line rationale per story tied to
(a) whether the story is reachable/valuable *before* ECON-018/ECON-008 are explicitly re-authorized,
and (b) the module's existing gated posture and trigger-based build order.

---

## Epic A — Mock deposit / mock wallet setup

### ECOSIM-001 — Set a mock starting balance (fiat and/or mock crypto holding) [Must]
**As** a tenant using the mock simulator, **I want** to set a fake starting balance (a fiat amount
and/or a mock crypto holding, e.g. "10,000 mock USD" / "0.5 mock BTC"), **so that** I have a bookkeeping
baseline to allocate toward staking a validated model+dataset combination in Epic B.

Acceptance criteria:
- [ ] A `dashboard-web` form lets a logged-in tenant record a starting balance: an amount, a currency/
      asset label, and an explicit, un-editable-by-the-tenant `is_mock: true` flag persisted alongside it.
- [ ] The balance record is a pure bookkeeping row (tenant_id, asset label, amount, created_at) with
      **zero** columns or fields resembling a payment reference, transaction id, card token, or any other
      real-payment-rail concept — mirrors `ECON-002`'s "no profitability-output-shaped column" schema
      test discipline, applied here to "no real-payment-shaped column."
- [ ] UI copy states plainly, adjacent to the form, in at least one full sentence: "This is a simulated
      balance for backtesting purposes only. No real money is deposited, held, or at risk."
- [ ] No code path in this story calls, imports, or configures any real payment processor, bank rail,
      or cryptocurrency deposit address of any kind — verified by the same AST/grep-based structural-check
      discipline `ECON-004`/`ECON-005` already use elsewhere in this platform (no `stripe`, `plaid`,
      on-chain address-generation, or equivalent import anywhere in this feature's code).
- [ ] Setting a balance never computes or displays any profitability/return figure — this story has no
      dependency on `check_economic_eligibility` at all, by design (bookkeeping only).

Rationale for priority: Must — every later story in Epics B/C/D needs a starting balance to allocate
or display against; this is the load-bearing bookkeeping primitive ECON-018 asked to see re-proposed
explicitly, and it is the cheapest possible version of it (no wallet-connect concept yet).
Depends on: none (pending the ECON-018 reauthorization flagged above).

### ECOSIM-002 — "Connect" a mock wallet (UI concept only, explicitly labeled) [Must]
**As** a tenant, **I want** a "connect wallet" UI affordance that establishes a mock wallet association
for my tenant, **so that** the staking UI in Epic B has a wallet-shaped concept to allocate from, without
implying any real wallet-connection protocol exists.

Acceptance criteria:
- [ ] A single button/flow labeled "Connect mock wallet" creates a bookkeeping record (tenant_id, a
      generated mock address/label string, `is_mock: true`) — no real cryptographic keypair, no real
      chain address derivation, no signature request of any kind.
- [ ] Adjacent UI copy states plainly, verbatim or materially equivalent: "This is a mock wallet concept
      for simulation purposes only. It does not use WalletConnect, MetaMask, or any real wallet-connection
      protocol, and cannot send, receive, or hold real funds." This exact disclosure is a required,
      tested string in the rendered template (mirrors `ECON-006`'s doc-sync-check precedent: a test
      asserts the string's presence, not just that a human wrote it once).
- [ ] No code path in this story imports, calls, or references any real wallet SDK, RPC endpoint,
      chain-explorer API, or key-management library — verified by the same import-scanning structural
      test style ECON-004/ECON-005 use for their own "never a real integration" guarantees.
- [ ] "Disconnect mock wallet" removes the bookkeeping record; no residual real-looking artifact (address,
      balance) survives disconnection.

Rationale for priority: Must — Epic B's "stake from a wallet" framing needs this concept to exist, and
the explicit-labeling requirement is the single highest-risk copy surface in this whole backlog (most
likely place a user could mistake mock for real) — get the disclosure right at the same time as the
feature, not as a follow-up.
Depends on: ECOSIM-001 (same reauthorization gate; independent bookkeeping otherwise).

### ECOSIM-003 — Mock balance/wallet bookkeeping schema, isolated from `economic.*`'s existing tables [Must]
**As** the platform's data-access layer, **I want** the new mock-balance/mock-wallet records to live in
their own clearly-labeled tables (or a clearly-labeled `dashboard-web`-owned store), never mixed into
`economic.fee_schedules`/`slippage_models`/`simulation_configs`, **so that** `ECON-002`'s existing
"inputs-only, no profitability-output-shaped column" schema regression guard continues to mean what it
already says, and this new bookkeeping surface gets its own, equally explicit regression guard.

Acceptance criteria:
- [ ] New tables (e.g. `mock_balances`, `mock_wallets`, both `tenant_id`-scoped) are additive, not
      inserted into any existing `economic.*` table `ECON-002` already defined.
- [ ] A schema-level regression test (mirroring `ECON-002`'s `test_no_profitability_columns.py` pattern,
      extended or duplicated with the same documented substring-matching approach) asserts these new
      tables carry **zero** columns shaped like a computed profitability/return/P&L figure — a mock
      balance is an input a tenant typed in, never a computed output, and must never be confusable with
      one at the schema level.
- [ ] Repository interface for these tables is a `typing.Protocol`, `tenant_id`-first, zero `sqlalchemy`
      import in the interface module — same shape as `EconomicInputRepository` (`ECON-002`), not a new
      pattern invented for this feature.
- [ ] Tenant-isolation test: two tenants, cross-tenant read of a mock balance/wallet returns nothing —
      same discipline as every other tenant-scoped table on this platform.

Rationale for priority: Must — without an explicit, separately-guarded schema, mock bookkeeping records
risk drifting into the same table space `ECON-002` deliberately kept output-free; this is the structural
guarantee that ECOSIM-001/002's disclosure promises stay true at the data layer too.
Depends on: ECOSIM-001, ECOSIM-002.

---

## Epic B — Staking / position setup

### ECOSIM-004 — Browse validated model+dataset combinations available to stake toward [Should]
**As** a tenant, **I want** to see a list of model+dataset combinations that have a `validation-service`
run on file (whatever their verdict), **so that** I can choose which one to express a staking intent
toward, before finding out (Epic C) whether that combination is actually eligible for a real backtest.

Acceptance criteria:
- [ ] The list is fetched from `validation-service`'s existing `GET /runs`-style endpoint (via
      `gateway-api`, same `_call_downstream` pattern `dashboard-web`'s `runs.py` already uses) — no new
      run-listing logic invented, no direct DB read of another service's schema.
- [ ] Each list entry shows the model/dataset label and, if already known without an extra call, whether
      it has ever produced a "better" DM verdict — but this list view **never** computes or implies a
      profitability figure; it is a picker, not a results screen (that's Epic C).
- [ ] UI copy near the list states that "eligibility for a cost/slippage-adjusted simulation is
      determined separately, after staking, and most model/dataset combinations on this platform have
      not beaten the naive benchmark" — sets the expectation before the tenant commits to a choice.
- [ ] No mock trade, balance change, or profitability number is computed or displayed on this screen.

Rationale for priority: Should, not Must — Epic B is meaningfully usable with a manually-entered
run/model identifier (a plain text field) as an MVP fallback if this browsing UI slips; the honest-
expectation-setting copy is the load-bearing part, not the polish of a rich picker.
Depends on: ECOSIM-001 (needs a balance to stake from), existing `validation-service` `GET /runs`.

### ECOSIM-005 — Allocate a mock stake toward a chosen model+dataset combination [Must]
**As** a tenant, **I want** to allocate some amount of my mock balance toward a specific model+dataset
combination (identified by its `validation-service` run id), **so that** I can express intent to
simulate following that model's already-audited signal, without that allocation itself executing any
trade or requiring the underlying model to be eligible yet.

Acceptance criteria:
- [ ] Allocating a stake creates a bookkeeping record (tenant_id, mock_balance reference, run_id,
      staked_amount, created_at) — a pure record of intent, structurally identical in spirit to
      `SimulationConfig`'s "references an upstream run by opaque string id, never a foreign key into
      `validation-service`'s schema" rule (`ECON-002`).
- [ ] Staking an amount **decrements the mock balance's available amount by bookkeeping only** — no real
      transfer, no lock against a real account, no interaction with any payment or custody system.
- [ ] Staking a run id that has never been evaluated at all is allowed (the eligibility check happens at
      simulation time, Epic C, not at staking time) — staking itself makes no eligibility claim.
- [ ] UI copy states: "Staking records your intent to simulate this model's historical signal. It does
      not buy, sell, or hold any real or mock asset by itself — see your position's simulation status
      below for whether a backtest is actually available."
- [ ] No code path in this story calls `check_economic_eligibility` or displays any profitability figure
      — staking is purely a bookkeeping precondition for Epic C, never a simulation trigger by itself.

Rationale for priority: Must — this is the connective tissue between Epic A's balance and Epic C's
gated simulation; without it there is no "position" for Epic C to evaluate.
Depends on: ECOSIM-001, ECOSIM-003, ECOSIM-004 (or its text-field fallback).

### ECOSIM-006 — View and unstake existing mock positions [Should]
**As** a tenant, **I want** to see my current staked positions and unstake (return the amount to my
mock balance), **so that** I can manage my mock allocations over time without needing developer/DB
access.

Acceptance criteria:
- [ ] A positions list shows each stake's run id, amount, created_at, and current simulation status
      (a plain-language pointer to Epic C's eligible/not-eligible state, not a re-derivation of it).
- [ ] "Unstake" reverses ECOSIM-005's balance decrement by the same bookkeeping-only mechanism — no
      real transfer, no interaction with any external system.
- [ ] Unstaking a position that was eligible and had simulated buy/sell events (Epic C/D) does not
      delete the historical record (Epic D) — it only stops future simulation from being computed
      against it going forward.

Rationale for priority: Should — valuable UX completeness, but a tenant can get by with staking once
and viewing Epic D's history without an edit/unstake flow for an initial release.
Depends on: ECOSIM-005.

---

## Epic C — The eligibility-gated simulation itself

### ECOSIM-007 — "Not eligible for simulation yet" state (the expected, common-case outcome) [Must]
**As** a tenant with a staked position, **I want** a clear, honest screen explaining that my position's
underlying model+dataset does not currently have a real, significant "better" DM verdict on file, **so
that** I understand why no backtest is shown, in plain language tied to the actual audit result — not a
vague error and not a fake placeholder trade.

Acceptance criteria:
- [ ] The screen is rendered from `economic-service`'s real `POST /simulations` (or `POST /backtests`)
      response — specifically, `NotEligibleForSimulation`'s `reason_code`/`message`/`upstream_verdict`
      fields, called via `gateway-api`, exactly as that endpoint already returns them. No client-side
      re-derivation of eligibility; `check_economic_eligibility` is called exactly once, server-side,
      inside `economic-service`, and its response is rendered as-is.
- [ ] The two distinct refusal reasons `EligibilityReason` already distinguishes
      (`NO_REAL_UPSTREAM_RESULT` vs. `UPSTREAM_RESULT_DID_NOT_BEAT_NAIVE`) render as two distinct,
      plain-language messages — e.g. "This model+dataset combination has not yet been evaluated against
      the naive benchmark" vs. "This model+dataset combination was evaluated and did not beat the naive
      benchmark with statistical significance" — not one generic "not eligible" string that collapses
      the distinction the backend already computed.
- [ ] Where `upstream_verdict` is present, the screen shows the real `dm_statistic`/`dm_pvalue`/
      `dm_verdict` values it carries (evidence, not a computed output) — consistent with `contracts.py`'s
      own documented reasoning for why this field doesn't violate `NotEligibleForSimulation`'s
      "zero numeric fields at the top level" rule.
- [ ] This screen is the one every real staked position renders today, and this story's acceptance
      criteria explicitly say so: given the platform's core finding (no model has beaten naive in a
      stable way at any horizon; `MockValidationResultClient` is `economic-service`'s only DI-wired
      upstream client), test coverage must include an end-to-end assertion that a freshly staked,
      real position renders this "not eligible" screen through the real running services, not a mocked
      test double standing in for them.
- [ ] No profitability figure, mock trade, or placeholder number of any kind appears on this screen —
      verified the same way `ECON-005`'s Test 1 verifies it (iterating actual rendered output, not just
      checking that *a* page loaded).

Rationale for priority: Must — per the requester's own framing, this is the expected, correct outcome
for the overwhelming majority of real usage, not an edge case; a good UX here is this epic's actual
deliverable, not a fallback state for a "real" eligible screen to eventually replace.
Depends on: ECOSIM-005 (a staked position must exist to evaluate), existing `economic-service`
`POST /simulations`/`POST /backtests` and `check_economic_eligibility` (unmodified).

### ECOSIM-008 — Eligible-branch backtest simulation display (the rare case) [Must]
**As** a tenant whose staked position's model+dataset has a real "better" DM verdict on file, **I want**
to see what following that model's historical signal would have done to my mock balance, **so that**
I can inspect a real, cost/slippage-adjusted retrospective simulation — clearly separated from any
claim that the underlying statistical edge implies future profitability.

Acceptance criteria:
- [ ] This screen renders only when `economic-service`'s real response is `EligibleSimulationResult` —
      the same server-side call as ECOSIM-007, same single call to `check_economic_eligibility`, just
      the other branch of its already-existing tagged result. No second, UI-side eligibility check.
- [ ] The screen displays the reporting-service's existing mandatory disclaimer, verbatim or materially
      identical: *"This audit evaluates statistical forecast accuracy only. No transaction costs,
      slippage, execution, or position sizing were modeled unless the client separately commissioned the
      economic module (Subsystem 5). A model that beats naive statistically may still be unprofitable
      after costs, and vice versa is not implied either."* — reused, not re-authored, per this repo's
      "keep code/copy DRY, extract don't duplicate" rule; a test asserts this exact string (or the shared
      constant it's extracted into) is present.
- [ ] The screen additionally, explicitly discloses the cost/slippage-modeling scope gap found in code
      for this backlog: *"The cost/slippage figure shown here uses a fixed, simplified assumption (a flat
      10 basis-point cost), not a fee-schedule- or slippage-curve-driven model. Treat this as illustrative,
      not a realistic execution-cost estimate."* — required, tested string, so the UI never overstates
      what `compute_economic_simulation` actually computes today.
- [ ] All displayed figures (`cost_adjusted_return`, `slippage_adjusted_return`, `total_cost_bps`) are the
      exact values `EligibleSimulationResult` returned — no client-side recomputation, rounding-induced
      reinterpretation, or additional derived "profit" figure invented in the UI layer.
- [ ] Because this branch cannot be reached through the real running platform today (no `VS-017`, no live
      outperformance result — `economic-service` README's own standing disclosure), this story's own test
      suite must exercise this screen against a hand-constructed eligible fixture in an isolated test, with
      an explicit test docstring stating that this path is not reachable through the real deployed service
      today — mirroring `ECON-005` Test 3's own required framing, applied here to the UI layer.
- [ ] Framed throughout as a retrospective backtest ("would have," past tense, historical window shown) —
      never present tense, never "will," never "recommended," matching `ECON-014`'s existing "hypothetical /
      retrospective / research purposes" language rule.

Rationale for priority: Must, ranked alongside ECOSIM-007 rather than below it — a "not eligible" screen
without a credible eligible-branch counterpart risks reading as if the eligible path is unfinished or
faked; both branches of the same gate must be built and tested together for either to be trustworthy.
Depends on: ECOSIM-007 (shares the same call site), existing `EligibleSimulationResult` shape.

### ECOSIM-009 — Reuse the real gate exclusively; structural non-bypass guarantee [Must]
**As** the platform's own ethical boundary made real in this new UI surface (not just documented), **I
want** a structural guarantee that no code path in this feature can compute, approximate, cache-and-
reuse-past-invalidation, or otherwise produce a profitability figure without a fresh, real call to
`check_economic_eligibility` returning the eligible branch, **so that** this UI cannot become a second,
softer, or bypassable version of `ECON-005`'s existing gate.

Acceptance criteria:
- [ ] A structural test (AST-based or equivalent, mirroring `ECON-005`'s own "route handler never imports
      `compute_economic_simulation` directly" test) asserts that no `dashboard-web` module in this feature
      imports or references `compute_economic_simulation`, `EligibilityReason`, or any economic-service
      internal module directly — every eligibility-dependent screen goes through `economic-service`'s real
      HTTP API (via `gateway-api`), exactly as `implementation-plan.md`'s "no service imports another
      service's code" rule already requires platform-wide, with zero special-casing for this feature.
- [ ] No caching layer in this feature persists an `EligibleSimulationResult` for longer than the
      individual page render that fetched it, without also re-verifying eligibility on next display —
      explicitly ruling out a "cache the eligible answer so it still shows after the underlying verdict
      changes" failure mode.
- [ ] No "preview," "demo," "sandbox," or "what if I ignore eligibility" mode exists anywhere in this
      feature's routes, query parameters, or feature flags — verified by an explicit negative test that
      no such route exists in the built `dashboard-web` app's route table.
- [ ] Code review checklist item (documented in this story, verified structurally where feasible) confirms
      no story in this backlog was implemented in a way that reintroduces the loose `startswith()` /
      invented-vocabulary bug this platform already found and fixed once in `ECON-005`'s own history —
      any string comparison against a DM verdict anywhere in this new UI code must use the same
      `DmVerdict` `Literal` type `economic-service` already defines, never a locally re-typed string.

Rationale for priority: Must — this is this backlog's own equivalent of `ECON-005`'s "actual point"
framing; every other story in Epic C is only trustworthy if this one holds.
Depends on: ECOSIM-007, ECOSIM-008.

### ECOSIM-010 — Won't: any bypass, preview, or "simulate anyway" path [Won't, this backlog]
Not proposed, and explicitly named as a boundary rather than an oversight. No story in this backlog
authorizes a code path that computes or displays a profitability figure, mock trade, or "what would
happen if this model were eligible" preview without `check_economic_eligibility`'s real conjunction
(`source == "live"` and `dm_verdict == "better"`) actually passing. This is the direct UI-layer
restatement of `ECON-005`'s own binding refusal condition and of the task instruction that authored
this backlog: no loosening, no softening, no route around the gate, ever.

---

## Epic D — Mock transaction / position history view

### ECOSIM-011 — History of mock deposits and stakes [Should]
**As** a tenant, **I want** to see a chronological record of my mock balance deposits and stake
allocations/unstakes, **so that** I can audit my own simulated bookkeeping activity over time.

Acceptance criteria:
- [ ] History is assembled from ECOSIM-001/003/005/006's existing bookkeeping tables — no new
      profitability-shaped data invented for this view.
- [ ] Every entry is labeled with its true nature ("mock deposit," "stake allocated," "stake returned")
      — never a generic "transaction" label that could read as a real financial transaction record.
- [ ] Page-level copy states: "This is a record of your simulated activity on this platform. It is not
      a bank statement, brokerage record, or record of any real financial transaction."

Rationale for priority: Should — valuable for trust/transparency but not required for Epic A/B/C's
core loop to be usable in an initial release; a tenant can inspect current state without full history.
Depends on: ECOSIM-001, ECOSIM-005, ECOSIM-006.

### ECOSIM-012 — History of simulated buy/sell events, framed explicitly as a backtest record [Must]
**As** a tenant with an eligible staked position, **I want** to see the simulated buy/sell events that
made up that position's historical backtest, **so that** I can inspect the simulation's own record
without mistaking it for a log of real trading activity.

Acceptance criteria:
- [ ] This view renders **only** for positions currently in `EligibleSimulationResult`'s branch
      (ECOSIM-008) — a position in `NotEligibleForSimulation`'s branch shows zero simulated events, not
      an empty-but-implying-pending list; the absence itself is explained by a link back to ECOSIM-007's
      "not eligible" explanation, not left as an unexplained blank state.
- [ ] Every listed event is labeled "simulated" and dated within the historical backtest window — never
      labeled with present/future-tense language ("executing," "pending," "live") anywhere in this view.
- [ ] If `ECON-013`'s `backtest_results` persistence exists and has a row for this position, this view
      reads from it (reuse, not reinvention); if not, this view computes the same on-demand call
      ECOSIM-008 already makes and displays that response directly — either way, the event list is
      always a direct rendering of `economic-service`'s real gated output, never a UI-invented list of
      hypothetical trades.
- [ ] Page-level copy states, adjacent to the event list: "These are retrospective, backtested events
      computed from historical data. No real or mock trade was executed by this platform in real time,
      and no future trade is scheduled or implied."

Rationale for priority: Must — this is the concrete deliverable the "mock transaction/position history"
requirement actually asks for on the eligible branch; without it, Epic C's eligible-branch screen has
no historical detail behind its headline numbers.
Depends on: ECOSIM-008, optionally `ECON-013` (`backtest_results` persistence, Should-priority upstream).

---

## Open questions for the requester/PM before this goes to sequencing

1. **ECON-018/ECON-008 reauthorization.** This backlog reopens two explicitly-declined prior decisions
   (mock-wallet bookkeeping, and dashboard-web UI over economic-service). ECON-018's own text requires
   this to be "proposed and reviewed on its own terms" by whoever authorizes it — I've written the
   stories, but I have not treated their mere existence in this file as that reauthorization having
   already happened. Please confirm explicitly before PM sequencing treats these stories as approved.
2. **Where the mock bookkeeping store lives** (a new `dashboard-web`-owned schema vs. a new,
   additive corner of `economic-service`'s own schema) is left to the Tech Lead/PM per the
   "architecture note" above — I did not prejudge it, since either choice satisfies every constraint
   in this backlog and it's an implementation decision, not a product one.
3. **Whether Epic D's simulated buy/sell event granularity should come from `ECON-013`'s persisted
   `backtest_results` table or be computed on demand** is flagged in ECOSIM-012 as an either/or; if
   `ECON-013` isn't prioritized ahead of this backlog, ECOSIM-012's on-demand fallback should be
   treated as the real MVP path, not a degraded one.

## Prioritization recommendation relative to the rest of the pipeline

This backlog should **not** be slotted "next" ahead of `docs/product/backlog-run-analysis-visualization.md`
(Sprint 26, mid-implementation) — interrupting in-flight work to insert a new feature is a cost this
backlog's own content doesn't justify: every Must story here is, by the platform's own core finding,
expected to render its "not eligible" state for the overwhelming majority of real usage, which means
this feature's business value today is almost entirely UX/trust-building, not unlocking a capability
tenants are blocked on. I recommend sequencing this **after** Sprint 26 completes, and evaluated
alongside — not automatically ahead of — `docs/product/backlog-crawl-lifecycle-control.md`'s Sprint 24
(sequenced, not started): Sprint 24 has no open policy question blocking it, while this backlog does
(item 1 above). My recommendation is: resolve the ECON-018/ECON-008 reauthorization question first
(cheap, a single explicit confirmation), and only then have the PM decide this backlog's slot relative
to Sprint 24 on ordinary priority/value grounds — I'm not aware of a reason it must go strictly before
or after Sprint 24 on product-value grounds alone.
