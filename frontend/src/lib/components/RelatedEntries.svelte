<script>
  /* "Related in the library" — other already-answered entries that share a
     keyword with the one being read (see relatedEntries() in
     $lib/utils/digest.js). This is the Wikipedia-rabbit-hole mechanic: every
     read should offer 2-3 more reads. Deliberately NOT the ghost-node "people
     also wonder" follow-ups (those are unanswered suggestions from the Brave
     harvest, when populated) — this links to real, already-answered siblings. */
  import { fmtNsRelative } from '$lib/utils/time.js';

  export let items = [];           // Entry[] from relatedEntries()
  export let onOpen = (_id) => {};
  export let plain = (t) => String(t || '');
</script>

{#if items.length}
  <div class="re">
    <div class="re-label">Related in the library</div>
    <ul class="re-list">
      {#each items as e (e.id)}
        <li>
          <button class="re-item" on:click={() => onOpen(e.id)}>
            <span class="re-q">{plain(e.query)}</span>
            <span class="re-meta">{fmtNsRelative(e.ts)} · {e.sources} source{e.sources === 1 ? '' : 's'}</span>
          </button>
        </li>
      {/each}
    </ul>
  </div>
{/if}

<style>
  .re { margin-top: 4px; }
  .re-label {
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em;
    color: hsl(45 80% 45%); margin-bottom: 8px;
  }
  .re-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .re-item {
    display: flex; flex-direction: column; gap: 3px; width: 100%; text-align: left;
    border: 1px solid hsl(var(--pg-border)); border-radius: 10px; cursor: pointer;
    background: hsl(var(--pg-surface)); padding: 9px 11px;
    transition: border-color .14s, background .14s;
  }
  .re-item:hover { border-color: hsl(45 75% 58%); background: hsl(45 60% 97%); }
  :global(.dark) .re-item:hover { background: hsl(45 40% 20% / 0.3); }
  .re-q { font-size: 12.5px; line-height: 1.4; color: hsl(var(--pg-fg)); font-weight: 500; }
  .re-meta { font-size: 10.5px; color: hsl(var(--pg-fg-muted)); font-family: 'JetBrains Mono', ui-monospace, monospace; }
</style>
