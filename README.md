# CafresoHQ

CafresoHQ is an **ICP-native** product with two faces sharing one Internet Identity:

- **Cafreso Pages** (`cafreso.com`, `ai.cafreso.com`) — a SvelteKit dapp: consumer site (blog, forums, shop/subscriptions, governance, leaderboard) **and** the per-user AI-agent "HQ" SaaS.
- **The HQ browser app** (`hq.html`) — a pixel-art AI-agent command center backed by `serve.py` and a per-user OCI container.

State that *must* be trustless lives on Internet Computer canisters (identity, vetKeys-encrypted vault, content, billing); only what *can't* run on-chain (LLM inference, terminal/PTY, the agent runtime) runs on the OCI fleet.

---

## Subsystems

| Subsystem | Lives in | What it is |
|-----------|----------|------------|
| **SvelteKit control plane** | `frontend/` | Modern ICP-hosted app (asset canister `cafresoai_frontend`). `(pages)` routes = the consumer site; `(hq)` routes = the SaaS dashboard. Talks to the `cafresoai_keys` canister for vetKeys zero-knowledge vault encryption. |
| **HQ browser app** | `hq.html` + `*.jsx` (`app.jsx`, `views.jsx`, `ui.jsx`, `modals.jsx`, `missions.jsx`, …) | The agent command center. Bundled by esbuild (`scripts/build_ui_bundle.mjs`); also servable from the `cafresohq_ui` asset canister. |
| **Backend / proxy** | `serve.py` | Stdlib HTTP server: LLM proxy, vault, PTY/terminal, approvals. Listens on `PORT` (default **8787**). |
| **Fleet** | `oci-fleet/` | Per-user OCI container provisioning + the Caddy TLS gateway + Stripe oracle. `fleet-api.py` bridges the shell to containers. |
| **Canisters** | `src/` + `dfx.json` | `cafresoai_keys` (vetKeys, Motoko); Phase-2 `cafresohq_state` (on-chain per-user state) on a feature branch. |
| **Desktop / streaming** | `electron/`, `streaming/` | Electron wrapper + WebRTC streaming. |

> Architecture deep-dives: [`docs/AGENT_BRIEF.md`](docs/AGENT_BRIEF.md), [`docs/strategy/`](docs/strategy), [`docs/PHASE2_STATE_CANISTER.md`](docs/PHASE2_STATE_CANISTER.md), [`docs/SCALING_STRATEGY.md`](docs/SCALING_STRATEGY.md), [`docs/CAFRESOHQ_ARCHITECTURE_REVIEW.md`](docs/CAFRESOHQ_ARCHITECTURE_REVIEW.md).

## A note on naming

The project has accreted three names — here's the convention:

- **CafresoHQ** — the canonical product/repo name. Use this for new docs and user-facing copy.
- **cafresoai** — the canister/app-id prefix (`cafresoai_frontend`, `cafresoai_keys`, the SvelteKit app). Keep as-is; canister names are load-bearing.
- **Openclaw** / `openclawhq` — the *internal module namespace* of the HQ browser app (the `window.Openclaw*` globals wired between `hq.html` and the JSX bundles) and a legacy directory name in old paths. Load-bearing in code; **don't rename** — just know it refers to the HQ app internals.

(A blanket rename would touch 140+ files and break the `window.Openclaw*` global contract and canister ids, so we document the mapping instead.)

## Ecosystem canisters

| Canister | ID | Role |
|----------|----|------|
| `cafresoai_frontend` | `v4tdv-riaaa-aaaab-agtfa-cai` | Unified Pages+HQ frontend → **ai.cafreso.com** |
| `cafreso_pages` | `dqcmv-zqaaa-aaaab-agp2a-cai` | Same build, served to **cafreso.com** (legacy Pages canister we control) |
| `cafresoai_keys` | `vhw7q-lqaaa-aaaab-agthq-cai` | vetKeys vault key derivation |
| `cafresohq_ui` | `vhoil-eyaaa-aaaal-qxc7q-cai` | HQ browser-app assets |
| IndexCanister | `bek5d-2qaaa-aaaab-agqrq-cai` | blog/forum/products/orders/burns/leaderboard |
| Banking.Brave / Minegold | `cqyto-tiaaa-aaaau-agppa-cai` | II `derivationOrigin` anchor; `/mine` dapp |

## Local development

**SvelteKit frontend**
```bash
npm --prefix frontend install
npm --prefix frontend run dev      # prebuild syncs assets/ → static/assets/
```

**HQ browser app + backend**
```bash
python serve.py                    # http://localhost:8787  (set PORT to change)
# or, with the elevated vault tools enabled (edit the allowlist first):
bash start-elevated.sh
```

**Self-hosted container**
```bash
docker run -d --name cafresohq -p 8787:8787 \
  -v cafresohq-data:/data docker.io/anthonycf1/cafresoai-serve:latest
```

## Deploy

```bash
# Frontend → ai.cafreso.com (v4tdv) and cafreso.com (dqcmv)
npm --prefix frontend run build
dfx deploy cafresoai_frontend --network ic --identity default
dfx deploy cafreso_pages      --network ic --identity default

# HQ browser-app assets
dfx deploy cafresohq_ui --network ic --identity default
```

> Gateway/oracle deploy scripts read config from a gitignored `.env` — copy [`.env.example`](.env.example) and set `GATEWAY_IP` first.

## Conventions

- Frontend deploys use the **`default`** dfx identity (a controller), not `ic_admin`.
- PRs target the active integration branch (**`merge/pages-cafresoai`**), not `master`.
- Secrets and machine-specific config go in `.env` / `oci-fleet/.env` (gitignored), never committed.
