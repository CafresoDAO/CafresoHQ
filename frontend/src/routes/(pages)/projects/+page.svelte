<script>
  import Icon from '$lib/components/Icon.svelte';
  import { PROJECTS, STATUS, ECOSYSTEM_ROADMAP } from '$lib/data/projects.js';

  // Portfolio index — every piece of open software we build, tied together in
  // one place. Cards link to /projects/[slug] where the roadmap + live dev-log
  // feed live. Deliberately calm: this is a directory, not a pitch.
</script>

<svelte:head>
  <title>Projects · Cafreso</title>
  <meta
    name="description"
    content="The open software Cafreso builds on the Internet Computer — AI agents, a community research library, self-custody banking, and more. Each with a live dev log and public roadmap."
  />
  <link rel="canonical" href="https://cafreso.com/projects" />
</svelte:head>

<section class="mx-auto w-full max-w-4xl px-5 py-10 sm:py-14">
  <header class="mb-10">
    <p class="text-sm font-medium uppercase tracking-wider text-ink-400">Projects</p>
    <h1 class="mt-2 font-serif-display text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
      Everything we build, in the open.
    </h1>
    <p class="mt-3 max-w-2xl text-[15px] leading-7 text-ink-500">
      Cafreso is a handful of open-source projects on the Internet Computer, stitched
      together by one Internet Identity. Each has a live dev log and a public roadmap —
      pick one to see what it does, where it's going, and what shipped this week.
    </p>
  </header>

  <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
    {#each PROJECTS as p}
      {@const st = STATUS[p.status]}
      <a
        href={`/projects/${p.slug}`}
        class="group flex flex-col rounded-2xl border border-ink-200/60 bg-background p-5 transition hover:border-brand-300 hover:shadow-md dark:border-ink-700/70 dark:hover:border-brand-500/50"
      >
        <div class="flex items-center gap-3">
          <span
            class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl"
            style={`background: hsl(${p.accent} 70% 92%); color: hsl(${p.accent} 60% 32%);`}
          >
            <Icon name={p.icon} size={22} />
          </span>
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <span class="font-medium text-foreground">{p.name}</span>
              <span
                class="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
                style={`background: hsl(${st.hue} 65% 92%); color: hsl(${st.hue} 55% 30%);`}
              >{st.label}</span>
            </div>
            <div class="truncate text-sm text-ink-400">{p.tagline}</div>
          </div>
        </div>
        <p class="mt-3 text-sm leading-6 text-ink-500 line-clamp-3">{p.summary}</p>
        <span class="mt-4 text-sm font-medium text-brand-600 group-hover:underline dark:text-brand-300">
          Explore →
        </span>
      </a>
    {/each}
  </div>

  <!-- ── The ecosystem arc: Now → Next → the .brave era ─────────────────── -->
  <div class="mt-16">
    <p class="text-sm font-medium uppercase tracking-wider text-ink-400">Roadmap</p>
    <h2 class="mt-2 font-serif-display text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
      The road to .brave
    </h2>
    <p class="mt-3 max-w-2xl text-[15px] leading-7 text-ink-500">
      Every project above feeds one arc: a real, gold-backed on-chain economy today — and
      when the .brave domain resolves in browsers, <b>minegold.brave</b> where Brave users
      turn their monthly BAT ad earnings into gold, with <b>banking.brave</b> as the DeFi
      surface underneath.
    </p>

    <div class="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
      {#each ECOSYSTEM_ROADMAP as stage}
        <div class="rounded-2xl border border-ink-200/60 bg-background p-5 dark:border-ink-700/70">
          <span
            class="inline-block rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
            style={`background: hsl(${stage.tone} 65% 92%); color: hsl(${stage.tone} 55% 30%);`}
          >{stage.era}</span>
          <h3 class="mt-3 font-medium text-foreground">{stage.title}</h3>
          <ul class="mt-3 space-y-2.5">
            {#each stage.items as it}
              <li class="flex items-start gap-2 text-sm leading-6 text-ink-500">
                {#if it.done}
                  <span class="mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold"
                    style="background: hsl(152 65% 90%); color: hsl(152 55% 28%);">✓</span>
                {:else}
                  <span class="mt-1 h-4 w-4 shrink-0 rounded-full border border-ink-300 dark:border-ink-600"></span>
                {/if}
                <span>{it.text}</span>
              </li>
            {/each}
          </ul>
        </div>
      {/each}
    </div>

    <p class="mt-6 text-sm leading-6 text-ink-400">
      Argue with this plan on the
      <a href="/forums/gold-economy-and-the-road-to-brave" class="font-medium text-brand-600 underline dark:text-brand-300">forums</a>
      — the roadmap is a living document, and the discussion is on-chain.
    </p>
  </div>
</section>

<style>
  .line-clamp-3 {
    display: -webkit-box;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
</style>
