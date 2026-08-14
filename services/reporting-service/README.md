# reporting-service

**Status: implemented -- Sprint 12 complete, all 9 in-scope stories done (RS-001 through RS-009):**
**scaffolding, `reporting.reports` Postgres schema/Repository with real RLS, Factory/**
**`ValidationAuditRenderer`, `POST /reports/generate`, `GET /reports/{id}` retrieval, a Redis**
**Streams `run.completed` subscriber reusing the same generation code path, `GET /health`, a**
**route-existence doc-sync check, and CI wiring. Full test suite: 36 passed, 0 failed, 88% coverage**
**(independently re-confirmed by the Tech Lead against real Postgres and Redis, not taken on any**
**single dev agent's report alone).** Built ahead of
trigger #7 (implementation-plan.md section 6: "as soon as a validation run needs to produce a
client-facing artifact instead of raw JSON -- i.e. right after the first pilot audit is requested")
-- no pilot client/audit request exists yet. Built anyway at explicit user request, the same
disclosed-override precedent already used in this repo for `services/gateway-api` (trigger #5) and
`services/dashboard-web` (trigger #8) -- see `docs/product/backlog-reporting-service.md`'s "Explicit
trigger override" section. Do not read anything in this README as "a pilot client exists."

**This service is not yet reachable through `gateway-api`** (no proxy route exists yet for
`POST /reports/generate`/`GET /reports/{id}`) and **not yet wired into `infra/docker-compose.yml`**
-- both are a disclosed capability gap (RS-GAP, `docs/product/backlog-reporting-service.md`), tracked
as follow-up tickets against `gateway-api`'s and `infra`'s own backlogs, not invented or worked
around here. RS-006's Redis Streams subscriber (below) is a third standalone-only piece of this same
gap: it exists and is fully tested, but is not started by `infra/docker-compose.yml` this ticket.

Formerly `audit-reports/`. See [../../docs/da-tese-ao-produto.md](../../docs/da-tese-ao-produto.md) section 2.3.4, [../../docs/solution-design.md](../../docs/solution-design.md) section 3.5, and the [`naive-first-audit` skill](../../.claude/skills/naive-first-audit/SKILL.md) for the report content/structure this service must reproduce programmatically.

**Owns**: the `reporting` Postgres schema (`reports`), report rendering (Jinja2 -> HTML).

**Storage backend (RS-002)**: Postgres-only from the start, no SQLite fallback (backlog decision 4
-- deliberate, since this service is built after Postgres/RLS/the `naive_first_app` non-superuser
role (INF-014) already exist, unlike `validation-service`/`gateway-api`'s original SQLite-then-
Postgres build order). `src/app/repositories/interfaces.py` declares `ReportRepository` as a
`typing.Protocol` (`create_report`/`get_report`, tenant_id-first per method, zero `sqlalchemy`
import); `src/app/repositories/postgres_repository.py`'s `PostgresReportRepository` implements it
via `psycopg` v3 (synchronous), `naive_first_common.db.build_engine` (ARCH-001) + the
memoized-by-URL provider (ARCH-002) -- no per-request `create_engine`. Tenant isolation is enforced
by real Postgres row-level security, not an application-side filter:
`migrations/versions/0002_add_row_level_security.py` enables and *forces* RLS on `reports` with a
`tenant_isolation` policy keyed on `current_setting('app.tenant_id')`; every transaction the
repository opens sets that GUC first (`SELECT set_config('app.tenant_id', :tenant_id, true)`, `SET
LOCAL`'s parameter-bindable equivalent) -- see `postgres_repository.py`'s module docstring for the
full mechanism, mirroring `validation-service`'s VS-013 and `gateway-api`'s GW-012 exactly.
`migrations/env.py` targets the `reporting` schema specifically for both table creation and
`alembic_version` tracking (`version_table_schema="reporting"`), per INF-005's proven cross-service
collision. The RLS cross-tenant proof (`tests/test_postgres_repository.py::
test_rls_blocks_cross_tenant_reads_at_the_database_level`) runs as the real, already-provisioned
non-superuser `naive_first_app` role (INF-014), not a superuser/`BYPASSRLS` connection, so it is a
genuine proof rather than a vacuous pass.

**Does not own**: computing metrics or DM results — those come from `validation-service` via its
API; this service only renders and stores what it's given. Also does not own object storage this
sprint — `reporting.reports.content` stores the rendered HTML inline in Postgres (a `text` column),
not a `reports/{tenant_id}/...` object-storage-prefix reference; that remains a documented future
contract (implementation-plan.md section 5), revisited only once `INF-008` (MinIO, still deferred)
ships or inline storage becomes impractical at real report volume (backlog decision 2). PDF export is
also out of scope this sprint (HTML only, backlog decision 3).

**Design notes**:
- Subscribes to the `run.completed` event (Redis Streams) — Observer pattern, implementation-plan.md section 7 — rather than being polled or called synchronously by `validation-service`.
- Report "kind" (audit report today; certification seal / continuous-monitoring digest later, docs section 2.6 phase 5) is selected via a Factory (`get_report_renderer(kind)`, `src/app/renderers/factory.py`, RS-003) so new report types don't require touching existing renderer code. `"validation_audit"` (`ValidationAuditRenderer`, `src/app/renderers/validation_audit.py`) is the only real kind shipped this backlog — matches backlog decision 7 / RS-105 (certification seal) Won't. Any other `kind` raises `UnknownReportKindError`, no silent fallback. Renderers implement the `ReportRenderer` interface (`src/app/renderers/base.py`, `render(run: RunDetailResponse, splits: list[SplitResultResponse]) -> str`), importing those wire models from `naive_first_common.contracts` (ARCH-003) rather than redefining the field list. `ValidationAuditRenderer` renders via Jinja2 (`src/app/templates/validation_audit.html.jinja`), reproducing the `naive-first-audit` skill's report structure (Scope / leakage-protocol parameters / Results table / Verdict / mandatory statistical-accuracy-vs-economic-value disclaimer / Recommendations); it passes every `model_*`/`naive0_*`/`dm_*` field through unmodified (no recomputation/reinterpretation) and renders a status-only report (no fabricated metrics table) for any run with `status != "completed"`.
- The leakage checklist and statistical-vs-economic disclaimer in every report are populated programmatically from `validation-service` run metadata where possible, never hand-typed — reduces drift between what the engine actually did and what the report claims it did.
- Data access goes through a Repository layer (`ReportRepository`) — implementation-plan.md section 7 — same pattern as every other tenant-scoped service in this platform.
- **Service-to-service call path**: calls `validation-service`'s real `GET /runs/{id}`/`GET /runs/{id}/splits` directly by hostname inside the Docker network (same internal-call pattern `gateway-api` already uses), never through `gateway-api` — this is an internal call, not an external client request.
- `GET /reports/{id}` (RS-005) lives in its own router module, `src/app/routers/report_retrieval.py`, deliberately disjoint from RS-004's `src/app/routers/report_generation.py` so both tickets could be built in parallel with zero file overlap (mirrors `validation-service`'s VS-007/VS-008 `runs.py`/`splits.py` split); both mount under the same `/reports` prefix in `src/app/main.py`.
- **RS-004**: `POST /reports/generate`'s fetch-render-persist sequence (call `validation-service`'s
  `GET /runs/{id}`+`GET /runs/{id}/splits` -> render via the Factory with `kind="validation_audit"`
  -> persist via `ReportRepository.create_report`) lives in one named, reusable function,
  `generate_validation_audit_report` (`src/app/generation.py`), not inlined in the router handler.
  `src/app/routers/report_generation.py`'s handler is a thin adapter: resolve tenant, call that
  function, translate its typed exceptions (`RunNotFoundError`/`DownstreamUnavailableError`/
  `DownstreamTimeoutError`/`DownstreamResponseError`) into `404`/`502`/`504`. RS-006's Redis Streams
  subscriber imports and calls this exact same function -- no duplicated fetch/render/persist logic
  anywhere in this service.
- **RS-006**: `src/app/subscriber.py` is a standalone-runnable Redis Streams consumer (Observer
  pattern), not a FastAPI router -- no HTTP request is in scope when it runs. It subscribes to the
  `run.completed` stream (VS-014's exact wire format: stream key is the event name, flattened string
  fields `run_id`/`tenant_id`/`status`/`completed_at`) via `XREADGROUP` consumer-group semantics
  (group `reporting-service`, a fresh group only sees entries added after its own creation, `id="$"`,
  so it never replays an unrelated backlog e.g. from `validation-service`'s own producer-side tests).
  For each entry: a malformed/partially-missing event (e.g. missing `tenant_id`) is logged (naming the
  missing field) and skipped -- the loop keeps running; an event whose payload `status != "completed"`
  is skipped outright; an event claiming `status == "completed"` triggers one extra
  `GET /runs/{id}` re-check (defense in depth, does **not** trust the event payload's own `status`
  field) before calling `generate_validation_audit_report` (RS-004's exact function, same import) with
  the event's `run_id`/`tenant_id` -- if the freshly fetched run's real status isn't `"completed"`, no
  report is generated. `generate_validation_audit_report`'s typed `GenerationError` subclasses are
  caught and logged per event, never crashing the loop.
  Runs standalone: `cd services/reporting-service && uv run python -m app.subscriber` (or
  `.venv\Scripts\python.exe -m app.subscriber` on Windows without `uv run`), reading `REDIS_URL` (same
  env var name/convention VS-014 already established for validation-service's producer side, default
  `redis://localhost:6379/0`) plus the same `DATABASE_URL`/`VALIDATION_SERVICE_URL` env vars
  `POST /reports/generate` already uses (it reuses `get_validation_service_client`/
  `get_report_repository`, the same DI providers). **Not wired into `infra/docker-compose.yml` this
  ticket (RS-GAP)** -- no container/service entry runs it automatically; it must be started by hand
  (or by a future infra ticket) alongside the FastAPI app.

## Routes

The route list below (path + method) is machine-checked against the live FastAPI app by
[`scripts/check_doc_sync.py`](scripts/check_doc_sync.py) (also runnable as `tests/test_doc_sync.py`;
RS-008) -- **re-run it (`.venv\Scripts\python.exe scripts/check_doc_sync.py` from this directory)
after adding, removing, or renaming any route.** This list only tracks route *existence* (path +
method), not request/response shape -- see this running service's `/openapi.json`/`/docs` for that.

- `GET /health`
- `POST /reports/generate`
- `GET /reports/{report_id}`

**Contract**: FastAPI service. `POST /reports/generate` (RS-004 — done) resolves tenant via
`Depends(naive_first_common.get_tenant_context)`, calls `validation-service`'s real
`GET /runs/{id}`/`GET /runs/{id}/splits` by hostname (`VALIDATION_SERVICE_URL` env var, mirrors
`gateway-api`'s own naming), renders + persists a `"validation_audit"` report, and returns
`{"id": ..., "status": "generated"}` (`201`). A `run_id` that does not exist for the resolved tenant
(nonexistent or cross-tenant, both collapsed by `validation-service` itself) passes through as this
endpoint's own `404`; a downstream timeout/connection failure returns a generic `502`/`504` with no
leaked hostname/exception text; a `"failed"`-status run still generates a status-only report.
`GET /reports/{id}` (retrieval, RS-005 — done) resolves tenant via
`Depends(naive_first_common.get_tenant_context)` and returns the fetched report's `id`, `run_id`,
`report_kind`, `generated_at`, `status`, `content`; a report that does not exist and a report that
exists but belongs to a different tenant both return the same `404`, since
`ReportRepository.get_report` (RS-002) already collapses both cases to `None` before the handler ever
sees them. Automatic generation on `run.completed` (RS-006 — done): `python -m app.subscriber`
(standalone process, not yet Compose-wired, see Design notes above) consumes the `run.completed`
Redis Streams event and calls the same generation function `POST /reports/generate` calls, after its
own defense-in-depth status re-check. `GET /health` (RS-007 — done)
runs a real `SELECT 1` against this service's own `reporting` Postgres schema through a memoized
`Engine` (`get_health_check_engine`, `src/app/dependencies/repositories.py`, same seam
validation-service's OPS-005-01 established): `200 {"status": "ok"}` on success, `503
{"status": "unhealthy", "detail": "database unreachable"}` on any connection/execution failure, with
a fixed generic detail string only — never the raw exception, connection string, or credential. Redis
connectivity (RS-006's subscriber) is explicitly out of scope for this check. See
`docs/tickets/RS-*.md` for live ticket status.

**CI**: `.github/workflows/ci.yml` runs this module's test suite on every push/PR.

**Coverage**: run tests with coverage locally via `uv run pytest -q --cov=app --cov-report=term-missing` (no coverage threshold is enforced — CI prints the report, it never fails the build on a percentage).

**Dependency upgrades**: see [../../docs/dependency-upgrade-policy.md](../../docs/dependency-upgrade-policy.md) for this platform's cadence.
