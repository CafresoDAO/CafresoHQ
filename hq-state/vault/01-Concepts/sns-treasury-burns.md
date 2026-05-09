---
title: SNS Treasury Burns
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/sns-treasury-burns
  - icp/governance/sns
  - icp/sns/tokenomics
  - icp/sns/supply-dynamics
source:
  - https://github.com/dfinity/ICRC-1/blob/main/standards/ICRC-1/README.md
  - https://github.com/dfinity/ic/tree/master/rs/sns/governance
  - https://docs.internetcomputer.org/building-apps/governing-apps/tokenomics/preparation
related:
  - "[[sns-operations]]"
  - "[[sns-canisters]]"
  - "[[sns-supply-dynamics]]"
  - "[[sns-tokenomics]]"
  - "[[sns-fee-burn-patterns]]"
difficulty: intermediate
open_questions:
  - Exact current name of the SNS proposal type that transfers treasury funds — historically `TransferSnsTreasuryFunds` and/or a generic treasury-disbursement proposal; verify the canonical type name in the current SNS Governance release before quoting.
  - Whether the SNS Ledger's minting account is exposed on the dashboard / via a public accessor so that a "burn" to it can be authored confidently, or whether teams route burns through a canister-controlled address that can never spend (a pragmatic burn address).
  - Whether a "scheduled-burn canister" (a dedicated canister that periodically burns on receipt of treasury transfers on a predictable cadence) is a widely-used pattern or a bespoke per-project contrivance.
---

# SNS Treasury Burns

> The mechanism by which tokens held in the SNS Governance treasury are removed from circulation — each burn is an SNS proposal that, on adoption, executes an ICRC-1 transfer to the ledger's minting account (or to a provably unspendable burn address).

## Why it exists

Treasury burns are the DAO's explicit supply-reduction lever. Unlike genesis allocations (fixed) or voting rewards (formulaic), a treasury burn is a discretionary act: the DAO decides, proposal by proposal, how many tokens to permanently remove. Teams propose burn schedules as part of a "deflationary" narrative, but because each burn requires a proposal and a vote, a schedule is aspirational — the DAO can always vote any particular burn down. This note documents the mechanics so a proposal author can implement a burn correctly, and a proposal reviewer can evaluate whether the "scheduled burn" on the forum actually corresponds to an enforceable on-chain event.

## How it works

### The proposal flow

1. **Draft the proposal.** The canonical type is a treasury-transfer proposal — historically `TransferSnsTreasuryFunds` (verify the current name and schema against the live SNS Governance source). The proposal specifies:
   - Source: the SNS Governance treasury subaccount.
   - Destination: the ICRC-1 minting account, *or* a burn address (see "two burn targets" below).
   - Token: the SNS token (not ICP — for ICP burns the flow is different).
   - Amount: the tokens to burn, in e8s.
   - Memo / justification: visible on-forum and on-proposal.
2. **Submit + vote.** Proposal goes to the DAO with the normal voting window. See [[sns-operations]] and [[sns-neurons-and-voting]].
3. **Execution.** On adoption, SNS Root / Governance instructs the SNS Ledger to perform the transfer. The ledger's `icrc1_total_supply` decreases immediately on execution (if the destination is the minting account) or only if the burn-address controller can never spend (if using a canister-controlled sink).
4. **Verification.** The burn is visible on the ledger's transaction log and should propagate to dashboard.internetcomputer.org's supply view after the next index refresh.

### Two burn targets (pick one, state which)

- **ICRC-1 minting account (the canonical burn).** A transfer to the minting account is, per ICRC-1 spec, a *burn* transaction — tokens are removed from circulation, `total_supply` decreases, no fee is charged, and a minimum-burn threshold applies. This is the unambiguous path: the ledger records a burn, and supply updates automatically.
- **Canister-controlled "burn address" (pragmatic alternative).** Some teams prefer transferring to a canister whose controller is set such that the tokens can provably never be retrieved (e.g. a black-hole canister with no controller, or a canister controlled by a principal that is itself unspendable). This is *not* a burn under ICRC-1 — `total_supply` does not decrease because the tokens still sit in a real account — but it achieves the same economic effect (tokens unreachable). **Do not conflate the two on public communications.** If the project narrative says "burned 5M tokens", the community will read that as `total_supply` falling; if the implementation used a canister sink, `total_supply` does not fall and the narrative is technically incorrect.

Recommendation: unless there is a specific reason otherwise, burn via transfer to the minting account. It is the mechanism the ICRC-1 spec was designed for and the only one that updates supply correctly.

### Governance risk: a schedule is not a guarantee

Every scheduled burn needs an approved proposal at the scheduled time. Implications:

- The DAO can vote any particular burn down. A "10M/year burn schedule" is a commitment the current community has made to itself; a future community is not bound by it.
- A well-timed opposition campaign during the voting window can cause a specific burn to fail — the tokens remain in treasury.
- Governance-calendar gaps (holidays, low-participation periods, contested periods) can delay burns past their nominal date.
- If the SNS Governance release changes the rules for treasury proposals (minimum stake, voting window, quorum), scheduled burns can become harder or easier over time.

A team that wants a hard commitment to burns cannot get one via scheduled-proposal flow; they would need either (a) a scheduled-burn canister pattern or (b) a protocol-level burn (like fee-burns — see [[sns-fee-burn-patterns]]).

### Scheduled-burn canister pattern (optional)

An alternative to proposal-per-burn: deploy a dedicated canister that holds a specified balance of SNS tokens and auto-burns a fixed amount on a fixed cadence. The proposal to *fund* the canister happens once; subsequent burns are executed by the canister itself without further governance action.

Pattern caveats:

- The canister must be controlled in a way that prevents the funds from being diverted — typically controlled by SNS Root (so only an SNS proposal can change its code or configuration).
- The canister must burn correctly (transfer to minting account) each cycle.
- The DAO retains the ability to *stop* future burns by upgrading or destroying the canister via proposal, but the scheduled burns happen autonomously between such interventions.
- This pattern is not in the default SNS canister cluster; teams build it themselves. Verify via source before assuming any project uses it.

## Example

```text
Treasury burn, end-to-end:

  1. Forum post: "Treasury burn proposal — 5M TOK, H1 2027 tranche."
     - Rationale, expected supply delta, community discussion.
  2. Submit TransferSnsTreasuryFunds-style proposal:
       from:    SNS Governance treasury subaccount
       to:      SNS Ledger minting account (burn)
       amount:  5_000_000 × 10^8  (e8s)
       memo:    "scheduled H1 2027 burn"
     - Rejection fee staked.
  3. Voting window opens — typical duration per SNS nervous-system params.
  4. Adopted → SNS Governance signals SNS Ledger to execute transfer.
  5. Ledger: icrc1_total_supply decreases by 5M; tx appears in ledger log.
  6. Treasury balance on dashboard.internetcomputer.org updates after
     the indexer's next refresh.
```

## Gotchas

- **Schedules are aspirational.** Every burn is a proposal and can be rejected. Do not model a "5M/year burn" as enforced — model it as conditional on DAO adoption.
- **"Burn to a wallet we control" is not a burn.** The ICRC-1 definition of burn is a transfer to the minting account; anything else is just a transfer. Ensure the implementation matches the claim.
- **Minimum burn amount applies.** ICRC-1 ledgers can require a minimum burn amount (otherwise BadBurn error); a proposal that burns less than the minimum will fail execution. Verify the SNS Ledger's minimum burn threshold per project.
- **Burn decreases total supply, not treasury-as-a-percentage-of-supply.** A 5M burn from a 55M treasury in a 100M total supply changes total to 95M and treasury to 50M — the treasury's *share* of supply changes from 55% to 50M/95M ≈ 52.6%. This is often surprising in modelling.
- **Treasury must have the tokens.** Burns from treasury are bounded above by treasury balance. If earlier burns or treasury disbursements exhausted the supply, scheduled burns will fail at execution.
- **ICP-burns vs. SNS-token-burns.** Treasury holds both ICP (from the swap) and SNS tokens (from the initial allocation). Burning SNS tokens reduces SNS supply; "burning ICP" is a different operation that reduces the treasury's ICP balance but has no effect on SNS supply. Be explicit about which token.
- **Post-burn, the governance landscape shifts.** Holders' percentage of supply rises proportionally with each burn. This concentrates voting power among the remaining holders — not a problem, but a side-effect worth naming in the proposal.

## See also

- [[sns-operations]]
- [[sns-canisters]]
- [[sns-supply-dynamics]]
- [[sns-tokenomics]]
- [[sns-fee-burn-patterns]]
- [[sns-neurons-and-voting]]
- [[tokenomics-100m-v2-burn-and-staking]]
