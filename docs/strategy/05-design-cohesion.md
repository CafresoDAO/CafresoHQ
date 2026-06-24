# 05 · Design Cohesion — Making CafresoHQ Feel Like the Ecosystem

> **Status:** Draft for founder review · Generated 2026-05-29
> **Scope:** How the Cafreso apps (~3 codebases: Pages, CafresoHQ/HQ, and Minegold.defi/Banking.Brave) relate visually today, where they diverge, and a concrete plan to make CafresoHQ read as a sibling of `ai.cafreso.com`, `cafreso.com`, and `Banking.Brave` — without throwing away the pixel‑art office that gives HQ its personality.
> **This is the one section that is purely a design audit.** Strategy, tokenomics, roadmap, and market research live in the sibling docs (`00`–`04`).

---

## TL;DR

The ecosystem already shares a **single brand palette** (banana‑yellow accent, coffee‑brown ink, cream paper) and the **same three type families** (Playfair Display / Inter / JetBrains Mono). That's a strong, ownable foundation most startups never get to.

The problem is that there are **two visual dialects** built on top of that shared palette, and they don't yet speak to each other:

| | Pixel‑art HQ (root React app, `hq.html`) | Control plane (`ai.cafreso.com`, SvelteKit) |
|---|---|---|
| Corners | **Square / 2–4px** (`--radius-2`) | **Soft / 8–16px** (`rounded-lg`…`rounded-2xl`) |
| Shadows | **Hard pixel** offset (`2px 2px 0 0 ink`) | **Soft, layered** (inset rim + blurred drop) |
| Surfaces | Flat brutal‑grid panels | Gradient cards with white inset highlight |
| Signature font | Adds **Press Start 2P** (retro pixel) | No pixel font; **Playfair** does the personality |
| Theme | `body.night` (day/night) | `.dark` class via `theme.js` (light/dark) — *different token names* |
| Ecosystem switcher | **None** | `EcosystemNav.svelte` (app‑switcher with per‑app accents) |

**Recommendation in one line:** keep the pixel‑art office as an intentional, *contained* motif (the "Agent Office" view only), and bring HQ's **chrome** — nav, panels, modals, settings, buttons — into the softer control‑plane language so the whole product family feels like one company. Then unify the token names so a color or radius change propagates everywhere.

---

## 1. What already unifies the ecosystem (protect this)

These are shared today and should be treated as **locked brand primitives**:

- **Accent — Banana yellow** `hsl(45 95% 62%)` ≈ `#F5D25D`, hover/rim `hsl(32 72% 50%)` ≈ `#C68A32`
- **Ink — Coffee brown** `hsl(24 48% 9%)` ≈ `#262313` (primary text / dark UI)
- **Paper / Crema** — `#FFFAF0` paper, `#BFAE9B` crema (warm backgrounds, never pure white/grey)
- **Type** — Playfair Display (display/headlines), Inter (UI/body), JetBrains Mono (code/labels/pills)
- **Per‑app accent colors** already defined in `frontend/src/app.css` and used by `EcosystemNav`:
  - Pages = peach/orange `hsl(18 79% 86%)` · AI = plum `hsl(280 38% 56%)` · HQ = banana `hsl(45 95% 62%)` · Banking = gold `hsl(43 74% 54%)`

This is genuinely good. The warm, human, "coffee‑shop‑not‑a‑terminal" palette is a differentiator in a category drowning in cold dark‑mode SaaS (see `02-positioning`). **Do not water it down.**

---

## 2. Where the apps diverge (fix this)

### 2.1 Two token systems, no shared source of truth
- HQ defines tokens in `styles.css :root` (e.g. `--brand-banana`, `--radius-2`, `--shadow-hard`).
- The control plane defines tokens in `tailwind.config.js` + `src/app.css` (e.g. `--brand-500`, `--ink-50`, `--card-shadow`).
- They encode the **same colors** under **different names** and **different scales** (HQ uses semantic names; frontend uses 50–900 numeric ramps).

> **Consequence:** a brand tweak (say, nudging the yellow) has to be made twice, by hand, in two notations. They *will* drift.

### 2.2 Shape language is inconsistent
- HQ is square/pixel by default; the control plane is soft/rounded. A user moving from the dashboard (`ai.cafreso.com`) into the embedded HQ office (`/app`) crosses a visible seam.

### 2.3 The "one ecosystem" promise isn't wired
- `frontend/static/.well-known/ii-alternative-origins` is **empty**, so the shared‑principal identity story (the thing that makes it *one* product) doesn't actually function across domains yet. *(Tracked as a launch blocker in `03-mvp-roadmap`; called out here because cohesion is identity, not just pixels.)*
- The **EcosystemNav app‑switcher exists only in the SvelteKit shell.** Once a user is inside the HQ iframe, there's no consistent way back to the rest of the family.

### 2.4 Theme handling forks
- HQ: `body.night`. Control plane: `.dark` + `meta theme-color` (`#f2dfc8` light / `#1b100b` dark). Two mechanisms, two token sets — dark mode looks different in each.

---

## 3. The cohesion strategy

### Decision to make first: *what is the pixel‑art for?*
The pixel office is delightful and ownable — it's the thing nobody else has. But applied to **every** surface it reads as "retro game," which fights the "serious, private, you‑own‑it AI infrastructure" positioning. The resolution:

> **Pixel‑art is a *feature surface*, not the *chrome*.** It lives in the "Agent Office" view (the isometric desks, sprites, cork board, ticker) as a signature, joyful centerpiece. Everything structural around it — top bar, side rail, panels, modals, forms, settings, the chat window — adopts the softer ecosystem language so HQ reads as the same company as the dashboard you just came from.

This keeps the magic *and* the credibility.

### Three concrete workstreams

**A. Unify the token layer (highest leverage, lowest risk)**
- Create one canonical token source (a tiny `cafreso-tokens.css` of CSS custom properties, or a JSON the build consumes) and have **both** apps import it.
- Map HQ's semantic names onto the ecosystem ramp (e.g. `--brand-banana` → `--brand-500`) so existing HQ CSS keeps working via aliases while the values come from one place.
- Result: change the brand once, it propagates to all 5 apps.

**B. Soften HQ's chrome to match the control plane**
- Adopt the control‑plane radius/shadow on HQ's **non‑office** components: rail, top bar, `.oc-card`, `.Modal`, `.px-btn`, inputs.
  - Radius: move chrome from `--radius-2` (4px) to the `8–16px` family used by `.card`/`.btn` on `ai.cafreso.com`.
  - Shadows: replace `--shadow-hard` (pixel offset) with the layered `--card-shadow` *outside the office view*.
- Keep `--shadow-hard`, square corners, and Press Start 2P **scoped to `.office-*` classes only.**

**C. Make the family visible from inside HQ**
- Port `EcosystemNav` (or a compact version) into the HQ top bar so the app‑switcher + "you are in HQ" badge is present everywhere, exactly as it is on the dashboard.
- Align the HQ "night" theme to the control plane's `.dark` tokens so dark mode is identical across the seam.

---

## 4. Prioritized recommendations

| # | Change | Why | Effort | Where |
|---|--------|-----|--------|-------|
| 1 | **Single shared token file** imported by both apps (alias HQ's names to the 50–900 ramp) | Stops inevitable brand drift; one knob for all 5 apps | M | new `cafreso-tokens.css`; `styles.css`, `tailwind.config.js`, `app.css` |
| 2 | **Soften HQ chrome** (rail, top bar, cards, modals, buttons, inputs) to the rounded/soft‑shadow language; scope pixel styling to `.office-*` only | Removes the visible seam between dashboard and HQ; keeps the office as a feature | M | `styles.css` (`.px-btn`, `.oc-card`, `.Modal`, `.px-panel`) |
| 3 | **Port EcosystemNav into HQ** + add the "HQ" wordmark badge | Makes it one product family from any screen; consistent way home | S | `ui.jsx` rail/topbar; reuse `EcosystemNav.svelte` patterns |
| 4 | **Unify dark/night theme tokens** across HQ and control plane | Dark mode currently looks like two different products | S–M | `body.night` ↔ `.dark` token map |
| 5 | **Populate `ii-alternative-origins`** so the shared‑principal identity actually works | Cohesion is identity, not just pixels — the "one login, every app" story is currently broken | S | `frontend/static/.well-known/ii-alternative-origins` (also in `03-roadmap` as a blocker) |
| 6 | **Standardize the wordmark lockup** (`cafreso-wordmark.png` + app suffix badge) and favicons across all 5 apps | A consistent mark is the cheapest, strongest cohesion signal | S | `static/` assets per app |

`S` = hours · `M` = a day or two · effort assumes the existing token values are reused, not redesigned.

---

## 5. What "done" looks like

A user signs in once (Internet Identity, shared principal), lands on `ai.cafreso.com`, opens HQ, and **never feels a brand seam**: same yellow, same coffee ink, same Playfair headlines, same app‑switcher in the corner, same soft cards and dark mode. Then they open the **Agent Office** and get a deliberate, delightful pixel‑art moment that says *this* is the part that's uniquely Cafreso. The pixel‑art reads as a signature, not an inconsistency.

---

*Companion docs: `00-executive-summary`, `01-research-icp-dao-and-agentic-market`, `02-positioning-and-mass-accessibility`, `03-mvp-roadmap`, `04-sns-tokenomics-decisions`.*
