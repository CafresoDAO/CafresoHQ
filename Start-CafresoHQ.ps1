<#
  Start-CafresoHQ.ps1 — Windows launcher.

  Runs the WHOLE CafresoHQ stack inside WSL (so hermes + every agent CLI is
  unix-native and the Projects terminal works), then opens the browser once the
  backend is listening. On native Windows, Hermes (a unix-only Python package)
  cannot run, which is exactly why we host the stack in WSL.

  Requires: WSL with Ubuntu, python3, and (optionally) the hermes CLI. See
  Start-CafresoHQ.sh for the unix-side logic.
#>
$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
$port = 8787

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
  Write-Host "WSL not found. Install it with:  wsl --install -d Ubuntu" -ForegroundColor Yellow
  exit 1
}

Write-Host "Starting CafresoHQ in WSL ($repo)..." -ForegroundColor Cyan

# Launch serve.py inside WSL in its own window so logs stay visible. We pipe the
# script through `tr -d '\r'` so CRLF line endings (from Windows/git) can't break
# the shell, and use a login+interactive shell so ~/.local/bin (hermes) is on PATH.
Start-Process wsl.exe -ArgumentList @(
  '--cd', $repo, '-e', 'bash', '-lic',
  "tr -d '\r' < Start-CafresoHQ.sh | PORT=$port bash -s"
)

# Wait for the backend to bind, then open the browser. The boot screen covers
# any remaining warm-up time.
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
  try {
    $r = Invoke-WebRequest -Uri "http://localhost:$port/health" -TimeoutSec 2 -UseBasicParsing
    if ($r.StatusCode -eq 200) { $ok = $true; break }
  } catch { }
  Start-Sleep -Milliseconds 700
}

Start-Process "http://localhost:$port/hq.html"
if ($ok) {
  Write-Host "CafresoHQ is up → http://localhost:$port/hq.html" -ForegroundColor Green
} else {
  Write-Host "Backend still warming up — the boot screen will connect when it's ready." -ForegroundColor Yellow
}
