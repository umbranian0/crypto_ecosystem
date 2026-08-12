# INF-016: single source of the `alembic upgrade head` invocation for
# validation-service / gateway-api, run from the host against the
# Compose-published Postgres port (not from inside a container).
#
# Always connects as `naive_first` (migration-time, superuser/schema-owner,
# INF-014) -- never `naive_first_app` (runtime-only, no CREATE/ownership
# privileges, would fail at the first CREATE TABLE).
#
# Usage: infra/migrate.ps1 -Service validation-service|gateway-api|both
# Defaults to `both` if -Service is not given.

param(
    [ValidateSet("validation-service", "gateway-api", "both")]
    [string]$Service = "both"
)

$ErrorActionPreference = "Stop"

$pgUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "naive_first" }
$pgPassword = if ($env:POSTGRES_PASSWORD) { $env:POSTGRES_PASSWORD } else { "naive_first_dev_password" }
$pgPort = if ($env:POSTGRES_PORT) { $env:POSTGRES_PORT } else { "5432" }
$pgDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "naive_first" }

$repoRoot = Split-Path -Parent $PSScriptRoot

function Invoke-Migration {
    param([string]$Svc)

    $svcDir = Join-Path $repoRoot "services\$Svc"
    $venvPython = Join-Path $svcDir ".venv\Scripts\python.exe"

    if (-not (Test-Path $venvPython)) {
        Write-Error "ERROR: $svcDir\.venv not found (or missing Scripts\python.exe). Create it first, e.g.: cd services\$Svc; uv sync"
        exit 1
    }

    Write-Host "==> Running 'alembic upgrade head' for $Svc"

    # postgresql+psycopg:// (not bare postgresql://): both services'
    # pyproject.toml declare psycopg v3 as their Postgres driver, not
    # psycopg2, and SQLAlchemy's default dialect for a bare "postgresql://"
    # scheme resolves to psycopg2, which isn't installed. Each service's own
    # app code (dependencies/repositories.py) already rewrites an incoming
    # "postgresql://" DATABASE_URL to "postgresql+psycopg://" before use;
    # alembic's env.py does not do that rewrite, so this script supplies the
    # explicit scheme directly.
    $env:DATABASE_URL = "postgresql+psycopg://${pgUser}:${pgPassword}@localhost:${pgPort}/${pgDb}"
    try {
        Push-Location $svcDir
        & $venvPython -m alembic upgrade head
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
        Remove-Item Env:\DATABASE_URL -ErrorAction SilentlyContinue
    }

    if ($exitCode -ne 0) {
        Write-Error "ERROR: alembic upgrade head failed for $Svc (exit code $exitCode)"
        exit $exitCode
    }
}

switch ($Service) {
    "both" {
        Invoke-Migration -Svc "validation-service"
        Invoke-Migration -Svc "gateway-api"
    }
    default {
        Invoke-Migration -Svc $Service
    }
}
