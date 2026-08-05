# gateway-api

**Status: planned (trigger #5 — create when a second external party needs access, i.e. the first pilot client, per the multi-tenant-from-day-one decision).**

The only internet-facing service. See [../../docs/solution-design.md](../../docs/solution-design.md) section 3.6 and [../../docs/implementation-plan.md](../../docs/implementation-plan.md) sections 2, 4.

**Owns**: the `identity` Postgres schema (tenants, users, api_keys), JWT/API-key auth, tenant-context resolution, request routing to internal services over HTTP.

**Does not own**: any business logic — this service orchestrates calls to `ingestion-service`, `validation-service`, `reporting-service`; it does not duplicate their logic (DRY across service boundaries means routing here, not reimplementation).

**Design notes**:
- Tenant context is resolved once per request and injected via FastAPI `Depends()` into every downstream call — this is the Dependency Injection point referenced in implementation-plan.md section 7.
- No direct DB access to other services' schemas, ever — only their HTTP APIs.

**Contract**: this is the OpenAPI schema external clients (`dashboard-web`, `libs/sdk`, pilot clients) build against. Breaking changes here are breaking changes to the whole product surface — version deliberately.
