# Backlog — Multimodal Dataset Fusion (validation-service / naive_first_engine / ingestion-service)

Source: `CLAUDE.md` (core finding, non-negotiable positioning), `docs/da-tese-ao-produto.md` (thesis's own
multimodal gap, section on "Cobertura exógena real"), `docs/solution-design.md` (ingestion → storage →
processing → validation architecture, sentiment/on-chain connector phasing), `docs/implementation-plan.md`
sections 2-6 (module scope + trigger table), `services/ingestion-service/README.md`, `libs/naive_first_engine`
source (`baselines.py`, `splitting.py`, `dm_test.py`), `docs/product/backlog-ingestion-pipeline-integration.md`,
`docs/product/backlog-forecast-horizon-summary.md` (positioning-discipline precedent this backlog reuses).

## The request, as asked, and what it actually requires

The request is: let a candidate model be validated against a dataset that combines multiple data sources —
price, hash rate (on-chain), sentiment — instead of a single price series, still benchmarked against naive-first
under the existing walk-forward/purge-gap/DM-test protocol. This is a legitimate, on-brand question: the thesis
itself (`docs/da-tese-ao-produto.md`) flagged its own multimodal coverage as "muito abaixo do desenho
conceptual — não é um teste multimodal 'cheio'" and named this exact gap as Phase 2 work. Nothing here proposes
producing a better prediction — it proposes finding out, honestly, whether more data changes the answer.

## Key findings from reading the current code (binds scope below)

1. **Multimodal ingestion already exists; multimodal *fusion* does not.** `ingestion-service` already runs three
   working connectors per tenant on independent schedules — `BinancePriceConnector` (price/OHLCV),
   `BlockchainInfoConnector` (parameterized for hash-rate and other on-chain metrics), and
   `RedditSentimentConnector` (sentiment) — each queryable via `GET /datasets/{source}/series`. There is no
   component anywhere that joins two or more of these into one aligned table for a single validation run. This is
   the actual gap, not "we need a fourth connector."
2. **Ingestion serves raw levels, not returns, and nothing computes returns from them.** Per
   `services/ingestion-service/README.md`: "computing a returns series before validating is the caller's
   responsibility today," and whether that transform belongs in ingestion, validation-service, or stays the
   caller's job is explicitly left open. A multimodal-features story inherits this same open question, twice
   over — once for the price series being turned into the target return, and again for whether raw on-chain/
   sentiment levels get any transform (e.g. differencing, z-scoring) before being used as model features.
3. **`naive_first_engine` is strictly univariate today, at the type level, not just by convention.** The
   `Baseline` protocol (`baselines.py`) is `predict(self, train: pd.Series, test: pd.Series) -> pd.Series` — a
   single `Series` in, a single `Series` out; `Naive0`/`NaiveLast` both implement exactly that. `dm_test.py` takes
   pre-computed per-point error `Series`/arrays for one model against Naive0's errors on one split. `splitting.py`
   operates only on a `DatetimeIndex` and is column-count-agnostic — it does not need to change. **This means the
   engine's core naive-baseline and DM-test logic never needs to see more than one column; only what feeds a
   *candidate model* (never the naive baselines, never the target) could plausibly become multi-column.**
4. **`validation-service` runs exactly one dataset/field per run today.** Its `DatasetSource` abstraction
   (`InlineOrLocalFileDatasetSource` / `ObjectStorageDatasetSource` / `CompositeDatasetSource`, per
   `backlog-ingestion-pipeline-integration.md`'s Epic C) resolves to a single `{source, field}` series per run.
   `CompositeDatasetSource`'s existing name is a false friend here — confirm in ticket breakdown whether it
   already composes multiple *fallback* sources for one field (likely) versus multiple *simultaneous* fields
   (needed for this backlog and, per current reading, not present) before assuming it's reusable as-is.
5. **No feature-store/join-engine component exists, and nothing in the trigger table names one.**
   `implementation-plan.md`'s trigger table covers ingestion connectors (#6, #10) and validation-service running
   `naive_first_engine` against one dataset (#3) but has no line item for "combine N datasets into one aligned
   input." This is new scope. It most naturally extends `validation-service` (it already owns "assemble input for
   a run") rather than justifying a new service — see MDF-001's explicit recommendation and the Tech Lead
   questions at the end of this document.
6. **Leakage risk is real and source-specific, not generic.** Sentiment connectors can carry lookahead/revision
   risk (a "sentiment score for day D" that was computed or revised using information published after day D's
   close); on-chain metrics can have reporting/confirmation lag (a hash-rate estimate for a given block interval
   may not be available until after that interval closes). Both interact directly with the purge-gap protocol
   that is this platform's core IP — a naively-joined multimodal dataset could reintroduce exactly the leakage
   failure mode CLAUDE.md says the whole business case is built on avoiding.

## Framing decision (binding on every story below, reusing `backlog-forecast-horizon-summary.md`'s pattern)

Every story and its UI/API copy describes this feature as testing **whether adding data sources changes whether
a candidate model beats naive-first, under the same leakage-free validation protocol** — never as "richer data
will make predictions better." The words "prediction," "forecast," "signal," "alpha," or "edge" do not appear in
this feature's UI, API descriptions, or exported text; permitted vocabulary is "candidate model," "feature set,"
"validation result," "backtested performance," matching FHS's existing restriction. Every run built from a
multi-source feature set still renders naive-first baseline value + candidate-model value + DM verdict together,
never the model number alone, per CLAUDE.md's "any comparison must default to naive-first" rule. A run using a
multi-source feature set is visibly labeled as such in its record (dataset lineage — which sources/fields
composed it) so a beat-naive result can't be silently read as "price alone was enough," and a not-beat-naive
result is reported with the same neutrality as every other validation run — a null result here is exactly the
kind of honest finding this platform exists to surface.

## Stories

### MDF-001 — Decide the fusion architecture and leakage posture per connector type [Must, blocking]

**Status: Done (Sprint 31).** See `docs/adr/0008-multimodal-fusion-architecture-and-leakage-posture.md`
(accepted). No source code was written or touched — decision-work only, per this story's own acceptance
criteria.

As the Tech Lead/Architect, I need a written decision on where multi-source dataset assembly lives and what each
connector type's leakage risk is, before any join code is written, because this determines whether the work is a
`validation-service` extension or new scope, and because getting a connector's lag/leakage treatment wrong
directly threatens this platform's core validity claim.

Acceptance criteria:
- [x] ADR (or dated `services/validation-service/README.md` section, matching this repo's existing pattern for
  scope decisions) states: (a) where the join happens — most likely a new dataset-assembly step inside
  `validation-service` that resolves N `{source, field}` references into one aligned feature table before
  `naive_first_engine` is invoked, versus a standalone feature-store service — with a stated reason if it's not
  the validation-service-extension option; (b) whether this counts as pulling a component forward against an
  un-fired trigger (per `implementation-plan.md`'s trigger table) and, if so, the same ADR-0003-style disclosure
  already used for the two prior ingestion-connector pull-forwards.
  Satisfied by ADR-0008 (a): join lives inside `validation-service` (new `feature_dataset.py`, sibling to
  `dataset_source.py`); explicit no-pull-forward finding with reasoning tied to trigger #3 already having
  fired and the module's own README-stated bounded context.
- [x] For each of the three existing connector types (price, on-chain, sentiment), the ADR documents: known
  publication/confirmation lag, whether any field can be revised after initial publication, and the resulting
  minimum safe purge-gap or alignment rule for that source — reusing/extending the "documented causal lag"
  concept `docs/solution-design.md` already assigns to the sentiment/on-chain connector, rather than inventing a
  new one.
  Satisfied by ADR-0008 (b): per-connector table (`BinancePriceConnector`, `BlockchainInfoConnector`,
  `RedditSentimentConnector`) with lag, revision-risk, and minimum purge-gap/alignment rule for each, plus
  the binding `fetched_at`-not-nominal-timestamp constraint carried into MDF-002.
- [x] Explicitly confirms or corrects this backlog's reading of `CompositeDatasetSource` (finding #4 above) — states
  whether it already supports multi-field composition or is single-field-with-fallback-sources only.
  Satisfied by ADR-0008 (c): confirmed (not corrected) as single-reference-with-mode-dispatch only, read
  directly against `dataset_source.py`.
- [x] No fusion or join code is written until this closes.
  Confirmed via `git status`/`git diff` scoped to `libs/naive_first_engine`, `services/validation-service/src/`,
  and every other source tree — commit `fc7b7c0` touched only the two ADRs and `docs/sprints/sprint-31.md`.

### MDF-002 — Timestamp alignment / frequency-reconciliation design for a multi-source feature set [Must]

**Status: Done (Sprint 31).** See `docs/adr/0009-multimodal-timestamp-alignment-design.md` (accepted). No
source code was written or touched.

As the Tech Lead, I need a documented alignment strategy for combining series sampled at different frequencies
(e.g. minute-level price, hourly on-chain, daily-or-irregular sentiment) into one row-aligned table, because
`naive_first_engine`'s splitter assumes one coherent `DatetimeIndex` and every existing connector samples on its
own schedule.

Depends on: MDF-001.

Acceptance criteria:
- [x] Design doc states, per source-pair, the resampling/alignment rule (e.g. forward-fill a slower series onto the
  faster series's index, only ever using values timestamped strictly before or at each row's own timestamp minus
  that source's confirmed lag from MDF-001 — never interpolating using a future-dated value).
  Satisfied by ADR-0009's "Per-source-pair resampling/alignment rule" section (price-onto-price, on-chain-
  onto-target, sentiment-onto-target), all keyed off `fetched_at` per ADR-0008 (b).
- [x] States the missing-timestamp policy (drop the row vs. carry-forward vs. exclude the source from that run) and
  requires it be a config choice recorded on the run, not a silent default, so two runs' results are comparable
  when they use different policies.
  Satisfied by ADR-0009's "Missing-timestamp policy" section: required `missing_timestamp_policy` field
  (`"drop_row"` / `"forward_fill_exhausted_as_null_then_drop"` / `"exclude_source"`), no default, `422` if
  omitted, persisted on the run record.
- [x] States how the final aligned table's own `DatetimeIndex` is derived (which source's clock is authoritative)
  and confirms this index is what gets passed to `generate_splits` unchanged — i.e. this step happens strictly
  before splitting/purge-gap, never after, so the purge gap still operates on the real combined-data risk window.
  Satisfied by ADR-0009's "Authoritative clock for the final aligned index" section: target series' own index
  is authoritative; explicit confirmation `generate_splits` receives it unchanged, strictly before splitting;
  `splitting.py` requires no change.
- [x] Includes at least one worked example combining real data from two of the three existing connectors, showing
  the aligned table and calling out any row dropped or filled.
  Satisfied by ADR-0009's "Worked example" section: `binance_price_btcusdt_1h` (target) +
  `blockchain_info_hash-rate` (feature) over a four-hour window under `"drop_row"`, with the dropped row and
  each forward-filled row called out explicitly.

### MDF-003 — `validation-service` dataset assembly for a multi-source feature set [Must]

**Status: done (Sprint 36, VS-030).** MDF-001 and MDF-002 (Sprint 31) unblocked this story; implemented in full
by `docs/tickets/VS-030.md` — see that ticket and `services/validation-service/README.md`'s "Multi-source
feature assembly" section for the shipped shape.

As a tenant, I want to specify multiple `{source, field}` references when submitting a validation run so my
candidate model can be scored using a combined feature set instead of a single series, while the run is still
validated against the same naive-first baselines on the same target return series as every other run.

Depends on: MDF-001, MDF-002.

Acceptance criteria:
- [x] `POST /runs` accepts a list of `{source, field}` feature references (`feature_references`) in addition to
  the existing single target-series reference; the **target** being validated remains exactly one return series
  — VS-030 does not change what is being predicted, only what a candidate model is allowed to see as input.
- [x] The assembled multi-column feature table (`app.feature_dataset.FeatureDatasetAssembler.assemble`) is what
  would be handed to a candidate model's `predict`/inference path; `Naive0`/`NaiveLast`/`dm_test.py` continue to
  operate on the target Series alone, unchanged — `run_validation_protocol`'s call site is unmodified, and
  `libs/naive_first_engine` is untouched by VS-030's diff (see MDF-004 for the still-deferred question of
  whether a new consumer interface is needed for the candidate-model side).
- [x] Preprocessing applied to feature columns (`FeatureFoldScaler`) is fit on the training fold only, per
  split, per CLAUDE.md's leakage rule — verified by `tests/test_feature_dataset.py`'s hard-gate tests: a
  behavioral test that a fold's fitted parameters differ from another fold's, and a structural (AST-scan) test
  that no function in `feature_dataset.py` computes a mean/std over anything other than the `train_df` argument
  passed to `fit`.
- [x] The persisted run record stores which sources/fields (and each one's applied lag) composed its feature
  set (`runs.feature_lineage`, migration `0009_add_runs_feature_lineage_column.py`), surfaced via
  `RunDetailResponse.feature_lineage`/`has_multimodal_features` so a multimodal run is distinguishable from a
  single-series run in the API response.
- [x] A run submitted with feature references naming a connector still `"running"`/`"queued"`/`"failed"` is
  rejected with an explicit `FeatureDatasetError` before any alignment is attempted
  (`IngestionServiceConnectorStatusChecker`, `GET /connectors/{source}/status`) — same fail-closed posture as
  the existing single-series path. **Disclosed gap, not fixed by VS-030**: `ingestion-service`'s
  `GET /datasets/{source}/series` does not currently expose each row's `fetched_at`, so any feature reference
  that resolves to `IngestionServiceDatasetSource` fails closed with a disclosed error rather than aligning at
  all (ADR-0009's "never use a nominal timestamp as a stand-in for fetched_at" rule) — real per-row `fetched_at`
  alignment is implemented and tested for inline/object-storage-CSV-backed references only; extending
  `ingestion-service`'s endpoint to expose `fetched_at` is flagged as a follow-up, not filed as a numbered
  ticket by VS-030 itself (out of that ticket's file scope).

### MDF-004 — Confirm (or extend) `naive_first_engine`'s interfaces for multi-column model input [Must, high scrutiny] — **DONE** (Sprint 38, `docs/tickets/MDF-004-01.md`, `docs/adr/0010-multimodal-candidate-model-interface.md`, status `accepted`)

As the Tech Lead, I need an explicit, reviewed answer on whether `naive_first_engine`'s public types need to
change to support a multi-column candidate-model input, because this library is the platform's core IP and any
change to it carries more risk than an equivalent change anywhere else in the codebase.

Depends on: MDF-001, MDF-003 (needs to know the actual shape MDF-003 assembles).

Acceptance criteria:
- [x] Written analysis states whether the existing `Baseline` protocol's `predict(train: pd.Series, test: pd.Series)`
  signature can stay untouched (most likely — it currently governs only naive baselines and DM-test error
  Series, not the candidate model's own inference call) or whether a *new*, separate interface is needed for
  "a candidate model that consumes a multi-column feature DataFrame and emits a Series of predictions on the
  same target," kept as an addition alongside the existing `Baseline` protocol rather than a modification to it.
  Answer: `Baseline` stays untouched; a new additive `CandidateModel` protocol added
  (`libs/naive_first_engine/src/naive_first_engine/candidate_model.py`), not wired into any call site.
- [x] If a new interface is added, it is proven not to change `Naive0`/`NaiveLast`/`dm_test.py`'s behavior or
  existing test results — the full existing `naive_first_engine` regression suite (1h/6h/24h) passes unmodified.
  Confirmed: zero-line diff on `baselines.py`/`splitting.py`/`dm_test.py`/`report_schema.py`/`protocol.py`,
  99 passed (95 pre-existing + 4 new), zero existing test files modified.
- [x] Confirms `generate_splits`'s purge-gap logic is applied identically regardless of whether the model side is
  univariate or multivariate — the purge gap protects the target/test-fold boundary, not the feature count, and
  this story must not accidentally narrow or skip it for the multivariate path. Confirmed by
  `tests/test_candidate_model.py::test_generate_splits_same_regardless_of_model_input_shape`.
- [x] Any change to `libs/naive_first_engine` in this story is called out by name in the PR/ticket title and gets an
  explicit extra reviewer pass (leakage-safety-focused), per this document's own "high scrutiny" flag — not
  merged as an incidental part of a validation-service story. Reviewer pass recorded in
  `docs/adr/0010-multimodal-candidate-model-interface.md`'s Consequences section and
  `docs/tickets/README.md`'s Sprint 38 entry.

### MDF-005 — Positioning and copy discipline for multimodal validation results [Must] — **DONE** (Sprint 38, `docs/tickets/MDF-005-01.md`)

As a Product Owner, I want every surface that shows a multimodal validation run's result to frame it strictly as
"does more data help this model beat naive, honestly measured" — matching this platform's existing convention —
so a beat-naive or not-beat-naive result from a richer feature set is never read as this platform now producing
better predictions.

Depends on: MDF-003 (needs the run/lineage data to render).

Acceptance criteria:
- [x] Any run detail view or API description showing a multi-source run states the feature-set composition (which
  sources/fields) next to the same naive-first-baseline + candidate-model + DM-verdict presentation every other
  run already uses — no separate "multimodal mode" visual treatment that implies elevated confidence.
  `_feature_lineage.html` (new partial, `services/dashboard-web`) reuses existing `.chart-container` styling.
- [x] Banned-word grep test (reusing the pattern from `docs/product/backlog-forecast-horizon-summary.md`'s FHS-003/
  FHS-004) covers this feature's new templates/copy for "prediction," "forecast," "signal," "alpha," "edge."
  (word list extended to also include "target"/"recommendation" per this repo's existing FHS-003/004 precedent).
- [x] A not-beat-naive result on a multi-source run is presented with identical neutrality/formatting to a
  not-beat-naive result on a single-series run — no story in this backlog treats a null result as a feature
  failure to be minimized in the UI. Proven by
  `test_run_detail_not_beat_naive_verdict_identical_for_multimodal_and_single_series`.
- [x] Any external-facing description of this feature (docs, marketing-adjacent copy) states plainly that this
  answers a validation question, not a claim that multimodal data improves prediction — consistent with
  CLAUDE.md's "statistical accuracy != economic value" separation. `_feature_lineage.html`'s own caption text
  states this explicitly ("a validation/composition fact only, not evidence that combining sources changes
  the benchmark-comparison verdict").

## Explicitly out of scope for this backlog

- Any new connector type beyond the three that already exist (price, on-chain via blockchain.info, Reddit
  sentiment) — adding a fourth data source is a separate, ordinary ingestion-service story, not part of fusion.
- The ingestion-service data-quality gate and the raw-levels-to-returns transform — both remain open questions
  already flagged in `services/ingestion-service/README.md` and `backlog-ingestion-pipeline-integration.md`;
  this backlog depends on them being resolved sanely but does not resolve them itself.
- A general-purpose feature store or streaming join engine — MDF-001 explicitly favors extending
  `validation-service`'s existing dataset-assembly responsibility over standing up new infrastructure, unless
  the Tech Lead's ADR finds a concrete reason that doesn't hold.
- Any change to `economic-service` or portfolio/profitability framing — untouched, and remains deferred per
  CLAUDE.md until a model beats naive in `validation-service`, multimodal or not.
- Automatic/scheduled multimodal runs (e.g. "always fuse all available sources") — every story here is scoped to
  a tenant explicitly choosing which sources to combine for one run.

## Sequencing note

MDF-001 is a hard blocking architecture/leakage decision, the same role FHS-001 and RAV-001 played for their own
backlogs — nothing else here should be estimated or ticketed until it closes. MDF-002 depends on MDF-001's
component-placement answer but can proceed in parallel with early MDF-004 analysis. MDF-003 depends on both
MDF-001 and MDF-002. MDF-004 should be scoped and reviewed before MDF-003's implementation is considered done,
since MDF-003's actual assembled shape is what MDF-004 needs to evaluate against the engine's interfaces. MDF-005
can start once MDF-003 defines the lineage data it renders. Not sequenced into a sprint yet — this is backlog
only, pending PM sequencing.
