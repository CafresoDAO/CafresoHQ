<script>
  import { onMount } from 'svelte';
  import { bbLinks, aiCafresoOrigin, bankingBraveOrigin } from '$lib/links.js';
  import Icon from '$lib/components/Icon.svelte';
  import Avatar from '$lib/components/Avatar.svelte';
  import { POSTS, fmtDate } from '$lib/data/blog.js';
  import { PROPOSALS, PROPOSAL_STATUSES, PROPOSAL_TYPES } from '$lib/data/governance.js';
  import { listPosts, listForumPosts, getLeaderboard } from '$lib/api/devlog.js';
  import { aiSearchOpen } from '$lib/stores/blog.js';

  // Governance is still seed-backed — no governance canister yet (roadmap Phase 4).
  const openProposals = PROPOSALS.filter((p) => p.status === 'open');
  const featuredProposal = openProposals[0] ?? null;
  const totalProposals = PROPOSALS.length;

  // Activity hub: live from the IndexCanister, with seed as first-paint fallback
  // so SSR/preview never blanks. Hydrated on mount; falls back silently offline.
  let latestPost = POSTS[0] ?? null;
  let devLogCount = POSTS.length;
  let forumThreadCount = 0;
  let nanasBurned = 0;

  onMount(async () => {
    try {
      const [posts, forums, leaderboard] = await Promise.all([
        listPosts(),
        listForumPosts(),
        getLeaderboard(500),
      ]);
      if (posts?.length) {
        latestPost = [...posts].sort((a, b) => (b.date || '').localeCompare(a.date || ''))[0] ?? latestPost;
        devLogCount = posts.length;
      }
      forumThreadCount = forums?.length ?? 0;
      nanasBurned = (leaderboard || []).reduce((sum, r) => sum + (r.burned || 0), 0);
    } catch (e) {
      console.warn('[home] live activity fetch failed, using seed', e);
    }
  });
</script>

<svelte:head>
  <title>Cafreso · A Blockchain DAO</title>
  <meta
    name="description"
    content="Cafreso is a DAO of coffee-loving developers governing the Banking.Brave protocols on the Internet Computer. Buy coffee with $nanas, mine sGLDT, bridge ckUNI — all in one Internet Identity."
  />
</svelte:head>

<div class="homepage">

  <!-- ── HERO ──────────────────────────────────────────────── -->
  <section class="hero">
    <img
      src="/assets/cafreso-wordmark.png"
      alt="Cafreso"
      class="hero-logo"
    />
    <p class="hero-tagline">
      Coffee-loving developers designing<br />
      open-source software on ICP
    </p>
    <p class="hero-sub">
      A Decentralized Autonomous Organization governing the Banking.Brave protocols,
      a farm-to-cup coffee marketplace, and on-chain DeFi tooling — all accessed
      through a single Internet Identity.
    </p>
    <div class="hero-links">
      <a href="/shop" class="hero-btn outline">
        <Icon name="storefront" size={16} /> Shop
      </a>
      <a href="/blog" class="hero-btn outline">
        <Icon name="newspaper" size={16} /> Blog
      </a>
      <button
        type="button"
        class="hero-btn search"
        on:click={() => aiSearchOpen.set(true)}
      >
        <Icon name="magnifying-glass" size={18} weight="bold" />
      </button>
      <a href={bbLinks.mine} data-sveltekit-reload="on" rel="noopener" class="hero-btn outline">
        <Icon name="pickaxe" size={16} /> Mine
      </a>
      <a
        href="https://github.com/DappjakLabs/Cafreso"
        rel="noopener"
        target="_blank"
        class="hero-btn outline"
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" style="margin-right:4px;">
          <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/>
        </svg>
        GitHub
      </a>
    </div>
  </section>

  <!-- ── ACTIVITY HUB ───────────────────────────────────── -->
  <section class="activity-hub">
    <div class="ah-header">
      <h2 class="ah-title">What's happening</h2>
      <span class="ah-live"><span class="ah-dot"></span> Live</span>
    </div>

    <div class="ah-grid">

      <!-- Latest Dev Log post -->
      {#if latestPost}
        <a href="/blog/{latestPost.slug}" class="ah-card ah-card--post">
          <div class="ah-card-eyebrow">
            <Icon name="article" size={12} />
            Dev Log
          </div>
          <div class="ah-card-body">
            <div class="ah-card-avatar">
              <Avatar name={latestPost.author?.name ?? 'Cafreso'} hue={latestPost.author?.hue ?? 24} size={30} />
            </div>
            <div class="ah-card-text">
              <div class="ah-card-title">{latestPost.title}</div>
              <div class="ah-card-meta">
                {latestPost.author?.name ?? 'Cafreso'} · {fmtDate(latestPost.date)} · {latestPost.readMin} min
              </div>
            </div>
          </div>
          <div class="ah-card-excerpt">{latestPost.excerpt?.slice(0, 110)}…</div>
          <div class="ah-card-footer">
            <span class="ah-tag" style="background: hsl(26 40% 93%); color: hsl(24 48% 28%);">
              <Icon name="fire" size={10} /> {(latestPost.burned ?? 0).toLocaleString()} $nanas
            </span>
            <span class="ah-cta">Read post <Icon name="arrow-right" size={11} /></span>
          </div>
        </a>
      {/if}

      <!-- Featured open governance proposal -->
      {#if featuredProposal}
        {@const ps = PROPOSAL_STATUSES[featuredProposal.status]}
        {@const pt = PROPOSAL_TYPES[featuredProposal.type]}
        <a href="/governance/{featuredProposal.id}" class="ah-card ah-card--gov">
          <div class="ah-card-eyebrow" style="color: hsl(260 60% 50%);">
            <Icon name="gavel" size={12} />
            Governance · {openProposals.length} open
          </div>
          <div class="ah-card-title" style="margin-top: 10px;">{featuredProposal.title}</div>
          <div class="ah-card-meta" style="margin-top: 4px;">
            Proposed by {featuredProposal.proposedBy?.name ?? 'DAO'}
          </div>
          <div class="ah-card-footer" style="margin-top: auto; padding-top: 14px;">
            <span class="ah-tag" style="background: {ps.bg}; color: {ps.color};">
              {ps.label}
            </span>
            {#if pt}
              <span class="ah-tag" style="background: hsl(260 40% 95%); color: hsl(260 50% 40%);">
                <Icon name={pt.icon} size={10} /> {pt.label}
              </span>
            {/if}
            <span class="ah-cta">Vote now <Icon name="arrow-right" size={11} /></span>
          </div>
        </a>
      {/if}

      <!-- Forums CTA -->
      <a href="/forums" class="ah-card ah-card--forums">
        <div class="ah-card-eyebrow" style="color: hsl(24 48% 28%);">
          <Icon name="chats-circle" size={12} />
          Community forums
        </div>
        <div class="ah-card-title" style="margin-top: 10px;">Join the conversation</div>
        <div class="ah-card-meta" style="margin-top: 4px; margin-bottom: 14px;">
          {forumThreadCount > 0 ? `${forumThreadCount} active threads · ` : ''}Discuss proposals, share ideas
        </div>
        <div class="ah-forum-pills">
          {#each ['DAO talk', 'Tokenomics', 'Banking.Brave', 'Community'] as tag}
            <span class="ah-forum-pill">{tag}</span>
          {/each}
        </div>
        <div class="ah-card-footer">
          <span class="ah-cta">Browse forums <Icon name="arrow-right" size={11} /></span>
        </div>
      </a>

      <!-- DAO stats strip -->
      <div class="ah-stats">
        <div class="ah-stat">
          <div class="ah-stat-num">{totalProposals}</div>
          <div class="ah-stat-label">Proposals</div>
        </div>
        <div class="ah-stat-div"></div>
        <div class="ah-stat">
          <div class="ah-stat-num">{openProposals.length}</div>
          <div class="ah-stat-label">Open votes</div>
        </div>
        <div class="ah-stat-div"></div>
        <div class="ah-stat">
          <div class="ah-stat-num">{nanasBurned.toLocaleString()}</div>
          <div class="ah-stat-label">$nanas burned</div>
        </div>
        <div class="ah-stat-div"></div>
        <div class="ah-stat">
          <div class="ah-stat-num">{devLogCount}</div>
          <div class="ah-stat-label">Dev Log posts</div>
        </div>
      </div>

    </div>
  </section>

  <!-- ── WHAT THIS APP CAN DO ─────────────────────────────── -->
  <section class="features">
    <h2 class="section-title">What you can do</h2>
    <div class="feature-grid">
      <div class="feature-card">
        <div class="feature-icon" style="background: hsl(26 85% 95%); color: hsl(26 70% 40%);">
          <Icon name="shopping-bag" size={22} weight="duotone" />
        </div>
        <h3>Buy coffee with $nanas</h3>
        <p>Purchase premium ethically-sourced coffee from El Salvador. Pay with $nanas tokens on-chain or credit card via Stripe.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon" style="background: hsl(48 80% 92%); color: hsl(38 75% 38%);">
          <Icon name="coins" size={22} weight="duotone" />
        </div>
        <h3>Tip & burn $nanas</h3>
        <p>Stake tokens on dev-log posts and forum threads. Burns are recorded on-chain with full principal attribution.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon" style="background: hsl(112 40% 93%); color: hsl(112 43% 32%);">
          <Icon name="chat-circle-text" size={22} weight="duotone" />
        </div>
        <h3>Community forums</h3>
        <p>Post and discuss on canister-backed forums. Every comment is signed by your Internet Identity — no impersonation.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon" style="background: hsl(215 50% 94%); color: hsl(215 60% 38%);">
          <Icon name="wallet" size={22} weight="duotone" />
        </div>
        <h3>Multi-token wallet</h3>
        <p>View balances of ICP, $nanas, ckUNI, and sGLDT in one place. Transfer tokens directly from the profile page.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon" style="background: hsl(280 40% 94%); color: hsl(280 50% 40%);">
          <Icon name="identification-card" size={22} weight="duotone" />
        </div>
        <h3>Internet Identity login</h3>
        <p>Non-custodial authentication. No passwords, no KYC. Your principal is your identity across every canister.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon" style="background: hsl(0 50% 95%); color: hsl(0 55% 42%);">
          <Icon name="fire" size={22} weight="duotone" />
        </div>
        <h3>On-chain order ledger</h3>
        <p>Every order is signed under your principal and stored on the ICP blockchain. Admin-verified payments. Full audit trail.</p>
      </div>
    </div>
  </section>

  <!-- ── PROTOCOLS ────────────────────────────────────────── -->
  <section class="protocols">
    <h2 class="section-title">Banking.Brave Protocols</h2>
    <p class="section-sub">Governed by the Cafreso DAO and executed on the Internet Computer.</p>

    <div class="protocol-cards">
      <a href={bbLinks.mine} data-sveltekit-reload="on" rel="noopener" class="protocol-card">
        <div class="pc-icon" style="background: hsl(48 80% 92%);">
          <Icon name="pickaxe" size={24} weight="duotone" />
        </div>
        <h3>MineGold.Brave</h3>
        <p>Exchange Brave browser BAT revenue for sGLDT — a gold-backed token. Non-custodial. No KYC. All on-chain.</p>
        <span class="pc-link">Open the mine <Icon name="arrow-right" size={13} /></span>
      </a>

      <a href={bbLinks.exchange} data-sveltekit-reload="on" rel="noopener" class="protocol-card">
        <div class="pc-icon" style="background: hsl(215 50% 93%);">
          <Icon name="bank" size={24} weight="duotone" />
        </div>
        <h3>Banking.Brave</h3>
        <p>Decentralized credit access through Internet Identities. No paperwork, no middlemen. Your on-chain history is your credit score.</p>
        <span class="pc-link">Visit the protocol <Icon name="arrow-right" size={13} /></span>
      </a>

      <a href={bbLinks.bridge} data-sveltekit-reload="on" rel="noopener" class="protocol-card">
        <div class="pc-icon" style="background: hsl(160 40% 92%);">
          <Icon name="bridge" size={24} weight="duotone" />
        </div>
        <h3>ckUNI Bridge</h3>
        <p>Bridge Uniswap governance tokens into chain-key ckUNI on the Internet Computer for fee-light, high-speed DeFi composability.</p>
        <span class="pc-link">Open the bridge <Icon name="arrow-right" size={13} /></span>
      </a>
    </div>
  </section>

  <!-- ── ECOSYSTEM ────────────────────────────────────────── -->
  <section class="ecosystem">
    <h2 class="section-title">The Cafreso Ecosystem</h2>
    <p class="section-sub">Three interconnected properties — all on the Internet Computer.</p>
    <div class="eco-grid">

      <!-- Cafreso Pages / DAO -->
      <div class="eco-card eco-card--pages">
        <div class="eco-card-icon">
          <Icon name="house" size={22} />
        </div>
        <div class="eco-card-label">cafreso.com</div>
        <h3 class="eco-card-title">DAO Hub</h3>
        <p class="eco-card-desc">
          Shop for coffee, govern the protocol, read the dev log, and participate in
          community forums — the DAO's home base on-chain.
        </p>
        <div class="eco-card-links">
          <a href="/shop" class="eco-link">Shop <Icon name="arrow-right" size={12} /></a>
          <a href="/governance" class="eco-link">Governance <Icon name="arrow-right" size={12} /></a>
          <a href="/forums" class="eco-link">Forums <Icon name="arrow-right" size={12} /></a>
        </div>
      </div>

      <!-- AI Library -->
      <a
        href={aiCafresoOrigin}
        data-sveltekit-reload="on"
        rel="noopener"
        class="eco-card eco-card--ai eco-card-link"
      >
        <div class="eco-card-icon">
          <Icon name="brain" size={22} />
        </div>
        <div class="eco-card-label">ai.cafreso.com <Icon name="arrow-up-right" size={11} style="opacity:0.6;" /></div>
        <h3 class="eco-card-title">AI Library</h3>
        <p class="eco-card-desc">
          Decentralized search powered by the CafresoDAO vault. Ask anything —
          the agent-workflow searches on-chain memory first, then the open web.
        </p>
        <div class="eco-card-links">
          <span class="eco-chip">Vault search</span>
          <span class="eco-chip">Brave web fallback</span>
          <span class="eco-chip">ICP-hosted</span>
        </div>
      </a>

      <!-- Banking.Brave -->
      <a
        href={bankingBraveOrigin}
        data-sveltekit-reload="on"
        rel="noopener"
        class="eco-card eco-card--banking eco-card-link"
      >
        <div class="eco-card-icon">
          <Icon name="bank" size={22} />
        </div>
        <div class="eco-card-label">banking.cafreso.com <Icon name="arrow-up-right" size={11} style="opacity:0.6;" /></div>
        <h3 class="eco-card-title">Banking.Brave</h3>
        <p class="eco-card-desc">
          DeFi protocols governed by Cafreso DAO. Mine sGLDT, exchange tokens,
          bridge assets, and track yield — all through a single Internet Identity.
        </p>
        <div class="eco-card-links">
          <span class="eco-chip">Mine</span>
          <span class="eco-chip">Exchange</span>
          <span class="eco-chip">Bridge</span>
        </div>
      </a>

    </div>
  </section>

  <!-- ── EL SALVADOR ──────────────────────────────────────── -->
  <section class="farming">
    <div class="farming-inner">
      <div class="farming-text">
        <h2 class="section-title" style="text-align: left;">
          Accelerating Blockchain in El Salvador <span style="font-size: 24px;">🇸🇻</span>
        </h2>
        <p>
          Cafreso's urban farm-cafe combines a working cafe with a public urban farm in El Salvador.
          Every cup of coffee funds the farm. Every harvest is recorded on-chain. Vertical farming
          maximises yield with less water. Treasury flows and CO₂ offsets are published as upgradeable
          canister state — no spreadsheets, no trust required.
        </p>
        <p style="font-weight: 500; color: hsl(222 47% 11%);">
          Blockchain literacy and sustainable agriculture, together.
        </p>
      </div>
      <div class="farming-img-wrap">
        <img src="/assets/cafreso-roaster.png" alt="Cafreso roaster" class="farming-img" />
      </div>
    </div>
  </section>

  <!-- ── PARTNER RIBBON ───────────────────────────────────── -->
  <section class="partners">
    <div class="partner-row">
      {#each [
        { src: '/assets/icp.png', alt: 'Internet Computer' },
        { src: '/assets/nanas-coin.png', alt: '$nanas' },
        { src: '/assets/gold-dao.png', alt: 'Gold DAO' },
        { src: '/assets/banking-brave-logo.png', alt: 'Banking.Brave' },
        { src: '/assets/cf-black.png', alt: 'Cafreso' }
      ] as logo}
        <img src={logo.src} alt={logo.alt} class="partner-logo" />
      {/each}
    </div>
  </section>

  <!-- ── FOOTER BAR ───────────────────────────────────────── -->
  <div class="hp-footer">
    <span>
      Web2 ·
      <a
        href="https://github.com/DappjakLabs/Cafreso"
        rel="noopener"
        target="_blank"
      >GitHub</a>
    </span>
    <span class="dot">·</span>
    <span>
      Web3 ·
      <a
        href="https://oc.app/community/cpkbm-lyaaa-aaaaf-bkcwa-cai"
        rel="noopener"
        target="_blank"
      >OpenChat</a>
    </span>
    <span class="dot">·</span>
    <span>
      AI ·
      <a href={aiCafresoOrigin} data-sveltekit-reload="on" rel="noopener">ai.cafreso.com</a>
    </span>
  </div>

</div>

<style>
  /* ── Base ──────────────────────────────────────────────── */
  .homepage {
    --ink: hsl(222 47% 11%);
    --ink-soft: hsl(222 47% 11% / 0.6);
    --ink-muted: hsl(222 47% 11% / 0.4);
    --leaf: hsl(112 43% 35%);
    --leaf-bg: hsl(112 40% 95%);
    --gold: hsl(26 70% 46%);
    --surface: hsl(0 0% 99%);
    --border: hsl(0 0% 88%);
    background: var(--surface);
    min-height: 100vh;
  }

  /* ── Hero ──────────────────────────────────────────────── */
  .hero {
    text-align: center;
    padding: 56px 24px 48px;
    max-width: 720px;
    margin: 0 auto;
  }
  .hero-logo {
    width: min(380px, 80vw);
    height: auto;
    display: block;
    margin: 0 auto 28px;
  }
  .hero-tagline {
    font-size: clamp(20px, 4.5vw, 28px);
    font-weight: 600;
    color: var(--ink);
    line-height: 1.35;
    margin: 0 0 16px;
    letter-spacing: -0.01em;
  }
  .hero-sub {
    font-size: 15px;
    line-height: 1.7;
    color: var(--ink-soft);
    margin: 0 auto 28px;
    max-width: 560px;
  }
  .hero-links {
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: 10px;
  }
  .hero-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13.5px;
    font-weight: 600;
    padding: 10px 22px;
    border-radius: 10px;
    text-decoration: none;
    transition: all 0.2s;
  }
  .hero-btn.outline {
    background: transparent;
    color: var(--ink);
    border: 1.5px solid var(--border);
  }
  .hero-btn.outline:hover {
    border-color: hsl(0 0% 72%);
    background: hsl(0 0% 96%);
  }
  .hero-btn.search {
    width: 46px;
    height: 46px;
    padding: 0;
    justify-content: center;
    background: hsl(260 70% 50%);
    color: #fff;
    border-radius: 50%;
    border: none;
    box-shadow: 0 4px 16px hsl(260 70% 50% / 0.35), 0 1px 0 hsl(260 90% 75% / 0.4) inset;
    cursor: pointer;
    font-family: inherit;
  }
  .hero-btn.search:hover {
    background: hsl(260 70% 44%);
    box-shadow: 0 6px 22px hsl(260 70% 50% / 0.45), 0 1px 0 hsl(260 90% 75% / 0.4) inset;
    transform: scale(1.06);
  }

  /* ── Section titles ────────────────────────────────────── */
  .section-title {
    font-size: clamp(18px, 4vw, 23px);
    font-weight: 700;
    color: var(--ink);
    margin: 0 0 8px;
    text-align: center;
    letter-spacing: -0.015em;
  }
  .section-sub {
    font-size: 14.5px;
    color: var(--ink-soft);
    margin: 0 0 32px;
    text-align: center;
  }

  /* ── Features ──────────────────────────────────────────── */
  .features {
    padding: 48px 24px 56px;
    max-width: 920px;
    margin: 0 auto;
  }
  .features .section-title { margin-bottom: 32px; }
  .feature-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 18px;
  }
  .feature-card {
    background: #fff;
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 24px 22px;
    transition: box-shadow 0.25s, border-color 0.25s;
  }
  .feature-card:hover {
    border-color: hsl(0 0% 78%);
    box-shadow: 0 4px 20px hsl(0 0% 0% / 0.04);
  }
  .feature-icon {
    width: 42px;
    height: 42px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 14px;
  }
  .feature-card h3 {
    font-size: 15px;
    font-weight: 600;
    color: var(--ink);
    margin: 0 0 8px;
  }
  .feature-card p {
    font-size: 13.5px;
    line-height: 1.65;
    color: var(--ink-soft);
    margin: 0;
  }

  /* ── Protocols ─────────────────────────────────────────── */
  .protocols {
    padding: 48px 24px 56px;
    max-width: 920px;
    margin: 0 auto;
    border-top: 1px solid var(--border);
  }
  .protocol-cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 18px;
  }
  .protocol-card {
    display: block;
    text-decoration: none;
    background: #fff;
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 26px 22px 22px;
    transition: border-color 0.25s, box-shadow 0.25s, transform 0.25s;
  }
  .protocol-card:hover {
    border-color: hsl(112 43% 70%);
    box-shadow: 0 6px 24px hsl(112 43% 35% / 0.08);
    transform: translateY(-2px);
  }
  .pc-icon {
    width: 46px;
    height: 46px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 16px;
    color: var(--ink);
  }
  .protocol-card h3 {
    font-size: 16px;
    font-weight: 600;
    color: var(--ink);
    margin: 0 0 8px;
  }
  .protocol-card p {
    font-size: 13.5px;
    line-height: 1.65;
    color: var(--ink-soft);
    margin: 0 0 16px;
  }
  .pc-link {
    font-size: 13px;
    font-weight: 600;
    color: var(--leaf);
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }

  /* ── Ecosystem ────────────────────────────────────────── */
  .ecosystem {
    padding: 48px 24px 56px;
    max-width: 1020px;
    margin: 0 auto;
    border-top: 1px solid var(--border);
  }
  .eco-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 18px;
  }
  .eco-card {
    background: #fff;
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 26px 22px 22px;
    display: flex;
    flex-direction: column;
    gap: 0;
  }
  .eco-card-link {
    text-decoration: none;
    transition: border-color .2s, box-shadow .2s, transform .2s;
  }
  .eco-card-link:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 28px -8px hsl(222 47% 20% / 0.12);
  }
  .eco-card--pages { border-top: 3px solid hsl(32 72% 50%); }
  .eco-card--ai    { border-top: 3px solid hsl(260 70% 55%); }
  .eco-card--banking { border-top: 3px solid hsl(220 78% 44%); }
  .eco-card--ai:hover    { border-color: hsl(260 60% 65%); }
  .eco-card--banking:hover { border-color: hsl(220 70% 55%); }

  .eco-card-icon {
    width: 44px; height: 44px; border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    margin-bottom: 14px;
  }
  .eco-card--pages .eco-card-icon  { background: hsl(32 60% 93%);  color: hsl(32 72% 44%); }
  .eco-card--ai .eco-card-icon     { background: hsl(260 70% 93%); color: hsl(260 70% 50%); }
  .eco-card--banking .eco-card-icon { background: hsl(220 78% 92%); color: hsl(220 78% 44%); }

  .eco-card-label {
    font-size: 10.5px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.08em; margin-bottom: 6px;
    display: flex; align-items: center; gap: 3px;
  }
  .eco-card--pages .eco-card-label   { color: hsl(32 60% 44%); }
  .eco-card--ai .eco-card-label      { color: hsl(260 60% 46%); }
  .eco-card--banking .eco-card-label { color: hsl(220 70% 40%); }

  .eco-card-title {
    font-size: 17px; font-weight: 700; color: var(--ink);
    margin: 0 0 10px; line-height: 1.2;
  }
  .eco-card-desc {
    font-size: 13.5px; line-height: 1.65; color: var(--ink-soft);
    margin: 0 0 18px; flex: 1;
  }
  .eco-card-links {
    display: flex; flex-wrap: wrap; gap: 8px;
  }
  .eco-link {
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 12.5px; font-weight: 600; text-decoration: none;
    color: hsl(32 72% 44%);
  }
  .eco-link:hover { color: hsl(32 65% 34%); }
  .eco-chip {
    font-size: 11px; font-weight: 600;
    padding: 3px 8px; border-radius: 6px;
    background: hsl(26 40% 93%); color: hsl(24 48% 30%);
  }
  .eco-card--ai .eco-chip     { background: hsl(260 60% 93%); color: hsl(260 60% 36%); }
  .eco-card--banking .eco-chip { background: hsl(220 60% 93%); color: hsl(220 70% 34%); }

  @media (max-width: 700px) {
    .eco-grid { grid-template-columns: 1fr; }
  }

  /* ── Farming ───────────────────────────────────────────── */
  .farming {
    padding: 56px 24px;
    border-top: 1px solid var(--border);
  }
  .farming-inner {
    max-width: 880px;
    margin: 0 auto;
    display: flex;
    align-items: center;
    gap: 48px;
  }
  .farming-text {
    flex: 1;
  }
  .farming-text p {
    font-size: 14.5px;
    line-height: 1.7;
    color: var(--ink-soft);
    margin: 0 0 12px;
  }
  .farming-img-wrap {
    flex-shrink: 0;
  }
  .farming-img {
    width: 200px;
    height: auto;
    opacity: 0.85;
  }
  @media (max-width: 640px) {
    .farming-inner {
      flex-direction: column-reverse;
      gap: 24px;
      text-align: center;
    }
    .farming-text .section-title { text-align: center !important; }
    .farming-img { width: 140px; }
  }

  /* ── Partners ──────────────────────────────────────────── */
  .partners {
    padding: 36px 24px;
    border-top: 1px solid var(--border);
  }
  .partner-row {
    display: flex;
    align-items: center;
    justify-content: center;
    flex-wrap: wrap;
    gap: 32px;
    opacity: 0.5;
  }
  .partner-logo {
    height: 28px;
    width: auto;
    object-fit: contain;
  }

  /* ── Activity Hub ──────────────────────────────────────── */
  .activity-hub {
    padding: 40px 24px 48px;
    max-width: 920px;
    margin: 0 auto;
    border-top: 1px solid var(--border);
  }
  .ah-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
  }
  .ah-title {
    font-size: clamp(18px, 4vw, 22px);
    font-weight: 700;
    color: var(--ink);
    letter-spacing: -0.015em;
    margin: 0;
  }
  .ah-live {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 11.5px;
    font-weight: 600;
    color: hsl(112 43% 38%);
    background: hsl(112 40% 93%);
    border: 1px solid hsl(112 40% 80%);
    border-radius: 20px;
    padding: 3px 10px;
  }
  .ah-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: hsl(112 43% 45%);
    animation: ah-pulse 2s ease-in-out infinite;
  }
  @keyframes ah-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }
  .ah-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: auto auto;
    gap: 14px;
  }
  @media (max-width: 640px) {
    .ah-grid { grid-template-columns: 1fr; }
  }

  .ah-card {
    display: flex;
    flex-direction: column;
    background: #fff;
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 18px 20px;
    text-decoration: none;
    color: inherit;
    transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
  }
  .ah-card:hover {
    border-color: hsl(0 0% 74%);
    box-shadow: 0 4px 20px hsl(0 0% 0% / 0.05);
    transform: translateY(-1px);
  }
  .ah-card--post { border-left: 3px solid hsl(26 70% 52%); }
  .ah-card--gov  { border-left: 3px solid hsl(260 60% 60%); }
  .ah-card--forums { border-left: 3px solid hsl(24 55% 65%); }

  .ah-card-eyebrow {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 10.5px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: hsl(215 16% 47%);
    margin-bottom: 8px;
  }
  .ah-card-body {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    margin-bottom: 8px;
  }
  .ah-card-avatar { flex-shrink: 0; }
  .ah-card-text { flex: 1; min-width: 0; }
  .ah-card-title {
    font-size: 14.5px;
    font-weight: 700;
    color: var(--ink);
    line-height: 1.35;
    letter-spacing: -0.01em;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .ah-card-meta {
    font-size: 11.5px;
    color: hsl(215 16% 52%);
    margin-top: 3px;
  }
  .ah-card-excerpt {
    font-size: 12.5px;
    line-height: 1.55;
    color: hsl(215 16% 42%);
    margin-bottom: 12px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .ah-card-footer {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: auto;
  }
  .ah-tag {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    font-size: 10.5px;
    font-weight: 600;
    border-radius: 6px;
    padding: 2px 7px;
  }
  .ah-cta {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    font-size: 11.5px;
    font-weight: 600;
    color: var(--ink);
    margin-left: auto;
  }
  .ah-forum-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin-bottom: 4px;
  }
  .ah-forum-pill {
    font-size: 10.5px;
    font-weight: 600;
    background: hsl(26 40% 93%);
    color: hsl(24 48% 28%);
    border-radius: 6px;
    padding: 2px 8px;
    border: 1px solid hsl(26 30% 83%);
  }

  /* Stats strip — spans full width */
  .ah-stats {
    grid-column: 1 / -1;
    display: flex;
    align-items: center;
    justify-content: space-around;
    background: hsl(222 47% 11%);
    border-radius: 14px;
    padding: 18px 24px;
    gap: 0;
  }
  .ah-stat {
    text-align: center;
    flex: 1;
  }
  .ah-stat-num {
    font-size: 22px;
    font-weight: 800;
    color: #fff;
    letter-spacing: -0.02em;
    line-height: 1;
    margin-bottom: 4px;
  }
  .ah-stat-label {
    font-size: 10.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: hsl(222 30% 65%);
  }
  .ah-stat-div {
    width: 1px;
    height: 32px;
    background: hsl(222 30% 22%);
    flex-shrink: 0;
  }

  /* ── Footer bar ────────────────────────────────────────── */
  .hp-footer {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 8px;
    padding: 24px;
    font-size: 12.5px;
    color: var(--ink-muted);
  }
  .hp-footer a {
    color: var(--ink-soft);
    text-decoration: none;
    transition: color 0.18s;
  }
  .hp-footer a:hover { color: var(--ink); }
  .hp-footer .dot { color: hsl(0 0% 80%); }
</style>
