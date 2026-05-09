---
tags: [research, tokenomics, sns, inflation, deflation]
---

# Token Supply Dynamics: Inflation vs Deflation Mechanisms

## Core Tension

SNS must balance two opposing forces:
- **Inflationary mechanisms** → increase circulation, promote economic activity, reward participation
- **Deflationary mechanisms** → preserve holder value, create scarcity, prevent dilution

Neither is inherently superior; the right mix depends on DAO stage and goals.

## Inflationary Mechanisms

**Emission schedules** control new token creation:
- Common models: fixed rate (e.g., 5% annually), declining rate (halving events), dynamic rate (adjusts based on network activity)
- Benefits: incentivizes staking/voting, funds ongoing development, rewards early contributors
- Risks: dilutes existing holders if emission > value creation, can spiral into death spiral if poorly calibrated

**Best practice**: Front-load emissions during launch phase to bootstrap participation, then taper to <3% annual inflation for mature DAOs.

## Deflationary Mechanisms

**Token burning** systematically removes supply:
- Revenue burns: protocol fees → burn (creates direct value-accrual for holders)
- Activity burns: transaction fees, governance proposal deposits
- Buyback-and-burn: treasury purchases tokens from market then destroys them

**Example**: 100% burn mechanism where node-generated revenue is removed from circulation creates "genuine scarcity" and counters inflation without requiring external demand.

## Dual-Token Models

Separating **governance** and **value** functions:
- Governance token: non-transferable or low-velocity, used for voting only
- Utility token: high-velocity, used for transactions/fees
- Prevents governance attacks via market manipulation
- Allows independent tuning of each token's supply dynamics

**Caution**: Adds complexity; only justified for high-throughput DAOs with significant transaction volume.

## SNS-Specific Considerations

For [[neuron-staking-voting-power-mechanics]], inflation rewards long-term stakers:
- Voting rewards typically 5-15% APY for max-dissolve-delay neurons
- Lower rewards for shorter lock periods
- Creates natural deflation for circulating supply (locked ≠ circulating)

For [[sns-treasury-and-initial-token-distribution]], initial allocation impacts inflation tolerance:
- High community allocation (>60%) → can tolerate higher inflation to fund development
- High team/investor allocation → needs deflationary pressure to prevent sell-off spiral

## Sustainability Framework

**Healthy DAO token economics**:
1. Inflation rate ≤ real value creation rate (measured by treasury growth, revenue, or TVL)
2. Emission schedule is transparent and immutable (or requires supermajority to change)
3. At least one deflationary sink (burns, permanent locks, etc.)
4. Circulating supply <70% of total supply (rest locked in staking/vesting)

**Red flags** (from [[dao-failures-tokenomics-mistakes]]):
- Uncapped inflation with no burn mechanism
- Emission schedule controlled by small group without timelock
- >80% circulating supply at launch (no lock-up incentives)

## Implementation in SNS Init File

Key parameters:
- `initial_voting_period_seconds` + `neuron_minimum_dissolve_delay_to_vote_seconds` → controls lock-up incentives
- Voting rewards → effective inflation rate for stakers
- Transaction fee structure → potential deflationary sink
- Treasury allocation rules → whether fees accumulate or burn

**Recommended approach**: Start with 8-12% voting rewards (inflationary), implement fee burns (deflationary), front-load 40% of emissions in first 2 years, then taper to 2-3% perpetual inflation.

---
*Related: [[governance-voting-parameters]], [[token-vesting-schedules-design]]*