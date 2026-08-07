# Sprint 04 — libs/common (tenant-context module) + validation-service VS-010 wiring

Sprint goal: Ship `libs/common`'s minimal tenant-context module (`TenantContext` + fail-closed `Depends()` resolver, fully tested standalone) and wire it into `validation-service`, retiring VS-006/007/008's interim explicit `tenant_id` field so tenant resolution is a shared, DI-based mechanism proven against its one real consumer.

Backlog source: docs/product/backlog-libs-common.md (4 Must stories: LC-001, LC-002, LC-003, LC-004); docs/product/backlog-validation-service.md (VS-010)

Stories in scope (execution order):

1. **LC-001** — Package scaffolding. Depends on: none. Literal first step — nothing else in this backlog has a package skeleton to live in until this exists. Per its own acceptance criteria, this story does **not** touch `services/validation-service/pyproject.toml` — that wiring is VS-010's job (see note below), keeping the two backlogs independently shippable even though they land in the same sprint.
2. **LC-002** — `TenantContext` typed value object. Depends on LC-001. Defines the return shape LC-003's resolver needs before the resolver itself is built.
3. **LC-003** — FastAPI `Depends()`-based tenant context resolver (interim: explicit-field extraction). Depends on LC-002. This is the literal thing VS-010 has been blocked on since Sprint 03; needs `TenantContext` to resolve to first.
4. **LC-004** — Fail-closed test suite for tenant context resolution. Depends on LC-003. Proves LC-003's fail-closed guarantee standalone, inside `libs/common`'s own test app, before any real consumer wires it in — sequenced before VS-010 (even though VS-010's own stated dependency is only "libs/common minimal tenant-context module exists") because VS-010 should wire a resolver that is already proven, not one whose fail-closed behavior is verified for the first time against a real service.
5. **VS-010** — Tenant context resolution. Depends on: `libs/common` tenant-context module (LC-001–004, all now complete). Replaces VS-006/007/008's interim explicit `tenant_id` request field with the `Depends(get_tenant_context)` import from `naive_first_common`. This story — not LC-001 — is the one that adds `naive_first_common` as a dependency in `services/validation-service/pyproject.toml` and performs the actual swap in the route handlers, per the explicit division of responsibility stated in both backlogs.

Stories explicitly deferred:
- **LC-005** (README status update + public API doc-sync) — Should priority; doc-sync tooling isn't required to unblock or verify VS-010 against the real code (LC-001–004 are sufficient). Deferred to a later sprint, matching the Sprint 01→02/03 pattern of Shoulds rolling forward.
- **LC-006** (shared Pydantic schemas for cross-service payloads) — Won't (this backlog); no second real consumer exists yet (`gateway-api`/`reporting-service` triggers not fired). Deferred pending a second consumer, per the backlog's own YAGNI reasoning.
- **LC-007** (DB session helpers) — Won't (this backlog); no live Postgres instance exists yet (infra trigger #4 not fired) and still only one service. Deferred pending that trigger.
- **LC-008** (common formatting logic) — Won't (this backlog); neither `dashboard-web` nor `reporting-service` exists yet (triggers #7/#8 not fired). Deferred pending a second real consumer.
- **LC-009** (JWT/API-key-based tenant resolution) — Won't (this backlog); explicitly `gateway-api`'s concern (trigger #5, not fired). LC-003's swappable-resolution-strategy seam is what makes this a clean follow-up later, not a rewrite. Deferred pending that trigger; flagged in the backlog as a future `libs/common` backlog round, not a reopening of LC-003.

Binding sprint notes for the Tech Lead (decisions already made, not open for re-litigation this sprint):

- **LC-003's acceptance criteria says the resolver returns "400/401" on missing/empty `tenant_id`; the user has decided this must be 401 Unauthorized specifically** (not 400), for consistency with what `gateway-api`'s real auth will eventually return once it exists (trigger #5). Implement and test LC-003/LC-004 against 401, not 400.
- **LC-001 does not modify `services/validation-service/pyproject.toml`, even with VS-010 in-scope this same sprint.** VS-010 is the ticket that adds the `naive_first_common` dependency to `validation-service` and performs the swap from the interim explicit `tenant_id` field to the `Depends()`-based resolver. Keep this division intact when writing tickets — do not fold the dependency-wiring step into LC-001 just because both land in Sprint 04.

Definition of done for this sprint:
- All 4 in-scope `libs/common` Must stories' acceptance criteria are met as written in docs/product/backlog-libs-common.md, including the 401-not-400 binding note above.
- VS-010's acceptance criteria are met as written in docs/product/backlog-validation-service.md: `validation-service` route handlers (VS-006/007/008) resolve `tenant_id` via `Depends(get_tenant_context)` imported from `naive_first_common`; no tenant-resolution logic is hand-rolled inside `validation-service`; a test confirms requests without a resolvable tenant context are rejected before reaching repository code.
- `uv run pytest` passes in both `libs/common` (including LC-004's fail-closed suite, run against `libs/common`'s own minimal test app, independent of `validation-service`) and `services/validation-service` (including the updated VS-006/007/008 tests now exercising the `Depends()`-based resolver instead of the interim field).
- `libs/common/README.md`'s status line is updated from "planned" to "scaffolded" per LC-001; full doc-sync (LC-005) remains explicitly deferred, not silently skipped.
- `services/validation-service/README.md` is updated to reflect that the interim explicit `tenant_id` field (documented as interim in Sprint 03) has been retired and replaced by the shared `libs/common` resolver.
- No code in this sprint touches `libs/naive_first_engine`, `services/ingestion-service`, `services/reporting-service`, `services/gateway-api`, `services/dashboard-web`, or `services/economic-service` — all out of scope.
- LC-005, LC-006, LC-007, LC-008, LC-009 remain unscheduled/deferred as stated above — this sprint does not start any of them.
