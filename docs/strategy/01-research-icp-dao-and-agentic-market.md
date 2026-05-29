# 01 · Research — ICP DAO (SNS) Landscape & the Agentic-Tooling Market

> **Status:** Cited research report · Generated 2026-05-29
> **Method:** Multi-agent deep-research with adversarial verification (107 agents, 25 sources fetched, 108 claims extracted, top 25 fact-checked by 3-vote panels → 22 confirmed, 3 killed), plus targeted founder-directed follow-up searches for the competitor pricing matrix and SNS allocation examples.
> **How to read confidence:** Claims marked **[High]** rest on DFINITY primary docs / IC Wiki / on-chain artifacts and passed unanimous verification. **[Approx]** = directionally right but price/USD-sensitive or from secondary aggregators. **[Gap]** = could not be verified — treat as an open question, listed in §C.

---

## Part A — ICP DAOs and the SNS Framework

### A1. How an SNS DAO works, and how you launch one **[High]**
- An **SNS (Service Nervous System)** is a per-project DAO modeled on the NNS: a set of system canisters (governance, ledger, root, swap, index) that take over control of your dapp's canisters. Token holders stake into **neurons** and vote on proposals (upgrades, treasury spends, parameter changes).
- **Since the August 2023 amendment, you launch with a *single* NNS proposal** (`CreateServiceNervousSystem`). If the NNS adopts it, the SNS canisters are created, your dapp is handed over, and the **decentralization swap starts and finishes automatically.** Only two stages are manual: (1) developer prep, and (2) the NNS community vote.
  - *Sources:* [launch-summary-1proposal](https://internetcomputer.org/docs/building-apps/governing-apps/launching/launch-summary-1proposal), [NNS/SNS update Aug 25 2023](https://forum.dfinity.org/t/nns-sns-update-august-25-2023/22303)
- **All parameters live in one `sns_init.yaml`** — token name/symbol, ledger fee, tokenomics, the initial distribution, and the swap conditions (start time, min/max ICP). The *same file* is used for local testflight and production (`dfx sns propose`). 2024-2025 changes ("Swap as a proper SNS canister," a revised hand-off workflow) **refine but do not overturn** this model.
  - *Sources:* [tokenomics/preparation](https://docs.internetcomputer.org/building-apps/governing-apps/tokenomics/preparation), [dfinity/sns-testing example_sns_init.yaml](https://github.com/dfinity/sns-testing/blob/main/example_sns_init.yaml)

### A2. The decentralization swap = the ICP-raising mechanism **[High]**
- Swap parameters set: **minimum ICP** to succeed, **maximum ICP** to collect, **minimum distinct participants**, **per-principal max ICP**, a **confirmation text**, and optional **excluded countries** (ISO codes, IP-enforced).
- If the swap **succeeds**, every participant pays the same price and receives SNS tokens **as a basket of neurons** (2–10 neurons with staggered dissolve delays, set by `VestingSchedule.events`), **pro-rated** to their share of total ICP. If it **fails to hit the minimum, all ICP is refunded.**
- *Sources:* [tokenomics/preparation](https://docs.internetcomputer.org/building-apps/governing-apps/tokenomics/preparation), [example_sns_init.yaml](https://github.com/dfinity/sns-testing/blob/main/example_sns_init.yaml)

### A3. Neurons' Fund matching — free leverage on your raise, with a hard cap **[High]**
- The **Neurons' Fund (NF)** lets NNS neuron-holders auto-contribute ICP to swaps. Its match is bounded **1:1 maximum** (NF contribution ≤ direct participation) **and** additionally capped at **min(10% of NF maturity at execution, 0.75M XDR)**.
- The match follows a **three-phase curve** (lag → growth → saturation), reaching the 1:1 ceiling only near threshold **t₃ = 375k XDR**; **below that, NF typically matches *less* than 1:1.**
- ⚠️ The **0.75M XDR cap is a governance-tunable NNS parameter** (not immutable), and XDR→ICP conversion uses the 30-day average rate at execution. **Model both "NF participates" and "NF doesn't" scenarios** — it materially changes who holds your swap bucket.
- *Sources:* [IC Wiki: Matched Funding](https://wiki.internetcomputer.org/wiki/Matched_Funding), [tokenomics/preparation](https://docs.internetcomputer.org/building-apps/governing-apps/tokenomics/preparation)

### A4. Tokenomics structure + real allocation examples **[High] / [Approx]**
- DFINITY docs recommend **four distribution blocks**: **DAO treasury**, **decentralization swap**, **seed funders**, **funding development team**. Treasury tokens are held by the SNS governance canister and spent only by community vote.
  - *Sources:* [tokenomics/preparation](https://docs.internetcomputer.org/building-apps/governing-apps/tokenomics/preparation), [IC Wiki: Tokenomics of a DAO](https://wiki.internetcomputer.org/wiki/Tokenomics_of_a_DAO)
- **Real peer example — ELNA SNS** `sns_init.yaml`: **swap 25%**, **team 15% (vested 36 months)**, **seed 3% (vested 36 months)**, **LBP + airdrops 5.3% (vested 12 months)** → treasury ≈ remainder. This is a concrete, citable shape to benchmark against. **[Approx]** *(secondary)*
  - *Source:* [elna-ai/SNS sns_init.yaml](https://github.com/elna-ai/SNS/blob/main/sns_init.yaml)
- **Real peer example — WaterNeuron:** "100% of the ICP raised during the SNS will be staked in an 8-year neuron" — i.e. the raised ICP becomes protocol-controlled, long-locked value rather than spent. A useful model for a treasury-credibility story. **[Approx]**
  - *Source:* [WaterNeuron SNS-DAO Launch (forum)](https://forum.dfinity.org/t/waterneuron-sns-dao-launch/31464)

> **Takeaway for `04`:** ELNA's **36-month team vesting** is exactly the dev-vesting commitment Cafreso's own internal tokenomics note flags as missing. Adopt a comparable (or longer) schedule.

### A5. Adoption + verified historical raises **[High], USD [Approx]**
- **Timeline:** SNS-1 test (Nov 2022) → **OpenChat** first production SNS (swap **3 Mar 2023**, **~2,375 participants**, **~1,000,000 ICP for 25M CHAT**). **~14 SNS DAOs by end-2023; ~30 by Dec 2024** (independent arXiv 2507.20234 reports 29 as of Sept 30 2024). The market is **proven but modest, and only recently accelerating.**
- **2023 raises (cite the ICP, not the USD — ICP price is volatile):**

  | Project | ICP raised | ≈USD (2023, approx) |
  |---|--:|--:|
  | OpenChat | 1,000,000 | ~$5.6M |
  | Hot or Not | 1,074,000¹ | ~$4.7M |
  | Modclub | 654,000 | ~$2.3M |
  | Catalyze | 602,000 | ~$1.98M |
  | Sonic | 519,000 | ~$1.5M |
  | Kinic | 509,000 | ~$2.0M |
  | BOOM DAO | 408,900 | ~$1.2M |
  | IC Ghost | 20,000 | ~$84K |

  ¹ includes ~501k expected NF matching. Ecosystem-wide, **>6.5M ICP (~$80M, reported as high as $120M) committed to SNS swaps across 2023.**
- *Sources:* [DFINITY: ICP in 2023](https://medium.com/dfinity/icp-in-2023-the-year-of-sns-daos-and-x-chain-d233ba9c7876), [DFINITY: Governance on ICP in 2024 Part 2](https://medium.com/dfinity/governance-on-icp-in-2024-part-2-sns-2b6ccd799317), [arXiv 2507.20234](https://arxiv.org/abs/2507.20234), [aicoin per-project table](https://www.aicoin.com/en/article/371027), [Cointelegraph: ~$80M pledged](https://cointelegraph.com/news/internet-computer-users-pledge-80-million-decentralize-protocols-2023)

> **Realistic raise band for a credible-but-not-blockbuster launch: ~0.4–1.0M ICP direct** (plus possible NF match), i.e. **low single-digit millions USD.** Anchor your `min_icp` so that *success-at-minimum* still funds the plan; don't set a hopeful-high minimum that triggers a refund.

### A6. Cost & timeline to launch **[Gap → reasoned estimate]**
**No concrete dollar cost or calendar duration survived verification** (the deep-research pass explicitly failed to confirm any), and direct public figures are scarce. What *is* well-established (DFINITY checklist + the team's own `sns-launch-readiness` vault note) are the **cost/time drivers**:
- **Third-party security audit of your canisters** — the single biggest hard cost and a common gating item; budget weeks of lead time and (industry norm) low-to-mid five figures USD+, scope-dependent. **[Gap on exact $]**
- **Cycles runway** — plan **≥90 days** of canister cycles before launch.
- **Public forum review** — open a thread, complete **≥1 revision round**; community/DFINITY scrutiny of tokenomics and decentralization typically runs **weeks**.
- **Engineering prep** — dapp live on mainnet, upgrade round-trip tested, **NNS Root added as co-controller**, fallback controllers set, `sns_init.yaml` validated on a local **testflight**.
- **The automated portion is fast** — once the proposal is adopted, canister creation + swap run on the order of **days** (swap duration is a parameter).
- **Action:** This is **open question #1** — validate exact cost/timeline directly with DFINITY's current SNS preparation docs and 1–2 recent (2025) launch retrospectives before committing a fundraising calendar.

### A7. Lessons, failure modes & best practices (synthesis)
- **Product-market fit *before* the raise is the top success signal.** Strong launches (OpenChat) had live products and real users; the framework does not rescue a pre-product token. *(Verified anecdote-level "winners vs. stalled" comparisons were **killed in verification** — so this is stated as a pattern, not a scoreboard.)*
- **Decentralization is only as real as your swap config.** A low minimum + no NF + few participants = "performative" decentralization the community will call out.
- **Concentration risk:** large treasury + large team bucket = most voting weight in few hands on day one. Mitigate with **long team vesting + long dissolve delays** and by **publishing the day-one voting-power model.**
- **Treasury must have a published use-plan**, not "ecosystem growth." Over-sized treasuries without a roadmap draw criticism (see `04`).

---

## Part B — The Agentic Developer-Tooling & AI-Agent Subscription Market

### B1. Pricing matrix (current, 2026 unless noted) **[Approx — re-verify at planning time]**

| Product | Entry / Pro | Higher tiers | Model |
|---|---|---|---|
| **Claude Code** | Pro **$20** | Max **$100 / $200**; API overflow at token rates (Sonnet ~$3 in / $15 out per M) **[High]** | Subscription, separate from API billing |
| **Cursor** | Pro **$20** | Pro+ **$60**, Ultra **$200**, Teams **$40/user** | Credit-based since Jun 2025 (was 500 req → ~225 at $20) |
| **GitHub Copilot** | Pro **$10** | Pro+ **$39** (usage overage), Business/Enterprise custom; Free tier exists | Per-seat + usage on higher tier |
| **Devin (Cognition)** | **$20** (Devin 2.0, slashed from $500) | **$500/seat** team | Usage (ACU) + seat |
| **Replit** | Core **$25** | Teams **$40** (Agent 3) | Per-seat, usage included |
| **Manus** | Free (300 daily credits) / Standard **$20** (4k credits) | Pro ~**$39** (8k), Extended (40k) | Credit-based |
| **Windsurf (Codeium)** | Free / Pro **$15** | Teams **$30**, Enterprise **$60+** | Flat + monthly prompt credits |
| **Amazon Q Developer** | **$19** | custom | Per-seat |
| **Tabnine** | **$12** | **$39** business | Flat-rate |
| **v0 / Lovable / Bolt.new** | ~**$20** entry | higher credit packs | Credit/usage-based **[Gap on exact 2026 tiers]** |

- *Sources:* [Claude Code Pro/Max (Anthropic)](https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan), [getdx pricing](https://getdx.com/blog/ai-coding-assistant-pricing/), [Cursor pricing 2026](https://aiproductivity.ai/blog/cursor-pricing/), [Manus pricing](https://www.nocode.mba/articles/manus-ai-pricing), Devin/Replit via [nocode.mba](https://www.nocode.mba/articles/cursor-pricing)

### B2. Pricing-model trends (2024-2026)
- **The anchor price is ~$20/mo** for an individual "pro" agent across nearly every product. **$100–$200** is the new "power user" ceiling (Claude Max, Cursor Ultra).
- **Shift from fixed seats → usage/credits.** Cursor moved to credits (Jun 2025); Manus, v0, Lovable, Bolt are credit-native. Reason: autonomous agents have **unbounded, variable inference cost**, so flat pricing leaks money. *(This is the exact dynamic that makes Cafreso's per-user OCI metering a launch blocker — see `03`.)*
- **Devin's $500 → $20 collapse** shows competitive pressure crushing premium "AI engineer" positioning toward the $20 anchor.

### B3. "Build on ICP with AI" is **no longer a differentiator** **[High]**
- **internetcomputer.org now leads with "Built for agents."** DFINITY explicitly names **Claude Code, Codex, Copilot, Cursor, Perplexity, and its own Caffeine.ai** as agents that "build and deploy services directly into the network," backed by agent-readable **ICP Skills** files.
- **Caffeine.ai** = DFINITY's first-party **no-code, chat-to-app** tool that writes a Motoko backend and deploys on-chain canisters (alpha ~Jul 2025, **15,000+ alpha testers**, broader launch ~Oct 2025).
- **Implication:** "deploy to ICP via AI" is becoming a **DFINITY-led commodity.** Cafreso's moat **cannot** be "AI + ICP." It must be the **zero-knowledge user-owned vault + per-user private compute + the consumer multi-app ecosystem + community ownership (DAO).**
- *Sources:* [internetcomputer.org](https://internetcomputer.org/), [ICP Skills (forum)](https://forum.dfinity.org/t/introducing-icp-skills/65905), [caffeine.ai](https://www.caffeine.ai)

### B4. Crypto-native / private-compute competitors — **adjacent, not direct** **[High, with caveats]**
- **Phala** — confidential AI compute: runs LLMs/agents/GPU jobs inside **hardware TEEs** (Intel TDX CPU, NVIDIA Confidential Computing GPU) with cryptographic attestation ("verify, don't trust"). Markets crypto/web3 AI; **partners include Uniswap and Flashbots** (its `dstack` is a Flashbots project). ⚠️ **Caveat:** 2025 **"TEE.Fail"** DDR5 side-channel research extracted TDX/SEV-SNP attestation keys and **named Phala** — its trust model took a credibility hit.
- **Virtuals Protocol** — a crypto-native, **on-chain ecosystem of tokenized autonomous agents** (identity, capital, jobs, markets, DAO governance; 18,000+ agents on Base/Solana; `VIRTUAL` token). ⚠️ **Caveat:** market deteriorated sharply in late 2025 (token ~80% below Jan-2025 peak; falling revenue/DAUs) — the *model* exists, its commercial success is partly aspirational.
- **Neither combines** ICP-native zero-knowledge vaults + per-user private OCI compute + a multi-app consumer ecosystem. **No *direct* competitor to Cafreso's exact thesis surfaced.**
- *Sources:* [phala.com](https://phala.com/), [virtuals.io](https://www.virtuals.io/), [Phala docs](https://docs.phala.network), [Virtuals whitepaper](https://whitepaper.virtuals.io)

---

## Synthesis — gaps & opportunities for CafresoHQ
1. **Your moat is privacy + ownership, not "AI on ICP."** Lead every message with **"your data and your AI workspace are yours — end-to-end encrypted, you hold the keys, the community owns the platform."** That is the one thing Caffeine, Cursor, Devin, and even Phala/Virtuals don't jointly offer.
2. **The $20 anchor is your pricing gravity.** A free tier (BYO-compute/local companion) + a ~$20 hosted tier is the market-expected shape. Usage/credit metering is **mandatory**, not optional, because agent compute is unbounded.
3. **An SNS raise is realistic at ~0.4–1.0M ICP** *if* you launch with a live product and a published, defensible tokenomics + decentralization story. The mechanism is well-documented and largely automated; the **gating work is audit + forum review + a real product.**
4. **DAO ownership is itself a wedge** in a market where every competitor is a VC-funded company that can raise prices or change terms (Cursor's credit cut, Devin's $500→$20 whiplash). "Own a piece of the AI workspace you use" is a genuinely differentiated consumer story (developed in `02`).

---

## C. Caveats & open questions (be honest with investors)
- **[Open #1] Exact SNS launch cost & timeline** — not verified; dominated by audit + forum review + cycles. Validate directly before setting a fundraising calendar.
- **[Open #2] Verified peer allocation ratios** beyond ELNA/WaterNeuron — pull 3–4 real `sns_init.yaml`s from `dashboard.internetcomputer.org/sns` before freezing your split.
- **[Open #3] Full competitor pricing is fast-moving** — re-check Cursor/Copilot/Devin/Replit/Lovable/v0/Bolt/Manus/Windsurf at planning time; several 2026 tiers here are **[Approx]**.
- **Killed in verification (do NOT cite):** a "$20.6M / 11 projects" combined figure; "Dragginz 20x / Modclub stalled" outcome anecdotes; two project-list enumerations. All failed 3-vote checks.
- **USD figures are price-sensitive** — the same 6.5M ICP was reported as both ~$80M and ~$120M. **Cite ICP quantities.**

---

*Companion docs: `00-executive-summary`, `02-positioning-and-mass-accessibility`, `03-mvp-roadmap`, `04-sns-tokenomics-decisions`, `05-design-cohesion`.*
