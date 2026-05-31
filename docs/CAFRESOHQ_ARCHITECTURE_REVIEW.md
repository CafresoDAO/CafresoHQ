# CafresoHQ — Architecture Review & MVP Blueprint

> A senior-engineer reverse-engineering of the CafresoHQ codebase: current data
> flow, what's wrong, and a clean-architecture MVP to ship. Written after mapping
> `serve.py`, the `.jsx` HQ app, the SvelteKit shell, and the OCI fleet.

---

## 1. What CafresoHQ Is (reverse-engineered)

CafresoHQ is a **personal AI-agent command center** delivered as a per-user cloud
container, wrapped in a pixel-art "office" metaphor. Three tiers:

1. **Control plane** — `ai.cafreso.com`, a SvelteKit dapp on an ICP canister.
   Internet Identity login → ecosystem-shared principal → provisions/looks up the
   user's container → iframes the HQ app.
2. **Per-user container** — OCI Container Instance running `serve.py` (port 8787)
   *and* `hermes gateway` (Hermes Agent's OpenAI-compatible API on 127.0.0.1:8642).
   serve.py serves the HQ app, proxies LLM backends, hosts the vault, terminal,
   and approval bridge.
3. **Gateway** — a Caddy VM (`hq.cafreso.com`) TLS-terminating and routing
   `/u/<slug>/*` → the user's container, where `slug = sha256(principal)[:16]`.

### End-to-end data flow (happy path)

```
User → ai.cafreso.com (II login)
     → fleet-api /fleet/lookup or /fleet/provision  (principal → container)
     → SvelteKit iframes  hq.cafreso.com/u/<slug>/hq.html
        → Caddy → container:8787 (serve.py serves hq.html + .jsx)
     → HQ app boots (React via CDN+Babel), window.OpenclawClient.stream()
        → serve.py /hermes/v1/* proxy (injects API_SERVER_KEY)
        → hermes gateway :8642 → Groq (default) / Anthropic / Gemini (BYOK)
     → vault ops bridge via postMessage → SvelteKit → ICP canister (E2E encrypted)
        (or directly → serve.py /vault/* → OCI Object Storage in fleet mode)
```

### Current App Architecture Diagram (as-is)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ BROWSER                                                                    │
│                                                                            │
│  ai.cafreso.com (SvelteKit canister)        ── iframes ──┐                 │
│  ├─ Internet Identity auth (lib/stores/auth.js)          │                 │
│  ├─ fleetClient.js → /fleet/*                            │                 │
│  ├─ vault store (E2E crypto) ◄── postMessage bridge ──┐  │                 │
│  └─ routes/hq/app → <iframe src=.../hq.html>          │  │                 │
│                                                       │  ▼                 │
│  HQ app (CDN React + in-browser Babel, no bundler)    │  hq.html           │
│  ├─ window.OpenclawClient (claude-client.jsx) ────────┼─ stream()          │
│  ├─ window.OpenclawUI / V2 / Views / Modals (globals) │  (8 providers)     │
│  ├─ OfficeView pixel-art agents (ui.jsx + sprites)    │                    │
│  └─ custom events: openclaw:agentAction / :activity   │                    │
└───────────────────────────────────────────────────────┼────────────────── ┘
                         │ https                          │ postMessage(vault:*)
                         ▼                                 
┌─────────────────────────────────────────────────────────────────────────┐
│ CADDY GATEWAY (hq.cafreso.com)  — ⚠ NO AUTH on /u/<slug>/*                 │
│   /u/<slug>/*  → reverse_proxy  container:8787                             │
│   /fleet/*     → fleet-api.py :8080                                        │
└─────────────────────────────────────────────────────────────────────────┘
                         │
                         ▼  (also reachable DIRECTLY via public IP :8787 ⚠)
┌─────────────────────────────────────────────────────────────────────────┐
│ OCI CONTAINER (per user, 1 vCPU / 6 GB, ALWAYS ON)                         │
│  serve.py :8787  (BaseHTTPRequestHandler + ThreadingMixIn, ~5400 LOC)      │
│   ├─ /hermes/v1/* ─► hermes gateway :8642 ─► Groq/Anthropic/Gemini         │
│   ├─ /claudecode /openclaw /codex (spawn CLIs, SSE)  ← 4× duplicated       │
│   ├─ /vault/* ─► OCI Object Storage (no encryption at FS layer)            │
│   ├─ /terminal/pty (WebSocket + PTY)                                       │
│   ├─ /approvals/external/* (long-poll bridge → ApprovalTray)              │
│   └─ _record_hermes_usage → /data/hermes-usage.log (metering, unverified)  │
└─────────────────────────────────────────────────────────────────────────┘
                         │
                         ▼
              fleet.json (registry: principal → IP, api_server_key, vault_prefix)
              fleet-manager.py (OCI SDK) · fleet-api.py (HTTP bridge)
```

---

## 2. Findings

Severity: 🔴 critical · 🟠 high · 🟡 medium

### 2.1 Bad architecture decisions

| # | Finding | Sev |
|---|---|---|
| A1 | **Open containers** — every container has a public IP on `:8787` *and* the Caddy gateway has **no auth** on `/u/<slug>/*`. Slug is `sha256(public-principal)` — derivable, not secret. Anyone can reach any user's vault + agent. | 🔴 |
| A2 | **Secrets in `fleet.json`** — per-principal `api_server_key`, container IPs, OCI namespace, gateway SSH key path, all plaintext in one unencrypted file. One leak = full fleet breach. | 🔴 |
| A3 | **`fleet-api.py` dev-mode bypass** — if `FLEET_API_SECRET` is unset, *all* auth is skipped. A forgotten env var in prod opens provisioning to the world. | 🟠 |
| A4 | **Shared backend key** — all users share the operator's `GROQ/ANTHROPIC/GOOGLE` key. Rate limits + billing hit the operator; one compromised container exposes the key to all. | 🟠 |
| A5 | **No build pipeline** — HQ app ships raw `.jsx` transpiled by **in-browser Babel** on every load (~640 KB Babel + ~900 KB JSX). 1–2 s blank screen; far worse on mobile. | 🟠 |
| A6 | **Always-on per-user containers** — 1 vCPU/6 GB each (~$14/mo) with no auto-pause. 100 users ≈ $1.4 k/mo for mostly-idle compute. | 🟠 |
| A7 | **`shell=True` BASH tool** in `/tools/exec` — RCE surface if the tool allowlist includes Bash. | 🟠 |
| A8 | **HTTP/1.0 + `Connection: close`** forced — no keep-alive; a handler thread is tied up for the whole life of each streamed CLI/agent call. | 🟡 |

### 2.2 Duplicate logic

| # | Finding | Sev |
|---|---|---|
| D1 | **4× near-identical stream handlers** in serve.py: `_claudecode_stream`, `_openclaw_stream`, `_codex_stream`, `_terminal_stream` (~200 lines each). Same parse→validate→spawn→SSE shape. | 🟠 |
| D2 | **BYOK env-injection** repeated in all 4 stream handlers; **path validation** repeated 3×; **configure** endpoints duplicated. | 🟡 |
| D3 | **`_render_caddyfile()` + `_principal_slug()` duplicated** across `fleet-manager.py` and `fleet-api.py` — and they've **already diverged** (fleet-api's version is missing the `/u/<slug>` redirect rules, so a gateway-side re-render can silently break routing). | 🟠 |
| D4 | **Provider stream parsing** in `claude-client.jsx` repeats the SSE/`usage` decode across claudecode/openclaw/codex. | 🟡 |

### 2.3 Performance bottlenecks

| # | Finding | Sev |
|---|---|---|
| P1 | **In-browser Babel** (A5) — biggest user-facing perf hit. | 🟠 |
| P2 | **`useFileStored` sync storms** — every state mutation PUTs the *entire* collection to `/hq/state/*`. During token streaming this can fire 20–50 PUT/s of the full 80-msg history. | 🟠 |
| P3 | **Graph view O(n²)** force layout re-running on every mousemove with no rAF/worker — lags at 500+ vault nodes. | 🟠 |
| P4 | **Blocking subprocess per request** — each agent/CLI call holds its handler thread; concurrency caps out at the thread pool. | 🟠 |
| P5 | **Vault graph rebuilt every request** (no mtime cache); **emulated arm64 image builds** take 20–40 min. | 🟡 |

### 2.4 Scalability risks

| # | Finding | Sev |
|---|---|---|
| S1 | **`fleet.json` single-file registry** — concurrent provision/read races, no locking. Won't survive real signup volume. | 🟠 |
| S2 | **Single Caddy gateway = SPOF**; OCI **public-IP exhaustion** as the fleet grows. | 🟠 |
| S3 | **No metering→billing** — `hermes-usage.log` is written but never aggregated/enforced; principal is an unverified header (`X-User-Principal`), so usage is spoofable. | 🟠 |
| S4 | **Shared rate limits** (A4) cap the whole fleet at one key's quota. | 🟠 |

### 2.5 Maintainability issues

| # | Finding | Sev |
|---|---|---|
| M1 | **God files**: `views.jsx` ~6.4 k LOC, `app.jsx` ~3.8 k, `ui.jsx` ~3.4 k, `serve.py` ~5.4 k. No code-splitting, hard to test. | 🟠 |
| M2 | **`window.*` global namespaces** (OpenclawUI/V2/Views/...) instead of modules — zero static analysis, fragile load-order coupling, crashes if one script fails. | 🟠 |
| M3 | **Magic numbers everywhere** (TTLs, buffer caps, size limits) — should be named constants/config. | 🟡 |
| M4 | **Mutable globals without locks** (`_vault_root`, `_vault_backend`, …) — reconfigure races. | 🟡 |
| M5 | **Mock data (80 KB, 50+ agents) shipped to prod**; **capabilities inferred by string-matching role names**; **elevation enforced client-side only**. | 🟡 |
| M6 | **CRLITF/line-ending hazard** — `entrypoint.sh` shipped CRLF once and broke container boot (`exec format error`). Now fixed via `.gitattributes`. | 🟡 |

---

## 3. The MVP — Clean Architecture

**Principle:** keep the charming pixel-office UX and the per-user-container model,
but (a) make it *secure by default*, (b) introduce a *build pipeline*, (c) collapse
the duplication into clear layers, and (d) make cost/metering real.

### 3.1 Target architecture diagram

```
┌──────────────────────────── CONTROL PLANE (ai.cafreso.com) ────────────────────────────┐
│  SvelteKit canister                                                                       │
│   • Internet Identity → principal                                                         │
│   • mints SHORT-LIVED SESSION TOKEN (JWT, principal-bound)  ◄── the missing auth layer    │
│   • fleetClient → fleet-api                                                               │
│   • vault crypto (E2E)                                                                    │
│   • iframes hq.cafreso.com/u/<slug>/  (token in HttpOnly cookie)                          │
└───────────────────────────────────────────┬──────────────────────────────────────────────┘
                                             │ https + session cookie
                                             ▼
┌──────────────────────── EDGE (Caddy gateway, HA-ready) ────────────────────────┐
│  forward_auth → verifier(:9090): validate JWT, slug==sub  → 401 if not          │
│  then reverse_proxy → container PRIVATE ip:8787   (no public IPs)               │
│  /fleet/* → fleet-api (FLEET_API_SECRET REQUIRED; fail-closed)                  │
└───────────────────────────────────────────┬────────────────────────────────────┘
                                             ▼
┌──────────────────────── PER-USER CONTAINER (private IP only) ───────────────────┐
│  serve.py (refactored into layers)                                              │
│   ┌── http/         route table (dict dispatch, not if/elif cascade)            │
│   ┌── agents/       ONE _spawn_and_stream(cli, cwd, tools, byok) ← was 4×        │
│   ┌── providers/    hermes proxy (default) + selectable BYOK providers           │
│   ┌── vault/        single backend iface (OCI/FS/Obsidian) w/ locks             │
│   ┌── meter/        usage tap → emits to billing sink (principal from JWT)       │
│   └── security/     principal from verified token, allowdirs sandbox            │
│  hermes gateway :8642 → Groq (default) / Anthropic / Gemini (BYOK)              │
└──────────────────────────────────────────┬──────────────────────────────────────┘
                                            ▼
   Registry: SQLite (was fleet.json)   Secrets: OCI Vault (was plaintext)
   Idle containers AUTO-PAUSE          Metering → billing aggregation
```

### 3.2 MVP scope (ship this, defer the rest)

**In:**
- ✅ II login → container provision/lookup → themed HQ (already working)
- ✅ Hermes default runtime (Groq) + selectable BYOK providers (done)
- ✅ Vault (E2E via canister) + office view + chat + tasks
- 🔓 **Container auth** (JWT + Caddy `forward_auth`) — the one must-fix before public
- 🔒 Private IPs + secrets in OCI Vault
- 📊 Metering tap → simple per-principal usage aggregation

**Defer (post-MVP):** full build-pipeline migration, SQLite registry, HA gateway,
auto-pause, graph-view worker. (Tracked in §5 roadmap.)

### 3.3 Layering rules (the clean-architecture part)

1. **serve.py → package** (`hq_server/`): `http/` (routing), `agents/`,
   `providers/`, `vault/`, `meter/`, `security/`. One responsibility per module;
   the 4 stream handlers collapse into one parameterized `_spawn_and_stream`.
2. **Shared fleet lib** (`fleet/common.py`): `principal_slug()`, `render_caddyfile()`
   imported by *both* manager and api — kill the divergence (D3).
3. **Frontend build step** (Vite): pre-transpile `.jsx`, code-split per view,
   replace `window.*` globals with ES modules. Keep the exact same UI/themes.
4. **Config, not magic numbers**: a `config.py` / `config.js` with all TTLs, caps,
   URLs, and an injected `window._CAFRESO_ENV` for dev/stg/prod.
5. **Security is a layer, not a sprinkle**: principal comes only from the verified
   token; elevation checked server-side; no `shell=True`.

---

## 4. Security must-fixes (gate to public launch)

These are pulled forward because the app is currently open. Detail in
`docs/CONTAINER_AUTH_DESIGN.md`.

1. **Container auth** — JWT minted at II login, `HttpOnly` cookie, Caddy
   `forward_auth` verifier; slug stops being a credential.
2. **Private IPs** — `is_public_ip_assigned=False`; reach containers only via the
   gateway over the VCN.
3. **Secrets out of `fleet.json`** — `api_server_key` + OCI creds → OCI Vault;
   registry keeps only non-secret metadata.
4. **`fleet-api` fail-closed** — refuse to start without `FLEET_API_SECRET`.
5. **Per-user keys / BYOK** — stop forwarding the operator's shared backend key.

---

## 5. Phased roadmap

| Phase | Theme | Items |
|---|---|---|
| **0 ✅** | Hermes default | Groq default, OCA removed, Codex→OpenAI, HQ launch links fixed (done) |
| **1 🔓** | Lock it down | Container JWT auth + Caddy forward_auth; private IPs; secrets→OCI Vault; fleet-api fail-closed |
| **2 🧹** | De-dupe backend | `_spawn_and_stream` refactor; shared `fleet/common.py`; config module; locks on mutable globals |
| **3 ⚡** | Frontend pipeline | Vite build, code-split, ES modules, kill in-browser Babel; batch `useFileStored`; graph worker |
| **4 💵** | Cost + scale | Metering→billing; auto-pause idle containers; SQLite registry; HA gateway |
| **5 ✨** | Polish | Office "real HQ" revamp (see `OFFICE_REVAMP.md`); a11y; demo-data opt-in |

---

## 6. One-paragraph verdict

CafresoHQ is an ambitious, genuinely novel product — a private, containerized agent
HQ with a delightful pixel-office metaphor — built at impressive speed. The ideas and
the plumbing are sound. The gaps are the predictable ones for a fast build: **security
was deferred** (open containers, plaintext secrets), **the frontend skipped a build
step** (in-browser Babel, god files, window globals), and **the backend grew by
copy-paste** (4× stream handlers, duplicated fleet logic). None require a rewrite —
they're a focused hardening + refactor pass. Do Phase 1 (auth) before any public
exposure; everything else is incremental.
