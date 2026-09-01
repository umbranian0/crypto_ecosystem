# INGEST-012 — `GET /connectors/credentials-status`: tenant-scoped credential presence check

**Sprint**: 18. **Module**: `services/ingestion-service`, `services/gateway-api`. **Status**: done
(dev-squad implementation/test/documentation phases complete; Review acceptance criteria's live
Compose-stack verification is the Tech Lead's own remaining step, per this ticket's own Review
section -- not re-attempted here).
**Priority**: Must (unblocks `DASH-112`). **Depends on**: `INGEST-004` (done). **Blocks**: `DASH-112`.

## Analysis

Live-UAT finding (not in the original backlog): `GW-021`'s `GET /ingestion/connectors/
credentials-status` proxies to a path that was never built — `INGEST-009` shipped `GET /connectors/
{source}/status` (crawl-run status, a different resource), and no endpoint exposes credential
*presence* at all. See `docs/sprints/sprint-18.md`'s UAT addendum for the full design decision this
ticket implements: per-tenant lookup (operator supplies `tenant_id` explicitly), not a cross-tenant
aggregate — no new RLS-bypass trust boundary introduced, consistent with `SETUP-011`'s full
tenant-directory scope staying out of this sprint.

## Design

Pattern: Repository (reuses `INGEST-004`'s existing `CredentialRepository.get_credentials`, no new
data-access mechanism). Files touched: `services/ingestion-service/src/app/routers/connectors.py` (add
one new route to the existing router — do not create a second router file for one endpoint) or a new
small router if `connectors.py` is judged too crowded (dev agent's call); `services/gateway-api/src/app/
routers/operator.py` (patch the existing `GET /ingestion/connectors/credentials-status` route to accept
an explicit `tenant_id` query parameter and forward it as `X-Tenant-Id`, replacing its current
no-tenant-context proxy call).

## Implementation acceptance criteria

- [x] `GET /connectors/credentials-status` (tenant-authenticated via `X-Tenant-Id`, same convention as
  every other `ingestion-service` endpoint) returns `{"items": [{"source": str, "credential_set": bool,
  "last_set_at": datetime | null}]}` for every known credentialed source (Reddit only, today) — never
  the credential value itself.
- [x] `GW-021`'s proxy route is patched: accepts `tenant_id` as an explicit query parameter (the caller
  is an operator, who has no tenant context of their own to forward), forwards it as `X-Tenant-Id` on
  the downstream call. Missing `tenant_id` → `422` from gateway-api itself (FastAPI's own required-param
  validation), not a downstream call with an empty/garbage tenant id.
- [x] `get_authenticated_operator` (GW-021) remains the only auth gate on this route — this patch does
  not change who may call it, only what they must supply.

## Test acceptance criteria

- [x] `ingestion-service`: a tenant with a stored Reddit credential shows `credential_set: true` +
  timestamp; a tenant with none shows `credential_set: false`, `last_set_at: null` — never a `404` (an
  empty/unset status is a valid answer, not an error, matching this platform's "empty is 200" convention).
- [x] `gateway-api`: a valid operator token + valid `tenant_id` → `200`, forwarded correctly; missing
  `tenant_id` → `422`; a real tenant's own API key (not an operator token) → `401`, same cross-boundary
  proof `GW-021`'s original tests already established, re-run unmodified.

## Review acceptance criteria (Tech Lead verifies personally)

- Confirms no new cross-tenant/unscoped query path was introduced anywhere (the endpoint is tenant-scoped
  exactly like every sibling endpoint; the operator's `tenant_id` parameter selects *which* tenant's
  scope to apply, it does not bypass scoping).
- Live-verifies against the real Compose stack (not just mocked tests), given this exact gap was found
  via live UAT and not by any ticket-level suite — the same lesson this sprint's own UAT addendum names.

## Documentation acceptance criteria

- [x] `services/ingestion-service/README.md` and `services/gateway-api/README.md` both updated
  (read fresh, merge additively) documenting the new endpoint and the corrected proxy contract; `GW-021`'s
  own README section is corrected in place (not left describing the now-fixed permanent-404 mismatch as
  a temporary "not built yet" state).
