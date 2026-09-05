# CafresoHQ

CafresoHQ is an **ICP-native** product with two faces sharing one Internet Identity:

- **Cafreso Pages** (`cafreso.com`, `ai.cafreso.com`) — a SvelteKit dapp: consumer site (blog, forums, shop/subscriptions, governance, leaderboard) **and** the per-user AI-agent "HQ" SaaS.
- **The HQ browser app** (`hq.html`) — a pixel-art AI-agent command center backed by `serve.py` and a per-user OCI container.

State that *must* be trustless lives on Internet Computer canisters (identity, vetKeys-encrypted vault, content, billing); only what *can't* run on-chain (LLM inference, terminal/PTY, the agent runtime) runs on the OCI fleet.

---

## Subsystems

| Subsystem | Lives in | What it is |
|-----------|----------|------------|
| **SvelteKit control plane** | **a separate repo** — `../cafreso-pages` | Modern ICP-hosted app (asset canister `cafresohq_frontend`). `(pages)` routes = the consumer site; `(hq)` routes = the SaaS dashboard. Talks to the `cafresohq_keys` canister for vetKeys zero-knowledge vault encryption. It used to live in `frontend/` here; that directory was deleted in `8dbcc6f` and is **not** in this checkout. |
| **HQ browser app** | `hq.html` + `*.jsx` (`app.jsx`, `views.jsx`, `ui.jsx`, `modals.jsx`, `missions.jsx`, …) | The agent command center. Bundled by esbuild (`scripts/build_ui_bundle.mjs`); also servable from the `cafresohq_ui` asset canister. |
| **Backend / proxy** | `serve.py` | Stdlib HTTP server: LLM proxy, vault, PTY/terminal, approvals. Listens on `PORT` (default **8787**). |
| **Canisters** | `src/` + `dfx.json` | `cafresohq_keys` (vetKeys, Motoko); Phase-2 `cafresohq_state` (on-chain per-user state) on a feature branch. |
| **Desktop** | `electron/` | Electron wrapper. |
| **Container image** | `docker/` | The serve.py container image (Dockerfile, entrypoint, Hermes bootstrap) used by `docker-compose.local.yml` and the fleet. |

> Fleet provisioning, the Caddy gateway, Stripe oracle, and WebRTC streaming live in the separate **cafreso-fleet** repo.

> Architecture deep-dives: [`docs/AGENT_BRIEF.md`](docs/AGENT_BRIEF.md), [`docs/strategy/`](docs/strategy), [`docs/PHASE2_STATE_CANISTER.md`](docs/PHASE2_STATE_CANISTER.md), [`docs/CAFRESOHQ_ARCHITECTURE_REVIEW.md`](docs/CAFRESOHQ_ARCHITECTURE_REVIEW.md).

## A note on naming

The project has accreted three names — here's the convention:

- **CafresoHQ** — the canonical product/repo name. Use this for new docs and user-facing copy.
- **cafresohq** — the canister/app-id prefix (`cafresohq_frontend`, `cafresohq_keys`, the SvelteKit app). Keep as-is; canister names are load-bearing.
- **CafresoHQ** / `cafresohq` — the *internal module namespace* of the HQ browser app (the `window.CafresoHQ*` globals wired between `hq.html` and the JSX bundles) and a legacy directory name in old paths. Load-bearing in code; **don't rename** — just know it refers to the HQ app internals.

(A blanket rename would touch 140+ files and break the `window.CafresoHQ*` global contract and canister ids, so we document the mapping instead.)

## Ecosystem canisters

| Canister | ID | Role |
|----------|----|------|
| `cafresohq_frontend` | `v4tdv-riaaa-aaaab-agtfa-cai` | Unified Pages+HQ frontend → **ai.cafreso.com** |
| `cafreso_pages` | `dqcmv-zqaaa-aaaab-agp2a-cai` | Same build, served to **cafreso.com** (legacy Pages canister we control) |
| `cafresohq_keys` | `vhw7q-lqaaa-aaaab-agthq-cai` | vetKeys vault key derivation |
| `cafresohq_ui` | `vhoil-eyaaa-aaaal-qxc7q-cai` | HQ browser-app assets |
| IndexCanister | `bek5d-2qaaa-aaaab-agqrq-cai` | blog/forum/products/orders/burns/leaderboard |
| Banking.Brave / Minegold | `cqyto-tiaaa-aaaau-agppa-cai` | II `derivationOrigin` anchor; `/mine` dapp |

## Local development

**SvelteKit frontend** — *not in this repo.* It lives in the sibling
`cafreso-pages` checkout; `frontend/` was deleted here in `8dbcc6f`, so these
commands only work from that repo:
```bash
cd ../cafreso-pages && npm install && npm run dev
```

**HQ browser app + backend**
```bash
npm install                        # once — esbuild + the graph engine
npm run build                      # required: hq.html is 500 until dist-ui/ exists
python3 serve.py                   # serve.py prints the URL *and* scheme — it is
                                   # https:// whenever mkcert is installed
                                   # (set PORT to change; default 8787)
# or, with the elevated vault tools enabled (edit the allowlist first):
bash start-elevated.sh
```

For a **complete** local office, prefer the launcher — bare `serve.py` does not
start a Hermes gateway, so the default brain has nothing listening on
`127.0.0.1:8642` and every message fails:
```bash
sh Start-CafresoHQ.sh                # serve.py + the Hermes gateway + TLS notes
```

**What a local run exposes.** `serve.py` binds `127.0.0.1` only, so the
`📱 Mobile / LAN` address it prints is *not* reachable from your phone unless
you also set `CAFRESOHQ_BIND` (and, off loopback, `CAFRESOHQ_API_KEY`). The
`/fs` read routes are keyless by design and default to serving your **home
directory** — see `CAFRESOHQ_ALLOWED_DIRS` in [`.env.example`](.env.example)
and narrow it before running the office on a machine you share.

**Self-hosted container**
```bash
docker run -d --name cafresohq -p 8787:8787 \
  -v cafresohq-data:/data docker.io/anthonycf1/cafresoai-serve:latest
```

## Deploy

```bash
# Frontend → ai.cafreso.com (v4tdv) and cafreso.com (dqcmv)
# Both canisters ship from the SEPARATE cafreso-pages repo, via its own script
# (it deploys the pair together; deploying one alone leaves the sites skewed):
cd ../cafreso-pages && ./scripts/deploy.sh

# HQ browser-app assets
dfx deploy cafresohq_ui --network ic --identity default
```

> Machine-specific config lives in a gitignored `.env` — copy [`.env.example`](.env.example). Gateway/oracle deploy config (`GATEWAY_*`, `OCI_*`, …) moved to the **cafreso-fleet** repo with the scripts that read it.

## Conventions

- Frontend deploys use the **`default`** dfx identity (a controller), not `ic_admin`.
- PRs target the active integration branch (**`merge/pages-cafresohq`**), not `master`.
- Secrets and machine-specific config go in `.env` (gitignored), never committed.
