# 06 · App Update TODO — Critique + Compounded Build Checklist

> **Status:** Living checklist · Generated 2026-05-29 · Compounds docs `00`–`05`.
> **Two parts:** **Part A** is an overall critique of the CafresoHQ app (what to fix and why). **Part B** is the prioritized, ordered TODO that turns the whole strategy package into a build checklist.
> **Severity:** 🔴 high · 🟡 medium · 🟢 low. **Priority:** P0 launch-blocking / safe quick-win · P1 needed for a credible MVP · P2 post-MVP / pre-SNS. **Effort:** S hours · M a day or two · L 1–2+ weeks.

## Ecosystem mapping (corrected)
The ecosystem is **~3 codebases + the per-user container**, all under `C:\Users\Anthony\Documents`:
- **Pages** — `Documents\CafresoPages` → `cafreso.com`
- **CafresoHQ** (control plane + embedded HQ) — `Documents\CafresoHQLocal` → `ai.cafreso.com`; per-user **HQ** containers at `hq.cafreso.com/u/{slug}`
- **Minegold.defi / Banking.Brave** — `Documents\minegold.defi` → frontend canister `cqyto-…` is the **Internet Identity anchor** (`derivationOrigin`). Banking.Brave is the app's homepage; Minegold.defi is the protocol hosted under the Banking.Brave domain.

## ✅ Safe wins already executed (2026-05-29)
- ✅ **`serve.py` portability** — replaced the hardcoded `C:\Users\Anthony\.claude\…\memory` default with a repo-relative `hq-state/memory` default (env `CAFRESOHQ_MEMORY_DIR` still overrides). `serve.py:~186`.
- ✅ **Ecosystem identity unblocked** — added the custom domains (`cafreso.com`, `ai.cafreso.com`, `hq.cafreso.com`, `minegold.defi`) to the Banking.Brave anchor's `ii-alternative-origins` (`minegold.defi\src\frontend\public\.well-known\`), keeping the existing canister URLs. **Purely additive.** Takes effect on the next deploy of the `cqyto-…` canister.
- ✅ **Workspace consolidation** — stray older duplicate moved out of `Downloads` into `Documents\_archive\` (reversible; see Track 0).
- ✅ **Docs corrected** — strategy docs updated for the Banking.Brave/Minegold mapping above.

---

## Part A — Critique of CafresoHQ (overall)

### Architecture & build
- 🔴 **No build step — Babel transpiles JSX in the browser.** `hq.html:36–49` loads React 18 **dev** UMD bundles + `@babel/standalone` from unpkg and runs every `*.jsx` via `<script type="text/babel">`. → multi-MB uncompressed payload, no minify/tree-shake, transpile-on-load latency, hard CDN dependency, dev-mode React in production. *Fix:* a real bundler (Vite) → minified prod build; keep `serve.py` as dev/proxy.
- 🟡 **Monolithic files** — `views.jsx` 6,394 LOC, `styles.css` 7,817, `app.jsx` 3,754, `ui.jsx` 3,367, `modals.jsx` 1,936. *Fix:* split by feature with the bundler migration.
- 🟡 **`window`-global module wiring** (`app.jsx:6–10`). One failed script → cascading `undefined`. *Fix:* ES module imports once bundled.

### Duplication & data integrity
- 🟡 **Two vault implementations** — root app writes plaintext via `/vault/note`; the SvelteKit frontend (`frontend/src/lib/stores/vault.js`) is the real E2E-encrypted client; the root app is embedded as an **iframe** bridged by `postMessage`. No conflict resolution. *Fix:* encrypted store = single source of truth; HQ writes via the bridge.
- 🟡 **`postMessage` origin `'*'`** (`frontend/src/routes/app/+page.svelte` ~line 61). *Fix:* pin to the container origin.

### "Real vs mock" product gaps
- 🔴 **Agents / missions / tasks aren't durably persisted** — hired agents are in-memory (only the 3 seed agents survive reload, `mock-data.jsx`); missions read seed data; tasks use `useFileStored` (`app.jsx:49`) → localStorage + local `/hq/state/`, lost on container restart. *Fix:* persist to the encrypted vault / a state endpoint + an agent registry. **This is the gap between "demo" and "product."**

### Security & ops (flag)
- 🔴 **`subprocess.run(arg, shell=True)`** for the BASH tool (`serve.py:~2258`). Gated by `CAFRESOHQ_ALLOWED_TOOLS` (default read-only), but shell-injection is real if Bash is enabled. *Fix:* drop `shell=True`/use arg lists; keep allowlist default-deny.
- 🟡 **Open LLM proxies without auth** (`serve.py:41–43`). *Fix:* require auth before any public exposure.
- ✅ **Non-portable hardcoded path** (`serve.py:187`) — **fixed** (see above).

### UX, accessibility, mobile
- 🟡 **No onboarding path** — the dashboard assumes you know what an "endpoint" is. *Fix:* guided sign-in → provision → first-task.
- 🟢 **Touch targets < 44px** (buttons ~32–40px). 🟢 **Contrast** — `--brand-coffee-3` (and `--brand-coffee-2` small text) likely fail WCAG AA. 🟡 **Thin error recovery** — no retry on failed async ops.
- 🟢 **Brand seam** — pixel-art HQ chrome vs. soft control-plane chrome (`05-design-cohesion`).

### Workspace hygiene
- ✅ **Stray duplicate** (`Downloads\CafresoHQ`) — relocated under `Documents`.
- 🟢 **~30 uncommitted files** on the working branch — commit/branch to avoid loss.

---

## Part B — Compounded TODO (build checklist)

### Track 0 — Workspace & repo hygiene
- [x] **P0 (S)** Fix hardcoded memory path `serve.py:187` → repo-relative default. ✅
- [x] **P0 (S)** Relocate stray `Downloads\CafresoHQ` → `Documents\_archive\` (reversible). ✅
- [ ] **P0 (S)** Commit/branch the ~30 uncommitted files; verify `.gitignore`.
- [x] **P1 (S)** Confirm Pages / Minegold.defi / HQ all have a working tree under `Documents`. ✅

### Track 1 — Ecosystem wiring & cohesion *(03 Phase 0, 05)*
- [x] **P0 (S)** Populate the Banking.Brave anchor `ii-alternative-origins` with ecosystem domains. ✅ *(redeploy `cqyto-…` to activate)*
- [ ] **P1 (M)** Wire `gateway.public_hostname` + Caddy TLS so `hq.cafreso.com/u/{slug}` resolves publicly (no raw IPs).
- [ ] **P1 (M)** Extract a **single shared design-token file**; alias HQ's `styles.css` names to the `50–900` ramp.
- [ ] **P1 (M)** Soften HQ **chrome** (rail, top bar, `.oc-card`, `.Modal`, `.px-btn`, inputs) to the rounded/soft-shadow language; scope pixel styling to `.office-*` only.
- [ ] **P1 (S)** Port `EcosystemNav` (+ "HQ" badge) into the HQ top bar.
- [ ] **P2 (S)** Unify dark/night theme tokens; standardize wordmark/favicons.

### Track 2 — HQ product: make it real *(03 Phase 1)*
- [ ] **P0 (L)** One **live agent loop**: assign task → dispatch to Claude in the container → persist result + receipt to the **encrypted vault**.
- [ ] **P1 (M)** Durable **agent registry** + mission/task persistence (survives restart).
- [ ] **P1 (M)** Resolve the **vault duplication** (encrypted store = source of truth; HQ writes via bridge).
- [ ] **P1 (M)** **3-step onboarding** with empty/loading/error states; self-explanatory dashboard.

### Track 3 — Fleet productionization *(03 Phase 2)*
- [ ] **P0 (M)** Persist fleet **job state** (file/DB); add provisioning rate-limits.
- [ ] **P0 (L)** **Meter** per-user OCI cost + canister cycles; expose a usage endpoint.
- [ ] **P1 (M)** **Free-tier quota** enforcement + usage/cost panel.
- [ ] **P1 (S)** Basic observability (health, provision success rate, cost/active user).

### Track 4 — Monetization & token utility *(02 B1/B3, 04 §3)*
- [ ] **P1 (L)** **$CF = compute credits** (top-up gates compute beyond free tier).
- [ ] **P1 (M)** **Stake-to-unlock** tiers.
- [ ] **P1 (M)** **Treasury-subsidized free tier** (governed budget + kill-switch).
- [ ] **P2 (M)** Fiat + ICP/ckBTC on-ramps.

### Track 5 — Engineering quality & hardening *(Part A)*
- [ ] **P1 (L)** Introduce **Vite** → minified prod build; production React bundles; drop in-browser Babel/CDN for prod.
- [ ] **P1 (M)** Split monolithic `views.jsx` / `styles.css` / `app.jsx`; move off `window` globals.
- [ ] **P0 (S)** Remove `shell=True` (`serve.py`); keep tool allowlist default-deny.
- [ ] **P1 (S)** Pin `postMessage` origin; require auth on LLM proxies before public exposure.

### Track 6 — Accessibility & mobile *(02 A3, Part A)*
- [ ] **P1 (S)** Interactive targets ≥44px; fix `--brand-coffee-2/3` contrast.
- [ ] **P1 (M)** Polish the **mobile PWA** (manifest + service worker + mobile tab bar).
- [ ] **P1 (S)** Error-recovery/retry UI on failed async ops.

### Track 7 — SNS launch readiness *(04)*
- [ ] **P1 (S)** **Reconcile the two token models** (100M/55-30-15 vs $CF/46-27-22) → adopt one (recommended: swap 30 / treasury 43 / team 15 vested / seed 2 / community 10).
- [ ] **P1 (S)** Publish **team vesting + dissolve-delay** table (per principal; 36-mo+).
- [ ] **P1 (S)** Size **swap params** (min/max ICP, per-principal cap, min participants); decide **Neurons' Fund** stance.
- [ ] **P1 (M)** Publish **treasury-use roadmap**; decide **fee-burn** + rewards ≈4–5%.
- [ ] **P2 (L)** Security **audit**; **NNS Root co-controller** + fallback controllers; SNS-controlled upgrade test; **forum thread** (≥1 revision); decentralization roadmap; ≥90-day cycles runway.
- [ ] **P1 (S)** **Validate SNS launch cost/timeline** directly *(01 §A6 open question)*.

### Track 8 — Positioning & go-to-market *(02)*
- [ ] **P1 (S)** Re-position copy → **"a private AI workspace you own."**
- [ ] **P1 (S)** Stand up a **community/airdrop bucket**; reward early users.
- [ ] **P2 (M)** Referral/ambassador program (treasury-funded $CF); Spanish-first onboarding (LatAm/café channel).
- [ ] **P2 (S)** Privacy/compliance one-pager for sensitive-data audiences.

---

## Execution order (critical path)
1. **Track 0** quick-wins (mostly done) → **commit the working tree**.
2. **Track 1** ecosystem wiring + cohesion → it becomes one product. *(Redeploy `cqyto-…` to activate the identity fix.)*
3. **Track 2** ‖ **Track 3** (real agent loop ‖ fleet metering).
4. **Track 5/6** hardening + a11y alongside.
5. **Track 4** monetization/token utility (depends on metering).
6. **Track 7/8** SNS readiness + positioning → the raise. **Do not raise before the product is real** *(01 §A7)*.

*Companion docs: `00-executive-summary` · `01-research-icp-dao-and-agentic-market` · `02-positioning-and-mass-accessibility` · `03-mvp-roadmap` · `04-sns-tokenomics-decisions` · `05-design-cohesion`.*
