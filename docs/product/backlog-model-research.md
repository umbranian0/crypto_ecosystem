# Backlog — Model Research (Phase 3, `research/`)

Source: `docs/da-tese-ao-produto.md` (sections 1.3, 1.5, 1.6, 2.6 roadmap Phase 3), `libs/naive_first_engine/README.md` (public API, `Baseline`/`config.extra_baselines` contract, "Owns/Does not own"), `docs/product/backlog-multimodal-dataset-fusion.md` + ADR-0008/0009 (MDF-001/002/003 decisions, MDF-004 deferred), `docs/implementation-plan.md` section 6 (trigger table) and its folder layout (`research/` = "phase-3 applied research, unchanged"), `research/README.md` (status: not started).

**Scope confirmation**: this is legitimate model-improvement research, explicitly requested and explicitly accepted as uncertain-outcome by the requester. It is not a pivot to a trading-signal product (CLAUDE.md non-negotiable positioning stands unchanged). Every story below is either (a) a research question tested under the existing honest protocol, or (b) infrastructure/plumbing needed to run that question — never a feature that assumes or promises the answer is "yes, we beat naive."

**Trigger status**: `research/` exists today only as a placeholder directory + README stating "Status: not started" (per `docs/implementation-plan.md`'s folder layout, "phase-3 applied research, unchanged"). This backlog is the first work proposed to actually populate it. I'm treating the user's explicit request this session as the trigger event for `research/` — flagging this for the requester's confirmation rather than assuming it silently, since implementation-plan.md's trigger table (section 6) is otherwise the sole authority on when a module starts.

## Architecture decision this backlog assumes (flagged for explicit sign-off — see summary)

`research/` code calls `naive_first_engine` as a **library dependency only**, the same way `services/validation-service` does. It never modifies `naive_first_engine`'s source, never forks the leakage-safety logic, and any new baseline/candidate model research needs is wired in through the **existing, unmodified `config.extra_baselines: list[Baseline]` extension point** in `protocol.py` (confirmed this session — `run_validation_protocol` already iterates `config.extra_baselines` alongside the built-in Naive0/NaiveLast). A candidate model becomes a `Baseline` implementation (the `Strategy` pattern already in place) with a `.predict(train, test) -> pd.Series` method; it is fit inside the existing per-split loop, so it inherits purge-gap enforcement, train-fold-only fitting, and DM-vs-Naive0 comparison for free, with zero new leakage surface. If any research direction turns out to need something the `Baseline` protocol genuinely can't express (e.g. a model needing more than train/test series — see MDF-004's open question about multi-column feature input), that is treated as a high-scrutiny, extra-reviewer-pass change to `naive_first_engine` itself, not a research-side workaround — never silently bypassed.

## What does NOT change (binding on every story below, no exceptions)

- Purge-gap enforcement (`splitting.generate_splits`) is never disabled, shortened, or bypassed for a research run.
- Every research candidate is compared against Naive0/NaiveLast — no candidate model story ships without the mandatory naive-baseline comparison.
- Any DM-test claim on 6h/24h (overlapping) horizons uses the Harvey et al. (1997) correction already in `dm_test.py` — no research-only shortcut statistic.
- Preprocessing (scaling, feature engineering, imputation) is fit on the training fold only, per split, exactly as CLAUDE.md requires — this applies to every new feature-engineering story here as much as it did to the original OLS/RF/ARIMA work.
- Negative results are reported through the same report/reporting-service pipeline as positive ones — there is no separate, lower-scrutiny "research results" channel. A story that concluded "no improvement" is a *complete*, valuable, closed story, not a failed one.
- No story here implies or claims trading/economic value. Statistical improvement over naive (if found) still does not authorize any profitability claim — that requires the deferred `economic-service` (trigger #11), unchanged.

## Prioritization

MoSCoW, one-line rationale per story tied to the thesis's own stated gaps (section 1.6) and the `Baseline`/`extra_baselines` extension point.

## Stories

### MR-001 — Returns-vs-levels methodology audit [Must]
**As a** validation engine user (internal: `validation-service`/`dashboard-web` operators), **I want** a documented, tested rule that a dataset submitted as raw price levels is either rejected or auto-transformed to returns before any Naive0 comparison runs, **so that** the "misleading Naive0 comparison on levels" risk (currently only a UI tooltip caveat) becomes an enforced methodology guarantee, not an easily-missed hint.

Acceptance criteria:
- [ ] A documented decision (ADR or ticket) states whether this check lives in `validation-service` (input validation, before calling `naive_first_engine`) or as a new, explicit precondition check inside `naive_first_engine` itself — respecting the "owns/does not own" boundary in `libs/naive_first_engine/README.md`.
- [ ] A stationarity/level-detection check (e.g. ADF test or a simpler heuristic) exists with a unit test proving it flags a synthetic non-stationary (price-level-like) series and passes a synthetic returns series.
- [ ] The existing UI tooltip in `run_new.html` is not removed but is now backed by an enforced check, not just advisory text.
- [ ] No change to `naive_first_engine`'s public `Baseline`/`generate_splits`/`dm_test` signatures.

Rationale for priority: this is a methodology correctness fix flagged by the thesis's own target-choice ("retorno direto, não preço em nível," section 1.2) and by the platform's own existing UI caveat — fixing it is cheap, has no uncertain research outcome, and protects every downstream research story from a false "beat naive" result caused by comparing on levels.
Depends on: none

### MR-002 — Engineered feature set: rolling volatility and rolling-return statistics [Should]
**As a** research candidate model, **I want** a documented, leakage-safe feature-engineering function (rolling volatility, rolling mean/std of returns, lagged returns) computable per training fold only, **so that** candidate models in MR-004/MR-005 have engineered inputs beyond raw returns to test against naive, matching the thesis's explicit future-work gap ("dados exógenos... features engenheiradas," section 1.6).

Acceptance criteria (see `docs/tickets/MR-002.md` — done):
- [x] Feature functions live in `research/` (or a `research/features.py` module), not inside `naive_first_engine`, and take only a train-fold `Series` as input — no global fit.
- [x] Each function has a unit test proving it uses no data past its own fold boundary (e.g. asserting output length/window alignment against a synthetic series with a known future value that must not leak in).
- [x] A short note states explicitly this is a research question, not a guaranteed improvement: whether these features help is answered by MR-004/MR-005's DM-test results, not assumed here.

Rationale for priority: directly extends the thesis's own stated future-work table (section 1.6, "Comparação alargada de modelos" implies richer features too) and is a prerequisite for any non-trivial candidate model story; kept to "Should" not "Must" because MR-001 (methodology correctness) and the plug-in mechanism (MR-004) matter more first.
Depends on: none

### MR-003 — Multimodal fusion inputs feed into research candidates (bridges MDF-003) [Should] — **done (Sprint 41, `docs/tickets/MR-003.md`)**
**As a** research candidate model, **I want** the aligned multi-source feature table produced by MDF-003 (once built, in `validation-service`) to be consumable by a `research/`-side candidate model without duplicating the alignment/purge-gap logic ADR-0008/0009 already specified, **so that** on-chain/sentiment features (the thesis's stated coverage gap, section 1.5/1.6) can be tested as real candidate-model inputs, not just theoretically.

Acceptance criteria:
- [x] A documented interface (e.g. "research code calls `validation-service`'s existing API/exported dataset, never re-implements `CompositeDatasetSource` or the `fetched_at`-based alignment rule from ADR-0008") is written before any research code touches multimodal data. See `research/README.md`'s "Multimodal feature interface (MR-003)" section.
- [x] Explicitly blocked, with the blocking condition stated: MDF-003 itself shipped (Sprint 36), but `validation-service` exposes no export endpoint for the assembled table yet — that is the actual, revised blocking condition this ticket discloses, per sprint-41.md's pre-read finding.
- [x] No `naive_first_engine` change (per ADR-0008's own finding that the engine needs no edit for aligned-table consumption); any need for a multi-column `Baseline` input surfaces as MDF-004's open question (already answered additively by ADR-0010's `CandidateModel` interface), not solved ad hoc here.

Rationale for priority: "Should" not "Must" because it is explicitly gated on MDF-003 landing first (a separate, already-scoped backlog item) — sequencing dependency, not lower research value; this is the most direct link between the ADR-approved fusion work and genuine model improvement.
Depends on: MDF-003 (external, tracked in `docs/product/backlog-multimodal-dataset-fusion.md`)

### MR-004 — Gradient boosting candidate as a `Baseline` implementation [Should]
**As a** research candidate model, **I want** a gradient-boosting model (e.g. LightGBM/XGBoost) wrapped as a `Baseline` implementation (`.predict(train, test) -> pd.Series`, `.name` attribute) registered via `config.extra_baselines`, **so that** it runs through the exact same purge-gap, train-fold-only-fit, DM-vs-Naive0 protocol as OLS/RF/ARIMA did in the thesis, on a model class the thesis's own section 1.6 names as untested ("Boosting, GRU, Transformer ainda não testados").

Acceptance criteria:
- [x] `research/models/gradient_boosting.py` (or similar) implements the `Baseline` protocol exactly as documented in `libs/naive_first_engine/README.md`'s public API — no edits to `naive_first_engine` itself.
- [x] Fit happens strictly inside the per-split training fold (no global fit) — test asserts the model object is re-instantiated/re-fit per split, not reused stale across splits.
- [x] Full run at 1h and 6h horizons produces a `SplitResult` set with MAE/RMSE/DA/F1 and a DM-vs-Naive0 verdict count, in the exact same report shape as the thesis's OLS/RF rows (section 1.3) — enabling direct side-by-side comparison.
- [x] The story's "definition of done" explicitly includes reporting the result honestly regardless of outcome — beating or not beating naive are both valid closes.

Shipped: Sprint 41, `docs/tickets/MR-004.md`, light-compute-scoped (3,000-row seeded synthetic series, fixed hyperparameters, CPU-only, 1h/6h horizons only) per this section's own dataset ambiguity note.

Rationale for priority: the single most direct match to the thesis's explicit "not yet tried" list and the lowest-friction plug-in point (`extra_baselines` already exists, purpose-built for exactly this); "Should" not "Must" because MR-001 must land first to avoid a levels-vs-returns false positive.
Depends on: MR-001

### MR-005 — Regime-sensitive (HMM/hybrid) candidate as a `Baseline` implementation [Could] — **done (Sprint 42, `docs/tickets/MR-005.md`), scope narrowed to a 2-state HMM per sprint-42.md's compute-budget decision**
**As a** research candidate model, **I want** a regime-switching or hybrid model (e.g. a hidden Markov model gating a simple linear model per regime) wrapped as a `Baseline` implementation, **so that** the thesis's top-listed future direction ("Modelos sensíveis a regime... estrutura preditiva pode depender do estado do mercado," section 1.6, motivated by the volatile OOS window itself: ETF approval + April 2024 halving) gets tested under the same honest protocol.

Acceptance criteria:
- [x] Same `Baseline`-protocol, same per-split fit-on-train-only, same DM-vs-Naive0 reporting shape as MR-004.
- [x] Regime detection/fit itself happens on the training fold only, per split — no regime labels computed globally across the whole series (this is exactly the leakage failure mode CLAUDE.md warns about, applied to a less obvious case: regime state is often computed with hindsight).
- [x] Result reported honestly regardless of outcome, same as MR-004.

Shipped: Sprint 42, `docs/tickets/MR-005.md`, light-compute-scoped (fixed 2-state Gaussian HMM, no state-count search, same MR-004 3,000-row seeded synthetic series, fixed hyperparameters, CPU-only, 1h/6h horizons only) per the ticket's own compute-budget ceiling section.

Rationale for priority: "Could" not "Should" — this is a materially harder modeling problem (regime detection itself needs care to avoid look-ahead) with higher research-time cost and a less certain path to even a clean negative result; sequenced after the simpler MR-004 boosting story to establish the research-to-report pipeline first.
Depends on: MR-001, MR-004 (establishes the pipeline/report shape reused here)

### MR-006 — Per-split explainability artifacts [Could]
**As a** future reader of a research run's report (internal: whoever is deciding whether a candidate model's marginal DM win is worth productionizing), **I want** feature-importance or SHAP values persisted per split alongside each split's metrics, **so that** the thesis's stated gap ("Explicabilidade consistente por split... Arquivo não guarda feature importance/SHAP por split," section 1.6) is closed for any new candidate model.

Acceptance criteria:
- [ ] Explainability artifacts are computed from the same per-split fitted model object already produced by the `Baseline.predict` call — no separate, unaudited refit.
- [ ] Artifacts are stored/reported through the existing report pipeline (same reporting-service path as metrics), not a parallel ad hoc file dump.
- [ ] Explicitly out of scope for MR-004/MR-005's initial "does it beat naive" question — this is additive instrumentation, not a precondition for those stories to close.

Rationale for priority: valuable but not required to answer the core research question (does anything beat naive); "Could" reflects it's an enhancement to reporting depth, sequenced after at least one candidate model exists to explain.
Depends on: MR-004

### MR-007 — Read-only export endpoint for an already-executed run's assembled feature table [Should] — Done, see `docs/tickets/MR-007.md`
**As a** `research/`-side candidate model (calling `validation-service` by Compose hostname, never via `app.*` import, per MR-003's documented interface), **I want** a single read-only `GET` route on `validation-service` that re-produces and returns the multi-column feature table `FeatureDatasetAssembler.assemble` built for a specific, already-executed `{tenant_id, run_id}`, **so that** MR-003's disclosed gap (no export endpoint exists today; `assemble`'s output is only ever consumed internally by `routers/runs.py::create_run` and immediately reduced to a re-indexed target series) is closed with the smallest possible surface, letting research candidates train on real multimodal data instead of synthetic.

Keying and response-shape decisions (made explicitly, per this story, not left to implementation):
- **Keyed by `run_id`, not by fresh `{feature_references, missing_timestamp_policy}` params.** A run's `feature_lineage` (VS-030, `runs.feature_lineage` column, migration `0009_add_runs_feature_lineage_column.py`) already persists the feature references and assembly parameters an existing run used. The endpoint re-invokes `FeatureDatasetAssembler.assemble` with those persisted, already-validated parameters — it does not accept new/ad-hoc feature-reference lists from the caller. This avoids standing up a second validation path for arbitrary feature-reference input (which `POST /runs` already owns) and avoids a new request-parsing/validation surface, at the cost of only being able to export tables for runs that already exist — an acceptable trade for a first cut.
- **Plain JSON body, not an object-storage pointer.** Grepped `feature_dataset.py` and `validation-service/README.md`'s "Multi-source feature assembly" section for any documented row-count/size expectation — none exists; no evidence the assembled tables are large enough to need the `{"object_key": ...}` indirection `ObjectStorageDatasetSource` uses elsewhere. Per this session's "don't over-engineer" instruction, ship the simpler JSON-serializable multi-column time-indexed table first; revisit as a follow-up story only if a real table size problem is observed.

Acceptance criteria:
- [x] A new route, `GET /runs/{run_id}/features` (or equivalent path under the existing `/runs/{run_id}` resource), is added to `services/validation-service/src/app/routers/runs.py`, tenant-scoped through the same `X-Tenant-Id`/API-key dependency every other route in this router already uses — no new auth mechanism.
- [x] The route re-invokes `FeatureDatasetAssembler.assemble` using the target run's persisted `feature_lineage`-derived parameters, returning `404` if the run has no multimodal feature lineage (`has_multimodal_features` is `False`) — this is a re-export, not a new assembly configuration surface. **Disclosed deviation (a real, documented schema gap — see `docs/tickets/MR-007.md`'s Analysis section)**: `runs.missing_timestamp_policy` and the original `dataset_reference` are not persisted anywhere, so the route cannot literally reuse "the same `missing_timestamp_policy` that run originally used" as this bullet originally envisioned — `missing_timestamp_policy` is instead accepted as an optional query param (default `"drop_row"`), and the primary series is reloaded via `dataset_source.load({"source": run.dataset_id})`, which only works for ingestion-service-backed runs (`422` otherwise). Not solved ad hoc — flagged as the correct scope for a follow-up ticket if this limitation proves to matter.
- [x] Response body is a JSON-serializable representation of the assembled multi-column, time-indexed table (e.g. `{"index": [...], "columns": [...], "data": [[...], ...]}` or the project's existing DataFrame-to-JSON convention if one is already established elsewhere in this service) — no object-storage pointer in this first cut.
- [x] `routers/runs.py::create_run`'s existing internal call path (assemble → `series.loc[assembled.index]` → `run_validation_protocol`) is unchanged — this story is strictly additive (one new `GET` route); a test diff/review confirms zero lines changed in `create_run` itself.
- [x] A test proves the exported table for a given `run_id` is reproducible/consistent with what that run's own lineage records (same columns, same index range) — not merely "returns 200."
- [x] `services/validation-service/README.md`'s "Routes" list (machine-checked by `scripts/check_doc_sync.py`) and its "Multi-source feature assembly (VS-030/MDF-003)" section are updated to reflect the new route and that the previously-disclosed gap (MR-003, `docs/tickets/MR-003.md`) is now closed.
- [x] No change to `libs/naive_first_engine` and no new alignment/fusion logic — the route only calls the existing `FeatureDatasetAssembler`, never re-implements `CompositeDatasetSource` or ADR-0008's `fetched_at`-based alignment rule.

Rationale for priority: "Should" not "Must" — it directly unblocks MR-003's disclosed gap and is small/additive, but is not required for MR-004/MR-005 (which train on the returns series ± MR-002's engineered features, not multimodal data yet); sequenced as soon as convenient after MR-003 rather than gating the current research pipeline.
Depends on: MR-003 (interface already documented), MDF-003/VS-030 (external, `docs/product/backlog-multimodal-dataset-fusion.md` — already shipped, per MR-003)

## What "success" looks like, stated explicitly

Success for this backlog is **not** "a model beats naive." Success is: every story above executes under the unmodified leakage-safe protocol and produces an honestly reported result — beating naive with statistical significance (Harvey-corrected DM, Naive0 baseline, purge-gap enforced) counts as success; *not* beating naive, again, is an equally valid, complete, reportable outcome, and is exactly the kind of result this platform's audit/validation credibility is built on being willing to publish. If every candidate here fails to beat naive, that is not a failed sprint — it is a second, independently-obtained confirmation of the thesis's core finding, on model classes (boosting, regime-switching) the thesis itself flagged as untested, which is itself valuable evidence for the product's "we tested this honestly, including the things that didn't work" positioning (`da-tese-ao-produto.md` section 2.5).
