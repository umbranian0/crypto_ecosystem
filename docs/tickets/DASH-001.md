# DASH-001 — Service scaffolding

**Status: done**

## Analysis
Story: DASH-001 (Must), no dependency — first ticket of a brand-new service, `services/dashboard-web`,
stood up under a disclosed trigger-#8 override (see `docs/sprints/sprint-11.md`'s "Pre-planning
checks" and `docs/product/backlog-dashboard-web.md`'s "Explicit trigger override" section — trigger
#8, implementation-plan.md section 6, has not fired; no pilot client exists). Acceptance criteria
(backlog): `uv`-managed `pyproject.toml` declaring FastAPI + Jinja2/HTMX deps, only `httpx` to call
`gateway-api` (no import of another *service's* code — `libs/*` remain importable per
implementation-plan.md section 2's module boundary map, "Imported by every service"); `src/app/`
skeleton (`routers/`, `dependencies/`, `templates/`); working `tests/`/pytest config, `uv run pytest`
passing with 0 collected as baseline; README status moved planned -> scaffolded with the trigger-#8
override note.

## Design
Pattern: none yet (pure scaffolding — no route/business logic exists to apply a pattern to). File
layout mirrors `services/gateway-api`'s and `services/validation-service`'s own `src/app/{routers,
dependencies}` shape (implementation-plan.md section 3), plus a new `templates/` directory for
Jinja2/HTMX (this service's own addition, since it's the first server-rendered UI service).

DRY check: grepped `services/gateway-api/pyproject.toml` and `services/validation-service/
pyproject.toml` before writing this service's own — reused the same `uv`/hatchling/pytest
conventions (dependency-groups `dev`, `testpaths = ["tests"]`) rather than inventing a new shape.
`naive_first_common` is included as a real dependency (not just `httpx`) because DASH-004/006 will
need to parse `gateway-api`'s proxied responses using the exact same `RunRequest`/`RunResponse`/
`RunDetailResponse`/`SplitResultResponse` models `gateway-api` itself imports from
`naive_first_common.contracts` (ARCH-003) — a third hand-copied field list here would violate the
DRY rule this platform already applied once (ARCH-003 existed specifically to stop `gateway-api` and
`validation-service` from maintaining two independent copies). `naive_first_common` is a `libs/*`
package, not another service's code, so this does not violate the "only httpx" constraint's intent
(that constraint is about not importing `gateway-api`'s or `validation-service`'s own `app.*` code).

## Implementation acceptance criteria
- [x] `services/dashboard-web/pyproject.toml` declares FastAPI + Jinja2/HTMX (`jinja2`,
  `python-multipart` for form parsing) + `httpx` + `naive_first_common` (editable path dependency,
  same pattern as `gateway-api`/`validation-service`); no import of `gateway-api`'s or
  `validation-service`'s own service code anywhere.
- [x] `src/app/` skeleton: `routers/__init__.py`, `dependencies/__init__.py`, `templates/base.html`
  (a minimal Jinja2 base layout with the HTMX `<script>` tag, since every later template will extend
  it — a scaffolding convenience, not a design decision about any specific page).
- [x] `src/app/main.py`: constructs the `FastAPI` app + `Jinja2Templates` environment; mounts no
  routers yet (later tickets add them).
- [x] `tests/` with `tests/__init__.py`, `tests/e2e/__init__.py` (DASH-009's future home); `uv run
  pytest` config via `pyproject.toml`'s `[tool.pytest.ini_options]`, including an `e2e` marker
  declaration up front (DASH-009 will use it, declaring it now avoids an "unknown marker" warning
  later and needs no further pyproject edits when DASH-009 lands).
- [x] README status moved planned -> scaffolded, states the trigger-#8 override explicitly (mirrors
  `gateway-api`'s own README precedent), and documents the `DASH-005` deferral up front so no later
  ticket has to retrofit that disclosure.

## Test acceptance criteria
- [x] `uv sync` succeeds (53 packages resolved/installed, confirmed by direct run).
- [x] `.venv\Scripts\python.exe -m pytest -q` from `services/dashboard-web` passes with 0 tests
  collected ("no tests ran") — confirmed by direct run, not assumed.

## Review acceptance criteria
- Tech Lead (this ticket was scaffolded directly, not delegated, matching the NFE-001/VS-001/LC-001/
  GW-001 precedent — "pure scaffolding, no design decision to delegate") confirms: `pyproject.toml`
  has no `sqlalchemy`/`alembic`/DB driver dependency (this service owns no schema — no data-access
  layer to scaffold, unlike every prior service's first ticket); `src/app/main.py` imports nothing
  from `app.routers`/`app.dependencies` of `gateway-api` or `validation-service`; `git status` scoped
  to `services/dashboard-web/` shows only the files this ticket added.

## Documentation acceptance criteria
- [x] `services/dashboard-web/README.md` status line updated (planned -> scaffolded), trigger-#8
  override stated explicitly, `DASH-005` deferral disclosed, local-setup/test-running instructions
  added.

## Outcome
Scaffolded directly by the Tech Lead (2026-08-12), not delegated — matches this repo's own
precedent for every module's first ticket (NFE-001/VS-001/LC-001/GW-001). Files added:
`services/dashboard-web/pyproject.toml`, `src/app/__init__.py`, `src/app/main.py`,
`src/app/routers/__init__.py`, `src/app/dependencies/__init__.py`, `src/app/templates/base.html`,
`tests/__init__.py`, `tests/e2e/__init__.py`, `.gitignore`. README updated in place.

**Known environment note**: this session hit an intermittent Windows-specific ENOENT error when
using the Write/Edit tools' own temp-file-then-rename mechanism directly inside this repo (and,
separately, in `bash`'s own file redirection and `uv sync`'s `.venv` creation via the bash shell) —
but *not* when the same operations were issued through PowerShell (`New-Item`, `Copy-Item`, or
invoking `uv sync`/`pytest` via `powershell -Command`). Every file affected was therefore written to
the session's scratchpad directory first and copied into place via `Copy-Item` (or created directly
via `New-Item` for empty `__init__.py` files), each copy verified afterward by reading the file back
from its real repo path. This is disclosed here so a future session hitting the same symptom knows a
working fallback exists.
