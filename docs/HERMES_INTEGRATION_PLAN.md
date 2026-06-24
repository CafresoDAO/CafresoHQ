# Hermes Agent Integration Plan — CafresoHQ Revamp

> Goal: make **Nous Research's Hermes Agent (v0.15.1, released 2026-05-29)** the
> **default** agent runtime for CafresoHQ (codename *CafresoHQ*), while keeping
> Claude Code, Gemini CLI, CafresoHQ, and Codex CLI as user-selectable providers.
>
> Status: architecture + integration plan. Sources are a deep-research pass over
> the Hermes GitHub repo + official docs, **reconciled against the v0.15.1 source
> installed locally** at `~/.hermes/hermes-agent` (authoritative for the two lead
> surfaces and the metering question).

---

## 0. Decisions locked

| Decision | Choice |
|---|---|
| Default runtime | **Hermes** (others remain selectable: Claude Code, Gemini CLI, CafresoHQ, Codex CLI) |
| Lead integration surfaces | **(1) OpenAI-compatible API server** + **(4) tui_gateway WebSocket embed** |
| Secondary / future | ACP adapter, MCP serve |
| Per-container execution | **Hybrid**: one always-on `hermes gateway` + on-demand `hermes chat -q` |
| UI scope | **Both** — new themed "Hermes Console" view **and** Hermes-backed pixel-office agents |

---

## 1. Execution model — HYBRID (one gateway + ephemeral CLI)

**Recommendation:** each per-user OCI Container Instance runs **a single always-on
`hermes gateway` process**, plus optional ephemeral `hermes chat -q "..."` subprocess
calls for stateless one-offs.

Why a persistent gateway is mandatory (not optional):
- **Cron** is ticked by the gateway daemon every 60s; *"Without a running gateway,
  cron jobs will not execute."*
- The **OpenAI-compatible API server** is started **by** `hermes gateway` — no gateway, no API.
- **Persistent memory** (`MEMORY.md`/`USER.md`, FTS5 recall) + multi-channel messaging
  all run from the one gateway process.

When to deviate to pure ephemeral CLI: fully stateless compute jobs that need neither
cron, memory, nor messaging (e.g. a one-shot batch transform). Use `hermes chat -q`
with per-invocation `--provider` / `--toolsets`.

Fit on 1 vCPU / 6 GB: the gateway is the right default because it backs **both** the
office agents and the API server from one process. Memory is disk-backed under
`~/.hermes/` and survives restarts.

> ⚠️ WSL lesson already learned (dev box): the gateway is a **singleton** — a stale
> `~/.hermes/gateway.lock` or a duplicate systemd unit causes `SystemExit: 75`
> ("another instance already running"). In containers, run exactly one gateway under
> the init system and do **not** also enable a systemd unit.

---

## 2. Lead surface #1 — OpenAI-compatible API server

### Enable (per-user, written by `fleet-manager.py` at provision time)
`~/.hermes/.env`:
```bash
API_SERVER_ENABLED=true
API_SERVER_KEY=<strong-per-principal-secret>     # MANDATORY — see security
# API_SERVER_HOST=127.0.0.1                        # default; keep loopback in-container
# API_SERVER_PORT=8642                             # default
# API_SERVER_MODEL_NAME=hermes-agent               # advertised model id
# API_SERVER_CORS_ORIGINS=...                       # only if a browser calls Hermes directly
```
Start: `hermes gateway` → logs `[API Server] API server listening on http://127.0.0.1:8642`.

### Endpoints (verified against local `website/docs/user-guide/features/api-server.md`)
- `POST /v1/chat/completions` — standard OpenAI, **stateless**, SSE when `stream:true`.
- `POST /v1/responses` — OpenAI Responses API, **stateful** via `previous_response_id` + `store:true`.
- `GET /v1/models` · `GET /v1/capabilities` · `GET /health` (also `/v1/health`).
- Auth: `Authorization: Bearer <API_SERVER_KEY>`. Model id: `hermes-agent`.
- **Full agent toolset runs server-side** (terminal, files, web, memory, skills) — proxying this yields a real agent, not just chat.
- Streaming = standard `chat.completion.chunk` **plus** custom `event: hermes.tool.progress`
  for tool-start visibility (drives office-agent activity UI + ApprovalTray).
- **`usage` object is returned** (`prompt_tokens` / `completion_tokens` / `total_tokens`) — see §7.

### `serve.py` changes
Add a Hermes proxy mirroring the existing LM Studio/Ollama proxies:
- New route `/hermes/v1/*` → forwards to `http://127.0.0.1:8642/v1/*`, injecting
  `Authorization: Bearer ${API_SERVER_KEY}` server-side (key never reaches the browser).
- Stream SSE straight through; **parse `usage` + `hermes.tool.progress`** on the way past (§7).
- Add `/hermes/health` liveness passthrough to `/v1/health`.

### `claude-client.jsx` changes
- Register a **`hermes`** provider; make it the **default** selection.
- Point it at the same-origin `/hermes/v1/chat/completions` (Caddy routes per-principal).
- Keep `claudecode`, `codex`, `cafresohq`, `gemini` in the provider list (selectable).
- Map `hermes.tool.progress` SSE events into the existing `cafresohq:agentActivity` event
  so office agents animate on tool use with no UI rewrite.
- Point Hermes' own LLM backend (in `config.yaml` `model` / `custom_providers`, `api_mode:
  chat_completions|anthropic_messages`) at CafresoHQ's existing Anthropic/OCA/LM Studio
  proxies so there's one billing/credential path.

---

## 3. Lead surface #4 — WebSocket TUI embed (CORRECTED)

**Verified from local `tui_gateway/ws.py`** — this is **not** a PTY/xterm.js stream:
- Wire protocol = **newline-delimited JSON-RPC**, identical to stdio, both directions.
- Mounted at FastAPI `@app.websocket("/api/ws")`; server emits a **`gateway.ready`**
  event immediately on connect.
- **Approval / clarify / sudo flows travel over the same socket** via the shared
  `tui_gateway.server.dispatch` handlers.

Implications:
- **Build a custom themed React renderer**, NOT xterm.js. You're rendering structured
  JSON-RPC messages (assistant text, tool events, approval prompts) — style them with
  your pixel-art tokens, not a raw terminal.
- The approval messages are the clean hook into **ApprovalTray** (§5).
- Route `wss://hq.cafreso.com/u/<principal>/api/ws` through Caddy → container `127.0.0.1`.
- Auth the upgrade at the Caddy layer (per-principal) since the socket carries full
  agent control.

New frontend module (e.g. `hermes-console.jsx`): a JSON-RPC-over-WS client +
themed transcript/terminal renderer, surfaced in the new **Hermes Console** view.

---

## 4. Containerization for the OCI fleet

**Recommendation: install Hermes into the existing `cafresoai-serve` image** (single
container, one init), rather than a separate s6-overlay sidecar — simpler on 1 vCPU/6GB
and avoids two PID-1 init systems fighting.

- `oci-fleet/Dockerfile`: add Hermes install (`uv`-based, Python 3.11 already present;
  Node 22 for browser tooling if used). Keep `serve.py` as the front door on 8787.
- `oci-fleet/entrypoint.sh`: start **one** `hermes gateway` (backgrounded/supervised)
  **and** `serve.py`. Ensure single-gateway invariant (no systemd unit, no stale lock).
- **Volume:** mount a per-principal volume at the container user's `~/.hermes` — this is
  the entire persistence boundary (`config.yaml`, `memories/`, `cron/`, `.env`). Map
  **UID/GID** so the gateway process owns it.
- `oci-fleet/fleet-manager.py`: at provision time, seed `~/.hermes/.env`
  (`API_SERVER_ENABLED`, per-principal `API_SERVER_KEY`, provider keys) and a templated
  `config.yaml` (`model`/`custom_providers` → CafresoHQ proxies, `approvals.mode`).
- **Caddy:** expose only `…/u/<principal>/hermes/v1/*` (API) and `…/api/ws` (console)
  with TLS + per-principal auth; everything stays `127.0.0.1` inside the container.

> If you later need hard process isolation, revisit the official s6-overlay image as a
> sidecar — but mind: `/init` must remain PID 1, and you'd manage two containers per user.

---

## 5. Approvals & tools

- Set per-user `approvals.mode` in `config.yaml`: **`manual`** (prompt before flagged
  command) or **`smart`** (auxiliary LLM risk-assesses; auto-approve low-risk, escalate
  risky). Never ship `off` (== `HERMES_YOLO_MODE=true`) for fleet users.
- Consume **`hermes.tool.progress`** (API SSE) and the **approval messages** (WS JSON-RPC)
  to populate **ApprovalTray**, gating execution exactly like the existing Claude Code
  `claude_approval_hook.py` PreToolUse bridge.
- **ACP** (`acp_adapter`, `uvx hermes-agent[acp]==0.15.1` → `hermes-acp`) stays a
  **future** surface for editor-grade edit/permission approvals; not required for v1.

---

## 6. Security (dominant constraint)

- `API_SERVER_KEY` is **mandatory even on loopback** — the API grants full toolset
  access *including terminal commands*. `fleet-manager.py` must inject a strong
  per-principal key and never leave it blank (empty key = auth bypass, see issue #6439).
- Keep API server + dashboard bound to **127.0.0.1 inside the container**. Expose only
  via Caddy (`https://hq.cafreso.com/u/<principal>/…`) with TLS + per-principal auth.
- **Never** set `HERMES_DASHBOARD_INSECURE=1` / `--insecure` (v0.15.1 made this an
  explicit opt-in precisely to stop accidental gate-disabling on containers).
- Per-principal isolation: separate container, separate `~/.hermes` volume, separate
  `API_SERVER_KEY`. Secrets only in `~/.hermes/.env` (referenced from YAML via `${VAR}`).

---

## 7. Metering / billing (unblocks the launch blocker)

**Verified:** `/v1/chat/completions` returns an OpenAI `usage` object
(`prompt_tokens`, `completion_tokens`, `total_tokens`).

- **Token metering:** instrument the **`serve.py` `/hermes/v1` proxy boundary** — read
  `usage` on non-streaming responses; for SSE, accumulate from the final chunk /
  count deltas. Attribute to the principal (one container = one user = clean attribution).
- **Compute metering:** vCPU/RAM-seconds come from **OCI Container Instance telemetry**,
  not Hermes. Combine token + compute for the bill.
- Persist usage per principal (extend the vault or a new `usage/` store) and enforce
  quotas at the Caddy/`serve.py` layer before the gateway runs work.
- ⚠️ Verify token-accounting fidelity for **tool-call / multi-step turns** against the
  running server before relying on it for invoicing.

---

## 8. Migration / rollout plan (phased)

**Phase 0 — Container plumbing.** Add Hermes to `oci-fleet/Dockerfile`; update
`entrypoint.sh` (one gateway + serve.py, single-gateway invariant); per-principal
`~/.hermes` volume + UID/GID; `fleet-manager.py` seeds `.env` + `config.yaml`.

**Phase 1 — API proxy + provider.** `serve.py` `/hermes/v1/*` proxy (key injection +
`usage`/`tool.progress` parsing); `claude-client.jsx` registers `hermes`, **set as
default**, others kept selectable; map `hermes.tool.progress` → `cafresohq:agentActivity`.

**Phase 2 — Approvals.** Wire `hermes.tool.progress` + WS approval messages into
ApprovalTray; set `approvals.mode=manual|smart` per user.

**Phase 3 — Hermes Console (WS).** New `hermes-console.jsx` (JSON-RPC over `/api/ws`,
themed renderer); new view in `views.jsx` + `VIEW_LABELS`; Caddy `wss …/api/ws` route.

**Phase 4 — Hermes-backed office agents.** Re-point Mira/Kip/Bop in `app.jsx` /
`agent_runner.jsx` to the `hermes` provider; add Hermes color tokens to `styles.css`
and document new components in `DESIGN_SYSTEM.md`.

**Phase 5 — Metering + quotas.** Persist per-principal token+compute usage; enforce
quotas; ship the paywall (the documented launch blocker).

**Phase 6 — Cleanup.** Keep Claude Code/Codex/CafresoHQ/Gemini as fallbacks; deprecate
the old default path once Hermes is stable.

### File touch-list
| File | Change |
|---|---|
| `oci-fleet/Dockerfile` | Install Hermes into the serve image |
| `oci-fleet/entrypoint.sh` | Start one `hermes gateway` + `serve.py`; single-gateway invariant |
| `oci-fleet/fleet-manager.py` | Seed per-principal `~/.hermes/.env` + `config.yaml`; inject `API_SERVER_KEY` |
| `serve.py` | `/hermes/v1/*` proxy (Bearer inject, SSE passthrough, `usage`/`tool.progress` parse), `/hermes/health` |
| `claude-client.jsx` | Register `hermes` provider as default; keep others selectable; map tool-progress events |
| `agent_runner.jsx` | Route office-agent actions to `hermes`; thread Hermes opts through `ask()` |
| `hermes-console.jsx` *(new)* | JSON-RPC-over-WS client + themed renderer |
| `views.jsx` | New "Hermes Console/Fleet" view + `VIEW_LABELS` entry |
| `ui.jsx` / `modals.jsx` | Hermes agent cards; integrate into HireModal |
| `styles.css` / `DESIGN_SYSTEM.md` | Hermes theme tokens + component docs |
| Caddy template | Routes for `…/hermes/v1/*` and `wss …/api/ws`, per-principal auth |

---

## Appendix — caveats & open items
- **Version pinning:** most config/feature claims read from `main` docs; only the
  2026-05-29 release + the `HERMES_DASHBOARD_INSECURE` change are strictly v0.15.1-tagged.
  Treat surfaces as current-and-stable; re-verify exact strings against the deployed tag.
- **`supports_vision` placement** differs between docs (model block) and
  `cli-config.yaml.example` (under `auxiliary.vision`) — verify against the running build.
- **Refuted, do NOT design around:** a `hermes proxy` OAuth-backed local OpenAI proxy
  (does not exist); and the "exactly two entry points" taxonomy (richer than that).
- **Verify before billing:** token-accounting fidelity for streaming/tool-call turns.
- **ACP mapping** to ApprovalTray is deferred; confirm scope if/when adopted.
