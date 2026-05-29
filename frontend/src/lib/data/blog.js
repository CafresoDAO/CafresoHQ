export const CATEGORIES = {
  'build-log':     { label: 'Build Log',     icon: 'wrench',      hue: 24  },
  'dao':           { label: 'DAO',           icon: 'infinity',    hue: 262 },
  'farm':          { label: 'Farm',          icon: 'plant',       hue: 130 },
  'product':       { label: 'Product',       icon: 'storefront',  hue: 200 },
  'community':     { label: 'Community',     icon: 'users-three', hue: 320 },
  'tokenomics':    { label: 'Tokenomics',    icon: 'coins',       hue: 45  },
  'banking-brave': { label: 'Banking.Brave', icon: 'bank',        hue: 220 }
};

// Exactly two seed posts — these are used as a fallback only when the
// devlog canister has no posts yet (brand-new deploys, local replica). In
// production the canister at `dff5y-yyaaa-aaaab-agpzq-cai` is authoritative.
export const POSTS = [
  {
    slug: 'introducing-cafreso',
    title: 'Introducing Cafreso — a DAO-powered café on the Internet Computer',
    cat: 'product',
    layout: 'standard',
    author: { name: 'Cafreso DAO', hue: 24, role: 'Core team' },
    date: '2026-04-18',
    readMin: 4,
    burned: 0,
    tips: 0,
    comments: 0,
    canister: 'dqcmv-z...cai',
    block: 0,
    hero: 'roaster',
    pinned: true,
    excerpt:
      "Cafreso is a coffee shop that runs as a decentralized autonomous organization on the Internet Computer. Every bag you buy, every post you tip, every proposal you vote on — it's all on-chain, auditable, and owned by the community.",
    body: [
      { kind: 'p', text: "Cafreso is a coffee shop that happens to be a decentralized autonomous organization. That framing matters — we didn't start with a token and look for a product. We started with great single-origin coffee, a farm in San Miguel, El Salvador, and a question: what would it look like if the people drinking the coffee also owned the supply chain?" },
      { kind: 'h2', text: 'What you can do today' },
      { kind: 'ul', items: [
        'Shop coffee, merch, and limited SNS-gated drops with $nanas or $CF',
        'Read (and tip) dev-log posts signed on the devlog canister',
        'Burn $nanas to climb the leaderboard — tied to real perks at the café',
        'Connect Internet Identity to carry your principal across every Cafreso surface'
      ]},
      { kind: 'h2', text: 'What comes next' },
      { kind: 'p', text: "We're rolling out Banking.Brave — a sister protocol for on-chain gold-backed yield — on a separate canister so each product can evolve on its own cadence. A single Internet Identity sign-in will unify your principal across both, and leaderboard scoring will weight mining activity alongside $nanas burns." },
      { kind: 'p', text: "Everything you see here is open: the code, the treasury, the proposals. If you want to build with us, the dev log is where we think out loud." },
      { kind: 'callout', tone: 'banana', icon: 'coffee-bean', title: "You're early", text: "This is the public launch post. The SNS decentralization swap is queued for Q2 — hold your $CF, review the proposals, and we'll see you at the café." }
    ]
  },
  {
    slug: 'introducing-banking-brave',
    title: 'Introducing Banking.Brave — DAO-native yield, custody, and governance',
    cat: 'banking-brave',
    layout: 'banking-brave',
    author: { name: 'Cafreso DAO', hue: 24, role: 'Core team' },
    date: '2026-04-18',
    readMin: 9,
    burned: 0,
    tips: 0,
    comments: 0,
    canister: 'cqyto-t...cai',
    block: 0,
    hero: 'banking-brave',
    pinned: false,
    excerpt:
      "Today we're debuting Banking.Brave — a sovereign, non-custodial banking protocol built on the Internet Computer, powered by the Cafreso DAO treasury. Every deposit earns governance-set yield; every withdrawal is atomic; every vote is on-chain."
  }
];

export const COMMENTS = [];

export const fmtDate = (iso) =>
  new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

export function postHeroImg(hero) {
  if (hero === 'farm') return '/assets/cafreso.png';
  if (hero === 'banking-brave') return '/assets/banking-brave-logo.png';
  return '/assets/cafreso-roaster.png';
}
