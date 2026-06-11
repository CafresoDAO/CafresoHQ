# ── CafresoAI — Multi-platform Docker build + push ───────────────────────────
# Builds a fat manifest covering linux/amd64 + linux/arm64 so the image runs
# natively on x86-64 Linux servers, OCI Fleet nodes, AND Apple Silicon Macs
# without any "platform mismatch" warning or QEMU emulation penalty.
#
# Usage (from the repo root in PowerShell):
#   .\scripts\docker-build.ps1                  # build + push :latest
#   .\scripts\docker-build.ps1 -Tag v1.2.0      # also tag a version
#   .\scripts\docker-build.ps1 -DryRun          # print commands, don't run
#
# Requirements:
#   Docker Desktop for Windows (ships buildx): docker buildx version
#   Logged into Docker Hub: docker login

param(
    [string]$Tag     = "",
    [switch]$DryRun  = $false
)

$ErrorActionPreference = "Stop"

$IMAGE     = "docker.io/anthonycf1/cafresoai-serve"
$PLATFORMS = "linux/amd64,linux/arm64"

function Run-Cmd {
    param([string[]]$Cmd)
    Write-Host ("» " + ($Cmd -join " ")) -ForegroundColor Cyan
    if (-not $DryRun) {
        & $Cmd[0] $Cmd[1..($Cmd.Length-1)]
        if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE)" }
    }
}

# ── 1. Ensure a multi-platform builder exists ─────────────────────────────────
$builders = docker buildx ls 2>&1
if ($builders -notmatch "multiarch") {
    Write-Host "Creating buildx builder 'multiarch'..." -ForegroundColor Yellow
    Run-Cmd @("docker","buildx","create","--name","multiarch","--driver","docker-container","--bootstrap")
}
Run-Cmd @("docker","buildx","use","multiarch")

# ── 2. Build + push both platforms in one shot ────────────────────────────────
$tagArgs = @("--tag","${IMAGE}:latest")
if ($Tag -ne "") { $tagArgs += @("--tag","${IMAGE}:${Tag}") }

Run-Cmd (@(
    "docker","buildx","build",
    "--platform",$PLATFORMS
) + $tagArgs + @(
    "--push",
    "-f","oci-fleet/Dockerfile",
    "."
))

Write-Host ""
Write-Host "✓ Pushed multi-arch manifest: ${IMAGE}:latest  [$PLATFORMS]" -ForegroundColor Green
if ($Tag -ne "") { Write-Host "  also tagged:               ${IMAGE}:${Tag}" -ForegroundColor Green }
Write-Host ""
Write-Host "Users can now run:"
Write-Host "  docker run -d --name cafresohq -p 8787:8787 ``"
Write-Host "    -v cafresohq-data:/data ``"
Write-Host "    ${IMAGE}:latest"
Write-Host ""
Write-Host "Docker will automatically pull the correct architecture for their machine."
