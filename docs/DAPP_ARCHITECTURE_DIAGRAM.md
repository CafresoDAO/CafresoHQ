# CafresoHQ — Dapp Architecture Diagram

> The full system as it runs **today** (post OCA-removal, OpenRouter default,
> Hermes runtime). ICP canisters for identity/UI + per-user OCI containers for
> compute, stitched by a Caddy gateway.

---

## 1. System overview (control plane → edge → compute)

```
                                   ┌──────────────────────────────────────┐
                                   │            INTERNET COMPUTER (ICP)     │
                                   │                                        │
  ┌──────────────┐  II login       │  ┌────────────────────────────────┐   │
  │   End user    │───────────────▶│  │ cafresohq_frontend  (canister)  │   │
  │  (browser)    │   derivation    │  │  ai.cafreso.com SvelteKit shell │   │
  └──────┬────────┘   origin →      │  │  • Internet Identity auth       │   │
         │            shared        │  │  • principal (ecosystem-shared) │   │
         │            principal     │  │  • fleetClient → /fleet/*       │   │
         │                          │  │  • vault E2E crypto (vetKeys)   │   │
         │                          │  └───────────────┬────────────────┘   │
         │                          │  ┌───────────────▼────────────────┐   │
         │                          │  │ cafresohq_keys (Motoko canister)│   │
         │                          │  │  zero-knowledge key/vault store │   │
         │                          │  └─────────────────────────────────┘   │
         │                          └──────────────────────────────────────┘
         │
         │  iframes  https://hq.cafreso.com/u/<slug>/hq.html      slug = sha256(principal)[:16]
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  CADDY GATEWAY  (OCI VM · hq.cafreso.com · TLS/Let's Encrypt)                  │
│    /u/<slug>/*  → reverse_proxy  container:8787   (per-user routes)            │
│    /fleet/*     → fleet-api.py :8080  (provision/lookup)                       │
│    ⚠ no per-request auth yet  (see CONTAINER_AUTH_DESIGN.md — beta gap)         │
└──────────────────────────────────┬────────────────────────────────────────────┘
                                    │  HTTP  (also reachable via container public IP — beta)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PER-USER OCI CONTAINER INSTANCE   (CI.Standard.A1.Flex · ARM64 · 1 vCPU/6 GB) │
│  Debian 12 (bookworm-slim) · Python 3.11 · Node 20                             │
│                                                                                │
│  entrypoint.sh ── starts TWO processes ──────────────────────────────────┐    │
│                                                                            │    │
│   ① serve.py  (HTTP :8787, PID 1)          ② hermes gateway (127.0.0.1)    │    │
│   ┌───────────────────────────────┐         ┌──────────────────────────┐  │    │
│   │ serves hq.html + .jsx (HQ app)│         │ OpenAI-compat API :8642  │  │    │
│   │ /hermes/v1/* ─proxy(+key)────▶│────────▶│  runs Hermes agent loop  │  │    │
│   │ /hermes/model  (quick-switch) │         │  toolset · memory · cron │  │    │
│   │ /hermes/capability (lite/full)│         └────────────┬─────────────┘  │    │
│   │ /hermes/openrouter-key (rec.) │                      │ HTTPS          │    │
│   │ /vault/*  ──▶ OCI Object Store │                      ▼                │    │
│   │ /claudecode /cafresohq /codex  │         ┌──────────────────────────┐  │    │
│   │ /terminal/pty (WebSocket+PTY) │         │  OpenRouter (DEFAULT)     │  │    │
│   │ /approvals/external/* (tray)  │         │  free open-weights:       │  │    │
│   │ _record_hermes_usage (meter)  │         │  gpt-oss-120b / nemotron  │  │    │
│   └───────────────────────────────┘         │  / hermes-3-405b / llama  │  │    │
│   subprocess CLIs (BYOK / elevated):         └──────────────────────────┘  │    │
│     claude (Claude Code) · codex (OpenAI)                                   │    │
│   └────────────────────────────────────────────────────────────────────────┘  │
│   /data volume: hq-state/ · vault/ · hermes/ (config.yaml, .env, memories, cron)│
└──────────────────────────────────┬────────────────────────────────────────────┘
                                    │ OCI SDK (provision/start/stop/delete)
                                    ▼
        fleet-manager.py (CLI) · fleet-api.py (HTTP) · fleet.json (registry)
        builds+pushes ARM64 image → OCIR → pulled per container
```

---

## 2. Request data flow — a chat message

```
1. User types in HQ app (iframe)        app.jsx → window.CafresoHQClient.stream()
2. claude-client.jsx                     provider='hermes' → POST _API_BASE/hermes/v1/chat/completions
3. Browser → Caddy                       https://hq.cafreso.com/u/<slug>/hermes/v1/chat/completions
4. Caddy handle_path                     strips /u/<slug> → container:8787/hermes/v1/chat/completions
5. serve.py _hermes_proxy                injects Authorization: Bearer <API_SERVER_KEY> (server-side)
6. serve.py → hermes gateway             127.0.0.1:8642/v1/chat/completions
7. hermes gateway                        builds agent prompt (~13-17k tok) + tools → OpenRouter
8. OpenRouter                            free open-weights model → SSE tokens back
9. serve.py streams SSE back             taps final `usage` → _record_hermes_usage (per-principal)
10. tokens → browser                     onToken → chat UI renders live
```

## 3. Vault data flow (zero-knowledge)

```
HQ app (iframe)  ──postMessage(vault:*)──▶  SvelteKit shell (parent)
                                              │  E2E encrypt (vetKeys, principal-derived)
                                              ▼
                                            cafresohq_keys canister (ciphertext only)
   OR (fleet mode, large blobs):
HQ app ──▶ serve.py /vault/* ──▶ OCI Object Storage (bucket, per-user prefix)
```

## 4. Provisioning flow (new user)

```
ai.cafreso.com  ──POST /fleet/provision {principal}──▶  Caddy ──▶ fleet-api.py :8080
   fleet-api spawns: fleet-manager.py provision <principal>
      → OCI SDK create_container_instance (ARM64, pulls image from OCIR)
      → injects env: API_SERVER_KEY (per-principal), OPENROUTER_API_KEY, HERMES_HOME, OCI creds
      → polls ACTIVE → writes fleet.json (ip, slug, key)
      → re-renders Caddyfile (adds /u/<slug>/* route) → reload Caddy
   container boots: entrypoint → hermes-bootstrap (config.yaml: provider=openrouter)
                                → hermes gateway + serve.py
   shell iframes hq.cafreso.com/u/<slug>/hq.html  ✓
```

---

## 5. Component / responsibility table

| Layer | Component | Responsibility |
|---|---|---|
| Identity/UI | `cafresohq_frontend` (ICP) | II auth, ecosystem principal, shell, vault crypto, iframe host |
| Keys | `cafresohq_keys` (ICP Motoko) | zero-knowledge vault/key store |
| Edge | Caddy gateway (OCI VM) | TLS, per-user routing, fleet API proxy |
| Compute | OCI Container (per user) | the user's private HQ runtime |
| ↳ front door | `serve.py` :8787 | serve app, proxy LLM, vault, terminal, approvals, metering |
| ↳ agent | `hermes gateway` :8642 | Hermes agent loop, OpenAI-compat API |
| ↳ default LLM | OpenRouter | free open-weights (gpt-oss-120b default; switchable) |
| ↳ elevated | claude / codex CLIs | BYOK code agents inside the sandbox |
| Control | `fleet-manager.py` / `fleet-api.py` | provision/manage containers, render Caddy, build/push image |
| Registry | `fleet.json` | principal → container id, ip, slug, key, vault prefix |

---

## 6. Tech stack at a glance

- **Frontend:** React 18 (CDN + in-browser Babel, no bundler) · SvelteKit shell (ICP asset canister)
- **Identity:** Internet Identity, ecosystem-shared principal via derivationOrigin
- **Edge:** Caddy 2 (auto-TLS)
- **Container:** Debian 12 slim · Python 3.11 (`serve.py`, stdlib http.server + ThreadingMixIn) · Node 20 (Claude Code, Codex) · `hermes-agent==0.15.1`
- **LLM:** OpenRouter (default, free open-weights) · BYOK Anthropic/Gemini/Groq-paid/OpenAI · local LM Studio/Ollama
- **Cloud:** OCI Container Instances (ARM64 Ampere A1.Flex) · OCI Object Storage (vaults) · OCIR (images)
```
