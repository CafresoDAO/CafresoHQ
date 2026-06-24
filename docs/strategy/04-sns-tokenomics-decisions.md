# 04 · SNS Tokenomics — Decisions to Lock Before You Launch

> **Status:** Draft for founder review · Generated 2026-05-29
> **Builds on** your own internal analysis (`hq-state/vault/05-Projects/tokenomics-100m-analysis.md` and `…-v2-burn-and-staking.md`) — which is thorough, skeptical, and deliberately *unfinished*. This doc's job is to **finish it** with concrete, defensible proposals, using the verified peer data in `01-research`.
> **Nothing here is final** — these are proposals to take to the community forum, not decrees. But "proposed with rationale" beats "TBD" every time a reviewer asks.

---

## 1. First problem: you have two conflicting token models — reconcile them

| Source | Supply | Treasury | Swap | Team/Dev | Seed | Community/Airdrop |
|---|---|---|---|---|---|---|
| **Vault analysis** (`tokenomics-100m-analysis.md`) | 100M | **55%** | **30%** | **15%** | 0% | 0% |
| **Public About page** (`$CF`) | — | **46%** | **27%** | **22%** | — | — |
| **Peer: ELNA SNS** (real `sns_init.yaml`) | — | ~51.7% | 25% | 15% (36mo vest) | 3% (36mo) | 5.3% (12mo) |

These **don't match**, and a forum reviewer *will* notice. Two issues jump out:
- **Treasury 55% (vault) is above the typical 30–50% band** — your own note flags this as needing a public defense.
- **Team 22% (public page) is high** — above ELNA's 15%, near the top of the 10–25% band, and a concentration/dump-risk flag unless heavily vested.

**Action #0: pick one model and retire the other** before anything else ships publicly.

---

## 2. Recommended starting split (a defensible proposal for the forum)

A split that improves decentralization, keeps the team reasonable-and-vested, brings treasury back into the normal band, and **funds the mass-accessibility plan in `02`:**

| Bucket | Proposed | Tokens (of 100M) | Rationale |
|---|--:|--:|---|
| **Decentralization swap** | **30%** | 30,000,000 | At/above peer norm (ELNA 25%); the higher, the more real the decentralization |
| **DAO treasury** | **43%** | 43,000,000 | Back inside the 30–50% band; large enough to fund the free tier + cycles + liquidity *with a published roadmap* |
| **Team / dev** | **15%** | 15,000,000 | Matches ELNA; defensible **only with 36-month vesting + multi-year dissolve delay** |
| **Seed funders** | **2%** | 2,000,000 | If you have them; else fold into treasury |
| **Community / airdrop** | **10%** | 10,000,000 | **New bucket** — powers "earn your stake" onboarding (`02 C1`) and broadens day-one voting distribution |

→ **42% of supply ends up outside team+treasury hands** (swap + seed + community), a materially stronger decentralization story than the original 30%. Treasury drops from 55%→43% (defensible). Team stays at the peer-standard 15%, vested.

*(If you prefer to preserve a larger treasury, the trade is treasury 45% / community 8% — but do not go back above 50% without a line-item treasury roadmap.)*

---

## 3. The big unlock: **what is $CF actually *for*?**

Your own analysis names this the **blocking open question** ("Is there a specific dapp this tokenomics is intended for?"). The answer — grounded in the product — is what makes the whole raise credible. A governance-only token with no operational use is a **documented failure mode** (your `dao-failures-tokenomics-mistakes` note). $CF must *do* something. Proposed utility:

1. **$CF = compute credits.** Agent runs and hosted containers are metered and paid in credits; **$CF tops up credits.** This is real, recurring demand tied to the product actually working. *(Requires metering — `03 Phase 2–3`.)*
2. **Stake-to-unlock.** Staking $CF (a neuron) grants monthly free credits / higher quotas / priority provisioning → a reason to **hold**, not flip, and it doubles as voting power.
3. **Treasury-funded free tier.** The treasury subsidizes onboarding compute by community vote (`02 B3`) — turning the large treasury from a *liability* ("why so much?") into a *feature* ("it funds free access for everyone").
4. **Governance.** Vote on roadmap, treasury spend, the free-tier budget, marketplace bounties.
5. **(Optional) Fee-burn.** A slice of credit spend buys-and-burns $CF, tying token scarcity to real usage (see §4 — and **prefer this over a fixed-schedule burn**).

> This is the single most important thing to nail. **Value flows from usage → credits → $CF demand → treasury sustainability.** Everything else is parameters.

---

## 4. The open knobs → recommended defaults

Your analysis correctly says the headline split is meaningless until these are set. Recommended starting positions:

| Knob | Your note says | Recommended default | Why |
|---|---|---|---|
| **Team vesting** | "single largest risk," unspecified | **36-month linear, 6–12mo cliff**, published per-principal | Matches ELNA; removes the dump-risk flag |
| **Team dissolve delay** | must be long | **Multi-year (e.g. 4–8yr)** on team neurons | Restricts voting-power concentration, not just liquidity |
| **Swap min / max ICP** | unspecified | **min ~0.4M / max ~1.0M ICP** (tune to interest) | Peer band (`01 §A5`); set **min so success-at-minimum still funds the plan** |
| **Min participants** | — | set a **meaningful floor** (peers used hundreds–thousands) | Prevents "performative" decentralization |
| **Per-principal max** | unspecified | cap so no single buyer dominates the basket | Decentralization is a swap-config property, not a bucket size |
| **Neurons' Fund** | unspecified | **opt-in; model both scenarios** | NF matches ≤1:1, capped min(10% NF maturity, 0.75M XDR); free leverage but changes holder mix (`01 §A3`) |
| **Burn** | v2 proposed fixed 10M/yr | **Reject fixed schedule → fee-burn tied to credit usage** | Your v2 analysis shows fixed 10M/yr **exhausts treasury by ~year 5.5**; fee-burn tracks real usage and preserves runway |
| **Voting rewards (APY)** | v2 proposed 8%→2% | **Start ~4–5%, decay** | Your note: 8% is "aggressive"; peers/NNS landed lower |
| **Airdrop / community** | 0% / undecided | **10% bucket** (see §2) | Drives accessibility + decentralization (`02 C1`) |
| **Treasury use** | must publish roadmap | **Publish line-items**: cycles, free-tier subsidy, liquidity, grants, audits, marketing — with sizing + horizon | Converts "55% too much?" into "is this roadmap sensible?" |

*Consider the **WaterNeuron model** (`01 §A4`): staking 100% of *raised ICP* into a long (e.g. 8-year) neuron makes the treasury's backing visibly long-term and yield-bearing — a strong credibility signal.*

---

## 5. Launch-readiness gates + honest cost/timeline

**Gates (from your `sns-launch-readiness` note + DFINITY checklist) — none are closed yet:**
- [ ] Dapp live on mainnet, **upgrade round-trip tested**
- [ ] **NNS Root added as co-controller** of every dapp canister; fallback controllers set to team principals
- [ ] **Third-party security audit** of `cafresohq_keys` + any payment/ledger canister
- [ ] `sns_init.yaml` validated on a **local testflight**
- [ ] **Tokenomics published with rationale** (this doc → a forum post)
- [ ] **Team vesting + dissolve-delay table** published per principal
- [ ] **Swap params sized**; success-at-minimum is viable
- [ ] **Forum thread open, ≥1 revision round** completed
- [ ] **Decentralization roadmap** written
- [ ] **≥90 days cycles runway** funded

**Cost & timeline — be honest: not publicly standardized (`01 §A6`, open question #1).** What's known:
- The **automated part is fast** (post-adoption: canister creation + swap run in **days**).
- The **slow/expensive part is prep:** a **security audit** (the main hard cost — budget weeks of lead time + meaningful $) and the **public forum review/revision cycle** (typically **weeks**).
- **Validate exact numbers** against DFINITY's current SNS prep docs and 1–2 recent (2025) launch retrospectives before you commit a fundraising calendar.

---

## 6. Failure modes to avoid (from your own research + verified findings)
- **Raising before the product is real** — the #1 predictor of SNS failure (`01 §A7`). Launch with a live, ideally revenue/credit-generating product (`03`).
- **Voting concentration on day one** — large team+treasury share with short dissolve delays lets founders outvote the DAO. Fix with vesting + long dissolve + a *published* day-one voting-power model.
- **Rigid tokenomics** — fixed burn/reward schedules that can't adapt (your v2 note). Prefer usage-linked (fee-burn) and governance-tunable.
- **Treasury starvation** — over-spending a big treasury with no roadmap. Publish line-items; size for 10+ years, not 5.5.
- **Abstract token** — governance-only with no operational use. §3 fixes this.

---

## 7. Decision list — lock these before the forum thread (in priority order)
1. **Reconcile to one token model** (§1) and **adopt a split** (§2).
2. **Commit $CF utility = compute credits + stake-to-unlock + treasury-funded free tier + governance** (§3).
3. **Publish team vesting + dissolve-delay** per principal (§4) — your single largest risk.
4. **Size swap min/max + per-principal cap + min participants + NF stance** (§4).
5. **Publish the treasury-use roadmap** (§4).
6. **Decide burn = fee-burn (not fixed) and rewards ≈4–5%** (§4).
7. **Validate launch cost/timeline** directly (§5).

Everything else is downstream of these seven.

---

*Companion docs: `00-executive-summary`, `01-research-icp-dao-and-agentic-market`, `02-positioning-and-mass-accessibility`, `03-mvp-roadmap`, `05-design-cohesion`.*
