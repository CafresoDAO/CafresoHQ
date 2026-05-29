// Governance seed data — 5 proposals spanning all status types.
// body arrays use PostRenderer block format (same as blog posts).
// Once the SNS canister is live these will be fetched via agent-js;
// the seed acts as both demo data and the offline fallback.

export const PROPOSAL_TYPES = {
  tokenomics:  { key: 'tokenomics',  label: 'Tokenomics',       icon: 'chart-pie',       color: 'hsl(43 74% 54%)' },
  treasury:    { key: 'treasury',    label: 'Treasury',          icon: 'vault',           color: 'hsl(112 43% 45%)' },
  upgrade:     { key: 'upgrade',     label: 'Protocol Upgrade',  icon: 'arrow-circle-up', color: 'hsl(210 80% 58%)' },
  motion:      { key: 'motion',      label: 'Motion',            icon: 'file-text',       color: 'hsl(260 70% 62%)' },
  governance:  { key: 'governance',  label: 'Governance',        icon: 'gavel',           color: 'hsl(24 48% 35%)' },
};

export const PROPOSAL_STATUSES = {
  open:     { key: 'open',     label: 'Open',     color: 'hsl(112 43% 45%)',  bg: 'hsl(112 40% 92%)' },
  passed:   { key: 'passed',   label: 'Passed',   color: 'hsl(210 80% 48%)',  bg: 'hsl(210 60% 93%)' },
  rejected: { key: 'rejected', label: 'Rejected', color: 'hsl(0 62% 48%)',    bg: 'hsl(0 50% 94%)' },
  pending:  { key: 'pending',  label: 'Pending',  color: 'hsl(43 74% 44%)',   bg: 'hsl(43 74% 92%)' },
  executed: { key: 'executed', label: 'Executed', color: 'hsl(262 52% 44%)',  bg: 'hsl(262 40% 92%)' },
};

// Helper: ms timestamp relative to "now" for realistic deadlines.
const NOW = 1746662400000; // 2026-05-08 00:00 UTC (stable for seed)
const DAY = 86_400_000;

export const PROPOSALS = [
  // -------------------------------------------------------------------------
  // 1 — Open tokenomics vote
  // -------------------------------------------------------------------------
  {
    id: 'prop-001',
    title: 'Set $CF Staking APY to 7.25% for Q2 2026',
    summary:
      'Adjust the base staking APY from 6.5% to 7.25% to incentivise longer lock-up periods ahead of the mainnet launch window.',
    type: 'tokenomics',
    status: 'open',
    deadline: NOW + 2 * DAY + 14 * 3600_000, // ~2d 14h from seed date
    votes: { yes: 4_210_000, no: 380_000, abstain: 620_000, total: 14_800_000 },
    quorumPct: 3,   // % of total supply needed for quorum
    proposedBy: { name: 'Cafreso Core', hue: 220 },
    block: 4_218_812,
    forumSlug: 'q2-apy-proposal-discussion',
    blogSlug: null,
    sneedLink: 'https://app.sneeddao.com/proposals',
    body: [
      {
        kind: 'h2',
        text: 'Rationale',
      },
      {
        kind: 'p',
        text: 'With the mainnet launch approaching, sustaining a meaningful staking yield is critical to attracting early $CF holders. Historical ICP-native token launches show a 20-30% higher neuron-stake rate when APY exceeds 7%. The proposed 7.25% rate remains comfortably within treasury sustainability projections for the next 12 months.',
      },
      {
        kind: 'callout',
        icon: '📊',
        title: 'Treasury model',
        text: 'At 7.25% APY with 12-month projection, the treasury draw is estimated at 1.07M $CF — within the approved Q2 budget envelope of 1.4M $CF.',
      },
      {
        kind: 'stats',
        items: [
          { label: 'Current APY',    value: '6.50%' },
          { label: 'Proposed APY',   value: '7.25%' },
          { label: 'APY Delta',      value: '+0.75%' },
          { label: 'Q2 Treasury Est.', value: '1.07M $CF' },
        ],
      },
      {
        kind: 'calculator',
        apy: 7.25,
        min: 250,
        max: 50000,
        step: 250,
        currency: 'CF',
      },
    ],
  },

  // -------------------------------------------------------------------------
  // 2 — Passed treasury proposal
  // -------------------------------------------------------------------------
  {
    id: 'prop-002',
    title: 'Treasury Allocation: Community Marketing Budget Q2 2026',
    summary:
      'Allocate 120,000 $CF from the treasury to fund community-led marketing initiatives, influencer partnerships, and ICP ecosystem conferences for Q2 2026.',
    type: 'treasury',
    status: 'passed',
    deadline: NOW - 8 * DAY,
    votes: { yes: 8_440_000, no: 920_000, abstain: 310_000, total: 14_800_000 },
    quorumPct: 3,
    proposedBy: { name: 'Growth Guild', hue: 112 },
    block: 4_194_230,
    forumSlug: 'q2-marketing-budget-discussion',
    blogSlug: null,
    sneedLink: 'https://app.sneeddao.com/proposals',
    body: [
      {
        kind: 'h2',
        text: 'Scope of Spend',
      },
      {
        kind: 'p',
        text: 'The Growth Guild has identified three primary channels for Q2 community marketing: ICP ecosystem conferences (42k $CF), creator partnership programme (48k $CF), and a community bounty board for content, translations and tooling (30k $CF).',
      },
      {
        kind: 'stats',
        items: [
          { label: 'Conferences',  value: '42,000 $CF' },
          { label: 'Creators',     value: '48,000 $CF' },
          { label: 'Bounties',     value: '30,000 $CF' },
          { label: 'Total Budget', value: '120,000 $CF' },
        ],
      },
      {
        kind: 'callout',
        icon: '✅',
        title: 'Status',
        text: 'This proposal passed and funds have been transferred to the Growth Guild multi-sig at block #4,194,301.',
      },
    ],
  },

  // -------------------------------------------------------------------------
  // 3 — Rejected governance motion
  // -------------------------------------------------------------------------
  {
    id: 'prop-003',
    title: 'Disable Anonymous Forum Posting',
    summary:
      'Require Internet Identity authentication for all forum posts to reduce spam and increase accountability in governance discussions.',
    type: 'governance',
    status: 'rejected',
    deadline: NOW - 15 * DAY,
    votes: { yes: 1_820_000, no: 6_440_000, abstain: 880_000, total: 14_800_000 },
    quorumPct: 3,
    proposedBy: { name: 'Community Member', hue: 0 },
    block: 4_177_409,
    forumSlug: 'anonymous-posting-debate',
    blogSlug: null,
    sneedLink: 'https://app.sneeddao.com/proposals',
    body: [
      {
        kind: 'h2',
        text: 'Background',
      },
      {
        kind: 'p',
        text: 'A community member proposed that all forum posts require Internet Identity (II) authentication to combat spam and coordinated low-quality content. The motion generated significant debate over the trade-off between accessibility and accountability.',
      },
      {
        kind: 'callout',
        icon: '🗳️',
        title: 'Community verdict',
        text: 'The DAO rejected this proposal 78% to 22%. Key concern: requiring II authentication would create a barrier to entry that disadvantages non-technical users and newcomers. A softer rate-limiting mechanism is under research.',
      },
      {
        kind: 'h2',
        text: 'Next Steps',
      },
      {
        kind: 'p',
        text: 'The Core team will explore II-optional reputation scoring (posts from authenticated principals carry a "verified" badge) and progressive trust levels as an alternative to hard authentication requirements.',
      },
    ],
  },

  // -------------------------------------------------------------------------
  // 4 — Executed upgrade
  // -------------------------------------------------------------------------
  {
    id: 'prop-004',
    title: 'Protocol Upgrade: CanDB Partition Rebalance v1.2',
    summary:
      'Upgrade the CanDB storage layer to v1.2, implementing partition rebalancing to support 10× the current user load before canister memory limits are reached.',
    type: 'upgrade',
    status: 'executed',
    deadline: NOW - 22 * DAY,
    votes: { yes: 11_200_000, no: 140_000, abstain: 290_000, total: 14_800_000 },
    quorumPct: 3,
    proposedBy: { name: 'Cafreso Core', hue: 220 },
    block: 4_161_005,
    forumSlug: null,
    blogSlug: null,
    sneedLink: 'https://app.sneeddao.com/proposals',
    body: [
      {
        kind: 'h2',
        text: 'What Changed',
      },
      {
        kind: 'p',
        text: 'CanDB v1.2 introduces automatic partition splitting when any single canister approaches 1.8 GB of heap, preventing unbounded growth and ensuring sub-200 ms read latency across the full principal dataset.',
      },
      {
        kind: 'stats',
        items: [
          { label: 'Previous max principals', value: '~42,000' },
          { label: 'New max principals',       value: '420,000+' },
          { label: 'Avg read latency',         value: '< 200 ms' },
          { label: 'Upgrade block',            value: '#4,161,188' },
        ],
      },
      {
        kind: 'callout',
        icon: '🚀',
        title: 'Executed successfully',
        text: 'The canister upgrade was executed at block #4,161,188 with zero downtime. All partitions rebalanced within 4 hours of the upgrade.',
      },
    ],
  },

  // -------------------------------------------------------------------------
  // 5 — Pending motion (awaiting quorum threshold to open)
  // -------------------------------------------------------------------------
  {
    id: 'prop-005',
    title: 'Testnet Reward Airdrop: 500 $CF per Eligible Principal',
    summary:
      'Distribute 500 $CF to every principal that participated in testnet activities (posts, votes, or burns) before block #4,200,000 as a retroactive reward.',
    type: 'motion',
    status: 'pending',
    deadline: NOW + 5 * DAY,
    votes: { yes: 0, no: 0, abstain: 0, total: 14_800_000 },
    quorumPct: 3,
    proposedBy: { name: 'Community Member', hue: 43 },
    block: 4_220_001,
    forumSlug: 'testnet-airdrop-proposal',
    blogSlug: null,
    sneedLink: 'https://app.sneeddao.com/proposals',
    body: [
      {
        kind: 'h2',
        text: 'Eligibility Criteria',
      },
      {
        kind: 'p',
        text: 'Any Internet Identity principal that completed at least one of the following on the Cafreso testnet before block #4,200,000: authored a dev log post, submitted a forum reply, cast a governance vote, or tipped another user via the burn mechanism.',
      },
      {
        kind: 'progress',
        label: 'Eligible principals verified',
        value: 614,
        max: 2000,
        unit: 'principals',
        color: 'hsl(43 74% 54%)',
      },
      {
        kind: 'callout',
        icon: '⏳',
        title: 'Pending neuron signatures',
        text: 'This proposal requires signatures from 3 of the 5 founding neurons before it opens for community vote. 1 of 3 signatures collected so far.',
      },
      {
        kind: 'stats',
        items: [
          { label: 'Reward per principal', value: '500 $CF' },
          { label: 'Verified principals',   value: '614' },
          { label: 'Estimated total',       value: '307,000 $CF' },
          { label: 'Neuron sigs needed',    value: '3 of 5' },
        ],
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function getProposal(id) {
  return PROPOSALS.find((p) => p.id === id) ?? null;
}

export function proposalType(typeKey) {
  return PROPOSAL_TYPES[typeKey] ?? { key: typeKey, label: typeKey, icon: 'file-text', color: 'hsl(215 16% 47%)' };
}

export function proposalStatus(statusKey) {
  return PROPOSAL_STATUSES[statusKey] ?? { key: statusKey, label: statusKey, color: 'hsl(215 16% 47%)', bg: 'hsl(215 16% 94%)' };
}

/** Returns a human-readable deadline string. */
export function fmtDeadline(ms) {
  const diff = ms - Date.now();
  if (diff <= 0) return 'Closed';
  const days  = Math.floor(diff / 86_400_000);
  const hours = Math.floor((diff % 86_400_000) / 3_600_000);
  if (days > 0) return `${days}d ${hours}h remaining`;
  const mins  = Math.floor((diff % 3_600_000) / 60_000);
  return hours > 0 ? `${hours}h ${mins}m remaining` : `${mins}m remaining`;
}

/** % voted of total supply (for quorum display). */
export function votedPct(votes) {
  if (!votes.total) return 0;
  return Math.round(((votes.yes + votes.no + votes.abstain) / votes.total) * 1000) / 10;
}

/** % of cast votes that are yes. */
export function yesPct(votes) {
  const cast = votes.yes + votes.no + votes.abstain;
  if (!cast) return 0;
  return Math.round((votes.yes / cast) * 1000) / 10;
}
