# Sprint 64 — Epic C: ADMIN-005 self-serve API key rotation (`services/gateway-api` + `services/dashboard-web`)

Sprint goal: by the end of this sprint, a logged-in tenant can mint a new API key and revoke an old one for its own
tenant without an operator, and cannot lock itself out doing so.

Backlog source: `docs/product/backlog-trust-and-admin-ops.md`, Epic C, `ADMIN-005` (Should, already approved/prioritized).
Capacity: not stated by the requester; one story, no capacity claim made.

## Independent verification (code read, not taken from the backlog)

- **ADMIN-005 is not done.** No `/me/api-keys` route, no tenant-facing key list/mint/revoke anywhere in `services/`
  (grep for `/me/`, `rotate`, `rotation` hits only operator-token rotation notes in READMEs/`operator_auth.py`).
  The deferral history (sprints 55-61, 63) is consistent: never started.
- **Existing building blocks (all confirmed present):**
  - Key minting is inline in `gateway-api/src/app/provisioning.py::provision()` (`secrets.token_urlsafe(32)`, sha256,
    `api_key_repo.create_key`), and `provision()` also creates the tenant and seeds platform history. It cannot be
    called for an existing tenant. **Backlog says "reuse the same key-generation code" -- this requires extracting a
    tiny `mint_api_key(tenant_id, api_key_repo) -> raw_key` helper that `provision()` then calls (one implementation,
    no behavior change to `provision()`).** Disclosed, small.
  - `ApiKeyRepository` (`interfaces.py`): `create_key`, `get_by_hash`, `revoke_key(tenant_id, key_id)` (sets
    `revoked_at`, WHERE scoped to `tenant_id`, plus RLS), `list_api_keys(tenant_id)`.
  - GW-010 revocation: `get_authenticated_tenant` rejects a revoked key with 401 on the very next request, no cache.
  - Operator revoke (`routers/tenants.py`): 404-on-not-owned via `list_api_keys` + id match, already-revoked is a
    200 no-op, writes `operator_audit_log` row. There is **no operator "mint a key for an existing tenant"
    endpoint**: `POST /tenants` always creates a new tenant. So a tenant that loses all active keys has no
    UI/API recovery (only DB/CLI). This is why the lockout guard must be server-enforced, not UI-only.
  - `get_authenticated_tenant` returns only `TenantContext(tenant_id)`; the matched key's id is discarded.
  - dashboard-web: login stores the **raw key** in an in-memory `SessionStore` (`session_id` cookie, DASH-002);
    `DownstreamHeadersDep` (DASH-003) injects it as `Authorization: Bearer` and redirects to `/login` on 401.
    Operator settings pages use a separate `OperatorTokenHeaderDep`. `_one_time_reveal.html` (SETUP-012) takes
    `label`, `name`, `api_key`, `continue_url`, `continue_text`.
  - `operator_audit_log` (ADMIN-002, migration 0006): `action` is a free `String`, no CHECK constraint, no actor
    column, no RLS; `target_tenant_id` nullable. New action values need no migration.

## Lockout-guard stress test: every question and its resolution

All resolved with safe defaults. None needs a user decision.

1. **Rotate while only one key exists.** Mint-new is always allowed, so the tenant goes 1 -> 2 active keys; nothing
   is lost. Revoke is where danger lies. Rule (server-side, `gateway-api`): a revoke is refused (409) if it would
   leave the tenant with zero active keys. Checked inside the same transaction as the update, see Q5.
2. **Revoke-old-before-new-confirmed.** No single "replace" endpoint exists; mint and revoke are separate calls.
   "Confirmed usable" is enforced structurally, not by a flag: **`POST /me/api-keys/{key_id}/revoke` returns 409 if
   `key_id` is the key that authenticated this very request.** Revoking key A therefore requires a request
   authenticated by a different active key B, which proves B works. Stateless, no pending-rotation table.
3. **Session using the key being rotated.** Consequence of Q2: the dashboard session (which holds exactly one raw
   key) can never revoke its own key. Flow for a leaked key: mint new, copy it, log out, log in with the new key,
   revoke the old one. Another session on the old key (or a script) simply gets 401 on its next request (GW-010)
   and DASH-003 redirects to `/login`; nothing new needed. The new key is **never** auto-swapped into the session.
   **AC amendment, disclosed:** the backlog AC asks for a UI *warning* before revoking the in-use key; this plan
   replaces that with a hard server block plus a disabled "revoke" control labelled "key in use by this session"
   (stricter, so strictly safer; satisfies the intent). The user may restore warn-and-allow if wanted, but there is
   no reason to.
4. **Knowing which key is "current".** Add a small dependency (e.g. `get_authenticated_key`, returns the matched
   `ApiKeyRecord`) that `get_authenticated_tenant` is refactored to wrap, so auth behavior is unchanged and 401
   paths/logging stay in one place. `GET /me/api-keys` marks the caller's own key `current: true`. The raw
   key/`key_hash` never appears in any response model.
5. **Concurrent rotation.** Two sessions on keys A and B revoking each other simultaneously would both pass Q2 and
   leave zero keys. Resolution: the guarded revoke must be atomic with the last-active-key check (Postgres: lock the
   tenant's `api_keys` rows `FOR UPDATE` in the revoke transaction, count active keys excluding the target, refuse if
   zero; SQLite repo: equivalent single write transaction). Implement as one new repository method (Tech Lead names
   it); the operator path keeps calling plain `revoke_key` unchanged (operator is a deliberate privileged override,
   and its behavior is out of this story's scope). Concurrent mints are independent inserts, harmless. Concurrent
   revokes of the same key are idempotent (already-revoked is a 200 no-op, matching the operator endpoint). Required
   test: the A-revokes-B / B-revokes-A race on Postgres (or, if the repo test harness cannot run real concurrency,
   a deterministic test of the "count excluding target" rule plus a note of that limitation).
6. **Tenant isolation.** Tenant id comes only from the authenticated key, never from a path/body parameter (routes
   are `/me/...`). Revoke resolves `key_id` via `list_api_keys(caller_tenant)` + match; not-found and
   belongs-to-another-tenant both return the same generic 404 (same non-disclosure stance as the operator endpoint).
   RLS remains defense in depth. Required tests per the AC: another tenant's key cannot be listed, minted-for or
   revoked (404 for revoke, not present in list).
7. **Audit log via ADMIN-002.** The table is typed "operator" but has a free-string `action` and nullable target, so
   reuse it, no migration: write `api_key.self_create` and `api_key.self_revoke` with `target_tenant_id` = caller
   tenant and `correlation_id_var.get()`, on 201/200 only (same write-on-success rule, including the already-revoked
   200 no-op, matching `routers/tenants.py`). The `self_` prefix distinguishes tenant-initiated from operator-
   initiated actions since the table has no actor column. No key id, key, or hash in the row. Disclosed: the
   operator-only `/settings/audit-log` page will now show tenant self-service rows too; that is intended (the
   operator sees tenant key changes), and no tenant-facing audit view is added. Update ADMIN-002's wording/README
   where it says "operator action" only if it would now be false (one-line note, not a rename).
8. **One-time reveal.** `POST /me/api-keys` returns the raw key once in the 201 body (same contract as
   `TenantCreateResponse.api_key`); add `Cache-Control: no-store` on that response. dashboard-web renders the
   existing `_one_time_reveal.html` partial (label "API key", name = short key id/created time, continue link back
   to "My API Keys") -- no second template, and the raw key is not stored in `SessionStore`, logs, URLs or
   redirects (render directly from the POST response, no redirect-with-key). The list and revoke responses are
   metadata only (`id`, `created_at`, `revoked_at`, `current`).
9. **Revoked keys in the list.** Show them (metadata, greyed), matching the operator view; no deletion.
10. **Cap on active keys / rate limit on minting.** Default: none. Authenticated, tenant-scoped, same exposure as the
    operator path, and the platform has no rate-limiting anywhere (YAGNI, matches ADMIN-004's reasoning). Revisit
    with a real abuse trigger.
11. **Positioning.** Page and copy describe keys as validation-run credentials only (the existing partial text
    already does); no prediction/signal/forecast wording.

## Stories in scope, in execution order

1. **ADMIN-005** — one story; suggested internal order (Tech Lead may split into tickets):
   a. `gateway-api`: extract `mint_api_key` helper from `provision()` (no behavior change); `get_authenticated_key`
      dependency; atomic guarded-revoke repository method (Postgres + SQLite + interface + test fakes).
   b. `gateway-api`: new router `me_api_keys.py` -- `GET /me/api-keys`, `POST /me/api-keys` (201, no-store),
      `POST /me/api-keys/{key_id}/revoke` (200 / 404 / 409 own-key / 409 last-active-key), audit rows, README route
      docs. Why before dashboard-web: dashboard-web depends on this contract.
   c. `dashboard-web`: tenant-session-gated "My API Keys" page (`DownstreamHeadersDep`, not the operator session),
      create via the shared reveal partial, revoke as an HTMX row fragment following the `_tenant_row.html`
      precedent, revoke control disabled for the current key, nav link, README.
   d. Docs: backlog ADMIN-005 status in place (with the disclosed AC amendment and `mint_api_key` extraction),
      `docs/tickets/README.md` Sprint 64 section, both service READMEs.

## Binding constraints carried into tickets

- Lockout guards are server-side in `gateway-api`; the UI disabling is a convenience, not the control.
- One minting implementation (CLI/operator/self-service), one revocation primitive family; operator revoke behavior
  unchanged.
- No new tables, no migration, no pending-rotation state, no key expiry/scheduled rotation, no email/webhook
  notification, no "rotate" combined endpoint.
- Boundary rules: dashboard-web talks to gateway-api over HTTP only; no raw key persisted outside the existing
  in-memory session store.

## Stories explicitly deferred

- Operator "mint key for existing tenant" recovery endpoint: not in backlog, not pulled in (would need the Product
  Owner). The server-side last-active-key guard is what makes it unnecessary for this story.
- Tenant-facing view of their own rotation history, key expiry, per-tenant key caps: not in AC, YAGNI.
- `RPT-002`, other open Epic A/B/D stories, Sprint 62 matview-lag copy follow-up, `DBOPT-*` follow-ups: not in this sprint.

## Definition of done

- ADMIN-005 acceptance criteria checked in `docs/tickets/` ticket(s), with the two disclosed amendments (hard block
  replaces warn-before-revoke; `mint_api_key` extraction) recorded in the backlog entry.
- Tests: gateway-api and dashboard-web suites green. Covered: mint (reveal once, key authenticates, no-store header);
  list never exposes hash/raw key and marks `current`; revoke other key succeeds and the revoked key gets 401 next
  request; revoke own key 409; revoke last active key 409; mutual-revoke race; cross-tenant list/revoke (404);
  already-revoked 200 no-op; audit rows written on 201/200 only with no secret; `provision()` unchanged; dashboard
  page gated by tenant session (operator session cannot satisfy it, and vice versa), reveal partial reused, current
  key's revoke control disabled.
- Positioning grep over every touched file and new copy.
- Docs as part of the work: `services/gateway-api/README.md` (routes), `services/dashboard-web/README.md`,
  `docs/tickets/README.md`, backlog status.
- QA gate (mandatory): Tech Lead raises the `qa` agent (`/qa-validation`) after tickets are done, against the real
  rebuilt `naive-first-*` containers (confirm images are not stale; no host-run scripts, which hit a stale SQLite
  copy): through the UI, mint a second key, log out/in with it, revoke the first, confirm the first returns 401 and
  the new one works; attempt to revoke the in-use key and the last active key via the gateway (expect 409);
  cross-tenant attempt (404); operator audit-log page shows the `api_key.self_*` rows without any secret. QA
  fixtures additive only, named "QA64 ...", left in place, never touching audit-log rows or existing data. QA must
  not revoke keys of existing tenants/pilots (use a fresh QA tenant).

## Next (not this sprint)

RPT-002 (then its PDF extension), optional dashboard-web PDF download link, Sprint 62 matview-lag copy follow-up.
