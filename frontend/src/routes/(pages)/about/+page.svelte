<script>
  import Icon from '$lib/components/Icon.svelte';
  import { bbLinks, aiCafresoOrigin, bankingBraveOrigin } from '$lib/links.js';
</script>

<svelte:head>
  <title>About · Cafreso</title>
  <meta
    name="description"
    content="Cafreso is a DAO-governed ecosystem on the Internet Computer — a coffee marketplace, AI-powered library, and DeFi banking protocol unified under a single Internet Identity."
  />
</svelte:head>

<div class="about-wrap">

  <!-- Hero -->
  <section class="about-hero">
    <div class="about-hero-badge">
      <Icon name="globe" size={13} />
      Internet Computer · ICP Blockchain
    </div>
    <h1 class="about-hero-title">One identity.<br />Three ecosystems.</h1>
    <p class="about-hero-sub">
      Cafreso is a Decentralized Autonomous Organization building the intersection of
      specialty coffee, on-chain AI search, and DeFi banking — all governed by $CF token
      holders and deployed on the Internet Computer.
    </p>
    <div class="about-property-row">
      <a href="/" class="about-property about-property--pages">
        <Icon name="house" size={18} />
        <span>cafreso.com</span>
      </a>
      <div class="about-property-sep">+</div>
      <a href={aiCafresoOrigin} data-sveltekit-reload="on" rel="noopener" class="about-property about-property--ai">
        <Icon name="brain" size={18} />
        <span>ai.cafreso.com</span>
      </a>
      <div class="about-property-sep">+</div>
      <a href={bankingBraveOrigin} data-sveltekit-reload="on" rel="noopener" class="about-property about-property--banking">
        <Icon name="bank" size={18} />
        <span>banking.cafreso.com</span>
      </a>
    </div>
  </section>

  <!-- The three properties -->
  <section class="about-section">
    <h2 class="about-h2">The Cafreso Ecosystem</h2>

    <div class="about-property-cards">

      <div class="apc apc--pages">
        <div class="apc-head">
          <span class="apc-icon"><Icon name="house" size={20} /></span>
          <div>
            <div class="apc-name">Cafreso Pages</div>
            <div class="apc-domain">cafreso.com</div>
          </div>
        </div>
        <p>
          The DAO's public-facing hub. Shop for ethically-sourced coffee, participate in
          governance votes, follow the dev log, and engage with the community in forums — all
          accessible with a single Internet Identity login.
        </p>
        <ul class="apc-list">
          <li><Icon name="storefront" size={13} /> Farm-to-cup coffee marketplace</li>
          <li><Icon name="gavel" size={13} /> On-chain governance (SNS proposals)</li>
          <li><Icon name="article" size={13} /> Developer log and community forums</li>
          <li><Icon name="coin" size={13} /> sGLDT gold rewards on every purchase</li>
        </ul>
      </div>

      <div class="apc apc--ai">
        <div class="apc-head">
          <span class="apc-icon"><Icon name="brain" size={20} /></span>
          <div>
            <div class="apc-name">AI Library</div>
            <div class="apc-domain">ai.cafreso.com</div>
          </div>
        </div>
        <p>
          A decentralized, big-data search engine built on the CafresoDAO agent-workflow.
          Think Google and Bing — but open-source, on-chain, and governed by the DAO.
          The AI agent searches the DAO's own knowledge vault first; if the answer isn't
          cached, it falls back to the Brave Search API and persists results back to the vault.
        </p>
        <ul class="apc-list">
          <li><Icon name="database" size={13} /> Vault-first search (on-chain memory)</li>
          <li><Icon name="magnifying-glass" size={13} /> Brave Search API fallback for new queries</li>
          <li><Icon name="robot" size={13} /> Agent-workflow orchestration (CafresoHQ)</li>
          <li><Icon name="lock" size={13} /> ICP-hosted — no central server</li>
        </ul>
        <a href={aiCafresoOrigin} data-sveltekit-reload="on" rel="noopener" class="apc-cta">
          Open AI Library <Icon name="arrow-up-right" size={12} />
        </a>
      </div>

      <div class="apc apc--banking">
        <div class="apc-head">
          <span class="apc-icon"><Icon name="bank" size={20} /></span>
          <div>
            <div class="apc-name">Banking.Brave</div>
            <div class="apc-domain">banking.cafreso.com</div>
          </div>
        </div>
        <p>
          The DeFi protocol layer governed by Cafreso DAO. Mine synthetic gold (sGLDT),
          exchange tokens, bridge ckUNI and other ICP assets, and track your yield positions —
          all from one wallet, one identity.
        </p>
        <ul class="apc-list">
          <li><Icon name="coin" size={13} /> Mine sGLDT yield</li>
          <li><Icon name="arrows-left-right" size={13} /> Token exchange &amp; liquidity</li>
          <li><Icon name="bridge" size={13} /> Cross-chain bridge (ckUNI, ckBTC)</li>
          <li><Icon name="receipt" size={13} /> On-chain transaction history</li>
        </ul>
        <a href={bankingBraveOrigin} data-sveltekit-reload="on" rel="noopener" class="apc-cta">
          Open Banking <Icon name="arrow-up-right" size={12} />
        </a>
      </div>

    </div>
  </section>

  <!-- DAO + Tokenomics -->
  <section class="about-section about-section--dark">
    <h2 class="about-h2">The DAO &amp; $CF Token</h2>
    <div class="about-two-col">
      <div>
        <p>
          Cafreso is governed as a Service Nervous System (SNS) DAO on the Internet Computer.
          $CF token holders vote on protocol upgrades, treasury allocations, fee parameters,
          and roadmap priorities. Every vote is recorded as an immutable on-chain proposal.
        </p>
        <p>
          Revenue from the coffee marketplace, mining fees, and exchange spreads flows
          into the DAO treasury — transparently, in real time.
        </p>
        <a href="/governance" class="about-link">
          Browse proposals <Icon name="arrow-right" size={13} />
        </a>
      </div>
      <div class="about-tokenomics">
        <div class="about-tok-title">$CF Token Distribution</div>
        {#each [
          { label: 'DAO Treasury',          pct: 46, color: 'hsl(32 72% 50%)' },
          { label: 'Decentralization Swap', pct: 27, color: 'hsl(112 43% 40%)' },
          { label: 'Development Team',      pct: 22, color: 'hsl(222 47% 40%)' },
          { label: 'Airdrops',              pct:  5, color: 'hsl(260 70% 55%)' },
        ] as t}
          <div class="about-tok-row">
            <div class="about-tok-bar-wrap">
              <div class="about-tok-bar" style="width: {t.pct}%; background: {t.color};"></div>
            </div>
            <div class="about-tok-meta">
              <span style="color: {t.color}; font-weight: 700;">{t.pct}%</span>
              <span>{t.label}</span>
            </div>
          </div>
        {/each}
        <div class="about-tok-supply">Total supply: 100,000,000 $CF</div>
      </div>
    </div>
  </section>

  <!-- El Salvador -->
  <section class="about-section">
    <h2 class="about-h2">Rooted in El Salvador <span style="font-size: 20px;">🇸🇻</span></h2>
    <div class="about-two-col">
      <div>
        <p>
          Cafreso's physical home is an urban farm-café in San Miguel, El Salvador — one of
          the first countries to adopt Bitcoin as legal tender. Every cup of coffee sold
          funds the farm. Every harvest is recorded on-chain. Vertical farming maximises
          yield with less water, and CO₂ offsets are published as upgradeable canister state.
        </p>
        <p style="font-weight: 600; color: hsl(var(--pg-fg));">
          Blockchain literacy and sustainable agriculture, together.
        </p>
        <a href="mailto:anthony@cafreso.com" class="about-link">
          <Icon name="envelope" size={13} /> anthony@cafreso.com
        </a>
      </div>
      <div style="display: flex; align-items: center; justify-content: center;">
        <img
          src="/assets/cafreso-roaster.webp"
          alt="Cafreso roaster"
          loading="lazy"
          decoding="async"
          style="width: min(260px, 100%); border-radius: 14px;"
        />
      </div>
    </div>
  </section>

  <!-- Built on ICP -->
  <section class="about-section about-section--dark">
    <h2 class="about-h2">Built on the Internet Computer</h2>
    <div class="about-icp-grid">
      {#each [
        { icon: 'lightning',    title: 'Web-speed smart contracts',  desc: 'Canisters serve HTTP directly — no bridges, no L2, no AWS dependency.' },
        { icon: 'fingerprint',  title: 'Internet Identity',          desc: 'One passkey-based identity works across all three Cafreso properties.' },
        { icon: 'lock-key',     title: 'Trustless governance',       desc: 'Every DAO vote is a signed on-chain transaction — no multisig committees.' },
        { icon: 'infinity',     title: 'Infinite scalability',       desc: 'CanDB-partitioned big-data vaults for the AI Library scale horizontally on ICP.' },
      ] as card}
        <div class="about-icp-card">
          <Icon name={card.icon} size={20} style="color: hsl(32 72% 50%); margin-bottom: 10px; display: block;" />
          <div style="font-size: 14px; font-weight: 700; color: hsl(var(--pg-fg)); margin-bottom: 6px;">{card.title}</div>
          <div style="font-size: 13px; line-height: 1.6; color: hsl(var(--pg-fg-muted));">{card.desc}</div>
        </div>
      {/each}
    </div>
  </section>

</div>

<style>
  .about-wrap {
    max-width: 920px;
    margin: 0 auto;
    padding-bottom: 80px;
  }

  /* Hero */
  .about-hero {
    text-align: center;
    padding: 56px 24px 48px;
  }
  .about-hero-badge {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em;
    padding: 4px 12px; border-radius: 999px;
    background: hsl(26 40% 93%); color: hsl(24 48% 30%);
    margin-bottom: 20px;
  }
  .about-hero-title {
    font-size: clamp(28px, 6vw, 44px); font-weight: 700; line-height: 1.15;
    color: hsl(var(--pg-fg)); margin: 0 0 18px; letter-spacing: -0.02em;
  }
  .about-hero-sub {
    font-size: 16px; line-height: 1.7; color: hsl(var(--pg-fg-muted));
    max-width: 580px; margin: 0 auto 32px;
  }
  .about-property-row {
    display: flex; align-items: center; justify-content: center;
    flex-wrap: wrap; gap: 10px;
  }
  .about-property {
    display: inline-flex; align-items: center; gap: 7px;
    padding: 8px 16px; border-radius: 10px; text-decoration: none;
    font-size: 13px; font-weight: 600;
    border: 1.5px solid transparent;
    transition: transform .2s, box-shadow .2s;
  }
  .about-property:hover { transform: translateY(-1px); }
  .about-property--pages  { background: hsl(32 60% 93%);  color: hsl(32 60% 34%);  border-color: hsl(32 50% 82%); }
  .about-property--ai     { background: hsl(260 60% 93%); color: hsl(260 60% 36%); border-color: hsl(260 50% 82%); }
  .about-property--banking { background: hsl(220 60% 93%); color: hsl(220 65% 34%); border-color: hsl(220 50% 82%); }
  .about-property-sep { font-size: 18px; font-weight: 300; color: hsl(var(--pg-fg-subtle)); }

  /* Sections */
  .about-section {
    padding: 48px 24px;
    border-top: 1px solid hsl(var(--pg-border));
  }
  .about-section--dark {
    background: hsl(var(--pg-surface));
    border-radius: 16px;
    margin: 0 12px;
  }
  .about-h2 {
    font-size: clamp(18px, 4vw, 24px); font-weight: 700;
    color: hsl(var(--pg-fg)); margin: 0 0 28px;
  }

  /* Property cards */
  .about-property-cards {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 18px;
  }
  .apc {
    background: hsl(var(--pg-elevated)); border-radius: 14px; padding: 24px 20px;
    border: 1px solid hsl(var(--pg-border));
    display: flex; flex-direction: column; gap: 12px;
  }
  .apc--pages  { border-top: 3px solid hsl(32 72% 50%); }
  .apc--ai     { border-top: 3px solid hsl(260 70% 55%); }
  .apc--banking { border-top: 3px solid hsl(220 78% 44%); }

  .apc-head { display: flex; align-items: center; gap: 12px; }
  .apc-icon {
    width: 40px; height: 40px; border-radius: 10px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
  }
  .apc--pages .apc-icon   { background: hsl(32 60% 93%);  color: hsl(32 60% 40%); }
  .apc--ai .apc-icon      { background: hsl(260 60% 93%); color: hsl(260 65% 46%); }
  .apc--banking .apc-icon { background: hsl(220 60% 92%); color: hsl(220 70% 40%); }

  .apc-name   { font-size: 14px; font-weight: 700; color: hsl(var(--pg-fg)); }
  .apc-domain { font-size: 11px; color: hsl(var(--pg-fg-muted)); margin-top: 1px; }

  .apc p { font-size: 13.5px; line-height: 1.65; color: hsl(var(--pg-fg-muted)); margin: 0; flex: 1; }

  .apc-list {
    list-style: none; padding: 0; margin: 0;
    display: flex; flex-direction: column; gap: 6px;
  }
  .apc-list li {
    display: flex; align-items: center; gap: 7px;
    font-size: 12.5px; color: hsl(var(--pg-fg-muted));
  }

  .apc-cta {
    display: inline-flex; align-items: center; gap: 5px; margin-top: 4px;
    font-size: 12.5px; font-weight: 700; text-decoration: none;
    padding: 7px 13px; border-radius: 8px;
    transition: background .15s;
  }
  .apc--ai .apc-cta      { background: hsl(260 60% 93%); color: hsl(260 60% 38%); }
  .apc--ai .apc-cta:hover { background: hsl(260 55% 87%); }
  .apc--banking .apc-cta  { background: hsl(220 60% 93%); color: hsl(220 65% 34%); }
  .apc--banking .apc-cta:hover { background: hsl(220 55% 87%); }

  /* Two-column layout */
  .about-two-col {
    display: grid; grid-template-columns: 1fr 1fr; gap: 40px; align-items: start;
  }
  .about-two-col p {
    font-size: 14.5px; line-height: 1.7; color: hsl(var(--pg-fg-muted)); margin: 0 0 14px;
  }
  .about-link {
    display: inline-flex; align-items: center; gap: 5px;
    font-size: 13px; font-weight: 600; text-decoration: none; color: hsl(32 72% 44%);
  }
  .about-link:hover { color: hsl(32 65% 34%); }

  /* Tokenomics */
  .about-tokenomics {
    background: hsl(var(--pg-elevated)); border-radius: 12px; padding: 20px;
    border: 1px solid hsl(var(--pg-border));
  }
  .about-tok-title {
    font-size: 12px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.07em; color: hsl(var(--pg-fg-muted)); margin-bottom: 14px;
  }
  .about-tok-row { margin-bottom: 12px; }
  .about-tok-bar-wrap {
    height: 6px; background: hsl(var(--pg-border)); border-radius: 3px;
    overflow: hidden; margin-bottom: 4px;
  }
  .about-tok-bar { height: 100%; border-radius: 3px; transition: width .6s; }
  .about-tok-meta {
    display: flex; gap: 6px; align-items: baseline;
    font-size: 12px;
  }
  .about-tok-meta span:last-child { color: hsl(var(--pg-fg-muted)); }
  .about-tok-supply {
    font-size: 11.5px; color: hsl(var(--pg-fg-muted)); margin-top: 10px;
    padding-top: 10px; border-top: 1px solid hsl(var(--pg-border));
  }

  /* ICP grid */
  .about-icp-grid {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
  }
  .about-icp-card {
    background: hsl(var(--pg-elevated)); border-radius: 12px; padding: 20px 16px;
    border: 1px solid hsl(var(--pg-border));
  }

  /* Responsive */
  @media (max-width: 720px) {
    .about-property-cards { grid-template-columns: 1fr; }
    .about-two-col { grid-template-columns: 1fr; }
    .about-icp-grid { grid-template-columns: 1fr 1fr; }
    .about-section--dark { margin: 0; border-radius: 0; }
  }
  @media (max-width: 480px) {
    .about-icp-grid { grid-template-columns: 1fr; }
  }

  /* ── Dark-mode overrides for branded pale chips ──
     Base rules keep their exact light values so light mode is unchanged;
     these translucent-brand versions only apply under .dark so the pale
     wash + dark-ink chips don't read as loud bright blocks on dark cards. */
  :global(.dark) .about-hero-badge {
    background: hsl(32 45% 26%); color: hsl(38 80% 76%);
  }
  :global(.dark) .about-property--pages {
    background: hsl(32 55% 30% / 0.4); color: hsl(32 85% 76%); border-color: hsl(32 55% 50% / 0.5);
  }
  :global(.dark) .about-property--ai {
    background: hsl(260 55% 34% / 0.4); color: hsl(260 85% 84%); border-color: hsl(260 55% 58% / 0.5);
  }
  :global(.dark) .about-property--banking {
    background: hsl(220 55% 34% / 0.4); color: hsl(220 85% 82%); border-color: hsl(220 55% 58% / 0.5);
  }
  :global(.dark) .apc--pages .apc-icon {
    background: hsl(32 55% 30% / 0.4); color: hsl(32 85% 72%);
  }
  :global(.dark) .apc--ai .apc-icon {
    background: hsl(260 55% 34% / 0.4); color: hsl(260 85% 80%);
  }
  :global(.dark) .apc--banking .apc-icon {
    background: hsl(220 55% 34% / 0.4); color: hsl(220 85% 78%);
  }
  :global(.dark) .apc--ai .apc-cta {
    background: hsl(260 55% 34% / 0.4); color: hsl(260 85% 82%);
  }
  :global(.dark) .apc--ai .apc-cta:hover {
    background: hsl(260 55% 40% / 0.5);
  }
  :global(.dark) .apc--banking .apc-cta {
    background: hsl(220 55% 34% / 0.4); color: hsl(220 85% 80%);
  }
  :global(.dark) .apc--banking .apc-cta:hover {
    background: hsl(220 55% 42% / 0.5);
  }
</style>
