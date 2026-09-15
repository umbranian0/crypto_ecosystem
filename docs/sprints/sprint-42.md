# Sprint 42 — `research/`: regime-sensitive candidate (MR-005) + `validation-service`: feature export endpoint (MR-007)

Sprint goal: `research/` gains a second candidate model — a simple 2-state HMM gating a linear model,
wrapped as a `Baseline`, run on the same seeded synthetic fixture MR-004 used — reporting an honest
DM-vs-Naive0 verdict at 1h/6h, extending the "does anything beat naive" evidence base to a regime-
switching model class the thesis itself flagged as untested, without exceeding this platform's light
research-compute budget; in parallel, `services/validation-service` gains a read-only
`GET /runs/{run_id}/features` export endpoint, closing MR-003's disclosed gap so research candidates
can eventually train on real multimodal data instead of synthetic.

Backlog source: `docs/product/backlog-model-research.md` (MR-005 and MR-007; MR-006 considered and
deferred, see below).

## Two parallel-eligible tracks this sprint

This sprint has two independent tracks that can be built in either order or concurrently — same
parallel-pairing precedent as Sprint 40's DASH-128/MR-002:

- **Track A — MR-005** (`research/`): regime-sensitive candidate model, light-compute-scoped. See scoping
  section below.
- **Track B — MR-007** (`services/validation-service`): read-only feature-export endpoint. Depends on
  MR-003 (done, Sprint 36) and VS-030 (done) — not on MR-005 or MR-004 in any way; MR-007's own backlog
  rationale explicitly notes it is "not required for MR-004/MR-005 (which train on the returns series ±
  MR-002's engineered features, not multimodal data yet)."

**No file overlap**: Track A touches only `research/` (plus `research/README.md` and
`docs/product/backlog-model-research.md`'s MR-005 entry). Track B touches only
`services/validation-service/src/app/routers/runs.py`, its tests, and
`services/validation-service/README.md`. Per this project's module-boundary rules, no service imports
another service's or library's code across these two tracks, so there is no ordering constraint between
them — either can start first, or both can run concurrently, without blocking the other.

## Pre-read findings that shape this plan

- `docs/tickets/README.md`'s `research/` (MR-*) tracking table: MR-001/002/003/004 done (Sprint 41 most
  recent), MR-005/MR-006 "not started". MR-004 shipped light-compute-scoped: 3,000-row seeded synthetic
  series, fixed hyperparameters, CPU-only, 1h/6h horizons only, `research/` suite currently 10 passing.
- MR-005's stated backlog dependency is MR-001 (done) and MR-004 (done, "establishes the pipeline/report
  shape reused here") — both satisfied, MR-005 is unblocked.
- MR-005's own backlog rationale already flags it as materially harder than MR-004: "regime detection
  itself needs care to avoid look-ahead," "higher research-time cost," "less certain path to even a
  clean negative result." Sprint 41 explicitly named MR-005 as the "next research story," "subject to
  ... the same light-compute discipline this sprint establishes for MR-004."
- MR-006 depends only on MR-004 (already done), not on MR-005 — it is additive instrumentation
  (feature importance/SHAP persisted per split), not a precondition for MR-005's own DM-vs-Naive0
  question. It is technically unblocked and could run independently of MR-005 this sprint.

## Explicit compute-budget scoping decision for MR-005 (binding on the Tech Lead)

MR-005's literal acceptance criteria ask for a full regime-sensitive/hybrid `Baseline` under the same
protocol as MR-004. Read verbatim, "regime-switching or hybrid model (e.g. a hidden Markov model gating
a simple linear model per regime)" already names the cheapest reasonable interpretation — this plan
takes that example as the actual scope, not a jumping-off point for something broader (e.g. a
multi-model regime ensemble, a wider regime-count search, or feature sets beyond what MR-002 already
provides). Flagging directly, per this backlog's own standing constraint, that MR-005 in full plausibly
exceeds "light" compute/time budget if scope is allowed to drift (regime detection has more failure
modes and more hyperparameter surface — number of states, covariance type, per-regime model choice —
than a single boosting model does) and scoping this down explicitly rather than letting it expand
quietly:

- **Model**: exactly a 2-state Gaussian HMM (state count fixed, not searched) gating a simple linear
  regression (one linear model fit per state, on the state's own training-fold rows only) — not a
  3+-state model, not a more expressive per-state model class, not an HMM-LSTM or other hybrid variant.
- **Dataset**: the same seeded 3,000-row synthetic fixture MR-004 already uses (or an equivalently
  seeded/sized fixture if the existing one isn't directly reusable) — no new, larger, or real-market
  dataset introduced for this story.
- **Regime fit boundary**: regime detection (the HMM fit itself) happens strictly on the training fold,
  per split, exactly as MR-005's own AC already states — this is the one AC that must not be scoped down,
  since it is the specific leakage failure mode (hindsight regime labeling) this story exists to guard
  against.
- **Hyperparameters**: fixed, no search loop — same "tight and fixed, no CV tuning" rule Sprint 41 set
  for MR-004, applied here to both the HMM's own settings and the per-regime linear model.
- **Horizons**: 1h and 6h only, matching MR-004 and MR-005's own stated report-shape parity requirement.
- **Expected runtime**: minutes, not hours — if the Tech Lead's ticket breakdown trends toward materially
  longer, that is a signal to narrow further (e.g. fewer splits, smaller fixture), not to relax this cap.
- If, once implementation starts, the Tech Lead finds even this narrowed slice does not cleanly fit a
  light-compute budget, the correct move is to say so and re-scope further (or flag back to the PM) —
  not to silently expand time/compute to make the full backlog AC work.

## Stories in scope, in execution order

1. **MR-005** (Track A) — regime-sensitive (2-state HMM gating linear model) `Baseline`,
   light-compute-scoped per the section above. Runs after MR-001 (done) and MR-004 (done), per its own
   stated dependency and Sprint 41's explicit sequencing precedent.
2. **MR-007** (Track B) — read-only `GET /runs/{run_id}/features` export endpoint on
   `services/validation-service`, closing MR-003's disclosed gap. Depends on MR-003 (done) and VS-030
   (done). Listed second here only because MR-005 was sequenced first when this sprint was originally
   scoped — this is **not** a dependency ordering: MR-007 has no file overlap with MR-005 (`research/`
   vs. `services/validation-service`) and no dependency on it or on MR-004, so it is parallel-eligible
   and may be built before, after, or concurrently with MR-005.

## MR-006 considered, explicitly deferred to a following sprint (not combined into this one)

MR-006 (per-split explainability artifacts) is dependency-unblocked today — it depends on MR-004, which
is done, not on MR-005. It would be technically legal to run in the same sprint. Deferring it anyway,
for reasons stated explicitly rather than left implicit:

- **Scope-creep risk, not dependency risk.** MR-005 already carries this sprint's compute-budget risk
  (a materially harder modeling problem per its own backlog rationale, scoped down above specifically to
  stay light). Adding MR-006 in the same sprint means the Tech Lead is simultaneously scoping a novel
  model class *and* wiring a new instrumentation/reporting surface (explainability artifacts persisted
  through the reporting-service path) in one pass — two different kinds of new surface area reviewed at
  once, which is exactly the condition under which scope quietly expands.
- **MR-006's natural target only exists after MR-005 lands.** MR-006's stated purpose is explaining "a
  candidate model's marginal DM win" — while it's written against MR-004 today, the more interesting
  and more novel artifact to persist (once MR-005 exists) is explainability for the HMM/regime-gated
  model, not just re-deriving what SHAP already shows for a boosting model. Running MR-006 immediately
  after MR-005 lands, rather than concurrently, lets it cover both candidate models with one pass instead
  of potentially two.
- **"Keep it simple, don't over-engineer."** One new candidate model class, evaluated honestly, is a
  complete and closeable sprint on its own — bundling in reporting-instrumentation work does not make
  MR-005's own result any more honest or any faster to land.

MR-006 remains eligible for the next sprint once MR-005 lands (whichever way its result goes), with no
change to its own stated backlog dependency (MR-004, already satisfied).

## Stories explicitly deferred

- **MR-006** (per-split explainability) — see "MR-006 considered, explicitly deferred" above. Reason:
  scope-creep risk of combining a novel-model story with a novel-instrumentation story in one sprint,
  and MR-006's output is more valuable once it can cover both MR-004 and MR-005's fitted models.

## Definition of done for this sprint

- MR-005's acceptance criteria (as stated verbatim in `docs/product/backlog-model-research.md`) are
  checked off: same `Baseline`-protocol/per-split-train-only-fit/DM-vs-Naive0 reporting shape as MR-004;
  regime detection fit strictly on the training fold per split (explicit unit test proving no
  whole-series/global regime fit, mirroring MR-004's "re-instantiated per split" test precedent); result
  reported honestly regardless of outcome (beating naive and not beating naive are both valid closes).
- The compute-budget scoping above (2-state HMM, fixed hyperparameters, MR-004's existing seeded fixture,
  1h/6h only, CPU-only, minutes not hours) is reflected in the shipped ticket, not silently expanded —
  Tech Lead states the actual measured runtime/dataset size in the ticket, same as MR-004's precedent.
- `libs/naive_first_engine` and `services/validation-service` suites re-run with zero regressions (this
  story lives entirely under `research/`, same boundary MR-004 held).
- `research/README.md` updated: MR-005's shipped status, the HMM/linear-hybrid `Baseline`'s file
  location, and its light-compute scoping stated plainly (state count, dataset, hyperparameters, horizons)
  so a future session knows this was a scoped-down slice of the full backlog AC, not an open-ended regime
  research program.
- `docs/product/backlog-model-research.md`'s MR-005 entry marked done with acceptance-criteria boxes
  checked, pointing to its ticket file, and a note that scope was narrowed to a 2-state HMM per this
  sprint's compute-budget decision (so the backlog record doesn't silently imply a broader search ran).
- **MR-007's** acceptance criteria (as stated verbatim in `docs/product/backlog-model-research.md`) are
  checked off: `GET /runs/{run_id}/features` added to `routers/runs.py`, tenant-scoped through the
  existing auth dependency; route re-invokes `FeatureDatasetAssembler.assemble` from the run's persisted
  `feature_lineage`, returning `404` when `has_multimodal_features` is `False`; JSON-serializable table
  response; `create_run`'s existing call path unchanged (zero lines diff); reproducibility test against
  the run's own lineage; no `libs/naive_first_engine` changes.
- `services/validation-service/README.md`'s "Routes" list and "Multi-source feature assembly
  (VS-030/MDF-003)" section updated for MR-007, and `scripts/check_doc_sync.py` passes.
- `docs/product/backlog-model-research.md`'s MR-007 entry marked done, pointing to its ticket file.
- `docs/tickets/README.md`'s Sprint 42 section updated for both MR-005 and MR-007, matching the existing
  table format.
- QA gate: per this platform's standing rule, the Tech Lead raises the `qa` agent (`/qa-validation`)
  after each track's stories are done, before sign-off. Given `research/` has no service/API surface and
  nothing here runs inside a deployed container, QA scope for MR-005 should be sized accordingly (no
  live-deploy rebuild needed) — but QA should independently re-confirm the regime fit's per-split-only
  boundary (the specific leakage failure mode this story exists to guard against) and the actual measured
  runtime/state-count/dataset size against this sprint's light-compute ceiling, mirroring Sprint 41's QA
  precedent for MR-004. MR-007 does run inside a deployed container (`services/validation-service`) and
  should get the standard live-service QA pass: new route smoke-tested against a running container,
  tenant-scoping/404 behavior verified, `create_run`'s zero-diff claim independently confirmed.

## Next (explicitly not this sprint)

- MR-006 (per-split explainability) is the natural next research story once MR-005 lands, ideally
  covering both MR-004's and MR-005's fitted models in one pass, subject to separate sign-off per this
  sprint's own deferral reasoning above.
