<#
.SYNOPSIS
    Clone a Hyper-V VM from a gold image checkpoint for a workspace session.

.DESCRIPTION
    Called by fleet-api.py (HyperVProvider.create_vm) when a user launches a
    Hyper-V workspace. Creates a differencing VHDX from the gold checkpoint,
    builds a new VM referencing it, applies resource configuration (vCPU, RAM,
    GPU-P partition), starts the VM, and polls until Sunshine responds on its
    HTTP port.

    Outputs a JSON object with the new VM's name, IP, and status.

    Usage (from fleet-api.py / hyperv-provider.py):
      powershell -NoProfile -File New-WorkspaceVM.ps1 `
        -GoldCheckpoint "win11-dev-gold" `
        -SessionId "ses_a1b2c3d4" `
        -VmName "CafresoVM-windows-dev-a1b2c3d4" `
        -VCpus 4 -MemoryGB 16 `
        -GpuPartition "50%" `
        -SunshinePort 47989 `
        -VSwitchName "Default Switch"

.NOTES
    Requires: Windows Server 2025 Datacenter with Hyper-V, Administrator
    Run on the Hyper-V HOST (not inside the VM).
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$GoldCheckpoint,

    [Parameter(Mandatory)]
    [string]$SessionId,

    [Parameter(Mandatory)]
    [string]$VmName,

    [int]$VCpus = 4,

    [int]$MemoryGB = 16,

    [string]$GpuPartition = "",

    [int]$SunshinePort = 47989,

    [string]$VSwitchName = "Default Switch",

    [string]$GoldImagesPath = "C:\HyperV\GoldImages",

    [string]$WorkspaceVmPath = "C:\HyperV\Workspaces",

    [int]$SunshineTimeoutSec = 120,

    [switch]$Persistent
)

$ErrorActionPreference = 'Stop'

# ── Output helper ─────────────────────────────────────────────────────────────
function Write-Result {
    param(
        [string]$Status,
        [string]$VmName,
        [string]$IP = "",
        [int]$Port = 0,
        [string]$Error = "",
        [string]$VhdxPath = ""
    )
    $result = @{
        status       = $Status
        vm_name      = $VmName
        ip           = $IP
        port         = $Port
        error        = $Error
        vhdx_path    = $VhdxPath
        session_id   = $SessionId
        timestamp    = (Get-Date -Format 'o')
    }
    $result | ConvertTo-Json -Depth 4
}

# ── 1. Locate gold image VHDX ────────────────────────────────────────────────
Write-Host "=== New-WorkspaceVM: $VmName ===" -ForegroundColor Cyan
Write-Host "[1/7] Locating gold image: $GoldCheckpoint" -ForegroundColor Yellow

# Strategy: look for a checkpoint on an existing gold VM, or find a VHDX
# directly by name convention.
$goldVm = Get-VM -Name $GoldCheckpoint -ErrorAction SilentlyContinue

if (-not $goldVm) {
    # Try alternative: look for VHDX file directly
    $goldVhdx = Get-ChildItem -Path $GoldImagesPath -Filter "$GoldCheckpoint*.vhdx" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $goldVhdx) {
        Write-Result -Status 'error' -VmName $VmName -Error "Gold image '$GoldCheckpoint' not found as VM or VHDX in $GoldImagesPath"
        exit 1
    }
    $parentVhdxPath = $goldVhdx.FullName
    Write-Host "  Found gold VHDX: $parentVhdxPath" -ForegroundColor Green
} else {
    # Get the first VHDX attached to the gold VM
    $goldDisk = Get-VMHardDiskDrive -VMName $GoldCheckpoint -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $goldDisk) {
        Write-Result -Status 'error' -VmName $VmName -Error "Gold VM '$GoldCheckpoint' has no hard disk drives"
        exit 1
    }
    $parentVhdxPath = $goldDisk.Path
    Write-Host "  Gold VM disk: $parentVhdxPath" -ForegroundColor Green
}

# Verify parent VHDX exists
if (-not (Test-Path $parentVhdxPath)) {
    Write-Result -Status 'error' -VmName $VmName -Error "Parent VHDX not found: $parentVhdxPath"
    exit 1
}

# ── 2. Create differencing VHDX ──────────────────────────────────────────────
Write-Host "[2/7] Creating differencing VHDX..." -ForegroundColor Yellow

$vmDir = Join-Path $WorkspaceVmPath $VmName
if (-not (Test-Path $vmDir)) {
    New-Item -ItemType Directory -Path $vmDir -Force | Out-Null
}

$diffVhdxPath = Join-Path $vmDir "$VmName.vhdx"

if (Test-Path $diffVhdxPath) {
    Write-Host "  VHDX already exists (reusing): $diffVhdxPath" -ForegroundColor Yellow
} else {
    New-VHD -Path $diffVhdxPath -ParentPath $parentVhdxPath -Differencing | Out-Null
    Write-Host "  Differencing VHDX: $diffVhdxPath" -ForegroundColor Green
}

# ── 3. Create the VM ─────────────────────────────────────────────────────────
Write-Host "[3/7] Creating VM: $VmName" -ForegroundColor Yellow

$existingVm = Get-VM -Name $VmName -ErrorAction SilentlyContinue
if ($existingVm) {
    Write-Host "  VM already exists (state: $($existingVm.State))" -ForegroundColor Yellow
} else {
    $memoryBytes = [int64]$MemoryGB * 1GB
    New-VM -Name $VmName `
           -MemoryStartupBytes $memoryBytes `
           -VHDPath $diffVhdxPath `
           -Path $WorkspaceVmPath `
           -Generation 2 `
           -SwitchName $VSwitchName | Out-Null

    # Disable dynamic memory for consistent performance
    Set-VMMemory -VMName $VmName -DynamicMemoryEnabled $false

    # Set processor count
    Set-VMProcessor -VMName $VmName -Count $VCpus

    # Enable secure boot with Microsoft template (for Win11)
    Set-VMFirmware -VMName $VmName -SecureBootTemplate 'MicrosoftWindows'

    # Enable integration services
    Enable-VMIntegrationService -VMName $VmName -Name 'Guest Service Interface' -ErrorAction SilentlyContinue

    # Set automatic stop action to ShutDown (for clean shutdown)
    Set-VM -VMName $VmName -AutomaticStopAction ShutDown -AutomaticStartAction Nothing

    # Add notes for tracking
    Set-VM -VMName $VmName -Notes "CafresoAI Workspace | Session: $SessionId | Template: $GoldCheckpoint | Created: $(Get-Date -Format 'o')"

    Write-Host "  VM created: $VCpus vCPUs, ${MemoryGB}GB RAM, Gen 2" -ForegroundColor Green
}

# ── 4. Assign GPU-P partition ─────────────────────────────────────────────────
if ($GpuPartition) {
    Write-Host "[4/7] Assigning GPU-P partition ($GpuPartition)..." -ForegroundColor Yellow

    # Remove any existing GPU adapter first
    $existingGpu = Get-VMGpuPartitionAdapter -VMName $VmName -ErrorAction SilentlyContinue
    if ($existingGpu) {
        Remove-VMGpuPartitionAdapter -VMName $VmName -ErrorAction SilentlyContinue
    }

    # Parse percentage to fraction (e.g., "50%" -> 50000000 / 100000000)
    $pctValue = [int]($GpuPartition -replace '%', '')
    $maxPartition = [uint64]($pctValue * 1000000)       # e.g., 50% = 50000000
    $optPartition = [uint64]($pctValue * 1000000)
    $minPartition = [uint64]($pctValue * 500000)         # min = half of requested

    try {
        # Hyper-V GPU-P: partition the host GPU for the VM
        Add-VMGpuPartitionAdapter -VMName $VmName

        # Set partition limits
        Set-VMGpuPartitionAdapter -VMName $VmName `
            -MinPartitionVRAM    $minPartition `
            -MaxPartitionVRAM    $maxPartition `
            -OptimalPartitionVRAM $optPartition `
            -MinPartitionEncode  $minPartition `
            -MaxPartitionEncode  $maxPartition `
            -OptimalPartitionEncode $optPartition `
            -MinPartitionDecode  $minPartition `
            -MaxPartitionDecode  $maxPartition `
            -OptimalPartitionDecode $optPartition `
            -MinPartitionCompute $minPartition `
            -MaxPartitionCompute $maxPartition `
            -OptimalPartitionCompute $optPartition

        # Copy host GPU driver files into the VM for GPU-P
        # The VM needs access to the host's GPU driver DLLs
        Set-VM -VMName $VmName -GuestControlledCacheTypes $true -LowMemoryMappedIoSpace 1GB -HighMemoryMappedIoSpace 32GB

        Write-Host "  GPU-P assigned: $pctValue%" -ForegroundColor Green
    } catch {
        Write-Host "  GPU-P failed: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "  VM will run without GPU acceleration" -ForegroundColor Yellow
    }
} else {
    Write-Host "[4/7] No GPU-P requested, skipping..." -ForegroundColor DarkGray
}

# ── 5. Start the VM ──────────────────────────────────────────────────────────
Write-Host "[5/7] Starting VM..." -ForegroundColor Yellow

$vm = Get-VM -Name $VmName
if ($vm.State -ne 'Running') {
    Start-VM -Name $VmName
    # Wait for VM to enter Running state
    $timeout = 60
    $elapsed = 0
    while ((Get-VM -Name $VmName).State -ne 'Running' -and $elapsed -lt $timeout) {
        Start-Sleep -Seconds 2
        $elapsed += 2
    }
    if ((Get-VM -Name $VmName).State -ne 'Running') {
        Write-Result -Status 'error' -VmName $VmName -VhdxPath $diffVhdxPath -Error "VM failed to enter Running state after ${timeout}s"
        exit 1
    }
}
Write-Host "  VM is running" -ForegroundColor Green

# ── 6. Wait for IP address ───────────────────────────────────────────────────
Write-Host "[6/7] Waiting for network (IP address)..." -ForegroundColor Yellow

$vmIp = $null
$ipTimeout = 90
$ipElapsed = 0
while (-not $vmIp -and $ipElapsed -lt $ipTimeout) {
    Start-Sleep -Seconds 3
    $ipElapsed += 3
    $adapters = Get-VMNetworkAdapter -VMName $VmName -ErrorAction SilentlyContinue
    foreach ($adapter in $adapters) {
        $ips = $adapter.IPAddresses | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' }
        if ($ips) {
            # Prefer private IP ranges
            $vmIp = $ips | Where-Object {
                $_ -match '^10\.' -or $_ -match '^172\.(1[6-9]|2[0-9]|3[01])\.' -or $_ -match '^192\.168\.'
            } | Select-Object -First 1
            if (-not $vmIp) { $vmIp = $ips | Select-Object -First 1 }
        }
    }
}

if (-not $vmIp) {
    Write-Result -Status 'error' -VmName $VmName -VhdxPath $diffVhdxPath -Error "No IP address obtained after ${ipTimeout}s"
    exit 1
}
Write-Host "  VM IP: $vmIp" -ForegroundColor Green

# ── 7. Wait for Sunshine to respond ──────────────────────────────────────────
Write-Host "[7/7] Waiting for Sunshine (port $SunshinePort)..." -ForegroundColor Yellow

$sunshineReady = $false
$sunElapsed = 0
while (-not $sunshineReady -and $sunElapsed -lt $SunshineTimeoutSec) {
    Start-Sleep -Seconds 3
    $sunElapsed += 3
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $connectResult = $tcp.BeginConnect($vmIp, $SunshinePort, $null, $null)
        $waitResult = $connectResult.AsyncWaitHandle.WaitOne(2000, $false)
        if ($waitResult -and $tcp.Connected) {
            $sunshineReady = $true
        }
        $tcp.Close()
    } catch {
        # Not ready yet
    }
}

if (-not $sunshineReady) {
    Write-Host "  Sunshine not responding after ${SunshineTimeoutSec}s (VM may still be booting)" -ForegroundColor Yellow
    Write-Host "  Returning VM info anyway - Sunshine may start shortly" -ForegroundColor Yellow
    Write-Result -Status 'started' -VmName $VmName -IP $vmIp -Port $SunshinePort -VhdxPath $diffVhdxPath
    exit 0
}

Write-Host "  Sunshine is ready!" -ForegroundColor Green

# ── Output final result ───────────────────────────────────────────────────────
Write-Host "`n=== VM Ready ===" -ForegroundColor Cyan
Write-Result -Status 'ready' -VmName $VmName -IP $vmIp -Port $SunshinePort -VhdxPath $diffVhdxPath
