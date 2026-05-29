# 07 · Pages + CafresoAI Merge — Implementation Record

> **Status:** ✅ DEPLOYED LIVE (2026-05-29) to `cafresoai_frontend` (`v4tdv-riaaa-aaaab-agtfa-cai`) — serving at https://v4tdv-riaaa-aaaab-agtfa-cai.icp0.io/ (= ai.cafreso.com). `ic-domains` (ai.cafreso.com + cafreso.com) confirmed live. Remaining: point cafreso.com DNS at v4tdv + register the custom domain; redeploy `cqyto` so the ii-alternative-origins fix goes live. (Note: the dependency chain also ran a same-code upgrade of `cafresoai_keys` — state preserved.)
> **Decision basis:** side-chat architecture — unify Pages + CafresoAI into ONE SvelteKit app/canister; keep Minegold/Banking + backends separate; HQ stays on OCI. Home repo = `CafresoHQLocal/frontend`. Scope = full merge to one frontend canister.

## What changed
The consumer surface (Cafreso **Pages**) was merged into the **CafresoAI** SvelteKit app at `C:\Users\Anthony\Documents\CafresoHQLocal\frontend`. One app now serves both surfaces:

| URL | Surface | Source |
|---|---|---|
| `/` (+ `/shop`, `/blog`, `/forums`, `/governance`, `/leaderboard`, `/profile`, `/about`, `/checkout`, …) | **Consumer (Pages)** | `src/routes/(pages)/*` |
| `/hq` (+ `/hq/app`, `/hq/chat`, `/hq/vault`, `/hq/settings`, `/hq/search`) | **Control plane (CafresoAI/HQ)** | `src/routes/hq/*` |
| `/loading` | shared | `src/routes/loading/*` |

### Key mechanics
- **Route groups:** Pages routes copied into a `(pages)` group (home = `/`); CafresoAI's flat routes moved under a real `/hq` segment. No path collisions.
- **Layouts:** root `+layout.svelte` slimmed to shared globals (theme + Internet Identity init). Consumer chrome lives in `(pages)/+layout.svelte` (uses `PageHeader`/`Footer`/`MobileNav`/Cart/Toast); control-plane chrome in new `hq/+layout.svelte` (uses `Header` + `EcosystemNav` + endpoint detection).
- **Header collision:** Pages' `Header.svelte` → `PageHeader.svelte`. CafresoAI's `Header.svelte` kept; its nav links repointed to `/hq/*`.
- **Auth dedup:** Pages' `stores/auth.js` dropped; the app uses CafresoAI's richer `auth.js` (superset of exports; same `derivationOrigin` = Banking.Brave `cqyto-…`).
- **Design tokens unified:** one `tailwind.config.js` + `app.css` carrying CafresoAI's `brand`(50–900)/`ink`(50–900) scale **and** Pages' shadcn/bits-ui semantic tokens + named `brand.*` aliases (light + dark) + Pages' utility/responsive CSS.
- **Deps added** to `frontend/package.json`: `bits-ui`, `layerchart`, `tailwind-merge`, `@dfinity/candid`.
- **Browser-safe declarations:** `declarations/index/index.js` (and `cafresoai_keys/index.js`) rewritten from `process.env.*` → `import.meta.env.* || <mainnet id>` so consumer routes don't crash in-browser. Index canister fallback = `bek5d-2qaaa-aaaab-agqrq-cai` (matches `api/store.js` + `api/devlog.js`).
- **Backends unchanged:** the merged frontend calls the existing deployed Pages backends (devlog/store/index) via their declarations + hardcoded mainnet IDs. They remain separate canisters by design.

## Deploy checklist (founder-run — not done yet)
1. ✅ **DONE** — Built + deployed the unified frontend to `cafresoai_frontend` (`v4tdv`) via `dfx deploy --network ic cafresoai_frontend` (default identity, a controller). 342 asset ops committed.
2. **Custom domain:** register `cafreso.com` on `v4tdv` (boundary-node custom domain + DNS `CNAME`/`_canister-id` TXT). `ic-domains` already lists `ai.cafreso.com` + `cafreso.com`. Repoint `cafreso.com` DNS from the old Pages canister (`dqcmv-…`) to `v4tdv`; then retire/redirect `dqcmv`.
3. **Activate ecosystem login:** redeploy the **Minegold.defi / Banking.Brave** canister (`cqyto-…`) so the updated `ii-alternative-origins` (now lists the custom domains) takes effect.
4. *(Optional)* Host-based default route so `ai.cafreso.com/` lands on `/hq` (small client check on `window.location.host`).

## Verify
- ✅ Build: `npm --prefix frontend run build` (clean, verified twice).
- ⏳ **Runtime smoke test (recommended, not yet run):** `npm --prefix frontend run preview`, load `/` (consumer home) and `/hq` (dashboard), check the browser console; then QA representative consumer routes (`/shop`, `/blog`, `/forums`, `/leaderboard`) and control-plane routes (`/hq/app`, `/hq/vault`).

## Rollback / safety
- The original **`C:\Users\Anthony\Documents\CafresoPages`** repo is **left intact** (not modified/deleted) — it remains a reference and rollback source.
- All changes are confined to `CafresoHQLocal/frontend` and are reviewable via `git diff`. **Uncommitted** — recommend committing on a branch (`merge/pages-cafresoai`).

*Companion: `03-mvp-roadmap` (Track 1/5), `05-design-cohesion`, `06-app-update-todo`.*
