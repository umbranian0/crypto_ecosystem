# SETUP-010 — `gateway-api`: platform-operator authentication for cross-tenant admin endpoints

**Sprint**: 29. **Module**: `services/gateway-api`. **Status**: done. **Priority**: Must.
**Depends on**: none. **Blocks**: `SETUP-011` (next sprint, not in scope here).
**Can run in parallel with**: `SETUP-001`/`SETUP-002` (disjoint areas of `gateway-api`) and `SETUP-030`.

## Analysis — discovered-done finding, read before assuming this is greenfield

`GW-021` (Sprint 18, `docs/tickets/GW-021.md`) already shipped `get_authenticated_operator`
(`src/app/dependencies/operator_auth.py`) as an explicit, disclosed **minimal slice** of this exact
story — same `OPERATOR_TOKEN` env var, same `hashlib.sha256` hash-to-hash discipline, same structural
separation from `get_authenticated_tenant` (no shared function/header/repository lookup), and it is
already the auth gate on a real route (`GET /ingestion/connectors/credentials-status`). Read directly
(`operator_auth.py`, `tests/test_operator_auth.py`, `services/gateway-api/README.md`'s "Operator
authentication (GW-021...)" section) before writing this ticket, per the requester's explicit
instruction not to duplicate work.

**Most of `SETUP-010`'s AC is already satisfied by GW-021, confirmed by reading the code, not
assumed:**
- ✅ A new operator credential exists out of band from tenant API keys, `OPERATOR_TOKEN`, hashed with
  `hashlib.sha256`, checked by `get_authenticated_operator`, structurally separate from
  `get_authenticated_tenant`.
- ✅ `gateway-api`'s README documents it as a disclosed, narrow, single-shared-secret stopgap, and
  names the concrete revisit trigger (a second real human operator needing their own credential).
- ⚠️ **`SETUP-011`'s `/tenants` endpoints don't exist yet** — correctly deferred to next sprint,
  matching this sprint's own explicit scope decision; not a gap in this ticket.

**One real, genuine gap found, not already closed by GW-021** — this ticket's actual scope:
`SETUP-010`'s AC explicitly requires "a test proves a real tenant's own API key, presented to it, is
rejected (`403`)." `GW-021`'s existing `test_tenant_api_key_presented_as_operator_token_is_rejected`
proves the tenant key is rejected, but with status `401`, not `403` — because
`get_authenticated_operator` treats a tenant's own key exactly like any other wrong/unknown string
(hash mismatch against `OPERATOR_TOKEN`) rather than recognizing it *as* a valid-but-wrong-credential-
type presentation. `401` ("who are you") and `403` ("I know who you are, and you may not do this") are
not interchangeable outcomes, and the sprint's own DoD names `403` specifically for this exact
scenario — this is a real, disclosed gap, not a nitpick: it means today's dependency cannot
structurally distinguish "no credential presented"/"garbage token" from "a real, valid tenant
credential presented to the wrong gate," which is exactly the information a future audit-log/
diagnostics consumer (`SETUP-021`) would want to tell apart.

## Design

**Pattern**: DI (FastAPI `Depends()`), same shape GW-021 already established — this ticket extends
that dependency, it does not replace it.

**Files touched** (scoped to `services/gateway-api` only):
- `src/app/dependencies/operator_auth.py` — `get_authenticated_operator` gains one additional check,
  run only on a hash-mismatch (i.e. after the existing missing-header/unset-`OPERATOR_TOKEN` `401`
  paths, and only when the presented value does *not* match `OPERATOR_TOKEN`'s hash): look up the
  presented value's hash against `ApiKeyRepository.get_by_hash` (the exact same tenant-key lookup
  `get_authenticated_tenant` already uses in `auth.py`, imported, not reimplemented). If a real,
  non-revoked tenant `ApiKeyRecord` resolves, raise `403` instead of `401` — the credential is real,
  just the wrong kind for this gate. If nothing resolves (truly unknown value), the existing `401`
  behavior is unchanged.
- **This does touch the repository layer**, which GW-021's own docstring states this dependency
  "never touches ... at all" — that line in the docstring must be corrected as part of this ticket
  (not left contradicting the new code), and the change is scoped narrowly: the repository is
  consulted **only** on the failure path, after the primary hash comparison already failed, purely to
  decide which 4xx to return — it is never consulted to *grant* access; `OPERATOR_TOKEN`'s hash match
  remains the only path to `200`. `get_authenticated_operator`'s signature grows one new parameter,
  `api_key_repo: ApiKeyRepositoryDep` (the existing DI-injectable provider `auth.py`/`operator.py`
  already use), so this stays testable with the same fake-repository pattern `test_operator_auth.py`
  already uses.

**DRY check note** (grepped `src/app/dependencies/` and `src/app/repositories/` before writing this
ticket): `ApiKeyRepository.get_by_hash` and its SQLite/Postgres implementations already exist (`GW-004`/
`GW-012`) and are the exact lookup `get_authenticated_tenant` performs — reused directly here, not
reimplemented. No second hashing mechanism, no second repository method.

## Implementation acceptance criteria

- [x] `get_authenticated_operator` returns `403` (not `401`) when the presented `X-Operator-Token`
  value fails the `OPERATOR_TOKEN` hash comparison but *does* resolve to a real, non-revoked tenant
  `ApiKeyRecord` via `ApiKeyRepository.get_by_hash`.
- [x] All of GW-021's existing `401` cases (missing header, unset/empty `OPERATOR_TOKEN`, a value that
  resolves to no tenant key at all) are unchanged — still `401`.
- [x] A revoked tenant key presented as the operator token still returns `401` (revoked ≠ "a real
  credential of the wrong type" for this purpose — matches `get_authenticated_tenant`'s own treatment
  of a revoked key as unauthenticated, not merely forbidden).
- [x] `operator_auth.py`'s module docstring is corrected — it no longer claims this dependency "never
  touches [the API-key repository] at all."

## Test acceptance criteria

- [x] `test_tenant_api_key_presented_as_operator_token_is_rejected` (existing, GW-021) is updated to
  assert `403`, not `401` — the exact case `SETUP-010`'s own AC names.
- [x] New test: a revoked tenant key presented as the operator token still returns `401`.
- [x] New test: an unknown/garbage value (resolves to no tenant key at all) still returns `401`
  (regression guard on GW-021's existing behavior).
- [x] `test_no_raw_operator_token_appears_in_any_captured_log_record` (existing) re-passes unmodified —
  this ticket adds no new log call, so no new secret-leakage surface.
- [x] `uv run pytest -q` run in full, zero regressions outside the one intentional status-code change.

## Review acceptance criteria (Tech Lead verifies personally)

- Confirms the repository lookup is reachable **only** on the failure branch (after the primary hash
  comparison), never contributing to a `200` — reads the function body directly, not just the tests.
- Confirms `OPERATOR_TOKEN`'s hash-to-hash comparison remains the sole grant path — no weakening of
  the existing auth boundary while adding the `403` distinction.
- Confirms the corrected docstring accurately describes the new, narrower "consulted only to
  classify a rejection" relationship to the repository — not silently left stale.
- Re-runs `gateway-api`'s full suite, confirms zero regressions beyond the one intentional
  `401`→`403` test update.

## Documentation acceptance criteria

- [x] `services/gateway-api/README.md`'s existing "Operator authentication (GW-021...)" section is
  extended (not duplicated into a second section) to state the `403`-for-a-real-tenant-key behavior
  this ticket adds, and to note this is `SETUP-010`'s own closing of a gap GW-021's minimal slice
  left open (status-code precision on the cross-boundary case), citing this ticket.
- [x] `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-010` entry's acceptance-criteria
  boxes are checked and its status marked done, with a note that `GW-021` (Sprint 18) had already
  satisfied most of this story's scope and this ticket closed the one remaining gap (401→403
  precision) rather than rebuilding the mechanism from scratch.
