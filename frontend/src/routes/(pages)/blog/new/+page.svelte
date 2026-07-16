<svelte:options runes={true} />

<script>
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { browser } from '$app/environment';
  import { onMount, tick } from 'svelte';
  import Icon from '$lib/components/Icon.svelte';
  import Button from '$lib/components/Button.svelte';
  import CategoryTag from '$lib/components/CategoryTag.svelte';
  import PostRenderer from '$lib/components/PostRenderer.svelte';
  import { CATEGORIES, POSTS as SEED_POSTS, postHeroImg } from '$lib/data/blog.js';
  import { upsertPost, getPost } from '$lib/api/devlog.js';
  import { isAuthenticated, principalText, authStatus, login } from '$lib/stores/auth.js';
  import { profile } from '$lib/stores/profile.js';
  import { isDevlogAdmin } from '$lib/data/admins.js';
  import { parseBlocks, blocksToMarkdown, readMinutes, slugify, WIDGET_SNIPPETS } from '$lib/markdown.js';
  import { THEME_LIST, getTheme, layoutFromTheme } from '$lib/themes.js';

  // Form state
  let title = $state('');
  let slug = $state('');
  let slugTouched = $state(false);
  let category = $state('build-log');
  let theme = $state('standard');
  let excerpt = $state('');
  let pinned = $state(false);
  let authorRole = $state('Core team');
  let hero = $state('roaster');
  // Preserved from the loaded post in edit mode so saving doesn't silently
  // rewrite the original publish date.
  let originalDate = $state(null);
  let bodySrc = $state('');

  const HEROES = [
    { key: 'roaster', label: 'Roaster', desc: 'Warm beige, coffee gear' },
    { key: 'farm', label: 'Farm', desc: 'Pixel-art finca greens' },
    { key: 'banking-brave', label: 'Banking.Brave', desc: 'Navy + gold crest' },
  ];
  let previewing = $state(false);
  let submitting = $state(false);
  let err = $state(null);
  let savedSlug = $state(null);

  // Draft autosave
  let bodyTextarea;
  let draftKey = $derived(editSlug ? `cafreso:draft:edit:${editSlug}` : 'cafreso:draft:new');
  let draftSavedAt = $state(null);
  let hasDraft = $state(false);
  let draftLoaded = $state(false);

  function readDraft(key) {
    if (!browser) return null;
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  function writeDraft(key) {
    if (!browser) return;
    try {
      localStorage.setItem(
        key,
        JSON.stringify({
          title, slug, slugTouched, category, theme, excerpt,
          pinned, authorRole, hero, bodySrc, savedAt: Date.now()
        })
      );
      draftSavedAt = Date.now();
    } catch {}
  }

  function clearDraft(key) {
    if (!browser) return;
    try { localStorage.removeItem(key); } catch {}
    draftSavedAt = null;
    hasDraft = false;
  }

  function applyDraft(d) {
    if (!d) return;
    title = d.title ?? '';
    slug = d.slug ?? '';
    slugTouched = !!d.slugTouched;
    category = d.category ?? 'build-log';
    // backward compat: old drafts had layout instead of theme
    theme = d.theme ?? (d.layout === 'banking-brave' ? 'banking-brave' : 'standard');
    excerpt = d.excerpt ?? '';
    pinned = !!d.pinned;
    authorRole = d.authorRole ?? 'Core team';
    hero = d.hero ?? 'roaster';
    bodySrc = d.bodySrc ?? '';
    draftSavedAt = d.savedAt ?? null;
  }

  onMount(() => {
    if (!editSlug) {
      const d = readDraft('cafreso:draft:new');
      hasDraft = !!(d && (d.title || d.bodySrc || d.excerpt));
    }
    draftLoaded = true;
  });

  let saveTimer;
  $effect(() => {
    const _ = [title, slug, slugTouched, category, theme, excerpt, pinned, authorRole, hero, bodySrc];
    if (!browser || !draftLoaded || loadingEdit) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => writeDraft(draftKey), 600);
  });

  // Body textarea toolbar — inserts markdown-lite snippets at the cursor.
  async function insertSnippet(before, placeholder = '', after = '') {
    if (!bodyTextarea) return;
    const el = bodyTextarea;
    const start = el.selectionStart ?? bodySrc.length;
    const end = el.selectionEnd ?? bodySrc.length;
    const hasSel = end > start;
    const selection = hasSel ? bodySrc.slice(start, end) : placeholder;
    const insert = `${before}${selection}${after}`;
    bodySrc = bodySrc.slice(0, start) + insert + bodySrc.slice(end);
    await tick();
    const pos = start + before.length + selection.length;
    el.focus();
    el.setSelectionRange(pos, pos);
  }

  const TOOLBAR_TEXT = [
    { label: 'H2', icon: 'text-h-two', title: 'Section heading', action: () => insertSnippet('\n\n## ', 'Heading', '\n') },
    { label: '', icon: 'list-bullets', title: 'Bulleted list', action: () => insertSnippet('\n- ', 'First item', '\n- Second\n') },
    { label: '', icon: 'quotes', title: 'Callout', action: () => insertSnippet('\n> ⚡ | ', 'Callout title | body text', '\n') },
    { label: '', icon: 'paragraph', title: 'Paragraph break', action: () => insertSnippet('\n\n', '', '') },
  ];

  const TOOLBAR_WIDGETS = [
    { label: 'Stats', icon: 'chart-bar', title: 'Insert stats bar', action: () => insertSnippet('\n', WIDGET_SNIPPETS.stats, '\n') },
    { label: 'Chart', icon: 'chart-line-up', title: 'Insert area chart', action: () => insertSnippet('\n', WIDGET_SNIPPETS.chart, '\n') },
    { label: 'Roadmap', icon: 'map-trifold', title: 'Insert roadmap timeline', action: () => insertSnippet('\n', WIDGET_SNIPPETS.roadmap, '\n') },
    { label: 'Progress', icon: 'gauge', title: 'Insert progress meter', action: () => insertSnippet('\n', WIDGET_SNIPPETS.progress, '\n') },
    { label: 'Calc', icon: 'calculator', title: 'Insert yield calculator', action: () => insertSnippet('\n', WIDGET_SNIPPETS.calculator, '\n') },
  ];

  function clearAndStartOver() {
    if (!confirm('Clear the draft and start over?')) return;
    title = '';
    slug = '';
    slugTouched = false;
    category = 'build-log';
    theme = 'standard';
    excerpt = '';
    pinned = false;
    authorRole = 'Core team';
    hero = 'roaster';
    bodySrc = '';
    err = null;
    clearDraft(draftKey);
  }

  // Edit mode
  const editSlug = $derived($page.url.searchParams.get('edit'));
  const isEditing = $derived(!!editSlug);
  let loadedEditSlug = null;
  let loadingEdit = $state(false);

  $effect(() => {
    if (!editSlug || editSlug === loadedEditSlug) return;
    loadedEditSlug = editSlug;
    hydrateForEdit(editSlug);
  });

  async function hydrateForEdit(s) {
    loadingEdit = true;
    try {
      const live = await getPost(s);
      const seed = SEED_POSTS.find((p) => p.slug === s);
      const src = live || seed;
      if (!src) {
        err = `No post found with slug "${s}".`;
        return;
      }
      title = src.title || '';
      slug = src.slug || s;
      slugTouched = true;
      category = src.cat || src.category || 'build-log';
      theme = src.theme || (src.layout === 'banking-brave' ? 'banking-brave' : 'standard');
      excerpt = src.excerpt || '';
      pinned = !!src.pinned;
      authorRole = src.author?.role || 'Core team';
      hero = src.hero || 'roaster';
      originalDate = src.date || null;
      bodySrc = blocksToMarkdown(src.body || []);
    } finally {
      loadingEdit = false;
    }
  }

  // Derivations
  const canAuthor = $derived(isDevlogAdmin($principalText));
  const authorName = $derived($profile.name || 'Cafreso DAO');
  const authorHue = $derived(24);
  const blocks = $derived(parseBlocks(bodySrc));
  const readMin = $derived(readMinutes(bodySrc));
  const slugPreview = $derived(slug || slugify(title));
  const validationError = $derived(validate());
  const heading = $derived(isEditing ? 'Edit post' : 'Write a new post');
  const submitLabel = $derived(isEditing ? 'Save changes' : 'Publish to canister');
  const selectedTheme = $derived(getTheme(theme));

  function deriveExcerpt() {
    if (excerpt.trim()) return excerpt.trim();
    const firstPara = (bodySrc || '')
      .split(/\n\s*\n/)
      .map((p) => p.trim())
      .find((p) => p && !p.startsWith('##') && !p.startsWith('- ') && !p.startsWith('> ') && !p.startsWith('::'));
    if (!firstPara) return '';
    if (firstPara.length <= 240) return firstPara;
    return firstPara.slice(0, 237).trimEnd() + '…';
  }

  function validate() {
    if (!title.trim()) return 'Add a title.';
    if (!slugPreview) return 'Slug is empty — fix the title or set one manually.';
    if (!/^[a-z0-9-]+$/.test(slugPreview)) return 'Slug may only contain lowercase letters, numbers, and dashes.';
    if (!bodySrc.trim()) return 'The post body is empty.';
    if (excerpt.length > 280) return 'Excerpt is over 280 characters.';
    return null;
  }

  $effect(() => {
    if (slugTouched) return;
    slug = slugify(title);
  });

  async function submit() {
    err = null;
    const bad = validate();
    if (bad) {
      err = bad;
      return;
    }
    submitting = true;
    const finalExcerpt = deriveExcerpt();
    const result = await upsertPost({
      slug: slugPreview,
      title: title.trim(),
      cat: category,
      layout: layoutFromTheme(theme),
      theme,
      author: { name: authorName, hue: authorHue, role: authorRole.trim() || 'Core team' },
      date: (isEditing && originalDate) || new Date().toISOString().slice(0, 10),
      readMin,
      excerpt: finalExcerpt,
      hero,
      pinned,
      body: blocks,
      canister: 'bek5d-2…rq-cai',
      block: 0
    });
    submitting = false;
    if (result.err) {
      err = result.err;
      return;
    }
    savedSlug = result.ok?.slug || slugPreview;
    clearDraft(draftKey);
    setTimeout(() => goto(`/blog/${savedSlug}`), 600);
  }
</script>

<svelte:head><title>{heading} · Cafreso Dev Log</title></svelte:head>

<section class="mx-auto px-4 sm:px-[18px] pt-6 sm:pt-8 pb-24" style="max-width: 820px;">
  <a
    href="/blog"
    class="inline-flex items-center gap-1.5 text-[12.5px] no-underline mb-4"
    style="color: hsl(var(--pg-fg-muted));"
  >
    <Icon name="caret-left" size={13} /> Back to Dev Log
  </a>

  <div class="flex items-center gap-2 text-[13px] font-medium mb-3" style="color: hsl(var(--pg-eyebrow));">
    <Icon name={isEditing ? 'pencil-line' : 'pencil-simple'} size={16} />
    {isEditing ? 'Editing existing post' : 'Author tools'}
  </div>
  <h1 class="font-bold leading-tight mb-2" style="font-size: clamp(26px, 5vw, 36px); color: hsl(var(--pg-fg));">
    {heading}
  </h1>
  <p class="text-[14.5px] leading-[1.55] mb-6 sm:mb-8 max-w-[560px]" style="color: hsl(var(--pg-fg-muted));">
    {#if isEditing}
      Updating <code style="font-size: 12.5px;">/blog/{editSlug}</code>. The canister's <code style="font-size: 12.5px;">upsertPost</code> keys by slug, so saving overwrites the existing post.
    {:else}
      Posts are signed with your Internet Identity and persisted on the devlog canister. Only allowlisted admins can publish — the canister rejects anyone else.
    {/if}
  </p>

  {#if loadingEdit}
    <div class="rounded-[10px] px-3 py-2 text-[13px] inline-flex items-center gap-2 mb-4"
      style="background: hsl(45 80% 94%); color: hsl(32 56% 25%); border: 1px solid hsl(45 75% 72%);"
    >
      <Icon name="spinner-gap" size={13} /> Loading post…
    </div>
  {/if}

  {#if !$isAuthenticated}
    <div
      class="rounded-[14px] p-6 sm:p-8 text-center"
      style="background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border));"
    >
      <Icon name="fingerprint" size={28} style="color: hsl(32 56% 35%);" />
      <h2 class="text-[18px] font-bold mt-3 mb-2" style="color: hsl(var(--pg-fg));">Sign in to write</h2>
      <p class="text-[13.5px] mb-5 max-w-[360px] mx-auto" style="color: hsl(var(--pg-fg-muted));">
        Connect your Internet Identity so the canister can verify you're an admin.
      </p>
      <Button on:click={login} disabled={$authStatus === 'logging-in'}>
        <Icon name="fingerprint" size={15} /> Sign in
      </Button>
    </div>
  {:else if !canAuthor}
    <div
      class="rounded-[14px] p-5 sm:p-6"
      style="background: hsl(0 70% 96%); border: 1px solid hsl(0 70% 80%); color: hsl(0 70% 30%);"
    >
      <div class="flex items-center gap-2 font-semibold mb-1.5">
        <Icon name="lock" size={16} /> Not on the author allowlist
      </div>
      <p class="text-[13.5px] leading-[1.55]" style="color: hsl(0 65% 30%);">
        Your principal isn't registered as a devlog admin. Ask an existing admin to call <code>addAdmin</code> with your principal:
      </p>
      <code class="block mt-2 text-[11.5px] font-mono break-all p-2 rounded-[8px]"
        style="background: hsl(0 0% 100%); color: hsl(222 47% 11%); border: 1px solid hsl(0 70% 80%);"
      >{$principalText}</code>
    </div>
  {:else}
    <!-- Resume-draft banner -->
    {#if !isEditing && hasDraft && !title && !bodySrc}
      <div class="rounded-[14px] px-4 py-3 mb-4 flex flex-col sm:flex-row items-start sm:items-center gap-3"
        style="background: hsl(45 80% 94%); border: 1px solid hsl(45 75% 75%); color: hsl(32 56% 25%);"
      >
        <Icon name="bookmark-simple" size={16} />
        <div class="flex-1 text-[13px]">You have an unsaved draft from a previous session.</div>
        <div class="flex gap-2">
          <Button size="sm" on:click={() => { applyDraft(readDraft(draftKey)); hasDraft = false; }}>Resume</Button>
          <Button size="sm" variant="ghost" on:click={() => { clearDraft(draftKey); hasDraft = false; }}>Discard</Button>
        </div>
      </div>
    {/if}

    <div class="grid grid-cols-1 gap-4 sm:gap-5">
      <!-- Title + slug -->
      <div class="rounded-[14px] p-4 sm:p-5" style="background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border));">
        <label class="block text-[11.5px] font-semibold uppercase tracking-wide mb-1.5" style="color: hsl(var(--pg-fg-muted));" for="post-title">Title</label>
        <input
          id="post-title"
          bind:value={title}
          placeholder="Week 43: what we shipped"
          class="w-full text-[18px] sm:text-[20px] font-bold rounded-[10px] px-3 py-2.5 outline-none"
          style="background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border)); color: hsl(var(--pg-fg));"
        />

        <label class="block text-[11.5px] font-semibold uppercase tracking-wide mt-4 mb-1.5" style="color: hsl(var(--pg-fg-muted));" for="post-slug">
          URL slug <span class="font-normal normal-case" style="color: hsl(var(--pg-fg-subtle));">(auto from title)</span>
        </label>
        <div class="flex items-center gap-1.5 rounded-[10px] px-2.5 py-2" style="background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border));">
          <span class="text-[12.5px] font-mono shrink-0" style="color: hsl(var(--pg-fg-muted));">/blog/</span>
          <input
            id="post-slug"
            bind:value={slug}
            on:input={() => (slugTouched = true)}
            placeholder={slugify(title) || 'my-post-slug'}
            class="flex-1 min-w-0 text-[13px] font-mono bg-transparent border-none outline-none"
            style="color: hsl(var(--pg-fg));"
          />
        </div>
      </div>

      <!-- Theme picker -->
      <div class="rounded-[14px] p-4 sm:p-5" style="background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border));">
        <div class="text-[11.5px] font-semibold uppercase tracking-wide mb-3" style="color: hsl(var(--pg-fg-muted));">
          Post theme
        </div>
        <div class="grid gap-2" style="grid-template-columns: repeat(auto-fill, minmax(118px, 1fr));">
          {#each THEME_LIST as t}
            <button
              type="button"
              on:click={() => (theme = t.key)}
              class="rounded-[12px] overflow-hidden text-left cursor-pointer border-2 transition-all"
              style="
                border-color: {theme === t.key ? 'hsl(32 72% 50%)' : 'transparent'};
                box-shadow: {theme === t.key ? '0 0 0 3px hsl(32 72% 50% / 0.18)' : 'none'};
                outline: none;
              "
            >
              <!-- Color swatch -->
              <div
                style="
                  height: 52px;
                  background: {t.previewBg};
                  display: flex; align-items: center; justify-content: center;
                  font-size: 22px;
                "
              >{t.emoji}</div>
              <!-- Label -->
              <div
                style="
                  padding: 7px 10px 8px;
                  background: {theme === t.key ? 'hsl(32 72% 50%)' : 'hsl(var(--pg-elevated))'};
                  border-top: 1px solid hsl(var(--pg-border));
                "
              >
                <div class="text-[12px] font-semibold leading-tight"
                  style="color: {theme === t.key ? 'white' : 'hsl(var(--pg-fg))'};"
                >{t.label}</div>
                <div class="text-[10px] leading-tight mt-0.5"
                  style="color: {theme === t.key ? 'hsl(0 0% 100% / 0.8)' : 'hsl(var(--pg-fg-muted))'};"
                >{t.description}</div>
              </div>
            </button>
          {/each}
        </div>
        {#if theme === 'banking-brave'}
          <p class="text-[11.5px] mt-3" style="color: hsl(var(--pg-fg-subtle));">
            Banking.Brave uses a full-page layout with a built-in yield calculator and roadmap — body widgets are rendered inside that layout.
          </p>
        {/if}
      </div>

      <!-- Hero image picker -->
      <div class="rounded-[14px] p-4 sm:p-5" style="background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border));">
        <div class="text-[11.5px] font-semibold uppercase tracking-wide mb-3" style="color: hsl(var(--pg-fg-muted));">
          Hero image <span class="font-normal normal-case" style="color: hsl(var(--pg-fg-subtle));">(shown on the card and post header)</span>
        </div>
        <div class="grid gap-2" style="grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));">
          {#each HEROES as h}
            <button
              type="button"
              on:click={() => (hero = h.key)}
              aria-label={`Use the ${h.label} hero image`}
              class="rounded-[12px] overflow-hidden text-left cursor-pointer border-2 transition-all"
              style="
                border-color: {hero === h.key ? 'hsl(32 72% 50%)' : 'transparent'};
                box-shadow: {hero === h.key ? '0 0 0 3px hsl(32 72% 50% / 0.18)' : 'none'};
                outline: none;
              "
            >
              <div
                class="flex items-center justify-center"
                style="
                  height: 64px;
                  background: {h.key === 'farm'
                    ? 'radial-gradient(ellipse at 50% 70%, hsl(112 40% 82%), hsl(26 30% 74%))'
                    : 'linear-gradient(180deg, hsl(26 45% 96%), hsl(26 40% 88%))'};
                "
              >
                <img
                  src={postHeroImg(h.key)}
                  alt=""
                  style="height: 80%; object-fit: contain; image-rendering: {h.key === 'farm' ? 'pixelated' : 'auto'};"
                />
              </div>
              <div
                style="
                  padding: 6px 10px 7px;
                  background: {hero === h.key ? 'hsl(32 72% 50%)' : 'hsl(var(--pg-elevated))'};
                  border-top: 1px solid hsl(var(--pg-border));
                "
              >
                <div class="text-[12px] font-semibold leading-tight"
                  style="color: {hero === h.key ? 'white' : 'hsl(var(--pg-fg))'};"
                >{h.label}</div>
                <div class="text-[10px] leading-tight mt-0.5"
                  style="color: {hero === h.key ? 'hsl(0 0% 100% / 0.8)' : 'hsl(var(--pg-fg-muted))'};"
                >{h.desc}</div>
              </div>
            </button>
          {/each}
        </div>
      </div>

      <!-- Category + author role -->
      <div class="rounded-[14px] p-4 sm:p-5 grid grid-cols-1 sm:grid-cols-2 gap-4"
        style="background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border));"
      >
        <div>
          <label class="block text-[11.5px] font-semibold uppercase tracking-wide mb-1.5" style="color: hsl(var(--pg-fg-muted));" for="post-cat">Category</label>
          <select
            id="post-cat"
            bind:value={category}
            class="w-full text-[13.5px] rounded-[10px] px-2.5 py-2 outline-none"
            style="background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border)); color: hsl(var(--pg-fg));"
          >
            {#each Object.entries(CATEGORIES) as [k, m]}
              <option value={k}>{m.label}</option>
            {/each}
          </select>
        </div>
        <div>
          <label class="block text-[11.5px] font-semibold uppercase tracking-wide mb-1.5" style="color: hsl(var(--pg-fg-muted));" for="post-role">Author role</label>
          <input
            id="post-role"
            bind:value={authorRole}
            placeholder="Core team"
            class="w-full text-[13.5px] rounded-[10px] px-2.5 py-2 outline-none"
            style="background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border)); color: hsl(var(--pg-fg));"
          />
        </div>
        <label class="sm:col-span-2 inline-flex items-center gap-2 cursor-pointer text-[13px]" style="color: hsl(var(--pg-fg));">
          <input type="checkbox" bind:checked={pinned} /> Pin this post to the top of the dev log
        </label>
      </div>

      <!-- Excerpt -->
      <div class="rounded-[14px] p-4 sm:p-5" style="background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border));">
        <div class="flex items-center justify-between mb-1.5">
          <label class="text-[11.5px] font-semibold uppercase tracking-wide" style="color: hsl(var(--pg-fg-muted));" for="post-excerpt">
            Excerpt <span class="font-normal normal-case" style="color: hsl(var(--pg-fg-subtle));">(optional — auto-filled from first paragraph)</span>
          </label>
          <span class="text-[11px] tabular-nums" style="color: hsl(var(--pg-fg-muted));">{excerpt.length}/280</span>
        </div>
        <textarea
          id="post-excerpt"
          bind:value={excerpt}
          placeholder="Leave blank and we'll use the first paragraph of the body."
          rows="2"
          maxlength="280"
          class="w-full text-[13.5px] rounded-[10px] px-3 py-2 outline-none resize-none"
          style="background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border)); color: hsl(var(--pg-fg)); line-height: 1.55;"
        ></textarea>
        {#if !excerpt.trim() && deriveExcerpt()}
          <div class="mt-2 text-[11.5px]" style="color: hsl(var(--pg-fg-muted));">
            <Icon name="sparkle" size={11} /> Auto-fill preview:
            <span style="color: hsl(var(--pg-fg));">{deriveExcerpt()}</span>
          </div>
        {/if}
      </div>

      <!-- Body -->
      <div class="rounded-[14px] p-4 sm:p-5" style="background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border));">
        <div class="flex items-center justify-between mb-1.5 flex-wrap gap-2">
          <label class="text-[11.5px] font-semibold uppercase tracking-wide" style="color: hsl(var(--pg-fg-muted));" for="post-body">Body</label>
          <span class="text-[11px] tabular-nums" style="color: hsl(var(--pg-fg-muted));">~{readMin} min read</span>
        </div>

        <!-- Toolbar: text formats -->
        <div class="flex flex-wrap gap-1.5 mb-1">
          {#each TOOLBAR_TEXT as btn}
            <button
              type="button"
              on:click={btn.action}
              title={btn.title}
              aria-label={btn.title}
              class="h-8 px-2.5 rounded-[8px] inline-flex items-center gap-1.5 text-[11.5px] font-semibold cursor-pointer"
              style="background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border)); color: hsl(var(--pg-fg));"
            >
              <Icon name={btn.icon} size={13} />
              {#if btn.label}{btn.label}{/if}
            </button>
          {/each}

          <span style="width: 1px; height: 28px; align-self: center; background: hsl(var(--pg-border)); margin: 0 2px;"></span>

          <!-- Widget inserts -->
          {#each TOOLBAR_WIDGETS as btn}
            <button
              type="button"
              on:click={btn.action}
              title={btn.title}
              aria-label={btn.title}
              class="h-8 px-2.5 rounded-[8px] inline-flex items-center gap-1.5 text-[11px] font-semibold cursor-pointer"
              style="background: hsl(32 72% 50% / 0.08); border: 1px solid hsl(32 72% 50% / 0.3); color: hsl(32 56% 30%);"
            >
              <Icon name={btn.icon} size={12} />
              {btn.label}
            </button>
          {/each}

          <span class="flex-1"></span>
          <button
            type="button"
            on:click={clearAndStartOver}
            class="h-8 px-2.5 rounded-[8px] inline-flex items-center gap-1.5 text-[11.5px] font-medium cursor-pointer"
            style="background: transparent; border: 1px solid hsl(var(--pg-border)); color: hsl(0 72% 42%);"
          >
            <Icon name="arrow-counter-clockwise" size={12} /> Reset
          </button>
        </div>

        <textarea
          id="post-body"
          bind:this={bodyTextarea}
          bind:value={bodySrc}
          placeholder={`Write here.

Leave a blank line between paragraphs.

## Use a heading when a section changes

- Bullet lists work great
- Especially for changelog items

> ⚡ | Callout | Use these for highlights, decisions, warnings.

Use the toolbar above to insert widgets:
::stats | APY:7.25% | Treasury:$2.4M
::chart | area | Treasury Balance | Jan:2.1 | Feb:2.2
::roadmap | done:Q1 2026:Foundation | now:Today:Testnet | next:Q2:Mainnet
::progress | 614/1000 | Testnet seats | Opens May 12
::calculator | apy=7.25 | max=50000 | currency=CF`}
          rows="14"
          class="w-full text-[14.5px] rounded-[10px] px-3 py-3 outline-none resize-y"
          style="background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border)); color: hsl(var(--pg-fg)); line-height: 1.6; font-family: ui-monospace, 'SF Mono', Consolas, monospace;"
        ></textarea>
        <div class="mt-2 flex items-center justify-between text-[11px] flex-wrap gap-2" style="color: hsl(var(--pg-fg-muted));">
          <span>
            <code>##</code> heading ·
            <code>-</code> bullets ·
            <code>&gt; icon | title | body</code> callout ·
            <code>::widget</code> blocks
          </span>
          {#if draftSavedAt}
            <span class="inline-flex items-center gap-1">
              <Icon name="check-circle" size={11} style="color: hsl(142 55% 40%);" />
              Draft saved {new Date(draftSavedAt).toLocaleTimeString()}
            </span>
          {/if}
        </div>
      </div>

      <!-- Validation + actions -->
      {#if err}
        <div class="rounded-[10px] px-3 py-2 text-[13px]"
          style="background: hsl(0 70% 96%); color: hsl(0 70% 30%); border: 1px solid hsl(0 70% 85%);"
        >
          <Icon name="warning" size={14} /> {err}
        </div>
      {/if}
      {#if savedSlug}
        <div class="rounded-[10px] px-3 py-2 text-[13px] inline-flex items-center gap-2"
          style="background: hsl(142 50% 94%); color: hsl(142 70% 25%); border: 1px solid hsl(142 45% 70%);"
        >
          <Icon name="check-circle" size={14} /> Published — redirecting…
        </div>
      {/if}

      <div class="flex flex-col sm:flex-row gap-2 items-stretch sm:items-center">
        <Button
          on:click={submit}
          disabled={submitting || !!validationError || !!savedSlug}
          class="flex-1 sm:flex-none"
        >
          {#if submitting}
            <Icon name="spinner-gap" size={15} /> {isEditing ? 'Saving…' : 'Publishing…'}
          {:else}
            <Icon name={isEditing ? 'check' : 'paper-plane-tilt'} size={15} /> {submitLabel}
          {/if}
        </Button>
        <Button
          variant="outline"
          on:click={() => (previewing = !previewing)}
          class="flex-1 sm:flex-none"
        >
          <Icon name={previewing ? 'pencil-simple' : 'eye'} size={15} />
          {previewing ? 'Hide preview' : 'Show preview'}
        </Button>
        {#if validationError}
          <span class="text-[11.5px] self-center" style="color: hsl(var(--pg-fg-muted));">
            {validationError}
          </span>
        {/if}
      </div>
    </div>

    <!-- Themed live preview -->
    {#if previewing}
      <div class="mt-8 sm:mt-10 pt-6 sm:pt-8" style="border-top: 1px dashed hsl(var(--pg-border));">
        <div class="flex items-center gap-2 text-[11.5px] font-semibold uppercase tracking-wide mb-4" style="color: hsl(var(--pg-fg-muted));">
          <Icon name="eye" size={13} /> Live preview · {selectedTheme.emoji} {selectedTheme.label} theme
        </div>

        <!-- Hero band -->
        <div
          class="rounded-[14px] px-6 sm:px-10 py-8 mb-4"
          style="background: {selectedTheme.hero.bg};"
        >
          <div class="flex gap-2 items-center mb-3 flex-wrap">
            <CategoryTag cat={category} />
            <span class="text-[11.5px]" style="color: {selectedTheme.hero.sub};">
              {new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
            </span>
            <span class="text-[11.5px]" style="color: {selectedTheme.hero.sub};">· {readMin} min read</span>
          </div>
          <h2
            class="font-bold leading-[1.08] mb-3"
            style="font-size: clamp(22px, 4.5vw, 38px); color: {selectedTheme.hero.text}; letter-spacing: -0.025em;"
          >
            {title || 'Untitled post'}
          </h2>
          <p class="text-[15px] sm:text-[17px] leading-[1.55]" style="color: {selectedTheme.hero.sub}; max-width: 58ch;">
            {excerpt || deriveExcerpt() || 'Excerpt preview will appear here.'}
          </p>
        </div>

        <!-- Themed body -->
        {#if blocks.length > 0}
          <PostRenderer {blocks} theme={selectedTheme} />
        {:else}
          <div
            class="rounded-[14px] py-10 text-center text-[13px] italic"
            style="border: 1px dashed hsl(var(--pg-border)); color: hsl(var(--pg-fg-subtle));"
          >
            Body preview will appear once you start writing.
          </div>
        {/if}
      </div>
    {/if}
  {/if}
</section>
