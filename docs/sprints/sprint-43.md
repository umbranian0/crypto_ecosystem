# Sprint 43 — `research/`: per-split explainability artifacts (MR-006)

Sprint goal: every research candidate model's per-split fitted object (`LightGBMBaseline` from MR-004,
`RegimeHMMBaseline` from MR-005) has its feature-importance explainability captured and persisted
alongside that split's existing metrics through the same report pipeline, closing the thesis's stated gap
("Explicabilidade consistente por split... Arquivo não guarda feature importance/SHAP por split," section
1.6) for both fitted-model shapes now in `research/`, without a full SHAP integration or any new heavy
dependency.

Backlog source: `docs/product/backlog-model-research.md` (MR-006).

## Why now, single-story sprint

Sprint 42 explicitly deferred MR-006 specifically so it could cover both MR-004's (LightGBM) and MR-005's
(regime-HMM) fitted models in one pass rather than just MR-004's — see `docs/sprints/sprint-42.md`'s
"MR-006 considered, explicitly deferred" section. Both are now done (`docs/tickets/MR-004.md`,
`docs/tickets/MR-005.md`), so MR-006's deferral condition is satisfied and it is the only story in scope
this sprint.

## Pre-read findings that shape this plan

- MR-006's stated backlog dependency is MR-004 only; it does not depend on MR-005. Both are done, so
  MR-006 is fully unblocked either way — sequencing it after both simply lets one pass cover both model
  shapes, per Sprint 42's own stated reasoning.
- MR-006's backlog acceptance criteria (verbatim, `docs/product/backlog-model-research.md`):
  1. Explainability artifacts are computed from the same per-split fitted model object already produced
     by the `Baseline.predict` call — no separate, unaudited refit.
  2. Artifacts are stored/reported through the existing report pipeline (same reporting-service path as
     metrics), not a parallel ad hoc file dump.
  3. Explicitly out of scope for MR-004/MR-005's initial "does it beat naive" question — additive
     instrumentation, not a precondition for those stories' own closure.
- Neither the backlog entry nor MR-004/MR-005's tickets name SHAP as a hard requirement — the backlog's
  own title is "feature-importance or SHAP values" (either/or), and CLAUDE.md's standing "keep it simple"
  instruction plus this platform's light-compute-budget constraint governs the choice between them (see
  scope decision below).
- `reporting-service` is listed in `docs/implementation-plan.md` as planned (trigger #7), not yet built.
  AC2's "existing report pipeline (same reporting-service path as metrics)" needs a documented resolution
  of what "existing" means today, since a standalone `reporting-service` doesn't exist yet — see scope
  decision below for how this is handled without inventing a new service under this story.

## Explicit scope decision for MR-006 (binding on the Tech Lead)

**Feature-importance only, no SHAP, no new dependency.** Per CLAUDE.md's "don't over-engineer" instruction
and this platform's light-compute-budget standing constraint: `shap` is a genuinely heavier dependency
(its `TreeExplainer` for LightGBM is fine, but its `KernelExplainer` path needed for an HMM/per-state
linear model has no natural fit for a model class that isn't a single differentiable/tree estimator, and
would require inventing a background-distribution/sampling scheme to make SHAP apply at all). Both
candidate models already expose interpretable structure with zero new dependency:
- **`LightGBMBaseline` (MR-004)**: `LGBMRegressor.feature_importances_` is already computed as a
  byproduct of the existing `.fit()` call inside `predict` — read it directly off the same fitted
  `booster_`/`LGBMRegressor` object `predict` already builds, per split. No refit, no SHAP.
- **`RegimeHMMBaseline` (MR-005)**: classic SHAP/feature-importance doesn't map cleanly onto an HMM gate,
  as flagged in this story's own framing. The natural, honest explainability artifact for this model shape
  is **not** a SHAP value — it is (a) each per-state `LinearRegression`'s own fitted `.coef_`/`.intercept_`
  (the linear model genuinely is its own explanation — coefficients are the feature importance for a
  linear model), plus (b) which state was decoded as active for each row in that split's `test` fold (the
  HMM's own state-assignment output, already computed inside `predict` for MR-005's post-fix
  `test.shift(1)`-based routing — read it directly, do not recompute). Together these tell a reader
  "which regime was the model in, and what did that regime's linear model weight on which feature" — the
  actual explainability question for a regime-gated model, and one SHAP would not answer any better here.

**"Existing report pipeline" resolution**: since `services/reporting-service` (trigger #7) is not built
yet, "the same reporting-service path as metrics" is read as "the same in-process reporting/output
mechanism `research/`'s existing tests and README already use for MR-004/MR-005's DM-verdict-count
results" — i.e. explainability artifacts attach to the same `SplitResult`-shaped output `run_validation_
protocol` already returns per split (or a documented, equally-structured sibling artifact returned
alongside it), not a new file format or new persistence layer, and not a premature build-out of
`reporting-service` itself (that remains gated on its own trigger, unrelated to this story). The Tech Lead
should treat "no parallel ad hoc file dump" (AC2) as ruling out e.g. a raw pickle/CSV written straight to
disk outside the existing result objects/test-reported-output convention MR-004/MR-005 already
established — not as a mandate to stand up `reporting-service` early.

**Compute/scope ceiling, mirroring MR-004/MR-005's own precedent**:
- No new dependency (`shap` explicitly excluded per the above; `feature_importances_` and `.coef_` need
  none).
- No refit of either model — artifacts read directly off the fitted object each `predict` call already
  produces inside the existing per-split loop.
- Same seeded 3,000-row synthetic fixture (`research/tests/fixtures.py::synthetic_hourly_returns`) and
  same 1h/6h horizons MR-004/MR-005 already use — no new dataset.
- If, once implementation starts, attaching this to the existing `run_validation_protocol` result shape
  turns out to require a change inside `libs/naive_first_engine` itself (e.g. `SplitResult`'s own
  structure needs to grow a field), that is a **high-scrutiny, explicitly flagged** change per this
  backlog's own architecture-decision section — not a silent edit. If it can be attached as a
  research-side wrapper around the existing `Baseline`/`run_validation_protocol` output instead (e.g. a
  research-side collector that pairs each split's existing `SplitResult` with an explainability record
  keyed the same way), prefer that path first and only escalate to a `naive_first_engine` change if that
  genuinely isn't workable.

## Stories in scope, in execution order

1. **MR-006** — per-split explainability, feature-importance-only (no SHAP) scope, covering both
   `LightGBMBaseline` (MR-004, feature_importances_) and `RegimeHMMBaseline` (MR-005, per-state
   coefficients + per-row active-state assignment). Single story this sprint; no dependency ordering
   within the story itself since both target models already exist.

## Stories explicitly deferred

None this sprint — MR-006 is the only story pulled from the approved backlog for this sprint, per Sprint
42's own explicit deferral reasoning that named it as "the natural next research story once MR-005
lands."

## Definition of done for this sprint

- MR-006's acceptance criteria (as stated verbatim in `docs/product/backlog-model-research.md`) are
  checked off: artifacts computed from the existing per-split fitted object with no separate/unaudited
  refit; artifacts stored/reported through the existing result/report path per the resolution above, not
  a parallel ad hoc file dump; explicitly documented as additive, not a precondition for MR-004/MR-005's
  own already-closed status.
- The scope decision above (feature-importance-only, no SHAP, no new dependency) is reflected in the
  shipped ticket exactly as scoped, not silently expanded to a SHAP integration — if the Tech Lead finds
  feature-importance-only insufficient for some concrete, stated reason, that is flagged back to the PM,
  not decided unilaterally mid-implementation.
- Both target model shapes are covered: `LightGBMBaseline`'s `feature_importances_` per split, and
  `RegimeHMMBaseline`'s per-state linear coefficients plus per-row active-state assignment per split.
- A test proves the artifact is read from the same fitted object `predict` already produces (e.g. no
  second `.fit()` call anywhere in the explainability path) — mirroring MR-004/MR-005's own
  leakage/re-fit-discipline test precedent.
- `libs/naive_first_engine` suite re-runs with zero regressions; if any change to `naive_first_engine`
  proved necessary per the escalation path above, it is called out explicitly and separately reviewed,
  not folded in silently.
- `research/README.md` updated: MR-006's shipped status, the artifact shape for each model type, the
  no-SHAP scope decision and why, and (if applicable) where in the existing report/result structure the
  artifact now lives.
- `docs/product/backlog-model-research.md`'s MR-006 entry marked done, acceptance-criteria boxes checked,
  pointing at its ticket file, noting the feature-importance-only scope reduction explicitly so the
  backlog record doesn't silently imply full SHAP support shipped.
- `docs/tickets/README.md`'s `research/` (MR-*) tracking table and this sprint's own row updated — MR-006
  stays "not started" until the Tech Lead actually builds it; this sprint file only plans the work.
- QA gate: per this platform's standing rule, the Tech Lead raises the `qa` agent (`/qa-validation`)
  after MR-006's ticket is done, before sign-off. `research/` has no service/API surface and nothing here
  runs inside a deployed container, so QA scope should be sized accordingly (no live-deploy rebuild
  needed) — but QA should independently re-confirm no refit occurred, both model shapes are actually
  covered (not just one), and no CLAUDE.md positioning-rule violation crept into any new
  docstring/comment describing "explainability" as predictive signal.
