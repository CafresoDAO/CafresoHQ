<script>
  /* Deep Research progress — shows HOW the research is being performed while a
     worker runs the pass. The network only reports coarse job status
     (pending → claimed → done), so these stages are an HONEST illustration of
     the method, not a live trace: they advance on elapsed-time estimates and
     are framed as "what a deep pass does", never claimed as real-time telemetry.
     The point is that a visitor sees the same shape of research HQ runs —
     decompose → search → note per angle → synthesize → tree. */
  import Icon from './Icon.svelte';

  export let elapsedMs = 0;
  export let workers = '';   // e.g. "2 workers online"

  // Rough pacing for a ~4–6 min pass. `at` is the elapsed second a stage is
  // expected to begin; the last never auto-completes (it lands with the answer).
  const STAGES = [
    { at: 0,   icon: 'list-bullets',   label: 'Breaking the question into angles' },
    { at: 25,  icon: 'globe',          label: 'Searching the web for each angle' },
    { at: 70,  icon: 'note-pencil',    label: 'Writing a note page per angle' },
    { at: 190, icon: 'tree-structure', label: 'Synthesizing + building the research tree' }
  ];
  $: secs = Math.floor(elapsedMs / 1000);
  // The active stage is the last one whose `at` has passed.
  $: active = STAGES.reduce((acc, s, i) => (secs >= s.at ? i : acc), 0);
  $: mm = String(Math.floor(secs / 60)).padStart(1, '0');
  $: ss = String(secs % 60).padStart(2, '0');
</script>

<div class="drp">
  <div class="drp-head">
    <span class="drp-badge"><Icon name="tree-structure" size={12} /> Deep Research</span>
    <span class="drp-timer">{mm}:{ss}</span>
  </div>
  <ul class="drp-stages">
    {#each STAGES as s, i}
      <li class="drp-stage" class:done={i < active} class:active={i === active} class:todo={i > active}>
        <span class="drp-ic">
          {#if i < active}
            <Icon name="check" size={13} />
          {:else if i === active}
            <span class="drp-spin"></span>
          {:else}
            <Icon name={s.icon} size={13} />
          {/if}
        </span>
        <span class="drp-label">{s.label}</span>
      </li>
    {/each}
  </ul>
  <p class="drp-foot">
    {#if secs > 45}
      Still researching — the finished report joins <a href="/library" class="drp-link">the library</a>
      either way, so you can close this and find it there.
    {:else}
      This is the same multi-step research HQ runs{workers ? ` · ${workers}` : ''}. It takes a few minutes.
    {/if}
  </p>
</div>

<style>
  .drp {
    border: 1px solid hsl(260 40% 60% / 0.35);
    background: linear-gradient(180deg, hsl(260 55% 60% / 0.08), transparent);
    border-radius: 14px;
    padding: 14px 15px 13px;
    margin: 2px 0 4px;
  }
  .drp-head {
    display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;
  }
  .drp-badge {
    display: inline-flex; align-items: center; gap: 5px;
    font-size: 10.5px; font-weight: 800; letter-spacing: 0.06em; text-transform: uppercase;
    color: hsl(260 70% 60%);
  }
  .drp-timer {
    font-size: 11.5px; font-weight: 600; color: hsl(var(--pg-fg-muted));
    font-variant-numeric: tabular-nums; font-family: 'JetBrains Mono', ui-monospace, monospace;
  }
  .drp-stages { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 9px; }
  .drp-stage { display: flex; align-items: center; gap: 9px; font-size: 12.5px; line-height: 1.3; }
  .drp-ic {
    width: 20px; height: 20px; flex-shrink: 0; border-radius: 50%;
    display: inline-flex; align-items: center; justify-content: center;
  }
  .drp-stage.done  .drp-ic { background: hsl(150 55% 45% / 0.18); color: hsl(150 60% 40%); }
  .drp-stage.active .drp-ic { color: hsl(260 70% 60%); }
  .drp-stage.todo  .drp-ic { color: hsl(var(--pg-fg-muted)); opacity: 0.55; }
  .drp-stage.done  .drp-label { color: hsl(var(--pg-fg-muted)); }
  .drp-stage.active .drp-label { color: hsl(var(--pg-fg)); font-weight: 600; }
  .drp-stage.todo  .drp-label { color: hsl(var(--pg-fg-muted)); opacity: 0.7; }
  .drp-spin {
    width: 13px; height: 13px; border-radius: 50%;
    border: 2px solid hsl(260 40% 60% / 0.3); border-top-color: hsl(260 70% 58%);
    animation: drp-spin 0.7s linear infinite;
  }
  @keyframes drp-spin { to { transform: rotate(360deg); } }
  .drp-foot { font-size: 11px; line-height: 1.5; color: hsl(var(--pg-fg-muted)); margin: 12px 0 0; }
  .drp-link { color: hsl(260 70% 58%); font-weight: 600; text-decoration: none; }
  :global(.dark) .drp-badge, :global(.dark) .drp-stage.active .drp-ic, :global(.dark) .drp-link { color: hsl(260 75% 72%); }
  @media (prefers-reduced-motion: reduce) { .drp-spin { animation: none; } }
</style>
