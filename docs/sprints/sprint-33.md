# Sprint 33 — Returns-vs-levels methodology audit (research/ greenlight, MR-001 only)

Sprint goal: a validation run submitted against raw, non-stationary price-level data is blocked (or
auto-transformed) before any Naive0 comparison executes, so the existing UI tooltip caveat becomes an
enforced methodology guarantee instead of an easily-missed hint.

Backlog source: `docs/product/backlog-model-research.md` — MR-001 only.

## Scope decision: MR-001 only, not the full MR-001–006 backlog

The user approved the full `backlog-model-research.md` (MR-001 through MR-006) with three explicit
constraints this sprint plan honors:

1. **`research/` is greenlit to start now.** `research/README.md` currently reads "Status: not
   started" — this sprint updates that status line as part of its own scope (see Definition of Done),
   not as a separate pass.
2. **Compute/time budget: keep it light — hours not days, no GPU/cloud spend, small/fast models
   only.** MR-001 involves no model training at all (it is an input-validation/methodology check), so
   it trivially satisfies this constraint. MR-002 through MR-006 all involve real feature-engineering
   or model-training work and are explicitly deferred to their own future sprint(s), sequenced after
   this one.
3. **No business urgency — normal priority alongside the rest of the currently open backlog**, not
   jump-the-queue urgent. This sprint schedules MR-001 as one normal-priority sprint among the
   session's other open work (the UAT-findings backlog, MDF-003, Sprint 32 close-out per
   `docs/tickets/README.md`) — it is pulled in now specifically because it is the lowest-risk, purely
   methodological, zero-model-training story, not because it jumps ahead of anything.

**MR-001 is also the backlog's own stated `Must`-priority, zero-dependency, first story** — the
backlog explicitly rationalizes it as protecting every later MR-002–006 research result from a known
false-positive artifact (comparing Naive0 on price levels instead of returns), which this session's
own test runs already demonstrated live. MR-004/005 explicitly list `Depends on: MR-001` in the
backlog itself, so taking MR-001 alone this sprint is a dependency-correct slice, not an arbitrary cut.

## Stories in scope, in execution order

1. **MR-001** — Returns-vs-levels methodology audit. No dependency (backlog: `Depends on: none`). Sole
   story this sprint.

## Stories explicitly deferred

- **MR-002** (engineered feature set: rolling volatility/return stats) — `Should`, no hard dependency
  on MR-001, but involves real feature-engineering code; deferred to keep this sprint's scope to the
  single zero-model-training story per the "keep it light" constraint. Backlog: `Depends on: none`.
- **MR-003** (multimodal fusion inputs bridge to MDF-003) — `Should`, explicitly blocked on MDF-003
  (a separate, already-scoped, not-yet-started backlog item) per the backlog's own text; cannot start
  regardless of this sprint's scope.
- **MR-004** (gradient boosting `Baseline` candidate) — `Should`, backlog: `Depends on: MR-001`. Real
  model-training work (LightGBM/XGBoost fit per split); explicitly out of scope this sprint both by
  the "keep it light" constraint and because it should only start once MR-001's enforcement exists to
  protect its own reported result from the levels-vs-returns artifact.
- **MR-005** (regime-sensitive/HMM candidate) — `Could`, backlog: `Depends on: MR-001, MR-004`. Doubly
  blocked (on MR-001 landing and on MR-004 establishing the research-to-report pipeline); not in scope.
- **MR-006** (per-split explainability artifacts) — `Could`, backlog: `Depends on: MR-004`. No
  candidate model exists yet to explain; not in scope.

No new scope beyond the approved backlog's six stories was pulled in or invented for this sprint.

## Dependency/sequencing note (module boundaries, implementation-plan.md sections 2 and 6)

MR-001 lives in an already-fired-trigger boundary: it is input validation, either inside
`services/validation-service` (trigger #3, live) before calling `naive_first_engine`, or as a new
precondition check inside `libs/naive_first_engine` itself (trigger #1, live) — the backlog's own
acceptance criteria requires an explicit, documented decision between these two, respecting
`libs/naive_first_engine/README.md`'s "owns/does not own" boundary, before implementation starts. The
backlog is explicit that this must not change `naive_first_engine`'s public `Baseline`/
`generate_splits`/`dm_test` signatures regardless of which module the check lands in. The existing UI
tooltip lives in `services/dashboard-web` (trigger #8, live) — `run_new.html` — and per the backlog is
not removed, only backed by the new enforced check. No `research/` code is touched by this sprint;
`research/`'s only in-scope change is its own `README.md` status line (see Definition of Done).

## Definition of done for this sprint

- A documented decision (ADR or ticket Design section) states explicitly whether the stationarity/
  level-detection check lives in `services/validation-service`'s input validation or as a new
  precondition inside `libs/naive_first_engine`, with the "owns/does not own" boundary reasoning shown,
  not just asserted.
- A stationarity/level-detection check (e.g. ADF test or a simpler heuristic) exists with a unit test
  proving it flags a synthetic non-stationary (price-level-like) series and passes a synthetic returns
  series.
- The existing `run_new.html` tooltip is retained (not removed) and is now backed by the enforced
  check, not advisory text alone — a run submitted on detected price levels is rejected or
  auto-transformed, not silently allowed through with only a hint.
- No change to `naive_first_engine`'s public `Baseline`/`generate_splits`/`dm_test` signatures.
- `research/README.md`'s status line is updated from "Status: not started" to reflect the user's
  explicit greenlight this sprint — while making clear no model-class research work has started yet
  (that remains future-sprint scope: MR-002 through MR-006, not opened by this update).
- No MR-002 through MR-006 work (no feature-engineering code, no candidate `Baseline` model, no model
  training of any kind) is present in this sprint's diff.
- Whichever service's README owns the new check (`validation-service` and/or `naive_first_engine`,
  and `dashboard-web` for the tooltip-to-enforcement change) is updated in the same pass that ships the
  code, not a separate pass, per this platform's standing documentation discipline.
- Full test suite(s) for every touched module re-run with zero regressions.
- QA gate (`qa` subagent / `/qa-validation`) run after MR-001's ticket(s) are implementation-complete,
  before this sprint is signed off — this platform's now-mandatory, standing gate.
