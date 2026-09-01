# INGEST-007 — `ingestion-service` FastAPI app scaffolding

**Sprint**: 18. **Module**: `services/ingestion-service`, `infra`. **Status**: done. **Priority**: Must.
**Depends on**: `INGEST-002` (schema, for a real `/health` DB check). **Blocks**: `INGEST-008`, `INGEST-009`.
**Can run in parallel with**: `INGEST-003` (disjoint files: `src/app/main.py`+`Dockerfile` vs.
`connectors/`+`src/app/repositories/`).

## Analysis
Story: backlog `INGEST-007`. This is a fresh, disclosed override of trigger #6 (implementation-plan.md
section 6) — no pilot client has requested an upload API; this exists to unblock `INGEST-009`/`VS-023`/
`DASH-108` per the backlog's own trigger-override disclosure. That disclosure must land in this
service's README status line as part of this ticket, not left implicit.

## Design
Files touched: `services/ingestion-service/src/app/main.py`, `src/app/dependencies/` (repository DI —
`get_health_check_engine`/`HealthCheckEngineDep`, mirroring `validation-service`'s shape; no tenant-context
wiring added since no route in this ticket consumes it yet — see Review note below), `Dockerfile`,
`pyproject.toml` (merged with `INGEST-002`'s/`INGEST-011`'s existing four dependencies — none dropped),
`infra/docker-compose.yml` (new `ingestion-service` entry), `infra/.env.example` (new `INGESTION_SERVICE_*`/
`INGESTION_CREDENTIAL_ENCRYPTION_KEY` entries, and a small factual correction to the existing GW-021
section, which pre-dated this ticket and said the service "not yet built"). **DRY check**: reuse
`naive_first_common.db.build_engine`/`naive_first_common.configure_structured_logging`/
`CorrelationIdMiddleware` (no new logging/DB-engine mechanism), reuse `reporting-service`'s `Dockerfile`
as the direct template (uv-managed, non-root, `additional_contexts: libs`).

## Implementation acceptance criteria
- [x] `src/app/main.py`: FastAPI app, `naive_first_common.configure_structured_logging()` +
  `CorrelationIdMiddleware` wired at import time (same as `validation-service`/`gateway-api`), `GET
  /health` checking real DB connectivity (`OPS-005` pattern: `SELECT 1` via the engine, `200`/`503`).
- [x] `Dockerfile` mirrors `reporting-service`'s exactly (uv sync --frozen --no-dev, non-root `appuser`,
  `libs` additional build context).
- [x] `infra/docker-compose.yml` gains an `ingestion-service` entry: `127.0.0.1`-only host port binding
  (same convention as every internal-only service), `DATABASE_URL` using `naive_first_app` (never the
  migration-only `naive_first` role). Port is **8003**, not 8004 — see Review note below: `GW-021`
  (landed before this ticket) already committed to 8003 as `ingestion-service`'s own port via
  `gateway-api`'s `dependencies/http_client.py` default and `infra/.env.example`'s existing
  `INGESTION_SERVICE_URL` entry. Using 8004 as originally suggested would have silently broken that
  already-built proxy route's default.
- [x] Existing `connectors/`/`tests/`/`requirements.txt` untouched in place (service wrapper added
  alongside, not replacing, the standalone-script layer).

## Test acceptance criteria
- [x] `tests/test_health.py`: healthy/unhealthy-DB cases plus a `CorrelationIdMiddleware` check,
  non-tautological (asserts real status code + body shape). 3/3 pass; full suite (29 tests) passes.
- [x] `docker compose build ingestion-service` succeeds (verified locally — Docker was available in
  this environment). `docker compose up ingestion-service` was also verified live against the real
  Postgres container (`GET /health` → `200 {"status": "ok"}`), on an alternate host port since a
  pre-existing, unrelated stray process on this dev machine already occupies 127.0.0.1:8003 outside
  Docker — not introduced by this ticket, left alone per the standing hygiene-incident instructions.

## Review acceptance criteria (Tech Lead verifies personally)
- Personally runs `docker compose up ingestion-service` against the real stack, confirms `GET /health`
  returns `200`. **Dev-agent note**: this dev agent already did this once (see Test acceptance criteria
  above) but flags that host port 8003 was occupied by an unrelated stray process during this session —
  the Tech Lead should confirm 8003 is free before relying on the default `docker compose up` binding.
- Confirms `pyproject.toml` correctly merges `INGEST-002`'s/`INGEST-011`'s dependency additions
  (`sqlalchemy`, `alembic`, `psycopg`, `cryptography`) plus this ticket's own (`fastapi`, `uvicorn`,
  `httpx`) — no dependency silently dropped from either prior ticket. **Note**: this ticket also added
  `naive_first_common` as a dependency (not listed in the ticket's own bullet list) since `main.py`
  cannot wire `configure_structured_logging`/`CorrelationIdMiddleware`/`build_engine` without it — this
  was necessary to satisfy the ticket's own explicit `main.py` requirement, not scope creep.

## Documentation acceptance criteria
- [x] `services/ingestion-service/README.md`'s status line states plainly: this is the disclosed
  override of trigger #6 (no pilot client has requested an upload API; built to unblock
  `INGEST-009`/`VS-023`/`DASH-108`).
