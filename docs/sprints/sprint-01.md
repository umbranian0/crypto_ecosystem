# Sprint 01 — libs/naive_first_engine (core validation protocol)

Sprint goal: Ship a pip-installable `naive_first_engine` library whose fixed split → baseline → metrics → DM-test protocol reproduces the thesis's published 1h results table, clearing the hard gate (implementation-plan.md section 9) before `services/validation-service` is allowed to depend on it.

Backlog source: docs/product/backlog-naive-first-engine.md (all 15 Must-priority stories, NFE-001 through NFE-015)

Stories in scope (execution order):

1. **NFE-001** — Package scaffolding. No dependencies; literal first step, nothing else can be built or tested without the package skeleton.
2. **NFE-002** — Rolling-origin walk-forward splitter. Depends on NFE-001; first stage of the fixed Template Method protocol order (implementation-plan.md section 7).
3. **NFE-003** — Configurable purge gap. Depends on NFE-002; extends the splitter before anything downstream consumes split boundaries.
4. **NFE-004** — Baseline Strategy interface. Depends on NFE-002 (needs `Split` shape); must exist before any concrete baseline to avoid Naive0/NaiveLast diverging from a not-yet-defined contract.
5. **NFE-005** — Naive0 baseline. Depends on NFE-004; mandatory naive floor, and a prerequisite for the DM test (NFE-011) and the Template Method orchestrator (NFE-014).
6. **NFE-006** — NaiveLast baseline. Depends on NFE-004; pairs with NFE-005 as the second mandatory benchmark, required by NFE-014.
7. **NFE-007** — Error metrics: MAE, RMSE. Depends on NFE-001 only; sequenced here (rather than immediately after NFE-001) because NFE-011 (DM test) needs both this and NFE-005 — grouping baseline completion and headline metrics adjacently keeps the DM-test prerequisites together.
8. **NFE-008** — Error metrics: sMAPE, MASE. Depends on NFE-001; no downstream story requires it before NFE-013, so it runs after the headline MAE/RMSE pair per the backlog's own stated priority ("not part of section 1.3 headline tables... can follow MAE/RMSE").
9. **NFE-009** — Directional metrics: DA, F1. Depends on NFE-001; required by NFE-013 (report schema), sequenced before it.
10. **NFE-010** — Out-of-sample R². Depends on NFE-001; completes the full metric set required by NFE-013.
11. **NFE-011** — Diebold-Mariano test core. Depends on NFE-005 and NFE-007, both now complete; statistical backbone of the audit, must exist before the Harvey correction (NFE-012).
12. **NFE-012** — Harvey correction for overlapping horizons. Depends on NFE-011; extends the DM test before it is frozen into the report schema (NFE-013).
13. **NFE-013** — Typed result/report schema objects. Depends on NFE-003, NFE-009, NFE-012 — all three now complete; bundles split boundaries, full metric set, and DM results into the output contract the orchestrator (NFE-014) returns.
14. **NFE-014** — Template Method orchestration. Depends on NFE-005, NFE-006, NFE-013 — all complete; wires the fixed split → baseline → metrics → DM-test order into one entry point, making every prior story composable and unskippable.
15. **NFE-015** — Regression suite: reproduce the thesis's published 1h results table. Depends on NFE-014; the hard completion gate for this module (implementation-plan.md section 9) — must run last since it exercises the full orchestrator end-to-end.

Stories explicitly deferred:
- **NFE-016** (regression suite for 6h/24h) — Should priority; depends on NFE-015. Extends confidence beyond the documented hard gate rather than being part of the minimum bar. Deferred to a future sprint.
- **NFE-017** (standalone publishability check) — Should priority; depends on NFE-001. Serves the future licensing business line, doesn't block core protocol correctness. Deferred to a future sprint.
- **NFE-018** (public API doc-sync check) — Could priority; depends on NFE-014. Explicitly framed in implementation-plan.md section 8 as a follow-up once the first lib ships, not a blocker. Deferred to a future sprint.
- **NFE-019, NFE-020** — Won't-priority items, not stories (client-model execution and economic/profitability metrics respectively, both out of scope by explicit design/ethical boundary). Not scheduled in any sprint; flagged for reference only.

Definition of done for this sprint:
- All 15 Must stories' acceptance criteria are met as written in docs/product/backlog-naive-first-engine.md.
- `uv run pytest` passes in `libs/naive_first_engine`, including `tests/test_regression_1h.py` (NFE-015), against the thesis's published 1h Naive0/OLS/RF/ARIMA numbers within documented tolerance.
- `run_validation_protocol` (NFE-014) is the only path to a `DMResult`; purge gap (NFE-003) and Harvey correction (NFE-012) cannot be bypassed by any code path, per their respective acceptance criteria.
- `libs/naive_first_engine/README.md` file layout matches the actual files shipped (no doc drift, per NFE-001).
- No code in this sprint touches `services/validation-service` or any other out-of-scope module listed in the backlog's scope section — the library remains dataset-agnostic, I/O-free, and standalone-importable.
- This gates trigger #3 in implementation-plan.md section 6 (`services/validation-service` scaffolding) — that trigger is not fired by this sprint; it is a future sprint's concern once NFE-015 passes.

---

## Sprint completion report (2026-08-05)

**Status: DONE — all 15 Must stories shipped. Trigger #3 (`services/validation-service`) is now cleared to fire.**

The Tech Lead agent hit an account-level API session limit mid-way through its final verification pass on NFE-015 (the last ticket) and terminated before writing this report. All 14 prior tickets had already been individually verified and marked done by the Tech Lead itself. The final verification of NFE-015 and this closing report were completed directly (not by a subagent) to avoid re-hitting the same session limit:
- Ran the full test suite directly: `libs/naive_first_engine` → **80 passed**, 0 failed.
- Read `tests/test_regression_1h.py` in full, including its disclosure block (Review acceptance criteria for NFE-015).
- Cross-checked all four models' 1h numbers (Naive0, OLS, RF, ARIMA — MAE/RMSE/DA/F1) against the published table in `docs/da-tese-ao-produto.md` section 1.3 by hand: all match within the documented tolerances.
- Read `metrics.py::oos_r2` directly and re-derived the formula (`1 - SSE(pred)/SSE(naive)`) to confirm it's naive-relative, not sklearn's mean-relative default — this was independently already verified by the Tech Lead per NFE-010's ticket file, re-confirmed here.
- Updated `docs/tickets/README.md` to mark NFE-015 done (it was individually complete in `docs/tickets/NFE-015.md`, just not yet reflected in the index when the Tech Lead's session ended).

**What got built** (`libs/naive_first_engine/src/naive_first_engine/`):
- `splitting.py` — rolling-origin walk-forward splitter with an always-enforced, non-bypassable purge gap (NFE-002, NFE-003).
- `baselines.py` — `Baseline` Strategy protocol, `Naive0`, `NaiveLast` (NFE-004, NFE-005, NFE-006).
- `metrics.py` — `mae`, `rmse`, `smape`, `mase`, `directional_accuracy`, `f1_directional`, `oos_r2` (naive-relative) (NFE-007–010).
- `dm_test.py` — Diebold-Mariano test with a mandatory, non-bypassable Harvey et al. (1997) long-run variance correction that degenerates exactly (not approximately) to the uncorrected statistic at horizon=1 (NFE-011, NFE-012).
- `report_schema.py` — typed, computation-free output contract (`SplitBoundaries`, `MetricSet`, `DMResult`, `BaselineResult`, `SplitResult`) (NFE-013).
- `protocol.py` — `run_validation_protocol`, the Template Method entry point enforcing split → baseline → metrics → DM-test with no shortcut path to a `DMResult` (NFE-014).
- `tests/` — 80 tests total, including `test_regression_1h.py`, the hard completion gate (NFE-015).

**Deviation worth flagging**: while building NFE-014, the dev agent found and fixed a real bug in `f1_directional` (`ZeroDivisionError` whenever a baseline predicts no "up" moves at all — which Naive0 does on every call by construction). This retroactively touched a file from the already-closed NFE-009 ticket. Documented in NFE-014's ticket file; flagged to the user for awareness rather than silently absorbed.

**Known, disclosed gap (not a defect)**: NFE-015's regression suite does not reconstruct RF's (0/13) or ARIMA's (0/53) Diebold-Mariano better/worse split counts — no per-split error fixture exists for those two models in this repo, and the backlog's own acceptance criteria explicitly allow stopping once one full B/W pair (OLS's, reproduced exactly) is done. This is stated at the top of `test_regression_1h.py`, not buried.

**Not started this sprint** (correctly out of scope): NFE-016/017/018 (Should/Could, deferred), NFE-019/020 (Won't, not stories), and anything in `services/validation-service` or any other module — `naive_first_engine` remains standalone, dataset-agnostic, and dependency-free as required.
