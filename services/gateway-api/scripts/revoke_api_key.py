"""GW-010: operator/test-fixture tool for revoking an API key. Not a public
or tenant-self-service endpoint -- there is no HTTP path to reach this
functionality at all (backlog care condition: revocation stays strictly
operator-only). Mirrors `scripts/provision_tenant.py`'s (GW-005) exact shape
and rationale: a standalone CLI script, invoked directly against
`app.dependencies.repositories`'s DI providers, not through FastAPI's request
cycle -- no new authenticated surface is added to this service by this
ticket.

Revoke-by-raw-key (Design section, GW-010 ticket): the operator presents the
raw API key they already have on hand (it was printed once at provisioning
time, GW-005). This script hashes it the same way `auth.py`'s
`get_authenticated_tenant` does (`hashlib.sha256(...).hexdigest()`, reused,
not re-derived -- sprint-05's binding, non-negotiable hashing choice, never
bcrypt/argon2/scrypt) and calls `ApiKeyRepository.get_by_hash(key_hash)`
(already exists, GW-004) to resolve the `tenant_id`/`key_id`, then calls
`ApiKeyRepository.revoke_key(tenant_id, key_id)` (already exists on both
storage backends, GW-004/GW-012). No new repository/interface surface is
added -- both methods this script calls already existed before this ticket.

Idempotency (both backends' `revoke_key` read first, not assumed): `revoke_key`
is a blind, unconditional `UPDATE ... SET revoked_at = now()` with no error on
a no-op match, so calling it a second time against an already-revoked key
would silently overwrite the original `revoked_at` with a new timestamp. This
script avoids that by checking `record.revoked_at` *before* calling
`revoke_key` and short-circuiting to a no-op (returning the already-revoked
record unchanged, preserving the original `revoked_at`) -- graceful, no error,
consistent with `revoke_key`'s own no-error behavior at the repository layer.

The raw key is never printed, logged, or included in any exception message
anywhere in this script -- matching `provision_tenant.py`'s own discipline.
"""

from __future__ import annotations

import argparse
import hashlib

from app.dependencies.repositories import get_api_key_repository
from app.repositories.interfaces import ApiKeyRecord, ApiKeyRepository


class UnknownApiKeyError(Exception):
    """Raised when a presented raw key resolves to no `api_keys` row.

    Deliberately a plain, clear operator-facing message with no raw key
    content and no underlying stack trace surfaced to the operator.
    """


def revoke(raw_key: str, api_key_repo: ApiKeyRepository) -> ApiKeyRecord:
    """Resolves `raw_key` to its `api_keys` row via `get_by_hash` and revokes
    it via `revoke_key`, returning the now-revoked record. Raises
    `UnknownApiKeyError` if no matching key exists. If the resolved record is
    already revoked, this is a no-op that returns the existing record
    unchanged (see module docstring: `revoke_key` itself has no built-in
    idempotency guard, so this function supplies one).
    """
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    record = api_key_repo.get_by_hash(key_hash)

    if record is None:
        raise UnknownApiKeyError("No API key found matching the presented key.")

    if record.revoked_at is not None:
        return record

    api_key_repo.revoke_key(record.tenant_id, record.id)

    revoked_record = api_key_repo.get_by_hash(key_hash)
    assert revoked_record is not None  # revoke_key only sets a column, never deletes the row
    return revoked_record


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Revoke an API key (operator/test-fixture tool -- not a "
            "tenant-self-service mechanism)."
        )
    )
    parser.add_argument("--key", required=True, help="The raw API key to revoke")
    args = parser.parse_args()

    try:
        record = revoke(args.key, get_api_key_repository())
    except UnknownApiKeyError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1) from None

    print(f"Revoked key id={record.id} for tenant_id={record.tenant_id} at {record.revoked_at}")


if __name__ == "__main__":
    main()
