# Applied Research (Phase 3)

Regime-sensitive models (HMM, hybrids), broader model comparison (boosting, GRU, Transformer), and per-split explainability (SHAP/feature importance) — all tested under the same purged walk-forward protocol against the naive benchmark, never as a standalone claim of predictive edge.

See [../docs/da-tese-ao-produto.md](../docs/da-tese-ao-produto.md) section 1.6.

Status: greenlit (Sprint 33, `docs/sprints/sprint-33.md`). Sprint 40 shipped MR-002
(`docs/tickets/MR-002.md`), the first real code in this directory: leakage-safe, stateless feature-
engineering functions in `research/features.py`, each operating only on a caller-supplied train-fold
`pandas.Series` (no global fit, no second Series-shaped parameter):

- `rolling_volatility(train_returns, window)` — rolling standard deviation of the fold's returns.
- `rolling_mean_return(train_returns, window)` — rolling mean of the fold's returns.
- `rolling_std_return(train_returns, window)` — rolling standard deviation of the fold's returns (kept as
  a separately named function from `rolling_volatility` for backlog-literal traceability; same primitive).
- `lagged_returns(train_returns, lags)` — one `shift(lag)` column per requested lag.

These are engineered inputs for a future candidate model, not signals — whether any of them help a model
beat the naive baseline is an open research question, answered only by MR-004/MR-005's future
Diebold-Mariano test results, not assumed by MR-002 itself. MR-004 (candidate model wiring), MR-005
(DM-test comparison against naive), and MR-006 (per-split explainability) remain not started and are not
implied by this sprint.

## Multimodal feature interface (MR-003, Sprint 41 — documentation/interface-design only)

`docs/product/backlog-multimodal-dataset-fusion.md`'s MDF-003 shipped in Sprint 36
(`services/validation-service/src/app/feature_dataset.py`, `FeatureDatasetAssembler`) and is real, tested
code — see that module's README, "Multi-source feature assembly (VS-030/MDF-003)". This section documents
the interface `research/` code *would* call to consume `FeatureDatasetAssembler`'s aligned multi-source
feature table, once such a call is actually possible, and explicitly discloses that it is not possible
today.

**The disclosed gap, stated plainly**: `FeatureDatasetAssembler.assemble`'s output (the aligned
multi-column `pandas.DataFrame`) is consumed only *internally* by `services/validation-service/src/app/
routers/runs.py::create_run` — it is immediately reduced to a re-indexed target `pd.Series`
(`series = series.loc[assembled.index]`) before `run_validation_protocol` runs, and is never returned by
any `GET` route. `FeatureFoldScaler` (the per-fold-fit preprocessing surface CLAUDE.md's leakage rule
requires) is likewise "not yet wired into any candidate-model inference call — no such consumer interface
exists yet" per that same README section. **`research/` cannot, today, pull the assembled multimodal
feature table out of `validation-service` by calling anything.** The join logic is real; it is not yet an
externally consumable interface.

**The interface `research/` would call, once it exists** (not built, not approved as a backlog story —
flagged for the Product Owner to write up, per sprint-41.md's "Next" section):

- **Transport**: a plain HTTP `GET` request to `validation-service`, by Compose hostname
  (`http://validation-service:8002` inside Compose), the same "call the service's own HTTP API, never its
  DB schema, never by importing `app.*`" rule every other cross-module caller in this platform already
  follows (implementation-plan.md section 4; `IngestionServiceDatasetSource`'s and `reporting-service`'s
  existing by-hostname precedent). `research/` is not a service and has no privileged DB access, so this
  is the only compliant transport — no exception is proposed for research code.
- **Auth**: tenant-scoped, the same `X-Tenant-Id`/API-key convention every existing `validation-service`
  route already uses. No new auth mechanism is proposed.
- **Request shape (proposed, not built)**: either `GET /runs/{run_id}/features` (return the table that
  composed an already-completed run, keyed by `run_id` + tenant) or a standalone
  `POST /feature-datasets` accepting the same `feature_references`/`missing_timestamp_policy` shape
  `POST /runs` already accepts, returning the assembled table without running the full validation
  protocol. Which shape is right is a product/API-design decision for the (not-yet-filed) export-endpoint
  story to make — this section only establishes that some such `GET`-reachable shape is needed, matching
  `ObjectStorageDatasetSource`'s existing convention of returning either the table directly or a
  `{"object_key": ...}` pointer for the caller to fetch.
- **Response shape (proposed, not built)**: a JSON-serializable, time-indexed multi-column table (or a
  storage pointer, per the point above), plus the same `feature_lineage` (`{"source", "field",
  "lag_hours"}` per reference) `RunDetailResponse.feature_lineage` already persists today — so a
  `research/`-side caller can attribute which columns came from which source/lag without re-deriving
  `FEATURE_SOURCE_LAG_HOURS`'s dispatch table itself.
- **What `research/` must never do instead**: re-implement `CompositeDatasetSource`, the `fetched_at`-based
  alignment rule (ADR-0008), or `FeatureFoldScaler`'s per-fold-fit logic locally. If a research direction
  needs multi-column input before this endpoint exists, the correct move is to wait for the endpoint (or
  request it be prioritized), not to duplicate `validation-service`'s join/alignment code inside
  `research/` — that would create exactly the "no service reads/reimplements another module's owned logic"
  violation this platform's architecture forbids (implementation-plan.md sections 2/5).

**What this means for MR-004 (this sprint's other story)**: MR-004 does **not** use this interface and
does **not** train on multimodal data — it trains on the returns series, optionally MR-002's engineered
features (`research/features.py`), because no export endpoint exists yet to pull real multimodal data
through. See `research/models/gradient_boosting.py`'s own module docstring and this README's MR-004
section below.

**No `naive_first_engine` change**: this ticket touches no file under `libs/naive_first_engine` — the
engine's own multi-column `CandidateModel` interface (`docs/adr/0010-multimodal-candidate-model-
interface.md`) already exists, additive and unwired, and is unaffected by this documentation-only ticket.

## Gradient-boosting candidate model (MR-004, Sprint 41 — shipped, light-compute-scoped)

`research/models/gradient_boosting.py`'s `LightGBMBaseline` is a `Baseline`-protocol Strategy
implementation (`libs/naive_first_engine/src/naive_first_engine/baselines.py`) wrapping
`lightgbm.LGBMRegressor`, registered via `config.extra_baselines` and run through the real, unmodified
`run_validation_protocol` — the same purge-gap, train-fold-only-fit, DM-vs-Naive0 protocol as every
other baseline. It trains on the returns series plus `research/features.py`'s existing lag/rolling
functions (MR-002) — not multimodal inputs (see the disclosed gap above).

This is a research baseline tested against Naive0 under the existing leakage-safe protocol, not a
price-prediction or trading-signal feature — whether it beats naive is reported honestly either way,
never assumed.

**Light-compute scoping (sprint-41.md, non-negotiable ceiling)**:
- Dataset: a seeded, deterministic 3,000-row synthetic hourly-returns series
  (`research/tests/test_gradient_boosting.py`'s `_synthetic_hourly_returns`) — not the thesis's real
  dataset, not claimed to reproduce its published numbers (see that file's DISCLOSURE block).
- `ValidationConfig`: `train_window=500, test_window=50, step=250, purge_gap=6`.
- LightGBM hyperparameters, fixed, no search: `n_estimators=50, max_depth=4, num_leaves=15,
  learning_rate=0.1, min_child_samples=10, n_jobs=1, random_state=42, verbose=-1`.
- CPU-only. Horizons: 1h and 6h only.
- Measured runtime: `pytest tests/test_gradient_boosting.py -q -s` — 3 passed in 1.63s
  (pytest-reported), well under the 5-minute ceiling.
- **Corrected at Tech Lead review (post-shipping bug fix)**: `_make_features` originally called
  `rolling_mean_return`/`rolling_volatility` on the same-row-inclusive `rolling(window)` output without
  the extra `.shift(1)` `lagged_returns` already applies via its own `lag>=1` convention — the feature at
  row t partially contained `returns[t]`, the exact target being predicted at that row (same-row target
  leakage, not a fold-boundary leak; `research/features.py` itself is unmodified and was never the bug).
  This produced the suspiciously one-sided verdict counts below the strikethrough. Fixed by shifting the
  rolling-derived features by one additional step in `gradient_boosting.py` (the caller), so row t only
  ever uses `returns[t-5..t-1]`.
- Observed DM-vs-Naive0 verdict counts on this synthetic fixture, corrected (not a claim about real BTC
  data): 1h `{'better': 0, 'worse': 1, 'no significant difference': 9}`; 6h `{'better': 0, 'worse': 0, 'no
  significant difference': 10}` — much more naive-like/balanced, consistent with the thesis's own core
  finding rather than the pre-fix leaked result. See `docs/tickets/MR-004.md`'s Outcome section for the
  full caveat.
  ~~Pre-fix (leaked) counts, no longer valid: 1h `{'better': 6, 'worse': 0, 'no significant difference':
  4}`; 6h `{'better': 7, 'worse': 0, 'no significant difference': 3}`~~

See `docs/tickets/MR-004.md` for the full ticket.

## Regime-gated linear candidate model (MR-005, Sprint 42 — shipped, light-compute-scoped)

`research/models/regime_hmm.py`'s `RegimeHMMBaseline` is a `Baseline`-protocol Strategy implementation
(`libs/naive_first_engine/src/naive_first_engine/baselines.py`) wrapping a 2-state
`hmmlearn.hmm.GaussianHMM` (fixed state count) gating one `sklearn.linear_model.LinearRegression` per
state, registered via `config.extra_baselines` and run through the real, unmodified
`run_validation_protocol` — the same purge-gap, train-fold-only-fit, DM-vs-Naive0 protocol as every other
baseline. The HMM's `.fit()`/`.predict()` calls see only the `train`/`test` arguments handed to that
split's `predict(train, test)` call, never a module-level or closed-over full series, per CLAUDE.md's
leakage rule and this ticket's own regime-fit-boundary AC. Per-state linear features come from
`research/features.py`'s existing `lagged_returns` (MR-002, `lag>=1` by construction) — no rolling
current-row-inclusive primitive is used, so the same-row target-leakage bug MR-004's review found and
fixed does not apply here.

This is a research baseline tested against Naive0 under the existing leakage-safe protocol, not a
price-prediction or trading-signal feature — whether it beats naive is reported honestly either way,
never assumed.

**Light-compute scoping (sprint-42.md, non-negotiable ceiling)**:
- State count: fixed at 2 (`GaussianHMM(n_components=2, covariance_type="diag")`), no state-count search
  of any kind.
- Dataset: the same seeded, deterministic 3,000-row synthetic hourly-returns series MR-004 already uses,
  now extracted into `research/tests/fixtures.py::synthetic_hourly_returns` for shared reuse (MR-004's own
  `test_gradient_boosting.py` was updated to import from the same place rather than keep a duplicate
  inline generator — its own assertions/numbers are unchanged).
- `ValidationConfig`: `train_window=500, test_window=50, step=250, purge_gap=6` (same as MR-004 — measured
  runtime did not require narrowing further).
- Hyperparameters, fixed, no search: HMM `n_components=2, covariance_type="diag", n_iter=30,
  random_state=42`; per-state `LinearRegression` uses library defaults.
- CPU-only. Horizons: 1h and 6h only.
- Measured runtime: `uv run pytest tests/test_regime_hmm.py -q` — 4 passed in ~5.3-5.9s (pytest-reported),
  well under the 5-minute ceiling.
- **Degenerate-state disclosure**: on this i.i.d.-Gaussian synthetic fixture, the 2-state HMM is not
  guaranteed to find a real, well-separated regime split (the fixture was built for MR-004's boosting
  story, not to contain a planted regime shift) — this is expected per the ticket's compute-budget section
  and is not treated as a bug; no fallback/retry logic was added to force better-separated states.
- Observed DM-vs-Naive0 verdict counts on this synthetic fixture (not a claim about real BTC data): 1h
  `{'better': 0, 'worse': 0, 'no significant difference': 10}`; 6h `{'better': 1, 'worse': 0, 'no
  significant difference': 9}` — consistent with the thesis's own core finding (no model beats naive in a
  stable, significant way); the single 6h "better" split is one split out of ten, not a stable/significant
  pattern, and is reported here exactly as observed, not smoothed over.

**Correction (post-review)**: Tech Lead review found that the original `predict` decoded each test row's
regime state using `test`'s own current-row return value (`test.to_numpy()` fed straight into
`hmm.predict()`) — target leakage, since `return[t]` is the exact value being predicted at row t. Fixed to
decode test states from the lagged return series (`test.shift(1)`, backfilled from `train`'s last
observation for the first test row) instead, matching this module's existing `lag>=1` convention. See the
"Correction" subsection in `docs/tickets/MR-005.md`'s Outcome section for the full bug/fix writeup. Re-run
verdict counts after the fix were unchanged on this specific seeded fixture (1h and 6h numbers above are the
corrected, post-fix numbers) — not evidence the leakage was harmless in general, only that this fixture's
lag-1 return doesn't route rows differently than the current-row return did here.

See `docs/tickets/MR-005.md` for the full ticket.

## Per-split explainability artifacts (MR-006, Sprint 43 — shipped, feature-importance-only, no SHAP)

`research/explainability.py`'s `ExplainableLightGBM`/`ExplainableRegimeHMM` are `Baseline`-protocol
Strategy wrappers (registered via `config.extra_baselines` exactly like the unwrapped MR-004/MR-005
classes) that additionally capture a per-split explainability artifact, read directly off the same fitted
object each split's `predict()` call already builds — no second/separate fit anywhere in this path.

**Scope decision (binding, no SHAP, no new dependency)**: classic SHAP does not map cleanly onto an
HMM-gated linear model — its `KernelExplainer` path would need an invented background-distribution/
sampling scheme to apply to a model class that isn't a single differentiable/tree estimator, which this
ticket explicitly declines to build. Both candidate models already expose interpretable structure with
zero new dependency:
- **`LightGBMBaseline` (MR-004)**: `LGBMRegressor.feature_importances_`, read off the same fitted
  `LGBMRegressor` object `predict()` already builds.
- **`RegimeHMMBaseline` (MR-005)**: (a) each per-state `LinearRegression`'s own fitted `.coef_`/
  `.intercept_` (the linear model genuinely is its own explanation), plus (b) which HMM-decoded state was
  active for each row of that split's test fold (the same lag-1-routed `test_state_series` the
  post-MR-005-review leakage fix already produces — read directly, not recomputed).

**Artifact shape**:
- LightGBM: a `pd.Series` of `feature_importances_`, indexed by feature name.
- RegimeHMM: a `dict` with `"state_coefficients"` (`{state: {"coef": [...], "intercept": ..., "features":
  [...]}}`) and `"test_state_assignment"` (a `pd.Series`, indexed like that split's `test` fold, giving
  the decoded active state per row).

**Where it lives ("existing report pipeline" resolution)**: `services/reporting-service` (trigger #7) is
not built yet, so "the existing report pipeline" is read as `research/`'s own `SplitResult`-shaped output
convention. Each `ExplainableLightGBM`/`ExplainableRegimeHMM` instance accumulates one
`ExplainabilityRecord` per split in `self.records`; `pair_with_split_results(split_results, wrapper)`
zips `run_validation_protocol`'s own, unmodified `SplitResult` list with those records by `split_index`
— a research-side sibling artifact attached to the existing result path, not a new persistence layer or
an ad hoc file dump.

**No `naive_first_engine` change was needed.** `research/models/gradient_boosting.py` and
`research/models/regime_hmm.py` were each minimally refactored — their `predict()` method bodies were
extracted into a private module-level `_fit_predict_and_explain` function returning
`(predictions, artifact)`; `predict()` itself now just discards the artifact, so its own observable
behavior (including the "no instance attribute is ever set" structural invariant MR-004/MR-005's own
tests assert) is unchanged. No new dependency was added.

**Test results**: `research/tests/test_explainability.py` — 7 new tests (no-refit proof via `.fit()`
spies for both model shapes, artifact-shape assertions, `pair_with_split_results` correctness at both
horizons for both model shapes, bit-identical-predictions check between the wrapper and the unwrapped
baseline). Full `research/tests/` suite: 21 passed in 7.38s. `libs/naive_first_engine` suite unaffected:
99 passed in 2.29s.

See `docs/tickets/MR-006.md` for the full ticket.

## Real BTC/USDT data (MR-008/MR-009)

`research/real_data.py`'s `load_real_hourly_returns(tenant_id, source, start, end, base_url, field=None)`
is a small, `research/`-owned HTTP client (`httpx`) that calls `ingestion-service`'s existing
`GET /datasets/{source}/series` route directly, sends `X-Tenant-Id`, and returns a sorted `pd.Series`
(raw levels, not returns — the returns transform is left to the caller, mirroring
`dataset_source.py`'s own "load a series" vs. "what the caller does with it" separation). Raises
`RealDataSourceError` (not a bare `httpx` exception) on a non-2xx response or malformed JSON.

**Binding "never import `app.*`" rule**: this module deliberately does **not** import
`services/validation-service/src/app/dataset_source.py::IngestionServiceDatasetSource`, even though that
class implements the identical HTTP contract — that class lives under `services/validation-service`'s own
`app` package (service code, not a shared `libs/*` package), and `research/` may only call another
module's HTTP API, never its app code (CLAUDE.md, `docs/tickets/MR-008.md`'s Design section).
`real_data.py` re-implements only the minimal request/response handling needed (`GET .../series` -> JSON
-> sorted `pd.Series`), not a copy of `dataset_source.py`'s CSV-parsing logic.

**Environment repair needed before this ticket's own scope could start (disclosed in full in
`docs/tickets/MR-008.md`'s Analysis section)**: the live local Docker stack's Postgres had exited; once
restarted, the live Postgres was found polluted with 1,870 leftover test tenants, none of which had the
Sprint 45 platform-history backfill present; the provision-time auto-seed hook (`GW-030`/`INGEST-030`)
itself 503'd because `services/ingestion-service`'s Docker image never ships the real seed CSVs
(`data/raw/_platform/`, present on the host, never `COPY`/mounted into the container — a real, disclosed
packaging gap, flagged as a follow-up infra ticket, not fixed here). Fixed live: Postgres restarted,
seed CSVs `docker cp`'d into the running container (not git-tracked, does not survive a container
recreate), a dedicated research tenant (`271d391dd7bf4213b3e5fb8ea6636563`) created and seeded with
78,523 real `binance_price_btcusdt_1h` rows (2017-08-17 through at least 2026-08-07).

**MR-008 (Sprint 47, `docs/tickets/MR-008.md`) — real-data run, 1h/6h**: `LightGBMBaseline` (MR-004) and
`RegimeHMMBaseline` (MR-005), unmodified, registered via `config.extra_baselines` and run through the
real, unmodified `run_validation_protocol` against the real research tenant's `binance_price_btcusdt_1h`
series.

- **Tenant/source**: `tenant_id="271d391dd7bf4213b3e5fb8ea6636563"`, `source="binance_price_btcusdt_1h"`,
  `field` omitted (defaults to `close`).
- **Date range / row count bound (disclosed)**: `start="2026-01-10T00:00:00"`,
  `end="2026-08-07T09:00:00"` — the most recent ~209-day window of the full 2017-08-17–2026-08-07 series
  (~78,500 rows total). This window returned **5,026 rows**; not the full history, to stay CPU-only and
  under a 5-minute runtime ceiling.
- **Returns transform**: `raw_series.pct_change().dropna()` (5,025 returns), applied by the test before
  any baseline/Naive0 comparison — consistent with MR-001's "compare on returns, not levels" methodology.
- **`ValidationConfig`**: `train_window=500, test_window=50, step=250, purge_gap=6`, horizons `1` and `6`
  — identical to MR-004/MR-005's synthetic-data config, reused rather than re-derived.
- **Measured runtime**: `uv run pytest tests/test_real_data_mr008.py -q -s` — 5 passed in 7.20s
  (pytest-reported; 8.16s wall-clock including interpreter startup), well under the 5-minute ceiling.
- **Observed DM-vs-Naive0 verdict counts** (18 splits per horizon, real BTC/USDT data, not synthetic):
  - 1h `LightGBMBaseline`: `{'better': 0, 'worse': 4, 'no significant difference': 14}`
  - 1h `RegimeHMMBaseline`: `{'better': 0, 'worse': 0, 'no significant difference': 18}`
  - 6h `LightGBMBaseline`: `{'better': 0, 'worse': 2, 'no significant difference': 16}`
  - 6h `RegimeHMMBaseline`: `{'better': 0, 'worse': 0, 'no significant difference': 18}`

Neither candidate model beat Naive0 in a stable, significant way on this real, recent BTC/USDT window —
consistent with the synthetic-data findings (MR-004/MR-005) and the thesis's own core finding. This is a
second, independent confirmation, reported honestly, not softened or buried.

**Hard gate restated (binding, CLAUDE.md)**: no README, UI copy, or customer-facing claim resulting from
this story asserts the system predicts Bitcoin prices or generates a trading signal — this is
leakage-safe benchmarking research against Naive0, and the result above (no improvement) does not change
that positioning either way.

See `docs/tickets/MR-008.md` for the full ticket.

**MR-009 (Sprint 47, `docs/tickets/MR-009.md`) — real-data run, 24h, Harvey-corrected**: same candidate
models, same real research tenant, same bounded `2026-01-10T00:00:00`–`2026-08-07T09:00:00` window MR-008
already fetched (5,026 raw rows / 5,025 returns — no re-fetch, no new window), extended to `horizon=24`.

- **Purge-gap-widening decision (explicit, binding)**: this run uses `purge_gap=24`, wider than MR-008's
  `purge_gap=6` — matching `libs/naive_first_engine`'s own thesis-regression-suite convention
  (`test_regression_1h/6h/24h.py` all use `purge_gap=24` uniformly, independent of horizon) and the minimum
  requirement to keep a 24-hours-ahead target window from overlapping into the very next split's training
  rows. `train_window`/`test_window`/`step` are unchanged from MR-008 so the split counts stay comparable.
- **Harvey correction confirmation**: `dm_test.py`'s long-run-variance correction is the
  `for k in range(1, horizon)` autocovariance-sum branch (`dm_test.py` lines ~104-120) — a no-op for
  `horizon=1` (`range(1, 1)` is empty) but active for `horizon=24` (23 summed terms), reached unmodified
  through `run_validation_protocol` → `dm_test(..., horizon=config.horizon)`
  (`libs/naive_first_engine/src/naive_first_engine/protocol.py` lines 126/137). Verified structurally (code
  read directly) and via `research/tests/test_real_data_mr009.py::
  test_harvey_correction_branch_fires_for_horizon_24`, which asserts the DM statistic for identical error
  series differs between `horizon=1` and `horizon=24` — proof the corrected-variance code path executes,
  not a hand-derivation of the statistic.
- **`ValidationConfig`**: `train_window=500, test_window=50, step=250, purge_gap=24, horizon=24`.
- **Measured runtime**: `uv run --no-sync pytest tests/test_real_data_mr009.py -q -s` — 2 passed in 3.32s
  (pytest-reported), ~4.03s wall-clock, well under the 5-minute ceiling.
- **Row count used**: 5,026 raw rows / 5,025 returns — identical to MR-008 (same window, no re-fetch).
- **Observed DM-vs-Naive0 verdict counts** (18 splits, real BTC/USDT data, `horizon=24`):
  - `LightGBMBaseline`: `{'better': 0, 'worse': 2, 'no significant difference': 16}`
  - `RegimeHMMBaseline`: `{'better': 0, 'worse': 0, 'no significant difference': 18}`

Neither candidate model beat Naive0 in a stable, significant way at 24h either — consistent with MR-008's
1h/6h findings and the thesis's own core finding across all three of its original horizons, now checked on
this real, bounded window. No profitability or price-prediction claim follows from this result either way
(CLAUDE.md).

See `docs/tickets/MR-009.md` for the full ticket.

## Widened real-data window + sklearn stacking ensemble (MR-012/MR-013, Sprint 52)

Two independent, parallel tracks against the real `binance_price_btcusdt_1h` series (same research tenant
`271d391dd7bf4213b3e5fb8ea6636563` MR-008/MR-009 used) — MR-012 widens the date-range bound to include more
market regimes, MR-013 adds a genuinely new sklearn-only Strategy implementation. Documented jointly here
per MR-014.

**MR-012 (Sprint 52, `docs/tickets/MR-012.md`) — widened window, same models, all three horizons**:
`LightGBMBaseline` (MR-004) and `RegimeHMMBaseline` (MR-005), unmodified, re-run via
`research/tests/test_real_data_mr012.py` against a wider bounded window than MR-008/MR-009 used.

- **Widened date-range bound (disclosed)**: `start="2024-08-08T09:00:00"`, `end="2026-08-07T09:00:00"` — a
  ~730-day (~2-year) window ending at the same timestamp MR-008/MR-009 used, extended backward to include
  the 2024-2025 halving-cycle regime shift MR-008's 209-day window did not cover. Not the full ~78,500-row/
  9-year history (still declined for compute-budget reasons, consistent with MR-008's own precedent).
  Returned **17,496 rows/returns** (~3.5x MR-008's 5,026-row window).
- **`ValidationConfig`**: `train_window=500, test_window=50, step=250` (identical to MR-008/MR-009);
  `purge_gap=6` for horizon=1/6, `purge_gap=24` for horizon=24 — unchanged, no narrowing.
- **Measured runtime**: 4 passed in 36.33s (Tech-Lead-verified re-run), well under the 5-minute ceiling.
- **Split count**: 68 splits per horizon (actual, not the ticket's ~60-67 estimate).
- **Observed DM-vs-Naive0 verdict counts**:
  - 1h `LightGBMBaseline`: `{'better': 0, 'worse': 19, 'no significant difference': 49}`
  - 1h `RegimeHMMBaseline`: `{'better': 2, 'worse': 4, 'no significant difference': 62}`
  - 6h `LightGBMBaseline`: `{'better': 0, 'worse': 14, 'no significant difference': 54}`
  - 6h `RegimeHMMBaseline`: `{'better': 2, 'worse': 3, 'no significant difference': 63}`
  - 24h `LightGBMBaseline`: `{'better': 0, 'worse': 4, 'no significant difference': 64}`
  - 24h `RegimeHMMBaseline`: `{'better': 0, 'worse': 0, 'no significant difference': 68}`

Neither model beats Naive0 in a stable, significant way even on a window covering a materially different
market regime — a third independent real-data confirmation of the thesis's core finding.

See `docs/tickets/MR-012.md` for the full ticket.

**MR-013 (Sprint 52, `docs/tickets/MR-013.md`) — sklearn-only stacking ensemble, new Strategy
implementation**: `research/models/stacking_ensemble.py`'s `StackingEnsembleBaseline` is a new
`Baseline`-protocol Strategy implementation combining `LightGBMBaseline` + `RegimeHMMBaseline` via an
`sklearn.linear_model.Ridge` meta-learner, registered via `config.extra_baselines` exactly like every other
baseline.

- **Leakage guard (a new failure mode relative to MR-004/MR-005)**: the meta-learner must never see a base
  model's in-sample training predictions. `predict(train, test)` splits `train` itself, in time order
  (first ~80% / last ~20%, never shuffled), fits fresh base-model instances on the base-fit portion only,
  gets each base model's genuinely out-of-sample predictions on the holdout portion, and fits `Ridge` on
  those. Fresh base-model instances are then re-fit on the *full* `train` to produce the final `test`
  predictions (standard stacking practice — meta-learner trained on out-of-fold predictions, base learners
  refit on full training data for inference). A fresh meta-learner and fresh base-model instances are
  constructed on every `predict()` call — no instance state persisted.
- **Leakage-guard unit test**: `test_meta_learner_fits_on_holdout_out_of_sample_predictions_not_in_sample`
  monkeypatches both base models with a deliberately-overfit fake (perfect in-sample memorization, a
  constant for genuinely unseen rows) and spies on `Ridge.fit()`'s actual `X`/`y` — asserting the
  meta-learner's target has the holdout portion's length/index (not the base-fit portion's) and its
  features are the fake's out-of-sample constant (not memorized in-sample values). This would fail against
  a naively-in-sample-fit implementation; Tech-Lead-verified by tracing the control flow directly, not by
  trusting the docstring.
- **Meta-learner choice**: `sklearn.linear_model.Ridge`. **Zero new `research/pyproject.toml`
  dependency** — `scikit-learn` was already a dependency (`git diff research/pyproject.toml` empty,
  confirmed).
- **Real-data run**: reused MR-012's already-landed widened window verbatim (17,496 returns, 68 splits per
  horizon, no second fetch).
- **Observed DM-vs-Naive0 verdict counts**:
  - 1h (`purge_gap=6`): `{'better': 0, 'worse': 5, 'no significant difference': 63}`
  - 6h (`purge_gap=6`): `{'better': 2, 'worse': 6, 'no significant difference': 60}`
  - 24h (`purge_gap=24`): `{'better': 0, 'worse': 1, 'no significant difference': 67}`

The stacking ensemble does not beat Naive0 in a stable, significant way at any horizon — a fourth
independent real-data confirmation of the thesis's core finding, not a failed story: combining two
already-tested non-beating candidates does not manufacture an edge neither had individually.

See `docs/tickets/MR-013.md` for the full ticket.

**GRU/Transformer deferral (dated record, 2026-09-16)**: a `torch`/`tensorflow`-based GRU/Transformer
candidate remains explicitly deferred per the backlog's own header — this sprint did not authorize adding
either dependency. Any future GRU/Transformer work requires its own explicit requester/PM sign-off,
separate from this sprint.

**Hard gate restated (binding, CLAUDE.md)**: no README, UI copy, or customer-facing claim resulting from
MR-012 or MR-013 asserts the system predicts Bitcoin prices or generates a trading signal — both are
leakage-safe research baselines run through the existing, unmodified protocol; the "no improvement" result
does not change that positioning either way.

See `docs/tickets/MR-014.md` for the documentation ticket itself.
