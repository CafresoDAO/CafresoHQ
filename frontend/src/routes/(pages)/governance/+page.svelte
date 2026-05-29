<svelte:options runes={true} />

<script>
  import Icon from '$lib/components/Icon.svelte';
  import Avatar from '$lib/components/Avatar.svelte';
  import {
    PROPOSALS, PROPOSAL_TYPES, PROPOSAL_STATUSES,
    proposalType, proposalStatus, fmtDeadline, votedPct, yesPct,
  } from '$lib/data/governance.js';
  import { isAuthenticated } from '$lib/stores/auth.js';

  const STATUS_KEYS = ['open', 'passed', 'rejected', 'pending', 'executed'];
  const TYPE_KEYS   = Object.keys(PROPOSAL_TYPES);

  let filterStatus = $state('all');
  let filterType   = $state('all');
  let searchQuery  = $state('');

  const filtered = $derived(
    PROPOSALS.filter((p) => {
      if (filterStatus !== 'all' && p.status !== filterStatus) return false;
      if (filterType   !== 'all' && p.type   !== filterType)   return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        if (!p.title.toLowerCase().includes(q) && !p.summary.toLowerCase().includes(q)) return false;
      }
      return true;
    })
  );

  const openCount = $derived(PROPOSALS.filter((p) => p.status === 'open').length);
</script>

<svelte:head>
  <title>Governance · Cafreso</title>
</svelte:head>

<!-- DAO Hero Banner -->
<div style="
  background: linear-gradient(160deg, hsl(262 55% 14%), hsl(262 45% 22%));
  border-bottom: 1px solid hsl(260 60% 30%);
  padding: 48px 18px 42px;
">
  <div style="max-width: 1100px; margin: 0 auto;">
    <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; flex-wrap: wrap;">
      <div>
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 16px;">
          <span style="
            display: inline-flex; align-items: center; gap: 5px;
            font-size: 10px; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase;
            background: hsl(260 70% 62% / 0.25); color: hsl(260 90% 80%);
            border: 1px solid hsl(260 60% 44%); border-radius: 6px; padding: 3px 9px;
          ">
            <span style="width: 6px; height: 6px; border-radius: 50%; background: hsl(260 90% 75%); animation: pulse 2s infinite;"></span>
            BETA
          </span>
          <span style="font-size: 10px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: hsl(260 25% 68%);">
            DAO not yet live · simulated votes
          </span>
        </div>
        <h1 style="font-size: clamp(28px, 5vw, 44px); font-weight: 800; letter-spacing: -0.025em; color: hsl(260 40% 96%); margin: 0 0 12px; line-height: 1.05;">
          Cafreso Governance
        </h1>
        <p style="font-size: 16px; line-height: 1.6; color: hsl(260 25% 76%); max-width: 540px; margin: 0;">
          Shape the future of Cafreso. Browse proposals, explore the context behind each vote,
          and engage with the community before the SNS DAO goes live.
        </p>
      </div>

      <!-- Stats strip -->
      <div style="display: flex; gap: 20px; flex-wrap: wrap;">
        {#each [
          { label: 'Total proposals', value: PROPOSALS.length },
          { label: 'Open for vote',   value: openCount, accent: true },
          { label: 'Total supply',    value: '14.8M $CF' },
          { label: 'Quorum needed',   value: '3%' },
        ] as s}
          <div style="text-align: right;">
            <div style="font-size: 26px; font-weight: 800; color: {s.accent ? 'hsl(260 90% 75%)' : 'hsl(260 40% 96%)'}; letter-spacing: -0.02em; line-height: 1;">
              {s.value}
            </div>
            <div style="font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.08em; color: hsl(260 25% 68%); margin-top: 2px;">
              {s.label}
            </div>
          </div>
        {/each}
      </div>
    </div>

    <!-- SneedDAO integration note -->
    <div style="
      margin-top: 28px; padding: 12px 16px;
      background: hsl(260 40% 20% / 0.7); border: 1px solid hsl(260 50% 38%); border-radius: 10px;
      display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    ">
      <Icon name="link-simple" size={15} style="color: hsl(260 90% 75%); flex-shrink: 0;" />
      <span style="font-size: 12.5px; color: hsl(260 25% 76%);">
        Once the Cafreso SNS DAO is live, proposals will be verifiable on
        <a href="https://app.sneeddao.com" target="_blank" rel="noopener" style="color: hsl(260 90% 80%); font-weight: 600;">SneedDAO</a>
        — the community-built SNS inspector for all ICP DAOs.
        Link your SneedDAO principal to carry your neuron voting power here.
      </span>
      <span style="
        font-size: 10px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
        background: hsl(260 50% 38%); color: hsl(260 90% 80%); padding: 2px 8px; border-radius: 4px; flex-shrink: 0;
      ">Coming soon</span>
    </div>
  </div>
</div>

<!-- Main content -->
<div style="max-width: 1100px; margin: 0 auto; padding: 32px 18px 80px;">

  <!-- Filters row -->
  <div style="display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-bottom: 24px;">
    <!-- Search -->
    <div style="position: relative; flex: 1; min-width: 200px; max-width: 320px;">
      <Icon name="magnifying-glass" size={14} style="position: absolute; left: 11px; top: 50%; transform: translateY(-50%); color: hsl(215 16% 47%);" />
      <input
        type="search"
        bind:value={searchQuery}
        placeholder="Search proposals…"
        style="
          width: 100%; padding: 8px 12px 8px 32px; border-radius: 10px;
          border: 1px solid hsl(26 30% 85%); font-size: 13px; font-family: inherit;
          background: white; color: hsl(222 47% 11%); outline: none;
          box-sizing: border-box;
        "
      />
    </div>

    <!-- Status filter -->
    <div style="display: flex; gap: 6px; flex-wrap: wrap;">
      {#each ['all', ...STATUS_KEYS] as s}
        {@const st = s !== 'all' ? proposalStatus(s) : null}
        <button
          type="button"
          onclick={() => (filterStatus = s)}
          style="
            padding: 6px 12px; border-radius: 8px; font-size: 12px; font-weight: 600;
            font-family: inherit; cursor: pointer;
            background: {filterStatus === s ? (st?.bg || 'hsl(262 55% 14%)') : 'white'};
            color: {filterStatus === s ? (st?.color || 'hsl(260 40% 96%)') : 'hsl(215 16% 47%)'};
            border: 1px solid {filterStatus === s ? (st?.color || 'hsl(260 60% 30%)') : 'hsl(26 30% 85%)'};
          "
        >{s === 'all' ? 'All' : PROPOSAL_STATUSES[s]?.label}</button>
      {/each}
    </div>
  </div>

  <!-- Proposal cards -->
  {#if filtered.length === 0}
    <div style="text-align: center; padding: 60px 20px; color: hsl(215 16% 47%); font-size: 14px;">
      <Icon name="funnel" size={28} style="opacity: 0.35; display: block; margin: 0 auto 12px;" />
      No proposals match your filters.
    </div>
  {:else}
    <div style="display: flex; flex-direction: column; gap: 14px;">
      {#each filtered as p (p.id)}
        {@const pt = proposalType(p.type)}
        {@const ps = proposalStatus(p.status)}
        {@const yp = yesPct(p.votes)}
        {@const vp = votedPct(p.votes)}
        <a
          href="/governance/{p.id}"
          style="
            display: block; border-radius: 14px; text-decoration: none;
            background: white; border: 1px solid hsl(26 30% 88%);
            padding: 20px 24px;
            transition: box-shadow 0.15s, border-color 0.15s;
          "
          onmouseenter={(e) => {
            e.currentTarget.style.boxShadow = '0 4px 20px -8px hsl(262 40% 30% / 0.25)';
            e.currentTarget.style.borderColor = 'hsl(260 50% 70%)';
          }}
          onmouseleave={(e) => {
            e.currentTarget.style.boxShadow = 'none';
            e.currentTarget.style.borderColor = 'hsl(26 30% 88%)';
          }}
        >
          <div style="display: flex; align-items: flex-start; gap: 14px; flex-wrap: wrap;">
            <!-- Type icon -->
            <div style="
              width: 40px; height: 40px; border-radius: 10px; flex-shrink: 0;
              background: {pt.color}18; border: 1px solid {pt.color}44;
              display: flex; align-items: center; justify-content: center; margin-top: 2px;
            ">
              <Icon name={pt.icon} size={18} style="color: {pt.color};" />
            </div>

            <!-- Content -->
            <div style="flex: 1; min-width: 0;">
              <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px;">
                <!-- Type badge -->
                <span style="
                  font-size: 10px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
                  color: {pt.color}; background: {pt.color}15; border-radius: 5px; padding: 2px 7px;
                ">{pt.label}</span>
                <!-- Status badge -->
                <span style="
                  font-size: 10px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
                  color: {ps.color}; background: {ps.bg}; border-radius: 5px; padding: 2px 7px;
                ">{ps.label}</span>
                <span style="font-size: 10.5px; font-family: ui-monospace, monospace; color: hsl(215 16% 56%);">{p.id}</span>
              </div>

              <h2 style="font-size: 17px; font-weight: 700; color: hsl(222 47% 11%); margin: 0 0 5px; letter-spacing: -0.01em; line-height: 1.25; text-wrap: pretty;">
                {p.title}
              </h2>
              <p style="font-size: 13px; color: hsl(215 16% 40%); margin: 0 0 12px; line-height: 1.5; max-width: 65ch;">
                {p.summary}
              </p>

              <!-- Vote bar (show for non-pending) -->
              {#if p.status !== 'pending' && (p.votes.yes + p.votes.no + p.votes.abstain > 0)}
                <div style="margin-bottom: 10px;">
                  <div style="
                    height: 6px; border-radius: 999px; overflow: hidden;
                    background: hsl(0 62% 92%);
                    display: flex; gap: 1px;
                  ">
                    <div style="width: {yp}%; background: hsl(112 43% 45%); border-radius: 999px; transition: width 0.4s;"></div>
                  </div>
                  <div style="display: flex; justify-content: space-between; margin-top: 4px; font-size: 10.5px; color: hsl(215 16% 47%);">
                    <span><span style="color: hsl(112 43% 40%); font-weight: 600;">{yp}% YES</span> · {vp}% participation</span>
                    <span>{p.votes.yes.toLocaleString()} / {p.votes.total.toLocaleString()} $CF</span>
                  </div>
                </div>
              {/if}
            </div>

            <!-- Right meta -->
            <div style="text-align: right; flex-shrink: 0; min-width: 120px;">
              {#if p.status === 'open' || p.status === 'pending'}
                <div style="font-size: 12px; font-weight: 600; color: hsl(112 43% 35%); margin-bottom: 4px;">
                  {fmtDeadline(p.deadline)}
                </div>
              {/if}
              <div style="display: flex; align-items: center; gap: 5px; justify-content: flex-end;">
                <Avatar name={p.proposedBy.name} hue={p.proposedBy.hue} size={20} />
                <span style="font-size: 11px; color: hsl(215 16% 47%);">{p.proposedBy.name}</span>
              </div>
              {#if p.block}
                <div style="font-size: 10px; font-family: ui-monospace, monospace; color: hsl(215 16% 56%); margin-top: 3px;">
                  block #{p.block.toLocaleString()}
                </div>
              {/if}
              <div style="
                margin-top: 10px; display: inline-flex; align-items: center; gap: 4px;
                font-size: 11.5px; font-weight: 600; color: hsl(260 52% 44%);
              ">
                View proposal <Icon name="arrow-right" size={12} />
              </div>
            </div>
          </div>
        </a>
      {/each}
    </div>
  {/if}
</div>

<style>
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.4; }
  }
</style>
