---
name: ml-engineer
description: Builds and evaluates production-grade machine learning pipelines, feature engineering steps, and prediction APIs. Trigger when working on data science scripts, model training, or scikit-learn/xgboost code.
---

# ML Engineering Guidelines

Applies to any code that fits, transforms, or scores data -- feature engineering scripts, model training code, or a `Baseline`/`extra_baselines` implementation plugged into `naive_first_engine`. In this repo, treat these guidelines as the ML-domain-specific companion to `/tdd` and `/code-review`, not a replacement for either -- and use `/ml-feature-planning` to sequence design -> tests -> review for a new feature/model step.

## Core rules

1. **Always split data before applying feature scaling or imputation.** Never call `.fit()`/`fit_transform()` on a scaler, imputer, or encoder against the full dataset before splitting. This is the exact leakage failure mode CLAUDE.md names as the reason this whole platform exists -- any transform must be fit on the training fold only, per split, never globally. If you're writing a `Baseline`/model adapter for `naive_first_engine`, remember `predict(train, test)` only ever receives pre-sliced data -- fit inside that call, on `train` alone, never on data captured from outside it.

2. **Write unit tests for data transformation pipelines using pytest** -- at minimum, one test confirming the transform's output shape/values on a known input, and one confirming it raises (or degrades sensibly) on a degenerate input (empty series, single row, all-NaN column). Follow `/tdd`'s seam and anti-pattern rules -- a transform test that recomputes its expected value the same way the code does is tautological, not a real check; expected values must come from an independent source (a hand-worked example, a published reference number, a known-good literal).

3. **Use Pydantic for validating incoming feature payloads in a prediction API** -- request/response models at the API boundary, never a bare `dict` passed straight into inference code. Reuse `naive_first_common.contracts`' existing shared models where a shape already exists (dataset references, run configs, split results) rather than defining a parallel one.

4. **Never let model/feature code imply a live trading or forecasting product.** If code here produces a real prediction (not a benchmark comparison), check CLAUDE.md's "Product positioning" section before writing any user-facing copy, docstring, or API description -- this platform audits predictions against naive baselines, it does not sell them as forecasts. See `docs/adr/0002-declined-automated-trading-product.md` for why this line exists.

5. **Report negative results plainly.** A model that fails to beat naive isn't a bug to quietly drop or a case to re-tune until it looks better -- see `/naive-first-audit` for how this codebase expects that finding to be written up, both ways.
