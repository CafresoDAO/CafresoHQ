<script>
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import Icon from '$lib/components/Icon.svelte';
  import { getProject, STATUS } from '$lib/data/projects.js';
  import { listPosts } from '$lib/api/devlog.js';
  import { fmtDate } from '$lib/data/blog.js';

  $: slug = $page.params.slug;
  $: project = getProject(slug);
  $: st = project ? STATUS[project.status] : null;

  // Live dev-log feed for this project: pull all posts, filter to this
  // project's category. Seed fallback keeps SSR/preview from blanking.
  let posts = [];
  let loadingPosts = true;

  async function loadFeed(cat) {
    loadingPosts = true;
    try {
      const all = await listPosts();
      posts = (all || [])
        .filter((p) => p.cat === cat)
        .sort((a, b) => (b.date || '').localeCompare(a.date || ''))
        .slice(0, 6);
    } catch (_e) {
      posts = [];
    } finally {
      loadingPosts = false;
    }
  }

  $: if (project) loadFeed(project.devlogCat);

  function isExternal(href) {
    return /^https?:\/\//.test(href || '');
  }
</script>

<svelte:head>
  <title>{project ? `${project.name} · Cafreso` : 'Project · Cafreso'}</title>
  {#if project}
    <meta name="description" content={project.summary} />
    <link rel="canonical" href={`https://cafreso.com/projects/${project.slug}`} />
  {/if}
</svelte:head>

{#if !project}
  <section class="mx-auto w-full max-w-2xl px-5 py-20 text-center">
    <h1 class="font-serif-display text-2xl font-semibold text-foreground">Project not found</h1>
    <p class="mt-3 text-ink-500">That project doesn't exist (yet).</p>
    <a href="/projects" class="mt-6 inline-block text-brand-600 hover:underline dark:text-brand-300">← All projects</a>
  </section>
{:else}
  <section class="mx-auto w-full max-w-3xl px-5 py-10 sm:py-12">
    <a href="/projects" class="text-sm text-ink-400 hover:text-ink-600 dark:hover:text-ink-200">← Projects</a>

    <!-- Header -->
    <header class="mt-5 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div class="flex items-start gap-4">
        <span
          class="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl"
          style={`background: hsl(${project.accent} 70% 92%); color: hsl(${project.accent} 60% 32%);`}
        >
          <Icon name={project.icon} size={28} />
        </span>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="font-serif-display text-3xl font-semibold tracking-tight text-foreground">{project.name}</h1>
            <span
              class="rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide"
              style={`background: hsl(${st.hue} 65% 92%); color: hsl(${st.hue} 55% 30%);`}
            >{st.label}</span>
          </div>
          <p class="mt-1 text-[15px] text-ink-500">{project.tagline}</p>
        </div>
      </div>
      <div class="flex shrink-0 gap-2">
        {#if project.url}
          <a
            href={project.url}
            data-sveltekit-reload={isExternal(project.url) ? 'on' : undefined}
            rel="noopener"
            class="inline-flex items-center gap-1.5 rounded-full bg-brand-500 px-4 py-2 text-sm font-medium text-ink-900 transition hover:bg-brand-400"
          >
            Open <Icon name="arrow-right" size={15} />
          </a>
        {/if}
        {#if project.repo}
          <a
            href={project.repo}
            target="_blank"
            rel="noopener"
            class="inline-flex items-center gap-1.5 rounded-full border border-ink-200/70 px-4 py-2 text-sm font-medium text-ink-600 transition hover:border-ink-300 dark:border-ink-700 dark:text-ink-300"
          >
            Code
          </a>
        {/if}
      </div>
    </header>

    <p class="mt-6 text-[15px] leading-7 text-ink-600 dark:text-ink-300">{project.summary}</p>

    <!-- What it does -->
    <section class="mt-9">
      <h2 class="text-sm font-medium uppercase tracking-wider text-ink-400">What it does</h2>
      <ul class="mt-3 space-y-2">
        {#each project.what as item}
          <li class="flex items-start gap-2.5 text-[15px] leading-6 text-ink-600 dark:text-ink-300">
            <Icon name="check" size={16} class="mt-1 shrink-0 text-brand-500" />
            <span>{item}</span>
          </li>
        {/each}
      </ul>
    </section>

    <!-- Roadmap — the planned future updates -->
    <section class="mt-9">
      <h2 class="text-sm font-medium uppercase tracking-wider text-ink-400">Roadmap</h2>
      <ol class="roadmap mt-4 space-y-0">
        {#each project.roadmap as step, i}
          <li class="flex gap-3.5">
            <div class="flex flex-col items-center">
              <span
                class="mt-1 flex h-4 w-4 items-center justify-center rounded-full border-2"
                class:done={step.done}
                style={step.done
                  ? `background: hsl(${project.accent} 60% 50%); border-color: hsl(${project.accent} 60% 50%);`
                  : 'border-color: hsl(var(--ink-300));'}
              >
                {#if step.done}<Icon name="check" size={10} class="text-white" />{/if}
              </span>
              {#if i < project.roadmap.length - 1}
                <span class="w-0.5 flex-1 bg-ink-200/70 dark:bg-ink-700"></span>
              {/if}
            </div>
            <div class="pb-5">
              <span class="text-[11px] font-semibold uppercase tracking-wide text-ink-400">{step.when}</span>
              <p class="text-[15px] leading-6 text-ink-700 dark:text-ink-200" class:opacity-60={step.done}>{step.title}</p>
            </div>
          </li>
        {/each}
      </ol>
    </section>

    <!-- Live dev log feed -->
    <section class="mt-9">
      <div class="flex items-baseline justify-between">
        <h2 class="text-sm font-medium uppercase tracking-wider text-ink-400">From the dev log</h2>
        <a href={`/blog?cat=${project.devlogCat}`} class="text-sm text-brand-600 hover:underline dark:text-brand-300">All posts →</a>
      </div>

      {#if loadingPosts}
        <div class="mt-4 space-y-3">
          {#each Array(3) as _}
            <div class="h-16 animate-pulse rounded-xl bg-ink-100 dark:bg-ink-800/60"></div>
          {/each}
        </div>
      {:else if posts.length === 0}
        <div class="mt-4 rounded-xl border border-dashed border-ink-200/70 p-6 text-center dark:border-ink-700">
          <p class="text-sm text-ink-500">No posts tagged for this project yet — updates land here as we ship.</p>
        </div>
      {:else}
        <ul class="mt-4 divide-y divide-ink-200/60 dark:divide-ink-700/60">
          {#each posts as post}
            <li>
              <a href={`/blog/${post.slug}`} class="group flex items-start justify-between gap-4 py-3">
                <div class="min-w-0">
                  <p class="font-medium text-foreground group-hover:text-brand-600 dark:group-hover:text-brand-300">{post.title}</p>
                  {#if post.excerpt}
                    <p class="mt-0.5 truncate text-sm text-ink-400">{post.excerpt}</p>
                  {/if}
                </div>
                <span class="shrink-0 whitespace-nowrap pt-0.5 text-xs text-ink-400">{fmtDate(post.date)}</span>
              </a>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  </section>
{/if}
