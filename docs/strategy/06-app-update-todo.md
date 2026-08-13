# 06 · App Update TODO — Critique + Compounded Build Checklist

> **Status:** Living checklist · Generated 2026-05-29 · Compounds docs `00`–`05`.
> **Two parts:** **Part A** is an overall critique of the CafresoHQ app (what to fix and why). **Part B** is the prioritized, ordered TODO that turns the whole strategy package into a build checklist.
> **Severity:** 🔴 high · 🟡 medium · 🟢 low. **Priority:** P0 launch-blocking / safe quick-win · P1 needed for a credible MVP · P2 post-MVP / pre-SNS. **Effort:** S hours · M a day or two · L 1–2+ weeks.
>
> ⚠️ **Part A predates ~2.5 months of subsequent work. Seven of its 🔴/🟡
> items were found stale on direct verification (2026-08-12/13)** — the
> build-step, `window`-global module wiring, `shell=True`, agent/task/mission
> persistence, onboarding, the monolithic-files entries, and
> open-LLM-proxy-auth are all corrected in place (the monolithic-files one
> only partially — `app.jsx`/`styles.css` are real, worsening problems, so
> read that one's fix line, not just its status). Not a full re-audit — those
> seven were checked because this session had direct, load-bearing evidence
> for each (things directly driven, measured, or built today), not because
> the rest of Part A was reviewed. The remaining entries should be read as
> "as of May", not "as of now", until someone does the same check on them.

## Ecosystem mapping (corrected)
The ecosystem is **~3 codebases + the per-user container**, all under `C:\Users\Anthony\Documents`:
- **Pages** — `Documents\CafresoPages` → `cafreso.com`
- **CafresoHQ** (control plane + embedded HQ) — `Documents\CafresoHQLocal` → `ai.cafreso.com`; per-user **HQ** containers at `hq.cafreso.com/u/{slug}`
- **Minegold.defi / Banking.Brave** — `Documents\minegold.defi` → frontend canister `cqyto-…` is the **Internet Identity anchor** (`derivationOrigin`). Banking.Brave is the app's homepage; Minegold.defi is the protocol hosted under the Banking.Brave domain.

## ✅ Safe wins already executed (2026-05-29)
- ✅ **`serve.py` portability** — replaced the hardcoded `C:\Users\Anthony\.claude\…\memory` default with a repo-relative `hq-state/memory` default (env `CAFRESOHQ_MEMORY_DIR` still overrides). `serve.py:~186`.
- ✅ **Ecosystem identity unblocked (ACTUALLY done + DEPLOYED 2026-07-30)** — the earlier version of this entry was aspirational: the file on disk still listed only `dqcmv-…`. Now live on `cqyto-…`: `banking.cafreso.com`, `cafreso.com`, `ai.cafreso.com`, `hq-ui.cafreso.com`, `dqcmv-…icp0.io`, `v4tdv-…icp0.io`, served as `application/json` (was `application/octet-stream`, which also had to be fixed in the asset-sync tool). minegold's own `auth.tsx` now pins `derivationOrigin` too, so the future custom-domain move cannot change principals. Verify: `curl https://cqyto-tiaaa-aaaau-agppa-cai.icp0.io/.well-known/ii-alternative-origins`.
- ✅ **Workspace consolidation** — stray older duplicate moved out of `Downloads` into `Documents\_archive\` (reversible; see Track 0).
- ✅ **Docs corrected** — strategy docs updated for the Banking.Brave/Minegold mapping above.

---

## Part A — Critique of CafresoHQ (overall)

### Architecture & build
- ✅ ~~**No build step — Babel transpiles JSX in the browser.**~~ **Done, not via Vite — verified 2026-08-12.** `scripts/build_ui_bundle.mjs` self-hosts the vendor UMD globals (dropping the unpkg dependency), bundles the app's real ES modules into IIFE chunks, and hashes the output to `dist-ui/bundle/`; `hq.html` confirms in its own comment: "JSX is pre-transformed at build time (no @babel/standalone, no unpkg)". This session ran that build after nearly every code change today. The doc's goal (drop in-browser Babel/CDN, ship a minified prod build) is met by a purpose-built esbuild script instead of Vite — same outcome, different tool, and re-pointing this at Vite now would be a rewrite of something that already works, not a fix.
- 🟡 **Monolithic files — mixed result, re-measured 2026-08-12.** `views.jsx`, `ui.jsx` and `modals.jsx` WERE split by feature as prescribed: all three are now thin barrels (721 / 50 / 16 bytes) re-exporting from `views/*.jsx` (7 files, 538–1,783 LOC each, 6,800 total — the original content, genuinely divided) and presumably equivalent `ui/`/`modals/` directories. But `app.jsx` and `styles.css` were NOT split, and both grew past the size that flagged them in the first place: `app.jsx` 3,754 → **5,814** LOC, `styles.css` 7,817 → **11,104** LOC. The fix landed for 3 of 5 named files and the other 2 got measurably worse in the same window. *Fix, unchanged for the remaining two:* split `app.jsx` and `styles.css` by feature.
- ✅ ~~**`window`-global module wiring** (`app.jsx:6–10`). One failed script → cascading `undefined`. *Fix:* ES module imports once bundled.~~ **Already the fix — verified 2026-08-13, same session as the build-step correction above.** `app.jsx`'s own current lines 1–19 are genuine `import { X } from './y.jsx'` statements, not `window.X` reads — this is literally the doc's own prescribed fix, already shipped. Confirmed at the build-output level too, not just the source: rebuilt via `scripts/build_ui_bundle.mjs` and inspected `dist-ui/manifest.json` — `app.jsx` plus every one of its ~20 imports (`ui.jsx`, `modals.jsx`, `views.jsx`, `features.jsx`, `hq-runtime.jsx`, the `app/*.jsx` submodules, etc.) resolve into exactly **one** output file, `bundle/hq-app-*.js`, with imports settled by esbuild at build time. The specific failure mode this bullet names — one of several separate feature scripts 404s or throws, leaving its `window.X` unset and everything downstream `undefined` — cannot happen to the app's own code anymore, because there is no longer more than one script tag carrying app code for it to happen between. (Vendor libraries — React, ReactDOM, xterm — are still separate `<script>` tags, and the optional `graphEngine`/`analyticsWorker` chunks are deliberately split for lazy-load/worker-thread reasons; neither is the "CafresoHQ's own feature files wired via globals" problem this bullet described.)

### Duplication & data integrity
- 🟡 **Two vault implementations** — root app writes plaintext via `/vault/note`; the SvelteKit frontend (`frontend/src/lib/stores/vault.js`) is the real E2E-encrypted client; the root app is embedded as an **iframe** bridged by `postMessage`. No conflict resolution. *Fix:* encrypted store = single source of truth; HQ writes via the bridge.
- 🟡 **`postMessage` origin `'*'`** (`frontend/src/routes/app/+page.svelte` ~line 61). *Fix:* pin to the container origin.

### "Real vs mock" product gaps
- ✅ ~~**Agents / missions / tasks aren't durably persisted**~~ **Wrong on every count — verified 2026-08-12.** `mock-data.jsx` does not exist anywhere in this codebase. `HQ.INITIAL_AGENTS` (`hq-runtime.jsx`) is `[]` — not "3 seed agents"; a fresh office starts with zero. Agents, tasks AND missions all go through the same `useFileStored` (`app.jsx:38,733,836`), which the doc's own next clause names correctly and then contradicts in the same sentence: it does not stop at localStorage, it syncs to `hq-state/<scope>/<name>.json` on the SERVER, and this session proved that survives a full process kill twice — a throwaway office was seeded by hand-writing `hq-state/memory/agents.json` before the server process even started, and a fresh `serve.py` picked it up correctly on boot both times. The gap this bullet named does not exist; whatever separates "demo" from "product" here, it isn't persistence.

### Security & ops (flag)
- ✅ ~~**`subprocess.run(arg, shell=True)`** for the BASH tool~~ **Re-examined 2026-08-12 — this is the correct implementation, not a bug.** A BASH tool's entire purpose is running shell syntax (pipes, `&&`, redirects); `shell=True` is what makes that possible, and "drop it, use arg lists" would silently break the feature rather than secure it — an arg-list `subprocess.run` cannot execute `ls | grep foo`. The actual mitigation is already layered and, per the code's own comment at `serve.py:~184`, deliberate: `Bash` is excluded from `CAFRESOHQ_ALLOWED_TOOLS`'s default set specifically *because* "enabling it by default makes every unconfigured deployment one request away from arbitrary command execution" — it requires an explicit env-var opt-in on top of that. And reaching the endpoint at all requires the AGENT to be `elevated`, which requires a boss-approved `grant-elevation` request (`app.jsx`, `hq-runtime.jsx:1748`). Three gates (server opt-in, per-agent elevation, human approval), a 30s timeout, and a 4000-char output cap. Removing `shell=True` was never the fix; the fix (default-deny + explicit consent) already shipped.
- ✅ ~~**Open LLM proxies without auth** (`serve.py:41–43`). *Fix:* require auth before any public exposure.~~ **Already real, verified live 2026-08-13** — see the corrected Track 5 entry in Part B for the full evidence (a real bearer-key gate covering a much larger surface than "LLM proxies," confirmed 401/401/200 live against a running server, plus a startup warning for the unkeyed-and-non-loopback case).
- ✅ **Non-portable hardcoded path** (`serve.py:187`) — **fixed** (see above).

### UX, accessibility, mobile
- ✅ ~~**No onboarding path** — the dashboard assumes you know what an "endpoint" is.~~ **Built and repeatedly verified — checked again 2026-08-12.** "Endpoint" appears zero times in any first-run UI string — the only two hits in the whole codebase are developer comments in `app.jsx`, not copy a boss sees. The doc's own prescribed fix (guided sign-in → provision → first-task) is exactly what shipped, under office words: the front desk auto-detects brains on the machine ("checking who's available…" → "found on this machine, ready to join" — `modals/hire.jsx`), then the FIRST ASSIGNMENT sheet hands over three starter cards (`modals/starter.jsx`). `OFFICE_AS_INTERFACE.md` §3 has logged multiple clean clock-timed walks of this exact path, most recently 33.3 seconds hire-to-artifact on 2026-08-12. `scripts/test_jargon_table.py` stands guard against this specific regression class.
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
- [x] **P0 (S)** Populate the Banking.Brave anchor `ii-alternative-origins` with ecosystem domains. ✅ deployed + curl-verified 2026-07-30
- [ ] **P1 (M)** Wire `gateway.public_hostname` + Caddy TLS so `hq.cafreso.com/u/{slug}` resolves publicly (no raw IPs).
- [ ] **P1 (M)** Extract a **single shared design-token file**; alias HQ's `styles.css` names to the `50–900` ramp.
- [ ] **P1 (M)** Soften HQ **chrome** (rail, top bar, `.oc-card`, `.Modal`, `.px-btn`, inputs) to the rounded/soft-shadow language; scope pixel styling to `.office-*` only.
- [ ] **P1 (S)** Port `EcosystemNav` (+ "HQ" badge) into the HQ top bar.
- [ ] **P2 (S)** Unify dark/night theme tokens; standardize wordmark/favicons.

### Track 2 — HQ product: make it real *(03 Phase 1)*
- [ ] **P0 (L)** One **live agent loop**: assign task → dispatch to Claude in the container → persist result + receipt to the **encrypted vault**.
- [x] ~~Durable **agent registry** + mission/task persistence (survives restart).~~ **Already true — verified 2026-08-12.** See Part A: agents/tasks/missions share `useFileStored`, which round-trips through `hq-state/` on the server and was proven to survive a killed-and-restarted process, twice, this session.
- [ ] **P1 (M)** Resolve the **vault duplication** (encrypted store = source of truth; HQ writes via bridge).
- [x] ~~**3-step onboarding** with empty/loading/error states; self-explanatory dashboard.~~ **Already shipped — verified 2026-08-12.** See Part A: front desk → hire → FIRST ASSIGNMENT, zero jargon, clocked at 33.3s hire-to-artifact.

### Track 3 — Fleet productionization *(03 Phase 2)*
> ⚠️ **This entire track is scoped to the wrong repository — checked 2026-08-12.**
> CafresoHQ contains no OCI provisioning code at all (zero hits for
> `compartment_id`/`launch_instance`/`oci.core` anywhere in this tree); it only
> *consumes* fleet-manager's output — `serve.py:757`, its own comment: "Fleet
> identity (set by fleet-manager when provisioning the container)". The actual
> provisioning, job state, and metering logic lives in the sibling repo
> `cafreso-fleet/oci-fleet/` (`fleet-manager.py`, `fleet-api.py`,
> `session_store.py`, `workspaces-api.py` all exist there and look like they
> already address parts of this — not independently verified, since that repo
> has none of the test/measurement infrastructure this session built up here).
> These four items should be tracked in `cafreso-fleet`'s own planning doc (or
> given one, if it doesn't have one), not worked on inside CafresoHQ — there is
> no code here for them to land against.
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
- [x] ~~Introduce **Vite** → minified prod build; production React bundles; drop in-browser Babel/CDN for prod.~~ **Done 2026-08-12** — via `scripts/build_ui_bundle.mjs` (esbuild-based), not Vite. See Part A.
- [ ] **P1 (M)** ~~Split monolithic `views.jsx`~~ / `styles.css` / `app.jsx`; move off `window` globals. **Partially done, re-measured 2026-08-12** — `views.jsx` (and `ui.jsx`, `modals.jsx`) were split into real per-file directories and are now thin barrels; see Part A. `styles.css` and `app.jsx` were not, and have grown to 11,104 and 5,814 LOC respectively since this was written. Still open for those two specifically.
- [x] ~~Remove `shell=True` (`serve.py`); keep tool allowlist default-deny.~~ **Re-examined 2026-08-12 — not a bug, no action needed.** See Part A: `shell=True` is required for a shell tool to work, and the actual protection (default-deny + per-agent elevation + boss approval) already exists.
- [x] ~~Require auth on LLM proxies before public exposure.~~ **Already real, verified live 2026-08-13.** `serve.py`'s `CAFRESOHQ_API_KEY` bearer-key gate covers `/vault`, `/hermes`, `/terminal`, `/agents`, `/hq-state`, `/tools`, `/export`, `/generate` and more — a materially larger surface than "LLM proxies," with an explicit, documented boundary (static shell + `/health` stay open; `/fs` read-only preview routes are deliberately excluded and explained why; OCI-fleet mode defers to the Caddy gateway instead). Confirmed live, not read-only: no key → `401`, wrong key → `401` (timing-safe `hmac.compare_digest`), right key → `200`, `/health`/`hq.html` unaffected either way. A startup warning already fires when bound to a non-loopback interface with no key set (`serve.py:~4401`). The remaining gap in this bullet — **pin `postMessage` origin** — is in `frontend/src/routes/app/+page.svelte`, a file that does not exist in this repository (confirmed: no `frontend/` directory here at all) — same "wrong repository" situation already flagged for Track 3. Still open, but not fixable from here.

### Track 6 — Accessibility & mobile *(02 A3, Part A)*
- [ ] **P1 (S)** Interactive targets ≥44px. *(Measured 2026-08-12 at 375×812:
  14 of the 15 controls in `.px-scene` are under 44px — mugs are 12×12 — and
  the naive fix is unsafe: the tightest gap between two of them is **11px**
  (filing cabinet ↔ 1:1 sofa), so growing both to 44 overlaps them by more
  than the gap. Needs a layout decision, not a CSS bump.)*
- [x] ~~fix `--brand-coffee-2/3` contrast~~ — **done 2026-08-12.** Measured on
  the running app across 132 coffee-2/-3 text nodes (office floor, eight
  views, Settings modal): the tokens themselves already pass AA on the paper
  surfaces they were tuned for — coffee-3 on the topbar gradient measures
  5.08:1 / 4.93:1. Exactly one real failure: the activity ticker's `•`
  separators at **3.38:1**, because the ticker is the one dark strip in a
  light app and `.sep` reused the paper-tuned `--ink-3` (= `--brand-coffee-3`).
  Fixed at the surface, not the token — lightening coffee-3 globally would
  have cleared the ticker by degrading every paper surface. Now 5.48:1, still
  3.08:1 dimmer than the ticker's own text. Pinned by
  `scripts/test_coffee_contrast.py`, which fails on that exact wrong fix.
- [ ] **P1 (M)** Polish the **mobile PWA** (manifest + service worker + mobile tab
  bar). *(Measured 2026-08-12 — this is mostly BUILT, not missing. The manifest
  is valid and served as `application/manifest+json`; icon-192/512 (any +
  maskable) and apple-touch-icons at 180/167/152 all exist; hq.html carries
  `viewport-fit=cover`, theme-color and the apple-mobile-web-app meta; the
  mobile tab bar ships. The one thing missing is that hq.html UNREGISTERS the
  service worker on every load, so the app cannot be installed.*
  *Driving `sw.js` for the first time — it had never executed — found it would
  have made a DEAD office report itself healthy: with the server killed,
  `/health`, `/agent/drivers` and `/missions/scheduled` all returned cached
  200s. Its fetch rule is now an allowlist (only the static shell is
  cacheable), re-verified against the same dead server: all three fail
  honestly while a page reload still renders the offline shell. Pinned by
  `scripts/test_sw_never_caches_state.py`.*
  *Left OFF deliberately: a service worker is sticky, and enabling it on a
  daily-driver office is a decision the owner should make. Raised as a task
  with three options.)*
- [ ] **P1 (S)** Error-recovery/retry UI on failed async ops. *(Census 2026-08-12:
  50 catch blocks report a failure to the boss. Most are behind a control they
  just pressed, so the way forward is that control — a second retry button
  there would imply the first had stopped working. The gap is AUTOMATIC loads,
  which have no button at all. Settings → Connections' driver probe is done:
  hoisted out of its `useEffect`, ↻ CHECK AGAIN wired to it, and two distinct
  sentences depending on whether the office answered. **Sweep completed same
  day:** only two other mount-time loads reported their own failure, and both
  are now fixed — the Projects file tree (replaced the whole tree with a raw
  `Error: {err}` and had no retry of its own) and `ModelPicker`, which
  silently substitutes a STATIC model list for the detected one. That second
  one was the worse find: proven live, the fallback shows three buy-a-key
  services where the real list is six groups including the boss's own running
  **Ollama**, and the only signal was a `title` tooltip. Its `refreshKey` prop
  is passed by none of its three call sites, so the refresh in the code could
  never fire; both components now own an internal nonce. Pinned by
  `scripts/test_mount_load_recovery.py`.)*

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
