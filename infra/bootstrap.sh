#!/bin/sh
# INF-015: first-boot bootstrap -- orchestrates the hand-run sequence
# documented in infra/README.md into one script. Owns orchestration only
# (compose up, health-wait, ordering, final app container start/restart); it
# delegates the one piece of logic that would otherwise be duplicated -- the
# `alembic upgrade head` invocation -- entirely to INF-016's infra/migrate.sh.
#
# Role note: migrations (step 3, delegated to infra/migrate.sh) run as the
# migration-time role `naive_first` (INF-014); the app containers this
# script starts in step 4 connect at runtime as `naive_first_app` via
# infra/docker-compose.yml's own env-var wiring -- nothing in this script's
# own body needs to name either role explicitly.
#
# Usage: infra/bootstrap.sh (run from anywhere; resolves paths relative to
# this script's own location, not the caller's cwd).
set -e

script_dir="$(cd "$(dirname "$0")" && pwd)"
compose_file="$script_dir/docker-compose.yml"

fail() {
    echo "ERROR: bootstrap failed at step: $1" >&2
    exit 1
}

echo "==> Step 1/6: starting postgres, redis"
docker compose -f "$compose_file" up -d postgres redis || fail "step 1 (docker compose up postgres redis)"

echo "==> Step 2/6: waiting for postgres to become healthy"
attempt=0
max_attempts=30
while :; do
    status="$(docker inspect --format '{{.State.Health.Status}}' naive-first-postgres 2>/dev/null || true)"
    if [ "$status" = "healthy" ]; then
        echo "    postgres is healthy"
        break
    fi
    attempt=$((attempt + 1))
    if [ "$attempt" -ge "$max_attempts" ]; then
        fail "step 2 (postgres did not become healthy within ${max_attempts} attempts; last status: '${status}')"
    fi
    sleep 2
done

echo "==> Step 3/6: running migrations (delegated to infra/migrate.sh both)"
"$script_dir/migrate.sh" both || fail "step 3 (infra/migrate.sh both -- see output above for which service's migration failed)"

echo "==> Step 4/6: starting validation-service, gateway-api"
docker compose -f "$compose_file" up -d --build validation-service gateway-api || fail "step 4 (docker compose up --build validation-service gateway-api)"

# SETUP-004: closes the "one command" loop -- starts dashboard-web via
# Compose (depends on SETUP-030's compose entry existing) and opens/prints
# the wizard URL. Idempotent by construction: `docker compose up` is already
# idempotent, migrations are already idempotent (INF-016, step 3 above), and
# SETUP-003's own /setup -> /login redirect on an already-initialized system
# means re-running this step against an already-initialized stack lands the
# operator on /login, not a duplicate-tenant error -- no new idempotency
# logic is added here.
echo "==> Step 5/6: starting dashboard-web"
docker compose -f "$compose_file" up -d --build dashboard-web || fail "step 5 (docker compose up --build dashboard-web)"

dashboard_port="${DASHBOARD_WEB_PORT:-8004}"
wizard_url="http://localhost:${dashboard_port}/"

echo "==> Step 6/6: opening the setup wizard"
opened=0
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$wizard_url" >/dev/null 2>&1 && opened=1
elif command -v open >/dev/null 2>&1; then
    open "$wizard_url" >/dev/null 2>&1 && opened=1
fi
if [ "$opened" -eq 0 ]; then
    # Headless environment (e.g. CI) with no way to launch a browser --
    # print the URL instead of failing. Never a non-zero exit purely because
    # no browser could be opened.
    echo "    Could not open a browser automatically. Open this URL manually:"
fi
echo "    $wizard_url"
echo ""

# Demoted, not deleted (INF-015's own "demote, don't delete" convention,
# unchanged text from before SETUP-004): the non-interactive/CI-friendly
# alternative to the browser wizard above, for an operator who prefers a
# terminal/script-driven first-tenant creation over the browser flow.
echo "Non-interactive alternative -- provision a tenant from the command line (mints a one-time-visible API key, not auto-run by this script):"
echo ""
echo "  docker compose -f infra/docker-compose.yml exec gateway-api .venv/bin/python scripts/provision_tenant.py --name \"Your Tenant Name\""
echo ""
