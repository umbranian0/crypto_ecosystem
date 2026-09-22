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
$repoRoot = Split-Path $PSScriptRoot -Parent
$composeFile = Join-Path $scriptDir "docker-compose.yml"

function Fail-Step {
    param([string]$Step)
    Write-Error "ERROR: bootstrap failed at step: $Step"
    exit 1
}

# BOOT-002: single reusable poll used for validation-service, gateway-api, and
# dashboard-web below (step 7) -- mirrors step 3's postgres wait-loop shape
# ($attempt/$maxAttempts/Start-Sleep), but over HTTP GET .../health instead of
# `docker inspect`. A connection failure/timeout and a non-200 response are
# both treated as "not yet healthy" and retried -- the try/catch below keeps
# a per-attempt failure from tripping this script's own top-level
# $ErrorActionPreference = "Stop".
function Wait-ForServiceHealth {
    param(
        [string]$Name,
        [string]$Port
    )
    $attempt = 0
    $maxAttempts = 30
    $lastStatus = "unreachable"
    while ($true) {
        $healthy = $false
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:$Port/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            $lastStatus = [string]$response.StatusCode
            if ($response.StatusCode -eq 200) { $healthy = $true }
        } catch {
            # Invoke-WebRequest throws on a non-2xx/3xx response too (not just
            # a connection failure) -- recover the real status code from the
            # exception when the server did respond, so a real 503 is
            # reported as "503", not lumped in with "unreachable".
            if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
                $lastStatus = [string][int]$_.Exception.Response.StatusCode
            } else {
                $lastStatus = "unreachable"
            }
            $healthy = $false
        }
        if ($healthy) {
            Write-Host "    $Name is healthy"
            return
        }
        $attempt++
        if ($attempt -ge $maxAttempts) {
            Fail-Step "step 7 ($Name did not become healthy within $maxAttempts attempts; last status: '$lastStatus')"
        }
        Start-Sleep -Seconds 2
    }
}

# BOOT-002 (extended): same stale-image warning bootstrap.sh prints, same structure.
# "Healthy" only means the process answers; it does not mean the process is running
# the code you are looking at. See bootstrap.sh's copy of this note for the incident
# that prompted it.
function Warn-IfImagePredatesSource {
    param([string]$Name)

    $created = docker image inspect "infra-$Name" --format '{{.Created}}' 2>$null
    if (-not $created) { return }   # never built locally; nothing to compare against
    try { $imageTime = [datetime]::Parse($created) } catch { return }

    $sourceDirs = @(
        (Join-Path $repoRoot "services/$Name/src"),
        (Join-Path $repoRoot "libs")
    ) | Where-Object { Test-Path $_ }
    if (-not $sourceDirs) { return }

    $newer = Get-ChildItem -Path $sourceDirs -Recurse -File -Filter *.py -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt $imageTime } | Select-Object -First 1
    if ($newer) {
        $ageDays = [int]((Get-Date) - $imageTime).TotalDays
        Write-Host "    WARNING: $Name's image was built $ageDays day(s) ago, but its source has"
        Write-Host "      changed since -- you are testing older code than you have checked out."
        Write-Host "      Rebuild with: docker compose -f $composeFile up -d --build $Name"
    }
}

Write-Host "==> Step 1/8: checking for infra/.env"
if (-not (Test-Path (Join-Path $scriptDir ".env"))) {
    try {
        Copy-Item (Join-Path $scriptDir ".env.example") (Join-Path $scriptDir ".env")
    } catch {
        Fail-Step "step 1 (copying .env.example to .env)"
    }
    Write-Host "    created $(Join-Path $scriptDir '.env') from .env.example"
    Write-Host "    Change these disclosed insecure dev-only defaults before any non-local deployment:"
    Write-Host "    OPERATOR_TOKEN, POSTGRES_PASSWORD, POSTGRES_APP_PASSWORD, INGESTION_CREDENTIAL_ENCRYPTION_KEY, INGESTION_INTERNAL_TOKEN"
} else {
    # BOOT-003: same drift warning bootstrap.sh prints, same structure -- an .env that
    # predates a variable added to .env.example since surfaces today only as a confusing
    # runtime failure. Variable NAMES only; the operator's file is never rewritten.
    $envKeyPattern = '^[A-Za-z_][A-Za-z0-9_]*='
    $exampleKeys = Select-String -Path (Join-Path $scriptDir ".env.example") -Pattern $envKeyPattern |
        ForEach-Object { ($_.Line -split '=', 2)[0] } | Sort-Object -Unique
    $currentKeys = Select-String -Path (Join-Path $scriptDir ".env") -Pattern $envKeyPattern |
        ForEach-Object { ($_.Line -split '=', 2)[0] } | Sort-Object -Unique
    $missingKeys = @($exampleKeys | Where-Object { $currentKeys -notcontains $_ })
    if ($missingKeys.Count -gt 0) {
        Write-Host "    WARNING: infra/.env is missing $($missingKeys.Count) key(s) that infra/.env.example defines:"
        $missingKeys | ForEach-Object { Write-Host "      $_" }
        Write-Host "    Not added for you -- your .env is never rewritten. Some may be intentionally"
        Write-Host "    unset; a service that needs one will fail at startup or fall back to a default."
    }
}

Write-Host "==> Step 2/8: starting postgres, redis"
docker compose -f $composeFile up -d postgres redis
if ($LASTEXITCODE -ne 0) { Fail-Step "step 2 (docker compose up postgres redis)" }

Write-Host "==> Step 3/8: waiting for postgres to become healthy"
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
        Fail-Step "step 3 (postgres did not become healthy within $maxAttempts attempts; last status: '$status')"
    }
    Start-Sleep -Seconds 2
}

Write-Host "==> Step 4/8: running migrations (delegated to infra/migrate.ps1 -Service both)"
& (Join-Path $scriptDir "migrate.ps1") -Service both
if ($LASTEXITCODE -ne 0) { Fail-Step "step 4 (infra/migrate.ps1 -Service both -- see output above for which service's migration failed)" }

Write-Host "==> Step 5/8: starting validation-service, gateway-api"
docker compose -f $composeFile up -d --build validation-service gateway-api
if ($LASTEXITCODE -ne 0) { Fail-Step "step 5 (docker compose up --build validation-service gateway-api)" }

# SETUP-004: closes the "one command" loop -- starts dashboard-web via
# Compose (depends on SETUP-030's compose entry existing) and opens/prints
# the wizard URL. Idempotent by construction: `docker compose up` is already
# idempotent, migrations are already idempotent (INF-016, step 3 above), and
# SETUP-003's own /setup -> /login redirect on an already-initialized system
# means re-running this step against an already-initialized stack lands the
# operator on /login, not a duplicate-tenant error -- no new idempotency
# logic is added here.
Write-Host "==> Step 6/8: starting dashboard-web"
docker compose -f $composeFile up -d --build dashboard-web
if ($LASTEXITCODE -ne 0) { Fail-Step "step 6 (docker compose up --build dashboard-web)" }

$validationServicePort = $env:VALIDATION_SERVICE_PORT
if ([string]::IsNullOrWhiteSpace($validationServicePort)) { $validationServicePort = "8001" }
$gatewayApiPort = $env:GATEWAY_API_PORT
if ([string]::IsNullOrWhiteSpace($gatewayApiPort)) { $gatewayApiPort = "8000" }
$dashboardPort = $env:DASHBOARD_WEB_PORT
if ([string]::IsNullOrWhiteSpace($dashboardPort)) { $dashboardPort = "8004" }
$wizardUrl = "http://localhost:$dashboardPort/"

# BOOT-002: dashboard-web is polled last -- its own /health already makes a
# real call to gateway-api's /health (DASH-008), so confirming
# validation-service/gateway-api first gives the clearest failure attribution
# if something upstream is broken.
Write-Host "==> Step 7/8: verifying validation-service, gateway-api, dashboard-web are healthy"
Wait-ForServiceHealth -Name "validation-service" -Port $validationServicePort
Wait-ForServiceHealth -Name "gateway-api" -Port $gatewayApiPort
Wait-ForServiceHealth -Name "dashboard-web" -Port $dashboardPort
Write-Host "    all services healthy"
Warn-IfImagePredatesSource -Name "validation-service"
Warn-IfImagePredatesSource -Name "gateway-api"
Warn-IfImagePredatesSource -Name "dashboard-web"

Write-Host "==> Step 8/8: opening the setup wizard"
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
