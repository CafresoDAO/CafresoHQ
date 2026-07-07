<script>
  import { aiCafresoOrigin } from '$lib/links.js';

  // Shared tier palette — the SAME four hues carry through the step icons,
  // the pillar icons, AND the architecture diagram below, so the overview
  // and the engineer diagram visibly tell one continuous story. Defined as
  // page-scoped CSS vars in the stylesheet below, rather than the shared
  // --eco-* tokens: --eco-pages is too pale (86% lightness) to hold up as
  // an icon/border accent on a dark card, and none of the --eco-* tokens
  // vary by theme.
  const TIER = { identity: 'var(--tier-1)', compute: 'var(--tier-2)', chain: 'var(--tier-3)', money: 'var(--tier-4)' };

  // The three-tier flow, told as a story a newcomer can follow in a minute.
  const steps = [
    {
      n: '01', emoji: '🔑', color: TIER.identity,
      title: 'You sign in once, with your keys',
      body: 'One Internet Identity signs you into every Cafreso app. No password, no account — a passkey on your device. The same identity owns your library, your agents, and your wallet across the whole ecosystem.'
    },
    {
      n: '02', emoji: '🏢', color: TIER.compute,
      title: 'You get a pixel office of AI agents',
      body: 'CafresoHQ is a little on-chain office. You meet the CEO agent, hire specialists to empty desks, and delegate real work — research, writing, code, whole websites. Agents run on your own container and model.'
    },
    {
      n: '03', emoji: '🧠', color: TIER.chain,
      title: 'They do real work — and it lives on-chain',
      body: 'Ask a question and the answer is researched, cited, and saved forever to a public library anyone can explore. Build a site and it publishes to a canister URL. Nothing is faked; every artifact is real and permanent.'
    },
    {
      n: '04', emoji: '🪙', color: TIER.money,
      title: 'Money is optional, and you always sign',
      body: 'Turn on the money module and agents can hold tokens under spending caps you set — but every transfer is signed by you, in the app that holds your identity. Agents can request; they can never move funds on their own.'
    }
  ];

  const pillars = [
    { emoji: '🪪', title: 'Your identity', tag: 'client', color: TIER.identity,
      body: 'The SvelteKit shell holds your Internet Identity delegation and the @dfinity actors. It is the only thing that ever signs a transaction.' },
    { emoji: '🧠', title: 'Inference', tag: 'your container', color: TIER.compute,
      body: 'A private container runs the agent runtime, your local LLM (Gemma, hermes, or a hosted model), and web search. This is where thinking happens — off-chain, fast, yours.' },
    { emoji: '⛓️', title: 'The chain', tag: 'internet computer', color: TIER.chain,
      body: 'One canister is the durable source of truth: encrypted vault, agent wallets, payroll, the public research library, and published sites — keyed to your principal.' },
    { emoji: '🕸️', title: 'The network', tag: 'community', color: TIER.money,
      body: 'Anyone can run a worker that answers public search queries with its own model and earns ICP. The library grows into a shared, on-chain web of knowledge.' }
  ];
</script>

<svelte:head>
  <title>How it works · Cafreso</title>
  <meta name="description"
    content="How the Cafreso ecosystem fits together — one Internet Identity, a pixel office of AI agents, private inference, and an on-chain research library on the Internet Computer." />
</svelte:head>

<div class="hiw">
  <!-- ── Hero / TLDR ─────────────────────────────────────────────────────── -->
  <section class="hiw-hero">
    <div class="hiw-badge">🌐 Internet Computer · fully on-chain</div>
    <h1 class="hiw-title">An office of AI agents<br />you actually own.</h1>
    <p class="hiw-lede">
      Cafreso is an agentic workflow OS on the blockchain. You sign in with one identity, hire
      AI agents into a pixel-art office, and put them to work — and everything they produce
      (answers, files, sites, even money) is real, permanent, and yours. No accounts, no lock-in,
      no company holding your keys.
    </p>
    <div class="hiw-hero-cta">
      <a href={aiCafresoOrigin} data-sveltekit-reload="on" rel="noopener" class="hiw-btn hiw-btn--primary">
        Open your HQ <span class="hiw-arw">→</span>
      </a>
      <a href="/library" class="hiw-btn hiw-btn--ghost">
        Explore the library <span class="hiw-arw">↗</span>
      </a>
    </div>
  </section>

  <!-- ── The 60-second version ───────────────────────────────────────────── -->
  <section class="hiw-section">
    <div class="hiw-kicker">The 60-second version</div>
    <h2 class="hiw-h2">How it works, start to finish</h2>
    <div class="hiw-steps">
      {#each steps as s}
        <div class="hiw-step">
          <div class="hiw-step-rail" style="--c: {s.color}">
            <span class="hiw-step-n">{s.n}</span>
            <span class="hiw-step-icon" style="--c: {s.color}">{s.emoji}</span>
          </div>
          <div class="hiw-step-body">
            <h3>{s.title}</h3>
            <p>{s.body}</p>
          </div>
        </div>
      {/each}
    </div>
  </section>

  <!-- ── The four pillars ────────────────────────────────────────────────── -->
  <section class="hiw-section">
    <div class="hiw-kicker">The building blocks</div>
    <h2 class="hiw-h2">Four layers, one system</h2>
    <p class="hiw-sub">
      The trick that makes this both fast and trustless: thinking happens off-chain on hardware
      you control, while identity and truth live on-chain. They meet at a signing boundary only
      you can cross.
    </p>
    <div class="hiw-pillars">
      {#each pillars as p}
        <div class="hiw-pillar">
          <span class="hiw-pillar-icon" style="--c: {p.color}">{p.emoji}</span>
          <div class="hiw-pillar-tag">{p.tag}</div>
          <h3>{p.title}</h3>
          <p>{p.body}</p>
        </div>
      {/each}
    </div>
  </section>

  <!-- ── The search flywheel ─────────────────────────────────────────────── -->
  <section class="hiw-section">
    <div class="hiw-kicker">The flywheel</div>
    <h2 class="hiw-h2">Every question makes the library smarter</h2>
    <div class="hiw-flywheel">
      <div class="hiw-fw-step"><span>1</span><p>Someone asks a question — even signed out.</p></div>
      <span class="hiw-fw-arw">→</span>
      <div class="hiw-fw-step"><span>2</span><p>A community worker answers it with its own model + web search.</p></div>
      <span class="hiw-fw-arw">→</span>
      <div class="hiw-fw-step"><span>3</span><p>The cited answer is written on-chain and pays the worker in ICP.</p></div>
      <span class="hiw-fw-arw">→</span>
      <div class="hiw-fw-step hiw-fw-step--gold"><span>∞</span><p>Everyone who asks it next gets it instantly, free, forever.</p></div>
    </div>
  </section>

  <!-- ── Architecture diagram (for engineers) ────────────────────────────── -->
  <section class="hiw-section hiw-arch">
    <div class="hiw-kicker">For engineers</div>
    <h2 class="hiw-h2">How inference, front-end &amp; blockchain fit together</h2>
    <p class="hiw-sub">
      Three tiers, one trust boundary. The sandboxed app can only <em>request</em>; the shell that
      holds your Internet Identity is the only place a signature happens; the container does the
      compute; the canister is the durable truth.
    </p>

    <div class="hiw-arch-scroll">
      <svg class="hiw-arch-svg" viewBox="0 0 1000 812" role="img"
        aria-label="Architecture diagram: browser tier holding Internet Identity, container tier for inference, and the Internet Computer tier for on-chain state.">
        <defs>
          <marker id="hiw-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--arw)"/>
          </marker>
          <marker id="hiw-arrow-gold" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--c-money)"/>
          </marker>
        </defs>

        <!-- Tier bands -->
        <g class="tier-band">
          <rect x="20" y="40" width="960" height="196" rx="18" class="band band--client"/>
          <rect x="20" y="300" width="960" height="150" rx="18" class="band band--compute"/>
          <rect x="20" y="512" width="960" height="272" rx="18" class="band band--chain"/>
        </g>

        <!-- Tier labels -->
        <text x="40" y="30" class="tier-label" style="fill: var(--c-client)">1 · THE BROWSER — your device, holds your Internet Identity</text>
        <text x="40" y="290" class="tier-label" style="fill: var(--c-compute)">2 · YOUR CONTAINER — inference &amp; agent runtime · off-chain</text>
        <text x="40" y="502" class="tier-label" style="fill: var(--c-chain)">3 · THE INTERNET COMPUTER — durable on-chain truth</text>

        <!-- ── Tier 1: browser ── -->
        <!-- Shell -->
        <g class="node">
          <rect x="52" y="72" width="405" height="140" rx="14" class="box box--client"/>
          <text x="72" y="102" class="node-t">SvelteKit Shell</text>
          <text x="72" y="122" class="node-d">ai.cafreso.com · @dfinity actors</text>
          <g class="chip chip--sign">
            <rect x="72" y="138" width="150" height="26" rx="13"/>
            <text x="147" y="155" class="chip-t">🔑 holds II · SIGNS</text>
          </g>
          <text x="72" y="186" class="node-n">The one place a transaction is ever signed.</text>
          <text x="72" y="202" class="node-n">No key ever leaves here.</text>
        </g>
        <!-- Pixel HQ app -->
        <g class="node">
          <rect x="543" y="72" width="405" height="140" rx="14" class="box box--client-alt"/>
          <text x="563" y="102" class="node-t">Pixel HQ App</text>
          <text x="563" y="122" class="node-d">sandboxed &lt;iframe&gt; · JSX · no keys, no II</text>
          <g class="chip chip--req">
            <rect x="563" y="138" width="168" height="26" rx="13"/>
            <text x="647" y="155" class="chip-t">only REQUESTS</text>
          </g>
          <text x="563" y="186" class="node-n">The office, agents, editor, terminal.</text>
          <text x="563" y="202" class="node-n">Runs untrusted; can never sign.</text>
        </g>
        <!-- postMessage bridge -->
        <line x1="457" y1="142" x2="543" y2="142" class="wire" marker-start="url(#hiw-arrow)" marker-end="url(#hiw-arrow)"/>
        <text x="500" y="132" class="wire-t" text-anchor="middle">postMessage</text>
        <text x="500" y="162" class="wire-t wire-t--dim" text-anchor="middle">request→ ←signed result</text>

        <!-- ── Tier 2: container ── -->
        <g class="node">
          <rect x="52" y="326" width="260" height="98" rx="14" class="box box--compute"/>
          <text x="72" y="356" class="node-t">serve.py runtime</text>
          <text x="72" y="376" class="node-d">agent loop · vault I/O</text>
          <text x="72" y="396" class="node-d">terminal · publish · search worker</text>
        </g>
        <g class="node">
          <rect x="372" y="326" width="270" height="98" rx="14" class="box box--compute"/>
          <text x="392" y="356" class="node-t">Local / hosted LLM</text>
          <text x="392" y="376" class="node-d">Gemma · hermes gateway</text>
          <text x="392" y="396" class="node-d">the model that thinks</text>
        </g>
        <g class="node">
          <rect x="702" y="326" width="246" height="98" rx="14" class="box box--compute"/>
          <text x="722" y="356" class="node-t">Web search</text>
          <text x="722" y="376" class="node-d">Brave Search API</text>
          <text x="722" y="396" class="node-d">sources for answers</text>
        </g>
        <!-- container internal wires -->
        <line x1="312" y1="375" x2="372" y2="375" class="wire" marker-end="url(#hiw-arrow)"/>
        <line x1="642" y1="375" x2="702" y2="375" class="wire" marker-end="url(#hiw-arrow)"/>
        <text x="672" y="365" class="wire-t" text-anchor="middle">inference</text>

        <!-- ── Tier 3: chain ── -->
        <g class="node">
          <rect x="52" y="544" width="560" height="216" rx="14" class="box box--chain"/>
          <text x="72" y="574" class="node-t">cafresohq_state <tspan class="node-mono">· canister</tspan></text>
          <text x="72" y="594" class="node-d">one per-user source of truth, keyed to your principal</text>
          <g class="subgrid">
            <g><rect x="72" y="610" width="250" height="40" rx="9" class="sub"/><text x="86" y="628" class="sub-t">🔒 vetKeys vault</text><text x="86" y="643" class="sub-d">encrypted ciphertext</text></g>
            <g><rect x="342" y="610" width="250" height="40" rx="9" class="sub"/><text x="356" y="628" class="sub-t">👛 agent wallets · payroll</text><text x="356" y="643" class="sub-d">ICRC subaccounts · caps</text></g>
            <g><rect x="72" y="660" width="250" height="40" rx="9" class="sub sub--lib"/><text x="86" y="678" class="sub-t">📚 public library</text><text x="86" y="693" class="sub-d">answers + search queue</text></g>
            <g><rect x="342" y="660" width="250" height="40" rx="9" class="sub"/><text x="356" y="678" class="sub-t">🌐 published sites</text><text x="356" y="693" class="sub-d">served at canister URLs</text></g>
          </g>
          <text x="72" y="732" class="node-n">http_request serves /library to the entire public web — no gateway, no server.</text>
        </g>
        <g class="node">
          <rect x="642" y="544" width="306" height="98" rx="14" class="box box--chain-alt"/>
          <text x="662" y="574" class="node-t">Asset canisters</text>
          <text x="662" y="594" class="node-d">cafresohq_ui · _frontend</text>
          <text x="662" y="614" class="node-d">serve the apps themselves</text>
        </g>
        <g class="node">
          <rect x="642" y="662" width="306" height="98" rx="14" class="box box--money"/>
          <text x="662" y="692" class="node-t">ICRC ledgers</text>
          <text x="662" y="712" class="node-d">ICP · ckUSDT</text>
          <text x="662" y="732" class="node-d">real value, real transfers</text>
        </g>

        <!-- ── Cross-tier wires ── -->
        <!-- shell → canister (signed candid): routed down the clear left margin so
             it never crosses the container tier; label runs vertically beside it. -->
        <path d="M90,212 L34,244 L34,530 L66,544" class="wire wire--strong" marker-end="url(#hiw-arrow)"/>
        <text x="26" y="388" class="wire-t" transform="rotate(-90 26 388)" text-anchor="middle">candid · II-signed · vault / wallets / publish</text>
        <!-- iframe → container (agent XHR) -->
        <path d="M745,212 L745,258 L200,258 L200,326" class="wire" marker-end="url(#hiw-arrow)"/>
        <text x="380" y="250" class="wire-t" text-anchor="middle">agent work · files · terminal (XHR)</text>
        <!-- container → canister (HMAC worker fulfill) — alone in the gap now -->
        <path d="M150,424 L150,544" class="wire wire--dash" marker-end="url(#hiw-arrow)"/>
        <text x="160" y="474" class="wire-t">HMAC POST</text>
        <text x="160" y="490" class="wire-t wire-t--dim">worker fulfill</text>
        <!-- canister → ledger (transfer_from) -->
        <path d="M612,700 L642,700" class="wire wire--gold" marker-end="url(#hiw-arrow-gold)"/>
        <text x="722" y="654" class="wire-t wire-t--gold">← icrc2_transfer_from · payroll / payouts</text>

        <!-- Trust boundary annotation -->
        <line x1="20" y1="272" x2="980" y2="272" class="boundary"/>
        <text x="960" y="266" class="boundary-t" text-anchor="end">⟂ trust boundary — nothing below ever holds your keys</text>
      </svg>
    </div>

    <div class="hiw-arch-legend">
      <span><i class="lg lg--client"></i> Browser · signs</span>
      <span><i class="lg lg--compute"></i> Container · computes</span>
      <span><i class="lg lg--chain"></i> Canister · stores</span>
      <span><i class="lg lg--money"></i> Ledgers · value</span>
      <span class="hiw-legend-note">Solid = signed / trusted · dashed = HMAC-authenticated · gold = value transfer</span>
    </div>
  </section>

  <!-- ── Closing CTA ─────────────────────────────────────────────────────── -->
  <section class="hiw-close">
    <h2>Ready to put a team to work?</h2>
    <p>Sign in with Internet Identity — it takes about thirty seconds, and there's nothing to install.</p>
    <a href={aiCafresoOrigin} data-sveltekit-reload="on" rel="noopener" class="hiw-btn hiw-btn--primary">
      Open your HQ <span class="hiw-arw">→</span>
    </a>
  </section>
</div>

<style>
  .hiw {
    max-width: 1080px; margin: 0 auto; padding: 0 4px 40px;
    --tier-1: hsl(32 72% 50%);
    --tier-2: hsl(280 42% 58%);
    --tier-3: hsl(155 45% 42%);
    --tier-4: hsl(43 74% 48%);
  }
  :global(.dark) .hiw {
    --tier-1: hsl(45 90% 62%);
    --tier-2: hsl(280 50% 70%);
    --tier-3: hsl(155 55% 58%);
    --tier-4: hsl(43 85% 62%);
  }

  /* ── Hero ── */
  .hiw-hero {
    text-align: center;
    padding: 48px 20px 40px;
  }
  .hiw-badge {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 12px; font-weight: 700; letter-spacing: 0.04em;
    /* brand-800 stays a dark, warm tone in both themes (36% / 32% lightness) —
       unlike ink-200, which flips to a light tone in dark mode and would sit
       as pale text on this same pale-gold chip, wrecking contrast. */
    color: hsl(var(--brand-800));
    background: color-mix(in srgb, hsl(var(--brand-500)) 16%, var(--surface-card));
    border: 1px solid hsl(var(--brand-300) / 0.7); border-radius: 999px;
    padding: 6px 13px; margin-bottom: 20px;
  }
  .hiw-title {
    font-family: 'Playfair Display', serif;
    font-size: clamp(2.1rem, 5.5vw, 3.6rem);
    font-weight: 800; line-height: 1.06;
    color: hsl(var(--ink-50)); margin: 0 0 18px;
  }
  .hiw-lede {
    font-size: clamp(1rem, 2.2vw, 1.18rem); line-height: 1.65;
    color: hsl(var(--ink-200)); max-width: 62ch; margin: 0 auto 26px;
  }
  .hiw-hero-cta { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }

  .hiw-btn {
    display: inline-flex; align-items: center; gap: 7px;
    font-size: 14px; font-weight: 700; text-decoration: none;
    padding: 12px 22px; border-radius: 12px; transition: transform .12s, filter .12s;
  }
  .hiw-btn:hover { transform: translateY(-1px); }
  .hiw-btn--primary { background: hsl(var(--brand-500)); color: hsl(var(--ink-50)); box-shadow: 0 8px 20px -8px hsl(var(--brand-700) / .6); }
  .hiw-btn--primary:hover { filter: brightness(1.05); }
  .hiw-btn--ghost { background: var(--surface-card); color: hsl(var(--ink-100)); border: 1px solid hsl(var(--surface-border)); }
  .hiw-arw { font-size: 1.05em; line-height: 1; }

  /* ── Sections ── */
  .hiw-section { padding: 40px 20px; border-top: 1px solid hsl(var(--ink-700)); }
  .hiw-kicker {
    font-size: 11px; font-weight: 800; letter-spacing: 0.14em; text-transform: uppercase;
    color: hsl(var(--brand-700));
  }
  .hiw-h2 {
    font-family: 'Playfair Display', serif;
    font-size: clamp(1.5rem, 3.5vw, 2.2rem); font-weight: 700;
    color: hsl(var(--ink-50)); margin: 8px 0 14px; line-height: 1.15;
  }
  .hiw-sub { font-size: 15px; line-height: 1.7; color: hsl(var(--ink-300)); max-width: 64ch; margin: 0 0 26px; }
  .hiw-sub em { font-style: italic; color: hsl(var(--ink-100)); }

  /* ── Steps ── */
  .hiw-steps { display: grid; gap: 14px; }
  .hiw-step {
    display: flex; gap: 18px; align-items: stretch;
    /* Reuses the site's real card treatment (see .card in app.css) instead of
       a flat ink-900 fill — in dark mode ink-900 IS the page background, so
       a flat fill made every card disappear into the page behind it. */
    background: linear-gradient(180deg, var(--surface-card), var(--surface-card-strong));
    border: 1px solid hsl(var(--surface-border)); box-shadow: var(--card-shadow);
    border-radius: 16px; padding: 20px 22px;
  }
  .hiw-step-rail { display: flex; flex-direction: column; align-items: center; gap: 10px; flex-shrink: 0; width: 46px; }
  .hiw-step-n { font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 700; color: hsl(var(--ink-400)); }
  .hiw-step-icon {
    width: 44px; height: 44px; border-radius: 12px;
    display: grid; place-items: center; font-size: 22px; line-height: 1;
    background: color-mix(in srgb, var(--c) 26%, transparent);
    border: 1.5px solid var(--c);
  }
  .hiw-step-body h3 { font-size: 17px; font-weight: 700; color: hsl(var(--ink-50)); margin: 2px 0 6px; }
  .hiw-step-body p { font-size: 14.5px; line-height: 1.62; color: hsl(var(--ink-300)); margin: 0; }

  /* ── Pillars ── */
  .hiw-pillars { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; }
  .hiw-pillar {
    background: linear-gradient(180deg, var(--surface-card), var(--surface-card-strong));
    border: 1px solid hsl(var(--surface-border)); box-shadow: var(--card-shadow);
    border-radius: 16px; padding: 22px;
  }
  .hiw-pillar-icon {
    display: grid; place-items: center; width: 46px; height: 46px; border-radius: 12px;
    font-size: 23px; line-height: 1; margin-bottom: 14px;
    /* Tinted against --c (the tier color) rather than a solid brand-100 fill —
       a solid pale-yellow square turns into a glowing block on a dark card;
       a tint stays proportionate to the card underneath in both themes. */
    background: color-mix(in srgb, var(--c) 22%, transparent);
    border: 1.5px solid var(--c);
  }
  .hiw-pillar-tag {
    font-size: 10px; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase;
    color: hsl(var(--ink-400)); margin-bottom: 4px;
  }
  .hiw-pillar h3 { font-size: 16px; font-weight: 700; color: hsl(var(--ink-50)); margin: 0 0 7px; }
  .hiw-pillar p { font-size: 13.5px; line-height: 1.6; color: hsl(var(--ink-300)); margin: 0; }

  /* ── Flywheel ── */
  .hiw-flywheel {
    display: flex; align-items: stretch; gap: 10px; flex-wrap: wrap;
    color: hsl(var(--ink-400));
  }
  .hiw-fw-arw { align-self: center; font-size: 18px; color: hsl(var(--ink-400)); }
  .hiw-fw-step {
    flex: 1 1 190px;
    background: linear-gradient(180deg, var(--surface-card), var(--surface-card-strong));
    border: 1px solid hsl(var(--surface-border)); box-shadow: var(--card-shadow);
    border-radius: 14px; padding: 16px 16px 18px;
    display: flex; flex-direction: column; gap: 8px;
  }
  .hiw-fw-step span {
    display: grid; place-items: center; width: 28px; height: 28px; border-radius: 8px;
    background: color-mix(in srgb, hsl(var(--brand-500)) 22%, var(--surface-card-strong));
    color: hsl(var(--brand-800));
    font-weight: 800; font-size: 14px;
  }
  .hiw-fw-step p { font-size: 13px; line-height: 1.5; color: hsl(var(--ink-200)); margin: 0; }
  .hiw-fw-step--gold {
    border-color: hsl(var(--brand-400));
    background: color-mix(in srgb, hsl(var(--brand-500)) 16%, var(--surface-card-strong));
  }
  /* brand-900 (not ink-50): a fixed dark tone that keeps the number readable
     on the bright brand-500 badge in both themes. ink-50 flips to near-white
     in dark mode, which is near-invisible on this same bright gold badge. */
  .hiw-fw-step--gold span { background: hsl(var(--brand-500)); color: hsl(var(--brand-900)); }

  /* ── Architecture diagram ──
     Three nested depths (page → band → box/sub) need to visibly separate.
     In light mode ink-800/ink-900 read fine even close together (near-white
     tones separate via shadow alone), but in dark mode ink-800/ink-900 are
     BOTH near-black and ink-900 equals the page body — so band, box, and the
     page itself collapsed into one flat black. Fixed with a dedicated
     dark-only depth ramp (--band-fill/--box-fill/--sub-fill) plus a real
     panel around the whole diagram so it reads as a distinct "console". */
  .hiw-arch-scroll {
    overflow-x: auto; border-radius: 18px; padding: 14px;
    background: var(--surface-muted); border: 1px solid hsl(var(--surface-border));
  }
  .hiw-arch-svg {
    width: 100%; min-width: 720px; height: auto; display: block;
    --c-client: hsl(32 72% 50%);
    --c-compute: hsl(280 42% 58%);
    --c-chain: hsl(155 45% 42%);
    --c-money: hsl(43 74% 48%);
    --arw: hsl(var(--ink-400));
    --band-fill: hsl(var(--ink-800));
    --box-fill: hsl(var(--ink-900));
    --sub-fill: hsl(var(--ink-800));
    --chip-req-fill: hsl(var(--ink-800));
  }
  :global(.dark) .hiw-arch-svg {
    --c-client: hsl(45 90% 62%);
    --c-compute: hsl(280 50% 70%);
    --c-chain: hsl(155 55% 58%);
    --c-money: hsl(43 85% 62%);
    --band-fill: hsl(24 34% 14%);
    --box-fill: hsl(24 30% 18%);
    --sub-fill: hsl(24 27% 22%);
    --chip-req-fill: hsl(24 27% 22%);
  }
  .band { fill: var(--band-fill); stroke: hsl(var(--surface-border)); stroke-width: 1; }
  .tier-label { font: 700 13px 'JetBrains Mono', monospace; letter-spacing: 0.02em; }
  .box { fill: var(--box-fill); stroke-width: 1.6; }
  .box--client, .box--client-alt { stroke: var(--c-client); }
  .box--client-alt { stroke-dasharray: 5 3; }
  .box--compute { stroke: var(--c-compute); }
  .box--chain, .box--chain-alt { stroke: var(--c-chain); }
  .box--money { stroke: var(--c-money); }
  .node-t { font: 700 16px Inter, system-ui, sans-serif; fill: hsl(var(--ink-50)); }
  .node-mono { font: 500 12px 'JetBrains Mono', monospace; fill: hsl(var(--ink-400)); }
  .node-d { font: 400 12.5px Inter, system-ui, sans-serif; fill: hsl(var(--ink-300)); }
  .node-n { font: 400 11.5px Inter, system-ui, sans-serif; fill: hsl(var(--ink-400)); }
  .chip--sign rect { fill: color-mix(in srgb, var(--c-client) 22%, transparent); stroke: var(--c-client); stroke-width: 1; }
  .chip--req rect { fill: var(--chip-req-fill); stroke: hsl(var(--ink-500)); stroke-width: 1; stroke-dasharray: 4 2; }
  .chip-t { font: 700 11px Inter, system-ui, sans-serif; fill: hsl(var(--ink-100)); text-anchor: middle; }
  .sub { fill: var(--sub-fill); stroke: hsl(var(--surface-border)); stroke-width: 1; }
  .sub--lib { stroke: var(--c-chain); }
  .sub-t { font: 700 12px Inter, system-ui, sans-serif; fill: hsl(var(--ink-100)); }
  .sub-d { font: 400 10.5px Inter, system-ui, sans-serif; fill: hsl(var(--ink-400)); }
  .wire { stroke: var(--arw); stroke-width: 1.6; fill: none; }
  .wire--strong { stroke: var(--c-client); stroke-width: 2.2; }
  .wire--dash { stroke: var(--c-compute); stroke-width: 1.8; stroke-dasharray: 6 4; }
  .wire--gold { stroke: var(--c-money); stroke-width: 2.2; }
  .wire-t { font: 600 11px 'JetBrains Mono', monospace; fill: hsl(var(--ink-300)); }
  .wire-t--dim { fill: hsl(var(--ink-400)); font-weight: 400; }
  .wire-t--gold { fill: var(--c-money); }
  .boundary { stroke: hsl(var(--ink-500)); stroke-width: 1; stroke-dasharray: 2 5; }
  .boundary-t { font: 600 11px 'JetBrains Mono', monospace; fill: hsl(var(--ink-400)); }

  .hiw-arch-legend {
    display: flex; flex-wrap: wrap; gap: 8px 18px; align-items: center;
    margin-top: 16px; font-size: 12.5px; color: hsl(var(--ink-300));
  }
  .hiw-arch-legend span { display: inline-flex; align-items: center; gap: 6px; }
  .lg { width: 12px; height: 12px; border-radius: 4px; display: inline-block; }
  .lg--client { background: var(--tier-1); }
  .lg--compute { background: var(--tier-2); }
  .lg--chain { background: var(--tier-3); }
  .lg--money { background: var(--tier-4); }
  .hiw-legend-note { color: hsl(var(--ink-400)); font-size: 11.5px; }

  /* ── Close ── */
  .hiw-close {
    text-align: center; padding: 52px 20px 20px; margin-top: 20px;
    border-top: 1px solid hsl(var(--ink-700));
  }
  .hiw-close h2 { font-family: 'Playfair Display', serif; font-size: clamp(1.5rem, 4vw, 2rem); font-weight: 700; color: hsl(var(--ink-50)); margin: 0 0 10px; }
  .hiw-close p { font-size: 15px; color: hsl(var(--ink-300)); margin: 0 0 22px; }

  @media (max-width: 640px) {
    .hiw-fw-arw { transform: rotate(90deg); }
    .hiw-flywheel { flex-direction: column; }
  }
  @media (prefers-reduced-motion: reduce) {
    .hiw-btn, .hiw-btn:hover { transition: none; transform: none; }
  }
</style>
