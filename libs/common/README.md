# naive_first_common

**Status: built out (LC-001–004, Sprint 04; ARCH-001/002/003/004, Sprint 06). Tenant context (`TenantContext` + `get_tenant_context`), a shared SQLAlchemy engine-building helper (`db.build_engine`), shared wire-contract Pydantic models (`contracts`), and a shared pytest test-fixture module (`testing`) are all implemented and consumed by both `validation-service` and `gateway-api` — see docs/sprints/sprint-04.md, docs/sprints/sprint-06.md, and docs/tickets/README.md.**

Shared library for cross-cutting concerns used by more than one service. See [../../docs/implementation-plan.md](../../docs/implementation-plan.md) sections 2, 7, 9.

**Owns**: tenant context (dependency-injected via FastAPI `Depends()` in every service), shared Pydantic schemas passed across service boundaries (`naive_first_common.contracts`: `RunRequest`/`RunResponse`/`RunDetailResponse`/`SplitResultResponse`, the run/split wire contract shared by `gateway-api` and `validation-service`, ARCH-003), DB session helpers, `naive_first_common.testing` (test-utility fixtures shared across services, e.g. the `sqlite_db_path` pytest fixture, imported via each service's `tests/conftest.py`), common formatting logic (e.g. metrics-table rendering shared by `dashboard-web` and `reporting-service`).

**Does not own**: any service-specific business logic. If logic is only used by one service, it stays in that service — don't pre-emptively move things here "in case" another service needs them later (YAGNI; move on second real use, per the DRY convention in the implementation plan).

**Contract**: plain typed Python, Pydantic + SQLAlchemy. Every service depends on this; this depends on nothing internal.
