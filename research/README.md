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
