# =====================================================================
# M0 database bootstrap
#
# Starts the PostgreSQL container, waits until healthy, runs Alembic
# migrations, then verifies connectivity from the app.
#
# Prerequisite: Docker Desktop installed AND running (engine up).
#
# Usage (from the repository root):
#   powershell -ExecutionPolicy Bypass -File deploy\setup-db.ps1
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads scripts
# without a BOM using the system ANSI code page (GBK on Chinese Windows),
# which corrupts non-ASCII literals and can even break parsing.
# =====================================================================

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $PSScriptRoot 'docker-compose.yml'
$container = 'sls-postgres'
$venvPython = Join-Path $repoRoot 'backend\.venv\Scripts\python.exe'
$desktopExe = Join-Path ${env:ProgramFiles} 'Docker\Docker\Docker Desktop.exe'

function Write-Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }

function Fail($message, $hint) {
    Write-Host "`n[FAILED] $message" -ForegroundColor Red
    if ($hint) { Write-Host "         $hint" -ForegroundColor Yellow }
    exit 1
}

# Resolve the docker CLI: PATH first, then Docker Desktop's default location
# (a terminal opened before the Docker install has a stale PATH).
function Resolve-DockerCli {
    $cmd = Get-Command docker -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $fallback = Join-Path ${env:ProgramFiles} 'Docker\Docker\resources\bin\docker.exe'
    if (Test-Path $fallback) { return $fallback }
    Fail 'docker CLI not found.' "Install Docker Desktop, then open a NEW terminal."
}

$script:dockerExe = Resolve-DockerCli

# Make the docker CLI's own directory visible on PATH for child processes.
# `docker compose` spawns helpers (e.g. docker-credential-desktop) resolved via
# PATH. A terminal launched before Docker Desktop was installed inherits a stale
# PATH from explorer.exe, so the helpers would not be found even though the
# registry PATH is correct. Prepending the directory makes the script self-healing.
$dockerDir = Split-Path -Parent $script:dockerExe
if ($env:PATH -notlike "*$dockerDir*") {
    Write-Host "Note: adding to PATH for this session -> $dockerDir" -ForegroundColor DarkGray
    $env:PATH = "$dockerDir;$env:PATH"
}

# Safe wrapper for external commands.
# We capture stdout only and let stderr pass straight to the console: with
# $ErrorActionPreference = 'Stop', PowerShell 5.1 turns a native command's
# stderr (once redirected) into a terminating error and would hide our friendly
# messages behind a stack trace; merging with 2>&1 would still print a red
# NativeCommandError block. SilentlyContinue + no redirection keeps output clean
# while the real docker diagnostics stay visible to the user.
function Invoke-Docker {
    param([string[]]$DockerArgs)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        $output = & $script:dockerExe @DockerArgs
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    [pscustomobject]@{ Output = ($output | Out-String).Trim(); ExitCode = $code }
}

# ---- 1. Is the Docker engine running? ----
Write-Step '1/4 Check the Docker engine'
$version = Invoke-Docker @('version', '--format', '{{.Server.Version}}')
if ($version.ExitCode -ne 0) {
    $desktopRunning = $null -ne (Get-Process 'Docker Desktop' -ErrorAction SilentlyContinue)
    $hint = if ($desktopRunning) {
        'Docker Desktop is starting up. Wait until the tray icon says "Running", then retry.'
    } else {
        "Start it first:  Start-Process '$desktopExe'   (accept the agreement on first launch, then wait ~1-2 min)"
    }
    Fail "Docker engine is not reachable. $($version.Output)" $hint
}
Write-Host "Docker engine OK, server version: $($version.Output)"

# ---- 2. Start PostgreSQL ----
Write-Step '2/4 Start the PostgreSQL container'
$busy = Get-NetTCPConnection -LocalPort 5432 -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Write-Host "WARNING: port 5432 is already in use by another process (PID $($busy.OwningProcess -join ','))." -ForegroundColor Yellow
    Write-Host '         If that is another PostgreSQL instance, stop it or change the port in docker-compose.yml.' -ForegroundColor Yellow
}

$up = Invoke-Docker @('compose', '-f', $composeFile, 'up', '-d')
if ($up.ExitCode -ne 0) { Fail 'docker compose up failed.' $up.Output }
Write-Host $up.Output

Write-Host 'Waiting for the container to become healthy...'
$healthy = $false
for ($i = 0; $i -lt 60; $i++) {
    $state = Invoke-Docker @('inspect', '--format', '{{.State.Health.Status}}', $container)
    if ($state.ExitCode -eq 0 -and $state.Output -eq 'healthy') { $healthy = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $healthy) {
    $logs = Invoke-Docker @('logs', '--tail', '40', $container)
    Fail "Container $container did not become healthy within 120s." $logs.Output
}
Write-Host 'PostgreSQL is ready.'

# ---- 3. Run migrations ----
Write-Step '3/4 Run Alembic migrations'
if (-not (Test-Path $venvPython)) {
    Fail "Virtualenv missing at $venvPython." 'Create it and install backend dependencies first (see README).'
}
Push-Location (Join-Path $repoRoot 'backend')
try {
    & $venvPython -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { Fail 'alembic upgrade head failed.' }
    & $venvPython -m alembic current
} finally {
    Pop-Location
}

# ---- 4. Verify connectivity from the app ----
Write-Step '4/4 Verify database connectivity from the app'
$probe = @'
import asyncio

from app.db.engine import check_db, engine


async def main() -> None:
    ok = await check_db()
    print("check_db ->", "OK" if ok else "FAILED")
    await engine.dispose()
    raise SystemExit(0 if ok else 1)


asyncio.run(main())
'@
Push-Location (Join-Path $repoRoot 'backend')
try {
    $probe | & $venvPython -
    if ($LASTEXITCODE -ne 0) { Fail 'Database connectivity check failed.' 'Check DATABASE_URL in backend\.env against docker-compose.yml.' }
} finally {
    Pop-Location
}

Write-Host "`nAll done. Start the backend and /health should return 200 with status=ok, db=ok:" -ForegroundColor Green
Write-Host '  cd backend; .venv\Scripts\python -m uvicorn app.main:app --reload'
Write-Host '  curl http://127.0.0.1:8000/health'
