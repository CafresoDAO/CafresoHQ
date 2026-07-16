export const CATEGORIES = {
  'build-log':     { label: 'Build Log',     icon: 'wrench',      hue: 24  },
  'cafresohq':     { label: 'CafresoHQ',     icon: 'brain',       hue: 262 },
  'search-net':    { label: 'Search Network', icon: 'magnifying-glass', hue: 200 },
  'dao':           { label: 'DAO',           icon: 'infinity',    hue: 262 },
  'farm':          { label: 'Farm',          icon: 'plant',       hue: 130 },
  'product':       { label: 'Product',       icon: 'storefront',  hue: 200 },
  'community':     { label: 'Community',     icon: 'users-three', hue: 320 },
  'tokenomics':    { label: 'Tokenomics',    icon: 'coins',       hue: 45  },
  'banking-brave': { label: 'Banking.Brave', icon: 'bank',        hue: 220 }
};

// Seed posts ship with the frontend bundle so the Dev Log is never blank.
// The canister (`bek5d-2qaaa-aaaab-agqrq-cai`) is authoritative: a canister
// post with the same slug wins on merge. Seeds without a canister copy can
// be adopted on-chain by an admin via /blog/new?edit=<slug> → publish.
export const POSTS = [
  {
    slug: 'redesigning-cafreso-com',
    title: 'Redesigning cafreso.com — one search box, every project',
    cat: 'build-log',
    layout: 'standard',
    theme: 'build-log',
    author: { name: 'Cafreso DAO', hue: 24, role: 'Core team' },
    date: '2026-07-14',
    readMin: 2,
    burned: 0,
    tips: 0,
    comments: 0,
    canister: 'bek5d-2qaaa-aaaab-agqrq-cai',
    block: 0,
    hero: 'roaster',
    pinned: true,
    excerpt:
      'We tore down the old wall-of-cards homepage and rebuilt cafreso.com around one search box, a /projects hub with live roadmaps, and — at last — icons that actually render.',
    body: [
      { kind: 'p', text: "cafreso.com used to open on a wall of cards — hero, banners, stats, three calls-to-action before you scrolled once. This week we tore it down and rebuilt the whole front door around a single idea: one wordmark, one search box, and a quiet row of doors into everything we build. If you've used a certain famous homepage, you already know how to use ours." },
      { kind: 'h2', text: 'What changed' },
      { kind: 'ul', items: [
        'The homepage is now a search box: ask anything and the AI search modal answers from the on-chain library, or jump straight to the shop, Dev Log, and governance from the quick links.',
        'A new /projects hub ties all our open software together — CafresoHQ, the Search Network, Banking.Brave, and the site itself — each with a status pill, a roadmap, and its own live dev-log feed.',
        'Site-wide icons finally render. A font that was never loaded (plus a one-character class bug) meant every icon on the site had been invisible. Both fixed — self-hosted, offline-safe.',
        'Every project page links back here: filter the Dev Log by project with one tap.'
      ]},
      { kind: 'h2', text: 'Why simplicity won' },
      { kind: 'p', text: 'The old page tried to explain the DAO, the token, the café, and the software all at once. But the people who land here mostly want one of two things: find something, or check what we\'re building. The redesign serves exactly those two moves and gets out of the way. Everything else — tokenomics, governance, the leaderboard — is one level down, where it belongs.' },
      { kind: 'roadmap', phases: [
        { num: '00', status: 'done', date: 'Q2 2026', title: 'Blog, shop + forums launch' },
        { num: '01', status: 'done', date: 'Jul 14', title: 'Google-simple redesign + projects hub' },
        { num: '02', status: 'now', date: 'Now', title: 'Dev Log publishing opened up' },
        { num: '03', status: 'next', date: 'Q3 2026', title: 'Search-first navigation everywhere' }
      ]},
      { kind: 'callout', icon: 'compass', title: 'Take the tour', text: 'Start at the homepage, type a question, then wander into /projects — every roadmap ties back to the posts that shipped it.' }
    ]
  },
  {
    slug: 'cafresohq-local-brains',
    title: 'Pick a brain: CafresoHQ agents on your own GPU',
    cat: 'cafresohq',
    layout: 'standard',
    theme: 'dao',
    author: { name: 'Cafreso DAO', hue: 24, role: 'Core team' },
    date: '2026-07-12',
    readMin: 2,
    burned: 0,
    tips: 0,
    comments: 0,
    canister: 'bek5d-2qaaa-aaaab-agqrq-cai',
    block: 0,
    hero: 'roaster',
    pinned: false,
    excerpt:
      'LM Studio and Ollama are now first-class Hermes backends: point CafresoHQ at your own GPU and every agent, search worker, and chat runs local — plus origin-pinned bridges and idle-container reaping.',
    body: [
      { kind: 'p', text: "CafresoHQ's agents have always talked to their models through the Hermes gateway — one OpenAI-compatible endpoint inside your container, no keys in the browser, no model calls from the page. Until now, though, the picker behind it only knew cloud providers. If your tokens came off your own GPU, the brain picker shrugged." },
      { kind: 'h2', text: 'Local backends are now first-class' },
      { kind: 'ul', items: [
        'LM Studio and Ollama join OpenRouter, Gemini, and Groq in the provider registry — same dropdown, same status chips, no separate mode.',
        'Local providers take a base URL instead of an API key: point HQ at http://localhost:1234/v1 (LM Studio) or :11434 (Ollama) and every agent in the office runs on your silicon.',
        'The gateway does the adapting — your local GPT-OSS-20b looks exactly like a cloud model to the agents, the search worker, and the CLI.'
      ]},
      { kind: 'h2', text: 'Also in this drop' },
      { kind: 'p', text: 'The same release hardens the shell-to-app bridge: every postMessage between the sandboxed pixel office and the Internet-Identity-holding shell is now pinned to a validated origin, failing closed instead of broadcasting. And the fleet finally reaps idle containers on a timer, so a forgotten session stops billing minutes after you walk away.' },
      { kind: 'stats', items: [
        { label: 'Brains', value: '5 providers' },
        { label: 'Cloud keys needed', value: '0' },
        { label: 'Gateway', value: '127.0.0.1:8642' },
        { label: 'Idle reap', value: '5-min ticks' }
      ]},
      { kind: 'callout', icon: 'cpu', title: 'Your GPU, your tokens', text: 'This lands with the next HQ deploy. Bring a local model and the whole office — agents, search, chat — runs without a single external API call.' }
    ]
  },
  {
    slug: 'cafreso-search-network-live',
    title: 'The Cafreso Search Network is live',
    cat: 'search-net',
    layout: 'standard',
    theme: 'standard',
    author: { name: 'Cafreso DAO', hue: 24, role: 'Core team' },
    date: '2026-07-06',
    readMin: 2,
    burned: 0,
    tips: 0,
    comments: 0,
    canister: 'bek5d-2qaaa-aaaab-agqrq-cai',
    block: 0,
    hero: 'roaster',
    pinned: false,
    excerpt:
      'Every answer on cafreso.com is now served by the network — HQ containers that opted in as search workers, reading the on-chain library and signing their answers back to the canister.',
    body: [
      { kind: 'p', text: "Ask a question anywhere on cafreso.com — the homepage box, the library, the search modal — and the answer doesn't come from a data center we rent. It comes from the network: CafresoHQ containers that opted in as search workers, each one running the same Hermes gateway that powers its owner's agents." },
      { kind: 'h2', text: 'How an answer happens' },
      { kind: 'ul', items: [
        'Your query lands on the state canister and is picked up by an available worker.',
        "The worker's model reads, reasons, and writes an answer with citations from the on-chain library.",
        'The result is signed back on-chain — workers earn credit for every answer they serve.'
      ]},
      { kind: 'h2', text: 'Why on-chain search' },
      { kind: 'p', text: "Search is the front door of the internet, and today a handful of companies own the key. A network where anyone can contribute compute, every answer is attributable, and the index lives on canisters is our bet on a different kind of door. It's early — the library is small and the worker fleet is smaller — but it works end to end, today." },
      { kind: 'progress', value: 1, max: 100, label: 'Search workers online', sub: 'Join from HQ Settings' },
      { kind: 'callout', icon: 'magnifying-glass', title: 'Run a worker', text: 'Any CafresoHQ container can serve the network — flip on Search Network in Settings and your idle GPU starts answering (and earning).' }
    ]
  },
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

// timeZone UTC: bare YYYY-MM-DD strings parse as UTC midnight, so local-time
// formatting shifted every date a day early west of Greenwich.
export const fmtDate = (iso) =>
  new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });

export function postHeroImg(hero) {
  if (hero === 'farm') return '/assets/cafreso.webp';
  if (hero === 'banking-brave') return '/assets/banking-brave-logo.png';
  return '/assets/cafreso-roaster.webp';
}
