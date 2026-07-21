# Quick tunnel for the Workspaces API (port 8080 only).
# Writes the assigned https URL to logs\cloudflared-url.txt for pickup.
param(
    [string] $LogDir = (Join-Path $PSScriptRoot 'logs')
)
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$log = Join-Path $LogDir 'cloudflared.log'
$cf  = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
if (-not (Test-Path $cf)) { $cf = (Get-Command cloudflared -ErrorAction Stop).Source }

# Already running?
$existing = Get-Process cloudflared -ErrorAction SilentlyContinue
if ($existing) { Write-Host "cloudflared already running (PID $($existing.Id))"; return }

Start-Process -FilePath $cf -ArgumentList @(
    'tunnel', '--no-autoupdate', '--url', 'http://127.0.0.1:8080',
    '--logfile', $log
) -WindowStyle Hidden
Write-Host "cloudflared quick tunnel starting; URL will appear in $log"
