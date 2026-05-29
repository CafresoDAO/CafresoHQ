# 03 · MVP Roadmap — From Current State to a Launchable, DAO‑Fundable Ecosystem

> **Status:** Draft for founder review · Generated 2026-05-29
> **Goal (founder's words):** "get as close to MVP for our entire ecosystem of apps" and "fully launch CafresoHQ so we can work towards raising ICP for our DAO."
> **How to read this:** §1 is the honest current state. §2 names the few things actually blocking a launch. §3 defines the smallest coherent MVP. §4 is the phased plan. §5 is a per‑app checklist. Tokenomics/SNS specifics live in `04`; market positioning in `02`.

---

## 1. Current state — what's real vs. what's a mockup

Grounded in the code as of this review. **The cryptographic and identity foundation is genuinely strong and already on mainnet.** The gaps are in *making the agents do real work*, *billing for compute*, and *wiring the apps into one ecosystem*.

| Layer | Status | Evidence / Notes |
|---|---|---|
| ICP frontend canister | ✅ Live | `cafresoai_frontend` = `v4tdv-riaaa-aaaab-agtfa-cai` |
| vetKeys vault canister | ✅ Live, production‑quality | `cafresoai_keys` = `vhw7q-lqaaa-aaaab-agthq-cai`; real threshold BLS12‑381, ~26.15B cycles/derive (~$0.03/day/user) |
| Internet Identity auth + ecosystem derivation | ✅ Working | `frontend/src/lib/stores/auth.js`; derives shared principal via Banking.Brave origin |
| Zero‑knowledge vault (E2E encrypt) | ✅ Working | `crypto/vaultKey.js` (HKDF + AES‑GCM), `stores/vault.js` (encrypted index, 200MB cap) |
| Frontend shell + routes (dashboard, chat, vault, search, settings) | ✅ Working | SvelteKit; stores wired |
| Chat → Claude | ✅ Working (needs endpoint) | `routes/chat`, proxied via `serve.py` (Anthropic/LM Studio/Ollama/OCA) |
| Banking.Brave / Minegold backend | ✅ Mostly built, live | `minegold_backend` = `c626g-iyaaa-aaaau-agpoa-cai`; deposits/exchange/bridge logic; admin dashboard missing |
| OCI fleet provisioning | ⚠️ Partial — **blocker** | `oci-fleet/fleet-api.py` + `fleet-manager.py` can spawn containers (1 OCPU/6GB); **no billing/metering, DNS not wired, job state in‑memory** |
| Caddy per‑user gateway (`/u/{slug}`) | ⚠️ Partial — **blocker** | `caddyfile.template` ready; `gateway.public_hostname` unset → falls back to raw IP |
| Shared‑principal identity across domains | ❌ Broken — **blocker** | `frontend/static/.well-known/ii-alternative-origins` is **empty** → "one login, every app" doesn't actually work yet |
| HQ agent execution | ❌ Mock only — **blocker for positioning** | `mock-data.jsx` `INITIAL_AGENTS` (Mira/Kip/Bop) are hardcoded UI state; `// INTEGRATE:` markers; no live task dispatch |
| HQ missions / workflows / graph | ❌ Stubbed | demo seed data; graph view designed not built |
| SNS / governance / token ledger canister | ❌ Not started | only frontend + keys canisters exist today |
| Unified design tokens across apps | ⚠️ Diverged | see `05-design-cohesion` |

**Bottom line:** you are ~70% of the way to a *private encrypted AI workspace on ICP* and ~25% of the way to the *"AI agent command center / agent team"* that the marketing promises. The fastest credible launch leans into the former while making one slice of the latter real.

---

## 2. The launch‑blocking gaps (the short list)

Everything else is polish. These five are the difference between "demo" and "a stranger can sign up and get value."

1. **Wire the ecosystem identity** — populate `ii-alternative-origins` so the shared principal works across `cafreso.com`, `ai.cafreso.com`, `hq.cafreso.com`, Banking.Brave, `minegold.defi`. Without this the "one ecosystem" story is fiction. *(S)*
2. **Make the HQ agent loop real** — replace at least one mock agent path with a live one: user assigns a task → it dispatches to Claude in their container → result + receipt persisted to the vault. One real loop beats five fake sprites. *(L)*
3. **Fleet: provisioning + metering + a paywall** — finish DNS/Caddy routing, persist job state, meter cycles/OCI cost per user, and gate provisioning behind *something* (free‑tier quota or payment). You cannot open the doors to the public while every signup spends your money invisibly. *(L)*
4. **Cost/usage visibility** — surface per‑user compute + cycle spend in the dashboard. This is both a trust feature and the precondition for any subscription or token‑credit model (`02`, `04`). *(M)*
5. **A real onboarding path** — a logged‑out visitor needs a 3‑step path to first value (sign in → provision/connect → run one agent task) without reading docs. Today the dashboard assumes you already know what an endpoint is. *(M)*

`S` = hours–1 day · `M` = a few days · `L` = 1–2+ weeks.

---

## 3. MVP definition — the smallest thing worth launching

> **CafresoHQ MVP = "Your private AI workspace you actually own, on the Internet Computer."**
> Sign in with Internet Identity → get (or connect) your private container → chat with Claude and run a small set of real agent tasks → everything you create is end‑to‑end encrypted in a vault only you can decrypt → one cohesive Cafreso ecosystem around it.

What's deliberately **in** the MVP:
- II login + working shared‑principal ecosystem nav.
- Encrypted vault (already done — this is your wedge; lead with it).
- Claude chat in your own container.
- **One** genuinely working agent task type (e.g. "research a topic → write a vault note," since the ICP‑researcher charter already models this loop end‑to‑end).
- Provisioning with a free‑tier quota and visible usage.

What's deliberately **deferred** (post‑MVP):
- Multi‑agent "office" orchestration, missions, workflow builder, vault graph 3D view.
- The pixel‑art office can ship as a *view* (it's charming) but isn't the product.
- Standalone Minegold governance.

This framing lets you launch in weeks, not quarters, and gives the DAO a *real product* to point at — the single biggest predictor of a successful SNS raise (see `04` case studies).

---

## 4. Phased roadmap

### Phase 0 — "It's one product" (days)
- [ ] Populate `ii-alternative-origins` on Banking.Brave with all ecosystem domains; verify shared principal end‑to‑end.
- [ ] Wire `gateway.public_hostname` + Caddy TLS so `hq.cafreso.com/u/{slug}` resolves publicly (no raw IPs).
- [ ] Extract a shared token file; port `EcosystemNav` into HQ; soften HQ chrome (`05-design-cohesion`).
- [ ] Standardize wordmark/favicons across all 5 apps.

**Exit:** sign in once, move between all apps with the same identity and a consistent brand.

### Phase 1 — "The agent does real work" (1–2 weeks)
- [ ] Replace one `// INTEGRATE:` mock path in `mock-data.jsx`/agent runner with a live dispatch to Claude in the user's container.
- [ ] Persist task state + receipts to the encrypted vault (not just `localStorage`).
- [ ] Build the 3‑step onboarding (sign in → provision/connect → run first task) with empty/loading/error states.
- [ ] Make the dashboard explain itself to a first‑time user (what's an endpoint, why provision).

**Exit:** a new user with no context completes one real agent task and sees the result saved in their vault.

### Phase 2 — "We can open the doors safely" (1–2 weeks, overlaps Phase 1)
- [ ] Persist fleet job state (file/DB, not in‑memory) and add provisioning rate‑limits.
- [ ] Meter per‑user OCI cost + canister cycles; expose a usage endpoint from `fleet-api.py`.
- [ ] Free‑tier quota enforcement (e.g. N agent‑hours / M vault‑MB) with graceful degradation.
- [ ] Usage/cost panel in the dashboard.
- [ ] Basic observability (health, provision success rate, cost per active user).

**Exit:** a stranger can self‑serve a container without you losing money silently; you can see unit economics.

### Phase 3 — "It makes money / has token utility" (2–3 weeks)
- [ ] Choose monetization (see `02`/`04`): fiat subscription, ICP/ckBTC top‑ups, **and/or** $CF compute credits.
- [ ] Wire a payment/credits ledger (ICRC‑1 token or off‑chain meter → on‑chain settlement) to gate compute beyond free tier.
- [ ] Define and implement **token utility**: $CF buys compute credits / unlocks tiers / votes on roadmap + treasury‑funded free tier. *(This closes the "what is the token for?" gap flagged in the team's own tokenomics analysis.)*

**Exit:** the DAO has a defensible value‑capture story: the token pays for the thing the product actually does.

### Phase 4 — "SNS‑ready" (parallel track; see `04` for detail)
- [ ] Security audit of `cafresoai_keys` (and any payment/ledger canister) by a recognized ICP auditor.
- [ ] Add NNS Root as co‑controller of dapp canisters; set fallback controllers; test an upgrade round‑trip under SNS control.
- [ ] Finalize & publish tokenomics (reconcile **100M / 15‑30‑55** vault model vs **$CF 46/27/22** public page — `04`), dev vesting + dissolve‑delay table, swap parameters, NF stance.
- [ ] Open the forum thread, complete ≥1 revision round, publish a decentralization roadmap, and size ≥90 days cycle runway.

**Exit:** you can submit a credible `CreateServiceNervousSystem` proposal pointing at a live, audited, revenue‑generating product.

---

## 5. Per‑app MVP checklist (whole ecosystem)

| App | Role | MVP must‑haves | Status |
|---|---|---|---|
| **Cafreso Pages** (`cafreso.com`) | Storefront + dev log + community front door | Working checkout (coffee/sub), dev‑log live, ecosystem nav, link to AI/HQ | Storefront/checkout partial; admin/treasury view missing |
| **CafresoAI** (`ai.cafreso.com`) | Control plane / shell | II login, ecosystem nav, vault, chat, provisioning + usage, onboarding | Shell done; provisioning/billing + onboarding are the gaps |
| **CafresoHQ** (`hq.cafreso.com`) | Per‑user agent workspace | One real agent loop, vault‑persisted state, cohesive chrome | Agents mock; chrome diverged |
| **Minegold.defi / Banking.Brave** (one app) | II anchor + treasury/yield — Banking.Brave is the homepage, Minegold.defi the protocol under that domain | Add custom domains to `ii-alternative-origins` (done); show DAO/treasury balances; admin dashboard | Backend live `c626g-…`; frontend canister `cqyto-…` = II anchor; admin UI missing |

---

## 6. Critical path (sequencing)

```
Phase 0 (identity + cohesion)  ─┐
                                ├─►  Phase 1 (real agent loop) ─┐
Phase 2 (fleet billing/meter) ─┘                               ├─► Phase 3 (monetize + token utility) ─► Phase 4 (SNS launch)
                                                                │
                                          (Phase 2 can start in parallel with Phase 1)
```
Phase 0 is the unlock for everything (and is mostly small). Phases 1 and 2 are the heavy lifts and can run in parallel. Phase 3 depends on metering (2). Phase 4 depends on a live, audited, ideally revenue‑generating product (1–3) — **do not raise before the product is real**; the case studies in `04` are unanimous that pre‑launch product‑market fit is the top predictor of SNS success.

---

## 7. Top risks

- **Per‑user containers are expensive at scale.** A free tier funded by treasury can bleed cash fast (the team's own tokenomics note flags treasury starvation). Metering + quotas (Phase 2) and a credible paid tier (Phase 3) are not optional. Consider a "bring‑your‑own‑compute / local companion" free path (already supported via `serve.py` localhost detection) to cap hosted‑tier cost.
- **Raising before product = the #1 DAO failure mode.** See `04`.
- **The "agent team" promise vs. mock reality** is a credibility risk if you market multi‑agent orchestration before one agent works. Right‑size the messaging to what Phase 1 actually ships.
- **Scope sprawl across 5 apps.** The shared‑identity layer (Phase 0) is what lets you launch them as one story without finishing all five; resist polishing every app before launch.

---

*Companion docs: `00-executive-summary`, `01-research-icp-dao-and-agentic-market`, `02-positioning-and-mass-accessibility`, `04-sns-tokenomics-decisions`, `05-design-cohesion`.*
