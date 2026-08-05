# Backlog — naive_first_engine

Source: `docs/da-tese-ao-produto.md` (sections 1.2, 1.3, 1.6, 2.3.1, 2.7), `docs/solution-design.md` (section 3.4, section 6 build order), `docs/implementation-plan.md` (sections 2, 3, 6, 7, 9), `libs/naive_first_engine/README.md`.

Scope: `libs/naive_first_engine` only — the sole module whose trigger (implementation-plan.md section 6, trigger #1) has fired ("Now — this is the core IP and has no dependencies"). In scope: `splitting.py`, `baselines.py`, `metrics.py`, `dm_test.py`, `report_schema.py`, the fixed Template Method orchestration, and the regression-test suite against the thesis's own published numbers. Out of scope, explicitly not touched by any story below: `services/validation-service` (trigger #3, not fired), `services/gateway-api`, `services/ingestion-service`, `services/reporting-service`, `services/dashboard-web`, `services/economic-service`, `libs/common`, `libs/sdk`, any Postgres/object-storage/Prefect/Redis code, any Bitcoin- or dataset-specific logic (the library must stay dataset-agnostic per its README's "owns" section), and any client-supplied-model execution (deliberately deferred per solution-design.md section 1, principle 2).

## Stories

### NFE-001 — Package scaffolding [Must]
**As a** future importer of this library (`services/validation-service`, or a standalone `pip install`) **I want** a proper `uv`-managed, pip-installable package skeleton **so that** the library can be developed, tested, and later published independently of any service code.

Acceptance criteria:
- [ ] `libs/naive_first_engine/pyproject.toml` exists, declares the package as `naive_first_engine`, has zero web/DB/orchestration dependencies (no FastAPI, no SQLAlchemy, no Prefect), matching the README's "no I/O, no database, no web framework" boundary.
- [ ] `src/naive_first_engine/{splitting,baselines,metrics,dm_test,report_schema}.py` exist as empty-but-importable modules with module-level docstrings stating the single responsibility of each file (matching implementation-plan.md section 3).
- [ ] `tests/` directory exists with a working test runner config (`pytest`), `uv run pytest` succeeds with zero tests collected as a passing baseline.
- [ ] `libs/naive_first_engine/README.md`'s file layout table matches the actual files created (no drift between doc and code).

Rationale for priority: nothing else in this backlog can be built, tested, or reviewed without a package to put it in; this is the literal first step of the only currently-triggered module.
Depends on: none

### NFE-002 — Rolling-origin walk-forward splitter [Must]
**As** the validation engine **I want** a function that produces successive rolling-origin train/test splits over a time-indexed series **so that** every downstream baseline/metric/DM-test computation operates on the same leakage-aware split boundaries the thesis used.

Acceptance criteria:
- [ ] A function (e.g. `generate_splits(index, train_window, test_window, step) -> list[Split]`) exists in `splitting.py`, fully typed, with no reference to Bitcoin, price, or any specific dataset (dataset-agnostic per the library's "owns" boundary).
- [ ] Each returned split exposes explicit `train_start`, `train_end`, `test_start`, `test_end` boundaries (mirrors the `split_results` fields already named in solution-design.md section 4, so `validation-service` can persist them unchanged later).
- [ ] Splits are strictly non-overlapping in the forward (origin-rolling) direction and ordered chronologically; a unit test asserts this invariant on a synthetic index.
- [ ] A unit test confirms the splitter run against a synthetic hourly series with a 1-year out-of-sample window produces the same *number* of splits reported for at least one horizon in da-tese-ao-produto.md section 1.3's DM tables (e.g. 53 for OLS/1h, as the "B/W" denominator implies) — tying the splitter's output count back to a verifiable published number, not just an arbitrary synthetic assertion.

Rationale for priority: the walk-forward split is the first stage of the non-negotiable fixed protocol order (implementation-plan.md section 7, Template Method); nothing downstream can be built or tested without it.
Depends on: NFE-001

### NFE-003 — Configurable purge gap between train and test [Must]
**As** the validation engine **I want** the splitter to accept a configurable purge gap and exclude any observation inside that gap from both train and test **so that** no run can silently reproduce the exact leakage failure mode this whole product exists to detect.

Acceptance criteria:
- [ ] `generate_splits(...)` accepts a `purge_gap` parameter (time-delta or number of periods); each returned `Split` exposes `purge_start`/`purge_end` boundaries distinct from train/test (matches solution-design.md section 4's `split_results` schema).
- [ ] A unit test asserts that with `purge_gap > 0`, no timestamp between `train_end` and `test_start` is present in either the train or test index returned by the split.
- [ ] A unit test asserts that with `purge_gap = 0` explicitly, train and test remain immediately adjacent (the gap is optional and configurable, not implicitly forced to a nonzero default) — a caller can still express the thesis's default of 24h by passing it explicitly.
- [ ] A unit test replicates the thesis's own configuration: 24h purge gap, 1h/6h/24h horizons (da-tese-ao-produto.md section 1.2) and asserts the gap width in the returned split matches exactly.
- [ ] There is no code path in `splitting.py` that returns a split without purge-gap enforcement applied (i.e. purge gap cannot be bypassed by omitting the parameter — it must default to a value, not to "off," or the story is rejected as written).

Rationale for priority: this is the specific mechanism the entire "Naive-First" positioning depends on (da-tese-ao-produto.md section 2.1: "o protocolo de validação em si"); a splitter without an enforced purge gap authorizes exactly the leakage the product audits against, which this backlog will not propose.
Depends on: NFE-002

### NFE-004 — Baseline Strategy interface [Must]
**As** the validation engine **I want** a single typed interface that any baseline (or, later, any client-model wrapper in `validation-service`) implements **so that** new baselines plug in without touching the splitter or DM-test code, per the Strategy pattern named for this module in implementation-plan.md section 7.

Acceptance criteria:
- [ ] `baselines.py` defines a `Baseline` protocol/ABC with a single method matching implementation-plan.md section 7's stated interface: `predict(train, test) -> Series`.
- [ ] The interface takes only the train/test data implied by a `Split` from NFE-002/003 (no access to data outside the split's train boundary — enforced by the function signature, not by convention).
- [ ] A docstring or type comment states explicitly that any implementation must not read data beyond `train_end`, cross-referencing the purge-gap guarantee from NFE-003.

Rationale for priority: Naive0/NaiveLast (NFE-005/006) and any future `validation-service` client-model wrapper both depend on this interface existing first; building concrete baselines before the interface risks the two diverging.
Depends on: NFE-002

### NFE-005 — Naive0 baseline [Must]
**As** the validation engine **I want** the Naive0 baseline (forecast = zero forward return) implemented against the Strategy interface **so that** every run has the mandatory naive floor benchmark the product's structural rule requires (solution-design.md section 1, principle 1: "there is no code path that scores a model without them").

Acceptance criteria:
- [ ] `Naive0` implements the `Baseline` interface from NFE-004 and returns a zero-valued forecast series for every test-period timestamp, aligned to the target (forward return, not price level — da-tese-ao-produto.md section 1.2).
- [ ] A unit test confirms `Naive0.predict` never reads any column/value from `test` other than its index (it is a pure function of the test index shape, matching "forecast = 0" by definition).
- [ ] A regression test computes MAE for Naive0 on a reconstructed 1h out-of-sample scenario and matches da-tese-ao-produto.md section 1.3's published Naive0 1h MAE (0.003627) within a documented floating-point tolerance.

Rationale for priority: Naive0 is named explicitly as a "benchmark naive obrigatório" (da-tese-ao-produto.md section 2.3.1) and is the baseline every DM test in this library compares against — it cannot be optional.
Depends on: NFE-004

### NFE-006 — NaiveLast baseline [Must]
**As** the validation engine **I want** the NaiveLast baseline (forecast = last observed value carried forward) implemented against the Strategy interface **so that** the second mandatory naive benchmark named in the design docs is available alongside Naive0.

Acceptance criteria:
- [ ] `NaiveLast` implements the `Baseline` interface from NFE-004 and returns the last train-period observation carried forward across the test period, reading no data past `train_end`.
- [ ] A unit test confirms `NaiveLast.predict` output is constant across the test period and equals the last value in `train`.
- [ ] A unit test confirms `NaiveLast` and `Naive0` produce different outputs on a synthetic series where the last train value is non-zero (guards against an accidental copy-paste making the two baselines equivalent).

Rationale for priority: da-tese-ao-produto.md section 2.3.1 lists Naive0/NaiveLast as a pair ("Benchmarks naive obrigatórios ... como baseline"); shipping only one leaves the mandatory-baseline rule half-enforced.
Depends on: NFE-004

### NFE-007 — Error metrics: MAE, RMSE [Must]
**As** the validation engine **I want** MAE and RMSE functions **so that** every model/baseline pair can be scored on the two primary error metrics the thesis reports for every horizon.

Acceptance criteria:
- [ ] `metrics.py` exposes typed `mae(y_true, y_pred) -> float` and `rmse(y_true, y_pred) -> float`.
- [ ] Regression tests reproduce da-tese-ao-produto.md section 1.3's 1h table exactly (within documented floating-point tolerance) for Naive0 (MAE 0.003627, RMSE 0.005321) and OLS (MAE 0.003683, RMSE 0.005367) on a reconstructed reference scenario.
- [ ] A unit test confirms `mae`/`rmse` raise on mismatched-length or misaligned-index inputs rather than silently truncating (protects against a silent leakage/misalignment bug reappearing at the metrics layer).

Rationale for priority: MAE/RMSE are the two metrics used for the paper's headline conclusion ("Naive0 venceu em MAE/RMSE médios," section 1.4.1) — the product's core claim is unverifiable without them.
Depends on: NFE-001

### NFE-008 — Error metrics: sMAPE, MASE [Must]
**As** the validation engine **I want** sMAPE and MASE functions **so that** the full metric set named in da-tese-ao-produto.md section 1.2 ("MAE, RMSE, sMAPE, MASE, Directional Accuracy, F1, R²") is available, not just the two headline metrics.

Acceptance criteria:
- [ ] `metrics.py` exposes typed `smape(y_true, y_pred) -> float` and `mase(y_true, y_pred, y_train, seasonal_period) -> float` (MASE requires the train series for its scaling denominator — signature reflects that, not just `y_true`/`y_pred`).
- [ ] A unit test confirms `smape` is bounded in its documented range (0–200% or 0–2 depending on the chosen convention) and symmetric under swapping over/under-forecast direction on a synthetic example.
- [ ] A unit test confirms `mase` returns 1.0 exactly when `y_pred` equals the naive-in-sample benchmark it's scaled against, on a synthetic series (the defining property of MASE).

Rationale for priority: listed explicitly in the thesis's metric set (section 1.2); required before `report_schema.py` (NFE-013) can carry a complete per-split result, but not part of the section 1.3 headline tables, so it can follow MAE/RMSE.
Depends on: NFE-001

### NFE-009 — Directional metrics: Directional Accuracy, F1 [Must]
**As** the validation engine **I want** Directional Accuracy (DA) and F1 functions **so that** the thesis's directional-performance conclusion (best DA = 52.51%, "marginal acima do acaso") can be reproduced and reported for future client audits.

Acceptance criteria:
- [ ] `metrics.py` exposes typed `directional_accuracy(y_true, y_pred) -> float` (percentage of test points where predicted sign matches actual sign) and `f1_directional(y_true, y_pred) -> float`.
- [ ] Regression tests reproduce da-tese-ao-produto.md section 1.3's published values within tolerance: OLS 6h DA 52.51 / F1 0.526, OLS 1h DA 51.33 / F1 0.528, on reconstructed reference scenarios.
- [ ] A unit test confirms `directional_accuracy` returns exactly 50.0 on a synthetic series where predicted direction is uncorrelated with actual direction (sanity check against the "marginal above chance" framing in section 1.4.3, so a client report can honestly state deviation from the 50% floor).

Rationale for priority: DA/F1 carry the thesis's single most quoted negative-but-honest finding (section 1.4.3) — the product's credibility rests on reproducing this number precisely, not approximately.
Depends on: NFE-001

### NFE-010 — Out-of-sample R² [Must]
**As** the validation engine **I want** an out-of-sample R² function **so that** the thesis's strongest documented conclusion (negative R² in every model/horizon, meaning trained models *increased* squared error relative to Naive0) can be recomputed for any future audited model.

Acceptance criteria:
- [ ] `metrics.py` exposes a typed `oos_r2(y_true, y_pred, y_naive) -> float` computed relative to the naive benchmark's squared error (not the in-sample training R², and not scikit-learn's default which uses the mean of `y_true` — that would silently misrepresent the thesis's own definition per section 1.5).
- [ ] A unit test confirms `oos_r2` returns a negative value when `y_pred`'s squared error exceeds `y_naive`'s squared error on a synthetic example, matching the "modelos treinados pioraram o erro quadrático relativo ao benchmark" framing (section 1.5).
- [ ] A docstring states explicitly which R² definition is used (naive-relative, not mean-relative), so a future report never mislabels the number — this is the metric most likely to be misread as "the model explains X% of variance," which section 1.5 explicitly warns against.

Rationale for priority: this is the metric underpinning the single most important interpretive claim in the whole business case (section 1.5) — getting its definition wrong would make every downstream client report misleading, which the product's entire positioning (section 2.1) forbids.
Depends on: NFE-001

### NFE-011 — Diebold-Mariano test core [Must]
**As** the validation engine **I want** a per-split Diebold-Mariano test against Naive0 **so that** every model comparison in this library carries the statistical-significance verdict the thesis used, not just a raw metric delta.

Acceptance criteria:
- [ ] `dm_test.py` exposes a typed `dm_test(errors_model, errors_naive0) -> DMResult` (statistic, p-value, verdict) computed per split, matching da-tese-ao-produto.md section 1.2 ("Teste Diebold–Mariano por split, contra Naive0").
- [ ] `DMResult.verdict` classifies each split as "better," "worse," or "no significant difference" at p<0.05, matching the "melhor/pior a p<0,05" language in section 1.2 and the B/W counts published in section 1.3's tables.
- [ ] A regression test aggregates per-split DM verdicts over a reconstructed 1h scenario and reproduces the published counts from section 1.3 within a documented tolerance for at least two of: OLS 0/4, RF 0/13, ARIMA 0/53 (best-effort reconstruction — exact reproduction of all rows is not required if the underlying per-split data isn't fully recoverable from the published summary tables alone; the story is satisfied once at least one full B/W pair matches).
- [ ] The function signature only accepts already-computed forecast errors per split (no direct access to future data), so the DM test cannot itself become a leakage vector.

Rationale for priority: DM-against-Naive0 is the statistical backbone of the entire audit product (da-tese-ao-produto.md section 2.3.1, "Teste Diebold–Mariano por split") — without it the library only reports point-estimate metrics, which section 2.7's ethical constraints explicitly warn against over-trusting.
Depends on: NFE-005, NFE-007

### NFE-012 — Harvey correction for overlapping horizons [Must]
**As** the validation engine **I want** the Harvey et al. (1997) long-run variance correction applied to the DM test for overlapping (multi-step) horizons **so that** the 6h/24h DM results are not silently invalid, per the thesis's own documented limitation.

Acceptance criteria:
- [ ] `dm_test.py` exposes the correction as an explicit, always-applied step for horizons > 1 (not an opt-in flag a caller could forget) — matching da-tese-ao-produto.md section 2.3.1's phrasing "com correção de variância de longo prazo para horizontes sobrepostos (Harvey et al. 1997)" and section 2.7's explicit risk: "Evitar reivindicar significância estatística em horizontes sobrepostos sem a correção de variância adequada."
- [ ] A unit test confirms the corrected DM statistic differs from the naive (uncorrected) DM statistic on a synthetic overlapping-horizon series with positive autocorrelation in the loss differential (demonstrates the correction is actually doing something, not a no-op passthrough).
- [ ] A unit test confirms that for horizon = 1 (non-overlapping, the 1h case), the corrected and uncorrected statistics are equal or near-equal, matching the expectation that the correction only matters once the horizon exceeds the sampling step.
- [ ] There is no code path in `dm_test.py` that computes a p-value for horizon > 1 without the correction applied — if such a path is requested by any future story, it is refused for the same reason NFE-003's purge gap cannot be bypassed.

Rationale for priority: this is called out by name as an explicit ethical risk in da-tese-ao-produto.md section 2.7 ("Riscos e limites éticos a respeitar") — shipping DM without it would let the platform produce exactly the kind of statistically dishonest report the whole product exists to prevent.
Depends on: NFE-011

### NFE-013 — Typed result/report schema objects [Must]
**As** `services/reporting-service` (a future consumer of this library's output) **I want** typed result objects covering split boundaries, per-baseline metrics, and DM-test outcomes **so that** downstream services can persist and render results without re-deriving the shape of a validation run from scratch.

Acceptance criteria:
- [ ] `report_schema.py` defines typed objects (dataclass or Pydantic, no framework dependency beyond what's already used elsewhere in the lib) for: `SplitBoundaries` (train/purge/test start-end, matching NFE-002/003), `MetricSet` (mae, rmse, smape, mase, da, f1, oos_r2 — the full set from NFE-007–010), `DMResult` (from NFE-011/012), and a composite `SplitResult` bundling all three per split.
- [ ] Field names and types in `SplitResult` are compatible with (a superset-or-equal shape of, not necessarily identical to) the `split_results` table columns already sketched in solution-design.md section 4, so `validation-service` can persist a `SplitResult` without a translation layer that silently drops a field.
- [ ] A unit test round-trips a `SplitResult` through serialization (e.g. `model_dump()`/`asdict()` + reconstruction) and confirms no data loss.
- [ ] The schema module has zero dependency on `splitting.py`/`baselines.py`/`metrics.py`/`dm_test.py` internals beyond the types they return (it is a pure output contract, not coupled to implementation details that would break the "pure functions" promise in the README).

Rationale for priority: named explicitly in implementation-plan.md section 3's file layout and solution-design.md section 3.4 as one of the five files this library must ship; without it, no service can consume the library's output in a stable way, which blocks trigger #3 (validation-service) from ever firing cleanly.
Depends on: NFE-003, NFE-009, NFE-012

### NFE-014 — Template Method orchestration of the fixed protocol [Must]
**As** the validation engine **I want** a single entry point that runs split → baseline → metrics → DM-test in that fixed, non-configurable order **so that** "you can't skip the purge gap or the naive baseline" is true by construction, per implementation-plan.md section 7.

Acceptance criteria:
- [ ] A function (e.g. `run_validation_protocol(series, config) -> list[SplitResult]`) exists that internally calls, in this exact fixed order for every split: NFE-002/003's splitter, both NFE-005/006 baselines plus any additional `Baseline` implementation passed in, NFE-007–010's metrics, then NFE-011/012's DM test — and returns `SplitResult` objects from NFE-013.
- [ ] The function signature makes it impossible to invoke metrics or DM-test computation without first going through the splitter and baselines for the same call (e.g. no public function accepts raw unsplit data and produces a `DMResult` directly) — verified by a unit test that the only public way to reach a `DMResult` is through this orchestrator or by manually replicating its full sequence.
- [ ] A unit test confirms Naive0 and NaiveLast are always present in the returned results for every split, even when the caller passes additional baselines — matching solution-design.md section 1 principle 1 ("no code path that scores a model without them").
- [ ] Given the same input series and config, two calls to `run_validation_protocol` produce bit-identical output (determinism), supporting the "everything the validation engine touches is reproducible" principle (solution-design.md section 1, principle 4).

Rationale for priority: this is the named Template Method from implementation-plan.md section 7 and is what makes every other Must story in this backlog compose into one auditable call — without it, callers could reorder or skip steps by hand.
Depends on: NFE-005, NFE-006, NFE-013

### NFE-015 — Regression suite: reproduce the thesis's published 1h results table [Must]
**As** `services/validation-service` (the library's only planned internal consumer) **I want** a regression test suite that reproduces da-tese-ao-produto.md section 1.3's full 1h table (Naive0, OLS, RF, ARIMA rows) **so that** the library is provably correct against the one horizon the thesis itself calls "the most demanding/noisy configuration" before any service is allowed to depend on it.

Acceptance criteria:
- [ ] `tests/test_regression_1h.py` reconstructs (from available thesis source data/scripts, or a documented synthetic proxy if the original dataset isn't available in this repo) an out-of-sample scenario for the 1h horizon and runs it through `run_validation_protocol` (NFE-014).
- [ ] Test assertions cover, within a documented tolerance, every published 1h number from section 1.3: Naive0 MAE 0.003627/RMSE 0.005321; OLS MAE 0.003683 (+1.55%)/RMSE 0.005367/DA 51.33/F1 0.528/DM 0-better-4-worse; RF MAE 0.004033/RMSE 0.005692/DA 51.12/F1 0.427/DM 0/13; ARIMA MAE 0.045971/RMSE 0.051331/DA 50.27/F1 0.488/DM 0/53.
- [ ] If exact reproduction of the original dataset isn't possible inside this library's test suite (the thesis's raw BTC data may not be checked into this repo), the test explicitly documents which numbers are reproduced from a checked-in reference fixture vs. which are only unit-tested at the function level (NFE-005–012) — the story is not "done" silently if it quietly downgrades to partial coverage; that downgrade must be visible in the test file and PR description.
- [ ] `uv run pytest` in `libs/naive_first_engine` passes with this suite included, gating any future `services/validation-service` work per implementation-plan.md section 9 ("must pass a regression test against the thesis's own numbers before any service is allowed to depend on it").

Rationale for priority: implementation-plan.md section 9 states this explicitly as a hard gate before any service may depend on the library — it is the single acceptance bar for this entire module being "done," not just one story among many.
Depends on: NFE-014

### NFE-016 — Regression suite: reproduce the thesis's published 6h and 24h results tables [Should]
**As** `services/validation-service` **I want** the same regression coverage extended to the 6h and 24h horizon tables from da-tese-ao-produto.md section 1.3 **so that** the library's overlapping-horizon path (NFE-012's Harvey correction) is verified against real published numbers, not just synthetic unit tests.

Acceptance criteria:
- [ ] `tests/test_regression_6h.py` and `tests/test_regression_24h.py` reproduce, within documented tolerance, the published Naive0/OLS/RF rows for each horizon (6h: Naive0 MAE 0.009110, OLS MAE 0.009533/DA 52.51/F1 0.526/DM 4/18, RF MAE 0.010936/DA 50.33/F1 0.480/DM 0/30; 24h: Naive0 MAE 0.019720, OLS MAE 0.020895/DA 50.80/F1 0.524/DM 14/22, RF MAE 0.029491/DA 49.48/F1 0.462/DM 7/34).
- [ ] Same partial-coverage disclosure rule as NFE-015 applies if the original dataset can't be reconstructed exactly.
- [ ] These two horizons specifically exercise the Harvey-corrected DM path (NFE-012), so at least one assertion per test file confirms the DM verdict differs from what an uncorrected test would report on the same fixture (demonstrating the correction mattered for this data, not just that a number matches by coincidence).

Rationale for priority: valuable and expected before a client-facing report ever cites 6h/24h numbers, but the 1h suite (NFE-015) is the documented hard gate (implementation-plan.md section 9) — this extends confidence rather than being the minimum bar, so it's Should, not Must.
Depends on: NFE-015

### NFE-017 — Standalone publishability check [Should]
**As** the future licensing/open-core business line (da-tese-ao-produto.md section 2.4, "SDK/licença do motor de validação") **I want** confirmation that this library builds and installs with zero access to the rest of the monorepo **so that** it can actually be published standalone later "without a rewrite," as solution-design.md section 3.4 promises.

Acceptance criteria:
- [ ] A CI or local check builds `libs/naive_first_engine` in a clean environment/venv containing only its own `pyproject.toml` dependencies (no implicit reliance on `libs/common`, any service code, or repo-root config).
- [ ] `import naive_first_engine` and a smoke call to `run_validation_protocol` succeed in that isolated environment.
- [ ] The check is documented (e.g. a short script or CI job) so it can be re-run whenever a new dependency is added, catching accidental coupling early rather than at actual publish time.

Rationale for priority: directly serves the stated revenue model (section 2.4) and an explicit design promise (solution-design.md section 3.4), but doesn't block correctness of the core protocol — it's a packaging safeguard, appropriately Should rather than Must at this stage.
Depends on: NFE-001

### NFE-018 — Public API doc-sync check [Could]
**As** a future contributor extending this library **I want** a check that `libs/naive_first_engine/README.md`'s public function list stays in sync with the actual code **so that** the README doesn't silently drift out of date, per implementation-plan.md section 8's documentation convention.

Acceptance criteria:
- [ ] A script or CI step compares the public (non-underscore-prefixed) top-level functions/classes in `splitting.py`, `baselines.py`, `metrics.py`, `dm_test.py`, `report_schema.py` against a function-signature list maintained in the README, and fails if they diverge.
- [ ] Running the check locally after intentionally adding an undocumented public function demonstrates a failure (verifies the check actually works, not just that it exists).

Rationale for priority: implementation-plan.md section 8 explicitly proposes this ("CI should fail if they drift — add a doc-check step once the first lib ships") but frames it as a follow-up once the first lib ships, not a blocker for the lib itself being usable — appropriately Could.
Depends on: NFE-014

### NFE-019 — Won't: executing client-supplied model code inside this library [Won't]
Not written as a story. Flagged explicitly: solution-design.md section 1, principle 2 states the MVP accepts client *predictions* (CSV/Parquet), never model binaries, specifically to avoid a sandboxing/security problem — "running client model artifacts is a deliberate phase-2+ decision, not an MVP requirement." No story in this backlog proposes an execution path for arbitrary client model code inside `naive_first_engine`, and none should be written until that trigger is separately and explicitly revisited.

Rationale for priority: out of scope by explicit design decision, not an oversight — recorded here so it isn't silently proposed later without re-examining the security tradeoff.
Depends on: none

### NFE-020 — Won't: economic/profitability metrics inside this library [Won't]
Not written as a story. Flagged explicitly: da-tese-ao-produto.md section 2.3.5 scopes transaction costs, slippage, execution, and portfolio simulation to the separate `services/economic-service`, itself gated (implementation-plan.md section 6, trigger #11) on "a specific client model has already demonstrated stable outperformance in `validation-service` — never before, per the ethical boundary in docs section 2.7." No story in this backlog adds profit/loss, return-on-capital, or trading-signal framing to any metric or report object in `naive_first_engine` — doing so would blur this library's audit/validation positioning into the trading-signal positioning the whole business case (section 2.1) explicitly rejects.

Rationale for priority: out of scope by explicit ethical/positioning boundary, not an oversight — recorded so a future request to "just add a quick P&L column to the metrics" is refused with the documented reason rather than silently accepted.
Depends on: none
