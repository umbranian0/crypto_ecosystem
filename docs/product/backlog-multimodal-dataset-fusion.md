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

As the Tech Lead/Architect, I need a written decision on where multi-source dataset assembly lives and what each
connector type's leakage risk is, before any join code is written, because this determines whether the work is a
`validation-service` extension or new scope, and because getting a connector's lag/leakage treatment wrong
directly threatens this platform's core validity claim.

Acceptance criteria:
- ADR (or dated `services/validation-service/README.md` section, matching this repo's existing pattern for
  scope decisions) states: (a) where the join happens — most likely a new dataset-assembly step inside
  `validation-service` that resolves N `{source, field}` references into one aligned feature table before
  `naive_first_engine` is invoked, versus a standalone feature-store service — with a stated reason if it's not
  the validation-service-extension option; (b) whether this counts as pulling a component forward against an
  un-fired trigger (per `implementation-plan.md`'s trigger table) and, if so, the same ADR-0003-style disclosure
  already used for the two prior ingestion-connector pull-forwards.
- For each of the three existing connector types (price, on-chain, sentiment), the ADR documents: known
  publication/confirmation lag, whether any field can be revised after initial publication, and the resulting
  minimum safe purge-gap or alignment rule for that source — reusing/extending the "documented causal lag"
  concept `docs/solution-design.md` already assigns to the sentiment/on-chain connector, rather than inventing a
  new one.
- Explicitly confirms or corrects this backlog's reading of `CompositeDatasetSource` (finding #4 above) — states
  whether it already supports multi-field composition or is single-field-with-fallback-sources only.
- No fusion or join code is written until this closes.

### MDF-002 — Timestamp alignment / frequency-reconciliation design for a multi-source feature set [Must]

As the Tech Lead, I need a documented alignment strategy for combining series sampled at different frequencies
(e.g. minute-level price, hourly on-chain, daily-or-irregular sentiment) into one row-aligned table, because
`naive_first_engine`'s splitter assumes one coherent `DatetimeIndex` and every existing connector samples on its
own schedule.

Depends on: MDF-001.

Acceptance criteria:
- Design doc states, per source-pair, the resampling/alignment rule (e.g. forward-fill a slower series onto the
  faster series's index, only ever using values timestamped strictly before or at each row's own timestamp minus
  that source's confirmed lag from MDF-001 — never interpolating using a future-dated value).
- States the missing-timestamp policy (drop the row vs. carry-forward vs. exclude the source from that run) and
  requires it be a config choice recorded on the run, not a silent default, so two runs' results are comparable
  when they use different policies.
- States how the final aligned table's own `DatetimeIndex` is derived (which source's clock is authoritative)
  and confirms this index is what gets passed to `generate_splits` unchanged — i.e. this step happens strictly
  before splitting/purge-gap, never after, so the purge gap still operates on the real combined-data risk window.
- Includes at least one worked example combining real data from two of the three existing connectors, showing
  the aligned table and calling out any row dropped or filled.

### MDF-003 — `validation-service` dataset assembly for a multi-source feature set [Must]

As a tenant, I want to specify multiple `{source, field}` references when submitting a validation run so my
candidate model can be scored using a combined feature set instead of a single series, while the run is still
validated against the same naive-first baselines on the same target return series as every other run.

Depends on: MDF-001, MDF-002.

Acceptance criteria:
- `POST /runs` (or a new endpoint, per MDF-001's decision) accepts a list of `{source, field}` feature
  references in addition to the existing single target-series reference; the **target** being validated remains
  exactly one return series — this story does not change what is being predicted, only what a candidate model is
  allowed to see as input.
- The assembled multi-column feature table is what gets handed to the candidate model's `predict`/inference path;
  `Naive0`/`NaiveLast` continue to operate on the target Series alone, unchanged from today — this story does not
  modify `naive_first_engine`'s `Baseline` protocol or `dm_test.py` (see MDF-004 for the one place engine changes
  might be needed, and only if MDF-004 finds it necessary).
- Preprocessing applied to feature columns (scaling, imputation) is fit on the training fold only, per split,
  per CLAUDE.md's leakage rule — verified by a test that a fold's fitted preprocessing parameters differ from
  another fold's and that no global fit path exists.
- The persisted run record stores which sources/fields composed its feature set (dataset lineage), so a run
  using multimodal features is distinguishable from a single-series run in the API response and in any dashboard
  view built later.
- A run submitted with feature references from a connector still mid-crawl or with `data-quality gate` (per
  `ingestion-service`'s README, still "not yet built") concerns is rejected with an explicit error rather than
  silently validating on partial data — same fail-closed posture as the existing single-series path.

### MDF-004 — Confirm (or extend) `naive_first_engine`'s interfaces for multi-column model input [Must, high scrutiny]

As the Tech Lead, I need an explicit, reviewed answer on whether `naive_first_engine`'s public types need to
change to support a multi-column candidate-model input, because this library is the platform's core IP and any
change to it carries more risk than an equivalent change anywhere else in the codebase.

Depends on: MDF-001, MDF-003 (needs to know the actual shape MDF-003 assembles).

Acceptance criteria:
- Written analysis states whether the existing `Baseline` protocol's `predict(train: pd.Series, test: pd.Series)`
  signature can stay untouched (most likely — it currently governs only naive baselines and DM-test error
  Series, not the candidate model's own inference call) or whether a *new*, separate interface is needed for
  "a candidate model that consumes a multi-column feature DataFrame and emits a Series of predictions on the
  same target," kept as an addition alongside the existing `Baseline` protocol rather than a modification to it.
- If a new interface is added, it is proven not to change `Naive0`/`NaiveLast`/`dm_test.py`'s behavior or
  existing test results — the full existing `naive_first_engine` regression suite (1h/6h/24h) passes unmodified.
- Confirms `generate_splits`'s purge-gap logic is applied identically regardless of whether the model side is
  univariate or multivariate — the purge gap protects the target/test-fold boundary, not the feature count, and
  this story must not accidentally narrow or skip it for the multivariate path.
- Any change to `libs/naive_first_engine` in this story is called out by name in the PR/ticket title and gets an
  explicit extra reviewer pass (leakage-safety-focused), per this document's own "high scrutiny" flag — not
  merged as an incidental part of a validation-service story.

### MDF-005 — Positioning and copy discipline for multimodal validation results [Must]

As a Product Owner, I want every surface that shows a multimodal validation run's result to frame it strictly as
"does more data help this model beat naive, honestly measured" — matching this platform's existing convention —
so a beat-naive or not-beat-naive result from a richer feature set is never read as this platform now producing
better predictions.

Depends on: MDF-003 (needs the run/lineage data to render).

Acceptance criteria:
- Any run detail view or API description showing a multi-source run states the feature-set composition (which
  sources/fields) next to the same naive-first-baseline + candidate-model + DM-verdict presentation every other
  run already uses — no separate "multimodal mode" visual treatment that implies elevated confidence.
- Banned-word grep test (reusing the pattern from `docs/product/backlog-forecast-horizon-summary.md`'s FHS-003/
  FHS-004) covers this feature's new templates/copy for "prediction," "forecast," "signal," "alpha," "edge."
- A not-beat-naive result on a multi-source run is presented with identical neutrality/formatting to a
  not-beat-naive result on a single-series run — no story in this backlog treats a null result as a feature
  failure to be minimized in the UI.
- Any external-facing description of this feature (docs, marketing-adjacent copy) states plainly that this
  answers a validation question, not a claim that multimodal data improves prediction — consistent with
  CLAUDE.md's "statistical accuracy != economic value" separation.

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
