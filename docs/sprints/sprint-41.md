# Sprint 41 — `research/`: multimodal-input interface (MR-003) then a light-compute gradient-boosting candidate (MR-004)

Sprint goal: `research/` gains a documented, non-duplicative interface for consuming
`validation-service`'s real multi-source feature assembly (MDF-003/VS-030), and its first candidate
model — a CPU-only, tightly-scoped gradient-boosting `Baseline` — runs the full leakage-safe
protocol at 1h and 6h horizons and reports an honest DM-vs-Naive0 verdict, whichever way it goes.

Backlog source: `docs/product/backlog-model-research.md` (MR-003, MR-004).

## Pre-read findings that shape this plan (not in the backlog file itself)

- **MDF-003/VS-030 is real and shipped**, not just documented: `services/validation-service/src/app/
  feature_dataset.py` (`FeatureDatasetAssembler`), wired into `POST /runs` via the optional
  `feature_references`/`missing_timestamp_policy` request fields, alignment-ordering and
  per-fold-scaler tests both passing (Sprint 36, commit `08d9d8a`; `services/validation-service`
  README "Multi-source feature assembly (VS-030/MDF-003)" section). MR-003's stated blocking
  condition (MDF-003 must ship first) is satisfied — confirmed against the actual diff/tests, not
  the backlog's own framing alone.
- **But there is no export endpoint** — this is the finding that reshapes MR-003's actual scope this
  sprint. `FeatureDatasetAssembler.assemble`'s output (the aligned multi-column `DataFrame`) is
  consumed *internally* by `routers/runs.py::create_run` and immediately reduced back to a
  re-indexed target `pd.Series` before `run_validation_protocol` runs — it is never returned by any
  `GET` route. `FeatureFoldScaler` (the per-fold-fit preprocessing surface) is explicitly "not yet
  wired into any candidate-model inference call — no such consumer interface exists yet (MDF-004's
  explicit, deferred question)" per that same README section. So `research/` cannot, today, pull the
  assembled multimodal feature table out of `validation-service` by calling anything — the join logic
  is real, but it is not yet an externally consumable interface for a `Baseline`/`CandidateModel` to
  train against.
- This means MR-003 in this sprint is **interface-design-and-documentation scope only**: write down
  the contract research code would call once such an endpoint exists (what shape, what auth, what it
  returns), explicitly naming the gap above, rather than any code that actually fetches or trains on
  real multimodal data this sprint. Writing that gap down is itself the deliverable — it is exactly
  the kind of dependency MR-004/MR-005 need spelled out before anyone assumes multimodal inputs are
  already pluggable.

## Stories in scope, in execution order

1. **MR-003** — multimodal fusion inputs interface (bridges MDF-003). Runs first: it is the cheaper,
   lower-risk story (documentation/interface design, no training run), and its output — a clear
   statement of what `research/` can and cannot call today re: multimodal features — is the honest
   context MR-004's implementer needs before building a candidate model, even though MR-004's own
   stated backlog dependency is only MR-001 (already done). Concretely: MR-003 does not change
   MR-004's actual inputs this sprint (MR-004 trains on the returns series ± MR-002's engineered
   features, not multimodal data — no multimodal export interface exists yet), but sequencing MR-003
   first avoids MR-004's implementer independently re-discovering the "no export endpoint yet" gap
   mid-story.
   - Acceptance criteria per `docs/product/backlog-model-research.md`: documented interface written
     before any research code touches multimodal data; explicit statement of the still-blocking
     condition (no export endpoint on `validation-service` yet, even though MDF-003 itself shipped);
     no `naive_first_engine` change.
2. **MR-004** — gradient-boosting (LightGBM) `Baseline` implementation, 1h and 6h horizons. Runs
   second: depends on MR-001 (done, satisfied) per the backlog; also benefits from MR-003 landing
   first so its own scope note doesn't need to re-derive the "no multimodal export yet" finding.
   Trains on the existing returns series, optionally MR-002's engineered features (rolling
   volatility/mean/std, lagged returns) — not multimodal inputs, per MR-003's finding above.

## Explicit light-compute scoping for MR-004 (non-negotiable per this run's constraint)

Flagging directly: MR-004's literal acceptance criterion ("Full run at 1h and 6h horizons") is
ambiguous about dataset size, and this repo does not currently have a confirmed real, large-scale
BTC dataset wired end-to-end for research use — `naive_first_engine`'s own regression fixtures use
synthetic series in the ~2,000-hourly-row range (see `tests/test_regression_1h.py`), and
`ingestion-service`'s real `processed/`/continuous-table zones are not confirmed populated with a
multi-year history (see `services/validation-service` README's disclosed gap notes). If a "full run"
were instead interpreted as years of hourly data across the full rolling-origin walk-forward window,
LightGBM refit-per-split at that scale could plausibly run for hours, not minutes — that is exactly
the heavy-compute risk this run's constraint prohibits. Scoping this down explicitly rather than
silently either skipping the AC or proceeding at unbounded scale:

- **Dataset window**: capped to a bounded recent history window (target: on the order of a few
  thousand hourly rows, matching the scale `naive_first_engine`'s own regression suite already
  exercises) — not the full multi-year history, even if a larger series happens to be available.
  The exact cap is a Tech Lead/dev-agent implementation decision within this ceiling, not specified
  further here (PM scope, not technical design).
- **Hyperparameters, tight and fixed, no search**: small `n_estimators` (double digits to low
  hundreds, not thousands), shallow `max_depth`/`num_leaves`, no cross-validated hyperparameter
  tuning loop (that would multiply the per-split fit cost by however many candidate configs are
  tried — explicitly out of scope this sprint).
- **CPU-only**: no GPU-accelerated LightGBM build, no cloud training job — must run locally in this
  session's own environment.
- **Horizons**: 1h and 6h only, per the backlog's own AC (24h and any exploratory horizon beyond
  those two are out of scope this sprint, keeping total split count bounded).
- **Expected runtime**: minutes, not hours, end to end (dataset prep + all splits’ fit/predict +
  DM-test) — if the Tech Lead's actual implementation trends toward hours at the ticket-breakdown
  stage, that is a signal to scope the window/split count down further, not a signal to relax this
  constraint.
- This scoped-down run is explicitly a **light-compute, hours-not-days research pass**, not the
  thesis's own original full-history backtest — the story's "definition of done" (report the result
  honestly regardless of outcome) still applies in full to this smaller run; a scoped-down dataset
  does not excuse a dishonest or inflated framing of what was actually tested.

## Stories explicitly deferred

- **MR-005** (regime-sensitive/HMM candidate) — depends on MR-001 and MR-004 (pipeline/report-shape
  precedent); not requested in scope this sprint and materially higher research-time cost per its own
  backlog rationale.
- **MR-006** (per-split explainability) — depends on MR-004 existing first; additive instrumentation,
  not requested this sprint.
- **The multimodal export endpoint itself** (whatever ships to let `research/` actually pull
  `FeatureDatasetAssembler`'s output) — not an approved backlog story yet; MR-003 documents the gap,
  it does not build the fix. Any such endpoint needs its own Product-Owner-approved story before a
  future sprint schedules it (same "no scope not already approved" rule this sprint itself follows).

## Definition of done for this sprint

- MR-003 and MR-004's acceptance criteria (as stated in `docs/product/backlog-model-research.md`) are
  checked off, including MR-003's explicit "still blocked on an export endpoint that does not exist
  yet" disclosure and MR-004's "reported honestly regardless of outcome" clause.
- MR-004's own unit test proves the model is re-instantiated/re-fit per split (no stale reuse across
  splits), per its stated AC.
- Full `libs/naive_first_engine` and `services/validation-service` suites re-run with zero
  regressions (neither module's source is expected to change this sprint — MR-003 is docs/interface
  only, MR-004 lives entirely under `research/`).
- `research/README.md` updated: MR-003's interface note and its disclosed gap, plus MR-004's shipped
  status, the gradient-boosting `Baseline`'s file location, and its light-compute scoping (dataset
  window/hyperparameter caps/CPU-only, as summarized above) stated plainly so a future session knows
  this was a scoped-down run, not the thesis's full-history backtest.
- `docs/product/backlog-model-research.md`'s MR-003 and MR-004 entries marked done with
  acceptance-criteria boxes checked, pointing to their ticket file(s).
- `docs/tickets/README.md`'s `research/` (MR-*) ticket-tracking subsection updated for both tickets,
  matching the existing table format (see the Sprint 40 entry's precedent).
- QA gate: per this platform's standing rule, the Tech Lead raises the `qa` agent (`/qa-validation`)
  after both tickets are done, before any sign-off. Given `research/` code has no service/API
  surface and nothing here is deployed inside a running container, QA scope should be sized
  accordingly (no live-deploy rebuild needed) — but QA should independently re-confirm MR-004's
  actual measured runtime and dataset size against this sprint's light-compute ceiling, not just
  trust the ticket's self-report.

## Next (explicitly not this sprint)

- MR-005/MR-006 are the natural next research stories once MR-004 lands and its report shape is
  established, subject to separate Product Owner/requester sign-off and (for MR-005) the same
  light-compute discipline this sprint establishes for MR-004.
- A dedicated `validation-service` export-endpoint story (to make `FeatureDatasetAssembler`'s output
  actually callable by `research/`) is flagged for the Product Owner to write up and prioritize — not
  filed as a ticket by this sprint.
