<#
.SYNOPSIS
    Maintain the SSH reverse tunnel from WSL → OCI that exposes fleet-api to Caddy.

.DESCRIPTION
    Runs a loop in WSL that keeps `ssh -R 8081:{host}:8081 opc@OCI_HOST` alive.
    On each reconnect the WSL host IP is auto-detected: prefers 10.0.0.100 (the
    Windows External vSwitch IP, reachable after normal boot), falls back to
    the WSL virtual gateway (172.30.x.x, reliable even after WinNAT restart).

    The tunnel forwards: OCI:8081 → ASERVER fleet-api:{port}

    Run this from an interactive PowerShell session (or a scheduled task that
    uses the same launch method as Start-FleetApi.ps1 — no stdout redirect).

.PARAMETER OciHost
    OCI instance hostname or IP (default: from .env.host OCI_HOST or hq.cafreso.com)

.PARAMETER RemotePort
    Port the OCI sshd binds for the reverse tunnel (default: 8081)

.PARAMETER LocalPort
    Port fleet-api listens on ASERVER (default: 8081)

.PARAMETER WslDistro
    WSL distro to run ssh from (default: Ubuntu)

.PARAMETER SshKey
    Path to the SSH private key inside WSL (default: ~/.ssh/id_rsa)

.PARAMETER ReconnectDelay
    Seconds between reconnect attempts (default: 10)
#>
param(
    [string] $OciHost       = '',
    [int]    $RemotePort    = 8081,
    [int]    $LocalPort     = 8081,
    [string] $WslDistro     = 'Ubuntu',
    [string] $SshKey        = '~/.ssh/id_rsa',
    [int]    $ReconnectDelay = 10
)

$ErrorActionPreference = 'Continue'
$EnvFile = Join-Path $PSScriptRoot '.env.host'

# ── Load .env.host ────────────────────────────────────────────────────────────
$env_vars = @{}
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') {
            $env_vars[$Matches[1]] = $Matches[2].Trim()
        }
    }
}

if (-not $OciHost) {
    $OciHost = $env_vars['OCI_HOST']
    if (-not $OciHost) { $OciHost = 'hq.cafreso.com' }
}

Write-Host "Keep-Tunnel: OCI=$OciHost remote=$RemotePort local=$LocalPort distro=$WslDistro" -ForegroundColor Cyan

# ── Helper: detect the best host IP for the reverse tunnel target ─────────────
function Get-TunnelTargetIp {
    param([string] $Distro, [int] $Port)

    # 1. Try the ASERVER external vSwitch IP (standard routing after clean boot)
    $candidates = @('10.0.0.100')

    # 2. Detect WSL default gateway (Windows host on WSL virtual NIC)
    #    `ip route show default` inside WSL → "default via 172.30.192.1 dev eth0"
    $wslGw = wsl -d $Distro -- bash -c "ip route show default 2>/dev/null | awk '{print \$3}' | head -1" 2>$null
    if ($wslGw) { $candidates += $wslGw.Trim() }

    foreach ($ip in $candidates) {
        # Quick TCP probe from WSL to see if fleet-api is reachable there
        $reachable = wsl -d $Distro -- bash -c "nc -z -w2 $ip $Port 2>/dev/null && echo ok" 2>$null
        if ($reachable -match 'ok') {
            Write-Host "  Tunnel target: $ip`:$Port (reachable)" -ForegroundColor Green
            return $ip
        } else {
            Write-Host "  Tunnel target: $ip`:$Port (unreachable, trying next)" -ForegroundColor Yellow
        }
    }

    # Last resort: the WSL gateway (always works for host-side services)
    if ($wslGw) {
        Write-Warning "  All TCP probes failed. Using WSL gateway $wslGw as fallback."
        return $wslGw.Trim()
    }
    Write-Warning "  Could not detect tunnel target IP. Defaulting to 127.0.0.1 (may not work)."
    return '127.0.0.1'
}

# ── Tunnel loop ───────────────────────────────────────────────────────────────
$attempt = 0
while ($true) {
    $attempt++
    Write-Host "$(Get-Date -Format 'HH:mm:ss') Tunnel attempt #$attempt..." -ForegroundColor DarkGray

    $targetIp = Get-TunnelTargetIp -Distro $WslDistro -Port $LocalPort

    # ssh options:
    #   -N          — no remote command; tunnel only
    #   -R          — reverse port forward
    #   -o ServerAliveInterval=60   — send keepalive every 60s
    #   -o ServerAliveCountMax=6    — fail after 6 missed (6 min total)
    #   -o ExitOnForwardFailure=yes — exit immediately if bind fails on OCI
    #   -o StrictHostKeyChecking=no — don't prompt for host key on first connect
    #   -o ConnectTimeout=30        — don't hang forever on connect
    $sshCmd = @(
        "ssh",
        "-N",
        "-i", $SshKey,
        "-R", "${RemotePort}:${targetIp}:${LocalPort}",
        "-o", "ServerAliveInterval=60",
        "-o", "ServerAliveCountMax=6",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=30",
        "-o", "TCPKeepAlive=yes",
        "opc@$OciHost"
    ) -join ' '

    Write-Host "  WSL: $sshCmd" -ForegroundColor DarkGray
    $exitCode = (wsl -d $WslDistro -- bash -c "$sshCmd; echo EXIT:$?")
    Write-Host "$(Get-Date -Format 'HH:mm:ss') Tunnel exited (code: $exitCode). Reconnecting in ${ReconnectDelay}s..." -ForegroundColor Yellow
    Start-Sleep -Seconds $ReconnectDelay
}
