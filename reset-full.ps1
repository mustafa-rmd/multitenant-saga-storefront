# Post-reset bootstrap: wait for Postgres, then migrate + create the
# platform admin as the `postgres` superuser. Called by `make reset-full`
# after the volumes have been wiped and the stack brought back up.
#
# Migrate needs a superuser because it installs RLS policies and runs DDL
# that app_user / app_admin don't have rights for. The bootstrap step
# only creates a single Django superuser; every other piece of state
# (tenants, gateway configs, customers, products) is created via the
# admin REST API.

$ErrorActionPreference = 'Stop'

$PY = '.\.venv\Scripts\python.exe'
$SUPERUSER_DB_URL = 'postgres://postgres:postgres@localhost:5432/acme_cart'

# ---------------------------------------------------------------------------
# Wait for Postgres to become healthy. The compose healthcheck runs every 5s
# with up to 10 retries, so 90s is a safe ceiling for cold starts.
# ---------------------------------------------------------------------------
Write-Host 'Waiting for Postgres to become healthy...' -ForegroundColor Cyan

$deadline = (Get-Date).AddSeconds(90)
while ($true) {
    $status = (docker inspect --format='{{.State.Health.Status}}' postgres 2>$null)
    if ($status -eq 'healthy') {
        Write-Host '  postgres: healthy' -ForegroundColor Green
        break
    }
    if ((Get-Date) -gt $deadline) {
        Write-Host "  postgres did not become healthy within 90s (last status: $status)" -ForegroundColor Red
        exit 1
    }
    Start-Sleep -Seconds 1
}

# ---------------------------------------------------------------------------
# Migrate + bootstrap under a one-shot superuser DATABASE_URL. We scope the
# env var to this process only -- not Set-Item -- so the user's shell is
# unchanged after this script exits.
# ---------------------------------------------------------------------------
$env:DATABASE_URL = $SUPERUSER_DB_URL
try {
    Write-Host 'Running migrations...' -ForegroundColor Cyan
    & $PY manage.py migrate
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host 'Creating platform admin...' -ForegroundColor Cyan
    & $PY manage.py shell -c "exec(open('scripts/bootstrap.py').read())"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host 'Reset complete. Restart the app processes so they reconnect:' -ForegroundColor Green
Write-Host '  make run-all' -ForegroundColor Yellow
Write-Host ''
Write-Host 'Next: log in as platform@acme.test (or your PLATFORM_ADMIN_EMAIL)' -ForegroundColor Cyan
Write-Host 'and provision tenants/gateway configs/customers via the admin REST API.' -ForegroundColor Cyan
