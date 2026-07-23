<script>
  /* "This week in the library" — what the network actually did, in one
     glance. Pure client-side digest over the index the page already fetches
     (see $lib/utils/digest.js) — no new endpoint, no canister change. Honest
     about what it is: real counts over real timestamps, plus a naive
     keyword-frequency "themes" pass, not true topic-cluster detection (that
     runs client-side inside graph-viewer.js at render time and is never
     persisted, so it isn't available here). */
  import Icon from './Icon.svelte';
  import { fmtNsDate } from '$lib/utils/time.js';
  import { weeklyDigest } from '$lib/utils/digest.js';

  export let entries = [];             // index.entries — already fetched by the page
  export let onOpen = (_id) => {};      // open an entry (drawer)
  export let onTheme = (_word) => {};   // jump the browse filter to a theme

  $: d = weeklyDigest(entries);
  $: maxDaily = d ? Math.max(1, ...d.daily.map((x) => x.count)) : 1;
  const dayLabel = (dt) => dt.toLocaleDateString(undefined, { weekday: 'short' });
</script>

{#if d}
  <section class="wd" aria-label="What the network learned this week">
    <div class="wd-head">
      <div class="wd-title"><span class="wd-glyph" aria-hidden="true">◆</span> This week in the library</div>
      <p class="wd-sub">What the network actually researched, at a glance.</p>
    </div>

    <div class="wd-stats">
      <div class="wd-stat">
        <span class="wd-n">{d.total}</span>
        <span class="wd-label">answered</span>
      </div>
      <div class="wd-stat">
        <span class="wd-n">{d.gaps}</span>
        <span class="wd-label">self-asked gaps</span>
      </div>
      {#if d.deep > 0}
        <div class="wd-stat">
          <span class="wd-n">{d.deep}</span>
          <span class="wd-label">deep research</span>
        </div>
      {/if}
      <div class="wd-stat">
        <span class="wd-n">{d.avgSources}</span>
        <span class="wd-label">avg. sources</span>
      </div>
    </div>

    <div class="wd-spark" role="img" aria-label="Entries answered per day, last 7 days">
      {#each d.daily as b}
        <div class="wd-bar-col">
          <div class="wd-bar" style="height: {Math.max(4, (b.count / maxDaily) * 34)}px;" title="{b.count} on {dayLabel(b.day)}"></div>
          <span class="wd-bar-label">{dayLabel(b.day)}</span>
        </div>
      {/each}
    </div>

    {#if d.themes.length}
      <div class="wd-themes">
        <span class="wd-themes-label">Themes:</span>
        {#each d.themes as t}
          <button class="wd-theme" on:click={() => onTheme(t.word)}>
            {t.word} <span class="wd-theme-n">{t.count}</span>
          </button>
        {/each}
      </div>
    {/if}

    {#if d.topEntry}
      <button class="wd-top" on:click={() => onOpen(d.topEntry.id)}>
        <Icon name="star" size={14} weight="fill" style="color: hsl(45 85% 55%); flex-shrink: 0;" />
        <span class="wd-top-body">
          <span class="wd-top-kicker">Most examined this week · {d.topEntry.sources} sources</span>
          <span class="wd-top-q">{d.topEntry.query}</span>
        </span>
        <Icon name="arrow-right" size={13} style="flex-shrink: 0; color: hsl(var(--pg-fg-subtle));" />
      </button>
    {/if}
  </section>
{:else if entries.length}
  <!-- Entries exist, just none in the last 7 days — a young or quiet library,
       not a broken one. The page's own zero-entries empty state covers the
       "no library at all" case, so this only fires when there's a library but
       an idle week. -->
  <section class="wd wd-quiet" aria-label="This week in the library">
    <div class="wd-title"><span class="wd-glyph" aria-hidden="true">◆</span> This week in the library</div>
    <p class="wd-quiet-note">
      Quiet week — nothing answered in the last 7 days. {entries.length.toLocaleString()} question{entries.length === 1 ? '' : 's'} answered so far, browsing below.
    </p>
  </section>
{/if}

<style>
  .wd {
    border: 1px solid hsl(var(--pg-border));
    border-radius: 18px;
    background: hsl(var(--pg-surface));
    padding: 18px 18px 16px;
    margin-bottom: 22px;
  }
  .wd-head { margin-bottom: 14px; }
  /* Eyebrow, not headline: this module is auxiliary to the actual stories,
     and giving it the same serif headline treatment as the news itself made
     the pre-content stack read as four equal-weight front pages. Playfair is
     reserved for real headlines; auxiliary modules get the small-caps label. */
  .wd-title {
    display: inline-flex; align-items: center; gap: 7px;
    font: 800 11px/1 Inter, system-ui, sans-serif;
    letter-spacing: 0.12em; text-transform: uppercase;
    color: hsl(var(--pg-fg-muted));
  }
  .wd-glyph { color: hsl(266 60% 55%); font-size: 15px; }
  .wd-sub { font-size: 12.5px; line-height: 1.5; color: hsl(var(--pg-fg-muted)); margin: 4px 0 0; }
  .wd-quiet { padding-bottom: 18px; }
  .wd-quiet-note { font-size: 13px; line-height: 1.55; color: hsl(var(--pg-fg-muted)); margin: 6px 0 0; }

  .wd-stats { display: flex; flex-wrap: wrap; gap: 22px; margin-bottom: 16px; }
  .wd-stat { display: flex; flex-direction: column; gap: 1px; }
  .wd-n { font-size: 22px; font-weight: 700; color: hsl(var(--pg-fg)); font-family: 'JetBrains Mono', ui-monospace, monospace; line-height: 1.1; }
  .wd-label { font-size: 10.5px; text-transform: uppercase; letter-spacing: .05em; color: hsl(var(--pg-fg-muted)); }

  .wd-spark {
    display: flex; align-items: flex-end; gap: 8px; height: 54px;
    padding: 0 2px 4px; margin-bottom: 16px;
    border-bottom: 1px solid hsl(var(--pg-border));
  }
  .wd-bar-col { display: flex; flex-direction: column; align-items: center; gap: 5px; flex: 1; }
  .wd-bar {
    width: 100%; max-width: 22px; border-radius: 4px 4px 2px 2px;
    background: linear-gradient(180deg, hsl(45 85% 60%), hsl(45 80% 50%));
  }
  .wd-bar-label { font-size: 9.5px; color: hsl(var(--pg-fg-subtle)); font-family: 'JetBrains Mono', ui-monospace, monospace; }

  .wd-themes { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; margin-bottom: 14px; }
  .wd-themes-label { font-size: 11.5px; font-weight: 600; color: hsl(var(--pg-fg-muted)); margin-right: 2px; }
  .wd-theme {
    display: inline-flex; align-items: center; gap: 5px;
    border: 1px solid hsl(var(--pg-border)); border-radius: 999px; cursor: pointer;
    background: hsl(var(--pg-elevated)); color: hsl(var(--pg-fg));
    font: 600 12px Inter, system-ui, sans-serif; padding: 5px 11px;
    text-transform: capitalize; transition: border-color .14s, background .14s;
  }
  .wd-theme:hover { border-color: hsl(45 75% 58%); background: hsl(45 60% 95%); }
  :global(.dark) .wd-theme:hover { background: hsl(45 40% 22% / 0.4); }
  .wd-theme-n { font-size: 10.5px; color: hsl(var(--pg-fg-muted)); font-family: 'JetBrains Mono', ui-monospace, monospace; }

  .wd-top {
    display: flex; align-items: center; gap: 10px; width: 100%; text-align: left;
    border: 1px solid hsl(45 60% 78%); border-radius: 12px; cursor: pointer;
    background: hsl(45 70% 96%); padding: 11px 13px;
    transition: border-color .14s, transform .14s;
  }
  .wd-top:hover { border-color: hsl(45 75% 55%); transform: translateY(-1px); }
  :global(.dark) .wd-top { background: hsl(45 40% 18% / 0.35); border-color: hsl(45 40% 42%); }
  .wd-top-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .wd-top-kicker { font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: hsl(38 60% 38%); }
  :global(.dark) .wd-top-kicker { color: hsl(45 75% 68%); }
  .wd-top-q {
    font-size: 13.5px; color: hsl(var(--pg-fg));
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }

  @media (max-width: 640px) {
    .wd-stats { gap: 16px; }
    .wd-n { font-size: 19px; }
  }
</style>
