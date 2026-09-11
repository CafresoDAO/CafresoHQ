# 08 · North Star — The Real Product of CafresoHQ

> **Status:** Founder-approved direction · 2026-08-05 · from a live design session.
> **What this is:** the one-page answer to "what are we actually building?" — the
> filter every feature, doc, and sprint gets held against from here on. It
> **supersedes the "Hermes as default runtime" decision** in
> `HERMES_INTEGRATION_PLAN.md` (see §3.1) and sequences the marketplace and
> per-user-canister ideas behind a legible core.
> **Companions:** `../DRIVER_CONTRACT.md` (the architecture that enforces §3.1),
> `../OFFICE_AS_INTERFACE.md` (the design system that enforces §3.2).

---

## 1. The one-liner

> **One office where all your AIs work together — no expertise required.**

If a user pays for Claude, Gemini, and ChatGPT, CafresoHQ is the single
environment where those agents sit at desks in the same room: planning together,
executing code, producing artifacts, filing results into a vault the platform
cannot read. You bring the subscriptions you already have; we give them a
workplace.

### Why this wins structurally (not just aesthetically)

Every AI vendor is building an agent product, and **every one of them is a silo
by design**. Anthropic will never build the room where ChatGPT sits at the next
desk. Google will never make Claude a first-class citizen. The neutral ground
*cannot be built by the incumbents* — only by someone with nothing to protect.
Each new frontier model makes the neutral office **more** valuable, not less.

This stacks on top of (not instead of) the ownership wedge from `02`:
privacy + ownership is *why you can trust the office*; vendor-neutrality is
*why the office is worth walking into*.

| Dimension | Vendor agent apps (Claude/ChatGPT/Gemini) | Cursor / Devin | **CafresoHQ** |
|---|:--:|:--:|:--:|
| Multiple vendors' agents in one workspace | ❌ (structurally impossible) | ⚠️ (models, not agents) | ✅ the whole point |
| Usable by non-developers | ⚠️ | ❌ | ✅ office metaphor (§3.2) |
| You own the data (E2E vault, II) | ❌ | ❌ | ✅ vetKeys + canister state |
| Bring subscriptions you already pay for | — | ⚠️ | ✅ BYOS is the default (§3.3) |
| Community-owned platform | ❌ | ❌ | ✅ SNS path |

## 2. Who it's for

**The capable non-guru.** A shop owner, a designer, a student, a founder — someone
who already pays for one or two AI subscriptions, gets real value from chat, and
has *heard* agents can do more but bounces off every tool that assumes they know
what a system prompt is. They will never open a terminal. They will absolutely
delegate work to a character they can watch doing it.

Developers are welcome (the Living Floor desktop mode serves them) but they are
the **second** audience. When a choice trades newcomer legibility against power-user
depth, legibility wins in the core path and depth moves behind a door.

## 3. Product principles

### 3.1 No privileged backend
No agent runtime gets special treatment — not in code, not in copy, not in
defaults. The founder's own retrospective: *"maybe making it Hermes agent by
default was a mistake to begin with."* The evidence agrees — the hairiest code
in `serve.py` is exactly where Hermes is privileged (config.yaml regex
rewrites, `.env` writes, four separate gateway-restart call sites). Privilege
metastasizes into special-case plumbing. **Every backend is a driver behind one
contract** (`DRIVER_CONTRACT.md`); Hermes becomes driver #4, its gateway an
internal detail of that one driver.

### 3.2 The office is the interface
The pixel office is not decoration — it is the **accessibility strategy**. Every
AI concept a newcomer finds alien has a physical counterpart they already
understand: models are coworkers with strengths, a system prompt is a job
description, approvals are a coworker walking to your desk to ask. Full mapping
and onboarding flow in `OFFICE_AS_INTERFACE.md`.

### 3.3 Bring what you already pay for (BYOS)
The default backend is **whatever the user already has**. `serve.py` already
detects installed CLIs and credentials (`_agent_auth_detect`); the front desk
turns that into "We found your Claude subscription — want them on the team?"
Zero-subscription visitors get the managed trial brain (already shipped). We
never make someone buy a new key to feel the product.

### 3.4 Show the work
Sprites doing things ARE the trace viewer. A newcomer never opens a log; they
watch a coworker walk to the filing cabinet (file read), type (token stream),
or come ask permission (tool approval). Every driver event maps to a visible
behavior — the contract's event schema exists partly to make this possible.

### 3.5 You own it
One Internet Identity across the ecosystem, vetKeys E2E vault the platform
cannot read, state on canisters, execution on compute you choose (your machine,
your container, or — later — an agent you hire from the network). This is `02`'s
wedge, unchanged, and it's the trust floor under everything above.

### 3.6 Five minutes to first delight
A stranger sits down → we detect what they already have → they hire one
coworker → pick a starter task → watch it happen → a real artifact lands in
their vault. Under five minutes, no settings pages, no model IDs. This flow is
the product's front door and gets protected like one.

## 4. What CafresoHQ is NOT

- **Not a dev console.** Dark-terminal vibes are what everyone else ships.
- **Not a prompt-engineering IDE.** Personas are job descriptions, not YAML.
- **Not an AI vendor.** We never compete with the coworkers' makers on models.
- **Not "build on ICP with AI."** That's Caffeine's lane and DFINITY gives it
  away free (`02 §1`).

## 5. The park list — shed to focus (beta is when you're allowed)

Parked ≠ deleted. These stay in the codebase or move behind an "advanced" door,
but leave the core path, the onboarding, and the pitch:

| Parked | Why |
|---|---|
| Hermes-as-default (+ Hermes Console as flagship surface) | §3.1 — becomes one driver among peers |
| User-facing PTY terminal in the core path | The #1 "this isn't for me" signal for non-gurus; stays in Living Floor desktop mode for devs |
| CDP browser screenshots | Niche, heavy, off-thesis for v1 |
| Obsidian bridge | Serves a power-user 1%; vault is the story |
| Exporter zoo (video gen, ComfyUI/A1111 wiring) | Cool, unfocused; image gen can return post-core |
| OCI fleet special-cases inside the core app | Already extracted to cafreso-fleet; keep it that way |

**Stays first-class:** the vault, the office floor + Living Floor, missions
(rebranded the "Night Shift" board), the Library integration, per-agent wallets,
the trial brain.

> ✅ **Shipped 2026-08-06** (Phase A UI complete, so the park expired). Exactly
> the shape below: `PUBLISH_SITE` is the one host tool — every floor coworker
> gets it through the runtime's shared tool surface regardless of driver — and
> the marker now QUEUES a one-click approval instead of publishing (the
> coworker literally walks to the boss desk and asks, via the §4 approval
> walk). The stamp executes the publish, tip jar riding along. Bonus surface:
> page deliverables in the cabinet grew a "Share it live" button on the
> delivery sheet (user-initiated — the click is the approval), which closes
> OFFICE_AS_INTERFACE §3.6's deferred share. Not yet covered: night_runner
> missions and CLI-native runs, which don't ride the browser tool surface.

**Parked *forward* (not built yet — founder-flagged 2026-08-05): Ship-to-chain.**
Give any hired coworker one tool to deploy the site/app it just built straight
to an ICP asset canister — with the user's permission — so finished work gets a
real, permanent URL instead of only a file in the vault. Asset canisters can
host just about anything, so this covers shares, portfolios, and full frontends
alike. This does **not** violate §4's "not Caffeine's lane": Caffeine sells
*building on ICP*; Ship-to-chain is *publishing the output* of whatever agent
you already pay for — hosting, not canister development. It rides the driver
contract as one host tool + one approval (the coworker walks over and asks
"ready to publish?"), and the groundwork already exists: Publish-to-Canister in
`cafresohq_state` and the `@dfinity/assets` sync script in cafreso-pages.
Parked until the Phase A core lands.

## 6. Sequencing — the big dreams, in order

Each phase makes the next one stronger; none skips ahead of a legible core.

- **Phase A — the legible core (now).** Driver contract implemented for
  Claude Code + Codex + Gemini CLI + one local driver (Ollama/LM Studio);
  detection-based first-run; five-minute onboarding; park list applied.
  *Exit test: a non-developer stranger delegates a task in under five minutes.*
- **Phase B — coworkers with depth.** Stat cards, XP/experience per completed
  job, job descriptions (persona editing), Night Shift polish. XP is deliberate
  groundwork for Phase C's résumés.
- **Phase C — the marketplace.** "Hire from the network": community-hosted
  agents (GPU + model + persona) join as **remote drivers** implementing the
  same contract, with an on-chain résumé ledger (jobs completed, re-hire rate)
  in `cafresohq_state`. The labor-market framing — selling *employees with
  résumés*, not FLOPs — is the moat vs io.net/Bittensor commodity compute.
  Cafreso's own managed agents seed the market and dogfood escrow/reviews.
  > ✅ **Hall built 2026-09-11** (`## 427.`, `../AGENT_MARKETPLACE.md`): its
  > own canister `cafresohq_market` with real per-job ICRC-2 escrow and the
  > on-chain résumé; the worker loop on a key of its own inside the
  > coworker's container; the Hiring Hall room. Not yet deployed — founder
  > steps in that doc §7. Still owed: the network coworker as a floor
  > sprite (DRIVER_CONTRACT §6) and the first replica run.
- **Phase D — own your office literally.** Per-user HQ state canister funded by
  the user's own cycles (identity, vault index, roster, hiring records,
  résumé ledger). Execution stays off-chain where it must (see the serve.py
  portability audit, 2026-08-05 session); the canister is persistence, identity,
  payment. Builds directly on `PHASE2_STATE_CANISTER.md`.

## 7. How we know it's working

- **Time-to-first-delegation** for a fresh user: target < 5 minutes.
- **Multi-backend adoption:** % of active users with ≥ 2 drivers connected —
  the direct measure of "the one place your AIs work together."
- **Non-developer retention:** do people who never open desktop mode come back?
- **Phase C leading indicator:** % of tasks users choose to route to a
  marketplace coworker once offered.
