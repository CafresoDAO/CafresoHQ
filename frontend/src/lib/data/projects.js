// The Cafreso open-software portfolio.
//
// One record per project we build in the open. The /projects index and each
// /projects/[slug] page read from here; per-project dev-log feeds are pulled
// live from the blog canister filtered by `devlogCat` (see lib/api/devlog.js
// + lib/data/blog.js CATEGORIES), so "planned future updates" live in two
// places by design: the durable `roadmap` below, and the running commentary
// in the dev log.
//
// Keep this the single source of truth — the homepage product row, the footer
// Projects column, and the project pages all derive from it.

export const STATUS = {
  live:    { label: 'Live',    hue: 152, note: 'in production' },
  beta:    { label: 'Beta',    hue: 210, note: 'usable, still hardening' },
  alpha:   { label: 'Alpha',   hue: 45,  note: 'early, rough edges' },
  planned: { label: 'Planned', hue: 240, note: 'on the roadmap' }
};

export const PROJECTS = [
  {
    slug: 'cafresohq',
    name: 'CafresoHQ',
    tagline: 'An office of AI agents you actually own',
    status: 'live',
    accent: 262,
    icon: 'brain',
    url: 'https://ai.cafreso.com',
    repo: 'https://github.com/CafresoDAO/CafresoHQ',
    devlogCat: 'cafresohq',
    summary:
      'A pixel-art office where AI agents work at desks you delegate to — running on your own container, keyed to your Internet Identity, with an on-chain wallet per agent. Bring a free key, a paid model, or your own local GPU.',
    what: [
      'Hire agents, drop tasks on desks, watch work happen in a live office',
      'Your own private container runtime — data never leaves it',
      'Bring your own model: OpenRouter, Gemini, Groq, or a local LM Studio / Ollama GPU',
      'Per-agent on-chain wallets with user-signed spending caps',
      'A markdown vault, site publishing, and payroll — all on the Internet Computer'
    ],
    roadmap: [
      { when: 'Shipped', title: 'Zero-signup free trial brain', done: true },
      { when: 'Shipped', title: 'Operator control panel — toggle features network-wide', done: true },
      { when: 'Shipped', title: 'Local-GPU backends (LM Studio / Ollama) in Settings', done: true },
      { when: 'Next', title: 'Card payments (Stripe) for plans, alongside ICP', done: false },
      { when: 'Next', title: 'Cycles + fleet health dashboard for operators', done: false },
      { when: 'Later', title: 'Invite / referral loop tied to the free tier', done: false }
    ]
  },
  {
    slug: 'search-network',
    name: 'Search Network',
    tagline: 'A public research library, grown by the community',
    status: 'beta',
    accent: 200,
    icon: 'magnifying-glass',
    url: '/library',
    repo: 'https://github.com/CafresoDAO/CafresoHQ',
    devlogCat: 'search-net',
    summary:
      'Ask a question and it is answered from an on-chain library — or queued to a network of community-run GPU workers who earn ICP for each answer. Every entry is permanent, sourced, and explorable as a growing web of knowledge.',
    what: [
      'Anonymous, sign-in-free search from any Cafreso surface',
      'Cache hits are instant; misses are answered by community workers',
      'Workers contribute a Brave key + a local LLM and earn ICP micro-payouts',
      'Every answer carries provenance — model, engine, worker, date',
      'The library densifies into a shared, explorable knowledge graph'
    ],
    roadmap: [
      { when: 'Shipped', title: 'On-chain library + worker protocol (HMAC-signed)', done: true },
      { when: 'Shipped', title: 'Anonymous search modal + flagship Library page', done: true },
      { when: 'Now', title: 'Bring the first GPU workers online', done: false },
      { when: 'Next', title: 'Seed the library so day-one visitors see a full web', done: false },
      { when: 'Later', title: 'Multi-worker cross-check + worker reputation', done: false }
    ]
  },
  {
    slug: 'banking-brave',
    name: 'Banking.Brave',
    tagline: 'Self-custody banking on the Internet Computer',
    status: 'live',
    accent: 220,
    icon: 'bank',
    url: 'https://banking.cafreso.com',
    repo: null,
    devlogCat: 'banking-brave',
    summary:
      'The protocol layer behind Cafreso — mine, exchange, and bridge assets from one Internet Identity, with no custodian in the middle.',
    what: [
      'Mine sGLDT and climb the leaderboard',
      'Exchange between ecosystem tokens',
      'Bridge ckUNI and other chain-key assets',
      'One Internet Identity across every Cafreso surface'
    ],
    roadmap: [
      { when: 'Live', title: 'Mine · Exchange · Bridge · Transactions', done: true },
      { when: 'Next', title: 'banking.cafreso.com custom domain', done: false },
      { when: 'Later', title: 'ckUSDT ledger integration', done: false }
    ]
  },
  {
    slug: 'minegold',
    name: 'MineGold.Brave',
    tagline: 'Proof-of-work gold, on-chain',
    status: 'live',
    accent: 45,
    icon: 'coin',
    url: 'https://banking.cafreso.com/mine',
    repo: null,
    devlogCat: 'banking-brave',
    summary:
      'The mining game at the heart of Banking.Brave — earn sGLDT, back a real farm in El Salvador, and turn burns into perks at the café.',
    what: [
      'Mine sGLDT from your browser',
      'Tip gold (sGLDT) to climb the contest leaderboard',
      'On-chain rewards tied to real-world café perks'
    ],
    roadmap: [
      { when: 'Live', title: 'Mining + leaderboard', done: true },
      { when: 'Later', title: 'Seasonal contests with café rewards', done: false }
    ]
  },
  {
    slug: 'cafreso-pages',
    name: 'Cafreso Pages',
    tagline: 'The DAO storefront, dev log, and forums',
    status: 'live',
    accent: 24,
    icon: 'storefront',
    url: '/',
    repo: null,
    devlogCat: 'product',
    summary:
      'This site. A shop, a dev log, forums, and governance — all on-chain, all owned by the community, all reachable from one identity.',
    what: [
      'Buy coffee and merch with gold (sGLDT) or card',
      'Read and tip signed dev-log posts',
      'Post in on-chain forums',
      'Weigh in on DAO governance'
    ],
    roadmap: [
      { when: 'Live', title: 'Shop · Dev Log · Forums', done: true },
      { when: 'Now', title: 'Google-simple homepage + Projects hub', done: false },
      { when: 'Next', title: 'On-chain governance canister (currently seed-backed)', done: false }
    ]
  }
];

// ── The ecosystem arc — where all of this is going ───────────────────────────
// Per-project roadmaps live on each PROJECTS entry above; this is the
// cross-project story the /projects page tells at the bottom: from today's
// cafreso.com surfaces to the .brave-domain future where minegold.brave lets
// Brave's ~100M monthly users convert their BAT ad earnings into on-chain gold.
export const ECOSYSTEM_ROADMAP = [
  {
    era: 'Now',
    title: 'A real economy on cafreso.com',
    tone: 152,
    items: [
      { text: 'Tips, shop, and contest run on gold — sGLDT, 1:1 gold-backed, on the ledger', done: true },
      { text: 'Deep Research: multi-angle, cited answers written forever to the public Library', done: true },
      { text: 'CafresoHQ agents with private containers and a managed default brain', done: true }
    ]
  },
  {
    era: 'Next',
    title: 'Traction you can verify on-chain',
    tone: 45,
    items: [
      { text: 'Public growth metrics — library entries, searches, tips, orders', done: false },
      { text: 'Design the BAT → gold conversion flow with the community', done: false },
      { text: 'SNS decentralization — the capstone, once usage and unit economics prove out', done: false }
    ]
  },
  {
    era: 'Horizon',
    title: 'The .brave era',
    tone: 262,
    items: [
      { text: '.brave resolves in browsers — minegold.brave and banking.brave go live on our own domains', done: false },
      { text: 'minegold.brave: convert monthly BAT ad earnings into gold — mining gold through Brave', done: false },
      { text: 'banking.brave: the self-custody DeFi surface for the whole ecosystem', done: false }
    ]
  }
];

export function getProject(slug) {
  return PROJECTS.find((p) => p.slug === slug) || null;
}

// Featured order for the homepage product row — the two flagships first.
export const HOME_ORDER = ['cafresohq', 'search-network', 'banking-brave', 'cafreso-pages'];
