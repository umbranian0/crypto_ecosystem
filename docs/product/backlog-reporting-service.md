# Backlog — reporting-service

Source: `docs/da-tese-ao-produto.md` (positioning constraints, sections 1.2/1.3/1.5/2.7), `docs/solution-design.md` (sections 1, 3.5, 4, 5, 6, 7 open questions), `docs/implementation-plan.md` (sections 2, 4, 5, 6 trigger #7, 7 — Factory pattern named explicitly for this service), `services/reporting-service/README.md`, `services/validation-service/README.md` (Contract/Routes, "Event publishing" section), `docs/tickets/VS-014.md` (Redis Streams `run.completed` wire format), `docs/tickets/VS-013.md`/`GW-012` (RLS pattern to replicate), `docs/product/backlog-infra.md` (INF-008 entry), `docs/tickets/README.md`, `libs/common/src/naive_first_common/contracts.py`, `.claude/skills/naive-first-audit/SKILL.md` (report structure to reproduce programmatically), `docs/product/backlog-dashboard-web.md` (override-note template and DASH-004's already-rendered data shape).

Scope: `services/reporting-service` only. In scope: service scaffolding, `reporting.*` Postgres schema + Repository pattern with RLS, one real report kind (validation audit) via a Factory, event-driven generation on `run.completed` plus a manual generate endpoint, HTML report storage in Postgres (not object storage), a retrieval endpoint. Out of scope: `dashboard-web` report-viewer UI, `gateway-api` proxy routes for this service's endpoints, MinIO/object storage, PDF export, automatic report distribution (email/webhook), any new report kind beyond "validation audit" (certification seal / continuous-monitoring digest are named as future Factory extension points only, not built).

## Explicit trigger override

Trigger #7 (`implementation-plan.md` section 6: "as soon as a validation run needs to produce a client-facing artifact instead of raw JSON — i.e. right after the first pilot audit is requested") has **not** fired — no pilot client exists (confirmed Sprint 11, `services/dashboard-web/README.md`'s own disclosure, unchanged as of this backlog). Built anyway at explicit user request, the same disclosed-override precedent already used in this repo for `services/gateway-api` (trigger #5), `services/ingestion-service`'s connectors (`INGEST-001`, trigger #6/#10), and `services/dashboard-web` (`docs/product/backlog-dashboard-web.md`, trigger #8). Unlike `services/economic-service` (a parallel backlog under construction), this override carries no comparable ethical constraint — it is purely a build-order-sequencing override, not a "never claim profitability before X" boundary, so this backlog is scoped as a full functional build, not scaffolding-only.

## Explicit scope/dependency decisions

1. Trigger override recorded above.
2. **Object storage (INF-008/MinIO) is confirmed still deferred** (`docs/product/backlog-infra.md` INF-008 is `[Should]`, not scheduled to any sprint, `docs/tickets/README.md`'s infra section lists it under "Deferred"). This PoC does **not** invent a MinIO dependency: `reporting.reports.content` stores the rendered report body directly in Postgres (a `text`/`bytea` column), not a storage-prefix reference. `implementation-plan.md` section 5's `reports/{tenant_id}/...` object-storage-prefix ownership stays a documented future contract, not built here — revisit only when INF-008 actually ships or report artifacts grow large enough that inline storage is impractical (a real, observable trigger, not preemptive).
3. **Report format for this PoC is HTML**, not PDF. Matches `dashboard-web`'s own DASH-004 rendering approach (Jinja2), keeps the dependency footprint to what's already proven in this repo, and avoids pulling in WeasyPrint/wkhtmltopdf (`solution-design.md` section 7's open question) before a client asks for a downloadable PDF specifically. A report row's `content` column holds the rendered HTML string.
4. **Repository backend is Postgres-only from the start**, not SQLite-then-Postgres like `validation-service`/`gateway-api`'s original build order. Those services started before `infra/docker-compose.yml` + Postgres existed (trigger #4 predates them); `reporting-service` is built after Postgres/RLS/the `naive_first_app` non-superuser role (INF-014) are already live and proven. Building directly against Postgres avoids a throwaway SQLite implementation with no real trigger to retire later. The Repository *interface* (Protocol) is still defined per implementation-plan.md section 7, so a lightweight test-only backend can be added later if test-suite speed becomes a real, observed problem — not mandated here.
5. **Service-to-service call path**: `reporting-service` calls `validation-service`'s existing `GET /runs/{id}` and `GET /runs/{id}/splits` directly by hostname inside the Docker network (`http://validation-service:8000/...`), the same pattern `implementation-plan.md` section 4 already establishes for `gateway-api` calling internal services — this is an internal service-to-service call, not an external client request, so it does not need to route through `gateway-api`. The `X-Tenant-Id` header value comes from the `run.completed` event payload (async path) or from the manual endpoint's caller-supplied tenant context (sync path) — reporting-service resolves its own tenant context via `naive_first_common.get_tenant_context` (`libs/common`, already shared) exactly as `validation-service` does, then forwards that same tenant id downstream.
6. **`gateway-api` does not yet proxy this service's endpoints.** Flagged as a gap for `gateway-api`'s own backlog (see RS-GAP below), mirroring `DASH-005-GAP`'s precedent — not invented or worked around here. `services/dashboard-web` calling this service is also out of scope (RS-101, Won't) for the same reason DASH-101 declined a report viewer.
7. **Report "kind" Factory** (`implementation-plan.md` section 7) ships with exactly one real kind, `"validation_audit"`. The interface (`get_report_renderer(kind) -> ReportRenderer`) is built to make adding a second kind (certification seal, continuous-monitoring digest) a new class, not a rewrite — but no second kind is built in this backlog (no concrete need yet, per the same YAGNI stance `implementation-plan.md` section 7 already states for CQRS/event sourcing).

## Stories

### RS-001 — Service scaffolding [Must]
**As** a Tech Lead standing up `reporting-service`, **I want** a `uv`-managed FastAPI service skeleton matching the shape of every other service in this repo, **so that** every other story has a place to live and a working test runner.

Acceptance criteria:
- [ ] `services/reporting-service/pyproject.toml` declares the FastAPI app + `httpx` (to call `validation-service`) + `redis` (to subscribe to `run.completed`, mirroring VS-014's dependency) + `jinja2` (report rendering) deps; no import of another service's code, only `libs/common` and `libs/naive_first_common`'s contracts.
- [ ] `src/app/{routers,dependencies,repositories}` skeleton, plus `src/app/templates/` for the Jinja2 report template and `src/app/renderers/` for the Factory (RS-003).
- [ ] `tests/` with a working pytest config; `uv run pytest` passes with 0 collected as a baseline.
- [ ] `Dockerfile` matching the non-root, port-binding pattern already established by `validation-service`/`gateway-api` (OPS-004's own verified precedent), even though this service isn't wired into `infra/docker-compose.yml` yet (RS-GAP notes this as a follow-up, not this story's job).
- [ ] `README.md` status moves planned -> scaffolded, with the trigger-#7 override note.

Rationale for priority: nothing else can be built without a skeleton; matches `owns: reporting.* schema + report rendering` boundary as the enabling first step.
Depends on: none

### RS-002 — `reporting` Postgres schema + Repository pattern with RLS [Must]
**As** `reporting-service`, **I want** a `reporting.reports` table (`id`, `tenant_id`, `run_id`, `report_kind`, `generated_at`, `content`, `status`) behind a `ReportRepository` interface, tenant-isolated the same way `validation.*`/`identity.*` already are, **so that** report artifacts are durable, versioned, and cannot leak across tenants — matching this platform's established multi-tenancy-from-day-one guarantee (`solution-design.md` section 1, principle 3).

Acceptance criteria:
- [ ] `src/app/repositories/interfaces.py` declares `ReportRepository` as a `typing.Protocol` (VS-003's precedent: first param after `self` is always `tenant_id`, returns a plain `@dataclass(frozen=True)` `ReportRecord`, no SQLAlchemy import in the interface file), with at minimum `create_report(tenant_id, run_id, report_kind, content, status) -> ReportRecord`, `get_report(tenant_id, report_id) -> ReportRecord | None`.
- [ ] `src/app/models.py` defines the `reports` table via SQLAlchemy 2.0 declarative (`id`, `tenant_id`, `run_id`, `report_kind`, `generated_at`, `content` (text), `status`), shared by the Alembic migration and the repository layer — no duplicate schema definitions.
- [ ] A Postgres-backed `PostgresReportRepository` implements the interface using `naive_first_common.db.build_engine` (ARCH-001) and the memoized-by-URL provider (ARCH-002) — no per-request `create_engine` call, mirroring VS-013/GW-012's exact seam.
- [ ] Alembic migration enables and **forces** row-level security on `reports` (`ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` + `CREATE POLICY tenant_isolation ON reports USING (tenant_id = current_setting('app.tenant_id'))`), matching VS-013's exact mechanism (not a weaker application-side filter).
- [ ] Every transaction the repository opens sets `app.tenant_id` first via `SELECT set_config('app.tenant_id', :tenant_id, true)` (VS-013's corrected, working syntax — not the invalid literal `SET LOCAL ... = :param` the original VS-013 ticket text specified), before any query.
- [ ] `migrations/env.py` targets the `reporting` schema specifically (`search_path` + `version_table_schema="reporting"`), conditional on `connection.dialect.name == "postgresql"` — required per INF-005's proven cross-service `alembic_version` collision, same as VS-013/GW-012.
- [ ] A test proves RLS actually blocks cross-tenant reads at the database level: a raw, unfiltered `SELECT tenant_id, id FROM reports` (no `WHERE tenant_id = ...` in the test) run as a dedicated non-superuser test role after scoping `app.tenant_id` to tenant A, asserting tenant B's row is absent — VS-013's exact non-vacuous-proof pattern (not run as a superuser/`BYPASSRLS` role, which would pass vacuously).
- [ ] Full test suite passes against real Postgres (skip-guarded if unreachable, same as `tests/test_postgres_repository.py`'s precedent).

Rationale for priority: Must — no report can be stored or retrieved without this; directly matches the module's stated `owns: reporting.* schema` boundary (implementation-plan.md section 2) and the RLS-as-hard-requirement precedent already set by VS-013/GW-012 for every other tenant-scoped table in this platform.
Depends on: RS-001

### RS-003 — Report Factory + "validation audit" report renderer [Must]
**As** `reporting-service`, **I want** a Factory (`get_report_renderer(kind)`) with one real implementation, `ValidationAuditRenderer`, that turns a `validation-service` run's status + per-split metrics + DM-test verdicts into a durable HTML report, **so that** `generate_report()` callers stay agnostic to which template renders (`implementation-plan.md` section 7's explicit justification for this pattern here) and a client gets the same honest, audit-grade report structure the `naive-first-audit` skill already defines.

Acceptance criteria:
- [ ] `src/app/renderers/base.py` defines a `ReportRenderer` interface (`render(run: RunDetailResponse, splits: list[SplitResultResponse]) -> str`, returning the rendered HTML), imported from `naive_first_common.contracts` for the `run`/`splits` shapes (`RunDetailResponse`, `SplitResultResponse`) — no local redefinition of those fields (DRY precedent already established for `gateway-api`/`dashboard-web` reusing ARCH-003's contracts).
- [ ] `src/app/renderers/factory.py`'s `get_report_renderer(kind: str) -> ReportRenderer` returns `ValidationAuditRenderer` for `kind == "validation_audit"` and raises a clear, typed error for any other kind — no silent fallback.
- [ ] `ValidationAuditRenderer` (Jinja2 template under `src/app/templates/`) renders, at minimum, the same fields `dashboard-web`'s DASH-004 already renders verbatim: run `id`/`status`/`dataset_id`/`horizon`/`purge_gap_hours`/`created_at`/`completed_at`/`failure_reason`, and per split: boundaries, model/naive0 metrics (`mae`/`rmse`/`smape`/`mase`/`da`/`f1`/`oos_r2`), and `dm_statistic`/`dm_pvalue`/`dm_verdict` **verbatim, with no recomputation or reinterpretation** — the DM verdict already reflects NFE-012's Harvey et al. (1997) long-run variance correction upstream in `naive_first_engine`; this renderer must not silently drop or reformat that correction's result. This is the acceptance criterion tying the story back to `da-tese-ao-produto.md` section 1.2/1.3's non-negotiable protocol.
- [ ] The rendered report explicitly states "did not beat naive" as a valid, expected outcome when `dm_verdict` says so — no conditional hiding, softening, or omission of a split/run where the model lost to Naive0 (`.claude/skills/naive-first-audit/SKILL.md`'s ground rule: "if the client's model does beat naive, report that plainly too — the goal is honest measurement in both directions").
- [ ] The rendered report includes the mandatory statistical-accuracy-vs-economic-value disclaimer text (skill's section 5) verbatim or near-verbatim — no implication of trading signal, profitability, or price prediction anywhere in the template (CLAUDE.md positioning, non-negotiable).
- [ ] A run with `status != "completed"` (e.g. `"failed"`, `"running"`) renders a report stating that plainly (no fabricated metrics table for a run with no splits) — mirrors DASH-004's "running-with-no-splits" handled case.
- [ ] Unit tests: a completed run with mixed better/worse DM verdicts renders correctly (metrics table + verdict text present, disclaimer present); a run that never beat naive on any split renders that outcome without alteration; a failed/no-split run renders a status-only report, not an error.

Rationale for priority: Must — this is the core "renders audit reports from `validation.*` results" contract the module exists to fulfill (implementation-plan.md section 2); the Factory is named explicitly in section 7 as earning its place here.
Depends on: RS-001

### RS-004 — Manual "generate report for run X" endpoint [Must]
**As** a future service or operator needing this PoC's own testability without waiting for the async event path, **I want** `POST /reports/generate` (accepting `run_id`, resolving tenant via `X-Tenant-Id`), **so that** a report can be produced synchronously and deterministically for testing/demo before RS-006's event subscriber is proven end-to-end.

Acceptance criteria:
- [ ] `POST /reports/generate` resolves tenant via `Depends(naive_first_common.get_tenant_context)` (same mechanism `validation-service`/`gateway-api` already use — no local reimplementation, per libs/common's own DRY precedent).
- [ ] Calls `validation-service`'s real `GET /runs/{run_id}` and `GET /runs/{run_id}/splits` directly by hostname (scope decision 5), forwarding the resolved `X-Tenant-Id` header — no fabricated/mocked data path in the production code.
- [ ] Uses RS-003's Factory with `kind="validation_audit"` to render the HTML, then RS-002's repository to persist a new `reports` row, returning `{"id": ..., "status": "generated"}` (`201`).
- [ ] A `run_id` that doesn't exist for the resolved tenant (validation-service's `404`, cross-tenant or nonexistent, both collapsed) is passed through as this endpoint's own `404` — no distinction shown, mirroring `validation-service`'s own non-disclosure stance for the same ambiguity.
- [ ] A `validation-service` timeout/connection failure returns a generic `502`/`504` — no leaked internals (matches DASH-004's "results currently unavailable" precedent, applied server-side here).
- [ ] Tests (mocked `validation-service` via `httpx` transport mocking): success generates and persists a report; 404 pass-through; 502/504 pass-through; a `"failed"`-status run still generates a status-only report (not rejected).

Rationale for priority: Must per the requester's explicit minimum-scope item #4 ("also expose a manual... endpoint for the PoC's own testability without needing to wait for the async event path").
Depends on: RS-002, RS-003

### RS-005 — `GET /reports/{id}` retrieval endpoint [Must]
**As** a future caller (e.g. `gateway-api`, once its own proxy route exists — RS-GAP), **I want** `GET /reports/{id}` returning a previously generated report's content and metadata, tenant-isolated, **so that** a generated report can actually be retrieved, not just produced and discarded.

Acceptance criteria:
- [ ] Resolves tenant via the same `Depends(naive_first_common.get_tenant_context)` seam as RS-004.
- [ ] On success (`200`): returns `id`, `run_id`, `report_kind`, `generated_at`, `status`, `content` (the rendered HTML).
- [ ] A report that doesn't exist, and a report that exists but belongs to a different tenant, both return the same `404` shape — no distinction shown (matches `GET /runs/{id}`'s established non-disclosure stance, VS-007).
- [ ] Tests: success; nonexistent id; cross-tenant id returns the same 404 as nonexistent (a real, non-tautological test — asserts the response body is identical for both cases, not merely that both are 404).

Rationale for priority: Must per the requester's explicit minimum-scope item #6 ("at minimum an API endpoint... tenant-isolated").
Depends on: RS-002

### RS-006 — Redis Streams subscriber for `run.completed` [Must]
**As** `reporting-service`, **I want** to subscribe to `validation-service`'s real `run.completed` Redis Streams event (VS-014's documented wire format) and automatically generate a `"validation_audit"` report on receipt, **so that** report generation happens without a manual trigger — the module's stated `triggered by run.completed` contract (`implementation-plan.md` section 2).

Acceptance criteria:
- [ ] Consumes `XADD run.completed run_id=... tenant_id=... status=... completed_at=...` (VS-014's exact documented flattened-field format, read from `services/validation-service/README.md`'s "Event publishing" section, not assumed/reinvented) via `XREAD`/consumer-group semantics against the same `REDIS_URL` env var convention (`DATABASE_URL`'s sibling, already established).
- [ ] On receiving an event, calls the same code path RS-004's endpoint uses (`run_id` + `tenant_id` from the event payload -> fetch from `validation-service` -> render via RS-003's Factory -> persist via RS-002's repository) — no duplicated generation logic between the manual and event-triggered paths (DRY within this module's own boundary, per implementation-plan.md section 9).
- [ ] A malformed or partially-missing event (e.g. missing `tenant_id` field) is logged and skipped, not crashed on — the subscriber loop must not die on one bad message.
- [ ] Only `status == "completed"` events trigger generation; a `run.completed` event is only ever published for a completed run per VS-012's structural guarantee, but this subscriber does not trust that blindly — it re-checks `status` on the fetched run detail before rendering, as defense in depth.
- [ ] Tests run against real Redis (`redis://localhost:6379/0`, skip-guarded if unreachable — VS-014's own precedent, not mocked for at least one integration-style test): publish a real `run.completed` event, assert a report row exists afterward with the right `run_id`/`tenant_id`.
- [ ] Not wired into `infra/docker-compose.yml` in this story (RS-GAP notes this) — the subscriber process/entrypoint exists and is documented as runnable standalone (`python -m app.subscriber` or equivalent), matching how this service isn't yet in Compose (scope decision, same category as `reporting-service`'s own not-yet-triggered `infra/README.md` note).

Rationale for priority: Must — this is the module's own stated trigger mechanism (`implementation-plan.md` section 2: "triggered by `run.completed`"); without it, "automatic report generation" (the whole point of a reporting service vs. a client re-requesting raw JSON) doesn't exist.
Depends on: RS-002, RS-003, RS-004 (shares its generation code path)

### RS-007 — Health check endpoint [Should]
**As** an operator, **I want** `GET /health` to check real connectivity to this service's own Postgres schema, matching OPS-005-01/02's precedent, **so that** this service's health reporting isn't a hardcoded `ok` like every other service already avoids.

Acceptance criteria:
- [ ] Real check via a memoized `Engine` (same `dependencies/repositories.py` seam as `validation-service`'s `get_health_check_engine`), running `SELECT 1` against the `reporting` schema.
- [ ] Success: `200 {"status": "ok"}`. Failure: `503 {"status": "unhealthy", "detail": "database unreachable"}` — fixed generic string, no raw exception/connection-string/credential leakage.
- [ ] Redis connectivity (RS-006's subscriber) is explicitly out of scope for this check, same stance `validation-service`'s own `/health` docs already take for its Redis producer side.

Rationale for priority: matches an established low-cost, repo-wide convention (OPS-005-01/02) — not part of the requester's stated minimum-scope items, so Should, not Must.
Depends on: RS-002

### RS-008 — OpenAPI contract / README doc-sync check [Should]
**As** a future contributor — human or Claude — **I want** a route-existence doc-sync check for `reporting-service`, matching VS-016/LC-005's precedent, **so that** this new service's README doesn't silently drift from its real routes the way `validation-service`'s did for seven sprints before VS-016 closed the gap.

Acceptance criteria:
- [ ] `scripts/check_doc_sync.py` (+ `tests/test_doc_sync.py`) introspects the live `app.routes` (VS-016's precedent, not NFE-018's AST-parsing — this is an already-running FastAPI service, same category as `validation-service`) and confirms every route in `README.md`'s Routes list exists, and vice versa.
- [ ] `README.md`'s Routes section lists path+method only (`GET /health`, `POST /reports/generate`, `GET /reports/{id}`) — exact request/response shapes stay in `/openapi.json`/`/docs`, same convention as every other service.

Rationale for priority: cheap, zero-risk, repo-wide convention already proven valuable (VS-016 closed a real 7-sprint drift gap) — worth building at service-creation time rather than deferring it the way `validation-service` did. Should, not Must, since it adds no user-facing capability.
Depends on: RS-004, RS-005 (routes must exist first)

### RS-009 — CI wiring [Should]
**As** a Tech Lead, **I want** `reporting-service`'s test suite added to `.github/workflows/ci.yml` (OPS-001's existing pipeline) and its README updated with a "Coverage"/"Dependency upgrades" pointer (OPS-002/OPS-003's existing convention), **so that** this new service doesn't sit outside the repo's already-established CI/coverage/dependency-cadence conventions from day one.

Acceptance criteria:
- [ ] `.github/workflows/ci.yml` runs `services/reporting-service`'s test suite alongside the existing five modules.
- [ ] `README.md` gets the same "Coverage" (`--cov=app --cov-report=term-missing`, no hard gate) and "Dependency upgrades" (link to `docs/dependency-upgrade-policy.md`) lines every other module's README already carries.

Rationale for priority: zero-cost, zero-risk, mirrors OPS-001/002/003's already-proven repo-wide pattern — Should, not Must, since the module functions without it, but cheap enough not to defer seven sprints the way LC-005/VS-016 were.
Depends on: RS-001 through RS-006 (test suite must exist)

### RS-101 — Won't: `dashboard-web` report viewer UI [Won't]
Not proposed here. Explicitly flagged by the requester as a separate, future `dashboard-web` backlog item — `dashboard-web`'s own backlog (`docs/product/backlog-dashboard-web.md`, DASH-101) already declined this for the same reason ("no report artifact to view" — now resolved by this backlog, but the viewer itself is still `dashboard-web`'s own story to author, not this module's).

### RS-102 — Won't: automatic report distribution (email/webhook) [Won't]
Not proposed. Out of scope for a PoC per the requester's explicit instruction. `GET /reports/{id}` (RS-005) is the only retrieval mechanism; no push/notification mechanism is built or implied.

### RS-103 — Won't: PDF export (WeasyPrint/wkhtmltopdf) [Won't]
Not proposed. Scope decision 3: HTML only for this PoC. Revisit only if a real client asks for a downloadable PDF specifically — `solution-design.md` section 7 already flags this as an open question, not a settled requirement.

### RS-104 — Won't: real object storage (MinIO, INF-008) [Won't, this backlog]
Not proposed. Scope decision 2: INF-008 is confirmed still `[Should]`/unscheduled in `docs/product/backlog-infra.md`. `reporting.reports.content` stores HTML inline in Postgres. Revisit when INF-008 actually ships or inline storage becomes impractical at real report volume — a concrete future trigger, not invented here.

### RS-105 — Won't: second report kind (certification seal / continuous-monitoring digest) [Won't, this backlog]
Not proposed. Scope decision 7: the Factory interface is built to support a second kind cheaply, but no second kind exists yet (`solution-design.md` section 6, phase 7/8 — continuous monitoring hasn't been built, so there is nothing yet for a "digest" report to summarize). Matches this repo's own YAGNI stance (implementation-plan.md section 7's "deliberately not using yet" list).

### RS-106 — Won't: `gateway-api` proxy routes for this service [Won't, this backlog]
Not proposed here — see RS-GAP below. This module owns no other service's routing.

## RS-GAP — Flagged capability gap (not a reporting-service story)

`gateway-api` currently proxies only `validation-service`'s routes (`POST /runs`, `GET /runs/{id}`, `GET /runs/{id}/splits}`, per GW-008). It has no proxy route for `reporting-service`'s `POST /reports/generate` or `GET /reports/{id}` (RS-004/RS-005), and `reporting-service` is not yet wired into `infra/docker-compose.yml` (mirrors `infra/README.md`'s own existing statement that `reporting-service` "is still not wired into compose," per INF-007's acceptance criteria). Both gaps are real and load-bearing for an actual end-to-end pilot flow (a client currently cannot reach this service's endpoints through the platform's one public-facing surface, `gateway-api`, at all) but belong as new tickets in `docs/product/backlog-gateway-api.md` (new `GW-0NN`, matching GW-008's routing pattern) and `docs/product/backlog-infra.md` (new `INF-0NN`, matching INF-003/INF-004's service-wiring pattern) respectively — not authored here, since this module owns neither `gateway-api`'s routing table nor `infra/`'s compose file. This mirrors `dashboard-web`'s own `DASH-005-GAP` precedent exactly: a disclosed gap, not a silent workaround.
