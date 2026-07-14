<script>
  // Unified themed block renderer for Dev Log and Forum posts.
  // Accepts the parsed blocks array and a theme config from themes.js.
  // banking-brave layout bypasses this (uses BankingBravePost.svelte directly).
  import StatsBar from '$lib/components/widgets/StatsBar.svelte';
  import ChartBlock from '$lib/components/widgets/ChartBlock.svelte';
  import RoadmapBlock from '$lib/components/widgets/RoadmapBlock.svelte';
  import ProgressMeter from '$lib/components/widgets/ProgressMeter.svelte';
  import YieldCalc from '$lib/components/widgets/YieldCalc.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import { THEMES } from '$lib/themes.js';

  export let blocks = [];
  export let theme = null;

  $: t = theme ?? THEMES.standard;

  // Callout icons accept either an emoji ("⚡") or a Phosphor icon name
  // ("coffee-bean") — names would otherwise render as literal words.
  const isIconName = (s) => /^[a-z0-9-]+$/.test(s || '');

  // Progress meter always appears on a light card — use slight tint for white body bg.
  $: progressBg = t.body.bg === 'white' ? 'hsl(26 40% 96%)' : t.body.bg;
</script>

<div
  class="post-body"
  style="
    background: {t.body.bg};
    border: 1px solid {t.body.border};
    border-radius: 16px;
    padding: 36px 48px;
    box-shadow: 0 1px 0 hsl(0 0% 100%) inset, 0 10px 24px -18px hsl(24 30% 20% / 0.22);
  "
>
  {#each blocks as b, i}
    {#if b.kind === 'p'}
      <p
        class:is-drop-cap={t.dropCap && i === 0}
        style="font-size: 16.5px; line-height: 1.68; margin: 0 0 16px; color: {t.body.text}; text-wrap: pretty;"
      >{b.text}</p>

    {:else if b.kind === 'h2'}
      <h2
        style="
          font-size: 22px; font-weight: 700; margin: 2em 0 0.45em;
          letter-spacing: -0.015em; line-height: 1.25; color: {t.body.heading};
        "
      >{b.text}</h2>

    {:else if b.kind === 'ul'}
      <ul style="margin: 0 0 16px; padding-left: 22px; line-height: 1.68; list-style: disc;">
        {#each b.items as item}
          <li style="margin: 5px 0; font-size: 16px; color: {t.body.text};">{item}</li>
        {/each}
      </ul>

    {:else if b.kind === 'callout'}
      <div
        style="
          display: flex; gap: 14px; align-items: flex-start;
          border-radius: 12px; margin: 20px 0;
          background: {t.calloutBg};
          border: 1px solid {t.accent}55;
          padding: 18px 22px;
        "
      >
        <span
          style="
            display: inline-flex; align-items: center; justify-content: center;
            width: 40px; height: 40px; flex-shrink: 0;
            border-radius: 10px;
            background: {t.accent}22;
            border: 1px solid {t.accent}44;
            font-size: 19px; line-height: 1;
            color: {t.accent};
          "
        >{#if isIconName(b.icon)}<Icon name={b.icon} size={20} />{:else}{b.icon}{/if}</span>
        <div>
          {#if b.title}
            <div style="font-size: 15.5px; font-weight: 700; margin-bottom: 4px; color: {t.body.heading};">{b.title}</div>
          {/if}
          {#if b.text}
            <div style="font-size: 14.5px; line-height: 1.55; color: {t.body.text};">{b.text}</div>
          {/if}
        </div>
      </div>

    {:else if b.kind === 'stats'}
      <StatsBar
        items={b.items}
        bg={t.stats.bg}
        border={t.stats.border}
        valueColor={t.stats.value}
        labelColor={t.stats.label}
      />

    {:else if b.kind === 'chart'}
      <ChartBlock
        points={b.points}
        chartType={b.chartType}
        title={b.title}
        color={t.chartColor}
        bodyBg={t.body.bg}
        bodyBorder={t.body.border}
        textColor={t.body.heading}
      />

    {:else if b.kind === 'roadmap'}
      <RoadmapBlock
        phases={b.phases}
        accent={t.accent}
        dark={t.stats.bg}
        bodyBg={t.body.bg}
        bodyBorder={t.body.border}
      />

    {:else if b.kind === 'progress'}
      <ProgressMeter
        value={b.value}
        max={b.max}
        label={b.label}
        sub={b.sub}
        accent={t.accent}
        bg={progressBg}
        border={t.body.border}
        textColor={t.body.heading}
        subColor={t.body.text}
      />

    {:else if b.kind === 'calculator'}
      <YieldCalc
        apy={b.apy}
        max={b.max}
        min={b.min}
        step={b.step}
        currency={b.currency}
        bg={t.stats.bg}
        border={t.accent}
        accent={t.accent}
        text={t.hero.text}
        sub={t.hero.sub}
        cardBg={t.calcCardBg ?? t.stats.bg}
        cardBorder={t.stats.border}
      />
    {/if}
  {/each}
</div>

<style>
  /* Drop cap on first paragraph when theme opts in */
  .is-drop-cap::first-letter {
    float: left;
    font-size: 4.4em;
    line-height: 0.82;
    margin: 0.06em 0.12em 0 0;
    font-weight: 800;
  }

  @media (max-width: 640px) {
    .post-body {
      padding: 24px 20px;
      border-radius: 12px;
    }
  }
</style>
