---
tags: [research, ICP, SNS, launch, NNS]
---

# SNS Launch Process — Step by Step

[[01-sns-dao-overview]] · [[03-tokenomics]] · [[04-sustainability]]

## Pre-Launch Checklist

Before submitting anything to the NNS:

- **Prepare SNS init YAML file** — defines all governance parameters; start from DFINITY's template and annotate every value with context
- **Test locally** — run the full SNS launch simulation locally to catch parameter inconsistencies
- **Add NNS root as controller** — dapp developers must add the NNS root canister as an additional controller on all dapp canisters *before* submitting the proposal
- **Community review** — post the init file publicly (DFINITY forum) so NNS neuron holders can scrutinize it

## Launch Stages (1-Proposal Flow)

| Stage | What happens |
|---|---|
| 1. Prep | Developer creates SNS init YAML with tokenomics, neuron params, swap params |
| 2. Hand-over | NNS root added as co-controller of dapp canisters |
| 3. NNS Proposal | Any eligible NNS neuron submits `CreateServiceNervousSystem` proposal |
| 4. NNS Vote | NNS community votes; proposal needs majority to pass |
| 5. SNS Deploy | If approved, NNS automatically deploys all SNS canisters (governance, ledger, root, swap) |
| 6. Decentralization Swap | SNS swap canister opens; participants send ICP, receive SNS tokens |
| 7. Swap finalization | If swap meets minimum ICP target → DAO goes live; if not → funds returned |
| 8. DAO control | Community neurons now control all dapp upgrades and treasury |

## Critical Parameters in the Init File

- **Governance params**: voting reward rate, neuron minimum stake, dissolve delay requirements
- **Token distribution**: developer allocation, treasury, swap allocation (must sum correctly)
- **Swap params**: min/max ICP to raise, min participants, swap duration
- **Neuron params**: vesting schedules for developer neurons (prevents immediate dump)

## Common Failure Points

- NNS proposal rejected → insufficient community trust; fix with better documentation and forum engagement
- Swap fails to meet minimum → funds refunded, DAO doesn't launch; fix with realistic targets and pre-committed participation
- Parameter inconsistencies → proposal rejected at validation; fix with local testing

## Official Resources

- Stages doc: https://internetcomputer.org/docs/building-apps/governing-apps/launching/launch-summary-1proposal
- Init params: https://docs.internetcomputer.org/building-apps/governing-apps/tokenomics/preparation
- Checklist: https://internetcomputer.org/docs/building-apps/governing-apps/tokenomics/sns-checklist