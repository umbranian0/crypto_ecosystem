# Sprint 38 — `naive_first_engine` multi-column interface analysis + multimodal copy discipline (MDF-004, MDF-005)

Sprint goal: the Tech Lead has a reviewed, written answer on whether `naive_first_engine`'s public
interfaces need to change for multi-column candidate-model input, and every surface showing a
multimodal run's result is proven (by a grep test) to describe it as a validation outcome, never as
prediction quality or elevated confidence.

Backlog source: `docs/product/backlog-multimodal-dataset-fusion.md` (MDF-004, MDF-005).

## Scope decision: both blockers already closed

MDF-003 shipped and was live-verified in Sprint 36 (`VS-030`, `services/validation-service/src/app/
feature_dataset.py`), so both stories this sprint are unblocked per the backlog's own sequencing note.
MDF-001/MDF-002 (Sprint 31, ADR-0008/ADR-0009, both `status: accepted`) remain the governing decisions
neither story re-opens.

**In scope this sprint (2 stories):** MDF-004 — confirm/extend `naive_first_engine`'s interfaces for
multi-column model input [Must, high scrutiny]; MDF-005 — positioning/copy discipline for multimodal
validation results [Must].

## Stories in scope, in execution order

1. **MDF-004** — analysis/decision story, no code dependency on MDF-005's output. Sequenced first (or
   in parallel — see note below) because it is the higher-risk story touching the platform's core IP
   and the backlog explicitly flags it as needing to be "scoped and reviewed" with priority attention.
2. **MDF-005** — depends on MDF-003's lineage data only (already shipped, Sprint 36), not on MDF-004's
   outcome. Can run in parallel with MDF-004 if the Tech Lead has separate dev-agent capacity; otherwise
   sequenced second. No ordering conflict either way — the two stories touch disjoint files
   (`libs/naive_first_engine` analysis output vs. UI/API copy in `dashboard-web`/`gateway-api`/
   `validation-service` templates and descriptions).

## Stories explicitly deferred

None from this backlog — MDF-001 through MDF-005 are now all either done (MDF-001/002/003) or in this
sprint's scope (MDF-004/005). This closes the `backlog-multimodal-dataset-fusion.md` backlog's Must
stories.

## Dependency/sequencing note

- MDF-004 depends on MDF-001 (done) and MDF-003 (done, Sprint 36) — it now has the real assembled shape
  (`feature_dataset.py`'s `FeatureDatasetAssembler.assemble()` output: an aligned multi-column
  `DataFrame`/index, not yet wired into any candidate-model inference call) to evaluate the existing
  `Baseline` protocol against.
- MDF-005 depends on MDF-003 (done) for the lineage data it renders — no dependency on MDF-004.

## High-scrutiny flag for MDF-004 — Tech Lead attention required

- This is analysis/documentation-first: a written decision on whether `Baseline`'s existing
  `predict(train: pd.Series, test: pd.Series) -> pd.Series` signature
  (`libs/naive_first_engine/src/naive_first_engine/baselines.py:16-31`) stays untouched, or whether a
  new, additive interface is needed for a multi-column-consuming candidate model — not a modification
  to `Naive0`/`NaiveLast`/`dm_test.py`'s existing behavior.
- Per the backlog's acceptance criteria: any new interface must be additive (kept alongside `Baseline`,
  not a change to it), proven not to alter the existing `naive_first_engine` regression suite results
  (1h/6h/24h, run unmodified), and must confirm `generate_splits`'s purge-gap logic applies identically
  regardless of univariate/multivariate model input.
- **If a new interface is added**, it requires an explicit extra reviewer pass focused on leakage
  safety, named in the PR/ticket title — this is not satisfied by ordinary code review. The Tech Lead
  should plan for this reviewer pass as a distinct step, not fold it into the same pass that reviews
  MDF-005's copy changes.
- If the analysis concludes no interface change is needed, that conclusion still needs to be written
  down and reviewed (not just implied by inaction) — the deliverable is the written analysis either way.

## Definition of done for this sprint

- MDF-004: written analysis exists (ticket-linked), states the `Baseline`-protocol-unchanged-or-extended
  decision explicitly, existing `naive_first_engine` regression suite passes unmodified, purge-gap
  behavior confirmed identical for both input shapes, and — if a new interface was added — the
  leakage-safety reviewer pass is recorded as done before sign-off.
- MDF-005: banned-word grep test (reusing the FHS-003/FHS-004 pattern) added and passing against all
  new multimodal-result templates/copy; run detail views show feature-set composition inline with the
  standard naive-baseline + candidate-model + DM-verdict presentation, no separate "multimodal mode"
  visual treatment; not-beat-naive results on multi-source runs render with identical neutrality to
  single-series runs; any external-facing copy states this answers a validation question, not a
  prediction-improvement claim.
- QA sign-off (`qa` agent / `/qa-validation`) obtained before either story is marked done, per this
  project's standing QA-gate rule.
- `docs/tickets/README.md`, `libs/naive_first_engine/README.md` (if touched), and relevant service
  READMEs updated to reflect status/contract; `docs/product/backlog-multimodal-dataset-fusion.md`'s
  MDF-004 and MDF-005 entries marked done with acceptance-criteria boxes checked.

## Ticket assignment

Tech Lead owns ticket numbering and further breakdown (e.g. whether MDF-004 splits into an analysis
ticket plus a conditional follow-up implementation ticket if a new interface is warranted, and which
service(s) MDF-005's copy changes land in). This sprint plan assigns story-level scope only.
