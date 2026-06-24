<svelte:options runes={true} />

<script>
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import Icon from '$lib/components/Icon.svelte';
  import Avatar from '$lib/components/Avatar.svelte';
  import { POSTS, fmtDate } from '$lib/data/blog.js';
  import { PROPOSALS, proposalType, proposalStatus } from '$lib/data/governance.js';
  import { aiSearchOpen } from '$lib/stores/blog.js';

  // Forum seed — when canister is live this is fetched; for now a static list.
  const FORUM_SEEDS = [
    { slug: 'q2-apy-proposal-discussion',   title: 'Q2 APY Proposal — Community Discussion',   excerpt: 'Thoughts on setting the $CF staking rate to 7.25% for Q2 2026.',   cat: 'dao' },
    { slug: 'q2-marketing-budget-discussion', title: 'Q2 Marketing Budget — Feedback Wanted',   excerpt: 'The Growth Guild is proposing 120k $CF for community marketing.', cat: 'community' },
    { slug: 'anonymous-posting-debate',      title: 'Should Anonymous Forum Posting Be Allowed?', excerpt: 'A discussion on requiring II auth for all forum posts.',          cat: 'governance' },
    { slug: 'banking-brave-discussion',      title: 'Banking.Brave Launch — Your Questions',    excerpt: 'Open Q&A thread on the Banking.Brave yield protocol launch.',     cat: 'banking-brave' },
    { slug: 'testnet-airdrop-proposal',      title: 'Testnet Reward Airdrop Discussion',        excerpt: '500 $CF per eligible principal — who counts and how?',            cat: 'dao' },
  ];

  const CAT_COLORS = {
    dao: 'hsl(260 70% 62%)', community: 'hsl(24 48% 35%)', governance: 'hsl(43 74% 44%)',
    'banking-brave': 'hsl(220 78% 44%)', 'build-log': 'hsl(32 72% 50%)',
  };

  let inputEl = $state(null);
  let query = $derived($page.url.searchParams.get('q') ?? '');

  // Normalised search — lower-cased, strips punctuation for robust matching.
  function score(text, q) {
    if (!q) return 0;
    const t = text.toLowerCase();
    const s = q.toLowerCase().trim();
    if (t.includes(s))         return 2;
    if (t.includes(s.slice(0, Math.max(s.length - 2, 3)))) return 1;
    return 0;
  }

  function matchPost(p, q) {
    return score(p.title + ' ' + p.excerpt + ' ' + p.cat, q) > 0;
  }
  function matchProposal(p, q) {
    return score(p.title + ' ' + p.summary + ' ' + p.type, q) > 0;
  }
  function matchForum(f, q) {
    return score(f.title + ' ' + f.excerpt + ' ' + f.cat, q) > 0;
  }

  const posts     = $derived(query ? POSTS.filter((p)   => matchPost(p, query))     : []);
  const proposals = $derived(query ? PROPOSALS.filter((p) => matchProposal(p, query)) : []);
  const forums    = $derived(query ? FORUM_SEEDS.filter((f) => matchForum(f, query)) : []);
  const totalHits = $derived(posts.length + proposals.length + forums.length);

  let draftQuery = $state(query);
  let searchTimer = null;

  $effect(() => {
    draftQuery = query;
  });

  function onInput() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      const q = draftQuery.trim();
      const url = q ? `/search?q=${encodeURIComponent(q)}` : '/search';
      goto(url, { replaceState: true, keepFocus: true });
    }, 240);
  }

  function onSubmit(e) {
    e.preventDefault();
    clearTimeout(searchTimer);
    const q = draftQuery.trim();
    goto(q ? `/search?q=${encodeURIComponent(q)}` : '/search', { replaceState: true });
  }
</script>

<svelte:head>
  <title>{query ? `"${query}" — Search` : 'Search'} · Cafreso</title>
  <meta name="description" content="Search the Cafreso ecosystem — Dev Log posts, forum threads, and governance proposals — or ask AI Search to query the CafresoDAO vault and the web." />
</svelte:head>

<div style="max-width: 800px; margin: 0 auto; padding: 36px 18px 80px;">

  <!-- Search bar -->
  <form onsubmit={onSubmit} style="margin-bottom: 32px;">
    <div style="position: relative;">
      <Icon name="magnifying-glass" size={18} style="
        position: absolute; left: 16px; top: 50%; transform: translateY(-50%);
        color: hsl(215 16% 47%); pointer-events: none;
      " />
      <input
        bind:this={inputEl}
        bind:value={draftQuery}
        oninput={onInput}
        type="search"
        placeholder="Search posts, proposals, discussions…"
        aria-label="Search posts, proposals, discussions"
        autofocus
        style="
          width: 100%; padding: 14px 48px 14px 46px; border-radius: 14px;
          border: 1.5px solid hsl(26 30% 82%); font-size: 16px; font-family: inherit;
          background: white; color: hsl(222 47% 11%); outline: none;
          box-shadow: 0 2px 12px -4px hsl(24 20% 20% / 0.1);
          box-sizing: border-box;
          transition: border-color 0.15s, box-shadow 0.15s;
        "
        onfocus={(e) => {
          e.currentTarget.style.borderColor = 'hsl(32 72% 50%)';
          e.currentTarget.style.boxShadow = '0 0 0 3px hsl(32 72% 50% / 0.15), 0 2px 12px -4px hsl(24 20% 20% / 0.1)';
        }}
        onblur={(e) => {
          e.currentTarget.style.borderColor = 'hsl(26 30% 82%)';
          e.currentTarget.style.boxShadow = '0 2px 12px -4px hsl(24 20% 20% / 0.1)';
        }}
      />
      {#if draftQuery}
        <button
          type="button"
          onclick={() => { draftQuery = ''; goto('/search', { replaceState: true }); inputEl?.focus(); }}
          aria-label="Clear search"
          style="
            position: absolute; right: 14px; top: 50%; transform: translateY(-50%);
            background: hsl(215 16% 80%); border: none; border-radius: 50%;
            width: 22px; height: 22px; cursor: pointer; display: flex;
            align-items: center; justify-content: center;
          "
        >
          <Icon name="x" size={12} style="color: white;" />
        </button>
      {/if}
    </div>
    {#if query}
      <div style="font-size: 12px; color: hsl(215 16% 47%); margin-top: 8px; text-align: center;">
        {#if totalHits === 0}
          No results for <strong>"{query}"</strong>
        {:else}
          {totalHits} result{totalHits !== 1 ? 's' : ''} for <strong>"{query}"</strong>
        {/if}
      </div>
    {/if}
  </form>

  {#if !query}
    <!-- AI Search callout -->
    <button
      type="button"
      onclick={() => aiSearchOpen.set(true)}
      style="
        display: flex; align-items: center; gap: 14px;
        width: 100%; padding: 16px 20px; margin-bottom: 24px;
        border-radius: 14px; cursor: pointer; text-align: left;
        background: linear-gradient(135deg, hsl(260 70% 97%), hsl(26 45% 97%));
        border: 1.5px solid hsl(260 50% 85%);
        box-shadow: 0 4px 16px -8px hsl(260 70% 60% / 0.2);
        transition: border-color .15s, box-shadow .15s;
        font-family: inherit;
      "
      onmouseenter={(e) => { e.currentTarget.style.borderColor = 'hsl(260 60% 70%)'; e.currentTarget.style.boxShadow = '0 6px 24px -8px hsl(260 70% 60% / 0.3)'; }}
      onmouseleave={(e) => { e.currentTarget.style.borderColor = 'hsl(260 50% 85%)'; e.currentTarget.style.boxShadow = '0 4px 16px -8px hsl(260 70% 60% / 0.2)'; }}
    >
      <span style="
        width: 44px; height: 44px; border-radius: 12px; flex-shrink: 0;
        background: hsl(260 70% 93%);
        display: flex; align-items: center; justify-content: center;
      ">
        <Icon name="brain" size={22} style="color: hsl(260 70% 50%);" />
      </span>
      <div style="flex: 1; min-width: 0;">
        <div style="font-size: 14px; font-weight: 700; color: hsl(222 47% 11%); margin-bottom: 2px;">
          Try AI Search
        </div>
        <div style="font-size: 12.5px; color: hsl(215 16% 47%);">
          Ask anything — searches the CafresoDAO vault, then the web if needed
        </div>
      </div>
      <Icon name="arrow-right" size={16} style="color: hsl(260 60% 60%); flex-shrink: 0;" />
    </button>

    <!-- Empty state / suggestions -->
    <div style="text-align: center; padding: 20px 0 40px;">
      <Icon name="magnifying-glass" size={32} style="opacity: 0.2; display: block; margin: 0 auto 12px; color: hsl(222 47% 11%);" />
      <div style="font-size: 15px; font-weight: 600; color: hsl(222 47% 11%); margin-bottom: 6px;">Search the Cafreso ecosystem</div>
      <div style="font-size: 13px; color: hsl(215 16% 47%);">Dev Log posts · Forum threads · Governance proposals</div>
    </div>
    <!-- Quick links -->
    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px;">
      {#each [
        { href: '/blog',       icon: 'article',       label: 'Dev Log',   desc: 'Read the latest updates', color: 'hsl(32 72% 50%)' },
        { href: '/forums',     icon: 'chats-circle',  label: 'Forums',    desc: 'Join the discussion',     color: 'hsl(112 43% 40%)' },
        { href: '/governance', icon: 'gavel',         label: 'Governance',desc: 'Browse proposals',        color: 'hsl(260 70% 62%)' },
      ] as link}
        <a href={link.href} style="
          display: block; border-radius: 12px; padding: 16px;
          border: 1px solid hsl(26 30% 88%); text-decoration: none;
          background: white; text-align: center;
          transition: border-color 0.15s, box-shadow 0.15s;
        "
          onmouseenter={(e) => { e.currentTarget.style.borderColor = link.color; e.currentTarget.style.boxShadow = `0 4px 16px -6px ${link.color}44`; }}
          onmouseleave={(e) => { e.currentTarget.style.borderColor = 'hsl(26 30% 88%)'; e.currentTarget.style.boxShadow = 'none'; }}
        >
          <Icon name={link.icon} size={22} style="color: {link.color}; display: block; margin: 0 auto 8px;" />
          <div style="font-size: 13px; font-weight: 700; color: hsl(222 47% 11%);">{link.label}</div>
          <div style="font-size: 11px; color: hsl(215 16% 47%); margin-top: 2px;">{link.desc}</div>
        </a>
      {/each}
    </div>
  {:else}
    <!-- Results -->
    <div style="display: flex; flex-direction: column; gap: 24px;">

      <!-- Blog posts -->
      {#if posts.length > 0}
        <section>
          <div style="
            display: flex; align-items: center; gap: 8px; margin-bottom: 12px;
            padding-bottom: 8px; border-bottom: 1px solid hsl(26 30% 90%);
          ">
            <Icon name="article" size={15} style="color: hsl(32 72% 50%);" />
            <span style="font-size: 11.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: hsl(32 72% 44%);">Dev Log</span>
            <span style="font-size: 11px; color: hsl(215 16% 56%);">{posts.length} result{posts.length !== 1 ? 's' : ''}</span>
          </div>
          <div style="display: flex; flex-direction: column; gap: 8px;">
            {#each posts as p (p.slug)}
              <a href="/blog/{p.slug}" style="
                display: flex; gap: 12px; padding: 14px 16px;
                border-radius: 12px; border: 1px solid hsl(26 30% 88%);
                background: white; text-decoration: none;
                transition: border-color 0.12s;
              "
                onmouseenter={(e) => (e.currentTarget.style.borderColor = 'hsl(32 72% 70%)')}
                onmouseleave={(e) => (e.currentTarget.style.borderColor = 'hsl(26 30% 88%)')}
              >
                <div style="
                  width: 44px; height: 44px; border-radius: 8px; flex-shrink: 0; overflow: hidden;
                  background: linear-gradient(180deg, hsl(26 45% 96%), hsl(26 40% 88%));
                  display: flex; align-items: center; justify-content: center;
                ">
                  <Icon name="article" size={18} style="color: hsl(32 72% 50%); opacity: 0.6;" />
                </div>
                <div style="flex: 1; min-width: 0;">
                  <div style="font-size: 14.5px; font-weight: 700; color: hsl(222 47% 11%); margin-bottom: 3px; line-height: 1.25;">{p.title}</div>
                  <div style="font-size: 12.5px; color: hsl(215 16% 47%); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{p.excerpt}</div>
                  <div style="font-size: 10.5px; color: hsl(215 16% 56%); margin-top: 4px;">{fmtDate(p.date)} · {p.readMin} min read</div>
                </div>
                <Icon name="arrow-right" size={14} style="color: hsl(215 16% 56%); flex-shrink: 0; margin-top: 14px;" />
              </a>
            {/each}
          </div>
        </section>
      {/if}

      <!-- Governance proposals -->
      {#if proposals.length > 0}
        <section>
          <div style="
            display: flex; align-items: center; gap: 8px; margin-bottom: 12px;
            padding-bottom: 8px; border-bottom: 1px solid hsl(26 30% 90%);
          ">
            <Icon name="gavel" size={15} style="color: hsl(260 70% 62%);" />
            <span style="font-size: 11.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: hsl(260 52% 44%);">Governance</span>
            <span style="font-size: 11px; color: hsl(215 16% 56%);">{proposals.length} result{proposals.length !== 1 ? 's' : ''}</span>
          </div>
          <div style="display: flex; flex-direction: column; gap: 8px;">
            {#each proposals as p (p.id)}
              {@const pt = proposalType(p.type)}
              {@const ps = proposalStatus(p.status)}
              <a href="/governance/{p.id}" style="
                display: flex; gap: 12px; padding: 14px 16px;
                border-radius: 12px; border: 1px solid hsl(26 30% 88%);
                background: white; text-decoration: none;
                transition: border-color 0.12s;
              "
                onmouseenter={(e) => (e.currentTarget.style.borderColor = 'hsl(260 50% 70%)')}
                onmouseleave={(e) => (e.currentTarget.style.borderColor = 'hsl(26 30% 88%)')}
              >
                <div style="
                  width: 44px; height: 44px; border-radius: 8px; flex-shrink: 0;
                  background: {pt.color}18; border: 1px solid {pt.color}33;
                  display: flex; align-items: center; justify-content: center;
                ">
                  <Icon name={pt.icon} size={18} style="color: {pt.color};" />
                </div>
                <div style="flex: 1; min-width: 0;">
                  <div style="display: flex; gap: 6px; align-items: center; margin-bottom: 3px; flex-wrap: wrap;">
                    <span style="font-size: 9.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: {ps.color}; background: {ps.bg}; border-radius: 4px; padding: 1px 5px;">{ps.label}</span>
                  </div>
                  <div style="font-size: 14.5px; font-weight: 700; color: hsl(222 47% 11%); margin-bottom: 3px; line-height: 1.25;">{p.title}</div>
                  <div style="font-size: 12.5px; color: hsl(215 16% 47%); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{p.summary}</div>
                </div>
                <Icon name="arrow-right" size={14} style="color: hsl(215 16% 56%); flex-shrink: 0; margin-top: 14px;" />
              </a>
            {/each}
          </div>
        </section>
      {/if}

      <!-- Forums -->
      {#if forums.length > 0}
        <section>
          <div style="
            display: flex; align-items: center; gap: 8px; margin-bottom: 12px;
            padding-bottom: 8px; border-bottom: 1px solid hsl(26 30% 90%);
          ">
            <Icon name="chats-circle" size={15} style="color: hsl(112 43% 40%);" />
            <span style="font-size: 11.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: hsl(112 43% 30%);">Forums</span>
            <span style="font-size: 11px; color: hsl(215 16% 56%);">{forums.length} result{forums.length !== 1 ? 's' : ''}</span>
          </div>
          <div style="display: flex; flex-direction: column; gap: 8px;">
            {#each forums as f (f.slug)}
              <a href="/forums/{f.slug}" style="
                display: flex; gap: 12px; padding: 14px 16px;
                border-radius: 12px; border: 1px solid hsl(26 30% 88%);
                background: white; text-decoration: none;
                transition: border-color 0.12s;
              "
                onmouseenter={(e) => (e.currentTarget.style.borderColor = 'hsl(112 40% 60%)')}
                onmouseleave={(e) => (e.currentTarget.style.borderColor = 'hsl(26 30% 88%)')}
              >
                <div style="
                  width: 44px; height: 44px; border-radius: 8px; flex-shrink: 0;
                  background: hsl(112 40% 93%); display: flex; align-items: center; justify-content: center;
                ">
                  <Icon name="chats-circle" size={18} style="color: hsl(112 43% 40%);" />
                </div>
                <div style="flex: 1; min-width: 0;">
                  <div style="font-size: 14.5px; font-weight: 700; color: hsl(222 47% 11%); margin-bottom: 3px; line-height: 1.25;">{f.title}</div>
                  <div style="font-size: 12.5px; color: hsl(215 16% 47%); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{f.excerpt}</div>
                </div>
                <Icon name="arrow-right" size={14} style="color: hsl(215 16% 56%); flex-shrink: 0; margin-top: 14px;" />
              </a>
            {/each}
          </div>
        </section>
      {/if}

      {#if totalHits === 0}
        <div style="text-align: center; padding: 36px 20px 20px;">
          <Icon name="magnifying-glass" size={28} style="opacity: 0.2; display: block; margin: 0 auto 10px; color: hsl(222 47% 11%);" />
          <div style="font-size: 15px; font-weight: 600; color: hsl(222 47% 11%); margin-bottom: 6px;">No local results found</div>
          <div style="font-size: 13px; color: hsl(215 16% 47%); margin-bottom: 20px;">Try AI Search to query the vault and the web.</div>
          <button
            type="button"
            onclick={() => aiSearchOpen.set(true)}
            style="
              display: inline-flex; align-items: center; gap: 8px;
              padding: 10px 18px; border-radius: 10px;
              background: hsl(260 70% 93%); border: 1px solid hsl(260 50% 82%);
              font-family: inherit; font-size: 13px; font-weight: 600;
              color: hsl(260 60% 38%); cursor: pointer;
              transition: background .15s;
            "
          >
            <Icon name="brain" size={15} />
            Try AI Search
          </button>
        </div>
      {/if}
    </div>
  {/if}
</div>
