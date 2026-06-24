# Agent Brief — CafresoHQ

Self-orientation doc for autonomous agents asked to study this repo and propose
upgrades. Read this first, then `docs/strategy/`. It captures what's already in
flight so you build on it instead of re-discovering it.

---

## 1. What this repo is

A unified **SvelteKit** dapp + **Motoko** canisters + an **OCI** compute fleet:

- `frontend/` — one SvelteKit app (adapter-static SPA), two route groups:
  - `(pages)` → **cafreso.com** "Pages": blog, forums, shop/subscriptions, governance, leaderboard, profile/wallet.
  - `(hq)` → **ai.cafreso.com** "CafresoHQ": the per-user AI agent SaaS.
- `src/cafresohq_keys/` — vetKeys (BLS12-381 threshold) vault key derivation (Motoko).
- `src/cafresohq_state/` — **new**, Phase 2 on-chain per-user state (HQ docs + vault ciphertext). Scaffolded, **not yet deployed** (PR #6).
- `oci-fleet/` — per-user container fleet, Caddy TLS gateway, Stripe oracle. The only load-bearing off-chain compute (LLM inference, PTY/terminal, agent runtime).
- `serve.py` / `scripts/` — container API + HQ-UI asset build.

**Identity:** one Internet Identity principal across the ecosystem via a shared
`derivationOrigin` anchored at Banking.Brave (`cqyto-…`). See `frontend/src/lib/stores/auth.js`.

**Architectural direction:** *maximize on-chain* — keep only what must be off-chain
(LLM inference, PTY, agent runtime) on OCI; move state/registry/metering/governance
onto canisters so the container becomes stateless ("cattle, not pets"). Full plan in
`docs/strategy/` and the Phase 2 design in `docs/PHASE2_STATE_CANISTER.md`.

---

## 2. Branch model — READ BEFORE OPENING PRs

- GitHub default branch is `master`, but the **active integration branch is
  `merge/pages-cafresohq`**. All recent PRs target it. **Base your PRs on
  `merge/pages-cafresohq`, not `master`.**
- One concern per branch/PR (the existing PRs follow this).

## 3. Open PRs (don't duplicate these)

| PR | Branch | What |
|----|--------|------|
| #1 | fix/dockerfile-build-ui | Docker builds the HQ UI bundle (fixed the original 500) |
| #2 | fix/embed-csp-localhost | CSP: allow framing the local HQ container |
| #3 | feat/local-custom-port | Local Companion on a custom port |
| #4 | feat/homepage-live-data | Live activity data on the homepage |
| #5 | feat/pages-polish | 23 launch-quality polish quick-wins |
| #6 | feat/phase2-state-canister-scaffold | On-chain per-user state canister (deploy-gated) |
| #7 | fix/frontend-assets-404 | `/assets/*` 404 fix + durable asset sync |

---

## 4. Ecosystem canister map

| Canister | ID | Role | Status |
|----------|----|------|--------|
| cafresohq_frontend | `v4tdv-riaaa-aaaab-agtfa-cai` | Unified Pages+HQ frontend → **ai.cafreso.com** | ✅ active pipeline |
| (old Pages) | `dqcmv-zqaaa-aaaab-agp2a-cai` | Pre-merge Pages canister → **cafreso.com** | ⚠️ superseded, retire (see §5) |
| cafresohq_keys | `vhw7q-lqaaa-aaaab-agthq-cai` | vetKeys vault key derivation | ✅ live |
| cafresohq_ui | `vhoil-eyaaa-aaaal-qxc7q-cai` | HQ UI asset canister | ✅ live |
| cafresohq_state | *(not deployed)* | Phase 2 per-user state (HQ docs + vault ciphertext) | 🟡 PR #6, deploy-gated on cycles |
| IndexCanister | `bek5d-2qaaa-aaaab-agqrq-cai` | blog/forum/products/orders/burns/leaderboard | ✅ live |
| Banking.Brave / Minegold | `cqyto-tiaaa-aaaau-agppa-cai` | II derivationOrigin anchor; `/mine` dapp | ✅ live |
| Blog/devlog content | `dff5y-yyaaa-aaaab-agpzq-cai` | authoritative blog content (per `lib/data/blog.js`) | ✅ live |
| ICP ledger | `ryjl3-tyaaa-aaaaa-aaaba-cai` | ICRC-1 (mainnet ICP) | external |
| $nanas ledger | `mwen2-oqaaa-aaaam-adaca-cai` | ICRC-1 $nanas | ⚠️ verify (see §6) |
| sGLDT ledger | `i2s4q-syaaa-aaaan-qz4sq-cai` | ICRC-1 sGLDT | external |
| ckUNI ledger | `ilzky-ayaaa-aaaar-qahha-cai` | ICRC-1 token | external |
| OpenChat community | `cpkbm-lyaaa-aaaaf-bkcwa-cai` | external community link (oc.app) | external |

(`c626g-iyaaa-aaaau-agpoa-cai` also appears once — identity unverified.)

---

## 5. cafreso.com vs ai.cafreso.com — the divergence

Two SEPARATE canisters serve the two domains:

- **ai.cafreso.com → `v4tdv`** — the unified frontend, built **2026-06-20**. All
  current work (PRs #4/#5/#7, homepage live data, polish) deploys here.
- **cafreso.com → `dqcmv`** — the *old* Pages-only canister, built **2026-05-08**
  (~47 days stale). It is **not** in `dfx.json`/`canister_ids.json`; nothing in the
  active pipeline deploys to it.

So cafreso.com isn't getting updates because it's pinned to a superseded canister,
not because the build pipeline is broken. **Remediation (founder-run, already TODO
in `docs/strategy/07-pages-cafresohq-merge.md` step 2):** register `cafreso.com` as a
custom domain on `v4tdv` + repoint DNS (`CNAME` + `_canister-id` TXT) from `dqcmv` →
`v4tdv`, then retire/redirect `dqcmv`. `ic-domains` on `v4tdv` already lists both
hosts. This is a DNS/boundary-node action — **not a code change** — so an agent
should *prepare* it (exact DNS records, verification steps) but a human runs the cutover.

---

## 6. Highest-leverage upgrade threads (prioritized)

1. **Idle auto-stop + start-on-login** 🔑 — biggest cost lever (per `docs/SCALING_STRATEGY.md`). Depends on the stateless container from Phase 2 (PR #6) being lossless. Wire `reap-idle` (`docs/LAUNCH_TODO.md` #4).
2. **Finish Phase 2 state migration** — deploy `cafresohq_state`, flip `PUBLIC_STATE_CANISTER=mirror`, backfill, then cut reads over. Makes the container truly stateless. See `docs/PHASE2_STATE_CANISTER.md`.
3. **Fleet-registry canister** — replace the race-prone flat `oci-fleet/fleet.json` (`LAUNCH_TODO` #5).
4. **Usage/metering canister** — `_record_hermes_usage` must use the *authenticated* principal, not a header → enables on-chain plan enforcement.
5. **Real governance / SNS** — `lib/data/governance.js` is "simulated votes"; the site positions as a DAO. At minimum fetch live proposals; ideally an on-chain governance canister.
6. **Gate `/fleet/provision`** — largest open surface (`LAUNCH_TODO` #1): session token + rate-limit.
7. **Kill the `search.cafreso.com` SPOF** — move semantic index into a canister/OCI; add a graceful fallback.
8. **$nanas ledger health** — `mwen2-…` reportedly not answering ICRC-1 queries; verify it's live before relying on burn/leaderboard reads.

## 7. User-owned blockers (agents cannot complete these)

- **Rotate leaked keys** — OpenRouter `sk-or-v1-…`, Groq `gsk_…` (`LAUNCH_TODO` #6). Do before public launch.
- **Top up the cycles wallet** to deploy `cafresohq_state` (PR #6).
- **cafreso.com → v4tdv DNS cutover** (§5).
- **Gateway VM access** — the Caddy gateway VM is currently locked out (key on an inaccessible build VM); Phase 3 gateway work depends on regaining access (serial console or rebuild from `oci-fleet/caddy-cloud-init.yaml`).
- **Replace the 9 placeholder images** with final artwork (`docs/ASSETS_NEEDED.md`).

## 8. Guardrails for agents

- **This is beta**; nothing critical is in prod, but still: no destructive prod canister
  ops, no emptying state, no `dfx canister delete`/`--mode reinstall` on live canisters.
- **DNS, payments, key rotation, custom-domain registration, cycles conversion** are
  founder-run. Prepare exact steps; don't execute.
- **Respect the off-chain boundary:** LLM inference, PTY/terminal, code-agent execution,
  and the Hermes runtime stay on OCI compute — the goal is a *stateless* container, not
  on-chain inference.
- **Deploy identity:** frontend deploys use the `default` dfx identity (a controller),
  not `ic_admin`.

## 9. Where to read more

`docs/strategy/` (roadmap + merge plan), `docs/PHASE2_STATE_CANISTER.md`,
`docs/SCALING_STRATEGY.md`, `docs/LAUNCH_TODO.md`, `docs/SAAS_MVP_PLAN.md`,
`docs/CAFRESOHQ_ARCHITECTURE_REVIEW.md`, `docs/ASSETS_NEEDED.md`.
