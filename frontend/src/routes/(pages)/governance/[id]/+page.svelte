<svelte:options runes={true} />

<style>
  .proposal-layout {
    display: flex;
    gap: 28px;
    align-items: flex-start;
    flex-wrap: wrap;
  }
  .proposal-main {
    flex: 1;
    min-width: 0;
  }
  .proposal-sidebar {
    width: 240px;
    flex-shrink: 0;
  }
  .related-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  @media (max-width: 600px) {
    .proposal-main {
      width: 100%;
      flex: none;
    }
    .proposal-sidebar {
      width: 100%;
      flex-shrink: 1;
      order: -1;
    }
    .related-grid {
      grid-template-columns: 1fr;
    }
  }
</style>

<script>
  import { page } from '$app/stores';
  import Icon from '$lib/components/Icon.svelte';
  import Avatar from '$lib/components/Avatar.svelte';
  import PostRenderer from '$lib/components/PostRenderer.svelte';
  import { getTheme } from '$lib/themes.js';
  import {
    getProposal, proposalType, proposalStatus,
    fmtDeadline, votedPct, yesPct, PROPOSALS,
  } from '$lib/data/governance.js';
  import { isAuthenticated } from '$lib/stores/auth.js';
  import { addNotification } from '$lib/stores/notifications.js';

  const id = $derived($page.params.id);
  const proposal = $derived(getProposal(id));
  const pt = $derived(proposal ? proposalType(proposal.type) : null);
  const ps = $derived(proposal ? proposalStatus(proposal.status) : null);
  const yp = $derived(proposal ? yesPct(proposal.votes) : 0);
  const vp = $derived(proposal ? votedPct(proposal.votes) : 0);
  const theme = $derived(getTheme('dao'));

  // Simulated local vote — localStorage only, clearly labelled BETA.
  // Key: 'cafreso:gov:vote:[id]'  value: 'yes' | 'no' | 'abstain'
  function loadLocalVote(proposalId) {
    if (typeof localStorage === 'undefined') return null;
    return localStorage.getItem(`cafreso:gov:vote:${proposalId}`) || null;
  }

  let localVote = $state(null);
  let voteCast = $state(false);
  let showVotePanel = $state(false);

  // Hydrate vote from localStorage whenever the proposal changes.
  $effect(() => {
    if (!proposal) return;
    const saved = loadLocalVote(proposal.id);
    localVote = saved;
    voteCast = !!saved;
  });

  function castVote(choice) {
    if (!proposal || proposal.status !== 'open') return;
    localVote = choice;
    voteCast = true;
    showVotePanel = false;
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(`cafreso:gov:vote:${proposal.id}`, choice);
    }
    // Push a notification so the user sees feedback in the bell.
    addNotification({
      id: `vote-${proposal.id}-${choice}`,
      type: 'proposal_update',
      title: `Your vote recorded (${choice.toUpperCase()})`,
      body: proposal.title.slice(0, 60),
      url: `/governance/${proposal.id}`,
    });
  }

  function resetVote() {
    if (!proposal) return;
    localVote = null;
    voteCast = false;
    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem(`cafreso:gov:vote:${proposal.id}`);
    }
  }

  // Related proposals: same type, different id.
  const related = $derived(
    PROPOSALS.filter((p) => proposal && p.type === proposal.type && p.id !== proposal.id).slice(0, 2)
  );
</script>

<svelte:head>
  <title>{proposal ? proposal.title : 'Proposal'} · Governance · Cafreso</title>
</svelte:head>

{#if !proposal}
  <div style="max-width: 760px; margin: 0 auto; padding: 60px 18px; text-align: center;">
    <h1 style="font-size: 28px; font-weight: 700; color: hsl(var(--pg-fg));">Proposal not found</h1>
    <a href="/governance" style="color: hsl(260 52% 44%); text-decoration: underline;">← Back to Governance</a>
  </div>
{:else}
  <!-- Hero band — DAO indigo -->
  <div style="
    background: linear-gradient(160deg, hsl(262 55% 14%), hsl(262 45% 20%));
    border-bottom: 1px solid hsl(260 50% 28%);
    padding: 36px 18px 32px;
  ">
    <div style="max-width: 860px; margin: 0 auto;">
      <a href="/governance" style="
        display: inline-flex; align-items: center; gap: 5px;
        font-size: 12.5px; color: hsl(260 25% 68%); text-decoration: none; margin-bottom: 18px;
      ">
        <Icon name="caret-left" size={13} /> All proposals
      </a>

      <!-- Badges row -->
      <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 14px;">
        {#if pt}
          <span style="
            font-size: 10px; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase;
            color: {pt.color}; background: {pt.color}22; border-radius: 6px; padding: 3px 9px;
          ">{pt.label}</span>
        {/if}
        {#if ps}
          <span style="
            font-size: 10px; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase;
            color: {ps.color}; background: {ps.bg}; border-radius: 6px; padding: 3px 9px;
          ">{ps.label}</span>
        {/if}
        <span style="font-size: 10.5px; font-family: ui-monospace, monospace; color: hsl(260 25% 56%);">{proposal.id}</span>
        <span style="
          font-size: 10px; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase;
          background: hsl(260 70% 62% / 0.22); color: hsl(260 90% 78%);
          border: 1px solid hsl(260 50% 38%); border-radius: 5px; padding: 2px 7px;
        ">BETA · simulated vote</span>
      </div>

      <h1 style="
        font-size: clamp(22px, 4.5vw, 36px); font-weight: 800; letter-spacing: -0.02em;
        color: hsl(260 40% 96%); margin: 0 0 12px; line-height: 1.1; text-wrap: pretty;
      ">{proposal.title}</h1>

      <p style="font-size: 15px; line-height: 1.6; color: hsl(260 25% 72%); max-width: 58ch; margin: 0 0 18px;">
        {proposal.summary}
      </p>

      <div style="display: flex; align-items: center; gap: 16px; flex-wrap: wrap;">
        <div style="display: inline-flex; align-items: center; gap: 6px;">
          <Avatar name={proposal.proposedBy.name} hue={proposal.proposedBy.hue} size={26} />
          <span style="font-size: 12.5px; color: hsl(260 25% 72%);">
            Proposed by <strong style="color: hsl(260 40% 92%);">{proposal.proposedBy.name}</strong>
          </span>
        </div>
        {#if proposal.block}
          <span style="font-size: 11px; font-family: ui-monospace, monospace; color: hsl(260 25% 60%);">
            block #{proposal.block.toLocaleString()}
          </span>
        {/if}
        {#if proposal.status === 'open' || proposal.status === 'pending'}
          <span style="font-size: 12px; font-weight: 600; color: hsl(112 55% 60%);">
            {fmtDeadline(proposal.deadline)}
          </span>
        {/if}
      </div>
    </div>
  </div>

  <div style="max-width: 860px; margin: 0 auto; padding: 32px 18px 80px;">
    <div class="proposal-layout">

      <!-- Left: main content -->
      <div class="proposal-main">

        <!-- Vote tally card -->
        <div style="
          border-radius: 14px; padding: 20px 22px; margin-bottom: 24px;
          background: hsl(262 55% 14%); border: 1px solid hsl(260 50% 28%);
        ">
          <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; color: hsl(260 25% 60%); font-weight: 700; margin-bottom: 14px;">
            Vote tally
          </div>
          <!-- Stacked bar -->
          <div style="height: 8px; border-radius: 999px; overflow: hidden; background: hsl(260 30% 22%); display: flex; gap: 1px; margin-bottom: 10px;">
            {#if proposal.votes.yes + proposal.votes.no + proposal.votes.abstain > 0}
              <div style="width: {yp}%; background: hsl(112 43% 45%); border-radius: 999px 0 0 999px; transition: width 0.5s;"></div>
              <div style="width: {Math.round(proposal.votes.no / proposal.votes.total * 1000) / 10}%; background: hsl(0 62% 48%);"></div>
              <div style="width: {Math.round(proposal.votes.abstain / proposal.votes.total * 1000) / 10}%; background: hsl(215 20% 44%); border-radius: 0 999px 999px 0;"></div>
            {:else}
              <div style="width: 100%; background: hsl(260 30% 28%); border-radius: 999px;"></div>
            {/if}
          </div>

          <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px;">
            {#each [
              { label: 'YES', val: proposal.votes.yes, color: 'hsl(112 43% 45%)', bg: 'hsl(112 40% 20%)' },
              { label: 'NO',  val: proposal.votes.no,  color: 'hsl(0 62% 48%)',   bg: 'hsl(0 50% 20%)' },
              { label: 'ABSTAIN', val: proposal.votes.abstain, color: 'hsl(215 20% 60%)', bg: 'hsl(215 20% 22%)' },
            ] as row}
              <div style="background: {row.bg}; border-radius: 8px; padding: 10px 12px;">
                <div style="font-size: 10px; letter-spacing: 0.08em; color: {row.color}; font-weight: 700; margin-bottom: 4px;">{row.label}</div>
                <div style="font-size: 17px; font-weight: 700; color: hsl(260 40% 96%);">
                  {row.val > 0 ? (row.val / 1_000_000).toFixed(2) + 'M' : '—'}
                </div>
              </div>
            {/each}
          </div>

          <div style="font-size: 11px; color: hsl(260 25% 60%); display: flex; justify-content: space-between; flex-wrap: wrap; gap: 4px;">
            <span>{vp}% participation of {(proposal.votes.total / 1_000_000).toFixed(1)}M total supply</span>
            <span>Quorum: {proposal.quorumPct}% required</span>
          </div>
        </div>

        <!-- PostRenderer body -->
        <PostRenderer blocks={proposal.body} theme={theme} />

        <!-- Links: Forum thread + Blog -->
        {#if proposal.forumSlug || proposal.blogSlug || proposal.sneedLink}
          <div style="
            border-radius: 12px; padding: 16px 18px; margin-top: 20px;
            background: hsl(262 40% 18%); border: 1px solid hsl(260 40% 30%);
          ">
            <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; color: hsl(260 25% 60%); font-weight: 700; margin-bottom: 10px;">
              Related resources
            </div>
            <div style="display: flex; flex-direction: column; gap: 7px;">
              {#if proposal.forumSlug}
                <a href="/forums/{proposal.forumSlug}" style="
                  display: inline-flex; align-items: center; gap: 7px;
                  font-size: 13px; color: hsl(260 90% 78%); text-decoration: none; font-weight: 500;
                ">
                  <Icon name="chats-circle" size={15} /> Community discussion thread
                  <Icon name="arrow-right" size={12} style="opacity: 0.6;" />
                </a>
              {/if}
              {#if proposal.blogSlug}
                <a href="/blog/{proposal.blogSlug}" style="
                  display: inline-flex; align-items: center; gap: 7px;
                  font-size: 13px; color: hsl(260 90% 78%); text-decoration: none; font-weight: 500;
                ">
                  <Icon name="article" size={15} /> Dev Log post
                  <Icon name="arrow-right" size={12} style="opacity: 0.6;" />
                </a>
              {/if}
              {#if proposal.sneedLink}
                <a href={proposal.sneedLink} target="_blank" rel="noopener" style="
                  display: inline-flex; align-items: center; gap: 7px;
                  font-size: 13px; color: hsl(260 55% 72%); text-decoration: none; font-weight: 500;
                ">
                  <Icon name="link-simple" size={15} /> Verify on SneedDAO
                  <Icon name="arrow-up-right" size={11} style="opacity: 0.6;" />
                  <span style="font-size: 9.5px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; background: hsl(260 40% 30%); color: hsl(260 25% 70%); border-radius: 4px; padding: 1px 5px;">DAO not live</span>
                </a>
              {/if}
            </div>
          </div>
        {/if}
      </div>

      <!-- Right: Vote sidebar -->
      <div class="proposal-sidebar">
        <!-- Simulated vote panel -->
        <div style="
          border-radius: 14px; overflow: hidden;
          background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border));
          box-shadow: 0 2px 16px -6px hsl(262 40% 20% / 0.15);
          position: sticky; top: 88px;
        ">
          <div style="
            padding: 13px 16px; background: hsl(262 55% 14%); border-bottom: 1px solid hsl(260 40% 28%);
          ">
            <div style="font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: hsl(260 25% 68%);">
              Cast your vote
            </div>
            <div style="font-size: 9.5px; color: hsl(260 25% 54%); margin-top: 3px;">
              Simulated · stored locally · not on-chain
            </div>
          </div>

          <div style="padding: 16px;">
            {#if proposal.status !== 'open'}
              <div style="
                text-align: center; padding: 20px 12px; font-size: 12.5px;
                color: hsl(var(--pg-fg-muted)); line-height: 1.5;
              ">
                <Icon name="lock-simple" size={22} style="opacity: 0.35; display: block; margin: 0 auto 8px;" />
                Voting is {proposal.status === 'pending' ? 'not yet open' : 'closed'} for this proposal.
              </div>
            {:else if voteCast}
              <!-- Voted state -->
              <div style="text-align: center; padding: 12px 0 8px;">
                <div style="
                  width: 44px; height: 44px; border-radius: 50%; margin: 0 auto 10px;
                  background: {localVote === 'yes' ? 'hsl(112 45% 45% / 0.16)' : localVote === 'no' ? 'hsl(0 62% 50% / 0.16)' : 'hsl(215 16% 50% / 0.16)'};
                  display: flex; align-items: center; justify-content: center;
                ">
                  <Icon
                    name={localVote === 'yes' ? 'check' : localVote === 'no' ? 'x' : 'minus'}
                    size={22}
                    style="color: {localVote === 'yes' ? 'hsl(112 43% 40%)' : localVote === 'no' ? 'hsl(0 62% 40%)' : 'hsl(215 20% 44%)'};"
                  />
                </div>
                <div style="font-size: 13.5px; font-weight: 700; color: hsl(var(--pg-fg));">
                  Voted {localVote?.toUpperCase()}
                </div>
                <div style="font-size: 11px; color: hsl(var(--pg-fg-muted)); margin: 4px 0 14px;">
                  Simulated · not yet on-chain
                </div>
                <button
                  type="button"
                  onclick={resetVote}
                  style="
                    background: none; border: 1px solid hsl(var(--pg-border)); border-radius: 8px;
                    font-size: 11.5px; font-family: inherit; cursor: pointer; padding: 6px 14px;
                    color: hsl(var(--pg-fg-muted));
                  "
                >Change vote</button>
              </div>
            {:else}
              <!-- Vote choices -->
              <div style="display: flex; flex-direction: column; gap: 7px; margin-bottom: 12px;">
                {#each [
                  { choice: 'yes',     label: 'Vote YES',     color: 'hsl(112 43% 40%)',  border: 'hsl(112 40% 70%)', bg: 'hsl(112 45% 45% / 0.16)' },
                  { choice: 'no',      label: 'Vote NO',      color: 'hsl(0 62% 42%)',    border: 'hsl(0 55% 72%)',   bg: 'hsl(0 62% 50% / 0.16)' },
                  { choice: 'abstain', label: 'Abstain',      color: 'hsl(215 16% 38%)',  border: 'hsl(215 20% 72%)', bg: 'hsl(215 16% 50% / 0.16)' },
                ] as v}
                  <button
                    type="button"
                    onclick={() => castVote(v.choice)}
                    style="
                      width: 100%; padding: 10px 14px; border-radius: 9px;
                      border: 1.5px solid {v.border}; background: {v.bg};
                      color: {v.color}; font-size: 13px; font-weight: 700;
                      font-family: inherit; cursor: pointer;
                      transition: filter 0.12s;
                    "
                    onmouseenter={(e) => (e.currentTarget.style.filter = 'brightness(0.94)')}
                    onmouseleave={(e) => (e.currentTarget.style.filter = 'none')}
                  >{v.label}</button>
                {/each}
              </div>

              {#if !$isAuthenticated}
                <div style="font-size: 11px; color: hsl(var(--pg-fg-muted)); text-align: center; line-height: 1.5;">
                  <Icon name="info" size={12} style="vertical-align: middle;" />
                  Sign in to cast a real vote when the DAO goes live.
                </div>
              {:else}
                <div style="font-size: 11px; color: hsl(var(--pg-fg-muted)); text-align: center; line-height: 1.5;">
                  Votes are simulated locally. Real governance requires neuron staking.
                </div>
              {/if}
            {/if}
          </div>
        </div>

        <!-- Neuron info teaser -->
        <div style="
          border-radius: 12px; padding: 14px; margin-top: 12px;
          background: hsl(262 40% 14%); border: 1px solid hsl(260 40% 28%);
        ">
          <div style="font-size: 10.5px; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase; color: hsl(260 25% 60%); margin-bottom: 8px;">
            Neuron power
          </div>
          <div style="font-size: 13px; color: hsl(260 25% 72%); line-height: 1.5;">
            Stake $CF to create a neuron and earn boosted voting power. The longer the dissolve delay, the greater the weight.
          </div>
          <a href="/profile" style="
            display: inline-flex; align-items: center; gap: 5px; margin-top: 10px;
            font-size: 12px; font-weight: 600; color: hsl(260 90% 78%); text-decoration: none;
          ">
            <Icon name="coins" size={13} /> View your $CF balance →
          </a>
        </div>
      </div>
    </div>

    <!-- Related proposals -->
    {#if related.length > 0}
      <div style="margin-top: 36px;">
        <div style="font-size: 13px; font-weight: 700; color: hsl(var(--pg-fg-muted)); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.05em;">
          Related proposals
        </div>
        <div class="related-grid">
          {#each related as r (r.id)}
            {@const rps = proposalStatus(r.status)}
            <a href="/governance/{r.id}" style="
              display: block; border-radius: 12px; padding: 14px 16px; text-decoration: none;
              background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border));
            ">
              <div style="
                display: inline-block; font-size: 9.5px; font-weight: 700; letter-spacing: 0.06em;
                text-transform: uppercase; color: {rps.color}; background: {rps.bg};
                border-radius: 4px; padding: 2px 6px; margin-bottom: 6px;
              ">{rps.label}</div>
              <div style="font-size: 14px; font-weight: 600; color: hsl(var(--pg-fg)); line-height: 1.3;">{r.title}</div>
            </a>
          {/each}
        </div>
      </div>
    {/if}
  </div>
{/if}
