<#
.SYNOPSIS
    Launch workspaces-api.py as a detached background process on ASERVER.

.DESCRIPTION
    Replaces the broken Start-Process -RedirectStandardOutput path that causes
    WinError 10013 / WSAEACCES on TCP bind.  Root cause: combining
    -RedirectStandardOutput + -RedirectStandardError produces a child token
    that cannot bind TCP listeners (a Windows ACL quirk with anonymous pipe
    inheritance in restricted contexts — scheduled task, SYSTEM account, etc.)

    FIX: use -RedirectStandardError only (stderr log is usually enough) and
    capture stdout with a Python-level redirect inside the process, OR use
    nssm to run as a proper Windows service (preferred for production).

.USAGE
    # Minimum — stderr log only, stdout lost
    .\Start-FleetApi.ps1

    # With stdout log as well (use nssm path)
    .\Start-FleetApi.ps1 -UseNssm

.NOTES
    - Reads .env.host from the same directory for environment variables
    - Uses the path recorded in fleet.json when port is not specified in .env.host
    - Port default: 8081 (tunnel from OCI forwards :8081 → this process)
#>
param(
    [string]  $FleetDir   = $PSScriptRoot,
    [string]  $EnvFile    = (Join-Path $PSScriptRoot '.env.host'),
    [string]  $LogDir     = (Join-Path $PSScriptRoot 'logs'),
    [switch]  $UseNssm,
    [switch]  $Force   # kill an existing fleet-api before starting
)

$ErrorActionPreference = 'Continue'

# ── 1. Read .env.host ────────────────────────────────────────────────────────
$env_vars = @{}
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') {
            $env_vars[$Matches[1]] = $Matches[2].Trim()
        }
    }
}

# Apply env vars to current process (fleet-api inherits them)
foreach ($kv in $env_vars.GetEnumerator()) {
    [System.Environment]::SetEnvironmentVariable($kv.Key, $kv.Value, 'Process')
}

$port = if ($env_vars['FLEET_API_PORT']) { $env_vars['FLEET_API_PORT'] } else { '8081' }

# ── 2. Ensure log directory exists ───────────────────────────────────────────
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$errLog = Join-Path $LogDir 'fleet-api-stderr.log'
$outLog = Join-Path $LogDir 'fleet-api-stdout.log'

# ── 3. Optionally kill existing instance ─────────────────────────────────────
if ($Force) {
    # Matches both the gateway's fleet-api.py and this host's workspaces-api.py
    # (the -Force kill only ever matched the former, so restarts on this box
    # silently no-op'd and left the old process listening — confirmed 2026-07-21).
    # Win32_Process, not Get-Process: Windows PowerShell 5.1's Get-Process has
    # no CommandLine property, so the filter silently matched nothing there.
    Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*fleet-api*' -or $_.CommandLine -like '*workspaces-api*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

# ── 4. Check if already running ──────────────────────────────────────────────
$existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "fleet-api already listening on :$port (PID $($existing.OwningProcess))" -ForegroundColor Green
    return
}

# ── 5. Launch ────────────────────────────────────────────────────────────────
$script    = Join-Path $FleetDir 'workspaces-api.py'
$pythonCmd = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
if (-not $pythonCmd) { $pythonCmd = 'python' }

if ($UseNssm) {
    # ── nssm service path (cleanest — survives reboots with proper token) ─────
    $nssmPath = (Get-Command nssm -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
    if (-not $nssmPath) {
        Write-Warning "nssm not found. Install from https://nssm.cc or `choco install nssm`."
        Write-Warning "Falling back to Start-Process method."
        $UseNssm = $false
    } else {
        $svcName = 'CafresoAI-FleetApi'
        $existing_svc = Get-Service $svcName -ErrorAction SilentlyContinue
        if (-not $existing_svc) {
            Write-Host "Installing $svcName via nssm..." -ForegroundColor Yellow
            & $nssmPath install $svcName $pythonCmd $script
            & $nssmPath set $svcName AppDirectory $FleetDir
            & $nssmPath set $svcName AppStdout $outLog
            & $nssmPath set $svcName AppStderr $errLog
            & $nssmPath set $svcName AppRotateFiles 1
            & $nssmPath set $svcName AppRotateOnline 1
            & $nssmPath set $svcName AppRotateBytes 10485760  # 10 MB

            # Pass environment (nssm AppEnvironmentExtra)
            foreach ($kv in $env_vars.GetEnumerator()) {
                & $nssmPath set $svcName AppEnvironmentExtra "$($kv.Key)=$($kv.Value)" | Out-Null
            }
        }
        & $nssmPath start $svcName
        Write-Host "$svcName started via nssm" -ForegroundColor Green
        return
    }
}

# ── Start-Process path (no -RedirectStandardOutput — that's the bug) ─────────
# -RedirectStandardOutput combined with -RedirectStandardError produces a
# child process with a restricted token that can't bind TCP listeners.
# Using -RedirectStandardError alone works correctly.
# Stdout goes to the Python-level log (fleet-api writes structured logs
# via logging module to stderr already; stdout is minimal startup banner).
Write-Host "Starting fleet-api on :$port (stderr -> $errLog)..." -ForegroundColor Yellow

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName               = $pythonCmd
$psi.Arguments              = "`"$script`""
$psi.WorkingDirectory       = $FleetDir
$psi.WindowStyle            = [System.Diagnostics.ProcessWindowStyle]::Hidden
$psi.UseShellExecute        = $false
$psi.RedirectStandardOutput = $false   # <-- DO NOT set to $true (breaks TCP bind)
$psi.RedirectStandardError  = $true
$psi.CreateNoWindow         = $true

# Inject env vars into the child
foreach ($kv in $env_vars.GetEnumerator()) {
    $psi.EnvironmentVariables[$kv.Key] = $kv.Value
}

$proc = [System.Diagnostics.Process]::Start($psi)

# Drain stderr async into the log file
$proc.add_ErrorDataReceived({
    param($sender, $e)
    if ($e.Data) { Add-Content -Path $errLog -Value $e.Data }
})
$proc.BeginErrorReadLine()

Write-Host "fleet-api PID $($proc.Id) started on :$port" -ForegroundColor Green
Write-Host "Stderr log: $errLog" -ForegroundColor DarkGray

# Wait a moment and confirm bind
Start-Sleep -Seconds 3
$bound = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($bound) {
    Write-Host "Confirmed: port $port is listening (PID $($bound.OwningProcess))" -ForegroundColor Green
} else {
    Write-Warning "Port $port NOT listening after 3s - check $errLog"
    if (Test-Path $errLog) { Get-Content $errLog -Tail 20 }
}
