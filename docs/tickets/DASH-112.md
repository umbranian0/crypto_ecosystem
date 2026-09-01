# DASH-112 (unblocked, revised, read-only, per-tenant lookup) — Settings: connector credential status

**Sprint**: 18. **Module**: `services/dashboard-web`, `services/gateway-api`. **Status**: done
(implementation + tests complete; Review acceptance criteria await the Tech Lead's own personal
verification per this ticket's own convention -- not self-certified here).
**Priority**: Should. **Depends on**: `INGEST-004` (done), `INGEST-012` (new, must land first — the
real endpoint this page calls), `GW-021` (done, patched by `INGEST-012`), `DASH-113` (done, operator-
session gate for `/settings/*`).

## Analysis
Story: backlog `DASH-112`, unchanged read-only scope (solution-design.md 8.9(a): credential-write form
is CLI-only this sprint, not relitigated). **Revised per the live-UAT design decision recorded in
`docs/sprints/sprint-18.md`'s UAT addendum**: this is a **per-tenant** lookup, not a cross-tenant
aggregate — an operator supplies a `tenant_id` explicitly (no tenant directory exists this sprint;
`SETUP-011`'s full tenant-list/lookup UI remains out of scope), and the underlying query stays
tenant-scoped via the existing RLS mechanism, introducing no new operator-level trust boundary.

## Design
File: new `services/dashboard-web` route, `/settings/connectors`, gated by `DASH-113`'s
`require_operator_session`. **DRY check**: calls `INGEST-012`'s patched `GW-021` proxy
(`GET /ingestion/connectors/credentials-status?tenant_id=...`) directly — no second credential-status
query invented.

## Implementation acceptance criteria
- [x] `/settings/connectors` requires the operator session (`DASH-113`) — a tenant's own session cannot
  reach it.
- [x] Page includes a `tenant_id` input field (text field is sufficient — no tenant directory/dropdown
  exists this sprint, an honest reflection of that gap, not a silently degraded feature) submitted as
  the query parameter `INGEST-012`'s patched proxy expects.
- [x] Lists, per source, whether a credential is stored (boolean) + last-set timestamp for the entered
  tenant — never the credential value itself.
- [x] No write form in this phase (structurally: no POST route exists here at all) — an operator uses
  `services/ingestion-service/scripts/set_connector_credentials.py` (CLI) in the meantime.
- [x] A missing/blank `tenant_id` submission redisplays the form with a clear "enter a tenant id" error,
  not a raw 422 passthrough.
- [x] Positioning check: no copy implies trading/prediction capability.

## Test acceptance criteria
- [x] A tenant's own session gets rejected from this route; a valid operator session with a valid
  `tenant_id` sees the status list; an unknown `tenant_id` shows an empty/all-false status list, not an
  error (mirrors this platform's "empty is a valid answer" convention). Covered in
  `services/dashboard-web/tests/test_settings_connectors.py` (7 tests, all passing).

## Review acceptance criteria (Tech Lead verifies personally)
- Confirms zero POST/write route exists on this page (grep for `@router.post` in this file — must find
  none).
- Confirms the `tenant_id` field is a plain, disclosed manual-entry gap, not presented as if a real
  tenant directory exists.

## Documentation acceptance criteria
- [x] `services/dashboard-web/README.md` documents this page, the CLI-only write-path caveat, and the
  manual-tenant-id-entry caveat (with `SETUP-011` named as the eventual fix once it exists); annotates
  `backlog-first-run-setup-and-ops.md`'s `SETUP-013` as superseded by this ticket.
