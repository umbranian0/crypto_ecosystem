# Sprint 58 — Epic C (Admin/Ops Maturity), slice 1: operator audit trail + crawl failure detail (ADMIN-002, ADMIN-003)

Sprint goal: the platform gains a persisted, queryable record of its own privileged operator actions
(tenant creation, API-key revocation) and surfaces the actual reason a crawl failed instead of the bare
word "failed" — closing two concrete, narrowly-scoped "we audit rigorously but don't audit ourselves /
don't explain our own failures" gaps `sprint-57`'s roadmap note flagged as this epic's starting slice.

Backlog source: `docs/product/backlog-trust-and-admin-ops.md` — `ADMIN-002` (Should) and `ADMIN-003`
(Should), both independently schedulable per the backlog's own sequencing note ("everything else in this
backlog is independently schedulable"). This file re-verifies `sprint-57`'s tentative "Next" sketch
against current code rather than carrying it over on trust, per that sketch's own stated caveat, and per
this platform's standing convention that a follow-up sprint's citations get their own independent PM pass.

## Verification of the backlog's cited findings (done independently, not taken on trust)

- **No persisted operator audit trail exists today, confirmed three ways.** `services/gateway-api/src/app/
  models.py` (grepped for `__tablename__`) defines exactly three tables — `tenants`, `users`, `api_keys`
  (lines 39, 48, 59) — no `audit_log`/`operator_audit_log` table anywhere. `services/gateway-api/migrations/
  versions/` holds `0001_create_identity_schema.py` through `0005_add_tenants_rls_read_fallback.py`; the
  next unused migration number is `0006`. Grepping the whole service for `audit_log`/`operator_audit_log`
  turns up only `services/gateway-api/README.md` (prose describing today's structured-logging convention)
  and one docstring reference in `tests/test_operator_auth.py:220` to the *log-line* test file
  `test_audit_logging.py` — neither is a persisted table. `services/gateway-api/README.md` (read around
  lines 64–69, the GW-014 auth-event-logging section) states plainly: "this stays a 'structured local log
  line' — no log retention/shipping/aggregation to any external system is added by this ticket... this is
  not a compliance-grade retained audit trail until a real auditor/compliance conversation defines
  retention requirements." This confirms `ADMIN-002`'s AC exactly: today's `OPS-006` logging (which does
  emit `api_key_issued`/`api_key_revoked`/`auth_failed` events, per that same README section) is
  deliberately, explicitly *not* the durable/queryable trail the story asks for.
- Both endpoints `ADMIN-002`'s AC names exist exactly as described, both already operator-gated. `POST
  /tenants` is `create_tenant` (`services/gateway-api/src/app/routers/tenants.py:119`, `Depends
  (get_authenticated_operator)` at line 124). `POST /tenants/{tenant_id}/api-keys/{key_id}/revoke` is
  `revoke_api_key` (same file, line 136, same operator dependency at line 141). Both are the two "existing
  operator-authenticated mutating endpoint[s]" the AC requires wiring — no third endpoint needs to be
  invented or found.
- The `validation-service` `failure_reason` shape the AC points to as the precedent to mirror is real, not
  an assumed analogy: `grep` across `services/validation-service` for `failure_reason` hits
  `src/app/models.py`, both repository implementations (`postgres_repository.py`, `sqlite_repository.py`),
  `repositories/interfaces.py`, and a dedicated `tests/test_failure_reason_readability.py` — a full,
  already-shipped "add a nullable reason/detail column, populate it at the existing failure call site,
  test it renders readably" pattern this sprint's two stories both reuse the shape of (not the code).
- **`ADMIN-003`'s core gap, confirmed at the exact line the backlog cites.** `services/ingestion-service/
  src/app/models.py:125` — `CrawlRun.status: Mapped[str]` is a bare, unconstrained string column with no
  companion `failure_detail`/reason column anywhere in the model (read the full `CrawlRun` class, lines
  113–134). The failure write site is `connectors/base.py:175` —
  `repository.record_crawl_run(tenant_id, connector.name, since, result.fetched_at, 0, "failed")` — inside
  the `except Exception:` block opened at line 174, and the caught exception (`raise`d unchanged
  immediately after, line 176, per that function's own documented "doesn't alter `run_incremental`'s
  existing exception-propagation behavior") is never captured into the recorded row — only the literal
  string `"failed"` is persisted. This is the exact, narrow gap `ADMIN-003`'s AC describes.
- **Correction to the backlog's own citation, confirmed by reading the actual router files**: `GET
  /connectors/{source}/status` is not in `routers/connectors.py` — that file holds only `POST
  /connectors/{source}/run`, `POST /connectors/{source}/cancel`, and the differently-scoped `GET
  /connectors/credentials-status` (connector credential state, not crawl outcomes). The real route is
  `connector_status` in `services/ingestion-service/src/app/routers/datasets.py:136–152`, returning a
  `ConnectorStatusResponse` built from fields `status`/`timestamp`/`row_count`/`rows_fetched_so_far`/
  `updated_at` (lines 146–151) — no `failure_detail` field exists on that response today. The ticket needs
  to target `datasets.py`, not `connectors.py`.
- `services/ingestion-service/migrations/versions/` holds `0001` through `0008` (`0008_add_crawl_runs_
  progress_columns.py` is the highest-numbered file present, confirmed via directory listing); the next
  unused migration number is `0009`. `0008` is itself the right precedent to cite for "additive nullable
  column on `crawl_runs`," since it already added `rows_fetched_so_far`/`updated_at` the same way this
  story adds `failure_detail`.
- **`dashboard-web`'s crawl-status panel, read in full**:
  `services/dashboard-web/src/app/templates/_crawl_status_panel.html` is the single `DASH-115`-extracted
  partial, shared between `monitoring.html`'s initial render and the polling `GET
  /monitoring/crawl-status-fragment` fragment (per its own header comment, lines 1–7). Its table columns
  are Source / Last crawl status / Last crawl timestamp / Row count / Progress / Trigger (lines 48–53);
  each row's `<td>` for status (line 60) renders `entry.status` bare, with no adjacent failure-detail cell
  or conditional today. A `failure_detail` addition, gated on `entry.status == "failed"`, is a bounded
  extension of the existing status `<td>` — no new page, no new partial, matching the AC's "extends the
  existing panel" requirement.
- The dict-shaped `entry` values the template consumes are assembled in `services/dashboard-web/src/app/
  routers/operator.py`'s `_fetch_crawl_statuses` (lines 366–409): each `entry` is built by spreading the
  downstream `GET /ingestion/connectors/{source}/status` JSON response (`{"source": source,
  **status_response.json()}`, line 403), then `progress_display` is added post-fetch via `_format_progress`
  in the same loop (lines 406–407) — confirmed as the exact precedent `ADMIN-003`'s AC should follow: once
  `ingestion-service`'s response includes `failure_detail`, it arrives on `entry` for free via the same
  spread, with no new fetch call needed; only the template's status cell needs the new conditional.
- **File-overlap check, done by reading both target areas in full rather than assuming from module names**:
  `ADMIN-002` touches `services/gateway-api` (`models.py`, a new migration `0006`, `tenants.py`) plus a new
  `dashboard-web` Settings-area page. `ADMIN-003` touches `services/ingestion-service` (`models.py`, a new
  migration `0009`, `connectors/base.py`, `datasets.py`) plus the existing `dashboard-web`
  `_crawl_status_panel.html`/`operator.py`. Zero files are touched by both stories. Confirmed no other
  in-flight or immediately-next sprint references any of these six files.

## Sequencing call: ADMIN-002 and ADMIN-003 both in scope, no forced order between them; ADMIN-001 and ADMIN-005 deferred

Independently evaluated against the backlog text and the verification above, not a rubber-stamp of the
prior sprint's tentative sketch:

- **ADMIN-002 and ADMIN-003 have zero file overlap and zero data/mechanism dependency on each other** — one
  is entirely within `gateway-api` + a new `dashboard-web` Settings page; the other is entirely within
  `ingestion-service` + the existing `dashboard-web` crawl-status panel/`operator.py`. Unlike `sprint-57`'s
  `TRUST-001 → TRUST-005` real mechanism-reuse dependency, nothing here requires one story's shared
  constant/mechanism to exist before the other starts. Order between the two in this sprint is therefore a
  scheduling convenience, not a dependency — each story's own internal ticket order (migration → endpoint/
  write-site → UI) is the only real sequencing that matters, and that's an internal-to-each-story concern
  for the Tech Lead's ticket breakdown, not a cross-story sprint-level constraint.
- **Both are Should-priority, both bounded (backlog's own words: "bounded scope, one table wired into two
  already-existing endpoints" for `ADMIN-002`; "narrowly-scoped visibility gap with an existing
  column-precedent to follow" for `ADMIN-003`), and both closely mirror an already-shipped precedent**
  (`validation-service`'s `failure_reason` shape for `ADMIN-003`; `OPS-006`'s existing structured-logging
  call sites, now given a durable table, for `ADMIN-002`) — consistent with how prior sprints (56, 57)
  bundled multiple related, individually-small Should stories rather than splitting them across sprints.
- **ADMIN-001 (health-transition webhook) is excluded, independently re-evaluated, not just carried from
  the sketch.** Read in full: it is a differently-shaped story from the other four `ADMIN-*` entries — it
  adds a new outbound-HTTP-side-effect mechanism (`MONITORING_WEBHOOK_URL`, a POST fired from
  `gateway-api`'s own health-check path) rather than extending an existing persisted-record/existing-panel
  pattern the way `ADMIN-002`/`003` do. It also carries its own explicit scope-discipline risk (the AC's
  own "so it cannot silently reopen `OPS-007`'s declined scope" line) that deserves a dedicated ticket pass
  rather than being folded in alongside two structurally different stories in the same sprint. Nothing in
  the verification above changes this call — deferred to a follow-up sprint, not dropped.
- **ADMIN-005 (self-serve API key rotation) is excluded, independently re-evaluated.** Its own backlog
  rationale states this directly: "the lockout-guard design needs real care, so it doesn't rank above the
  epic's other, lower-risk stories." Its AC also requires a real design decision this PM pass should not
  preempt — enforcing "mint-then-confirm-then-revoke" as the only reachable path, plus a new tenant-facing
  "My API Keys" page — meaningfully more design/review surface than `ADMIN-002`/`003`'s narrow,
  precedent-following additions. Confirmed this reasoning still holds: nothing in current code changes the
  lockout-guard risk the backlog itself already flagged. Deferred, not dropped.
- **Net call: ADMIN-002 + ADMIN-003 only, this sprint, no forced order between them.** Both stories are
  listed below in ID order for the ticket breakdown's convenience, not because either blocks the other.

## Stories in scope (no forced execution order between them — listed in ID order)

1. **ADMIN-002** — Operator action audit log.
   - Modules touched: `services/gateway-api` (`identity.operator_audit_log` new table, `src/app/models.py`,
     new migration `0006` — confirmed as the next unused number — and the two existing endpoints,
     `tenants.py:119` `create_tenant` and `tenants.py:136` `revoke_api_key`, each gaining a write-on-success
     row) plus a new read-only `services/dashboard-web` Settings-area page consuming a new
     `GET /operator-audit-log`.
   - No dependency on `ADMIN-003` — independently dispatchable.
   - Constraints to carry into the ticket: write-on-success only, no row for a rejected/`403` attempt (that
     remains covered by `OPS-006`'s existing structured logs, per the AC's own explicit scope line); never
     persist the raw or hashed operator token (there is only one shared token today — logging it, even
     hashed, adds no value and is a needless secret-adjacent surface, per the AC); `correlation_id` on each
     row should join back to `OPS-006`'s existing structured logs for full request context, reusing that
     existing id rather than minting a second one; `GET /operator-audit-log` uses the same `limit`/`offset`
     pagination convention `GET /runs`/`GET /tenants` already use, and stays behind the existing operator
     session gate (`SETUP-012`'s pattern), not a new auth mechanism.
   - Per implementation-plan.md section 2's module boundary rule: `dashboard-web`'s new Settings page reads
     this data only through `gateway-api`'s new HTTP endpoint, never by querying the `identity` schema
     directly.

2. **ADMIN-003** — Surface why a crawl failed, not just that it failed.
   - Modules touched: `services/ingestion-service` (`crawl_runs.failure_detail` nullable column, new
     migration `0009` — confirmed as the next unused number, following `0008`'s additive-column precedent —
     `src/app/models.py:125`'s `CrawlRun`, and the failure write site at `connectors/base.py:175` inside the
     `except Exception:` block opened at line 174, capturing the caught exception's message before the
     existing `raise` at line 176) plus `src/app/routers/datasets.py:136`'s `connector_status` response
     (correction from the backlog's own citation: this lives in `datasets.py`, not `connectors.py`) and the
     existing `services/dashboard-web` crawl-status panel (`_crawl_status_panel.html`'s status `<td>`,
     line 60, plus `operator.py`'s `_fetch_crawl_statuses`, lines 366–409, which needs no fetch-shape change
     since `failure_detail` arrives via the existing response-spread at line 403 once `ingestion-service`
     emits it).
   - No dependency on `ADMIN-002` — independently dispatchable.
   - Constraints to carry into the ticket: no raw credential, connection string, or stack trace ever lands
     in `failure_detail` — the Tech Lead defines the exact allowed message shape per connector at ticket
     time, following the discipline `GET /health`'s generic "database unreachable" convention models,
     adapted to be more specific since this is operator/tenant-facing troubleshooting context rather than a
     public unauthenticated endpoint (per the AC); `failure_detail` is `null` for any non-`"failed"` status,
     never a placeholder string; the panel change is additive only — no new page, no change to the existing
     Trigger/Progress column behavior.

## Module/dependency note for the Tech Lead (implementation-plan.md sections 2 and 6)

Both stories touch only already-built, already-live modules — no trigger-firing question here:
`services/gateway-api` (trigger #5) and `services/ingestion-service` (trigger #6) both fired long ago, and
`services/dashboard-web` (trigger #8) is likewise already live. Neither story proposes a new service or a
new `libs/*` package, and neither touches `libs/sdk` (trigger #9), a new ingestion connector (trigger #10),
or `services/economic-service` (trigger #11) — none of those triggers have fired, consistent with the
backlog's own explicit out-of-scope statement. Per implementation-plan.md section 2's module boundary rule:
`dashboard-web` reaches both new/extended data (`ADMIN-002`'s audit log, `ADMIN-003`'s `failure_detail`)
only through each owning service's HTTP API, never by querying `gateway-api`'s `identity` schema or
`ingestion-service`'s `ingestion` schema directly.

## Stories explicitly deferred

- **ADMIN-001** (health-state-transition webhook) — deferred, not dropped. Differently-shaped from this
  sprint's two stories (new outbound-side-effect mechanism vs. extending an existing persisted-record/
  existing-panel pattern) and carries its own scope-discipline risk (explicitly not reopening `OPS-007`'s
  declined full alerting stack) that warrants its own dedicated ticket pass rather than being folded in
  alongside two structurally different stories. See "Next" below.
- **ADMIN-005** (self-serve API key rotation) — deferred, not dropped, per the backlog's own stated
  rationale: real lockout-guard design risk ("does not rank above the epic's other, lower-risk stories")
  plus a new tenant-facing page, meaningfully heavier than this sprint's two precedent-following additions.
  See "Next" below.
- **ADMIN-004** (tenant-facing usage/quota view) — already `Won't` in the backlog itself (no quota/plan/
  rate-limit mechanism exists anywhere in the platform to display usage against); not reconsidered here,
  consistent with the backlog's own reasoning.
- Everything else in `backlog-trust-and-admin-ops.md` not in scope this sprint: all of Epic B
  (`RPT-001/002/004`, `RPT-003` already done Sprint 55), all of Epic D (`ONB-001/002`, `ONB-003` already
  `Won't`) — deferred per the backlog's own overall sequencing lean (Epic A/C ahead of Epic B/D), not
  dropped. Epic A (`TRUST-001` through `TRUST-005`) is fully shipped as of Sprint 57.

## File-overlap / concurrent-work risk

- **Zero shared files between `ADMIN-002` and `ADMIN-003`**, confirmed by reading both target areas in full
  during verification above (not assumed from module names) — the two are safe as fully independent,
  parallel dev tracks within this sprint.
- `services/gateway-api/src/app/models.py` and `services/gateway-api/migrations/versions/` (new `0006`) are
  touched by `ADMIN-002` only; no other in-flight or immediately-next-sprint story is known to touch them.
- `services/ingestion-service/src/app/models.py`, `migrations/versions/` (new `0009`), `connectors/base.py`,
  and `src/app/routers/datasets.py` are touched by `ADMIN-003` only; same check, no known overlap.
- `services/dashboard-web/src/app/templates/_crawl_status_panel.html` and `routers/operator.py`'s
  `_fetch_crawl_statuses`/`_format_progress` region are touched by `ADMIN-003` only in this sprint — the
  new `dashboard-web` Settings page `ADMIN-002` adds is a distinct, new template/route, not an edit to any
  file `ADMIN-003` touches.
- Both stories add a new Alembic migration in their own service (`gateway-api` `0006`, `ingestion-service`
  `0009`) — each is the correct next number in its own service's independent migration sequence; no
  cross-service migration-numbering conflict is possible since each service owns its own schema
  (implementation-plan.md section 5).

## Definition of done for this sprint

- `ADMIN-002`'s and `ADMIN-003`'s acceptance criteria (verbatim from
  `docs/product/backlog-trust-and-admin-ops.md`) are checked off in their respective tickets.
- `ADMIN-002`: a test proves `POST /tenants` and `POST /tenants/{tenant_id}/api-keys/{key_id}/revoke` each
  write exactly one `operator_audit_log` row on success, with the correct `action` value, `target_tenant_id`,
  and a `correlation_id` matching that request's `OPS-006` structured-log correlation id; a test proves no
  row is written on a rejected/`403` attempt (the disclosed write-on-success-only scope); a test proves no
  row ever contains the operator token (raw or hashed) in any column; a test proves `GET
  /operator-audit-log` is rejected without a valid operator session and paginates correctly with `limit`/
  `offset`; a test proves the new `dashboard-web` Settings page renders the log read-only behind the
  existing operator-session gate and renders no mutating controls.
- `ADMIN-003`: a test proves a fetch-write exception at `connectors/base.py`'s failure call site now
  produces a `crawl_runs` row with a non-null, non-empty `failure_detail` derived from the caught exception,
  and that the existing `raise` behavior (exception still propagates unchanged) is unaffected; a test proves
  `GET /connectors/{source}/status` (`datasets.py:136`) returns `failure_detail: null` for any non-`"failed"`
  status and a populated value for `"failed"`; a test proves `failure_detail` never contains a raw
  credential, connection string, or full stack trace for at least one representative connector exception
  case; a test proves `_crawl_status_panel.html` renders the failure detail next to the status cell only
  when `entry.status == "failed"`, with no layout change for any other status value.
- Positioning check (CLAUDE.md) explicitly re-verified in review for both: neither addition implies price
  prediction or a trading signal; both are framed as operational/audit transparency about the platform's
  own administration and data pipeline, consistent with the platform's "we audit rigorously" positioning
  (`da-tese-ao-produto.md` section 2.2) that `ADMIN-002`'s own rationale invokes.
- `services/gateway-api/README.md`, `services/ingestion-service/README.md`, and
  `services/dashboard-web/README.md` updated to record the new table/endpoint/page (`ADMIN-002`) and the
  new column/response field/panel extension (`ADMIN-003`) as shipped (README-current convention, per this
  repo's standing rule) — including gateway-api's README section on `OPS-006` logging being explicitly
  updated to note the new durable table now exists alongside (not instead of) the structured log lines.
- `docs/product/backlog-trust-and-admin-ops.md`'s `ADMIN-002`/`ADMIN-003` entries marked done with
  acceptance-criteria boxes checked, pointing to their ticket files.
- `docs/tickets/README.md` gets a new Sprint 58 section (Tech Lead updates this when tickets are
  created/closed, per this repo's standing convention — not done by this sprint plan itself).
- QA gate: per this platform's standing rule, the Tech Lead raises the `qa` agent (`/qa-validation`) after
  both tickets are Tech-Lead-verified done, before sign-off. QA scope should specifically, independently
  verify: `operator_audit_log` rows are actually written by both instrumented endpoints against the real
  local Docker stack (not just unit-test-mocked repositories), that a rejected/`403` attempt genuinely
  produces no row, that no raw or hashed operator token appears in any row or in the new Settings page's
  rendered HTML, that a real triggered connector failure (not just a unit-level mocked exception) produces
  a readable, non-secret `failure_detail` end to end through `GET /connectors/{source}/status` and into the
  rendered crawl-status panel, and that both new migrations (`gateway-api` `0006`, `ingestion-service`
  `0009`) apply cleanly against the current schema state in the real Compose stack.

## Next (explicitly not this sprint, roadmap note for continuing this backlog)

With `ADMIN-002`/`003` shipped, Epic C (Admin/Ops Maturity) has two stories remaining: `ADMIN-001`
(health-state-transition webhook) and `ADMIN-005` (self-serve API key rotation), both deferred here for
the reasons stated above. **Sprint 59 (tentative)**: `ADMIN-001` is the more self-contained of the two
(one new optional env var, one best-effort outbound POST, no new UI, no lockout-risk design work) and is
the more likely single-story candidate if the sprint stays small; `ADMIN-005` (self-serve key rotation) is
larger and carries real lockout-guard design risk that its own ticket should resolve explicitly before
implementation starts — the Tech Lead's ticket breakdown for `ADMIN-005`, whenever it's scheduled, would
benefit from a `/grilling` pass on the mint-then-confirm-then-revoke flow specifically, given the backlog's
own flagged risk. Either could also be paired with the start of Epic B (`RPT-001`, PDF export) if the
requester wants to shift focus; that scope call belongs to the Product Owner/requester, not preempted here.
That sprint will need its own PM pass re-verifying these citations against then-current code before being
handed to the Tech Lead, same as this one was.
