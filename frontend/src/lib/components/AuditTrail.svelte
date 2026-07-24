<script>
  // On-Chain Audit Trail — timeline of a principal's verifiable on-chain
  // activity: posts authored, comments submitted, burns/tips, governance votes.
  // In the MVP this is seeded from local store data; once the canister audit
  // log endpoint is ready the `events` prop is replaced by an async fetch.
  import Icon from '$lib/components/Icon.svelte';

  export let principalId = '';       // truncated or full principal
  export let events      = [];       // array of AuditEvent (see shape below)
  export let maxVisible  = 20;
  export let compact     = false;    // compact = no body text, tighter rows

  /*
  AuditEvent shape:
  {
    id:       string,
    kind:     'post' | 'comment' | 'burn' | 'vote' | 'login' | 'tip',
    title:    string,
    sub:      string,          // secondary line, e.g. "at block #4,218,812"
    block:    number | null,
    ts:       number,          // ms timestamp
    url:      string | null,   // link target
    amount:   number | null,   // for burn/tip
  }
  */

  const KIND_META = {
    post:    { icon: 'pencil-simple',  color: 'hsl(210 80% 48%)', label: 'Post authored'    },
    comment: { icon: 'chat-circle',    color: 'hsl(var(--brand-leaf))', label: 'Comment posted'   },
    burn:    { icon: 'fire',           color: 'hsl(32 72% 50%)',  label: 'Burn / Tip'       },
    vote:    { icon: 'gavel',          color: 'hsl(260 70% 62%)', label: 'Governance vote'  },
    login:   { icon: 'fingerprint',    color: 'hsl(var(--pg-fg-muted))', label: 'Identity login'   },
    tip:     { icon: 'hand-coins',     color: 'hsl(43 74% 54%)',  label: 'Tip received'     },
  };

  function meta(kind) {
    return KIND_META[kind] ?? { icon: 'circle', color: 'hsl(var(--pg-fg-muted))', label: kind };
  }

  function fmtDate(ts) {
    return new Date(ts).toLocaleString('en-GB', {
      day: 'numeric', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  }

  $: visible = events.slice(0, maxVisible);
  $: hasMore = events.length > maxVisible;
</script>

<div class="audit-trail">
  <!-- Header -->
  {#if !compact}
    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
      <div style="
        width: 36px; height: 36px; border-radius: 10px;
        background: hsl(262 52% 44%); display: flex; align-items: center; justify-content: center;
      ">
        <Icon name="link-simple" size={18} style="color: white;" />
      </div>
      <div>
        <div style="font-size: 15px; font-weight: 700; color: hsl(var(--pg-fg));">On-Chain Audit Trail</div>
        {#if principalId}
          <div style="font-size: 11px; font-family: ui-monospace, monospace; color: hsl(var(--pg-fg-muted));">{principalId}</div>
        {/if}
      </div>
      <div style="margin-left: auto; display: flex; align-items: center; gap: 6px;">
        <span style="
          display: inline-flex; align-items: center; gap: 4px;
          font-size: 10.5px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
          background: hsl(112 40% 92%); color: hsl(112 43% 30%);
          border: 1px solid hsl(112 40% 78%);
          padding: 3px 8px; border-radius: 999px;
        ">
          <span style="width: 6px; height: 6px; border-radius: 50%; background: hsl(var(--brand-leaf)); display: inline-block;"></span>
          Verified on-chain
        </span>
      </div>
    </div>
  {/if}

  <!-- Timeline -->
  {#if visible.length === 0}
    <div style="
      padding: 32px; text-align: center; border-radius: 12px;
      border: 1px dashed hsl(var(--pg-border)); color: hsl(var(--pg-fg-subtle)); font-size: 13px;
    ">
      <Icon name="hourglass" size={24} style="opacity: 0.35; display: block; margin: 0 auto 8px;" />
      No on-chain activity recorded yet
    </div>
  {:else}
    <div style="position: relative;">
      <!-- Vertical track line -->
      <div style="
        position: absolute; left: 17px; top: 8px; bottom: 8px;
        width: 1px; background: linear-gradient(180deg, hsl(var(--pg-border)), transparent);
        pointer-events: none;
      "></div>

      <div style="display: flex; flex-direction: column; gap: {compact ? 0 : 4}px;">
        {#each visible as ev (ev.id)}
          {@const m = meta(ev.kind)}
          <div style="
            display: flex; gap: 12px; align-items: flex-start;
            padding: {compact ? '8px 0 8px 4px' : '10px 12px 10px 4px'};
            border-radius: 10px;
            position: relative;
          ">
            <!-- Icon node -->
            <div style="
              width: 34px; height: 34px; border-radius: 50%; flex-shrink: 0;
              background: {m.color}1A; border: 1.5px solid {m.color}55;
              display: flex; align-items: center; justify-content: center;
              position: relative; z-index: 1;
            ">
              <Icon name={m.icon} size={15} style="color: {m.color};" />
            </div>

            <!-- Content -->
            <div style="flex: 1; min-width: 0; padding-top: 2px;">
              <div style="display: flex; align-items: baseline; justify-content: space-between; gap: 8px;">
                {#if ev.url}
                  <a
                    href={ev.url}
                    style="
                      font-size: {compact ? 13 : 14}px; font-weight: 600;
                      color: hsl(var(--pg-fg)); text-decoration: none;
                    "
                  >{ev.title}</a>
                {:else}
                  <span style="font-size: {compact ? 13 : 14}px; font-weight: 600; color: hsl(var(--pg-fg));">{ev.title}</span>
                {/if}
                <span style="font-size: 10.5px; color: hsl(var(--pg-fg-subtle)); white-space: nowrap; flex-shrink: 0;">{fmtDate(ev.ts)}</span>
              </div>

              {#if !compact && ev.sub}
                <div style="font-size: 12px; color: hsl(var(--pg-fg-muted)); margin-top: 2px;">{ev.sub}</div>
              {/if}

              <!-- Tags row -->
              <div style="display: flex; gap: 6px; margin-top: {compact ? 2 : 5}px; flex-wrap: wrap;">
                <span style="
                  font-size: 10px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase;
                  background: {m.color}18; color: {m.color}; border-radius: 4px; padding: 2px 6px;
                ">{m.label}</span>
                {#if ev.block}
                  <span style="
                    font-size: 10px; font-family: ui-monospace, monospace;
                    color: hsl(var(--pg-fg-subtle)); background: hsl(var(--pg-hover));
                    border-radius: 4px; padding: 2px 6px;
                  ">block #{ev.block.toLocaleString()}</span>
                {/if}
                {#if ev.amount}
                  <span style="
                    font-size: 10px; font-weight: 600;
                    color: hsl(32 72% 44%); background: hsl(32 72% 94%);
                    border-radius: 4px; padding: 2px 6px;
                  ">{ev.amount.toLocaleString()} $CF</span>
                {/if}
              </div>
            </div>
          </div>
        {/each}
      </div>

      {#if hasMore}
        <div style="
          margin-top: 12px; text-align: center;
          font-size: 12px; color: hsl(210 80% 48%); font-weight: 600;
        ">
          +{events.length - maxVisible} more events on-chain
        </div>
      {/if}
    </div>
  {/if}
</div>
