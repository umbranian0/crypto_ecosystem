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

### MR-006 — Per-split explainability artifacts [Could] — **done (Sprint 43, `docs/tickets/MR-006.md`), scope narrowed to feature-importance-only (no SHAP) per sprint-43.md's explicit scope decision**
**As a** future reader of a research run's report (internal: whoever is deciding whether a candidate model's marginal DM win is worth productionizing), **I want** feature-importance or SHAP values persisted per split alongside each split's metrics, **so that** the thesis's stated gap ("Explicabilidade consistente por split... Arquivo não guarda feature importance/SHAP por split," section 1.6) is closed for any new candidate model.

Acceptance criteria:
- [x] Explainability artifacts are computed from the same per-split fitted model object already produced by the `Baseline.predict` call — no separate, unaudited refit.
- [x] Artifacts are stored/reported through the existing report pipeline (same reporting-service path as metrics), not a parallel ad hoc file dump.
- [x] Explicitly out of scope for MR-004/MR-005's initial "does it beat naive" question — this is additive instrumentation, not a precondition for those stories to close.

**Scope reduction, disclosed explicitly**: shipped as feature-importance-only, not full SHAP support — `shap`
was excluded as a new dependency (its `KernelExplainer` path has no natural fit for an HMM-gated model
without inventing a background-distribution/sampling scheme). `LightGBMBaseline` exposes
`LGBMRegressor.feature_importances_`; `RegimeHMMBaseline` exposes per-state `LinearRegression`
`.coef_`/`.intercept_` plus per-row active-state assignment. See `research/README.md`'s "Per-split
explainability artifacts (MR-006)" section and `docs/tickets/MR-006.md` for the full scope decision and
artifact shapes — this backlog entry should not be read as implying full SHAP support shipped.

Shipped: Sprint 43, `docs/tickets/MR-006.md`, `research/explainability.py` (research-side `Baseline`
wrapper Strategy, no `libs/naive_first_engine` change, no new dependency).

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

## Extension: real Bitcoin historical data (MR-008 onward)

**Source for this extension**: `docs/tickets/MR-004.md`, `MR-005.md`, `MR-006.md`, `MR-007.md`, and this file's own `research/README.md`-mirrored sections above (read first, not re-derived). **Scope**: MR-004's `LightGBMBaseline` and MR-005's `RegimeHMMBaseline` were both shipped and tested only on a seeded 3,000-row *synthetic* series (Sprint 41/42's explicit light-compute scoping decision) — both showed no significant, stable improvement over Naive0. Real hourly BTC/USDT OHLC data has been ingested since 2017-08-17 UTC via `services/ingestion-service/connectors/binance_price.py` (source name `binance_price_btcusdt_1h`; see `services/ingestion-service/README.md` lines ~127, ~234, ~436-437) and copied to every tenant as of Sprint 45 (INGEST-010/030, GW-030). There is therefore no external-data-source blocker for this extension — it reaches `validation-service`'s existing `IngestionServiceDatasetSource` (`services/validation-service/src/app/dataset_source.py`), the same `DatasetSource` abstraction `POST /runs`'s `dataset_reference` already dispatches to, requiring no new connector and no change to `naive_first_engine`.

**Binding on every story below, restated per CLAUDE.md and this backlog's own "What does NOT change" section**: no story here may touch, weaken, or shortcut `libs/naive_first_engine`'s leakage-safety machinery (purge-gap enforcement, train-fold-only fitting, DM test) to make a result look better — no random/non-time-ordered splits, no global preprocessing, no leakage shortcut, no exception for compute-time convenience. And: **no product surface, README, UI copy, or customer-facing claim may assert the system predicts Bitcoin prices/futures, unless a candidate model has actually beaten Naive0 with Harvey-corrected DM significance under this protocol on real data.** A "no improvement" result on real data is a complete, valuable, honestly-reported research outcome, not a failed story — exactly the same standard this backlog's "What success looks like" section (below) already states for MR-004–MR-007.

### MR-008 — Re-run MR-004/MR-005 candidates against real BTC/USDT hourly data at 1h/6h [Should] — **done (Sprint 47, `docs/tickets/MR-008.md`)**
**As a** research candidate model already proven on synthetic data (`LightGBMBaseline`, `RegimeHMMBaseline`), **I want** to run against the real `binance_price_btcusdt_1h` returns series (via `IngestionServiceDatasetSource`, not a new connector) at the same 1h/6h horizons MR-004/MR-005 already used, **so that** the synthetic-only result gets its first real-data check under the identical honest protocol, with no new model code required — reusing the existing `config.extra_baselines` plug-in point exactly as MR-004/MR-005 already wired it.

**Bound used (disclosed, per Compute-budget scoping in `docs/tickets/MR-008.md`)**: `tenant_id="271d391dd7bf4213b3e5fb8ea6636563"`, `source="binance_price_btcusdt_1h"`, date range `2026-01-10T00:00:00`–`2026-08-07T09:00:00` (the most recent ~209-day window of the full 2017-08-17–2026-08-07 series), returning **5,026 rows** (5,025 returns after `.pct_change().dropna()`) — not the full ~78,500-row history, to stay CPU-only and under the 5-minute ceiling.

Acceptance criteria:
- [x] `LightGBMBaseline` (MR-004) and `RegimeHMMBaseline` (MR-005) are registered via `config.extra_baselines` and run through the real, unmodified `run_validation_protocol` against a real `binance_price_btcusdt_1h`-derived returns series pulled through a `research/`-owned HTTP client calling `ingestion-service`'s existing `GET /datasets/{source}/series` route directly (not `IngestionServiceDatasetSource` itself, which lives in `services/validation-service`'s `app.*` package and is off-limits to `research/` per CLAUDE.md's "never import another service's app code" rule — see the ticket's Design section for the full reasoning) — no new connector, no direct DB read, no bypass of the ingestion-service HTTP boundary.
- [x] The raw series is transformed to returns (not price levels) before any Naive0 comparison (`raw_series.pct_change().dropna()`, applied in the test before any baseline/Naive0 comparison), consistent with MR-001's methodology.
- [x] Purge-gap enforcement, train-fold-only fitting (including HMM regime-state fitting/decoding, matching MR-005's lag-1/no-current-row-leakage fix), and DM-vs-Naive0 comparison are exercised exactly as in MR-004/MR-005 — no split-generation or fitting-boundary code is modified to accommodate real data (`research/models/*.py` untouched, confirmed via `git status --porcelain research/models` empty).
- [x] Real-data date-range/row-count bound disclosed explicitly (above) — compute-budget scoping, not a data-quality shortcut.
- [x] DM-vs-Naive0 verdict counts reported for both models at both horizons (see below) — beating or not beating naive are both valid closes.
- [x] **Hard gate restated verbatim, honored**: no README/ticket/test copy resulting from this story asserts the system predicts Bitcoin prices — the observed result is "no improvement over Naive0" (see verdict counts below), reported honestly, not softened.

**Observed DM-vs-Naive0 verdict counts** (18 splits per horizon): 1h `LightGBMBaseline` `{'better': 0, 'worse': 4, 'no significant difference': 14}`; 1h `RegimeHMMBaseline` `{'better': 0, 'worse': 0, 'no significant difference': 18}`; 6h `LightGBMBaseline` `{'better': 0, 'worse': 2, 'no significant difference': 16}`; 6h `RegimeHMMBaseline` `{'better': 0, 'worse': 0, 'no significant difference': 18}`. Neither model beat Naive0 in a stable way — consistent with the synthetic-data finding (MR-004/MR-005) and the thesis's own core finding, now confirmed a second time on real, recent BTC/USDT data.

Rationale for priority: "Should" — this is the lowest-friction, highest-information extension available (no new model code, existing plug-in point, existing real-data path already shipped by Sprint 45), and it is the second, independent test needed before any 24h/feature-engineering extension is worth doing; not "Must" because a synthetic-data negative result already exists and this platform's core finding is not contingent on this story landing on any particular schedule.
Depends on: MR-004, MR-005 (candidate models), MR-001 (levels-vs-returns enforcement), Sprint 45 INGEST-010/030 and GW-030 (external, already shipped — real data copied to every tenant)

### MR-009 — Extend horizon coverage to 24h on real data, Harvey-corrected [Should] — done, see `docs/tickets/MR-009.md`
**As a** research candidate model already run at 1h/6h (MR-008), **I want** the same `LightGBMBaseline`/`RegimeHMMBaseline` runs extended to the 24h horizon on the real `binance_price_btcusdt_1h` series, **so that** all three of the thesis's original horizons (1h/6h/24h, `da-tese-ao-produto.md` section 1.2/1.3) are covered on real data, not just the two horizons MR-004/MR-005 tested on synthetic data.

Acceptance criteria:
- [x] 24h is treated as an overlapping-horizon case (each row's target window overlaps its neighbors') and the DM test applies the Harvey et al. (1997) long-run-variance correction already implemented in `dm_test.py` — no research-only shortcut statistic, no correction skipped "to keep numbers comparable" to the uncorrected 1h case. Confirmed structurally (`dm_test.py`'s `range(1, horizon)` autocovariance-sum branch, empty/no-op at `horizon=1`, active at `horizon=24`) and via a dedicated test asserting the DM statistic differs between `horizon=1` and `horizon=24` on identical input.
- [x] Same purge-gap/train-fold-only-fit protocol as MR-008 — **explicit purge-gap-widening decision made and documented**: this story uses `purge_gap=24` (wider than MR-008's `purge_gap=6`), matching `libs/naive_first_engine`'s own thesis-regression-suite convention and the minimum requirement to prevent a 24-hours-ahead target window from overlapping into the next split's training rows. See `docs/tickets/MR-009.md`'s "Explicit purge-gap decision for 24h" section.
- [x] DM-vs-Naive0 verdict counts reported for 24h alongside the existing 1h/6h numbers from MR-008, same report shape, same honesty standard (no improvement is a complete result): `LightGBMBaseline` `{'better': 0, 'worse': 2, 'no significant difference': 16}`; `RegimeHMMBaseline` `{'better': 0, 'worse': 0, 'no significant difference': 18}` — neither beat Naive0.
- [x] Same hard gate restated verbatim as MR-008's last acceptance criterion.

Rationale for priority: "Should" — directly closes the last of the thesis's three original horizons on real data, which MR-004/MR-005 never attempted (even on synthetic data) and which the original thesis found OLS's closest-but-still-losing performance on; not "Must" because it is additive coverage on top of MR-008, not a precondition for MR-008's own value.
Depends on: MR-008 (establishes the real-data pipeline this story extends)

### MR-010 — Engineered features (MR-002) against real data: bundled into MR-008/MR-009, not a separate story
**Decision, stated explicitly rather than left ambiguous**: MR-002's rolling-volatility/rolling-mean/lagged-return feature functions are already the feature inputs `LightGBMBaseline` (via `_make_features`) and `RegimeHMMBaseline` (via `lagged_returns`) use internally today — they are not an optional add-on, they are load-bearing parts of both models' existing `predict()` implementations per `research/README.md`'s MR-004/MR-005 sections. Re-running those same models against real data (MR-008/MR-009) therefore automatically exercises MR-002's feature functions against real data too, with no separate wiring needed. A standalone "MR-002 on real data" story would duplicate MR-008/MR-009's own acceptance criteria for no added information. This entry exists only to record that decision explicitly, per this session's instruction — it is not a new backlog item and carries no separate ID/acceptance criteria/priority.

### MR-011 — Document real-data outcomes in `research/README.md` and the ticket index [Must] — **done (Sprint 47, `docs/tickets/MR-011.md`)**
**As a** future reader of this research track (PM, Tech Lead, or a future session picking this work back up), **I want** MR-008's and MR-009's real-data results — positive or negative — written into `research/README.md` (a new "Real BTC/USDT data (MR-008/MR-009)" section, matching the existing MR-004/MR-005/MR-006 section format) and into the ticket index (`docs/tickets/MR-008.md`, `MR-009.md`), **so that** the same documentation rigor and review process already applied to every prior story in this backlog (disclosed bugs, disclosed scope reductions, exact hyperparameters/date ranges/row counts used) is applied here too, with no lower-scrutiny "just a data swap" shortcut.

Acceptance criteria:
- [x] `research/README.md` gains a section for MR-008/MR-009 in the same structural format as the existing MR-004/MR-005/MR-006 sections: what was run, exact scoping/bounding decisions (date range, row count, hyperparameters, any compute-time ceiling), verdict counts per horizon, and any bug found/fixed during review — no leakage bug was found in this pass (`research/models/*.py` were reused unmodified from MR-004/MR-005); instead, a real *environment* gap (live stack Postgres down, missing seed-CSV packaging) was found and disclosed with the same rigor, per `docs/tickets/MR-008.md`'s Analysis section.
- [x] `docs/tickets/MR-008.md` and `docs/tickets/MR-009.md` are written following the same Outcome-section format as `MR-004.md`/`MR-005.md`.
- [x] The hard gate (no price-prediction claim without a real, Harvey-corrected significant DM win) is restated in `research/README.md`'s new section itself, not only in this backlog file — so a reader of the README alone, without this backlog, still sees the constraint.
- [x] If the result is "no improvement on real data" (consistent with the synthetic-data finding), `research/README.md` states this explicitly as a second, independent confirmation of the thesis's core finding — mirroring this backlog's own "What success looks like" framing — not as an unstated or buried result. Confirmed: no model beat Naive0 in a stable, significant way at any of 1h/6h/24h on real data.

Rationale for priority: "Must" — this backlog's own "What does NOT change" section already commits to no separate, lower-scrutiny research-results channel; skipping documentation here would violate that commitment for the first time in this track, regardless of MR-008/MR-009's own priority level.
Depends on: MR-008, MR-009

## Extension: wider real-data window and a no-new-dependency ensemble candidate (MR-012 onward)

**Source for this extension**: `docs/product/backlog-model-research.md`'s own MR-008/MR-009/MR-011 sections above, `docs/tickets/MR-008.md` (disclosed 209-day/5,026-row compute-budget bound out of the full 2017-08-17–2026-08-07 real series), `research/pyproject.toml` (current dependency set: `pandas`, `numpy`, `lightgbm`, `scikit-learn`, `hmmlearn`, `httpx`, `naive_first_engine` — no `torch`/`tensorflow`/`keras`), MR-006's explicit precedent (`shap` declined as a new dependency), and `docs/da-tese-ao-produto.md` section 1.6's future-work table ("Boosting, GRU, Transformer ainda não testados"). **Scope**: this extension does two things — (1) a low-risk widening of the real-data window MR-008/MR-009 already established, and (2) an explicit, disclosed feasibility call on the thesis's remaining untested model class (GRU/Transformer), choosing a no-new-heavy-dependency path (an sklearn-based ensemble of the two already-shipped candidates) over adding `torch` now.

**Explicit feasibility call, stated rather than left ambiguous**: a GRU/Transformer candidate would require a new `torch` (or `tensorflow`) dependency — a materially heavier addition than `shap`, which this backlog already declined in MR-006 for a narrower reason (no natural explainer fit). No trigger in `docs/implementation-plan.md` section 6, no sprint decision record, and no story in this backlog to date has authorized adding a new ML framework dependency to `research/`. Per this backlog's own YAGNI precedent (MR-005's 2-state HMM narrowing, MR-008's 209-day bound), the next model-class story is scoped instead as **MR-013 below: an sklearn-only stacking ensemble of `LightGBMBaseline` + `RegimeHMMBaseline`**, which is genuinely a new model class relative to either candidate alone (a meta-learner combining two heterogeneous base learners) and requires zero new dependencies. Adding `torch` for a GRU/Transformer candidate is deferred and flagged for explicit requester/PM sign-off as its own future story — not silently declined and not silently approved.

**Binding on every story below, restated per CLAUDE.md and this backlog's own "What does NOT change" section**: no story here may touch, weaken, or shortcut `libs/naive_first_engine`'s leakage-safety machinery (purge-gap enforcement, train-fold-only fitting, DM test) to make a result look better. No product surface, README, UI copy, or customer-facing claim may assert the system predicts Bitcoin prices/futures unless a candidate model has actually beaten Naive0 with Harvey-corrected DM significance under this protocol on real data. A "no improvement" result is a complete, valuable, honestly-reported outcome, not a failed story.

### MR-012 — Extend the real-data window used by MR-008/MR-009 to a longer real history [Should] — DONE, `docs/tickets/MR-012.md`
**As a** research candidate model already validated on the 209-day/5,026-row real window (MR-008/MR-009), **I want** the same `LightGBMBaseline`/`RegimeHMMBaseline` runs re-executed at 1h/6h/24h against a materially longer slice of the real `binance_price_btcusdt_1h` series (available back to 2017-08-17 UTC, per `services/ingestion-service/README.md`), **so that** the MR-008/MR-009 finding is checked against a window that includes more market regimes (not just the most recent ~209 days), using the exact same pipeline and zero new model code.

Acceptance criteria:
- [x] The date-range bound is widened from MR-008's `2026-01-10`–`2026-08-07` window to a new, explicitly disclosed range and row count (`2024-08-08T09:00:00`–`2026-08-07T09:00:00`, 17,496 returns) — within the same CPU-only, sub-5-minute compute ceiling (4 passed in 36.33s).
- [x] Data is pulled through the same `research/`-owned HTTP client calling `ingestion-service`'s `GET /datasets/{source}/series` route directly, exactly as MR-008 established — no new connector, no `IngestionServiceDatasetSource` import.
- [x] `raw_series.pct_change().dropna()` applied before any Naive0 comparison, consistent with MR-001.
- [x] Same purge-gap values as MR-008 (`purge_gap=6` for 1h/6h) and MR-009 (`purge_gap=24` for 24h) — no narrowing.
- [x] `research/models/*.py` untouched (`git status --porcelain research/models` confirmed empty).
- [x] DM-vs-Naive0 verdict counts reported for all three horizons (68 splits/horizon) — no model beats Naive0 stably at any horizon.
- [x] Hard gate restated verbatim, honored.

Rationale for priority: "Should" — this is the lowest-risk, highest-information next step (reuses MR-008/MR-009's pipeline unchanged, no new model code, no new dependency, real data already available beyond the window already tested); not "Must" because MR-008/MR-009 already produced a complete, valid, honestly-reported negative result and this is confirmatory breadth, not a blocking gap.
Depends on: MR-008, MR-009 (pipeline and purge-gap conventions reused unchanged)

### MR-013 — Stacking ensemble of `LightGBMBaseline` + `RegimeHMMBaseline` as a new `Baseline` implementation, sklearn-only [Could] — DONE, `docs/tickets/MR-013.md`, meta-learner: `sklearn.linear_model.Ridge`
**As a** research candidate model, **I want** a stacking-ensemble `Baseline` implementation that combines `LightGBMBaseline`'s and `RegimeHMMBaseline`'s per-split predictions via an `sklearn.linear_model` meta-learner (e.g. `LinearRegression` or `Ridge` fit on the two base predictions, train-fold only), **so that** the thesis's remaining "broader model comparison" gap (section 1.6) gets one more genuinely new model class tested under the honest protocol, without adding a new heavy ML dependency (`torch`/`tensorflow`) — see this extension's explicit feasibility call above.

Acceptance criteria:
- [x] `research/models/stacking_ensemble.py` implements the `Baseline` protocol (`.predict(train, test) -> pd.Series`, `.name`) exactly as `LightGBMBaseline`/`RegimeHMMBaseline` already do — no edit to `naive_first_engine`.
- [x] The meta-learner is fit strictly on the training fold's own out-of-sample base-model predictions (chronological 80/20 train-fold-internal holdout split) — a unit test (`test_meta_learner_fits_on_holdout_out_of_sample_predictions_not_in_sample`) asserts the meta-learner is never fit on in-sample base predictions; Tech-Lead-verified to genuinely fail against a naive implementation.
- [x] Both base models re-instantiated and refit per split (8 fresh instances tracked across 2 `predict()` calls) — no global/cross-split reuse.
- [x] No new dependency added to `research/pyproject.toml` (`git diff research/pyproject.toml` confirmed empty).
- [x] Run at 1h/6h/24h against MR-012's already-landed wider window (17,496 returns, 68 splits/horizon) — the ensemble does not beat Naive0 stably at any horizon.
- [x] Hard gate restated verbatim, honored.

Rationale for priority: "Could" — this is a genuinely new model class and closes part of the thesis's "Boosting, GRU, Transformer ainda não testados" gap without the dependency cost of a GRU/Transformer, but it is the harder of the two stories in this extension (new leakage failure mode to guard against: meta-learner overfit-on-base-predictions) and is not required for MR-012's window-widening value to land independently.
Depends on: MR-004, MR-005 (base models reused), MR-008/MR-009 (real-data pipeline and purge-gap conventions)

### MR-014 — Document MR-012/MR-013 outcomes in `research/README.md` and the ticket index [Must] — DONE, `docs/tickets/MR-014.md`
**As a** future reader of this research track (PM, Tech Lead, or a future session picking this work back up), **I want** MR-012's and MR-013's results — positive or negative — written into `research/README.md` (a new section matching the existing MR-004/MR-005/MR-006/MR-008/MR-009 section format) and into `docs/tickets/MR-012.md`/`MR-013.md`, **so that** this backlog's "no separate, lower-scrutiny research-results channel" commitment (see "What does NOT change" above) is honored for this extension too, including an explicit written record of the GRU/Transformer-dependency deferral decision stated in this extension's header (so a future session doesn't silently re-litigate or silently forget it).

Acceptance criteria:
- [x] `research/README.md` gains a section for MR-012/MR-013 in the same structural format as the existing sections.
- [x] `docs/tickets/MR-012.md` and `docs/tickets/MR-013.md` are written following the same Outcome-section format as `MR-008.md`/`MR-009.md`.
- [x] The hard gate is restated in `research/README.md`'s new section itself.
- [x] The GRU/Transformer `torch`-dependency deferral decision is recorded in `research/README.md` as an explicit, dated (2026-09-16) decision.
- [x] MR-012/MR-013 both show "no improvement on real data" — `research/README.md` states this explicitly as a third/fourth independent confirmation of the thesis's core finding.

Rationale for priority: "Must" — same standing commitment already enforced by MR-011 for MR-008/MR-009; skipping documentation here would be the first inconsistency in an otherwise unbroken pattern this backlog has kept since MR-004.
Depends on: MR-012, MR-013

## What "success" looks like, stated explicitly

Success for this backlog is **not** "a model beats naive." Success is: every story above executes under the unmodified leakage-safe protocol and produces an honestly reported result — beating naive with statistical significance (Harvey-corrected DM, Naive0 baseline, purge-gap enforced) counts as success; *not* beating naive, again, is an equally valid, complete, reportable outcome, and is exactly the kind of result this platform's audit/validation credibility is built on being willing to publish. If every candidate here fails to beat naive, that is not a failed sprint — it is a second, independently-obtained confirmation of the thesis's core finding, on model classes (boosting, regime-switching) the thesis itself flagged as untested, which is itself valuable evidence for the product's "we tested this honestly, including the things that didn't work" positioning (`da-tese-ao-produto.md` section 2.5).
