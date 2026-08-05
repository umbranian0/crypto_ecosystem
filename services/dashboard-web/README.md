# dashboard-web

**Status: planned (trigger #8 — create when a pilot client needs to see results without you manually sending them a file, i.e. second pilot client or first "where do I log in" question).**

Formerly `dashboard/`. See [../../docs/solution-design.md](../../docs/solution-design.md) section 3.6.

**Owns**: server-rendered UI only (FastAPI + Jinja2 + HTMX) — login, dataset/run list, run detail, report viewer, degradation-alerts view.

**Does not own**: any data access — every page is rendered from calls to `gateway-api`'s public contract, same as an external client would use. This is deliberate: it keeps the UI honest to the same API contract external SDK users get, and means the UI can never drift into reading internal service schemas directly.

**Design notes**: metrics-table rendering shared with `reporting-service`'s HTML report templates belongs in `libs/common`, not duplicated between the two (DRY across the module boundary via a shared lib, per implementation-plan.md section 9).

**Contract**: consumes `gateway-api`'s OpenAPI schema; no contract of its own beyond its rendered HTML routes.
