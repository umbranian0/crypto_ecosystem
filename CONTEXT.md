# Domain Glossary

## Operability

The umbrella concern covering both keeping the system easy to change safely (code/ops health — dependency upgrades, doc-sync checks, test-coverage gaps) and keeping it observable at runtime (logs, metrics, health checks, alerting). Introduced 2026-08-09 when scoping Sprint 08: "maintainability" and "monitoring" were initially raised as separate asks but resolved to one umbrella term, tracked as one backlog rather than two, since the user did not want them split into separate concerns.

Not yet split into sub-terms — if a future session needs to distinguish the code-health half from the runtime-observability half, resolve that split explicitly rather than assuming the boundary.

## Dataset

A tenant's ongoing, continuously-growing table for one ingestion source (e.g. "tenant X's Binance BTC/USDT price data"). Introduced 2026-08-25 when scoping the ingestion-to-TimescaleDB migration: previously a dataset was an ambiguous file/inline-JSON blob passed to `POST /runs`; resolved because ingestion connectors moving from CSV files to per-tenant DB tables made "dataset" mean something concrete for the first time. Picking a dataset for a validation run means selecting {tenant, source} and a time-range slice *at submission time* — there is no fixed pre-cut snapshot to select from. Contrast with a **crawl run**: one execution of a connector that appends rows to a dataset — a crawl run is an event, a dataset is the table it appends to.

## Seed data

Historical/bootstrap rows loaded into a tenant's dataset from a source other than that tenant's own live crawler (e.g. the pre-2026 CSV archives migrated into TimescaleDB). Seeding must be a repeatable operation parameterized by tenant — not a one-time script hardcoded to a single fixed tenant — so that seeding a newly-created tenant with historical data is an ordinary, scalable operation rather than a special case.
