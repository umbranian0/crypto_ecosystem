"""GW-005: operator/test-fixture tool for provisioning a tenant plus its
first API key. Not a public sign-up flow -- there is no real pilot client
yet (backlog decision 1); this exists so operators (and integration tests)
can create the fixture data GW-006's auth mechanism will need to check
against.

CLI script, not an operator endpoint (Design section, GW-005 ticket): an
endpoint would need its own auth mechanism before GW-006 (the service's
actual auth) exists -- a chicken-and-egg problem a local script run by
whoever already has host access naturally avoids.

Invoked directly against `app.dependencies.repositories`' DI providers
(`get_tenant_repository`/`get_api_key_repository`), the same repositories a
route handler would receive via `Depends()`, just called without going
through FastAPI's request cycle.

Key handling (sprint-05.md's binding, non-negotiable choice): the raw key is
generated with `secrets.token_urlsafe(32)` and hashed with
`hashlib.sha256(...).hexdigest()` before it ever reaches `create_key` --
only the hash is persisted. The raw key is returned by `provision()` and
printed to stdout exactly once, by the CLI wrapper below; it is never
logged, never written to a file, and never appears in any exception message.
"""

from __future__ import annotations

import argparse
import hashlib
import secrets

from app.dependencies.repositories import get_api_key_repository, get_tenant_repository
from app.repositories.interfaces import ApiKeyRepository, TenantRepository, TenantRecord


def provision(
    name: str,
    tenant_repo: TenantRepository,
    api_key_repo: ApiKeyRepository,
) -> tuple[TenantRecord, str]:
    """Creates a tenant and its first API key, returning the tenant record
    and the raw (unhashed) key. Only `api_key_repo.create_key` is given the
    hash; the raw key lives solely in this function's return value and the
    caller's handling of it from there.
    """
    tenant = tenant_repo.create_tenant(name)

    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key_repo.create_key(tenant.id, key_hash)

    return tenant, raw_key


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Provision a tenant and its first API key (operator/test-fixture "
            "tool -- not a public sign-up flow)."
        )
    )
    parser.add_argument("--name", required=True, help="Tenant name")
    args = parser.parse_args()

    tenant, raw_key = provision(args.name, get_tenant_repository(), get_api_key_repository())

    print(f"Tenant created: id={tenant.id} name={tenant.name}")
    print(f"API key (shown once, not recoverable): {raw_key}")


if __name__ == "__main__":
    main()
