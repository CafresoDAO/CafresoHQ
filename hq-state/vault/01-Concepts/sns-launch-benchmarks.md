---
title: SNS Launch Benchmarks
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/sns-launch-benchmarks
  - icp/governance/sns
  - icp/sns/tokenomics
source:
  - https://dashboard.internetcomputer.org/sns
  - https://internetcomputer.org/sns
  - https://forum.dfinity.org
  - https://github.com/dfinity/ic
related:
  - "[[sns-tokenomics]]"
  - "[[sns-init-config]]"
  - "[[sns-launch]]"
  - "[[sns]]"
difficulty: intermediate
open_questions:
  - Every numeric row marked '?' below requires verification against either dashboard.internetcomputer.org/sns/<project> or the project's published forum-thread pre-launch post. Do NOT quote the '?' rows as if confirmed.
  - Whether DFINITY publishes a canonical machine-readable archive of historical `sns_init.yaml` payloads; if so this note should cite that source directly rather than individual project posts.
  - Whether Neurons' Fund participation is reliably reported per-SNS on dashboard.internetcomputer.org or only in the original proposal payload.
---

# SNS Launch Benchmarks

> A catalogue of publicly-launched SNSs and the shape of their initial token distributions — intended as a reference for sizing a new launch, **not** as a set of numbers to copy blindly. Every figure below marked `?` is unverified in this vault and must be checked against the dashboard or the project's own published tokenomics.

## Why it exists

Designing an `sns_init.yaml` with no reference point is how teams end up with tokenomics that are either radically off consensus (and fail community review) or conspicuously template-shaped (which signals inattention). A benchmark table lets a team position their choices relative to the field — "our dev bucket is smaller than most", "our treasury is at the high end", "our swap is at the low end of the decentralization floor" — and then *defend* those positions rather than stumble into them. The purpose of this note is strictly reference; the analysis of whether a given split is sensible lives in [[sns-tokenomics]] and in any per-project analysis (e.g. [[tokenomics-100m-analysis]]).

## How to use this table

- **All numeric cells default to `?` until verified from primary sources.** Primary sources in priority order: the project's `dashboard.internetcomputer.org/sns/<id>` page, the original `CreateServiceNervousSystem` proposal payload (findable via the NNS proposal dashboard), the project's launch-thread on forum.dfinity.org, the project's own tokenomics post.
- **Do not fabricate.** If a row is `?`, leave it `?`. Wrong numbers are worse than missing ones here because they circulate.
- **Numbers drift** — post-launch events (airdrops, treasury spends, token burns) change *circulating* supply and treasury share. The benchmarks below refer to *initial* distribution at genesis, which is the quantity comparable to a pre-launch `sns_init.yaml`.
- **Not all launches are comparable.** Early-era SNSs (OpenChat, ICPSwap) launched under the *multi-proposal* model that pre-dated the 1-proposal flow; some field names and defaults differ from current. Later launches used the 1-proposal model. Both are instructive but not identically-shaped.

## Qualitative landscape (what has shipped)

Publicly-known SNS launches referenced across dashboard.internetcomputer.org, forum.dfinity.org, and DFINITY's own ecosystem communications include (not an exhaustive list — verify currency against the dashboard):

- **OpenChat** — chat/messaging dapp; one of the first SNSs.
- **Dragginz** (the project by the Kinic/ORIGYN-adjacent team; historical name **SNS-1**/Kinic era) — early-era SNS.
- **Kinic** — search dapp.
- **ICPSwap** — DEX on ICP.
- **BOOM DAO** — gaming ecosystem.
- **WaterNeuron** — NNS-neuron liquid-staking.
- **Gold DAO** — tokenised-gold governance.
- **ELNA** — AI ecosystem.
- **YRAL** — short-video / social.
- Additional launches continue to land; the dashboard is the current-truth list.

Every entry above is a *name* the note author is confident appeared publicly in the SNS launch list. **Tokenomic figures for each project are not transcribed in this note** because they were not verifiable through WebFetch against the current docs/dashboard at the time this note was written, and the charter forbids inventing them.

## Comparison table (template, fill from primary sources)

The columns below are the fields a benchmarking exercise should capture for each launch. Populate rows by looking up each project on `dashboard.internetcomputer.org/sns` and the `CreateServiceNervousSystem` proposal payload.

| Project      | Total supply | Swap % | Dev/team % | Treasury % | Neurons' Fund % | Notable vesting / dissolve-delay | Source |
|--------------|-------------:|-------:|-----------:|-----------:|----------------:|----------------------------------|--------|
| OpenChat     | ?            | ?      | ?          | ?          | ?               | ?                                | ?      |
| Dragginz     | ?            | ?      | ?          | ?          | ?               | ?                                | ?      |
| Kinic        | ?            | ?      | ?          | ?          | ?               | ?                                | ?      |
| ICPSwap      | ?            | ?      | ?          | ?          | ?               | ?                                | ?      |
| BOOM DAO     | ?            | ?      | ?          | ?          | ?               | ?                                | ?      |
| WaterNeuron  | ?            | ?      | ?          | ?          | ?               | ?                                | ?      |
| Gold DAO     | ?            | ?      | ?          | ?          | ?               | ?                                | ?      |
| ELNA         | ?            | ?      | ?          | ?          | ?               | ?                                | ?      |
| YRAL         | ?            | ?      | ?          | ?          | ?               | ?                                | ?      |

**Notes on filling this table:**

- `Swap %`, `Dev/team %`, `Treasury %` should sum to 100% of initial supply *minus* any explicit airdrop bucket. If a project reports an airdrop as a named separate bucket, add a column for it rather than silently folding it into one of the three.
- `Neurons' Fund %` is **not** a share of supply — it is the share of the *swap ICP raise* contributed by the Neurons' Fund. Capture it in ICP or as a percentage of swap ICP, explicitly, and keep it in its own column to avoid confusion with the supply split.
- `Notable vesting / dissolve-delay` should include whether dev neurons are vested multi-year, dissolve-delayed to multi-year, or both.
- `Source` should be a dashboard URL or a forum URL, not a memory citation.

## Qualitative observations (from the public conversation, not per-launch numbers)

The following are patterns repeatedly discussed on forum.dfinity.org in SNS launch-review threads; they are not numeric claims, so they are safe to assert qualitatively even without a per-project table. **Verify that any of them still apply to the specific benchmark launch you're comparing against.**

- **Swap shares have clustered in the 20–50% band** across the publicly visible SNSs. Below ~20% the launch tends to draw "insufficient decentralization" criticism; above ~50% dev and treasury shares get squeezed enough to raise sustainability questions.
- **Treasury shares often sit in a 30–50% band**, sometimes higher for projects explicitly funding ecosystem or gaming content pipelines. 55%+ treasury is uncommon and has historically needed an explicit public spending roadmap to pass community review.
- **Dev/team shares in the 10–25% band are common**, with wide variation in vesting. The headline number matters less than the schedule; a 15% dev allocation with full multi-year vesting reads very differently from 15% with short or unclear vesting.
- **Neurons' Fund match** has been a routine participant in most recent launches and is often non-trivial relative to the public ICP contribution — plan tokenomics assuming NF *will* match unless you explicitly opt out.
- **Minimum raise vs. maximum raise ratio.** Launches where the minimum raise was set close to the maximum tend to either fail cleanly or over-subscribe; launches with a wide (min, max) band tend to finalise somewhere in between. Neither is "right" — it's a decision about risk appetite.

## Gotchas

- **Don't cite this table until it's filled.** A `?` row is a TODO, not a benchmark.
- **"Public tokenomics post" ≠ authoritative payload.** Teams sometimes post a tokenomics narrative on the forum that differs in small ways from the `sns_init.yaml` they actually submitted. The proposal payload is the source of truth.
- **Circulating supply drifts post-launch.** Treasury spends, vesting unlocks, and burns all move the numbers; initial distribution is what's comparable across launches, circulating distribution is what's relevant for trading and voting weight *today*.
- **"Neurons' Fund 10%" is ambiguous.** 10% of the raise *in ICP*? 10% of the swap's SNS-token bucket? 10% of total supply? Always specify the denominator.
- **Airdrops are sometimes sub-buckets of dev or treasury, and sometimes declared separately.** When comparing two launches, check that the airdrop line is being accounted the same way in both.

## See also

- [[sns-tokenomics]]
- [[sns-init-config]]
- [[sns-launch]]
- [[sns-launch-readiness]]
- [[sns-operations]]
- [[sns]]
- [[tokenomics-100m-analysis]]
