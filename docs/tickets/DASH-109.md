# DASH-109 (unblocked) — Monitoring page: add `ingestion-service` as a fourth status row

**Sprint**: 18. **Module**: `services/dashboard-web`, `services/gateway-api`. **Status**: done.
**Priority**: Must. **Depends on**: `INGEST-007`, `GW-022`, `DASH-113` (this sprint's minimal-slice
unblock of `SETUP-020`, per requester's explicit resolution — the full `SETUP-020`/`SETUP-021`/`022`
Monitoring epic in the sibling backlog remains its own scope; this sprint pulled only the aggregate
health endpoint + a bare `/monitoring` page, nothing else).

## Analysis
Story: backlog `DASH-109`, unchanged design. Extends `GW-022`'s aggregate health (already includes
`ingestion-service` as a fourth key per `GW-022`'s own AC) with a real per-tenant ingestion status panel
on `DASH-113`'s `/monitoring` page.

## Design
File: `services/dashboard-web`'s `/monitoring` template/route (extend `DASH-113`, not a second page).
New panel calls `INGEST-009`'s `GET /connectors/{source}/status` via `GW-019`'s proxy (or a small
addition to it if that proxy doesn't yet cover this route — confirm at implementation time) per tenant/
source. **DRY check**: reuses `DASH-113`'s existing health-row rendering, one more row, not a second
rendering path.

## Implementation acceptance criteria
- [x] `/monitoring` shows `ingestion-service` as a fourth health row (already surfaced by `GW-022`,
  this ticket just confirms the dashboard renders it — if `GW-022` already renders all returned keys
  generically, this criterion may already be satisfied and this ticket only adds the panel below).
  Confirmed: `monitoring.html`'s existing `{% for name, status in services.items() %}` loop already
  renders every key generically, no template change was needed for this half of the ticket.
- [x] New panel: per source, the calling tenant's own `crawl_runs` history (last status/timestamp/
  watermark) — labeled plainly "last crawl status," never implying predictive/data-quality signal
  (CLAUDE.md). Implemented as a second panel on the same `/monitoring` page, backed by a new
  `GET /ingestion/connectors/{source}/status` proxy on `gateway-api` (`GW-019`'s router had no proxy
  for `INGEST-009`'s per-source status endpoint before this ticket). Gated by a non-raising
  `OptionalDownstreamHeadersDep` (see design decision note below) rather than the whole page's own
  no-auth requirement being broken.

## Test acceptance criteria
- [x] Mocked all-healthy/one-degraded/unreachable cases for the fourth row (pre-existing
  `tests/test_monitoring.py` cases from `DASH-113`, still passing, now asserting on a 4-key response);
  mocked populated/empty crawl-status panel (`test_monitoring_crawl_status_panel_populated_for_logged_in_tenant`/
  `test_monitoring_crawl_status_panel_empty_for_logged_in_tenant_with_no_datasets`, plus an
  anonymous-visitor login-prompt case). New `gateway-api` proxy route covered in
  `tests/test_ingestion_routing.py` (happy path, downstream 404, tenant-id forwarding, missing-auth
  401, transport 502/504).

## Review acceptance criteria (Tech Lead verifies personally)
- Confirms panel copy makes no predictive/trading claim.
- Confirms no second `/monitoring`-equivalent page was created.

## Documentation acceptance criteria
- [x] `services/dashboard-web/README.md` documents the new panel (see "Last crawl status panel
  (DASH-109)" section). `services/gateway-api/README.md` also updated for the new proxy route.

## Auth design decision (not in original ticket, resolved during implementation)

`/monitoring` stays unauthenticated end-to-end (`GW-022`'s/`DASH-113`'s existing no-auth design,
`test_monitoring_requires_no_session` still passes unmodified). The crawl-status panel needs a
`TenantContext` to call `GET /ingestion/datasets`/`GET /ingestion/connectors/{source}/status`, so a
new `app.dependencies.downstream.get_optional_session_headers`/`OptionalDownstreamHeadersDep`
(dashboard-web) was added: a non-raising counterpart to the existing `get_session_headers` that
returns `None` (instead of redirecting to `/login`) for a missing/unknown tenant session, reusing the
same cookie-read/`SessionStore.get` call rather than a second copy. The panel itself renders a plain
"log in to view your own ingestion status" message when `headers is None`, and the real per-source
table once a tenant session cookie is present -- an anonymous visitor still sees the full four-row
health table, just not this one inherently tenant-scoped panel.
