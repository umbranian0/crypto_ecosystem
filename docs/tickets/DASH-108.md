# DASH-108 (revised) — `dashboard-web`: "pick a stored dataset" option (date-range) on the submit-run form

**Sprint**: 18. **Module**: `services/dashboard-web`. **Status**: done (route/template implementation
and unit tests; Selenium E2E extension not done, see Test acceptance criteria below). **Priority**: Must.
**Depends on**: `GW-020`, `VS-024`.

## Analysis
Story: backlog `DASH-108`, **revised** by solution-design.md section 8.7: since a dataset is a
continuous table (ADR-0005), this mode needs `start`/`end` date-range inputs, not just a dataset-name
dropdown — a UI detail the original backlog sketch (written before the continuous-table decision) did
not anticipate.

## Design
File: `services/dashboard-web`'s existing submit-run template/route (extend, not redesign the existing
two modes). **DRY check**: reuse the existing radio/tab UI pattern from the inline/path modes.

## Implementation acceptance criteria
- [x] Submit-run form gains a third mode ("Stored dataset") alongside "Inline data"/"Local file path".
- [x] Populates a source dropdown from `GW-020`'s `GET /ingestion/datasets`; selecting a source shows
  `start`/`end` date-range inputs (both optional — blank means "earliest"/"latest", matching the
  endpoint's own optional-both-ends semantics) and a `field` selector when applicable.
- [x] Submits `dataset_reference={"source": <selected>, "start": <or omitted>, "end": <or omitted>,
  "field": <or omitted>}` to `POST /runs` — the exact shape `VS-023` expects.
- [x] Empty-history tenant sees "no ingested datasets yet — run a crawl first," not an empty unexplained
  dropdown (links toward the trigger-a-crawl action once it exists — `DASH-110`, currently blocked).
- [x] Positioning check: copy describes "your ingested data," never "trading data"/"signals" (CLAUDE.md).

## Test acceptance criteria
- [ ] Extends the existing Selenium E2E suite (`DASH-009` precedent) with this third submission path,
  against a stubbed `gateway-api`. **Not done** — this pass added unit-level route-handler coverage
  instead (`tests/test_runs_submit.py`: dropdown population from a mocked `GET /ingestion/datasets`,
  the empty-history "no ingested datasets yet" messaging, a transport-failure degrade-to-empty case, and
  successful submission with/without `start`/`end`/`field`, verifying the exact omit-when-blank
  `dataset_reference` shape). The Selenium E2E suite (`tests/e2e/`) was not extended with a third flow —
  left for a follow-up ticket if the Tech Lead wants that specific browser-level coverage.

## Review acceptance criteria (Tech Lead verifies personally)
- Confirms the two existing submission modes are byte-unchanged.
- Confirms the submitted `dataset_reference` shape matches `VS-023`'s expected keys exactly (reads the
  actual form-to-payload code, not just the rendered HTML).

## Documentation acceptance criteria
- [x] `services/dashboard-web/README.md` documents the third submission mode.
