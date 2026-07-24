<script>
  /* "Up Next" — a personal research shortlist. Add questions you want the
     network to answer, boost to reorder them, and send any one into the live
     research pipeline. When a queued question lands in the library (answered
     by anyone), it graduates to a green "read it" row. Honest v1: boosts are
     device-local (see $lib/stores/upnext.js) — no invented global counts. */
  import Icon from './Icon.svelte';
  import { upNext, addQuestion, boost, removeQuestion, normQ } from '$lib/stores/upnext.js';

  // (q) => entryId | null — loose match against the already-answered index.
  export let findAnswered = (_q) => null;
  export let onOpen = (_id) => {};                       // open an answered entry
  export let onSend = async (_q) => ({ status: 'idle' }); // push a question to the network
  export let workersOnline = true;                        // gate the send CTA honestly

  let draft = '';
  let sending = {};   // normQ(q) -> bool
  let note = {};      // normQ(q) -> transient status string

  function add() {
    const ok = addQuestion(draft);
    if (ok) draft = '';
  }

  async function send(q) {
    const k = normQ(q);
    sending = { ...sending, [k]: true };
    note = { ...note, [k]: '' };
    try {
      const r = await onSend(q);
      if (r?.status === 'rejected') note = { ...note, [k]: r.reason === 'budget' ? "Today's budget is spent" : r.reason === 'busy' ? 'Network busy — try soon' : 'Still researching…' };
      else if (r?.status === 'dark') note = { ...note, [k]: 'No workers online right now' };
      // 'done'/'hit' → the item graduates via findAnswered on the next index refresh.
    } finally {
      sending = { ...sending, [k]: false };
    }
  }
</script>

<section class="un" aria-label="Up next — your research shortlist">
  <div class="un-head">
    <div class="un-title">
      <span class="un-glyph" aria-hidden="true">✦</span>
      Up Next
    </div>
    <p class="un-sub">Questions you want answered next. Boost to reorder — send any one to the live network.</p>
  </div>

  <form class="un-add" on:submit|preventDefault={add}>
    <input
      type="text"
      bind:value={draft}
      maxlength="240"
      placeholder="Add a question the network should answer…"
      aria-label="Add a question to your shortlist"
    />
    <button type="submit" disabled={!draft.trim()} aria-label="Add to shortlist">
      <Icon name="plus" size={15} /> Add
    </button>
  </form>

  {#if $upNext.length === 0}
    <p class="un-empty">Nothing queued yet. Add a question above, or tap “Boost” on a follow-up anywhere in the library.</p>
  {:else}
    <ul class="un-list">
      {#each $upNext as it (normQ(it.q))}
        {@const answeredId = findAnswered(it.q)}
        <li class="un-item" class:un-answered={answeredId}>
          <button class="un-boost" on:click={() => boost(it.q)} title="Boost — move it up your shortlist"
                  disabled={!!answeredId} aria-label={`Boost (${it.boosts})`}>
            <Icon name="caret-up" size={13} />
            <span class="un-boost-n">{it.boosts}</span>
          </button>

          <div class="un-body">
            <span class="un-q">{it.q}</span>
            {#if answeredId}
              <span class="un-status un-status-ok"><Icon name="check" size={11} /> Answered</span>
            {:else if note[normQ(it.q)]}
              <span class="un-status">{note[normQ(it.q)]}</span>
            {/if}
          </div>

          {#if answeredId}
            <button class="un-go un-go-read" on:click={() => onOpen(answeredId)}>
              Read it <Icon name="arrow-right" size={12} />
            </button>
          {:else}
            <button class="un-go" on:click={() => send(it.q)}
                    disabled={sending[normQ(it.q)] || !workersOnline}
                    title={workersOnline ? 'Send this to the research network now' : 'No workers online right now'}>
              {#if sending[normQ(it.q)]}
                <span class="un-spin" aria-hidden="true"></span> Sending…
              {:else}
                <Icon name="magnifying-glass" size={12} /> Ask
              {/if}
            </button>
          {/if}

          <button class="un-x" on:click={() => removeQuestion(it.q)} aria-label="Remove from shortlist">
            <Icon name="x" size={12} />
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .un {
    border: 1px solid hsl(var(--pg-border));
    border-radius: 18px;
    background: hsl(var(--pg-surface));
    padding: 18px 18px 14px;
    margin-bottom: 22px;
  }
  .un-head { margin-bottom: 12px; }
  /* Eyebrow, not headline — same demotion as WeeklyDigest's .wd-title:
     auxiliary modules take the small-caps label so the serif headline voice
     stays reserved for actual stories. */
  .un-title {
    display: inline-flex; align-items: center; gap: 7px;
    font: 800 11px/1 Inter, system-ui, sans-serif;
    letter-spacing: 0.12em; text-transform: uppercase;
    color: hsl(var(--pg-fg-muted));
  }
  .un-glyph { color: hsl(45 85% 55%); }
  .un-sub { font-size: 12.5px; line-height: 1.5; color: hsl(var(--pg-fg-muted)); margin: 4px 0 0; }

  .un-add { display: flex; gap: 8px; margin-bottom: 12px; }
  .un-add input {
    flex: 1; min-width: 0; border: 1px solid hsl(var(--pg-border)); border-radius: 999px;
    background: hsl(var(--pg-elevated)); padding: 9px 15px;
    font: 14px Inter, system-ui, sans-serif; color: hsl(var(--pg-fg)); outline: none;
    transition: border-color .14s;
  }
  .un-add input:focus { border-color: hsl(45 75% 58%); }
  .un-add input::placeholder { color: hsl(var(--pg-fg-muted)); }
  .un-add button {
    display: inline-flex; align-items: center; gap: 5px; flex-shrink: 0;
    border: none; border-radius: 999px; cursor: pointer;
    background: hsl(45 88% 56%); color: hsl(24 48% 14%);
    font: 700 13px Inter, system-ui, sans-serif; padding: 0 16px;
  }
  .un-add button:disabled { opacity: 0.5; cursor: default; }

  .un-empty { font-size: 13px; line-height: 1.6; color: hsl(var(--pg-fg-muted)); margin: 0; }

  .un-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
  .un-item {
    display: flex; align-items: center; gap: 10px;
    padding: 9px 10px; border-radius: 12px;
    background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border));
  }
  .un-answered { border-color: hsl(150 50% 62%); background: hsl(150 55% 96%); }
  :global(.dark) .un-answered { background: hsl(150 40% 18% / 0.4); border-color: hsl(150 40% 40%); }

  .un-boost {
    display: flex; flex-direction: column; align-items: center; gap: 0; flex-shrink: 0;
    width: 40px; padding: 5px 0; border-radius: 9px; cursor: pointer;
    border: 1px solid hsl(var(--pg-border)); background: hsl(var(--pg-surface));
    color: hsl(var(--pg-fg-muted)); transition: border-color .14s, color .14s, transform .1s;
  }
  .un-boost:hover:not(:disabled) { border-color: hsl(45 75% 58%); color: hsl(45 70% 42%); }
  .un-boost:active:not(:disabled) { transform: scale(0.94); }
  .un-boost:disabled { opacity: 0.5; cursor: default; }
  .un-boost-n { font-size: 12px; font-weight: 700; font-family: 'JetBrains Mono', ui-monospace, monospace; color: hsl(var(--pg-fg)); }

  .un-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .un-q { font-size: 13.5px; line-height: 1.4; color: hsl(var(--pg-fg)); }
  .un-status { font-size: 11px; color: hsl(var(--pg-fg-muted)); display: inline-flex; align-items: center; gap: 4px; }
  .un-status-ok { color: hsl(150 65% 34%); font-weight: 600; }
  :global(.dark) .un-status-ok { color: hsl(150 60% 66%); }

  .un-go {
    display: inline-flex; align-items: center; gap: 5px; flex-shrink: 0;
    border: 1px solid hsl(var(--pg-border)); border-radius: 999px; cursor: pointer;
    background: hsl(var(--pg-surface)); color: hsl(var(--pg-fg));
    font: 600 12px Inter, system-ui, sans-serif; padding: 7px 12px;
    transition: border-color .14s, background .14s;
  }
  .un-go:hover:not(:disabled) { border-color: hsl(45 75% 58%); }
  .un-go:disabled { opacity: 0.5; cursor: default; }
  .un-go-read { border-color: hsl(150 50% 55%); color: hsl(150 60% 30%); }
  :global(.dark) .un-go-read { color: hsl(150 60% 68%); border-color: hsl(150 40% 42%); }

  .un-x {
    flex-shrink: 0; width: 28px; height: 28px; display: grid; place-items: center;
    border: none; background: transparent; border-radius: 8px; cursor: pointer;
    color: hsl(var(--pg-fg-muted)); transition: background .14s, color .14s;
  }
  .un-x:hover { background: hsl(var(--pg-hover)); color: hsl(var(--pg-fg)); }

  .un-spin {
    width: 11px; height: 11px; border-radius: 50%;
    border: 2px solid hsl(var(--pg-fg-muted) / 0.35); border-top-color: hsl(var(--pg-fg-muted));
    animation: un-spin 0.7s linear infinite; display: inline-block;
  }
  @keyframes un-spin { to { transform: rotate(360deg); } }

  @media (max-width: 640px) {
    .un-q { font-size: 13px; }
    .un-go { padding: 7px 10px; }
    .un-item { gap: 8px; padding: 8px; }
  }
</style>
