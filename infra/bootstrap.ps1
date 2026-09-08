# INF-015: first-boot bootstrap -- orchestrates the hand-run sequence
# documented in infra/README.md into one script. Owns orchestration only
# (compose up, health-wait, ordering, final app container start/restart); it
# delegates the one piece of logic that would otherwise be duplicated -- the
# `alembic upgrade head` invocation -- entirely to INF-016's infra/migrate.ps1.
#
# Role note: migrations (step 3, delegated to infra/migrate.ps1) run as the
# migration-time role `naive_first` (INF-014); the app containers this
# script starts in step 4 connect at runtime as `naive_first_app` via
# infra/docker-compose.yml's own env-var wiring -- nothing in this script's
# own body needs to name either role explicitly.
#
# Usage: infra/bootstrap.ps1 (run from anywhere; resolves paths relative to
# this script's own location, not the caller's cwd).

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$composeFile = Join-Path $scriptDir "docker-compose.yml"

function Fail-Step {
    param([string]$Step)
    Write-Error "ERROR: bootstrap failed at step: $Step"
    exit 1
}

Write-Host "==> Step 1/6: starting postgres, redis"
docker compose -f $composeFile up -d postgres redis
if ($LASTEXITCODE -ne 0) { Fail-Step "step 1 (docker compose up postgres redis)" }

Write-Host "==> Step 2/6: waiting for postgres to become healthy"
$attempt = 0
$maxAttempts = 30
$status = ""
while ($true) {
    $status = (docker inspect --format '{{.State.Health.Status}}' naive-first-postgres 2>$null)
    if ($status -eq "healthy") {
        Write-Host "    postgres is healthy"
        break
    }
    $attempt++
    if ($attempt -ge $maxAttempts) {
        Fail-Step "step 2 (postgres did not become healthy within $maxAttempts attempts; last status: '$status')"
    }
    Start-Sleep -Seconds 2
}

Write-Host "==> Step 3/6: running migrations (delegated to infra/migrate.ps1 -Service both)"
& (Join-Path $scriptDir "migrate.ps1") -Service both
if ($LASTEXITCODE -ne 0) { Fail-Step "step 3 (infra/migrate.ps1 -Service both -- see output above for which service's migration failed)" }

Write-Host "==> Step 4/6: starting validation-service, gateway-api"
docker compose -f $composeFile up -d --build validation-service gateway-api
if ($LASTEXITCODE -ne 0) { Fail-Step "step 4 (docker compose up --build validation-service gateway-api)" }

# SETUP-004: closes the "one command" loop -- starts dashboard-web via
# Compose (depends on SETUP-030's compose entry existing) and opens/prints
# the wizard URL. Idempotent by construction: `docker compose up` is already
# idempotent, migrations are already idempotent (INF-016, step 3 above), and
# SETUP-003's own /setup -> /login redirect on an already-initialized system
# means re-running this step against an already-initialized stack lands the
# operator on /login, not a duplicate-tenant error -- no new idempotency
# logic is added here.
Write-Host "==> Step 5/6: starting dashboard-web"
docker compose -f $composeFile up -d --build dashboard-web
if ($LASTEXITCODE -ne 0) { Fail-Step "step 5 (docker compose up --build dashboard-web)" }

$dashboardPort = $env:DASHBOARD_WEB_PORT
if ([string]::IsNullOrWhiteSpace($dashboardPort)) { $dashboardPort = "8004" }
$wizardUrl = "http://localhost:$dashboardPort/"

Write-Host "==> Step 6/6: opening the setup wizard"
$opened = $false
try {
    Start-Process $wizardUrl -ErrorAction Stop
    $opened = $true
} catch {
    $opened = $false
}
if (-not $opened) {
    # Headless environment (e.g. CI) with no way to launch a browser --
    # print the URL instead of failing. Never a non-zero exit purely because
    # no browser could be opened.
    Write-Host "    Could not open a browser automatically. Open this URL manually:"
}
Write-Host "    $wizardUrl"
Write-Host ""

# Demoted, not deleted (INF-015's own "demote, don't delete" convention,
# unchanged text from before SETUP-004): the non-interactive/CI-friendly
# alternative to the browser wizard above, for an operator who prefers a
# terminal/script-driven first-tenant creation over the browser flow.
Write-Host "Non-interactive alternative -- provision a tenant from the command line (mints a one-time-visible API key, not auto-run by this script):"
Write-Host ""
Write-Host '  docker compose -f infra/docker-compose.yml exec gateway-api .venv/bin/python scripts/provision_tenant.py --name "Your Tenant Name"'
Write-Host ""
