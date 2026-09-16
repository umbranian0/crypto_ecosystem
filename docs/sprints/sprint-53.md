# Sprint 53 — `research/`: GRU sequence-model candidate (MR-015)

Sprint goal: the last untested model class in the thesis's future-work list (GRU) gets implemented as a
`Baseline` candidate, run against MR-012's real `binance_btcusdt_1h` window at 1h/6h/24h under the unmodified
leakage-safe protocol, and its outcome — beat or no-beat Naive0 — honestly documented.

Backlog source: `docs/product/backlog-model-research.md`, "Extension: GRU sequence-model candidate (MR-015)"
section — single story, MR-015.

## Sequencing note: single-story sprint, no parallel tracks

Unlike Sprint 52 (MR-012/MR-013 parallel tracks), this sprint has exactly one story. No pairing/ordering
decision is needed.

## Pre-read findings

- `docs/product/backlog-model-research.md`'s MR-015 entry read in full (its own "Extension: GRU sequence-model
  candidate" header and the story itself).
- MR-015's stated dependencies — MR-004, MR-005 (`Baseline`/report-shape precedent), MR-008/MR-009 (real-data
  pipeline), MR-012 (widened real-data window/loader reused directly), MR-013 (most recent `Baseline`
  precedent) — are all done (Sprints 41, 42, 47, 52).
- This MR-015 entry exists because the user explicitly signed off this session on adding `torch`, overriding
  Sprint 52's recorded deferral decision. That deferral record stands unchanged as accurate history of what
  was decided when; this sprint acts on the override, it does not silently contradict the prior record.
- Module boundary: this sprint lives entirely inside `research/` (plus `research/pyproject.toml`,
  `research/README.md`, and `docs/product/backlog-model-research.md` status updates) — no
  `libs/naive_first_engine` change, no `services/validation-service`/`ingestion-service` code change. Consistent
  with every prior MR-* story's module scope and with `docs/implementation-plan.md` section 2's boundary map.

## Compute ceiling — restated, binding on the Tech Lead

Per MR-015's own acceptance criteria: hidden size ≤ 32 units, epoch count ≤ 20, input sequence-window length
≤ 24 timesteps — these are upper bounds the Tech Lead must set to exact fixed numbers, not a range to search
over (no hyperparameter search). CPU-only, no GPU/CUDA path exercised. Measured wall-clock runtime for the
full run is reported in the ticket, targeting under 5 minutes, matching MR-004/MR-005/MR-012/MR-013's own
precedent. If the epoch loop threatens to exceed the 5-minute ceiling during implementation, the response is
to narrow further (fewer epochs, smaller hidden size, and/or a shorter sequence window) — never to loosen the
ceiling. The ceiling itself is non-negotiable.

## Leakage-guard requirement — restated, binding on the Tech Lead

A sequence model is especially prone to accidentally including the current timestep's target in its own
input window — this is a new leakage failure mode relative to every prior MR-* story (distinct from MR-004's
same-row rolling-feature bug and MR-005's target-row state-routing bug, both caught via Tech Lead review). A
dedicated unit test must assert the input window constructed for row `t` uses only data through row `t-1` —
never row `t` itself — for every row in a synthetic series with a known, distinguishable value at each
timestep. Tech Lead review must explicitly verify this before sign-off, not merely rely on the automated test
passing — and QA must independently re-verify the test actually exercises the failure mode (see QA gate
below), not a trivial always-pass assertion.

## Single-data-path requirement — restated, binding on the Tech Lead

Data is loaded exclusively through `research/real_data.py`'s existing MR-012 real BTC/USDT loader (the
`research/`-owned HTTP client against `ingestion-service`'s `GET /datasets/{source}/series` route). Building a
second data path for this story is explicitly forbidden. Same purge-gap conventions as MR-008/MR-009/MR-012
(`purge_gap=6` for 1h/6h, `purge_gap=24` for 24h) — no narrowing.

## Hard gate — restated, binding on the Tech Lead

No product surface, README, UI copy, or customer-facing claim may assert the system predicts Bitcoin
prices/futures unless MR-015's GRU candidate has actually beaten Naive0 with Harvey-corrected DM significance
under this protocol on real data **at every horizon tested**. "No significant edge" is a complete, valuable,
honestly-reported outcome, consistent with MR-004/005/012/013's convention — not a failure.

## Stories in scope

- **MR-015** (Could) — GRU sequence-model candidate as a `Baseline` implementation
  (`research/models/gru_sequence.py`), CPU-only, `torch` (CPU-only wheel) added as a new
  `research/pyproject.toml` dependency per this session's explicit sign-off. Runs against MR-012's real-data
  window at 1h/6h/24h. Sole story this sprint; no ordering decision needed against any other story (none is
  in scope).

## Stories explicitly deferred

None from this backlog extension — MR-015 is the entire scope of this sprint and, per the backlog file, no
further MR-* stories are currently approved beyond it.

## Definition of done for this sprint

- MR-015's acceptance criteria (as stated verbatim in `docs/product/backlog-model-research.md`) are checked
  off: `torch` added to `research/pyproject.toml` and documented in `research/README.md` as an explicit,
  dated (2026-09-16) decision in the same style as `lightgbm` (MR-004) and `hmmlearn` (MR-005), including why
  a GRU was chosen over a Transformer and why no lighter-weight alternative exists; `Baseline`-protocol
  compliant implementation with no edit to `naive_first_engine`; per-split re-instantiation/refit test;
  leakage-guard unit test (row-`t`-uses-only-through-`t`-minus-1) present and Tech-Lead-verified as genuinely
  exercising the failure mode; compute ceiling honored with wall-clock reported; single data path via
  `research/real_data.py`'s MR-012 loader; `pct_change().dropna()` applied before Naive0 comparison; same
  purge-gap conventions as MR-008/009/012; DM-vs-Naive0 verdict counts reported at 1h/6h/24h; hard gate
  restated and honored.
- `libs/naive_first_engine` and `services/validation-service` suites re-run with zero regressions (neither
  module is touched by this sprint's scope).
- `docs/product/backlog-model-research.md`'s MR-015 entry marked done with acceptance-criteria boxes checked,
  pointing to its ticket file, any scope-bound (exact hidden size/epochs/window length, date range/row count
  reused from MR-012, measured wall-clock) disclosed in the entry itself.
- `docs/tickets/README.md`'s `research/` (MR-*) tracking table and a new Sprint 53 section added, matching
  the existing table format (see Sprint 52's entry for the closest precedent). (Tech Lead updates this file
  when the ticket is created/closed — not done by this sprint plan itself.)
- QA gate: per this platform's standing rule, the Tech Lead raises the `qa` agent (`/qa-validation`) after
  MR-015's ticket is Tech-Lead-verified done, before sign-off. QA scope should mirror Sprint 52's MR-013
  precedent (no live-deploy rebuild needed, `research/` has no service/API surface) but should specifically
  and independently verify:
  - the leakage-guard unit test actually exercises the row-`t`-uses-only-through-`t`-minus-1 failure mode
    (e.g. fails against a deliberately-broken implementation that includes row `t`), not a trivial
    always-pass assertion;
  - the compute ceiling was honored (hidden size ≤ 32, epochs ≤ 20, sequence window ≤ 24 timesteps, CPU-only)
    and wall-clock runtime is reported in the ticket;
  - the Harvey et al. (1997) correction is applied at the 24h horizon;
  - no README/ticket/UI copy anywhere asserts predictive capability unless a real, Harvey-corrected
    significant DM win was actually produced at every horizon tested.

## Next (explicitly not this sprint)

- If MR-015 produces a genuine, Harvey-corrected significant DM win over Naive0 on real data at every horizon
  (an open, uncertain outcome — not assumed here), that should prompt an explicit follow-up conversation with
  the Product Owner about product-copy implications before any customer-facing surface changes — not
  something for the Tech Lead or dev squad to action unilaterally under this sprint's scope.
- No further MR-* stories are currently backlogged beyond MR-015; this sprint closes the "GRU sequence-model
  candidate" extension as currently approved.
