---
status: accepted
---

# Multimodal candidate-model interface: `Baseline` is unchanged; a new, additive `CandidateModel` Strategy interface (`libs/naive_first_engine/src/naive_first_engine/candidate_model.py`) is added for multi-column feature `DataFrame` input, not wired into `protocol.py`

`docs/product/backlog-multimodal-dataset-fusion.md` (MDF-004) asks whether `naive_first_engine`'s public
interface needs to change now that MDF-003 (`services/validation-service/src/app/feature_dataset.py`,
shipped Sprint 36) can assemble an aligned, multi-column `pd.DataFrame` via `FeatureDatasetAssembler.
assemble()`. No candidate-model call site exists anywhere in the codebase today — this ADR is analysis
plus an additive interface, not implementation of a real model or its wiring. Ticket:
`docs/tickets/MDF-004-01.md`. Depends on ADR-0008 (`docs/adr/0008-multimodal-fusion-architecture-and-
leakage-posture.md`, placed the join inside `validation-service`) and ADR-0009 (`docs/adr/0009-
multimodal-timestamp-alignment-design.md`, confirmed the assembled table's index is exactly the target
series' own index, handed to `generate_splits` unchanged, and stated `generate_splits` "requires no
change" — this ADR verifies that claim directly against the real `splitting.py` code rather than merely
citing it, per ADR-0009's own "Consequence for future readers" note).

## Context: what `Baseline` is actually consumed by today

`Baseline.predict(train: pd.Series, test: pd.Series) -> pd.Series` (`baselines.py:16-31`) is consumed
today only by `Naive0`, `NaiveLast`, and any `config.extra_baselines` entry `protocol.py`'s
`run_validation_protocol` calls inside its fixed Template Method sequence (split, then baselines, then
metrics, then DM test against Naive0 — `protocol.py:94-154`). Every one of those call sites passes a
`pd.Series`, never a `DataFrame` — `run_validation_protocol` itself only ever operates on a single
`series: pd.Series` argument (`protocol.py:94`). Nothing in `libs/naive_first_engine` or any service today
calls `Baseline.predict` with a multi-column input, and nothing calls `FeatureDatasetAssembler.assemble()`
output into any model-inference call at all (MDF-003's own docstring flags this gap explicitly:
`feature_dataset.py:41-43`, "Not yet wired into any candidate-model inference call (no such consumer
interface exists yet — MDF-004's explicit, deferred question)").

**DRY check (implementation-plan.md section 9)**: grepped `libs/naive_first_engine` for every reference to
`Baseline`, `predict(`, and `DataFrame` before writing anything below. Reused, not duplicated: `Split`
boundaries from `splitting.generate_splits` (the new interface composes with these exactly as `Baseline`
does — see Decision (3) below), `report_schema.py`'s typed result objects (not modified, not referenced by
the new interface, since it is not yet wired into `run_validation_protocol`'s output shape), and the same
Strategy pattern rationale implementation-plan.md section 7 already uses to justify `Baseline`'s existence.
Nothing new was needed for splitting/metrics/DM-test math — the new interface is purely a call-shape
addition, mirroring `Baseline`'s existing docstring leakage-safety argument rather than re-deriving it (see
Decision (4)).

## Decision

**(1) `Baseline.predict(train: pd.Series, test: pd.Series) -> pd.Series` does not change.** It governs only
the two mandatory naive baselines and the DM-test error Series they produce (`protocol.py:109-136`), not a
candidate model's own inference call — there is no forcing reason in the codebase today to touch it, and
doing so would risk `Naive0`/`NaiveLast`'s behavior (Sprint 38's high-scrutiny flag explicitly forbids
this). `baselines.py` has a zero-line diff for this ticket.

**(2) Yes, a new, additive interface is needed.** `CandidateModel`
(`libs/naive_first_engine/src/naive_first_engine/candidate_model.py`, new file, inside `libs/
naive_first_engine` — core IP, not `validation-service`, per implementation-plan.md section 2/5's
ownership split) is a second `typing.Protocol`, structurally parallel to `Baseline` but with a
`DataFrame`-shaped signature:

```python
def predict(
    self,
    train_features: pd.DataFrame,
    train_target: pd.Series,
    test_features: pd.DataFrame,
) -> pd.Series: ...
```

`train_features`/`test_features` are the pre-sliced feature `DataFrame`s implied by a `Split` boundary
(the same boundaries `Baseline` receives, just applied to `FeatureDatasetAssembler.assemble(...).
feature_dataframe` instead of a single `pd.Series`). `train_target` is the train-period target `Series`,
also pre-sliced to the same boundary — a model needs it to fit against, but there is deliberately no
`test_target` parameter, so `predict` has no way to receive the test period's own target values at all.

It composes with `generate_splits`'s `Split` boundaries the same way `Baseline` does: a caller (not yet
written — no such caller exists in this ticket's scope) would compute `splits = generate_splits(target_
index, ...)`, then slice `train_features = feature_dataframe.loc[split.train_start:split.train_end]`
(and the analogous `test_features`/`train_target` slices) before calling `predict`. This reuses `Split`
boundaries exactly as `protocol.py:106-107` already does for `Baseline`'s `train`/`test` Series slices —
no duplication of `generate_splits` or its purge-gap logic. `protocol.py`'s Template Method sequence
(split → baselines → metrics → DM test, in that fixed order) is **not modified** and does not call
`CandidateModel` anywhere; wiring a candidate-model call site into that sequence (or a parallel one) is
explicitly out of this ticket's scope, left open for a future ticket.

**(3) Confirmed: `generate_splits`'s purge-gap logic is identical regardless of model-input shape.**
`splitting.py`'s `generate_splits(index, train_window, test_window, step, purge_gap)` takes only a
`pd.DatetimeIndex` (`splitting.py:29-35`) — neither `_generate_splits_by_position` nor `_generate_splits_
by_time` (`splitting.py:59-146`) ever receives, inspects, or branches on any Series/DataFrame column data;
every purge-gap boundary (`train_end`, `test_start`, `purge_start`/`purge_end`) is computed purely from
`index` positions/timestamps. Column count is not an input to either branch at all — there is no
parameter through which it could be. This is backed by a new test, not just an assertion:
`tests/test_candidate_model.py::test_generate_splits_same_regardless_of_model_input_shape` calls
`generate_splits` twice with identical arguments (once "for" a hypothetical univariate caller, once "for"
a hypothetical multivariate caller — the labels are illustrative only, since `generate_splits` cannot tell
the difference) and asserts the returned `Split` lists are equal, then slices both a `pd.Series` and a
two-column `pd.DataFrame` from the *same* `Split` boundaries and confirms the resulting train/test index
sets and the `train_end < test_start` purge-gap relationship are identical either way. This directly
verifies ADR-0009's "Consequence for future readers" claim ("generate_splits's purge-gap logic applies
identically regardless of whether the assembled input is univariate or multivariate") against the real
`splitting.py` code, as ADR-0009 itself required MDF-004 to do rather than merely citing it.

**(4) `CandidateModel` carries the equivalent structural leakage-safety guarantee, not merely the same
argument by reference.** `Baseline`'s docstring argument is structural: because `predict` only ever
receives the pre-sliced `train`/`test` Series (no full series, no boundary argument), it is *impossible*
for an implementation to read past `train_end` — there is nothing to read past. `CandidateModel`'s
signature has the identical structural property for its wider input: `train_features`/`train_target` are
pre-sliced to `train_start..train_end`, `test_features` is pre-sliced to `test_start..test_end`, and there
is no `test_target` parameter at all — an implementation cannot read the test period's own target values
even by accident, because they are never passed in. This is not a restatement of `Baseline`'s docstring by
reference; it is the same structural guarantee re-derived for the `DataFrame` case, stated in `Candidate
Model`'s own docstring (`candidate_model.py`) and covered by
`tests/test_candidate_model.py::test_candidate_model_predict_cannot_reach_test_target_by_construction`,
which inspects the live signature (`inspect.signature`) to confirm no `test_target` parameter exists,
rather than only asserting it in prose.

## Consequences

- `libs/naive_first_engine/src/naive_first_engine/candidate_model.py` (new file) and
  `tests/test_candidate_model.py` (new file) are the only code changes. `baselines.py`, `splitting.py`,
  `dm_test.py`, `report_schema.py` all have a zero-line diff — confirmed by `git diff` on each (see
  MDF-004-01's final report). `protocol.py` is also unmodified — `CandidateModel` is not called by
  anything.
- `libs/naive_first_engine/README.md`'s "Public API" section deliberately does **not** list
  `CandidateModel` under a `### \`candidate_model.py\`` heading: `scripts/check_doc_sync.py`'s
  `MODULE_NAMES` list (NFE-018) is a fixed six-module list, and adding a seventh heading there would make
  the doc-sync check flag it as an "unknown module" (the check treats any `### \`module.py\`` heading not
  in `MODULE_NAMES` as an error). `CandidateModel`'s signature is documented in prose in the README's
  status notes and in the module's own docstring instead — `scripts/check_doc_sync.py` still passes
  because it never inspects `candidate_model.py`, consistent with that file not yet being part of any
  service's contract.
- Wiring a real candidate-model call site (a service-side or `protocol.py`-side orchestration step that
  actually calls `CandidateModel.predict`) is explicitly **not** part of this ADR or MDF-004-01 — it
  remains open for a future ticket, same as MDF-003's own disclosed gap.
- `MDF-004`'s broader acceptance criteria (`docs/product/backlog-multimodal-dataset-fusion.md` lines
  190-211) beyond this specific interface question are out of this ADR's scope; only the interface-design
  question is answered here.

**Tech Lead review pass (per Sprint 38's high-scrutiny flag, `docs/tickets/MDF-004-01.md` Review acceptance
criteria) — completed, `status` flipped to `accepted`.** Personally confirmed, independent of the dev
agent's own report: `git diff --stat` on `baselines.py`, `splitting.py`, `dm_test.py`, `report_schema.py`,
and `protocol.py` is empty; `candidate_model.py`'s `CandidateModel.predict` signature has no `test_target`
parameter (structurally cannot read past `train_end`/into the test target, matching `Baseline`'s existing
guarantee); `CandidateModel` is not imported or called by anything in `libs/naive_first_engine` or any
service (grepped); `tests/test_candidate_model.py::test_generate_splits_same_regardless_of_model_input_shape`
independently re-read and confirmed it proves `generate_splits` is index-only, never branching on model
input shape/column count. Full `libs/naive_first_engine` suite independently re-run: **99 passed** (95
pre-existing + 4 new, zero regressions, zero existing test files modified). `scripts/check_doc_sync.py`
re-run, passes.
