<script>
  import { goto } from '$app/navigation';
  import Icon from '$lib/components/Icon.svelte';
  import { aiSearchOpen, aiSearchPrefill } from '$lib/stores/blog.js';
  import { PROJECTS, HOME_ORDER, STATUS } from '$lib/data/projects.js';
  import { bbLinks, aiCafresoOrigin } from '$lib/links.js';

  // The homepage is deliberately spare: a wordmark, one on-chain search box,
  // and a quiet row of the software we build in the open. Everything deeper
  // (the farm story, the protocol breakdown, the DAO) lives one click away on
  // /about, /how-it-works, and /projects — the homepage stops trying to be all
  // of them at once.

  let q = '';

  function runSearch() {
    const term = q.trim();
    if (!term) {
      aiSearchOpen.set(true);
      return;
    }
    aiSearchPrefill.set(term);
    aiSearchOpen.set(true);
  }

  // The two flagships first, then the rest — resolved from the shared portfolio.
  const featured = HOME_ORDER.map((slug) => PROJECTS.find((p) => p.slug === slug)).filter(Boolean);

  const quickLinks = [
    { label: 'Projects', href: '/projects' },
    { label: 'Library', href: '/library' },
    { label: 'Shop', href: '/shop' },
    { label: 'Dev Log', href: '/blog' },
    { label: 'How it works', href: '/how-it-works' }
  ];
</script>

<svelte:head>
  <title>Cafreso · open software on the Internet Computer</title>
  <meta
    name="description"
    content="Cafreso builds AI agents, an on-chain research library, and self-custody banking — open software on the Internet Computer, owned by the community. Search it, or explore what we're building."
  />
  <link rel="canonical" href="https://cafreso.com" />
  <meta property="og:title" content="Cafreso · open software on the Internet Computer" />
  <meta
    property="og:description"
    content="AI agents you own, a community-grown research library, and self-custody banking — all on the Internet Computer."
  />
  <meta property="og:url" content="https://cafreso.com" />
  <meta property="og:type" content="website" />
  <meta property="og:image" content="/assets/cafreso-wordmark.png" />
</svelte:head>

<section class="home mx-auto flex w-full max-w-3xl flex-col items-center px-5 text-center">
  <!-- Wordmark lockup — the brand mark itself, keyed to transparency so the
       black ink art inverts cleanly to white between themes (ink on cream,
       chalk on coffee). A soft gold glow sits behind it for depth. -->
  <h1 class="wordmark-lockup mt-[10vh]">
    <span class="wordmark-glow" aria-hidden="true"></span>
    <img
      src="/assets/cafreso-wordmark-alpha.png"
      alt="Cafreso — a blockchain DAO"
      class="wordmark-img"
      width="1039"
      height="544"
      fetchpriority="high"
    />
  </h1>
  <p class="wordmark-sub mt-5 text-sm text-ink-400 sm:text-base">
    Open software on the Internet Computer, owned by the community.
  </p>

  <!-- The one search box -->
  <form
    class="search-box mt-8 flex w-full items-center gap-2 rounded-full border border-ink-200/70 bg-background px-5 py-3 shadow-sm transition focus-within:border-brand-400 focus-within:shadow-md dark:border-ink-700"
    on:submit|preventDefault={runSearch}
  >
    <Icon name="magnifying-glass" size={20} class="shrink-0 text-ink-400" />
    <input
      bind:value={q}
      type="text"
      placeholder="Ask the on-chain library anything…"
      aria-label="Search the on-chain library"
      autocomplete="off"
      class="min-w-0 flex-1 border-0 bg-transparent text-[15px] text-foreground outline-none placeholder:text-ink-400"
    />
    {#if q.trim()}
      <button type="submit" class="shrink-0 rounded-full bg-brand-500 px-4 py-1.5 text-sm font-medium text-ink-900 transition hover:bg-brand-400">
        Search
      </button>
    {/if}
  </form>
  <p class="mt-2 text-xs text-ink-400">
    Answered from a public library, or by the community search network. No sign-in needed.
  </p>

  <!-- Quiet quick links -->
  <nav class="quick-links mt-7 flex flex-wrap items-center justify-center gap-x-6 gap-y-2">
    {#each quickLinks as l}
      <a href={l.href} class="text-sm text-ink-500 underline-offset-4 transition hover:text-brand-600 hover:underline dark:hover:text-brand-300">
        {l.label}
      </a>
    {/each}
  </nav>

  <!-- What we build — the portfolio, at a glance -->
  <div class="projects-strip mt-16 w-full text-left">
    <div class="mb-4 flex items-baseline justify-between">
      <h2 class="text-sm font-medium uppercase tracking-wider text-ink-400">What we build</h2>
      <a href="/projects" class="text-sm text-brand-600 hover:underline dark:text-brand-300">All projects →</a>
    </div>
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {#each featured as p}
        {@const st = STATUS[p.status]}
        <a
          href={`/projects/${p.slug}`}
          class="project-card group flex items-start gap-3 rounded-2xl border border-ink-200/60 bg-background p-4 transition hover:border-brand-300 hover:shadow-sm dark:border-ink-700/70 dark:hover:border-brand-500/50"
        >
          <span
            class="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl"
            style={`background: hsl(${p.accent} 70% 92%); color: hsl(${p.accent} 60% 32%);`}
          >
            <Icon name={p.icon} size={18} />
          </span>
          <span class="min-w-0 flex-1">
            <span class="flex items-center gap-2">
              <span class="font-medium text-foreground">{p.name}</span>
              <span
                class="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
                style={`background: hsl(${st.hue} 65% 92%); color: hsl(${st.hue} 55% 30%);`}
              >{st.label}</span>
            </span>
            <span class="mt-0.5 block truncate text-sm text-ink-400">{p.tagline}</span>
          </span>
        </a>
      {/each}
    </div>
  </div>

  <!-- Thin footer strip -->
  <div class="foot mt-16 mb-10 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-xs text-ink-400">
    <a href="/about" class="hover:text-ink-600 dark:hover:text-ink-200">About</a>
    <a href={aiCafresoOrigin} class="hover:text-ink-600 dark:hover:text-ink-200">CafresoHQ</a>
    <a href={bbLinks.mine} data-sveltekit-reload="on" rel="noopener" class="hover:text-ink-600 dark:hover:text-ink-200">Banking.Brave</a>
    <a href="https://github.com/CafresoDAO/CafresoHQ" target="_blank" rel="noopener" class="hover:text-ink-600 dark:hover:text-ink-200">GitHub</a>
    <span>·</span>
    <span>On the Internet Computer</span>
  </div>
</section>

<style>
  .wordmark-lockup {
    position: relative;
    display: flex;
    justify-content: center;
    width: 100%;
    margin-bottom: 0;
    animation: wm-rise 0.7s cubic-bezier(0.2, 0.8, 0.2, 1) both;
  }
  .wordmark-img {
    position: relative;
    z-index: 1;
    width: clamp(258px, 62vw, 560px);
    height: auto;
    /* Light: the art is already black ink — a soft shadow lifts it off the
       cream. */
    filter: drop-shadow(0 8px 22px hsl(24 40% 20% / 0.14));
  }
  /* Dark: invert the ink to a WARM paper tone (not stark white) so the mark
     sits in the coffee palette — invert to white, then sepia/hue warm it to a
     cream ivory. The tiles read as clean negative tiles either way. */
  :global(.dark) .wordmark-img {
    filter: invert(1) sepia(0.34) saturate(1.45) hue-rotate(-8deg) brightness(1.03)
      drop-shadow(0 10px 26px hsl(0 0% 0% / 0.55));
  }
  /* Warm halo behind the mark — gold in light, a deeper ember in dark. */
  .wordmark-glow {
    position: absolute;
    z-index: 0;
    top: 50%;
    left: 50%;
    width: 84%;
    height: 162%;
    transform: translate(-50%, -50%);
    background: radial-gradient(ellipse at center, hsl(45 95% 58% / 0.44), transparent 70%);
    filter: blur(26px);
    pointer-events: none;
  }
  :global(.dark) .wordmark-glow {
    background: radial-gradient(ellipse at center, hsl(40 90% 50% / 0.36), transparent 68%);
  }
  @keyframes wm-rise {
    from { opacity: 0; transform: translateY(16px); }
  }
  @media (prefers-reduced-motion: reduce) {
    .wordmark-lockup { animation: none; }
    .search-box, .project-card { transition: none; }
  }
</style>
