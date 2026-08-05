# naive_first_common

**Status: planned (trigger #2 — create the moment a second module needs to share a data shape, expected alongside `services/validation-service`).**

Shared library for cross-cutting concerns used by more than one service. See [../../docs/implementation-plan.md](../../docs/implementation-plan.md) sections 2, 7, 9.

**Owns**: tenant context (dependency-injected via FastAPI `Depends()` in every service), shared Pydantic schemas passed across service boundaries, DB session helpers, common formatting logic (e.g. metrics-table rendering shared by `dashboard-web` and `reporting-service`).

**Does not own**: any service-specific business logic. If logic is only used by one service, it stays in that service — don't pre-emptively move things here "in case" another service needs them later (YAGNI; move on second real use, per the DRY convention in the implementation plan).

**Contract**: plain typed Python, no framework lock-in beyond Pydantic. Every service depends on this; this depends on nothing internal.
