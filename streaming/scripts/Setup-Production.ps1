<#
.SYNOPSIS
    One-time production setup for CafresoAI Workspace Portal streaming stack.

.DESCRIPTION
    Verifies prerequisites, creates required directories, pulls Docker images,
    generates secrets if missing, starts coturn, and validates connectivity.

    Run from the CafresoHQ repository root:
      powershell -NoProfile -File streaming/scripts/Setup-Production.ps1

.NOTES
    Requires: Docker Desktop, PowerShell 5.1+, Administrator (for Hyper-V checks)
    Host:     Windows Server 2025 Datacenter or Windows 11 Pro with Hyper-V
#>

$ErrorActionPreference = 'Continue'
$RepoRoot   = (Resolve-Path "$PSScriptRoot\..\..").Path
$StreamDir  = Join-Path $RepoRoot 'streaming'
$FleetDir   = Join-Path $RepoRoot 'oci-fleet'
$EnvFile    = Join-Path $StreamDir '.env'

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  CafresoAI Production Setup" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$errors   = @()
$warnings = @()

# ── 1. Check prerequisites ──────────────────────────────────────────────────
Write-Host "[1/8] Checking prerequisites..." -ForegroundColor Yellow

# Docker
$dockerOk = $false
try {
    $dv = docker version --format '{{.Server.Version}}' 2>$null
    if ($dv) {
        Write-Host "  Docker: $dv" -ForegroundColor Green
        $dockerOk = $true
    }
} catch {}
if (-not $dockerOk) {
    $errors += "Docker is not running. Start Docker Desktop first."
    Write-Host "  Docker: NOT FOUND" -ForegroundColor Red
}

# Python
$pythonOk = $false
try {
    $pv = python --version 2>&1
    Write-Host "  Python: $pv" -ForegroundColor Green
    $pythonOk = $true
} catch {
    $errors += "Python not found in PATH."
    Write-Host "  Python: NOT FOUND" -ForegroundColor Red
}

# Node.js
try {
    $nv = node --version 2>&1
    Write-Host "  Node.js: $nv" -ForegroundColor Green
} catch {
    $warnings += "Node.js not found — frontend dev server won't work."
    Write-Host "  Node.js: NOT FOUND" -ForegroundColor Yellow
}

# Hyper-V
$hypervOk = $false
try {
    $hvModule = Get-Module -ListAvailable -Name Hyper-V 2>$null
    if ($hvModule) {
        Write-Host "  Hyper-V: module available" -ForegroundColor Green
        $hypervOk = $true
    } else {
        Write-Host "  Hyper-V: module not found (VMs won't work)" -ForegroundColor Yellow
        $warnings += "Hyper-V PowerShell module not found."
    }
} catch {
    Write-Host "  Hyper-V: check failed" -ForegroundColor Yellow
}

# ── 2. Create directory structure ────────────────────────────────────────────
Write-Host "`n[2/8] Creating directories..." -ForegroundColor Yellow

$dirs = @(
    'C:\HyperV\GoldImages',
    'C:\HyperV\Workspaces',
    (Join-Path $StreamDir 'recordings'),
    (Join-Path $StreamDir 'monitoring'),
    (Join-Path $StreamDir 'monitoring\grafana\dashboards'),
    (Join-Path $StreamDir 'monitoring\grafana\provisioning\datasources'),
    (Join-Path $StreamDir 'monitoring\grafana\provisioning\dashboards')
)

foreach ($d in $dirs) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
        Write-Host "  Created: $d" -ForegroundColor Green
    } else {
        Write-Host "  Exists:  $d" -ForegroundColor DarkGray
    }
}

# ── 3. Generate / validate .env ──────────────────────────────────────────────
Write-Host "`n[3/8] Checking environment configuration..." -ForegroundColor Yellow

if (-not (Test-Path $EnvFile)) {
    Write-Host "  .env not found — copying from .env.example" -ForegroundColor Yellow
    $exampleEnv = Join-Path $StreamDir '.env.example'
    if (Test-Path $exampleEnv) {
        Copy-Item $exampleEnv $EnvFile
        # Generate a fresh TURN secret
        $newSecret = python -c "import secrets; print(secrets.token_hex(32))" 2>$null
        if ($newSecret) {
            (Get-Content $EnvFile) -replace 'change-me-to-a-random-hex-string', $newSecret | Set-Content $EnvFile
            Write-Host "  Generated TURN secret: $($newSecret.Substring(0,16))..." -ForegroundColor Green
        }
    } else {
        $warnings += ".env.example not found — create streaming/.env manually."
    }
} else {
    Write-Host "  .env exists" -ForegroundColor Green
}

# Load .env values
$envVars = @{}
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)$') {
            $envVars[$Matches[1]] = $Matches[2].Trim()
        }
    }
}

$turnSecret = $envVars['TURN_SECRET']
if (-not $turnSecret -or $turnSecret -eq 'change-me-to-a-random-hex-string') {
    $warnings += "TURN_SECRET is not set in .env"
    Write-Host "  TURN_SECRET: NOT SET" -ForegroundColor Yellow
} else {
    Write-Host "  TURN_SECRET: configured ($($turnSecret.Substring(0,12))...)" -ForegroundColor Green
}

# ── 4. Set environment variables for fleet-api ───────────────────────────────
Write-Host "`n[4/8] Setting environment variables..." -ForegroundColor Yellow

# Set TURN_SECRET for the current session so fleet-api picks it up
if ($turnSecret -and $turnSecret -ne 'change-me-to-a-random-hex-string') {
    $env:TURN_SECRET = $turnSecret
    Write-Host "  TURN_SECRET set for this session" -ForegroundColor Green
}

$turnUrl = $envVars['TURN_URL']
if ($turnUrl) {
    $env:TURN_URL = $turnUrl
    Write-Host "  TURN_URL: $turnUrl" -ForegroundColor Green
}

# ── 5. Pull Docker images ────────────────────────────────────────────────────
Write-Host "`n[5/8] Pulling Docker images..." -ForegroundColor Yellow

if ($dockerOk) {
    $images = @(
        'coturn/coturn:latest',
        'prom/prometheus:latest',
        'grafana/grafana:latest'
    )

    foreach ($img in $images) {
        Write-Host "  Pulling $img..." -ForegroundColor DarkGray
        docker pull $img 2>$null | Select-Object -Last 1
    }
    Write-Host "  All images pulled" -ForegroundColor Green
} else {
    Write-Host "  Skipped (Docker not available)" -ForegroundColor Yellow
}

# ── 6. Create Docker network ─────────────────────────────────────────────────
Write-Host "`n[6/8] Creating Docker networks..." -ForegroundColor Yellow

if ($dockerOk) {
    $networks = @('cafresoai-streaming', 'cafresoai-monitoring')
    foreach ($net in $networks) {
        $existing = docker network ls --filter "name=$net" --format '{{.Name}}' 2>$null
        if ($existing -eq $net) {
            Write-Host "  Network $net exists" -ForegroundColor DarkGray
        } else {
            docker network create $net 2>$null | Out-Null
            Write-Host "  Created network: $net" -ForegroundColor Green
        }
    }
}

# ── 7. Start coturn ──────────────────────────────────────────────────────────
Write-Host "`n[7/8] Starting coturn TURN server..." -ForegroundColor Yellow

if ($dockerOk -and $turnSecret -and $turnSecret -ne 'change-me-to-a-random-hex-string') {
    Push-Location $StreamDir
    try {
        docker compose -f docker-compose.coturn.yml up -d 2>&1 | ForEach-Object { Write-Host "  $_" }
        Start-Sleep -Seconds 3

        # Check if coturn is running
        $coturnStatus = docker inspect cafresoai-coturn --format '{{.State.Status}}' 2>$null
        if ($coturnStatus -eq 'running') {
            Write-Host "  coturn is RUNNING" -ForegroundColor Green
        } else {
            $warnings += "coturn container status: $coturnStatus"
            Write-Host "  coturn status: $coturnStatus" -ForegroundColor Yellow
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "  Skipped (Docker or TURN_SECRET not available)" -ForegroundColor Yellow
}

# ── 8. Validate connectivity ─────────────────────────────────────────────────
Write-Host "`n[8/8] Validating services..." -ForegroundColor Yellow

# Fleet API
try {
    $fleetHealth = Invoke-RestMethod -Uri 'http://localhost:8080/fleet/health' -TimeoutSec 3 -ErrorAction Stop
    Write-Host "  Fleet API: healthy" -ForegroundColor Green
} catch {
    $warnings += "Fleet API not responding on :8080"
    Write-Host "  Fleet API: not responding" -ForegroundColor Yellow
}

# Prometheus metrics endpoint
try {
    $metrics = Invoke-WebRequest -Uri 'http://localhost:8080/metrics' -TimeoutSec 3 -ErrorAction Stop
    $metricCount = ($metrics.Content -split "`n" | Where-Object { $_ -match '^cafresoai_' }).Count
    Write-Host "  Metrics endpoint: $metricCount metrics exposed" -ForegroundColor Green
} catch {
    Write-Host "  Metrics endpoint: not available" -ForegroundColor Yellow
}

# coturn port
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $result = $tcp.BeginConnect('127.0.0.1', 3478, $null, $null)
    $connected = $result.AsyncWaitHandle.WaitOne(2000, $false)
    $tcp.Close()
    if ($connected) {
        Write-Host "  coturn (port 3478): listening" -ForegroundColor Green
    } else {
        Write-Host "  coturn (port 3478): not listening" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  coturn (port 3478): check failed" -ForegroundColor Yellow
}

# Frontend
try {
    Invoke-WebRequest -Uri 'http://localhost:5174' -TimeoutSec 3 -ErrorAction Stop | Out-Null
    Write-Host "  Frontend dev server: running" -ForegroundColor Green
} catch {
    Write-Host "  Frontend dev server: not running" -ForegroundColor Yellow
}

# ── Summary ──────────────────────────────────────────────────────────────────
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Setup Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

if ($errors.Count -gt 0) {
    Write-Host "`nERRORS ($($errors.Count)):" -ForegroundColor Red
    $errors | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
}

if ($warnings.Count -gt 0) {
    Write-Host "`nWARNINGS ($($warnings.Count)):" -ForegroundColor Yellow
    $warnings | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
}

Write-Host "`nNext steps:" -ForegroundColor White
Write-Host "  1. Start fleet-api:    cd oci-fleet && python fleet-api.py" -ForegroundColor DarkGray
Write-Host "  2. Start frontend:     cd frontend && npm run dev" -ForegroundColor DarkGray
Write-Host "  3. Start monitoring:   cd streaming/monitoring && docker compose -f docker-compose.monitoring.yml up -d" -ForegroundColor DarkGray
Write-Host "  4. Open workspaces:    http://localhost:5174/workspaces" -ForegroundColor DarkGray
Write-Host "  5. Open Grafana:       http://localhost:3000 (admin / $($envVars['GRAFANA_ADMIN_PASSWORD']))" -ForegroundColor DarkGray
Write-Host "  6. Open Prometheus:    http://localhost:9090" -ForegroundColor DarkGray
Write-Host ""
