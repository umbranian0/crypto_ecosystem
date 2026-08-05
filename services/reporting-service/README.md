# reporting-service

**Status: planned (trigger #7 — create when a validation run needs to produce a client-facing artifact instead of raw JSON, i.e. right after the first pilot audit is requested).**

Formerly `audit-reports/`. See [../../docs/da-tese-ao-produto.md](../../docs/da-tese-ao-produto.md) section 2.3.4, [../../docs/solution-design.md](../../docs/solution-design.md) section 3.5, and the [`naive-first-audit` skill](../../.claude/skills/naive-first-audit/SKILL.md) for the report content/structure this service must reproduce programmatically.

**Owns**: the `reporting` Postgres schema (`reports`), the report object-storage zone (`reports/{tenant_id}/...`), report rendering (Jinja2 → HTML/PDF).

**Does not own**: computing metrics or DM results — those come from `validation-service` via its API; this service only renders and stores what it's given.

**Design notes**:
- Subscribes to the `run.completed` event (Redis Streams) — Observer pattern, implementation-plan.md section 7 — rather than being polled or called synchronously by `validation-service`.
- Report "kind" (audit report today; certification seal / continuous-monitoring digest later, docs section 2.6 phase 5) is selected via a Factory (`get_report_renderer(kind)`) so new report types don't require touching existing renderer code.
- The leakage checklist and statistical-vs-economic disclaimer in every report are populated programmatically from `validation-service` run metadata where possible, never hand-typed — reduces drift between what the engine actually did and what the report claims it did.

**Contract**: FastAPI service (internal, triggered by events) plus `GET /reports/{id}` for retrieval via `gateway-api`.
