# infra

**Status: planned (trigger #4 — create `docker-compose.yml` + Postgres the same moment `validation-service` is scaffolded; it needs somewhere to persist run/split results).**

Will hold: `docker-compose.yml` (services: gateway-api, ingestion-service, validation-service, reporting-service, dashboard-web, postgres+timescaledb, minio, redis — see [../docs/solution-design.md](../docs/solution-design.md) section 5), and per-service Alembic migration environments under `migrations/` (one per Postgres schema — `ingestion`, `validation`, `reporting`, `identity`, later `economic` — see [../docs/implementation-plan.md](../docs/implementation-plan.md) section 5).

Nothing here yet — don't add a compose file with services that don't exist as code.
