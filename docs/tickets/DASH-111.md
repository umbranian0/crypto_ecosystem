# DASH-111 — Dataset browsing view

**Sprint**: 18. **Module**: `services/dashboard-web`. **Status**: done. **Priority**: Should.
**Depends on**: `DASH-108`, `GW-020`.

## Analysis
Story: backlog `DASH-111`, unchanged design. Presentation layer over data `DASH-108` already fetches —
not on the Must critical path but genuinely independent of the blocked Epic E tickets (no operator auth
needed, it's a tenant-session page like the rest of `dashboard-web` today).

## Design
File: new `services/dashboard-web` route/template. **DRY check**: extract `DASH-108`'s
`GET /ingestion/datasets`-calling + dropdown-rendering code into one shared component reused by both
pages, not two near-identical implementations.

## Implementation acceptance criteria
- [x] New page listing all of a tenant's ingested datasets (source, earliest/latest timestamp,
  row_count) via `GW-020`'s proxy. `GET /datasets` (`src/app/routers/runs.py`), template
  `datasets.html`.
- [x] Links into `DASH-108`'s submit-run form (pre-selecting "Stored dataset" mode + that source)
  via `/runs/new?dataset_reference_source=<source>`; `run_new_form` grew that query param to
  pre-select the dropdown. A "Trigger a crawl" link per row points at `/monitoring` as a
  forward-compatible placeholder (`DASH-110` is not built yet, per this ticket's own scope).

## Test acceptance criteria
- [x] Test covers empty-history and populated-history rendering (`tests/test_datasets.py`), plus
  a transport-failure degrade, the session-required redirect, and the `run_new_form` pre-fill
  link. Full suite: 90 passed, 5 deselected (e2e), 0 failures -- zero regressions to the
  pre-ticket baseline (a transient failure observed mid-session in
  `tests/test_monitoring.py::test_monitoring_template_has_no_banned_positioning_words`, traced to a
  concurrent, unrelated in-flight edit to `monitoring.html` by another ticket's work, was gone by
  the final run and is not part of this ticket's diff).

## Review acceptance criteria (Tech Lead verifies personally)
- Confirms the dropdown-population logic is a shared component, not duplicated from `DASH-108`.
  `_fetch_ingestion_datasets(client, headers)` (`src/app/routers/runs.py`) is the single
  implementation both `run_new_form` (DASH-108) and `datasets_list` (this ticket) call -- see
  README.md's "Ingested datasets (DASH-111)" section for both call sites.

## Documentation acceptance criteria
- [x] `services/dashboard-web/README.md` documents the new page and its route -- see "Ingested
  datasets (DASH-111)" section.
