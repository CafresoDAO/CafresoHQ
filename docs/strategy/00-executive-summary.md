# 00 · Executive Summary — Cafreso Launch & DAO Strategy

> **Generated 2026-05-29** for the founder, overnight. This is the entry point to a 6-doc strategy package in `docs/strategy/`. Read this first; it links to everything else.
> **Scope:** deep research on (a) ICP DAO/SNS fundraising and (b) the agentic-tooling market, a competitive read of CafresoHQ, a brainstorm to make HQ accessible to the masses via the SNS DAO, and a rough-draft roadmap to MVP across the whole ecosystem.
> **Ecosystem note (corrected 2026-05-29):** the ecosystem is ~3 codebases under `Documents` — **Pages** (`cafreso.com`), **CafresoAI** (control plane + embedded **HQ**), and **Minegold.defi / Banking.Brave** (frontend canister `cqyto-…` is the Internet Identity anchor; Banking.Brave is the homepage, Minegold.defi the protocol). "5 apps" elsewhere is loose shorthand. See `06-app-update-todo.md`.

---

## The thesis, in one paragraph
Cafreso has built something most teams never get to: a **genuinely differentiated wedge** — *a private AI workspace you actually own* (end-to-end encrypted vault where only you hold the keys, private per-user compute, passwordless Internet Identity login, and community ownership via a DAO). The research is clear that **"AI on ICP" is no longer a moat** — DFINITY itself ships Caffeine.ai and courts Cursor/Claude Code/Copilot — but **the *combination* of zero-knowledge ownership + private compute + a community-owned multi-app ecosystem has no direct competitor.** The job now is not more vision; it's **making one slice real**: a working agent loop, metered/payable compute, and a wired-together ecosystem identity — then raising ICP through an SNS once there's a live product to point at.

---

## Where you are today (honest snapshot)
- ✅ **Strong, real foundation, live on mainnet:** Internet Identity auth + ecosystem-shared principal, and a **production-quality zero-knowledge vetKeys vault** (`cafresoai_keys`). The frontend shell, encrypted vault, and Claude chat all work. **This is your wedge — lead with it.**
- ⚠️ **The "agent command center" is mostly a mockup:** the office agents (Mira/Kip/Bop) are hardcoded UI; no live task execution yet.
- ⚠️ **Fleet provisioning works but can't bill or meter** — you can't safely open the doors (every signup spends your money invisibly).
- ❌ **The "one ecosystem" promise isn't wired:** `ii-alternative-origins` is empty, so the shared-identity story across the 5 apps doesn't actually function yet.
- ⚠️ **Two conflicting token models** exist (vault: 100M / 55-30-15; public page: $CF / 46-27-22) and **the token has no defined utility yet.**

**Verdict:** ~70% of the way to *"a private encrypted AI workspace on ICP"*; ~25% of the way to *"an autonomous AI agent team."* Launch the former; grow into the latter.

---

## The path (and the one rule)
```
Phase 0  Wire the ecosystem (identity + cohesion)      → it's ONE product
Phase 1  Make one agent loop real (task → Claude → vault) → there's a PRODUCT
Phase 2  Fleet billing + metering + free-tier quotas    → you can OPEN THE DOORS
Phase 3  Monetize: $CF compute credits + token utility   → there's VALUE CAPTURE
Phase 4  SNS launch (audit, forum, swap)                 → RAISE ICP
```
**The rule, from every data point in the research: do not raise before the product is real.** Product-market fit pre-launch is the single biggest predictor of a successful SNS. (Detail + sequencing in `03-mvp-roadmap`.)

---

## Top decisions only *you* can make
1. **Reconcile the token model** (100M/55-30-15 vs $CF/46-27-22) → adopt one. Recommended defensible split in `04 §2`: **swap 30 / treasury 43 / team 15 (vested) / seed 2 / community 10.**
2. **Commit $CF's utility = compute credits + stake-to-unlock + treasury-funded free tier + governance** (`04 §3`). This is the highest-leverage decision in the whole plan — it answers "what is the token for?" *and* "how do the masses get in cheaply, sustainably?"
3. **Greenlight the 3 launch blockers** (`03 §2`): wire ecosystem identity, make one agent loop real, add fleet metering + a paywall/quota.
4. **Approve the re-positioning** from "coding agent" to **"a private AI workspace you own"** (`02 §1, D1`) — escapes the saturated, $20-anchored dev-tool fight into a larger privacy-motivated audience.

---

## Numbers that matter (from `01-research`)
- **Realistic SNS raise band:** **~0.4–1.0M ICP** direct (+ possible Neuron Fund match ≤1:1). 2023 peers: OpenChat 1.0M ICP, Kinic ~0.5M, BOOM ~0.4M, IC Ghost just 20K. Market is **proven but modest** (~30 SNS DAOs by end-2024). **Cite ICP, not USD** (price-volatile).
- **Pricing gravity is ~$20/mo** across the entire agent market (Claude Code, Cursor, Devin-now, Replit, Manus); power tiers $100–$200. **Usage/credit metering is now standard** because agent cost is unbounded — which is exactly why fleet metering is a launch blocker.
- **SNS launch cost/timeline is *not* publicly standardized** — the dominant costs are a **security audit** + cycles runway; the dominant time is **forum review + audit lead time** (weeks). Validate directly before setting a calendar. *(Open question — `01 §A6`.)*
- **Closest competitors are adjacent, not direct:** Phala (TEE compute — trust model dented by 2025 "TEE.Fail"), Virtuals (tokenized agents — market down ~80% from peak). Nobody combines your six differentiators.

---

## If you do only five things
1. **$CF = compute credits + a treasury-subsidized free tier** (`02 B1/B3`, `04 §3`) — solves accessibility-vs-cost *and* gives the token a reason to exist.
2. **Lead with no-wallet Internet Identity onboarding + a free bring-your-own-compute tier** (`02 A1/A2`) — max reach, near-zero treasury cost, mostly *finishing* what's built.
3. **Make one real agent loop** (`03 Phase 1`) — turns the demo into a product.
4. **Wire ecosystem identity** (`ii-alternative-origins`) + soften HQ's chrome to match the control plane (`03 Phase 0`, `05`) — makes the 5 apps feel like one company.
5. **Stand up a community/airdrop bucket now** (`02 C1`, `04`) — cheap, compounding, and it strengthens your decentralization story for the swap.

---

## Reading guide
| Doc | What's in it |
|---|---|
| **`01-research-icp-dao-and-agentic-market`** | The cited, fact-checked evidence base: SNS mechanics, the swap, Neuron Fund matching, real raises, the competitor pricing matrix, and the crypto-AI landscape. |
| **`02-positioning-and-mass-accessibility`** | Your moat vs. the market, and the full brainstorm of ways to make HQ accessible to the masses via the DAO. |
| **`03-mvp-roadmap`** | The rough-draft launch plan: real current-state, the launch blockers, the MVP definition, the 5-phase roadmap, and a per-app checklist. |
| **`04-sns-tokenomics-decisions`** | Reconciles your two token models, defines $CF utility, and gives recommended defaults for every open knob + the launch-readiness gates. |
| **`05-design-cohesion`** | How to make CafresoHQ feel like the ecosystem (keep the pixel office as a feature; unify chrome + tokens). |

---

## Honest caveats
- Some agentic-market prices and all SNS cost/timeline figures are **fast-moving or unverified** — flagged inline as `[Approx]`/`[Gap]` and listed in `01 §C`. Re-verify before committing money or dates.
- The recommended token split and parameters in `04` are **proposals for the community forum**, not final decisions — they're grounded in peer launches (ELNA, WaterNeuron) and your own internal analysis, but the actual numbers are yours to set.
- This package assumes the architecture I read in the code is current. If priorities have shifted, the roadmap phases re-order cleanly.

---

*Package authored overnight from: a full read of the CafresoHQ codebase + your internal SNS/tokenomics vault research, a 107-agent adversarially-verified deep-research run, and targeted follow-up searches. — Claude*
