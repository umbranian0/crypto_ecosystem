# Sprint 63 — Epic B: RPT-001 certification-style PDF export in `services/reporting-service` (+ minimal gateway-api pass-through)

Sprint goal: by the end of this sprint, a tenant's stored validation audit report (including a status-only report)
can be downloaded as a PDF audit artifact, rendered from the same stored HTML as today, with the default response
unchanged.

Backlog source: `docs/product/backlog-trust-and-admin-ops.md`, Epic B, `RPT-001` (Should, already approved/prioritized).
Capacity: not stated by the requester; one story, no capacity claim made.

## Independent verification (code read, not taken from the backlog)

- **RPT-001 is not done.** Grep of `services/` for `pdf`/`weasyprint`/`application/pdf` finds only the README line
  ("PDF export is also out of scope", `services/reporting-service/README.md` line 65) and an unrelated seed CSV.
  `pyproject.toml` has no WeasyPrint dependency; `routers/report_retrieval.py::get_report` has no `format` parameter
  and always returns the JSON `ReportDetailResponse`.
- **Fact that shapes the design: the HTML is stored, not re-rendered on read.** `ReportDetailResponse.content` is the
  HTML string persisted at generation time (RS-002/RS-004). So the one-rendering-source rule is satisfied most simply
  by converting the stored `content` to PDF; no second renderer and no re-run of the Jinja2 template. A status-only
  report is stored as status-only HTML, so PDF parity falls out for free.
- **"Byte-identical default" means the existing JSON envelope.** Today the default is `application/json` with HTML
  inside `content`, not a bare HTML body. The backlog wording ("HTML response") is loose; the binding rule is: no
  `format` parameter -> same JSON, same fields, unchanged.
- **Gateway gap (changes the minimal scope).** `reporting-service` is internal. `gateway-api/routers/reports.py::get_report`
  forwards through `_call_downstream` and rebuilds a JSON `ReportDetailResponse`, so a PDF response cannot pass through
  it as is. Without a gateway change no tenant can obtain the PDF. The backlog AC only names `reporting-service`.
- **Dockerfile is `python:3.11-slim`** with no native libs; WeasyPrint needs Pango/Cairo-related system packages, so
  the image must change. The Windows host has no such libs (reporting-service `.venv` is a cp310 Windows venv).
- `scripts/check_doc_sync.py` / `tests/test_doc_sync.py` (RS-008) compare README route docs against the app; a new
  route or documented query parameter must be reflected in the README or that test fails.

## Decisions made in this plan (Tech Lead may refine; flagged where it matters)

1. **Route shape: `GET /reports/{id}?format=pdf`** on the existing handler (backlog's first option), returning
   `application/pdf` with `Content-Disposition: attachment`. Unknown `format` values -> 422 (do not silently fall back).
   Same tenant-scoping 404 for missing and cross-tenant, no new branch.
2. **Conversion lives in one small function** (e.g. `render_pdf(html: str) -> bytes`) in `reporting-service`; the
   router calls it only when `format=pdf`. WeasyPrint is imported lazily inside it so the service (and the default
   path) still imports and runs where native libs are absent.
3. **Test strategy on the Windows host (decision):**
   - Router/contract tests (200 + `application/pdf` + attachment header, 404 cross-tenant, 422 bad format, default
     JSON unchanged, status-only path) run everywhere with `render_pdf` monkeypatched to return a stub `%PDF-` bytes
     value.
   - One real-render test (output starts with `%PDF-`, non-trivial length, from both a completed and a status-only
     stored HTML fixture) is marked `@pytest.mark.pdf_render` and auto-skips when WeasyPrint's native libs cannot be
     loaded (skip on `OSError`/`ImportError` at import probe). It is run for real inside the rebuilt container.
   - The container run of that marked test (and the QA live check) is the proof of real rendering; the Windows host
     suite must stay green with the render test reported as skipped, not failing.
4. **Dockerfile:** add the system packages WeasyPrint needs (Pango + a minimal font package so text is not blank;
   Tech Lead picks exact apt package names for `python:3.11-slim` and verifies in the build), `--no-install-recommends`,
   apt lists cleaned, installed before the non-root user step. `uv.lock` must be regenerated with `weasyprint`.
5. **Gateway pass-through: included, minimal (flagged below).** `GET /reports/{id}?format=pdf` in `gateway-api`
   forwards the parameter and streams the PDF bytes back with the same status/headers, authenticated via the existing
   `get_authenticated_tenant`. Default (no `format`) path untouched. No tenant logic reimplemented.
6. **dashboard-web: no change.** No new UI, no link, since the backlog AC requires none. The PDF is reachable through
   the gateway API for API clients and pilot hand-offs. A download link in the UI is a separate story if wanted.
7. **No PDF for other report kinds.** Only `validation_audit` exists today; RPT-002's `consistency_trend` PDF stays a
   later ticket per RPT-002's own AC.

## Stories in scope, in execution order

1. **RPT-001** — one story, executed in this internal order (Tech Lead may split into tickets):
   a. Dockerfile native libs + `weasyprint` dependency + lockfile, container builds and imports WeasyPrint (everything
      else depends on this; do first so the real-render risk surfaces early).
   b. `render_pdf` + `?format=pdf` on `report_retrieval.py` + tests (stubbed on host, real in container).
   c. gateway-api `?format=pdf` pass-through + tests.
   d. Docs: README updates, ticket index, backlog status.

## Binding constraints carried into tickets

- One rendering source: PDF is produced from the stored HTML `content` (the existing Jinja2 output). No second
  template, no PDF-only content, no separate metrics computation.
- WeasyPrint must not fetch remote resources (no network access during render; use a restrictive `url_fetcher` or
  confirm the template has no external references). Report content is tenant data; the PDF must not leak across tenants
  or trigger outbound requests.
- Status-only report -> status-only PDF; assert no metrics table appears (extract text or check source HTML fixture).
- Positioning: the PDF carries the same content as the HTML audit report, so the existing honest naive-first framing
  and "statistical accuracy is not economic value" language is preserved. Any new text added (PDF title, filename,
  header/footer, any "certification" wording) must be an audit artifact: no prediction/forecast/signal/"recommend"
  language, and no claim of certification, endorsement or approval beyond what the report states. "Certification-style"
  describes the document form, not a granted seal. Filename suggestion: `audit-report-<id>.pdf`, no model-quality
  adjectives.
- Boundary rules: `gateway-api` uses `reporting-service` HTTP only; no service imports another service's code. Gateway
  must not duplicate or inspect report content.
- Keep it simple: no caching/storage of generated PDFs, no async job, no page-template/branding system, no new DB column.

## Stories explicitly deferred

- `RPT-002` (consistency-trend report), `RPT-004`, Epic A/C remainder (`ADMIN-005`, etc.): not pulled in.
- dashboard-web PDF download link/button: deferred (not required by AC).
- PDF for `consistency_trend` kind: deferred to after RPT-002.
- Sprint 62 follow-up (matview refresh lag vs. empty-data message) and sprint-61 `DBOPT-*` follow-ups: not in this sprint.

## Definition of done

- RPT-001 acceptance criteria checked in `docs/tickets/` ticket(s); gateway pass-through noted as a disclosed addition
  to the AC list in the backlog.
- Tests: reporting-service suite green on the Windows host (render test skipped by marker, never failing); gateway
  suite green; default JSON response unchanged (assert existing response shape); PDF 200/404/422 and status-only parity
  covered; real-render test passes inside the rebuilt reporting-service container.
- Positioning grep (prediction/forecast/signal/recommend, certified/approved claims) over every touched file and new text.
- Docs as part of the work: `services/reporting-service/README.md` (PDF line replaced with shipped behavior, route
  table updated so `check_doc_sync` passes, native-lib and test-marker notes), `services/gateway-api/README.md`,
  `docs/tickets/README.md` Sprint 63 section, `docs/product/backlog-trust-and-admin-ops.md` RPT-001 status in place.
- QA gate (mandatory): Tech Lead raises the `qa` agent (`/qa-validation`) after tickets are done. QA runs against the
  real rebuilt `naive-first-*` containers (confirm images are not stale; do not use host-run scripts, which hit a stale
  SQLite copy): generate a report for a completed run and download `?format=pdf` via the gateway, confirm
  `application/pdf`, `%PDF-` header, readable text; same for a status-only report (run not completed); default
  no-`format` response unchanged; cross-tenant request returns 404; unauthenticated gateway request rejected; invalid
  `format` rejected. QA fixtures are additive only, named "QA63 ...", left in place, and never touch audit-log rows or
  existing data (no deletion; the cleanup line is waived by the same standing user decision as Sprint 62).

## Next (not this sprint)

RPT-002 (then its PDF extension), ADMIN-005 (`/grilling` first), optional dashboard-web download link, Sprint 62
matview-lag copy follow-up.
