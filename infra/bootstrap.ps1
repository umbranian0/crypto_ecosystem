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

Write-Host "==> Step 1/5: starting postgres, redis"
docker compose -f $composeFile up -d postgres redis
if ($LASTEXITCODE -ne 0) { Fail-Step "step 1 (docker compose up postgres redis)" }

Write-Host "==> Step 2/5: waiting for postgres to become healthy"
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

Write-Host "==> Step 3/5: running migrations (delegated to infra/migrate.ps1 -Service both)"
& (Join-Path $scriptDir "migrate.ps1") -Service both
if ($LASTEXITCODE -ne 0) { Fail-Step "step 3 (infra/migrate.ps1 -Service both -- see output above for which service's migration failed)" }

Write-Host "==> Step 4/5: starting validation-service, gateway-api"
docker compose -f $composeFile up -d --build validation-service gateway-api
if ($LASTEXITCODE -ne 0) { Fail-Step "step 4 (docker compose up --build validation-service gateway-api)" }

Write-Host "==> Step 5/5: bootstrap complete"
Write-Host ""
Write-Host "Next step -- provision a tenant (mints a one-time-visible API key, not auto-run by this script):"
Write-Host ""
Write-Host '  docker compose -f infra/docker-compose.yml exec gateway-api .venv/bin/python scripts/provision_tenant.py --name "Your Tenant Name"'
Write-Host ""
