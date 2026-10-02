# reporting-service

**Status: implemented -- Sprint 12 complete, all 9 in-scope stories done (RS-001 through RS-009):**
**scaffolding, `reporting.reports` Postgres schema/Repository with real RLS, Factory/**
**`ValidationAuditRenderer`, `POST /reports/generate`, `GET /reports/{id}` retrieval, a Redis**
**Streams `run.completed` subscriber reusing the same generation code path, `GET /health`, a**
**route-existence doc-sync check, and CI wiring, plus a pooled-connection-reuse RLS regression test**
**(`test_set_local_scope_does_not_leak_across_pooled_connection_reuse`, mirroring gateway-api's own**
**test of the same name -- proves `set_config('app.tenant_id', ..., true)` reverts at transaction**
**end and does not leak across a recycled pooled connection, the exact bug class VS-021 found and**
**fixed once already in validation-service). Full test suite: 37 passed, 0 failed**
**(independently re-confirmed against real Postgres, not taken on any single dev agent's report**
**alone).** Built ahead of
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
genuine proof rather than a vacuous pass. A second regression test,
`test_set_local_scope_does_not_leak_across_pooled_connection_reuse` (mirroring gateway-api's test of
the same name exactly), proves the same `set_config(..., true)` scoping is genuinely per-transaction
-- not a value that survives a connection's return to (and reuse from) a connection pool -- via a
dedicated ephemeral `NOSUPERUSER NOBYPASSRLS` test role (`restricted_role_engine`,
`pool_size=1, max_overflow=0` to force physical-connection reuse) and `pg_backend_pid()`/
`current_setting('app.tenant_id', true)` checks; this is the exact bug class VS-021 found and fixed
once already in validation-service's `create_run`.

**Does not own**: computing metrics or DM results — those come from `validation-service` via its
API; this service only renders and stores what it's given. Also does not own object storage this
sprint — `reporting.reports.content` stores the rendered HTML inline in Postgres (a `text` column),
not a `reports/{tenant_id}/...` object-storage-prefix reference; that remains a documented future
contract (implementation-plan.md section 5), revisited only once `INF-008` (MinIO, still deferred)
ships or inline storage becomes impractical at real report volume (backlog decision 2). PDF export
(RPT-001-02) is a conversion of the stored HTML `content` at retrieval time -- nothing is cached or stored. The PDF stylesheet avoids splitting a table row across pages (CHORE-66-03).

**Design notes**:
- Subscribes to the `run.completed` event (Redis Streams) — Observer pattern, implementation-plan.md section 7 — rather than being polled or called synchronously by `validation-service`.
- Report "kind" (audit report today; certification seal / continuous-monitoring digest later, docs section 2.6 phase 5) is selected via a Factory (`get_report_renderer(kind)`, `src/app/renderers/factory.py`, RS-003) so new report types don't require touching existing renderer code. `"validation_audit"` (`ValidationAuditRenderer`, `src/app/renderers/validation_audit.py`) is the only real kind shipped this backlog — matches backlog decision 7 / RS-105 (certification seal) Won't. Any other `kind` raises `UnknownReportKindError`, no silent fallback. Renderers implement the `ReportRenderer` interface (`src/app/renderers/base.py`, `render(run: RunDetailResponse, splits: list[SplitResultResponse]) -> str`), importing those wire models from `naive_first_common.contracts` (ARCH-003) rather than redefining the field list. `ValidationAuditRenderer` renders via Jinja2 (`src/app/templates/validation_audit.html.jinja`), reproducing the `naive-first-audit` skill's report structure (Scope / Methodology / leakage-protocol parameter values / reproducibility statement / Results table / Verdict / mandatory statistical-accuracy-vs-economic-value disclaimer / Recommendations); it passes every `model_*`/`naive0_*`/`dm_*` field through unmodified (no recomputation/reinterpretation) and renders a status-only report (no fabricated metrics table) for any run with `status != "completed"`.
- **TRUST-001-02**: the report includes an always-visible "2. Methodology" section, inserted directly
  after section 1 ("Scope") and **before** the `status != "completed"` gate — unlike every other
  results-dependent section, it renders for a non-`"completed"`/zero-split run exactly as for a
  completed one. `ValidationAuditRenderer` passes `METHODOLOGY_FACTS: tuple[str, str, str, str]`,
  imported from `naive_first_common.disclosures` (`libs/common`), into the template context; the
  template renders the four facts verbatim in a `<ul>` (rolling-origin walk-forward, the purge gap,
  the mandatory Naive0/NaiveLast baseline comparison, and the Diebold-Mariano test with the Harvey et
  al. (1997) long-run variance correction). The previously-existing gated "2. Leakage-protocol
  parameters" section (this run's own parameter *values*, still completed-only) is renamed to
  **"2.1 This run's leakage-protocol parameter values"** — a sub-number under the new section 2;
  sections 2.5 (later renumbered to 2.2, see the TRUST-005/Sprint 57 note below)/3/4/5/6/7 kept their
  existing numbers unchanged at the time. `METHODOLOGY_FACTS`'s wording lives in
  `libs/common` (`naive_first_common/disclosures.py`), shared with `dashboard-web`'s run-detail panel
  so the audit report and the UI cannot tell a tenant two different things about the validation
  protocol — CLAUDE.md's DRY rule pulls cross-module duplication into a `libs/*` package rather than
  copy-pasting it across service boundaries (the no-cross-service-import rule is about one *service*
  importing another's code, which this is not). The canonical exact-text assertion lives once in
  `libs/common/tests/test_disclosures.py`; `tests/test_renderers.py::test_methodology_facts_comes_from_the_shared_library`
  asserts only *identity* with that shared constant. Originally (TRUST-001-02) this text was copy-pasted
  here with a hand-mirrored same-text test; that guard could not actually detect drift, since each
  service's test compared its own copy against another literal in its own test file.
- **TRUST-004**: the report includes a "2.5. Reproducibility statement" subsection, positioned between section 2 ("Leakage-protocol parameters") and section 3 ("Results table (per split)"), inside the same `status == "completed"` `else` branch (so it's omitted for a non-completed run same as every other results-dependent section). It renders verbatim, template-only, no recomputation: `RunDetailResponse.engine_version`, `.config_fingerprint`, and `.dataset_id` (reused, not a second independently-sourced field), plus a fixed sentence stating that re-running the same configuration/dataset/engine version is expected to reproduce these results (a methodology/audit claim, not a prediction/trading claim). For a run predating `TRUST-003`'s engine-fingerprint tracking (`engine_version`/`config_fingerprint` both `None`, the field default), it renders an explicit "Engine version / config fingerprint not available for runs created before this platform tracked engine fingerprints" note instead — never a fabricated fingerprint, never a bare `"None"` string. `ValidationAuditRenderer`/`generation.py` required zero Python change (`RunDetailResponse` already passes through to the template context unmodified, RS-003's existing pattern).
- **Sprint 57 renumbering**: TRUST-004's "2.5. Reproducibility statement" heading is now **"2.2
  Reproducibility statement"** — a cheap, non-cascading rename (Tech Lead review item, `sprint-57.md`):
  "2.5" read as a decimal offset sibling of "2.1" without actually being one, and no test or other
  document referenced the literal string "2.5", so renumbering it to sit immediately after "2.1" was a
  one-line template edit with no cascade into sections 3/4/5/6/7 (their numbers are unchanged).
- **TRUST-005**: section 4 ("Verdict")'s "Overall" paragraph, inside the existing `{% if better_count ==
  0 %}` branch, now renders one additional sentence after the existing, unchanged "the model did not
  beat naive on any split evaluated in this run." text:
  `naive_first_common.disclosures.NOT_BEATING_NAIVE_IS_EXPECTED_SENTENCE` (the same shared constant
  `dashboard-web`'s `build_headline_verdict_summary` appends under the equivalent condition,
  `has_client_model=True` and `better_count == 0`). `ValidationAuditRenderer.render` passes it into the
  template context as `not_beating_naive_note`. Never rendered in the `better_count > 0` branches (either
  "beat naive on every split" or "mixed"). Same shared-constant/identity-check drift-guard mechanism as
  `METHODOLOGY_FACTS` above (`tests/test_renderers.py::test_not_beating_naive_sentence_matches_shared_wording`).
  `TRUST-005-01`'s and this ticket's (`TRUST-005-02`) own tickets, as originally written, specified a
  per-service copy plus a per-service same-text test for this sentence — corrected before implementation
  to reuse the shared constant from the start (see both tickets' own "Superseded in part" notes).
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

## AI-assisted features (AI-002)

**Status: implemented (AI-002), documented here per AI-005.** `app.narrative.client` (`NarrativeClient`/
`NarrativeClientError`/`HostedApiNarrativeClient`/`get_narrative_client`) now lives in `libs/ai_assist`
(`naive_first_ai_assist.client`) as of AI-003-REFACTOR — this module re-exports those names unchanged,
it does not reimplement them.

**What it does**: an optional, AI-generated plain-language narrative paragraph summarizing a
*completed* run's own persisted metrics and DM verdict. It is generated only from RS-006's `run.
completed` Redis Streams subscriber (`src/app/subscriber.py`) — **never** from `POST /reports/
generate`'s synchronous route, which has no latency budget for a model round-trip and remains
byte-identical to its pre-AI-002 behavior for every caller. `generate_validation_audit_report`
(`src/app/generation.py`) exposes this as an optional `narrative_client: NarrativeClient | None =
None` keyword parameter (default `None`, backward compatible); only the subscriber constructs and
passes a real client (via `get_narrative_client()`).

**What it explicitly does not do**:
- No new data source. `app/narrative/prompt_template.py`'s `build_prompt(run, splits)` is fed only
  the same already-persisted `split_results`/run aggregate metrics the results table already
  renders — no live call to any prediction API, no raw tenant upload content.
- Never overrides or reinterprets the table or DM verdict. The existing table/verdict/disclaimer
  markup is unchanged; the narrative is additive and rendered in a separately labeled block.
- Never ships an unchecked claim. `app/narrative/fact_check.py`'s `contains_banned_term` (rejects
  "signal"/"buy"/"sell"/"profit"/"trade"/directive "recommendation" language) and
  `is_directionally_consistent` (rejects a "beat naive" claim the real DM verdicts don't support)
  both gate every candidate paragraph in `app/narrative/generation.py::generate_narrative_html`
  before it ever reaches the renderer; a rejected paragraph is regenerated once, then dropped
  (`None`) rather than shipped.
- Degrades to today's table-only report on any failure: an unconfigured deployment
  (`get_narrative_client()` returns `None` when `NARRATIVE_API_URL`/`NARRATIVE_API_KEY` aren't
  set), a model call error/timeout (`NarrativeClientError`), or a fact-check rejection all collapse
  to `narrative_html=None` — no exception escapes to the subscriber loop or the caller.

**Where it runs**: a hosted, OpenAI-compatible chat-completions HTTPS endpoint (ADR-0011,
`docs/adr/0011-ai-assist-model-serving.md`) — no local model (no Ollama/llama.cpp), no new
`infra/docker-compose.yml` container/service.

**Design**: `NarrativeClient` (`src/app/narrative/client.py`) is a one-method Adapter/Strategy
Protocol (`generate(prompt: str) -> str`). `HostedApiNarrativeClient` is the only implementation
that touches `httpx`/the network; every test in this service exercises a fake implementation
(`FakeNarrativeClient`) instead — no live network access or credentials required to run the suite.
`app/narrative/prompt_template.py` is a versioned, checked-in template module
(`PROMPT_TEMPLATE_VERSION`), not a runtime-built string.

**Tests**: banned-term and directional-consistency (fact-grounding) cases live in
`services/reporting-service/tests/narrative/test_fact_check.py`. Client behavior (mocked transport,
no live network call) is in `tests/narrative/test_client.py`; prompt construction in
`tests/narrative/test_prompt_template.py`; the fact-check-gate/regenerate/fallback orchestration
(including the banned-term-over-rendered-HTML case and the graceful-degradation-on-client-error
case) in `tests/narrative/test_generation.py` and `tests/narrative/test_generation_integration.py`.
`tests/test_generate_endpoint.py::test_generate_report_never_includes_ai_narrative_block` proves
`POST /reports/generate` never emits a narrative.

**Env vars**: `NARRATIVE_API_URL`, `NARRATIVE_API_KEY`, `NARRATIVE_API_TIMEOUT_SECONDS` (default
`10`) — see [`../../infra/README.md`](../../infra/README.md)'s "reporting-service narrative
generation (AI-002)" section for the disclosure/operational details (all unset by default in
every environment today, so no deployment currently calls the hosted endpoint).

## Routes

The route list below (path + method) is machine-checked against the live FastAPI app by
[`scripts/check_doc_sync.py`](scripts/check_doc_sync.py) (also runnable as `tests/test_doc_sync.py`;
RS-008) -- **re-run it (`.venv\Scripts\python.exe scripts/check_doc_sync.py` from this directory)
after adding, removing, or renaming any route.** This list only tracks route *existence* (path +
method), not request/response shape -- see this running service's `/openapi.json`/`/docs` for that.

- `GET /health`
- `POST /reports/generate`
- `GET /reports/{report_id}`
  - optional `?format=pdf` (RPT-001-02) returns `application/pdf` with `Content-Disposition: attachment; filename="audit-report-<id>.pdf"`; any other `format` value is `422`; default is the JSON body
- `GET /reports/{report_id}/diff/{other_id}`

**Report diff (RPT-004-01)**: a field-level diff of the per-split values of two `validation_audit` reports of the caller's tenant (`src/app/diff.py` pure function, `src/app/routers/report_diff.py`). Reports store rendered HTML only, so this is a **run-data diff keyed by two reports**: each report's stored `run_id` is re-fetched from validation-service (`X-Tenant-Id`, same fetch helpers as generation) and nothing is recomputed (DM values are the existing Harvey-adjusted ones, verbatim). Unknown id or another tenant's id: the same `404 {"detail": "report not found"}` as `GET /reports/{id}`; a run that no longer exists: `404 "run not found"`; downstream failures map to `502`/`504` as in generate.

- **Comparability rule** (checked in this order; failure is `422` with one plain reason as `detail`): (1) both reports are `validation_audit` ("both reports must be of kind 'validation_audit'"); (2) same `dataset_id` ("runs use different datasets"); (3) same `horizon` ("runs use different horizons"); (4) same `purge_gap_hours` and equal `split_config` ("runs use different split configurations"); (5) neither run has more than 500 splits ("too many splits to diff"); (6) identical `split_index` sets ("runs have different split sets") and identical `test_start`/`test_end` per split ("runs have different test windows for the same split"). A report diffed with itself is allowed (all deltas 0).
- **Output**: `report_id`, `other_report_id`, `run_id`, `other_run_id`, `dataset_id`, `horizon`, `split_count`, `verdict_changed_split_count`, and `splits` ordered by `split_index`, each `{split_index, metrics: {<field>: {base, other, delta}}, dm_verdict: {base, other, changed}}`. Fields are the seven `model_*` metrics, the seven `naive0_*` metrics, `dm_statistic`, `dm_pvalue`. `delta = other - base`, `null` when either side is `null` (undefined DM split). `dm_verdict.changed` compares the category via `naive_first_common.consistency.verdict_category`, so an undefined split is not conflated with "no significant difference". The only summary is `verdict_changed_split_count`, the number of splits whose Naive0 comparison verdict category differs.
- **Positioning**: deltas are neutral arithmetic differences, never ranked, scored, or labelled; a smaller or larger error between two runs is not an economic or predictive claim. A test greps the new source and response for outcome language.
- **AC3 not built**: the dashboard "compare with a previous report" action depends on a report viewer that does not exist (deferred in sprint 65, API-only slice).

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

**PDF export (RPT-001-02)**: `src/app/renderers/pdf.py`'s `render_pdf(html) -> bytes` converts the stored HTML with WeasyPrint (imported lazily; needs Pango/fonts, installed in this service's Dockerfile per RPT-001-01) using a `url_fetcher` that refuses every URL. A status-only stored report yields a status-only PDF. Tests that need the native libs are marked `@pytest.mark.pdf_render` and auto-skip on hosts without them; run them inside the built image (copy `src`/`tests` into a throwaway container, tests are not baked into the image).

**Report kinds and `POST /reports/generate` request fields (RPT-002-02)**: `kind` is `"validation_audit"` (default) or `"consistency_trend"`. `validation_audit` requires `run_id` and rejects `dataset_id`/`horizon` (a request with only `run_id` behaves exactly as before). `consistency_trend` requires `dataset_id` and `horizon` (an integer >= 1; 0 or negative is `422`) and rejects `run_id`; any other combination is `422`. The Factory (`get_report_renderer`) returns a `ReportRenderer` for the first kind and a `TrendReportRenderer` (`renderers/base.py`, `render(dataset_id, horizon, runs_with_splits)`) for the second (`ConsistencyTrendRenderer`, `templates/consistency_trend.html.jinja`). A `consistency_trend` report is an archivable point-in-time snapshot of "beat Naive0 in N of M completed runs" for one (dataset_id, horizon) group -- a descriptive count of already-computed Diebold-Mariano verdicts, never a prediction, signal, or economic claim; it carries the same statistical-accuracy-vs-economic-value disclaimer as the audit report (shared partial `templates/_accuracy_vs_economic_disclaimer.html.jinja`) and renders "No completed runs matched this selection." instead of "0 of 0" when nothing is evaluable. The majority rule is `naive_first_common.consistency` (shared with dashboard-web); this service has no copy of it. "Same contract" interpretation: it reads validation-service's `GET /runs` (paged at 100), `GET /runs/{id}/splits/count` and `GET /runs/{id}/splits?limit&offset` directly with `X-Tenant-Id` (the contract gateway-api proxies), filters to the dataset/horizon/`completed`, and bounds splits per run to the most recent `MAX_RENDERED_SPLITS` (500, `generation.py`, must equal dashboard-web's constant so counts match `/runs/trend`). **Scope storage**: `reports.run_id` is NOT NULL and a trend has no run, so the scope is stored there by convention as `consistency_trend:{dataset_id}:{horizon}` (no migration). **PDF (`?format=pdf`) is not built or verified for this kind.** The route list is unchanged, so the doc-sync list needed no edit (`tests/test_doc_sync.py` re-run, passing).

**CI**: `.github/workflows/ci.yml` runs this module's test suite on every push/PR.

**Coverage**: run tests with coverage locally via `uv run pytest -q --cov=app --cov-report=term-missing` (no coverage threshold is enforced — CI prints the report, it never fails the build on a percentage).

**Dependency upgrades**: see [../../docs/dependency-upgrade-policy.md](../../docs/dependency-upgrade-policy.md) for this platform's cadence.

**Test database**: Postgres-backed tests target the isolated `naive_first_test` DB, never the live `naive_first`; override with `REPORTING_SERVICE_TEST_DATABASE_URL`.
