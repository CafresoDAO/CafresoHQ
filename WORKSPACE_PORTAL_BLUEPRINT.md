# CafresoHQ → Workspace Portal Blueprint
> Extending CafresoHQ into a Kasm-like portal for Windows VMs, Linux containers, and AI-agentic workflows

---

## What We're Building

A unified **workspace portal** — think Kasm Workspaces but native to CafresoHQ's stack — where users log in via Internet Identity and launch any of:

| Workspace Type | Streaming | Provider |
|---|---|---|
| 🖥️ Windows Desktop VM | Sunshine → moonlight-web-stream (WebRTC) | Hyper-V on-prem |
| 🎮 GPU / Gaming VM | Sunshine → moonlight-web-stream (WebRTC, H.265/AV1) | Hyper-V + GPU-P |
| 🐧 Linux Dev Container | Selkies-GStreamer (WebRTC) | Docker / OCI |
| 🤖 AI Agent Workspace | Existing hq.html + /openclaw/stream | OCI Container |
| 🌐 Browser Isolation | KasmVNC (WebSocket) | Docker / OCI |
| 💻 App Streaming | Selkies or KasmVNC (single app) | Docker / OCI |

All behind the **existing Caddy gateway** at `hq.cafreso.com`, authenticated via **Internet Identity**, managed by an extended **fleet-api.py**.

---

## What Already Exists (Build On This)

| Existing Component | Location | Reuse |
|---|---|---|
| Auth (Internet Identity + principal) | `frontend/src/lib/stores/auth.js` | ✅ Reuse as-is |
| Caddy TLS gateway | `oci-fleet/caddyfile.template` | ✅ Extend with new routes |
| Fleet API (container lifecycle) | `oci-fleet/fleet-api.py` | ✅ Extend with VM + workspace types |
| Fleet Manager (OCI Container Instances) | `oci-fleet/fleet-manager.py` | ✅ Add Hyper-V provider alongside |
| Reverse proxy + session routing | `serve.py` | ✅ Add workspace + streaming routes |
| OCI vault + secrets | `serve.py` `/vault/*` | ✅ Store workspace credentials |
| SvelteKit portal shell | `frontend/src/routes/` | ✅ Add /workspaces, /admin routes |
| Agent runner | `/openclaw/stream`, `/claudecode/stream` | ✅ Reuse as AI workspace type |
| Docker Compose local dev | `oci-fleet/docker-compose.yml` | ✅ Extend with streaming sidecars |
| Design System | `DESIGN_SYSTEM.md` | ✅ Use existing tokens/components |

---

## New Components to Build

### 1. SvelteKit Frontend Routes

```
frontend/src/routes/
├── workspaces/
│   └── +page.svelte          # NEW: Workspace gallery (the Kasm home screen)
├── workspaces/[id]/
│   └── +page.svelte          # NEW: Active session viewer (embeds streaming frame)
├── admin/
│   ├── +page.svelte          # NEW: Admin dashboard
│   ├── users/+page.svelte    # NEW: User management
│   ├── workspaces/+page.svelte # NEW: Workspace template management
│   └── sessions/+page.svelte # NEW: Live session monitoring
└── app/
    └── +page.svelte          # EXISTING: Agent HQ (unchanged)
```

**`/workspaces` page** is the core addition — a grid of workspace tiles (like Kasm's catalog). Each tile shows:
- Workspace name + icon
- Type badge (Windows VM / Linux / Agent / Browser)
- Status indicator (Available / Starting / In Use)
- Launch button → starts session, redirects to `/workspaces/[session-id]`

**`/workspaces/[id]` page** is the session viewer:
- For Windows VM / GPU: embeds `moonlight-web-stream` iframe
- For Linux container: embeds Selkies WebRTC iframe
- For AI Agent: embeds existing `hq.html` (already done)
- For Browser: embeds KasmVNC iframe
- Toolbar: disconnect, resolution, clipboard, file transfer, fullscreen

### 2. Hyper-V Provider (`hyperv-provider.py`)

New Python module (alongside `fleet-manager.py`). Connects to Hyper-V host via **WinRM + PowerShell**.

```python
# Key operations
class HyperVProvider:
    def list_vms(self) -> list[VMInfo]
    def start_vm(self, vm_name: str) -> None
    def stop_vm(self, vm_name: str) -> None
    def get_vm_ip(self, vm_name: str) -> str
    def create_linked_clone(self, template: str, user: str) -> str
    def assign_gpu_partition(self, vm_name: str, gpu_index: int) -> None
    def get_sunshine_status(self, vm_name: str) -> bool
    def get_vm_status(self, vm_name: str) -> VMStatus
```

**Dependencies:**
```
# requirements-hyperv.txt
pywinrm>=0.4.3
requests>=2.31
```

**PowerShell scripts** (`oci-fleet/scripts/hyperv/`):
```
start-vm.ps1
stop-vm.ps1
get-vm-ip.ps1
create-clone.ps1          # New-VHD + New-VM from differencing disk
assign-gpu-partition.ps1  # Set-VMGpuPartitionAdapter
install-sunshine.ps1      # Copy + configure Sunshine inside VM
```

**WinRM setup on Hyper-V host:**
```powershell
Enable-PSRemoting -Force
Set-Item WSMan:\localhost\Client\TrustedHosts -Value "<broker-ip>"
# Certificate-based auth for production
```

### 3. Extended Fleet API (`fleet-api.py` additions)

New endpoints added to the existing Flask/HTTP server:

```python
# Workspace catalog
GET  /workspaces                    # List available workspace templates
GET  /workspaces/{id}               # Get workspace template details

# Session lifecycle
POST /sessions                      # Launch a session (type + workspace_id + principal)
GET  /sessions                      # List active sessions for principal
GET  /sessions/{session_id}         # Get session status + streaming URL
DELETE /sessions/{session_id}       # Terminate session

# VM-specific (Hyper-V)
GET  /vms                           # List available VMs
POST /vms/{name}/start              # Start a VM
POST /vms/{name}/stop               # Stop a VM
GET  /vms/{name}/status             # Get VM status + IP

# Admin endpoints (principal must be in admin list)
GET  /admin/users                   # All users + session counts
GET  /admin/sessions                # All active sessions
GET  /admin/resources               # CPU/RAM/GPU usage
```

**Session object:**
```json
{
  "session_id": "ses_abc123",
  "principal": "abc-xyz-...cai",
  "workspace_id": "windows-dev-vm-1",
  "type": "windows_vm",
  "status": "running",
  "streaming_url": "https://hq.cafreso.com/stream/ses_abc123/",
  "streaming_protocol": "moonlight_webrtc",
  "created_at": "2026-05-16T10:00:00Z",
  "expires_at": "2026-05-16T18:00:00Z"
}
```

### 4. Session Router (`serve.py` additions)

Add to `serve.py`:

```python
# New routes
/workspaces/*         → workspace catalog API (proxy to fleet-api)
/sessions/*           → session API (proxy to fleet-api)
/stream/{session_id}/ → streaming proxy (moonlight-web-stream or Selkies iframe src)
/admin/*              → admin API (fleet-api, principal auth check)
```

The **streaming URL** returned per session type:
- Windows VM: `https://hq.cafreso.com/stream/{id}/` → proxy to `moonlight-web-stream` container at `localhost:8888/?address=<vm-ip>&port=47989`
- Linux container: `https://hq.cafreso.com/stream/{id}/` → proxy to Selkies at container IP
- AI Agent: `https://hq.cafreso.com/hq.html` (already exists)
- Browser: `https://hq.cafreso.com/stream/{id}/` → proxy to KasmVNC

### 5. Streaming Sidecars (`oci-fleet/streaming/`)

```
oci-fleet/streaming/
├── docker-compose.streaming.yml   # Add to base compose
├── moonlight/
│   ├── Dockerfile                 # moonlight-web-stream v2.8
│   └── config.json                # Default stream settings
├── coturn/
│   └── turnserver.conf            # TURN server for WebRTC NAT
└── guacamole/
    ├── docker-compose.guacamole.yml
    └── guacamole.properties        # Fallback RDP gateway
```

**`docker-compose.streaming.yml`:**
```yaml
services:
  moonlight-web:
    image: ghcr.io/mrcreativ3001/moonlight-web-stream:2.8
    ports:
      - "8888:8888"
    environment:
      - WEBRTC_TURN_SERVER=turn:hq.cafreso.com:3478
      - WEBRTC_TURN_USER=openclaw
      - WEBRTC_TURN_PASS=${TURN_SECRET}
    restart: unless-stopped

  coturn:
    image: coturn/coturn:latest
    network_mode: host
    volumes:
      - ./coturn/turnserver.conf:/etc/coturn/turnserver.conf
    restart: unless-stopped

  guacamole:
    image: guacamole/guacamole:1.6.0
    ports:
      - "8080:8080"
    environment:
      - GUACD_HOSTNAME=guacd
    restart: unless-stopped

  guacd:
    image: guacamole/guacd:1.6.0
    restart: unless-stopped
```

### 6. Windows VM Preparation

Each Hyper-V Windows VM needs:

```powershell
# 1. Install Sunshine (run once per VM template)
# Download from https://github.com/LizardByte/Sunshine/releases
winget install LizardByte.Sunshine

# 2. Install Virtual Display Driver (headless GPU capture)
# https://github.com/itsmikethetech/Virtual-Display-Driver
# Enables Sunshine to capture GPU output with no physical monitor

# 3. Configure Sunshine as a Windows Service (auto-start)
sc config SunshineService start=auto
sc start SunshineService

# 4. Disable Hyper-V Synthetic Video Adapter
# (CRITICAL: conflicts with GPU-P streaming)
Disable-VMIntegrationService -VMName <name> -Name "Hyper-V Video"

# 5. Open firewall for Moonlight protocol
New-NetFirewallRule -DisplayName "Sunshine" -Direction Inbound `
  -Protocol TCP -LocalPort 47984,47989,48010 -Action Allow
New-NetFirewallRule -DisplayName "Sunshine UDP" -Direction Inbound `
  -Protocol UDP -LocalPort 47998-48000,48002,48010 -Action Allow

# 6. Enable WinRM for broker management
Enable-PSRemoting -Force
```

**GPU-P assignment** (Hyper-V host, Server 2025 Datacenter):
```powershell
# Assign a GPU partition to a VM
Add-VMGpuPartitionAdapter -VMName <name>
Set-VMGpuPartitionAdapter -VMName <name> `
  -MinPartitionVRAM 80000000 -MaxPartitionVRAM 800000000 `
  -OptimalPartitionVRAM 400000000 `
  -MinPartitionEncode 0 -MaxPartitionEncode 18446744073709551615 `
  -MinPartitionDecode 0 -MaxPartitionDecode 18446744073709551615 `
  -MinPartitionCompute 0 -MaxPartitionCompute 18446744073709551615
```

### 7. Caddyfile Extension

Extend `oci-fleet/caddyfile.template`:

```caddy
hq.cafreso.com {
    # Existing fleet API
    handle /fleet/* {
        reverse_proxy localhost:8080
    }

    # NEW: Session streaming proxy
    handle /stream/* {
        reverse_proxy localhost:8787   # serve.py routes to correct backend
    }

    # NEW: Admin API (same serve.py, auth enforced in handler)
    handle /admin/* {
        reverse_proxy localhost:8787
    }

    # Existing: per-user container routing
    handle /u/{slug}/* {
        reverse_proxy {fleet_lookup:{slug}}
    }

    # Existing: redirect to SvelteKit shell
    handle {
        redir https://ai.cafreso.com{uri}
    }
}
```

---

## Workspace Templates (Catalog Config)

Stored as `hq-state/workspaces.json` (served via fleet-api, editable by admin):

```json
[
  {
    "id": "windows-dev-vm",
    "name": "Windows Dev Desktop",
    "description": "Full Windows 11 development environment with VS Code, Git, Docker Desktop",
    "icon": "🖥️",
    "type": "windows_vm",
    "tags": ["windows", "development", "visual-studio"],
    "streaming": "moonlight_webrtc",
    "vm_template": "win11-dev-gold",
    "gpu": false,
    "max_sessions": 10,
    "idle_timeout_minutes": 60,
    "persistent": true
  },
  {
    "id": "gpu-gaming-vm",
    "name": "GPU Workstation",
    "description": "Windows 11 with NVIDIA GPU partition for rendering, ML, or gaming",
    "icon": "🎮",
    "type": "windows_vm",
    "tags": ["gpu", "gaming", "ml", "rendering"],
    "streaming": "moonlight_webrtc",
    "vm_template": "win11-gpu-gold",
    "gpu": true,
    "gpu_partition_vram_gb": 4,
    "max_sessions": 4,
    "idle_timeout_minutes": 30,
    "persistent": false
  },
  {
    "id": "linux-dev-container",
    "name": "Linux Dev Environment",
    "description": "Ubuntu 24.04 with full development tools, Docker, Python, Node",
    "icon": "🐧",
    "type": "linux_container",
    "tags": ["linux", "ubuntu", "development"],
    "streaming": "selkies_webrtc",
    "image": "cafresoai-linux-dev:latest",
    "max_sessions": 20,
    "idle_timeout_minutes": 90,
    "persistent": true
  },
  {
    "id": "ai-agent-workspace",
    "name": "AI Agent Workspace",
    "description": "Claude Code + Codex agent environment with vault and memory",
    "icon": "🤖",
    "type": "agent",
    "tags": ["ai", "agents", "claude", "automation"],
    "streaming": "hq_native",
    "max_sessions": 50,
    "idle_timeout_minutes": 120,
    "persistent": true
  },
  {
    "id": "browser-isolation",
    "name": "Isolated Browser",
    "description": "Sandboxed Chromium browser for safe web browsing and research",
    "icon": "🌐",
    "type": "linux_container",
    "tags": ["browser", "security", "isolation"],
    "streaming": "kasmvnc",
    "image": "kasmweb/chromium:1.16.1",
    "max_sessions": 30,
    "idle_timeout_minutes": 30,
    "persistent": false
  }
]
```

---

## Build Phases

### Phase 1 — Workspace Gallery UI (Weeks 1–3)
**Goal:** Users can see and launch workspaces from a new page in the SvelteKit portal.

- [ ] Add `/workspaces` SvelteKit route with workspace tile grid
- [ ] Add workspace template JSON + fleet-api GET /workspaces endpoint
- [ ] Session launch flow: POST /sessions → poll status → redirect to `/workspaces/[id]`
- [ ] Session viewer page (iframe placeholder while streaming is wired up)
- [ ] Wire in Internet Identity auth check (principal must be authenticated)
- [ ] Basic session list page (active sessions for current user)

**Deliverable:** Users can browse the catalog and "launch" a workspace (even if the stream isn't live yet — show a "Starting..." state).

---

### Phase 2 — AI Agent Workspace (Weeks 2–4, parallel)
**Goal:** `/workspaces/[id]` for type=agent works end-to-end (this is mostly already built!).

- [ ] Session viewer for agent type loads existing `hq.html`
- [ ] Session lifecycle calls existing OCI fleet provisioning
- [ ] Session state persisted via existing `/hq/state/*` endpoints
- [ ] "Open Agent Workspace" tile on the gallery works fully

**Deliverable:** The agent workspace is the first fully working workspace type — validates the session flow before tackling streaming.

---

### Phase 3 — Linux Container Streaming (Weeks 4–8)
**Goal:** Linux dev container workspace works with Selkies WebRTC streaming.

- [ ] Build `cafresoai-linux-dev` Docker image (Ubuntu + XFCE + Selkies-GStreamer + dev tools)
- [ ] Deploy coturn TURN server alongside the fleet
- [ ] Wire serve.py `/stream/{session_id}/` → Selkies container
- [ ] Session viewer page renders Selkies iframe with WebRTC handshake
- [ ] WebSocket fallback when UDP blocked
- [ ] Idle timeout → container auto-terminate (extend fleet-api)
- [ ] Audio forwarding (PulseAudio + Opus via Selkies)

**Deliverable:** Full Linux desktop in the browser. Validates the streaming infrastructure before Windows VMs.

---

### Phase 4 — Hyper-V Windows VM Streaming (Weeks 8–14)
**Goal:** Windows VM workspaces stream via Sunshine + moonlight-web-stream.

- [ ] Build `hyperv-provider.py` with WinRM + PowerShell operations
- [ ] Prepare Windows VM gold image (Sunshine + Virtual Display Driver + WinRM)
- [ ] Extend fleet-api with `/vms/*` and `/sessions` for VM type
- [ ] Deploy moonlight-web-stream container (alongside coturn)
- [ ] Wire serve.py `/stream/{session_id}/` → moonlight-web-stream pointing at VM IP
- [ ] Session viewer for windows_vm type loads moonlight-web-stream iframe
- [ ] Test sub-30ms LAN latency, validate H.264/H.265 codec selection
- [ ] GPU-P partition assignment for gpu_gaming_vm workspace type

**Deliverable:** Windows desktop in the browser via the Cafreso portal. First time replacing Kasm's core use case.

---

### Phase 5 — Admin Panel (Weeks 12–16, parallel)
**Goal:** Admin users can manage workspaces, users, and sessions.

- [ ] `/admin` SvelteKit route (gated to admin principals list)
- [ ] Live session monitor (poll /admin/sessions, show user + workspace + duration)
- [ ] Resource usage dashboard (CPU/RAM per VM, GPU utilization)
- [ ] Workspace template editor (add/edit/remove catalog entries)
- [ ] User management (list users, revoke access, view session history)
- [ ] Session termination (admin can kill any active session)

---

### Phase 6 — Production Hardening (Weeks 16–20)
**Goal:** Ready for 25–100 concurrent users.

- [ ] Audit logging (all session events to PostgreSQL or structured log)
- [ ] Session recording (optional: ffmpeg capture of streaming frames)
- [ ] Clipboard sync (Moonlight: built-in; Selkies: xdotool/xclip bridge)
- [ ] File transfer (Moonlight drag-drop; Selkies: SFTP or HTTP upload)
- [ ] VM pool pre-warming (keep N VMs pre-started to reduce cold-start latency)
- [ ] Metrics (Prometheus exporter in serve.py + Grafana dashboard)
- [ ] Load test to 100 concurrent sessions (k6 or Locust)
- [ ] HA broker (run serve.py on 2 nodes behind Caddy load balancing)

---

## File Map: What to Create vs. Modify

### New Files
```
frontend/src/routes/workspaces/+page.svelte         Workspace gallery
frontend/src/routes/workspaces/[id]/+page.svelte    Session viewer
frontend/src/routes/admin/+page.svelte              Admin dashboard
frontend/src/lib/api/sessionClient.js               Session API client
frontend/src/lib/stores/sessions.js                 Active session state
frontend/src/lib/components/WorkspaceTile.svelte    Catalog tile component
frontend/src/lib/components/SessionViewer.svelte    Streaming iframe wrapper

hyperv-provider.py                                  Hyper-V WinRM provider
oci-fleet/scripts/hyperv/start-vm.ps1              PowerShell VM ops
oci-fleet/scripts/hyperv/stop-vm.ps1
oci-fleet/scripts/hyperv/create-clone.ps1
oci-fleet/scripts/hyperv/assign-gpu.ps1
oci-fleet/scripts/hyperv/install-sunshine.ps1

oci-fleet/streaming/docker-compose.streaming.yml   Streaming sidecars
oci-fleet/streaming/coturn/turnserver.conf
oci-fleet/streaming/moonlight/config.json

hq-state/workspaces.json                           Workspace template catalog
hq-state/sessions.json                             Active session registry
```

### Modified Files
```
oci-fleet/fleet-api.py          Add /workspaces, /sessions, /vms, /admin endpoints
serve.py                        Add /stream/*, /workspaces/*, /sessions/*, /admin/* routes
oci-fleet/docker-compose.yml    Add streaming sidecar services
oci-fleet/caddyfile.template    Add /stream/* and /admin/* routing
oci-fleet/Dockerfile            Add Selkies deps for Linux workspace images
```

---

## Key Decisions

**Stay on SvelteKit** — The existing frontend is mature and well-structured. New routes fit naturally. No need to rewrite in React.

**Extend fleet-api.py** — The existing fleet API already handles OCI provisioning. Add VM types as a second provider (Hyper-V) with a common session interface.

**Keep serve.py as the proxy hub** — Already handles complex routing. `/stream/*` routes become a new category of proxy destination (streaming sidecar or VM IP).

**Internet Identity stays as auth** — Don't add a second auth system. Principal-based identity gates workspace access. Admin list is a JSON config.

**moonlight-web-stream for Windows, Selkies for Linux** — Best tool per workload. Not a single protocol for everything.

**OCI + Hyper-V as dual providers** — Linux containers on OCI (or on-prem Docker), Windows VMs on Hyper-V. Fleet API abstracts over both.

---

## What This Looks Like When Done

A user visits `ai.cafreso.com`, logs in with Internet Identity, and sees a grid of workspace tiles. They click "Windows Dev Desktop," wait ~10 seconds for the VM to start, and see a full Windows 11 desktop in their browser at 60fps with sub-30ms latency on LAN. Alternatively they launch an "AI Agent Workspace" and get the existing hq.html agent interface. Or they launch a "Linux Dev Environment" and get an Ubuntu desktop with all their tools.

All managed through the same Cafreso portal they already use. No Kasm. No external dependencies for the core streaming.
