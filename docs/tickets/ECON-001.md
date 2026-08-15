# ECON-001 — Service scaffolding

**Status: done** (implemented directly by Tech Lead — pure scaffolding, no design/logic decisions to delegate, same precedent as NFE-001/VS-001/GW-001/DASH-001).

## Analysis
Story: ECON-001 (Must), `docs/product/backlog-economic-service.md`, depends on nothing. This is the **disclosed trigger-#11 override** (implementation-plan.md section 6) authorized by the user for Sprint 13 — see `docs/sprints/sprint-13.md`'s "ethical-boundary distinction" section. Constraining docs: implementation-plan.md section 3 (repo layout: `src/app/` with `routers/`, `dependencies/`, `repositories/`), section 9 (uv, tests-before-API, no service imports another service's code), CLAUDE.md's positioning rules (no profitability/trading-signal language). Nothing built in this ticket may be, or imply, a real capability — this is inert scaffolding, matching every other module's own scaffolding-first ticket.

## Design
No design pattern applies (pure scaffolding, matching NFE-001/VS-001/GW-001/DASH-001's own Design sections). Files touched (all new, `services/economic-service/` only): `pyproject.toml`, `src/app/{__init__,main}.py`, `src/app/routers/__init__.py`, `src/app/dependencies/__init__.py`, `src/app/repositories/__init__.py`, `tests/{__init__,test_package_imports}.py`, `README.md`. DRY check: n/a, first files in the module.

`naive_first_common` (`libs/common`) is declared as a `uv` path/workspace dependency from commit one — unlike VS-001 (which deliberately deferred it because `libs/common` didn't exist yet), `libs/common` is already implemented and shipping `TenantContext`/`get_tenant_context`/`build_engine`, which ECON-002/ECON-004 are expected to reuse rather than reimplement (DRY, implementation-plan.md section 9). This is a lib dependency, not a service-to-service import, so it does not violate "no service imports another service's code."

No `Dockerfile`/`infra/` wiring — out of scope per sprint-13.md's Definition of Done ("this sprint touches only `services/economic-service`").

## Implementation acceptance criteria
- [x] `services/economic-service/pyproject.toml` (uv-managed) declares FastAPI + test deps; no import of another service's code.
- [x] `src/app/` skeleton: `routers/`, `dependencies/`, `repositories/`, mirroring `validation-service`'s/`gateway-api`'s established layout.
- [x] `GET /health` exists as a hardcoded-`ok` placeholder (real DB check deferred to ECON-002, must land in the same PR that adds the DB dependency).
- [x] `tests/` with a working pytest config; a non-empty, real (not vacuous) test collected.
- [x] `README.md` status line updated from "deferred" to "scaffolded (trigger #11 not fired — see backlog override note)" — the deferred framing is not deleted, it's updated to reflect real state, and the full ethical-override context (two verified upstream facts, ECON-004's hard mock-only rule) is stated up front for every future contributor.

## Test acceptance criteria
- [x] `.venv\Scripts\python.exe -m pytest -q` passes. Two smoke tests added (`test_app_constructs`, `test_health_endpoint_returns_ok`) instead of a literal zero-test baseline, same rationale as NFE-001/VS-001 (pytest exit code 5 on zero-collected would falsify "passing baseline").

## Review acceptance criteria
- Tech Lead verified: file tree matches implementation-plan.md section 3; `pyproject.toml` has no dependency on any other service's code, only `naive_first_common` (a lib) and standard web/DB deps pre-declared for ECON-002 onward; `.venv\Scripts\python.exe -m pytest -q` exits 0 with 2 passed (ran directly — see Outcome below).

## Documentation acceptance criteria
- [x] `README.md` status line updated to "scaffolded" with the full override disclosure (two verified upstream facts, hard mock-only rule for future tickets) stated up front, not deferred to ECON-006.

## Environment note (applies to every ticket in this sprint)
This repo directory sits inside a OneDrive-synced folder, causing intermittent file-write/`uv sync`/`.venv`-creation failures unrelated to code. Workaround used and confirmed working: `.venv` created via `python -m venv .venv`, dependencies installed via `.venv\Scripts\python.exe -m pip install -e . -e ../../libs/common pytest httpx`, tests run via `.venv\Scripts\python.exe -m pytest -q`. For direct file writes that fail with an `ENOENT` temp-file error: write to the scratchpad first, then `cp` into the repo path (Bash `cp` does not hit the same failure as the Write tool's atomic-tmp-file mechanism) — used throughout this ticket. `mkdir`/`touch` via the `bash` builtins also intermittently fail inside this tree; `cmd //c "mkdir ..."` / `cmd //c "type nul > ..."` reliably worked instead. Every dev agent in this sprint should be told this pattern up front rather than discover it by trial and error.

**Verified**: `.venv\Scripts\python.exe -m pytest -q` in `services/economic-service` → `2 passed, 1 warning in 0.73s` (the one warning is FastAPI's own `httpx`-via-`starlette.testclient` deprecation notice, unrelated to this ticket's code).
