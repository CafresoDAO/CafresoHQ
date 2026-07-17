<svelte:options runes={true} />

<script>
  import { page } from '$app/stores';
  import Icon from '$lib/components/Icon.svelte';
  import Avatar from '$lib/components/Avatar.svelte';
  import AuditTrail from '$lib/components/AuditTrail.svelte';
  import { POSTS } from '$lib/data/blog.js';
  import { PROPOSALS, proposalType, proposalStatus } from '$lib/data/governance.js';
  import { isAuthenticated, principalText } from '$lib/stores/auth.js';

  // The id segment is either a full principal or a display name slug.
  const id = $derived($page.params.id);

  // Try to match against known post authors.
  const authoredPosts = $derived(
    POSTS.filter((p) =>
      p.author?.name?.toLowerCase().replace(/\s+/g, '-') === id.toLowerCase() ||
      p.canister === id
    )
  );

  // Match governance proposals by proposer name slug.
  const proposedBy = $derived(
    PROPOSALS.filter((p) =>
      p.proposedBy?.name?.toLowerCase().replace(/\s+/g, '-') === id.toLowerCase()
    )
  );

  // Determine a display name from what we can find.
  const displayName = $derived(
    authoredPosts[0]?.author?.name ||
    proposedBy[0]?.proposedBy?.name ||
    id
  );
  const hue = $derived(authoredPosts[0]?.author?.hue ?? 45);

  // Check if this is the logged-in user's own principal.
  const isOwnProfile = $derived($principalText === id);

  // Seed audit events for demo purposes — replaced by canister fetch when live.
  const NOW_SEED = 1746662400000;
  const seedEvents = $derived([
    ...authoredPosts.map((p, i) => ({
      id: `post-${p.slug}`,
      kind: 'post',
      title: `Authored: "${p.title}"`,
      sub: `Dev Log post published`,
      block: p.block || (4_218_000 - i * 2000),
      ts: NOW_SEED - (i + 2) * 86_400_000,
      url: `/blog/${p.slug}`,
      amount: null,
    })),
    ...proposedBy.map((p, i) => ({
      id: `proposal-${p.id}`,
      kind: 'vote',
      title: `Proposed: "${p.title.slice(0, 40)}…"`,
      sub: `Governance proposal submitted`,
      block: p.block,
      ts: NOW_SEED - (i + 6) * 86_400_000,
      url: `/governance/${p.id}`,
      amount: null,
    })),
  ].sort((a, b) => b.ts - a.ts));

  const hasActivity = $derived(seedEvents.length > 0 || authoredPosts.length > 0 || proposedBy.length > 0);
</script>

<svelte:head>
  <title>{displayName} · Profile · Cafreso</title>
</svelte:head>

<div style="max-width: 760px; margin: 0 auto; padding: 36px 18px 80px;">

  <!-- Back -->
  <a href="/forums" style="
    display: inline-flex; align-items: center; gap: 5px;
    font-size: 12.5px; color: hsl(var(--pg-fg-muted)); text-decoration: none; margin-bottom: 20px;
  ">
    <Icon name="caret-left" size={13} /> Community
  </a>

  <!-- Profile card — background/border are deliberately per-user (tinted by
       {hue}, an Avatar-derived accent), so they stay inline; the .dark
       variant just pulls lightness down to match the rest of the card. -->
  <div class="profile-hero" style="
    --hue: {hue};
    border-radius: 16px; padding: 24px; margin-bottom: 24px;
    background: linear-gradient(135deg, hsl({hue} 55% 96%), hsl({hue} 45% 90%));
    border: 1px solid hsl({hue} 40% 80%);
  ">
    <div style="display: flex; align-items: flex-start; gap: 16px; flex-wrap: wrap;">
      <Avatar name={displayName} {hue} size={56} />
      <div style="flex: 1; min-width: 0;">
        <h1 style="font-size: 22px; font-weight: 800; color: hsl(var(--pg-fg)); margin: 0 0 4px; letter-spacing: -0.02em;">
          {displayName}
        </h1>
        <div style="font-family: ui-monospace, monospace; font-size: 11px; color: hsl({hue} 40% 35%); word-break: break-all; margin-bottom: 10px;">
          {id.length > 20 ? id : `Cafreso community member`}
        </div>
        <div style="display: flex; gap: 16px; flex-wrap: wrap;">
          <span style="font-size: 12.5px; color: hsl(var(--pg-fg-muted)); display: inline-flex; align-items: center; gap: 4px;">
            <Icon name="article" size={13} style="color: hsl(32 72% 50%);" /> {authoredPosts.length} post{authoredPosts.length !== 1 ? 's' : ''}
          </span>
          <span style="font-size: 12.5px; color: hsl(var(--pg-fg-muted)); display: inline-flex; align-items: center; gap: 4px;">
            <Icon name="gavel" size={13} style="color: hsl(var(--pg-accent-purple));" /> {proposedBy.length} proposal{proposedBy.length !== 1 ? 's' : ''}
          </span>
        </div>
      </div>
      {#if isOwnProfile}
        <a href="/profile" style="
          display: inline-flex; align-items: center; gap: 5px;
          padding: 7px 12px; border-radius: 8px; font-size: 12px; font-weight: 600;
          background: hsl(var(--pg-solid)); color: hsl(var(--pg-solid-fg)); text-decoration: none;
        ">
          <Icon name="user-circle" size={13} /> My profile
        </a>
      {/if}
    </div>

    <!-- On-chain verification note -->
    <div class="profile-hero-note" style="
      margin-top: 16px; padding: 10px 14px; border-radius: 10px;
      background: hsl(0 0% 100% / 0.55); border: 1px dashed hsl({hue} 35% 60%);
      display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    ">
      <Icon name="shield-check" size={14} style="color: hsl(112 43% 40%); flex-shrink: 0;" />
      <span style="font-size: 11.5px; color: hsl({hue} 35% 28%); line-height: 1.4;">
        Public activity is verified on the Internet Computer. Full canister-backed profiles coming with the SNS launch.
        <a href="https://app.sneeddao.com" target="_blank" rel="noopener" style="color: hsl(var(--pg-accent-purple)); font-weight: 600;">Verify on SneedDAO →</a>
      </span>
    </div>
  </div>

  {#if !hasActivity}
    <!-- No data state -->
    <div style="
      text-align: center; padding: 48px 24px;
      border-radius: 14px; border: 1.5px dashed hsl(var(--pg-border));
      background: hsl(var(--pg-surface));
    ">
      <Icon name="user-circle" size={32} style="opacity: 0.2; display: block; margin: 0 auto 12px; color: hsl(var(--pg-fg));" />
      <div style="font-size: 15px; font-weight: 600; color: hsl(var(--pg-fg)); margin-bottom: 6px;">No public activity found</div>
      <div style="font-size: 13px; color: hsl(var(--pg-fg-muted)); margin-bottom: 20px; max-width: 340px; margin-left: auto; margin-right: auto; line-height: 1.55;">
        On-chain activity for this principal will appear here once the canister audit log is live.
      </div>
    </div>
  {:else}
    <!-- Authored posts -->
    {#if authoredPosts.length > 0}
      <div style="margin-bottom: 24px;">
        <h2 style="font-size: 14px; font-weight: 700; color: hsl(var(--pg-fg-muted)); text-transform: uppercase; letter-spacing: 0.06em; margin: 0 0 12px;">
          Dev Log posts
        </h2>
        <div style="display: flex; flex-direction: column; gap: 8px;">
          {#each authoredPosts as p (p.slug)}
            <a href="/blog/{p.slug}" style="
              display: flex; align-items: center; gap: 12px; padding: 12px 16px;
              border-radius: 12px; border: 1px solid hsl(var(--pg-border));
              background: hsl(var(--pg-elevated)); text-decoration: none;
            ">
              <Icon name="article" size={16} style="color: hsl(32 72% 50%); flex-shrink: 0;" />
              <div style="flex: 1; min-width: 0;">
                <div style="font-size: 14px; font-weight: 600; color: hsl(var(--pg-fg));">{p.title}</div>
                <div style="font-size: 11px; color: hsl(var(--pg-fg-muted)); margin-top: 2px;">{p.date} · {p.readMin} min read</div>
              </div>
              <Icon name="arrow-right" size={13} style="color: hsl(var(--pg-fg-subtle)); flex-shrink: 0;" />
            </a>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Governance proposals -->
    {#if proposedBy.length > 0}
      <div style="margin-bottom: 24px;">
        <h2 style="font-size: 14px; font-weight: 700; color: hsl(var(--pg-fg-muted)); text-transform: uppercase; letter-spacing: 0.06em; margin: 0 0 12px;">
          Governance proposals
        </h2>
        <div style="display: flex; flex-direction: column; gap: 8px;">
          {#each proposedBy as p (p.id)}
            {@const ps = proposalStatus(p.status)}
            <a href="/governance/{p.id}" style="
              display: flex; align-items: center; gap: 12px; padding: 12px 16px;
              border-radius: 12px; border: 1px solid hsl(var(--pg-border));
              background: hsl(var(--pg-elevated)); text-decoration: none;
            ">
              <Icon name="gavel" size={16} style="color: hsl(260 70% 62%); flex-shrink: 0;" />
              <div style="flex: 1; min-width: 0;">
                <div style="font-size: 14px; font-weight: 600; color: hsl(var(--pg-fg));">{p.title}</div>
                <div style="font-size: 11px; margin-top: 2px;">
                  <span style="color: {ps.color}; background: {ps.bg}; border-radius: 4px; padding: 1px 5px; font-weight: 600; font-size: 10px;">{ps.label}</span>
                </div>
              </div>
              <Icon name="arrow-right" size={13} style="color: hsl(var(--pg-fg-subtle)); flex-shrink: 0;" />
            </a>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Audit trail -->
    {#if seedEvents.length > 0}
      <div style="
        border-radius: 16px; padding: 20px; margin-bottom: 16px;
        background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border));
      ">
        <AuditTrail
          principalId={id.length > 20 ? `${id.slice(0, 10)}…${id.slice(-5)}` : id}
          events={seedEvents}
          compact
        />
      </div>
    {/if}
  {/if}

  <!-- SneedDAO link teaser -->
  <div style="
    border-radius: 12px; padding: 14px 16px; margin-top: 8px;
    background: hsl(var(--pg-accent-purple-bg)); border: 1px solid hsl(var(--pg-accent-purple-border));
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  ">
    <Icon name="link-simple" size={15} style="color: hsl(var(--pg-accent-purple)); flex-shrink: 0;" />
    <span style="font-size: 12.5px; color: hsl(var(--pg-fg-muted)); flex: 1; line-height: 1.5;">
      Link your SneedDAO principal to display verified neuron voting power and cross-DAO governance history on this profile.
    </span>
    <span style="
      font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
      background: hsl(var(--pg-accent-purple) / 0.16); color: hsl(var(--pg-accent-purple)); border-radius: 4px; padding: 2px 7px; flex-shrink: 0;
    ">Coming soon</span>
  </div>
</div>

<style>
  /* The hue-tinted hero card and its verification note are pastel-light by
     construction ({hue} 55%/96% lightness) with no dark equivalent — pull
     lightness down for .dark instead of leaving them stuck light always. */
  :global(.dark) .profile-hero {
    background: linear-gradient(135deg, hsl(var(--hue) 35% 22%), hsl(var(--hue) 30% 16%)) !important;
    border-color: hsl(var(--hue) 30% 34%) !important;
  }
  :global(.dark) .profile-hero-note {
    background: hsl(0 0% 100% / 0.06) !important;
    border-color: hsl(var(--hue) 25% 42%) !important;
  }
</style>
