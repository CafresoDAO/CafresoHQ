#!/usr/bin/env python3
"""
HyperVProvider — Manage Windows/Linux VMs on a local Hyper-V host.

Creates workspace VMs from gold image checkpoints, assigns GPU-P partitions,
manages Sunshine lifecycle, and tracks per-session VM state.

Requires: Windows Server 2025 Datacenter with Hyper-V, Administrator privileges.
"""

import json
import logging
import os
import pathlib
import subprocess
import time
import uuid

log = logging.getLogger("hyperv-provider")

# Path to the New-WorkspaceVM.ps1 script (relative to this file)
_SCRIPTS_DIR = pathlib.Path(__file__).parent.parent / "streaming" / "scripts"
_NEW_VM_SCRIPT = _SCRIPTS_DIR / "New-WorkspaceVM.ps1"


class HyperVProvider:
    """Manages Hyper-V VMs for workspace sessions."""

    def __init__(self, config=None):
        """
        config: dict with optional keys:
          - gold_images_path: path to gold image VHDXs
          - workspace_vm_path: path to store per-session differencing disks
          - vswitch_name: virtual switch for VMs
          - vm_prefix: naming prefix (default: CafresoVM)
          - sunshine_timeout: seconds to wait for Sunshine (default: 120)
          - moonlight_web_image: docker image for moonlight-web-stream
        """
        self.config = config or {}
        self.gold_images_path = self.config.get(
            "gold_images_path", r"C:\HyperV\GoldImages"
        )
        self.workspace_vm_path = self.config.get(
            "workspace_vm_path", r"C:\HyperV\Workspaces"
        )
        self.vswitch_name = self.config.get("vswitch_name", "Default Switch")
        self.vm_prefix = self.config.get("vm_prefix", "CafresoVM")
        self.sunshine_timeout = self.config.get("sunshine_timeout", 120)
        self.moonlight_web_image = self.config.get(
            "moonlight_web_image", "ghcr.io/games-on-whales/moonlight-web:latest"
        )

    # ── PowerShell execution ─────────────────────────────────────────────────

    def _ps(self, script, timeout=30):
        """Execute a PowerShell script locally and return parsed output."""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                log.error("PowerShell error: %s", result.stderr.strip())
                return None
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            log.error("PowerShell timed out after %ds", timeout)
            return None
        except FileNotFoundError:
            log.error("PowerShell not found — is this a Windows Server host?")
            return None

    def _ps_json(self, script, timeout=30):
        """Execute PowerShell and parse JSON output."""
        raw = self._ps(script + " | ConvertTo-Json -Depth 4", timeout)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.error("Failed to parse PowerShell JSON: %s", raw[:200])
            return None

    # ── VM Listing ───────────────────────────────────────────────────────────

    def list_vms(self):
        """List all Hyper-V VMs, returning simplified records."""
        data = self._ps_json(
            "Get-VM | Select-Object Name, State, Uptime, "
            "MemoryAssigned, ProcessorCount, Path, Id"
        )
        if data is None:
            return []
        # PowerShell returns a single object (not array) when there's one VM
        if isinstance(data, dict):
            data = [data]
        vms = []
        for vm in data:
            vms.append({
                "name": vm.get("Name", ""),
                "state": self._normalize_state(vm.get("State", 0)),
                "uptime_seconds": self._parse_timespan(vm.get("Uptime")),
                "memory_mb": (vm.get("MemoryAssigned", 0) or 0) // (1024 * 1024),
                "vcpus": vm.get("ProcessorCount", 0),
                "id": vm.get("Id", ""),
            })
        return vms

    def get_vm_status(self, vm_name):
        """Get detailed status for a single VM."""
        data = self._ps_json(
            f'Get-VM -Name "{vm_name}" | Select-Object Name, State, Uptime, '
            f"MemoryAssigned, MemoryDemand, ProcessorCount, Status, "
            f"@{{N='CpuUsage';E={{$_.CpuUsage}}}}"
        )
        if data is None:
            return None
        if isinstance(data, list):
            data = data[0] if data else None
        if not data:
            return None
        return {
            "name": data.get("Name", vm_name),
            "state": self._normalize_state(data.get("State", 0)),
            "uptime_seconds": self._parse_timespan(data.get("Uptime")),
            "memory_assigned_mb": (data.get("MemoryAssigned", 0) or 0) // (1024 * 1024),
            "memory_demand_mb": (data.get("MemoryDemand", 0) or 0) // (1024 * 1024),
            "vcpus": data.get("ProcessorCount", 0),
            "cpu_usage": data.get("CpuUsage", 0),
            "status": data.get("Status", ""),
        }

    # ── VM Lifecycle ────────────────────────────────────────────────────────────

    def create_vm(self, template, session_id, principal):
        """
        Create a new VM from a gold image checkpoint.

        Delegates to streaming/scripts/New-WorkspaceVM.ps1 which:
          1. Creates a differencing VHDX from the gold image
          2. Creates a Gen 2 VM with configured vCPU / RAM
          3. Assigns GPU-P partition (if requested)
          4. Starts the VM
          5. Waits for IP address + Sunshine readiness

        Returns dict with vm_name, ip, port, state, vhdx_path, error.
        """
        vm_name = f"{self.vm_prefix}-{template.get('id', 'ws')}-{session_id[:8]}"
        gold_checkpoint = template.get("vm_template", "")
        resources = template.get("resources", {})
        vcpus = resources.get("vcpus", 4)
        memory_gb = resources.get("memory_gb", 16)
        gpu_partition = resources.get("gpu_partition", "")
        sunshine_port = template.get("sunshine_port", 47989)

        if not gold_checkpoint:
            log.error("No vm_template specified in template %s", template.get("id"))
            return {
                "vm_name": vm_name,
                "state": "error",
                "ip": None,
                "port": sunshine_port,
                "error": "no vm_template in workspace template",
            }

        # ── Fast path: persistent template with a pre-existing VM ────────────
        # When a template has gold_ip set, the VM already exists and is known.
        # Skip New-WorkspaceVM.ps1 entirely — just ensure the VM is running
        # and return the fixed IP. This is the path for Dev1 / windows-dev.
        gold_ip = template.get("gold_ip", "")
        if template.get("persistent", False) and gold_ip:
            log.info(
                "Persistent VM fast path: %s @ %s (port=%d)",
                gold_checkpoint, gold_ip, sunshine_port,
            )
            status = self.get_vm_status(gold_checkpoint)
            if status:
                state = status.get("state", "unknown")
                if state not in ("running", "starting"):
                    log.info("VM %s is %s — starting it", gold_checkpoint, state)
                    self.start_vm(gold_checkpoint)
            else:
                log.warning(
                    "Could not query VM status for %s — assuming running", gold_checkpoint
                )
            return {
                "vm_name": gold_checkpoint,
                "state": "running",
                "ip": gold_ip,
                "port": sunshine_port,
                "vhdx_path": "",
                "error": "",
            }

        log.info(
            "create_vm: %s from gold=%s (vcpus=%d, ram=%dGB, gpu=%s)",
            vm_name, gold_checkpoint, vcpus, memory_gb, gpu_partition or "none",
        )

        # Check that the New-WorkspaceVM.ps1 script exists
        if not _NEW_VM_SCRIPT.exists():
            log.error("New-WorkspaceVM.ps1 not found at %s", _NEW_VM_SCRIPT)
            return {
                "vm_name": vm_name,
                "state": "error",
                "ip": None,
                "port": sunshine_port,
                "error": f"script not found: {_NEW_VM_SCRIPT}",
            }

        # Build PowerShell command
        args = [
            "powershell", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-File", str(_NEW_VM_SCRIPT),
            "-GoldCheckpoint", gold_checkpoint,
            "-SessionId", session_id,
            "-VmName", vm_name,
            "-VCpus", str(vcpus),
            "-MemoryGB", str(memory_gb),
            "-SunshinePort", str(sunshine_port),
            "-VSwitchName", self.vswitch_name,
            "-GoldImagesPath", self.gold_images_path,
            "-WorkspaceVmPath", self.workspace_vm_path,
            "-SunshineTimeoutSec", str(self.sunshine_timeout),
        ]
        if gpu_partition:
            args += ["-GpuPartition", gpu_partition]
        if template.get("persistent", False):
            args.append("-Persistent")

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=300,  # 5 min max for full VM creation
            )

            # The script writes human-readable progress to stderr/stdout,
            # and the LAST JSON block is the result
            output = result.stdout.strip()
            stderr = result.stderr.strip()

            if stderr:
                log.warning("New-WorkspaceVM stderr: %s", stderr[:500])

            # Extract the last JSON object from output
            vm_result = self._extract_json_result(output)

            if result.returncode != 0 and not vm_result:
                log.error("New-WorkspaceVM failed (rc=%d): %s", result.returncode, output[:500])
                return {
                    "vm_name": vm_name,
                    "state": "error",
                    "ip": None,
                    "port": sunshine_port,
                    "error": output[:1000] or f"exit code {result.returncode}",
                }

            if vm_result:
                log.info(
                    "create_vm result: %s state=%s ip=%s",
                    vm_name, vm_result.get("status"), vm_result.get("ip"),
                )
                return {
                    "vm_name": vm_result.get("vm_name", vm_name),
                    "state": vm_result.get("status", "unknown"),
                    "ip": vm_result.get("ip"),
                    "port": vm_result.get("port", sunshine_port),
                    "vhdx_path": vm_result.get("vhdx_path", ""),
                    "error": vm_result.get("error", ""),
                }

            # Fallback: script ran but no JSON found
            return {
                "vm_name": vm_name,
                "state": "started",
                "ip": None,
                "port": sunshine_port,
                "error": "no JSON result from script",
            }

        except subprocess.TimeoutExpired:
            log.error("create_vm timed out after 300s: %s", vm_name)
            # Try to clean up the partially-created VM
            self.stop_vm(vm_name)
            return {
                "vm_name": vm_name,
                "state": "error",
                "ip": None,
                "port": sunshine_port,
                "error": "VM creation timed out after 300s",
            }
        except Exception as e:
            log.exception("create_vm unexpected error: %s", vm_name)
            return {
                "vm_name": vm_name,
                "state": "error",
                "ip": None,
                "port": sunshine_port,
                "error": str(e),
            }

    def start_vm(self, vm_name):
        """Start a stopped VM."""
        result = self._ps(f'Start-VM -Name "{vm_name}"')
        return result is not None

    def stop_vm(self, vm_name, force=True):
        """Gracefully stop a running VM."""
        flag = " -Force" if force else ""
        result = self._ps(f'Stop-VM -Name "{vm_name}"{flag}', timeout=60)
        return result is not None

    def delete_vm(self, vm_name, remove_disk=True):
        """
        Delete a VM and optionally its differencing disk.

          1. Stop-VM -Force -TurnOff (if running)
          2. Get VHDX paths before removal
          3. Remove-VM -Force
          4. Delete differencing VHDX + VM folder (if remove_disk)
        """
        log.info("delete_vm: %s (remove_disk=%s)", vm_name, remove_disk)

        # Get disk paths before we remove the VM
        vhdx_paths = []
        if remove_disk:
            disks = self._ps_json(
                f'Get-VMHardDiskDrive -VMName "{vm_name}" '
                f'| Select-Object -ExpandProperty Path'
            )
            if isinstance(disks, str):
                vhdx_paths = [disks]
            elif isinstance(disks, list):
                vhdx_paths = [d for d in disks if isinstance(d, str)]

        # Stop VM if running
        status = self.get_vm_status(vm_name)
        if status and status.get("state") in ("running", "starting", "paused"):
            log.info("  Stopping VM %s before deletion", vm_name)
            self._ps(f'Stop-VM -Name "{vm_name}" -TurnOff -Force', timeout=30)
            # Brief wait for shutdown
            import time
            time.sleep(2)

        # Remove the VM from Hyper-V
        result = self._ps(f'Remove-VM -Name "{vm_name}" -Force', timeout=30)
        if result is None:
            log.error("  Failed to remove VM %s from Hyper-V", vm_name)
            return False

        log.info("  VM %s removed from Hyper-V", vm_name)

        # Delete differencing VHDX files
        if remove_disk and vhdx_paths:
            for vhdx in vhdx_paths:
                # Only delete files under our workspace path (safety check)
                if self.workspace_vm_path.lower() in vhdx.lower():
                    try:
                        self._ps(f'Remove-Item -Path "{vhdx}" -Force', timeout=15)
                        log.info("  Deleted VHDX: %s", vhdx)
                    except Exception as e:
                        log.warning("  Failed to delete VHDX %s: %s", vhdx, e)
                else:
                    log.warning("  Skipping VHDX outside workspace path: %s", vhdx)

            # Try to remove the empty VM directory
            vm_dir = os.path.join(self.workspace_vm_path, vm_name)
            if os.path.isdir(vm_dir):
                try:
                    self._ps(
                        f'Remove-Item -Path "{vm_dir}" -Recurse -Force',
                        timeout=15,
                    )
                    log.info("  Cleaned up VM directory: %s", vm_dir)
                except Exception:
                    pass

        return True

    def get_vm_ip(self, vm_name):
        """Get the IP address of a running VM via Hyper-V network adapter."""
        # Use PowerShell to get IPv4 addresses from the VM's network adapters
        raw = self._ps(
            f'(Get-VMNetworkAdapter -VMName "{vm_name}").IPAddresses '
            f'| Where-Object {{ $_ -match "^\\d+\\.\\d+\\.\\d+\\.\\d+$" }} '
            f'| Select-Object -First 1'
        )
        if raw:
            return raw.strip()
        return None

    # ── GPU-P ────────────────────────────────────────────────────────────────

    def assign_gpu_partition(self, vm_name, partition_pct="50%"):
        """
        Assign a GPU-P partition to a VM. Requires Server 2025 Datacenter.

        partition_pct: e.g. "50%", "100%", "25%"
        """
        log.info("assign_gpu_partition: %s -> %s", vm_name, partition_pct)
        pct = int(partition_pct.replace("%", ""))

        # Remove existing GPU adapter if present
        self._ps(
            f'Remove-VMGpuPartitionAdapter -VMName "{vm_name}" '
            f'-ErrorAction SilentlyContinue'
        )

        # Add GPU partition adapter
        result = self._ps(f'Add-VMGpuPartitionAdapter -VMName "{vm_name}"')
        if result is None:
            log.error("Failed to add GPU partition adapter to %s", vm_name)
            return False

        # Configure partition limits
        min_val = pct * 500000
        opt_val = pct * 1000000
        max_val = pct * 1000000
        script = (
            f'Set-VMGpuPartitionAdapter -VMName "{vm_name}" '
            f'-MinPartitionVRAM {min_val} -MaxPartitionVRAM {max_val} '
            f'-OptimalPartitionVRAM {opt_val} '
            f'-MinPartitionEncode {min_val} -MaxPartitionEncode {max_val} '
            f'-OptimalPartitionEncode {opt_val} '
            f'-MinPartitionDecode {min_val} -MaxPartitionDecode {max_val} '
            f'-OptimalPartitionDecode {opt_val} '
            f'-MinPartitionCompute {min_val} -MaxPartitionCompute {max_val} '
            f'-OptimalPartitionCompute {opt_val}'
        )
        self._ps(script)

        # Enable GPU-P memory mapping
        self._ps(
            f'Set-VM -VMName "{vm_name}" '
            f'-GuestControlledCacheTypes $true '
            f'-LowMemoryMappedIoSpace 1GB '
            f'-HighMemoryMappedIoSpace 32GB'
        )

        log.info("GPU-P %s assigned to %s", partition_pct, vm_name)
        return True

    # ── Moonlight-web-stream sidecar ─────────────────────────────────────────

    def start_moonlight_sidecar(self, session_id, vm_ip, sunshine_port=47989,
                                 signaling_port=8443, turn_url="",
                                 turn_user="", turn_cred=""):
        """
        Start a moonlight-web-stream Docker container for a session.
        This container bridges Sunshine (inside the VM) to WebRTC (browser).

        Uses mrcreativ3001/moonlight-web-stream which exposes:
          - TCP signaling_port: web UI + WebSocket signaling
          - UDP 40000-40100: WebRTC media relay
        The Sunshine host is configured via the web UI on first launch,
        or pre-paired through the container's config volume.

        Returns (success, container_name, signaling_port).
        """
        container_name = f"cafresoai-moonlight-{session_id[:12]}"
        log.info(
            "Starting moonlight sidecar: %s -> %s:%d (web=%d)",
            container_name, vm_ip, sunshine_port, signaling_port,
        )

        # Allocate a UDP media port range for this session
        # Each session gets 20 ports from the 40000-40999 range
        port_hash = hash(session_id) % 50  # 0-49
        udp_start = 40000 + (port_hash * 20)
        udp_end = udp_start + 19

        # Build docker run command.
        # Env var names match ghcr.io/games-on-whales/moonlight-web image:
        #   SUNSHINE_HOST / SUNSHINE_PORT — where Sunshine is running (VM)
        #   PORT                          — container's own HTTP/WS listen port
        #   TURN_SERVER / TURN_USERNAME / TURN_CREDENTIAL — ICE relay
        cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "--restart", "unless-stopped",
            # Sunshine target (inside VM)
            "-e", f"SUNSHINE_HOST={vm_ip}",
            "-e", f"SUNSHINE_PORT={sunshine_port}",
            # moonlight-web listens on 8080 internally; signaling_port is the host port
            "-e", "PORT=8080",
            "-e", "MOONLIGHT_WS_FALLBACK=true",
            "-e", "STUN_SERVER=stun:stun.l.google.com:19302",
            "-p", f"{signaling_port}:8080",
            "-p", f"{udp_start}-{udp_end}:{udp_start}-{udp_end}/udp",
        ]
        if turn_url:
            cmd += [
                "-e", f"TURN_SERVER={turn_url}",
                "-e", f"TURN_USERNAME={turn_user}",
                "-e", f"TURN_CREDENTIAL={turn_cred}",
            ]
        cmd.append(self.moonlight_web_image)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                # If network doesn't exist, create it and retry
                if "network cafresoai-streaming not found" in (result.stderr or ""):
                    subprocess.run(
                        ["docker", "network", "create", "cafresoai-streaming"],
                        capture_output=True, text=True, timeout=15,
                    )
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=60,
                    )

            if result.returncode != 0:
                err = result.stderr.strip() or result.stdout.strip()
                log.error("Failed to start moonlight sidecar: %s", err[:500])
                return False, container_name, signaling_port

            log.info("Moonlight sidecar started: %s", container_name)
            return True, container_name, signaling_port

        except Exception as e:
            log.exception("Error starting moonlight sidecar")
            return False, container_name, signaling_port

    def stop_moonlight_sidecar(self, session_id):
        """Stop and remove the moonlight-web-stream container for a session."""
        container_name = f"cafresoai-moonlight-{session_id[:12]}"
        log.info("Stopping moonlight sidecar: %s", container_name)
        try:
            subprocess.run(
                ["docker", "stop", container_name],
                capture_output=True, text=True, timeout=15,
            )
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True, text=True, timeout=15,
            )
            return True
        except Exception as e:
            log.warning("Error stopping moonlight sidecar %s: %s", container_name, e)
            return False

    def _allocate_signaling_port(self, session_id):
        """
        Allocate a unique signaling port for a moonlight-web-stream instance.
        Uses a simple hash of the session ID to distribute across a port range.
        Range: 8500-8999 (500 ports, more than enough for concurrent sessions).
        """
        import hashlib
        h = int(hashlib.md5(session_id.encode()).hexdigest()[:8], 16)
        return 8500 + (h % 500)

    # ── Session Recording ─────────────────────────────────────────────────────

    def start_recording(self, session_id, stream_url, resolution="1920x1080",
                        framerate=30, duration=0):
        """
        Start an ffmpeg recording sidecar for a session.
        Returns (success, container_name).
        """
        container_name = f"cafresoai-recorder-{session_id[:12]}"
        log.info("Starting recording: %s -> %s", container_name, stream_url)

        recordings_path = self.config.get(
            "recordings_path", "/var/lib/cafresoai/recordings"
        )

        cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "-e", f"SESSION_ID={session_id}",
            "-e", f"STREAM_URL={stream_url}",
            "-e", f"RESOLUTION={resolution}",
            "-e", f"FRAMERATE={framerate}",
            "-e", f"RECORDING_DURATION={duration}",
            "-v", f"{recordings_path}:/recordings",
            "--network", "cafresoai-streaming",
            "linuxserver/ffmpeg:latest",
            "/bin/bash", "/record-session.sh",
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                log.error("Failed to start recorder: %s",
                          result.stderr.strip()[:300])
                return False, container_name
            log.info("Recorder started: %s", container_name)
            return True, container_name
        except Exception as e:
            log.exception("Error starting recorder")
            return False, container_name

    def stop_recording(self, session_id):
        """Stop the recording sidecar for a session (sends SIGTERM for clean MP4)."""
        container_name = f"cafresoai-recorder-{session_id[:12]}"
        log.info("Stopping recorder: %s", container_name)
        try:
            subprocess.run(
                ["docker", "stop", "-t", "10", container_name],
                capture_output=True, text=True, timeout=20,
            )
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True, text=True, timeout=10,
            )
            return True
        except Exception as e:
            log.warning("Error stopping recorder %s: %s", container_name, e)
            return False

    # ── VM Pool (pre-warming) ───────────────────────────────────────────────

    def create_pool_vm(self, template):
        """
        Create a pre-warmed VM from a gold image for the pool.
        The VM is started and waits for Sunshine readiness, then stays
        running so it can be claimed instantly by a session launch.

        Returns dict with pool entry fields or None on failure.
        """
        pool_id = uuid.uuid4().hex[:8]
        template_id = template.get("id", "unknown")
        vm_name = f"{self.vm_prefix}-pool-{template_id}-{pool_id}"

        log.info("create_pool_vm: %s (template=%s)", vm_name, template_id)

        gold_checkpoint = template.get("vm_template", "")
        resources = template.get("resources", {})
        vcpus = resources.get("vcpus", 4)
        memory_gb = resources.get("memory_gb", 16)
        gpu_partition = resources.get("gpu_partition", "")
        sunshine_port = template.get("sunshine_port", 47989)

        if not gold_checkpoint:
            log.error("No vm_template for pool VM template %s", template_id)
            return None

        if not _NEW_VM_SCRIPT.exists():
            log.error("New-WorkspaceVM.ps1 not found at %s", _NEW_VM_SCRIPT)
            return None

        args = [
            "powershell", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-File", str(_NEW_VM_SCRIPT),
            "-GoldCheckpoint", gold_checkpoint,
            "-SessionId", f"pool-{pool_id}",
            "-VmName", vm_name,
            "-VCpus", str(vcpus),
            "-MemoryGB", str(memory_gb),
            "-SunshinePort", str(sunshine_port),
            "-VSwitchName", self.vswitch_name,
            "-GoldImagesPath", self.gold_images_path,
            "-WorkspaceVmPath", self.workspace_vm_path,
            "-SunshineTimeoutSec", str(self.sunshine_timeout),
        ]
        if gpu_partition:
            args += ["-GpuPartition", gpu_partition]

        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=300,
            )
            output = result.stdout.strip()
            vm_result = self._extract_json_result(output)

            if result.returncode != 0 and not vm_result:
                log.error("Pool VM creation failed (rc=%d): %s",
                          result.returncode, output[:500])
                return None

            if vm_result and vm_result.get("status") != "error":
                ip = vm_result.get("ip")
                entry = {
                    "pool_id": pool_id,
                    "vm_name": vm_name,
                    "template_id": template_id,
                    "ip": ip,
                    "port": vm_result.get("port", sunshine_port),
                    "vhdx_path": vm_result.get("vhdx_path", ""),
                    "state": "ready" if ip else "started",
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                log.info("Pool VM ready: %s @ %s", vm_name, ip)
                return entry

            log.error("Pool VM failed: %s", vm_result.get("error") if vm_result else "no result")
            return None

        except subprocess.TimeoutExpired:
            log.error("Pool VM creation timed out: %s", vm_name)
            self.stop_vm(vm_name)
            self.delete_vm(vm_name, remove_disk=True)
            return None
        except Exception:
            log.exception("Pool VM creation unexpected error: %s", vm_name)
            return None

    def claim_pool_vm(self, pool_entry, session_id, vm_name_new=None):
        """
        Claim a pre-warmed pool VM for a session.
        Renames the VM to the session's name and returns updated info.

        pool_entry: dict from the pool registry
        session_id: session claiming the VM
        vm_name_new: optional new name; default is CafresoVM-{template}-{session}

        Returns updated pool_entry dict or None on failure.
        """
        old_name = pool_entry.get("vm_name", "")
        template_id = pool_entry.get("template_id", "ws")

        if not vm_name_new:
            vm_name_new = f"{self.vm_prefix}-{template_id}-{session_id[:8]}"

        log.info("claim_pool_vm: %s -> %s (session=%s)", old_name, vm_name_new, session_id)

        # Rename the VM in Hyper-V
        rename_ok = self._ps(
            f'Rename-VM -Name "{old_name}" -NewName "{vm_name_new}"',
            timeout=15,
        )
        if rename_ok is None:
            log.error("Failed to rename pool VM %s -> %s", old_name, vm_name_new)
            # Still usable under old name
            return {
                **pool_entry,
                "state": "claimed",
                "session_id": session_id,
            }

        # Rename the workspace directory too
        old_dir = os.path.join(self.workspace_vm_path, old_name)
        new_dir = os.path.join(self.workspace_vm_path, vm_name_new)
        if os.path.isdir(old_dir):
            try:
                os.rename(old_dir, new_dir)
            except OSError as e:
                log.warning("Failed to rename VM dir %s -> %s: %s", old_dir, new_dir, e)

        # If IP is missing, try to get it now
        ip = pool_entry.get("ip")
        if not ip:
            ip = self.get_vm_ip(vm_name_new)

        return {
            **pool_entry,
            "vm_name": vm_name_new,
            "ip": ip,
            "state": "claimed",
            "session_id": session_id,
            "claimed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def cleanup_stale_pool_vms(self, pool_entries, max_age_hours=12):
        """
        Clean up pool VMs that have been sitting unclaimed too long.
        Returns list of pool_ids that were cleaned up.
        """
        cleaned = []
        now = time.time()

        for entry in pool_entries:
            if entry.get("state") != "ready":
                continue
            created = entry.get("created_at", "")
            if not created:
                continue
            try:
                import datetime
                ts = datetime.datetime.fromisoformat(created.rstrip("Z"))
                age_hours = (now - ts.timestamp()) / 3600
            except (ValueError, OSError):
                continue

            if age_hours > max_age_hours:
                vm_name = entry.get("vm_name", "")
                log.info("Cleaning stale pool VM: %s (age=%.1fh)", vm_name, age_hours)
                if vm_name:
                    self.delete_vm(vm_name, remove_disk=True)
                cleaned.append(entry.get("pool_id"))

        return cleaned

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_json_result(output):
        """
        Extract the last JSON object from mixed PowerShell output.
        The New-WorkspaceVM.ps1 script writes progress to stdout as
        plain text, with a JSON result block at the end.
        """
        if not output:
            return None

        # Try to parse the whole output as JSON first
        try:
            return json.loads(output)
        except (json.JSONDecodeError, ValueError):
            pass

        # Scan backwards for a JSON object
        lines = output.strip().split("\n")
        json_lines = []
        brace_depth = 0
        collecting = False

        for line in reversed(lines):
            stripped = line.strip()
            if not collecting:
                if stripped.endswith("}"):
                    collecting = True
                    brace_depth = stripped.count("}") - stripped.count("{")
                    json_lines.insert(0, line)
                    if brace_depth <= 0:
                        break
            else:
                brace_depth += stripped.count("}") - stripped.count("{")
                json_lines.insert(0, line)
                if brace_depth <= 0:
                    break

        if json_lines:
            try:
                return json.loads("\n".join(json_lines))
            except (json.JSONDecodeError, ValueError):
                pass

        return None

    @staticmethod
    def _normalize_state(state):
        """Convert Hyper-V State enum to string."""
        states = {
            0: "other",
            1: "running",     # Hyper-V: Enabled (2) maps here in PS
            2: "running",
            3: "stopped",
            4: "stopping",
            5: "saved",
            6: "paused",
            7: "starting",
            8: "resetting",
            9: "saving",
            10: "pausing",
            11: "resuming",
        }
        if isinstance(state, str):
            return state.lower()
        return states.get(state, "unknown")

    @staticmethod
    def _parse_timespan(ts):
        """Parse a PowerShell TimeSpan JSON object to seconds."""
        if ts is None:
            return 0
        if isinstance(ts, (int, float)):
            return int(ts)
        if isinstance(ts, dict):
            # PowerShell ConvertTo-Json serializes TimeSpan as:
            # { "Ticks": N, "Days": D, "Hours": H, ... }
            ticks = ts.get("Ticks", 0) or 0
            return int(ticks / 10_000_000)  # 1 tick = 100 ns
        return 0


# ── CLI interface for testing ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    provider = HyperVProvider()

    if len(sys.argv) < 2:
        print("Usage: hyperv-provider.py <list|status|create|delete|ip|gpu> [args...]")
        print()
        print("Commands:")
        print("  list                         List all Hyper-V VMs")
        print("  status <vm_name>             Get detailed VM status")
        print("  ip <vm_name>                 Get VM IP address")
        print("  create <template_id> <sid>   Create VM from template (uses workspaces.json)")
        print("  delete <vm_name>             Delete VM and its disk")
        print("  stop <vm_name>               Stop a running VM")
        print("  start <vm_name>              Start a stopped VM")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list":
        vms = provider.list_vms()
        print(json.dumps(vms, indent=2))

    elif cmd == "status" and len(sys.argv) >= 3:
        status = provider.get_vm_status(sys.argv[2])
        print(json.dumps(status, indent=2))

    elif cmd == "ip" and len(sys.argv) >= 3:
        ip = provider.get_vm_ip(sys.argv[2])
        print(ip or "(no IP)")

    elif cmd == "create" and len(sys.argv) >= 4:
        # Load template from workspaces.json
        ws_file = pathlib.Path(__file__).parent / "workspaces.json"
        templates = json.loads(ws_file.read_text(encoding="utf-8"))
        tmpl = next((t for t in templates if t["id"] == sys.argv[2]), None)
        if not tmpl:
            print(f"Template not found: {sys.argv[2]}")
            sys.exit(1)
        result = provider.create_vm(tmpl, sys.argv[3], "cli-test-principal")
        print(json.dumps(result, indent=2))

    elif cmd == "delete" and len(sys.argv) >= 3:
        ok = provider.delete_vm(sys.argv[2])
        print("deleted" if ok else "failed")

    elif cmd == "stop" and len(sys.argv) >= 3:
        ok = provider.stop_vm(sys.argv[2])
        print("stopped" if ok else "failed")

    elif cmd == "start" and len(sys.argv) >= 3:
        ok = provider.start_vm(sys.argv[2])
        print("started" if ok else "failed")

    else:
        print(f"Unknown command or missing args: {cmd}")
        sys.exit(1)
