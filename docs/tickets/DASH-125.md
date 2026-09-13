# DASH-125 — UAT-001 frontend: honest "Model" column label when no client model was submitted

**Status: done (Sprint 31).**

**Module**: `services/dashboard-web` only.
**Depends on**: `VS-029` (needs the real `has_client_model` field on `RunDetailResponse`/
`SplitResultResponse` — do not start until VS-029 is merged/verified done).
**Sequencing**: first of the three Track A tickets (`DASH-125` → `DASH-126` → `DASH-127`) — establishes the
disclaimer-block layout `DASH-126` extends.

## Analysis

Covers `docs/product/backlog-uat-findings.md` UAT-001's frontend half. `run_detail.html`'s "Model" column
header/legend, `RAV-002`/`RAV-003`'s chart legends (`_error_chart.html`/`_dm_verdict_chart.html`), `FHS-003`'s
summary panel (`_forecast_horizon_summary_panel.html`), and `FHS-004`'s copy-summary export
(`build_shareable_summary_text` in `app/routers/runs.py`) must all render the placeholder disclosure
identically whenever `run.has_client_model` (VS-029) is `False`, and plain "Model" when `True` — no chart or
panel independently re-derives or contradicts the label.

## Design

**Pattern**: none from implementation-plan.md section 7 — presentation-only string selection based on an
already-fetched field.

**DRY check**: grepped `services/dashboard-web/src/app/routers/runs.py` and
`services/dashboard-web/src/app/templates/`. `run_detail`'s handler already fetches `run` (a
`RunDetailResponse`, now carrying `has_client_model` once VS-029 lands) once and passes it to every template
this ticket touches — no second fetch needed. To avoid re-deriving the label string in five separate places
(the exact same failure mode implementation-plan.md section 9 warns against), add **one** computed value in
`run_detail`'s handler and pass it through the existing context dict, consumed verbatim everywhere:

```python
MODEL_COLUMN_LABEL = "Model"
MODEL_COLUMN_PLACEHOLDER_LABEL = "Model (NaiveLast placeholder -- no client model submitted)"

def model_column_label(run: RunDetailResponse) -> str:
    return MODEL_COLUMN_LABEL if run.has_client_model else MODEL_COLUMN_PLACEHOLDER_LABEL
```

Put this in `app/charting.py` (a pure function, no I/O, matching that module's existing convention of
housing `verdict_category_and_css_slug`/`build_error_chart`/`build_dm_verdict_chart` — no Jinja2 import
there) or directly in `app/routers/runs.py` next to `build_shareable_summary_text` if `charting.py` is judged
the wrong home (Tech Lead's call at review time — either is acceptable as long as there is exactly one
function, not five copies).

**Files touched**:
- `services/dashboard-web/src/app/charting.py` (or `app/routers/runs.py`): add `model_column_label(run)`.
- `services/dashboard-web/src/app/routers/runs.py`: `run_detail` handler — compute
  `model_column_label_text = model_column_label(run)` once, add to the `TemplateResponse` context dict as
  `"model_column_label": model_column_label_text`. `build_shareable_summary_text(run, splits)` — add the
  same label logic inline (it already receives `run`, so `run.has_client_model` is available without a new
  parameter) as a prefixed line in the returned text when `run.has_client_model` is `False`.
- `services/dashboard-web/src/app/templates/run_detail.html`: the per-split table's "Model MAE"/"Model
  RMSE"/etc. column group header — add one `<tr>`/`<th colspan="7">{{ model_column_label }}</th>` spanning
  the model-metric columns (or replace each individual "Model ..." header's leading word with
  `{{ model_column_label }}` if that reads better structurally — Tech Lead's call, either satisfies the AC as
  long as the disclosure is visible above/on the model column group, not buried).
- `services/dashboard-web/src/app/templates/_forecast_horizon_summary_panel.html`: same treatment for its
  "Model MAE"/"Model RMSE"/etc. column group headers, consuming the same `model_column_label` passed through.
- `services/dashboard-web/src/app/templates/_error_chart.html`: the `chart-legend`'s "Model {{
  error_chart.metric_label }}" swatch label and the `<p class="chart-title">` — use `model_column_label`
  instead of the literal "Model" prefix.
- `services/dashboard-web/src/app/templates/_dm_verdict_chart.html`: no per-series "Model" label exists here
  today (bars are the platform's own verdict, not labeled "Model") — confirm this at implementation time; if
  there is genuinely nothing to change, note that explicitly rather than inventing a label to add.

## Implementation acceptance criteria

- [x] AC1 (UAT-001 AC2): `run_detail.html`'s "Model" column header renders
  `"Model (NaiveLast placeholder -- no client model submitted)"` when `run.has_client_model` is `False`,
  plain `"Model"` when `True`.
- [x] AC2 (UAT-001 AC3): RAV-002/003's chart legends and FHS-003's summary panel inherit the exact same label
  string (via the one shared `model_column_label` value) — no independent re-derivation. (`_dm_verdict_chart.html`
  confirmed to carry no per-series "Model" label at all — no change made there, not a gap.)
- [x] AC3 (UAT-001 AC4): FHS-004's copy-summary export includes the same disclosure verbatim when applicable.
- [x] AC4 (UAT-001 AC6): no computation changes — confirmed `libs/naive_first_engine` and
  `run_validation_protocol` untouched; only `services/dashboard-web` files changed.

## Test acceptance criteria

- [x] Unit test: a fixture run with `has_client_model=False` renders the placeholder label in `run_detail.html`;
  a fixture run with `has_client_model=True` renders plain "Model" — in the table header, at minimum (extend
  to chart partials/summary panel/export if the test harness already renders those, per this suite's
  existing precedent).
- [x] Unit test: `build_shareable_summary_text` output contains the placeholder disclosure line when
  `has_client_model=False`, and does not when `True`.
- [x] Full `services/dashboard-web` suite re-run, zero regressions (285 passed, up from 279, 7 e2e deselected).

## Review acceptance criteria (Tech Lead verifies personally)

- Confirm exactly one function computes the label (grep for the literal placeholder string across
  templates/Python — it should appear as a single Python string constant, referenced everywhere, not
  hand-typed five times).
- Confirm wording matches this platform's existing honesty-caveat style (DH-001 precedent) and does not use
  "prediction"/"signal" language (CLAUDE.md positioning check).
- Confirm `run_detail.html`'s disclaimer-block layout established here is one `DASH-126` can extend rather
  than fight over (read `DASH-126`'s ticket before approving this one's final diff, since it depends on this
  layout).

## Documentation acceptance criteria

- `services/dashboard-web/README.md`: document `model_column_label`/the placeholder-disclosure convention
  under its run-detail-page section.
- `docs/product/backlog-uat-findings.md`: UAT-001's remaining acceptance-criteria boxes checked, pointing at
  this ticket (frontend half) alongside `VS-029` (backend half).
