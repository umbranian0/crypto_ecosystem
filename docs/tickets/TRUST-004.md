# TRUST-004 — Auto-generated reproducibility statement per report (`reporting-service`)

**Sprint**: 56. **Module**: `services/reporting-service` (template only). **Status**: done (Implementation/
Test/Documentation acceptance criteria all met and Tech-Lead-verified — dev pass covered the template,
tests, and `services/reporting-service/README.md`; Tech Lead completed the remaining two Documentation
items, `docs/product/backlog-trust-and-admin-ops.md` and `docs/tickets/README.md`, in the same review
pass, per the `RPT-003` precedent). **Priority**: Should.
**Depends on**: `TRUST-003` (real data dependency, not priority order — this ticket's entire new
subsection is populated from `engine_version`/`config_fingerprint`, fields that do not exist on
`RunDetailResponse` until `TRUST-003` ships and merges). **Blocks**: nothing.
**Can run in parallel with**: nothing this sprint (strictly sequential after `TRUST-003`).

## Analysis

Covers `docs/product/backlog-trust-and-admin-ops.md`'s `TRUST-004` acceptance criteria in full. Verified
directly against the real code:

- `services/reporting-service/src/app/renderers/validation_audit.py` (read in full):
  `ValidationAuditRenderer.render(run, splits, *, narrative_html=None)` passes `run` (a
  `RunDetailResponse` instance) straight into the Jinja2 template as the `run` context variable — no
  field is extracted, filtered, or transformed before the template sees it. `run.engine_version`/
  `run.config_fingerprint` (once `TRUST-003` ships) are therefore automatically available in the
  template context with **zero Python code change** in this file.
- `services/reporting-service/src/app/generation.py` (read in full): `generate_validation_audit_report`
  fetches `GET /runs/{id}` from `validation-service` over HTTP (`httpx`) and reconstructs
  `run = RunDetailResponse(**run_response.json())`. Since `RunDetailResponse` is `libs/common`'s single
  canonical definition (both services import the same class, ARCH-003), the two new optional fields
  round-trip through this reconstruction with no code change here either — confirmed, not assumed: this
  is the same additive-field/default-`None` precedent every prior `RunDetailResponse` extension
  (`warnings`, `feature_lineage`, `has_client_model`, `label`) already relied on for this exact call
  site.
- `services/reporting-service/src/app/templates/validation_audit.html.jinja` (read in full): today's
  section 2, "Leakage-protocol parameters" (lines 32–40), lists `Horizon`, `Purge gap (hours)`,
  `Splits evaluated`, immediately followed by section 3, "Results table (per split)" (line 42). Both
  sections sit inside the same `{% if run.status != "completed" %}...{% else %}...{% endif %}` guard
  (line 24) that already omits every results-dependent section for a non-`"completed"` run. **This
  ticket's new subsection belongs inside that same `else` branch, between line 40 (end of section 2) and
  line 42 (start of section 3).**
- **Net: this ticket's entire scope is the template file.** No Python change is needed in
  `validation_audit.py` or `generation.py` — confirmed by tracing both files above, not assumed from the
  sprint plan's own citation.
- `dataset reference/source` (one of the backlog's four required subsection facts): `RunDetailResponse`
  already carries `dataset_id` (the field the rest of the template already renders in section 1,
  "Scope", as `{{ run.dataset_id }}`) — there is no separate `dataset_reference`/`dataset_source` field
  persisted anywhere on the run record (confirmed: `services/validation-service/src/app/routers/
  runs.py`'s own `GET /runs/{run_id}/features` docstring states plainly "the original `dataset_reference`
  dict `POST /runs` used [is] not persisted anywhere"). This subsection therefore reuses `run.dataset_id`
  verbatim — the same value already displayed elsewhere in this report, not a new field, not a second,
  independently-sourced reference string.
- **Sprint-57 file-overlap heads-up** (`docs/sprints/sprint-56.md`'s own flag): a tentative next sprint's
  `TRUST-001`/`TRUST-005` pairing also touches this same template file next. This ticket's new
  subsection is numbered `2.5` (not a renumber of sections 3–7) specifically so that future sprint does
  not have to rebase around a half-renumbered document — see Design below.

**Leakage-protocol safety check (CLAUDE.md)**: this is a template-only, read-only rendering change. No
split/baseline/metric/DM-test value is recomputed, re-thresholded, or re-interpreted — the new
subsection only renders two already-computed string fields (`engine_version`, `config_fingerprint`)
plus one already-rendered-elsewhere field (`dataset_id`) and one fixed, hand-authored sentence. Nothing
here can alter what `naive_first_engine` computed.

**Positioning check (CLAUDE.md)**: the fixed reproducibility sentence must describe re-running the
*validation protocol* under the same configuration, never imply the platform predicts prices or that a
"different result on re-run" is itself a trading signal — it states a methodology/audit claim only.

## Design

**Pattern**: none newly introduced — a same-shape extension of an existing Jinja2 template, matching the
"template-only, no renderer/generation Python change" precedent this ticket's own Analysis confirmed.

**Files touched** (scoped to `services/reporting-service` only):
- `services/reporting-service/src/app/templates/validation_audit.html.jinja`
- `services/reporting-service/tests/test_renderers.py` (new/extended tests, same file the existing
  `ValidationAuditRenderer` tests already live in — no new test module)

**DRY check note**: grepped `templates/` and `renderers/` before writing this ticket — no existing
"fingerprint" or "reproducibility" rendering logic exists anywhere in this service to duplicate. The new
subsection reuses `run.dataset_id` (already rendered in section 1) rather than introducing a second,
independently-sourced "dataset" string.

**Section numbering decision (Tech Lead's call, disclosed)**: new subsection is `<h2>2.5.
Reproducibility statement</h2>`, positioned between today's section 2 and section 3. Chosen over
renumbering sections 3–7 to 4–8 specifically because `docs/sprints/sprint-56.md`'s own file-overlap note
flags that a tentative `sprint-57` (`TRUST-001`/`TRUST-005`) touches this same template next — a `2.5`
subsection leaves every existing section number byte-stable, so that future sprint's diff against this
file stays minimal and unambiguous rather than having to reconcile a renumbering.

**Template addition** (inside the existing `{% else %}` branch, between section 2 and section 3):

```html
<h2>2.5. Reproducibility statement</h2>
{% if run.engine_version and run.config_fingerprint %}
<ul>
    <li>Engine version (naive_first_engine): {{ run.engine_version }}</li>
    <li>Config fingerprint (SHA-256 of this run's split configuration): {{ run.config_fingerprint }}</li>
    <li>Dataset reference: {{ run.dataset_id }}</li>
</ul>
<p>Re-running this exact configuration against the same dataset and the same naive_first_engine version
is expected to reproduce these results. A different result obtained under the same engine version and
config fingerprint should be investigated as a regression, not treated as a new finding.</p>
{% else %}
<p>Engine version / config fingerprint not available for runs created before this platform tracked
engine fingerprints.</p>
{% endif %}
```

Both fields are checked together (`if run.engine_version and run.config_fingerprint`) rather than
independently, since `TRUST-003`'s own contract is that they are populated together, at the same
`create_run` call, for every post-migration run — there is no valid state where exactly one of the two
is non-null for a real run. Checking both is defense in depth against a malformed/partial record, not an
expected branch.

## Implementation acceptance criteria

- [x] `validation_audit.html.jinja` gains the "2.5. Reproducibility statement" subsection exactly as
  drafted in Design (or functionally equivalent wording — exact copy is the dev agent's call, but must
  cover all four required facts: `engine_version`, `config_fingerprint`, dataset reference/source, and
  the fixed reproducibility-expectation sentence), positioned strictly between section 2 and section 3,
  inside the existing `{% if run.status != "completed" %}...{% else %}` guard's `else` branch.
- [x] A fingerprinted run (`run.engine_version`/`run.config_fingerprint` both non-null) renders the
  engine version, config fingerprint, dataset reference, and the fixed reproducibility sentence.
- [x] A null-fingerprint run (either field `None` — in practice both, per `TRUST-003`'s contract) renders
  the explicit "not available for runs created before this platform tracked engine fingerprints" note
  (or equivalent wording covering the same fact) — **never** a fabricated/inferred fingerprint, never a
  blank/empty subsection that silently omits the explanation.
- [x] No existing section (1, 3, 4, 5, 6, 7) is renumbered, reordered, or has its rendered content
  changed — `git diff` against the template shows a pure insertion, not a restructure.
- [x] A non-`"completed"` run (`run.status != "completed"`) still omits this subsection entirely, same as
  every other results-dependent section today (it lives inside the same `else` branch — this should fall
  out by construction, not require new conditional logic).

## Test acceptance criteria

- [x] Unit test (extends `tests/test_renderers.py`): a completed run with non-null
  `engine_version`/`config_fingerprint` renders all four required facts (engine version string, config
  fingerprint string, dataset id, and the fixed reproducibility sentence) in the output HTML.
- [x] Unit test: a completed run with `engine_version=None, config_fingerprint=None` (the default —
  simulating a pre-`TRUST-003` run, exactly what `test_renderers.py`'s existing `_make_run` helper
  already produces unmodified) renders the "not available for runs created before this platform tracked
  engine fingerprints" note, and does **not** render the string `"None"` anywhere in that subsection
  (guards against Jinja2's default `None -> "None"` string coercion leaking through as a fake-looking
  value).
- [x] Unit test: the new subsection's heading text appears strictly after "Leakage-protocol parameters"
  and strictly before "Results table" in the rendered HTML string (position assertion via substring
  index comparison, e.g. `html.index("Reproducibility statement") <
  html.index("Results table (per split)")`), proving the placement acceptance criterion is genuinely
  enforced, not just visually eyeballed.
- [x] Existing `test_renderers.py` tests (`test_completed_run_with_mixed_verdicts_...`,
  `test_run_that_never_beats_naive_...`, `test_failed_run_with_no_splits_...`,
  `test_running_run_with_no_splits_...`, the two narrative tests) all still pass unmodified — proves the
  addition doesn't perturb any existing rendered content/assertion.
- [x] This ticket does not touch `libs/naive_first_engine`, a `Baseline`/model-adapter, or a
  feature-engineering step — no thesis-numbers regression check applies.

## Review acceptance criteria (Tech Lead verifies personally)

- Reads the real `git diff` for `validation_audit.html.jinja` and `test_renderers.py`; confirms the diff
  is a pure insertion (no existing line changed/removed/renumbered).
- Personally runs the full `services/reporting-service` test suite (not just the new/changed tests) and
  confirms it passes clean, with no regression in any pre-existing test.
- Confirms, by reading the rendered HTML in a test, that the null-fingerprint case never renders a
  fabricated value and never leaks a bare `"None"` string.
- Confirms the new subsection sits inside the existing `{% if run.status != "completed" %}...{% else
  %}` guard (i.e. is correctly omitted for a non-completed run) by reading the template's actual
  indentation/nesting, not just trusting the ticket's own Design section.
- Confirms `RunDetailResponse`/`generation.py`/`validation_audit.py` genuinely required zero Python
  change (`git diff --stat` shows only the template and test file touched).
- Positioning/leakage re-check (CLAUDE.md): confirms the new sentence describes re-running the
  *validation protocol*, not a prediction/trading claim, and that no metric/DM value is recomputed or
  reinterpreted anywhere in the diff.

**Tech Lead review outcome (personally verified, not taken on the dev agent's self-report)**: read the
real `git diff` for `validation_audit.html.jinja` (pure 15-line insertion, no existing line
changed/removed/renumbered, positioned exactly between section 2 and section 3 inside the existing
`else` branch), `test_renderers.py` (four genuine new tests plus a backward-compatible `_make_run`
extension — both new kwargs default to `None`, so every pre-existing call site is unaffected), and
`README.md`. Confirmed `git diff --stat` shows only `README.md`, the template, and the test file touched
(plus an unrelated, harmless `uv.lock` drift-sync the dev agent disclosed — pre-existing
`naive-first-ai-assist` dependency already in `pyproject.toml` from an earlier sprint, the lockfile was
simply stale; no behavior change). Personally re-ran the full `services/reporting-service` test suite:
**63 passed, 9 skipped** (Postgres-dependent RLS tests skipped, no live DB in this sandbox — matches the
dev agent's own reported number exactly). Confirmed the null-fingerprint case never renders a fabricated
value and never leaks a bare `"None"` string (read the test and its assertion directly). Confirmed the
new subsection sits inside the `{% if run.status != "completed" %}...{% else %}` guard by reading the
template's actual indentation. Confirmed `RunDetailResponse`/`generation.py`/`validation_audit.py`
required zero Python change. Positioning/leakage re-check: the reproducibility sentence describes
re-running the validation protocol only, no metric/DM value is recomputed or reinterpreted anywhere in
the diff.

## Documentation acceptance criteria

- [x] `services/reporting-service/README.md` gets a new `TRUST-004` note (adjacent to the existing
  `ValidationAuditRenderer`/RS-003 "Design notes" bullet describing the report structure) stating: the
  report now includes a "2.5. Reproducibility statement" subsection sourced verbatim from
  `RunDetailResponse.engine_version`/`.config_fingerprint`/`.dataset_id`, and its explicit null-case
  wording for pre-`TRUST-003` runs.
- [x] `docs/product/backlog-trust-and-admin-ops.md`'s `TRUST-004` entry marked done, all three
  acceptance-criteria boxes checked, pointing to this ticket file. (Tech Lead completes this in the
  review pass, per this repo's convention.)
- [x] `docs/tickets/README.md`'s Sprint 56 section (created for `TRUST-003`) gets this ticket added
  alongside it, with its own status.
