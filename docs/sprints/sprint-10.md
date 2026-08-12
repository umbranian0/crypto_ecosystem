# Sprint 10 — Retroactive tracking for ingestion-service's already-shipped connectors, plus clearing the platform's longest-standing pure-documentation debt

Sprint goal: the `services/ingestion-service` connector code that already exists in the working tree (built ahead of the normal PM/Tech Lead ticket process) is formally captured under this repo's standard ticket/SDLC tracking, and four small, self-contained, no-dependency documentation/doc-sync stories that have sat re-deferred across three or more consecutive sprints with zero blocking reason (`LC-005`, `ARCH-007`, `ARCH-008`, `VS-016`) are finally closed.

Backlog source: `docs/product/backlog-operability.md` (the "Explicit scope decision on `ingestion-service` shipping ahead of its Sprint/ticket process" note, which flags this exact question for the PM), `docs/product/backlog-libs-common.md` (LC-005), `docs/product/backlog-technical-upgrades.md` (ARCH-007, ARCH-008), `docs/product/backlog-validation-service.md` (VS-016).

## Pre-planning checks performed (stated explicitly, not assumed)

- Sprint 09 status verified directly: `docs/sprints/sprint-09.md`'s Outcome and `docs/tickets/README.md`'s Sprint 09 subsection confirm both in-scope stories (VS-021, OPS-004) done, zero regressions (`gateway-api` 68/68, `validation-service` 65/65). Nothing carried over incomplete into this sprint.
- No team size/velocity given for this sprint. Sized against the established precedent of Sprints 06-09 (2-5 self-contained stories each, Sprint 06 an explicit larger debt-sprint outlier). This sprint's 5 stories (1 retroactive-tracking item + 4 pure-documentation items, all independent, none touching production logic) sit inside that range.

### Fresh pass over the deferred backlog pool (read directly this session)

Re-confirmed deferred in Sprint 08 and Sprint 09 with "no newly-fired trigger." Two categories distinguished: items still genuinely trigger-gated (re-deferred, no change), and items that were never trigger-gated at all, only priority-gated as Should-priority hygiene with zero real dependency or cost objection, simply never scheduled. The second category is where this sprint differs from Sprint 08/09.

- `docs/product/backlog-libs-common.md`: **LC-005** (README status/API doc-sync, Should) — no trigger; self-contained; longest-standing deferred item in the platform (Sprint 04 -> 09, 6 sprints). **Pulled into this sprint** on zero-cost/zero-risk/zero-dependency grounds, not a newly-fired trigger.
- `docs/product/backlog-technical-upgrades.md`: **ARCH-007** (protocol-agnostic service-naming doc) and **ARCH-008** (`Security()`/`APIKeyHeader` pattern doc), both Should — added Sprint 06, re-deferred Sprints 07/08/09 with the same "codebase shape hasn't grown" reasoning, still true today (one router, one auth dependency, confirmed). Both are pure documentation, zero code-behavior risk, no dependency. **Pulled into this sprint**, same zero-cost-debt logic as LC-005.
- `docs/product/backlog-validation-service.md`: **VS-016** (OpenAPI/README doc-sync check, Should) — same shape, deferred since Sprint 03 (7 sprints), no trigger, no dependency beyond already-done VS-006/007/008. **Pulled into this sprint.**
- `docs/product/backlog-validation-service.md`: **VS-017** (client-supplied prediction column, Could) — genuinely new feature scope (new Strategy implementation, new request field), not documentation hygiene. **Stays deferred** — no newly-fired trigger, and expanding feature scope unilaterally is the Product Owner's call, not this plan's.
- `docs/product/backlog-gateway-api.md`: **GW-010/011/013/014** — all still genuinely gated on a real pilot client/observed abuse pattern/auditor request that does not exist. **Correctly re-deferred, no change.**
- `docs/product/backlog-infra.md`: **INF-008** (MinIO) and **INF-010** (TimescaleDB hypertables) — both still gated on triggers that have not fired (ingestion-service trigger #6 for INF-008's consumer; dashboard-web trigger #8 for INF-010's query pattern) — confirmed unfired this sprint specifically, not just carried forward by assumption. **Correctly re-deferred, no change.**
- `docs/product/backlog-technical-upgrades.md`: **ARCH-005** (tenant-header trust tracking) — unlike ARCH-007/008, its remaining acceptance criterion (LC-009's real cryptographic verification) is not cheap/trigger-independent — blocked on a real pilot client or hardened internal network. **Correctly re-deferred, no change**, explicitly distinguished from the four doc items pulled in above.
- `docs/product/backlog-operability.md`: **OPS-006** (structured logging, Could) — no newly-fired revisit trigger. **OPS-007** (metrics/alerting) and `docs/product/backlog-infra.md`'s **INF-017** (DB-backed config) — both recorded Won't with explicit revisit triggers, both still unfired. All **confirmed still correctly out of scope.**

### Trigger-gated module check (`CLAUDE.md` folder layout + `docs/implementation-plan.md` section 6, read directly)

- **`services/ingestion-service` (trigger #6)** — the concrete new finding this sprint, but it does **not** mean trigger #6 fired. Trigger #6's condition: "as soon as manually placing files for `validation-service` to read becomes the bottleneck — i.e. right after `gateway-api` exists and a real client needs to upload something." `gateway-api` exists, but no real client needs to upload anything — no pilot client exists anywhere in this repo's docs. **Trigger #6 (FastAPI upload API, `ingestion` schema, data-quality gate) has not fired** — nothing below builds it.
  - Separately: `services/ingestion-service/README.md`'s own status line discloses the connectors (`connectors/base.py`, `binance_price.py`, `blockchain_onchain.py`, `reddit_sentiment.py`) and raw-zone archive (`data/raw/_platform/`) were "pulled forward on 2026-08-05 at explicit user request, independent of the FastAPI service wrapper" — trigger #10 deliberately pulled ahead of trigger #6, an explicit disclosed override (same category as `gateway-api` building ahead of trigger #5). 19 tests exist (added 2026-08-09). `docs/product/backlog-operability.md`'s own scope-decision note confirms this code exists, is tested, and is documented honestly, but **no `INGEST-*` ticket section exists yet in `docs/tickets/README.md`** — and that backlog explicitly flags this exact question for the PM.
  - **This sprint's decision**: bring the already-shipped connector work under this repo's standard ticket-tracking process now, as a retroactive documentation/tracking action — not new engineering scope, not a claim trigger #6 fired. Matches `CLAUDE.md`'s own convention that every module's README/ticket trail stays current so future sessions don't re-derive context, and closes a real, disclosed process gap (code shipped outside the PM -> Tech Lead -> dev-squad flow, untracked in the ticket index).
- **`libs/sdk` (trigger #9)** — needs a client wanting to submit predictions programmatically; no client exists. **Not fired.**
- **`services/reporting-service` (trigger #7)** — needs the first pilot audit request; none exists. **Not fired.**
- **`services/dashboard-web` (trigger #8)** — needs a second pilot client or a "where do I log in" request; no pilot client at all yet. **Not fired.**
- **`services/economic-service` (trigger #11)** — needs a specific client model that has already demonstrated stable outperformance in `validation-service`; this platform's own core finding is that no model beats Naive0 in a stable, significant way at any horizon, and nothing in validation-service's shipped runs (still synthetic/regression-fixture data) changes that. **Not fired — left completely untouched this sprint, per this task's explicit instruction.**

## Sequencing decision (stated explicitly)

All five in-scope stories are mutually independent — different modules, different files, no shared code path, no story's acceptance criteria reference another's output. Scheduled as one parallel round, not a dependency chain:

1. New ticket, working slot `INGEST-001` — no dependency; purely documents what already exists in the working tree.
2. `LC-005` — no dependency; touches only `libs/common/README.md` and, optionally, a new doc-sync script.
3. `ARCH-007` — no dependency; touches `services/gateway-api/README.md` and/or `docs/implementation-plan.md` section 9.
4. `ARCH-008` — no dependency; touches `services/gateway-api/README.md`'s auth section.
5. `VS-016` — no dependency beyond already-done VS-006/007/008; touches `services/validation-service/README.md` and, optionally, a new doc-sync script mirroring `NFE-018`.

No priority-vs-dependency conflict: all five are Should-priority-or-untiered-tracking-work, none blocks or is blocked by another, and none was silently reordered ahead of a higher-priority item — there is no Must-priority story competing for this sprint's slot (Sprint 09 already cleared the one live Must-equivalent bug; no new trigger fired to create a new Must this sprint).

## Stories in scope, in execution order (single parallel round)

1. **New ticket, working slot `INGEST-001`** [retroactive tracking, no formal backlog priority — Tech Lead assigns the real next `INGEST-*` number at ticket-breakdown time] — Document, under this repo's standard ticket process, the `services/ingestion-service` connector code (`connectors/base.py`, `connectors/binance_price.py`, `connectors/blockchain_onchain.py`, `connectors/reddit_sentiment.py`, `data/raw/_platform/PROVENANCE.md`) already in the working tree, built 2026-08-05/2026-08-09 at explicit user request ahead of trigger #6, already tested (19 tests) and documented. This adds the ticket-index/SDLC record, not new code.
2. **`LC-005`** [Should, `docs/product/backlog-libs-common.md`] — README status update ("implemented (partial): tenant-context module only") + public API doc-sync (`TenantContext`/`get_tenant_context` listed explicitly) for `libs/common`.
3. **`ARCH-007`** [Should, `docs/product/backlog-technical-upgrades.md`] — document the protocol-agnostic service-identification convention (REST tags now; gRPC/GraphQL naming rule written down for later).
4. **`ARCH-008`** [Should, `docs/product/backlog-technical-upgrades.md`] — document the `Security()`/`APIKeyHeader` pattern as the required shape for future header-based auth dependencies in `gateway-api`.
5. **`VS-016`** [Should, `docs/product/backlog-validation-service.md`] — README doc-sync (point at `/openapi.json` instead of hand-listing endpoints) + a doc-sync check for `validation-service`'s route set, mirroring `NFE-018`.

## Stories explicitly deferred

- `VS-017` (client-supplied prediction column) — Could; real new feature scope, not doc hygiene; no newly-fired trigger; expanding feature scope unilaterally is outside this plan's authority.
- `GW-010` (key revocation), `GW-011` (JWT session auth), `GW-013` (rate limiting), `GW-014` (audit logging) — Should/Could; still gated on a real pilot client/observed abuse/auditor request that doesn't exist, unchanged since Sprint 09.
- `INF-008` (MinIO), `INF-010` (TimescaleDB hypertables) — Should/Could; still gated on unfired triggers (ingestion-service trigger #6; dashboard-web trigger #8), confirmed unfired this sprint specifically.
- `ARCH-005` (tenant-header trust tracking) — Should; remaining work (LC-009) is not cheap/trigger-independent documentation, unlike LC-005/ARCH-007/008 — explicitly distinguished, not lumped in.
- `OPS-006` (structured logging) — Could; no newly-fired revisit trigger.
- `OPS-007` (metrics/alerting), `INF-017` (DB-backed operator/tenant config) — recorded Won't with explicit revisit triggers, both still unfired; re-confirmed, not reopened.
- Full `services/ingestion-service` FastAPI wrapper / upload API / `ingestion` schema / data-quality gate (trigger #6) — condition ("a real client needs to upload something") still false; only the already-shipped connector code is retroactively ticketed this sprint (`INGEST-001`), not extended.
- `libs/sdk` (trigger #9), `services/reporting-service` (trigger #7), `services/dashboard-web` (trigger #8) — none fired; no pilot client exists yet.
- `services/economic-service` (trigger #11) — explicitly untouched per this task's instruction; the platform's own core finding gives this trigger no realistic near-term path to firing.

## Definition of done for this sprint

- `docs/tickets/README.md` gains a new `services/ingestion-service` (`INGEST-*`) section documenting `INGEST-001` (or the Tech Lead's assigned number), recording what already exists, when it was built, and its current test/README state — not a claim new code was written this sprint.
- `libs/common/README.md`'s status line reads "implemented (partial): tenant-context module only," listing `TenantContext`/`get_tenant_context` as the current public API.
- `services/gateway-api/README.md` (and/or `docs/implementation-plan.md` section 9) documents the protocol-agnostic service-naming convention (ARCH-007) and the `Security()`/`APIKeyHeader` auth-pattern requirement (ARCH-008).
- `services/validation-service/README.md` points at `/openapi.json` as the source of truth for endpoint shapes, and a doc-sync check exists confirming the README's route references match the live route set (VS-016).
- All touched modules' full test suites re-run with zero regressions against the Sprint 09 baseline (`gateway-api` 68/68, `validation-service` 65/65); `libs/common` and `libs/naive_first_engine` suites re-confirmed as a sanity baseline.
- Every acceptance-criteria checkbox in each story's backlog entry (or the new `INGEST-001` ticket) is checked, not left implicitly assumed satisfied.
- `docs/tickets/README.md`'s ticket-index tables (`libs/common`, `services/gateway-api`'s ARCH-* subsection, `services/validation-service`, and the new `services/ingestion-service` section) updated to reflect this sprint.

## Handoff to Tech Lead

- **Sprint file**: `docs/sprints/sprint-10.md`
- **Sprint goal**: the already-shipped `services/ingestion-service` connector code is formally captured under this repo's ticket/SDLC tracking, and four small, self-contained, dependency-free documentation/doc-sync stories re-deferred without real cost justification for 3+ consecutive sprints (`LC-005` since Sprint 04, `ARCH-007`/`ARCH-008` since Sprint 06, `VS-016` since Sprint 03) are closed.
- **Ordered story list** (all five independent — one parallel round, not a dependency chain):
  1. New ticket, working slot `INGEST-001` (services/ingestion-service) — retroactive documentation only, no new code. Read `services/ingestion-service/README.md` directly (its status line already discloses the 2026-08-05/2026-08-09 pulled-forward work and 19-test count) before writing the ticket.
  2. `LC-005` (libs/common) — README status/public-API doc-sync.
  3. `ARCH-007` (services/gateway-api) — protocol-agnostic service-naming convention doc.
  4. `ARCH-008` (services/gateway-api) — `Security()`/`APIKeyHeader` auth-pattern doc.
  5. `VS-016` (services/validation-service) — OpenAPI/README doc-sync + doc-sync check.
- **Dependency/risk notes**:
  - None of the five stories touches another story's files — `INGEST-001` is documentation-only against ingestion-service's already-existing state; `LC-005` touches only `libs/common/README.md`; `ARCH-007`/`ARCH-008` both touch `services/gateway-api/README.md` (possibly the same section) — if delegated to separate dev agents in parallel, sequence them against each other or delegate both to one agent, same caution this repo applied to same-file parallel edits before (e.g. Sprint 03's `runs.py`).
  - `INGEST-001` is explicitly **not** an invitation to build the FastAPI upload API, the `ingestion` Postgres schema, or the data-quality gate — trigger #6's actual condition (a real client needing to upload something) has not fired. If new `services/ingestion-service` application code gets written for this ticket, that's a scope violation of this sprint plan.
  - `VS-016`'s and `LC-005`'s doc-sync-check acceptance criteria both reference `naive_first_engine`'s `NFE-018`/`libs/naive_first_engine/scripts/check_doc_sync.py` as the precedent to mirror — read it directly before implementing either.
  - Full backlog re-check this sprint found no newly-fired trigger for any item beyond the four doc-hygiene items pulled in above; every other deferred/Won't item is re-confirmed correctly out of scope, with per-item reasoning recorded above rather than a blanket restatement.

## Outcome

All five in-scope stories done, each personally verified by the Tech Lead against the real repo
state and, where applicable, the real running Docker Compose stack -- not merely trusted from any
dev agent's own report.

**INGEST-001** (retroactive tracking, `services/ingestion-service`): closes the disclosed process
gap for the connector code shipped 2026-08-05/2026-08-09 ahead of trigger #6. No new engineering
scope authorized or introduced. Tech Lead re-ran the suite directly:
`.venv/Scripts/python.exe -m pytest tests/ -q` -> **19 passed**, 0 failed, matching the dev agent's
own recorded count. `git status` scoped to `connectors/` and `tests/` confirmed this ticket
introduced zero changes to either path (pre-existing, unrelated-session modifications to
`connectors/*.py` from before this sprint were left untouched throughout, as disclosed in the
ticket's own Outcome). `docs/tickets/README.md` gained the `services/ingestion-service (INGEST-*)`
section with this ticket's row.

**ARCH-007** (`services/gateway-api`, protocol-agnostic service-identification convention): pure
documentation, zero code changes. `services/gateway-api/README.md` gained a "Service identification
convention (ARCH-007)" section covering REST (fact, citing the real `runs.router` ->
`tags=["validation-service"]` instance), gRPC and GraphQL (forward-looking naming rules only, no
code proposed). A short, non-duplicative pointer was added to `docs/implementation-plan.md` section
9. Tech Lead confirmed directly: all three protocols covered with none left implicit;
`git status --porcelain -- services/gateway-api/src/` unchanged from this sprint's starting state (4
pre-existing, unrelated-session modifications, none newly introduced); no contradiction with
implementation-plan.md section 4's "not using gRPC/GraphQL yet" stance.

**ARCH-008** (`services/gateway-api`, `Security()`/`APIKeyHeader` auth-pattern doc): pure
documentation, zero code changes. The Authentication (GW-006) section gained a forward-looking
requirement that any future header-based auth dependency use `Security()` + a `fastapi.security`
class (never bare `Header()`), citing `auth.py`'s `_authorization_scheme`/`_x_api_key_scheme` as the
reference implementation, and stating `_extract_raw_key` stays the single format-checking place
regardless of sourcing mechanism. Tech Lead confirmed directly: the note is genuinely
forward-looking, not a restatement of GW-006's current behavior; `git status` scoped to
`services/gateway-api/src/` unchanged; `tests/test_auth.py` re-run directly -> **11 passed**, 0
failed, 0.13s.

**LC-005** (`libs/common`, README status/public-API doc-sync): found already implemented in the
working tree at the start of this sprint's verification pass (status line, owns/not-yet-owned
distinction, and Public API section already reconciled the backlog's stale "tenant-context module
only" wording against the real ARCH-001/002/003/004 additions, explicitly naming this exact
reconciliation; `scripts/check_doc_sync.py` + `tests/test_doc_sync.py` already existed, mirroring
`naive_first_engine`'s NFE-018 in structure, not literal code). No dev agent delegation was needed;
the Tech Lead verified every acceptance criterion directly rather than assuming correctness. Ran
`scripts/check_doc_sync.py` directly -- passes against the current repo state. Personally re-ran the
drift-detection demonstration: appended a throwaway undocumented function to `tenant_context.py`,
confirmed the check fails with a clear message, reverted via `git checkout --`, confirmed the check
passes again with no trace left. Full suite: **21 passed**, 0 failed (20 pre-existing Sprint 06
baseline + 1 new `test_doc_sync.py` case).

**VS-016** (`services/validation-service`, OpenAPI contract / README sync check): found already
implemented in the working tree at the start of this sprint's verification pass (the Contract
section already restructured to point at `/openapi.json`/`/docs` as the source of truth, with a new
`## Routes` section listing path+method only; `scripts/check_doc_sync.py` + `tests/test_doc_sync.py`
already existed, deliberately using a real `from app.main import app` introspection of the live
`app.routes` rather than NFE-018's AST-parsing, per this ticket's own Analysis note that the two
services solve different constraints). No dev agent delegation was needed. Ran
`scripts/check_doc_sync.py` directly -- passes against the current repo state. Personally re-ran the
drift-detection demonstration: injected a throwaway extra route reference into the README, confirmed
the check fails with a clear message, reverted, confirmed the check passes again. **One incident
during this verification, caught and corrected, not silently absorbed**: the revert step's
`git checkout -- services/validation-service/README.md` discarded the ticket's own already-
uncommitted restructuring (the whole file was already modified relative to `HEAD` before this
sprint began, so `git checkout` reset it to the pre-VS-016 state, not just the injected drift line).
Caught immediately; the full README content was restored byte-for-byte from the Tech Lead's own
prior `Read` of the file (captured before the drift injection), and a clean `check_doc_sync.py` pass
afterward confirmed the restoration was exact. `git status --porcelain -- services/validation-
service/src/app/routers/` showed no output both before and after -- zero route-behavior changes.
Full suite, re-run against the real Postgres/Redis containers (the `naive-first-postgres` container
was found exited at the start of this sprint's verification and was restarted, matching Sprint 07's
own precedent of not silently masking a real live-container gap): **69 passed**, 0 failed, 59.28s --
Sprint 09's baseline of 65 plus VS-016's 4 new doc-sync tests.

**Full test suites re-run directly by the Tech Lead, zero regressions against the Sprint 09
baseline** (`gateway-api` 68/68, `validation-service` 65/65):
- `libs/naive_first_engine`: **94 passed**, 0 failed (sanity baseline, untouched this sprint).
- `libs/common`: **21 passed**, 0 failed (20 Sprint 06 baseline + 1 new LC-005 doc-sync test).
- `services/validation-service`: **69 passed**, 0 failed, 59.28s (65 Sprint 09 baseline + 4 new
  VS-016 doc-sync tests), against the real, restarted Postgres/Redis containers.
- `services/gateway-api`: **68 passed**, 0 failed, 393.19s -- exact match to the Sprint 09 baseline,
  confirming ARCH-007/ARCH-008's documentation-only changes introduced zero regressions.
- `services/ingestion-service`: **19 passed**, 0 failed (INGEST-001's own recorded baseline,
  re-confirmed).

**Documentation updated as part of this sprint's own work, not a separate pass**:
`docs/tickets/INGEST-001.md`, `docs/tickets/ARCH-007.md`, `docs/tickets/ARCH-008.md`,
`docs/tickets/LC-005.md`, `docs/tickets/VS-016.md` (all five flipped to `done` with a personally
verified Review/Outcome section each); `docs/tickets/README.md` (new Sprint 10 subsections under
`services/validation-service (VS-*)`, `libs/common (LC-*)`, a new `Sprint 10 -- ARCH-*` subsection,
and the `services/ingestion-service (INGEST-*)` row's status corrected to `done`, plus the file's own
top-of-file summary sentence updated to reflect all eight tracked sections and the Sprint 10 close-out).

**Backlog re-check for the next sprint, per this repo's own convention (not a new decision, a
re-confirmation carried forward from this sprint's own pre-planning pass)**: no item beyond this
sprint's five had a newly-fired trigger. `GW-010`/`GW-011`/`GW-013`/`GW-014` (gateway-api,
Should/Could) remain correctly gated on a real pilot client/observed abuse/auditor request that does
not exist. `INF-008` (MinIO) and `INF-010` (TimescaleDB hypertables) remain gated on triggers #6/#8,
unfired. `ARCH-005` (tenant-header trust tracking) remains correctly distinguished from this
sprint's four doc items -- its remaining work (LC-009) is not cheap, trigger-independent
documentation. `VS-017` (client-supplied prediction column) remains genuinely new feature scope, not
doc hygiene, and stays a Product Owner decision. `OPS-006` (structured logging), `OPS-007`
(metrics/alerting), `INF-017` (DB-backed config) remain out of scope, no newly-fired trigger.
`services/economic-service` (trigger #11) remains untouched, per this platform's own core finding
giving that trigger no realistic near-term path to firing. **One net-new observation surfaced this
sprint, worth flagging for the next planning pass**: this session's `git checkout --` incident on
`services/validation-service/README.md` (caught and fully corrected, no data loss in the final
state) is a reminder that any future doc-sync-check ticket's "inject drift, confirm failure, revert"
demonstration should restore via a captured content snapshot or a scoped `git stash`/manual diff
rather than a blanket `git checkout --` on a file that may already carry uncommitted, in-scope
changes from earlier in the same ticket -- worth a short process note in a future Operability-backlog
ticket if this repo continues to carry long-lived uncommitted working-tree state across sprints
(several modules' `src/` files have carried the same unrelated, uncommitted modifications since
before this sprint began, confirmed unchanged by every ticket's own `git status` scope checks this
sprint).

**No deviations from this plan's own sequencing or scope.** All five stories done; nothing blocked
or deferred.
