#!/bin/sh
# INF-016: single source of the `alembic upgrade head` invocation for
# validation-service / gateway-api, run from the host against the
# Compose-published Postgres port (not from inside a container).
#
# Always connects as `naive_first` (migration-time, superuser/schema-owner,
# INF-014) -- never `naive_first_app` (runtime-only, no CREATE/ownership
# privileges, would fail at the first CREATE TABLE).
#
# Usage: infra/migrate.sh [validation-service|gateway-api|both]
# Defaults to `both` if no argument is given.
set -e

service="${1:-both}"

POSTGRES_USER="${POSTGRES_USER:-naive_first}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-naive_first_dev_password}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-naive_first}"

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

migrate_one() {
    svc="$1"
    svc_dir="$repo_root/services/$svc"
    venv_python="$svc_dir/.venv/bin/python"

    if [ ! -x "$venv_python" ]; then
        echo "ERROR: $svc_dir/.venv not found (or missing bin/python)." >&2
        echo "Create it first, e.g.: cd services/$svc && uv sync" >&2
        exit 1
    fi

    echo "==> Running 'alembic upgrade head' for $svc"
    (
        cd "$svc_dir"
        # postgresql+psycopg:// (not bare postgresql://): both services'
        # pyproject.toml declare psycopg v3 as their Postgres driver, not
        # psycopg2, and SQLAlchemy's default dialect for a bare
        # "postgresql://" scheme resolves to psycopg2, which isn't
        # installed. Each service's own app code (dependencies/repositories.py)
        # already rewrites an incoming "postgresql://" DATABASE_URL to
        # "postgresql+psycopg://" before use; alembic's env.py does not do
        # that rewrite, so this script supplies the explicit scheme directly.
        DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT}/${POSTGRES_DB}" \
            "$venv_python" -m alembic upgrade head
    )
}

case "$service" in
    validation-service|gateway-api)
        migrate_one "$service"
        ;;
    both)
        migrate_one "validation-service"
        migrate_one "gateway-api"
        ;;
    *)
        echo "ERROR: unknown service '$service' (expected validation-service, gateway-api, or both)" >&2
        exit 1
        ;;
esac
