# =====================================================================
# dev.ps1 - start the local dev stack (backend :8000, frontend :5173)
#
# Behaviour:
#   1. Kill whatever is listening on 8000 / 5173 (including orphaned
#      uvicorn workers and vite processes), so the ports are always free.
#   2. Start the backend (uvicorn, no --reload: see dev-notes.md) and the
#      frontend (vite) in separate minimised consoles.
#   3. Wait for both ports and print a status summary.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Stop
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -BackendOnly
#
# NOTE: keep this file ASCII-only (PowerShell 5.1 reads scripts with the
# system ANSI code page and mangles non-ASCII text).
# =====================================================================

param(
    [switch]$Stop,
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

$ErrorActionPreference = 'Stop'

$repoRoot   = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot 'backend'
$frontendDir = Join-Path $repoRoot 'frontend'
$venvPython = Join-Path $backendDir '.venv\Scripts\python.exe'

$BackendPort  = 8000
$FrontendPort = 5173

function Write-Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }

function Stop-ListeningProcess([int]$Port) {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) {
        Write-Host "port $Port : free"
        return
    }
    foreach ($conn in $conns) {
        $procId = $conn.OwningProcess
        if (-not $procId -or $procId -eq 0) { continue }
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "port $Port : killing PID $procId ($($proc.ProcessName))" -ForegroundColor Yellow
            taskkill /F /PID $procId 2>&1 | Out-Null
        } else {
            # Socket still reported but the process is already gone (orphan socket)
            Write-Host "port $Port : PID $procId already gone (stale socket)" -ForegroundColor DarkGray
        }
    }
}

function Stop-AllDev() {
    Write-Step 'Stopping dev processes'
    Stop-ListeningProcess $BackendPort
    Stop-ListeningProcess $FrontendPort

    # Backstop: any leftover uvicorn / vite process (e.g. a reloader worker
    # that inherited the socket after its parent was killed)
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*uvicorn*' } |
        ForEach-Object {
            Write-Host "killing leftover uvicorn PID $($_.ProcessId)" -ForegroundColor Yellow
            taskkill /F /PID $_.ProcessId 2>&1 | Out-Null
        }

    Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
        Where-Object { $_.CommandLine -like '*vite*' } |
        ForEach-Object {
            Write-Host "killing leftover vite PID $($_.ProcessId)" -ForegroundColor Yellow
            taskkill /F /PID $_.ProcessId 2>&1 | Out-Null
        }

    Start-Sleep -Seconds 1
}

function Wait-Port([int]$Port, [int]$TimeoutSeconds = 45) {
    for ($i = 0; $i -lt ($TimeoutSeconds * 2); $i++) {
        if (Test-NetConnection 127.0.0.1 -Port $Port -WarningAction SilentlyContinue -InformationLevel Quiet) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Start-Backend {
    Write-Step "Starting backend on :$BackendPort"
    if (-not (Test-Path $venvPython)) {
        throw "venv python not found: $venvPython (create the venv and install requirements first)"
    }
    Start-Process -FilePath $venvPython `
        -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$BackendPort" `
        -WorkingDirectory $backendDir `
        -WindowStyle Minimized
}

function Start-Frontend {
    Write-Step "Starting frontend on :$FrontendPort"
    Start-Process -FilePath 'cmd.exe' `
        -ArgumentList '/c', 'npm run dev' `
        -WorkingDirectory $frontendDir `
        -WindowStyle Minimized
}

# --------------------------------------------------------------------- main

Stop-AllDev

if ($Stop) {
    Write-Host "`nAll dev processes stopped." -ForegroundColor Green
    return
}

if (-not $FrontendOnly) { Start-Backend }
if (-not $BackendOnly) { Start-Frontend }

Write-Step 'Waiting for ports'
$backendUp = $true
$frontendUp = $true
if (-not $FrontendOnly) { $backendUp = Wait-Port $BackendPort }
if (-not $BackendOnly) { $frontendUp = Wait-Port $FrontendPort }

Write-Step 'Status'
if ($FrontendOnly) {
    Write-Host 'backend : (skipped)'
} elseif ($backendUp) {
    $health = curl.exe -s -m 3 "http://127.0.0.1:$BackendPort/health"
    Write-Host "backend : http://127.0.0.1:$BackendPort  $health"
} else {
    Write-Host 'backend : FAILED to start within 45s' -ForegroundColor Red
}

if ($BackendOnly) {
    Write-Host 'frontend: (skipped)'
} elseif ($frontendUp) {
    Write-Host "frontend: http://127.0.0.1:$FrontendPort"
} else {
    Write-Host 'frontend: FAILED to start within 45s' -ForegroundColor Red
}

if ($backendUp -and ($FrontendOnly -or $frontendUp)) {
    Write-Host "`nOpen http://127.0.0.1:$FrontendPort  (Swagger: http://127.0.0.1:$BackendPort/docs)" -ForegroundColor Green
}
