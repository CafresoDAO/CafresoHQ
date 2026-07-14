<svelte:options runes={true} />

<script>
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { browser } from '$app/environment';
  import { onMount, tick } from 'svelte';
  import Icon from '$lib/components/Icon.svelte';
  import Button from '$lib/components/Button.svelte';
  import Avatar from '$lib/components/Avatar.svelte';
  import PostRenderer from '$lib/components/PostRenderer.svelte';
  import {
    getForumPost,
    upsertForumPost,
    stripForumPrefix
  } from '$lib/api/devlog.js';
  import { isAuthenticated, login, authStatus, principalText } from '$lib/stores/auth.js';
  import { profile, ACCENTS } from '$lib/stores/profile.js';
  import { parseBlocks, blocksToMarkdown, readMinutes, slugify, WIDGET_SNIPPETS } from '$lib/markdown.js';
  import { THEME_LIST, getTheme } from '$lib/themes.js';

  // Community-facing themes (exclude banking-brave — DAO/finance only for admins)
  const FORUM_THEMES = THEME_LIST.filter((t) => t.key !== 'banking-brave');

  let title = $state('');
  let slug = $state('');
  let slugTouched = $state(false);
  // Default matches what the thread page renders for themeless posts.
  let theme = $state('community');
  let excerpt = $state('');
  let bodySrc = $state('');
  let previewing = $state(false);
  let submitting = $state(false);
  let err = $state(null);
  let savedSlug = $state(null);
  let loadingEdit = $state(false);
  // Preserved from the loaded thread in edit mode so saving doesn't silently
  // rewrite the original post date.
  let originalDate = $state(null);

  // Draft autosave
  let bodyTextarea;
  const editSlug = $derived($page.url.searchParams.get('edit'));
  const isEditing = $derived(!!editSlug);
  let draftKey = $derived(editSlug ? `cafreso:forum:draft:edit:${editSlug}` : 'cafreso:forum:draft:new');
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
        JSON.stringify({ title, slug, slugTouched, theme, excerpt, bodySrc, savedAt: Date.now() })
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
    theme = d.theme ?? 'community';
    excerpt = d.excerpt ?? '';
    bodySrc = d.bodySrc ?? '';
    draftSavedAt = d.savedAt ?? null;
  }

  onMount(() => {
    if (!editSlug) {
      const d = readDraft('cafreso:forum:draft:new');
      hasDraft = !!(d && (d.title || d.bodySrc || d.excerpt));
    }
    draftLoaded = true;
  });

  let saveTimer;
  $effect(() => {
    const _ = [title, slug, slugTouched, theme, excerpt, bodySrc];
    if (!browser || !draftLoaded || loadingEdit) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => writeDraft(draftKey), 600);
  });

  // Toolbar
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

  let loadedEditSlug = null;

  $effect(() => {
    if (!editSlug || editSlug === loadedEditSlug) return;
    loadedEditSlug = editSlug;
    hydrateForEdit(editSlug);
  });

  async function hydrateForEdit(s) {
    loadingEdit = true;
    try {
      const p = await getForumPost(s);
      if (!p) {
        err = `No thread found with slug "${s}".`;
        return;
      }
      title = p.title || '';
      slug = stripForumPrefix(p.slug) || s;
      slugTouched = true;
      theme = p.theme && p.theme !== 'standard' ? p.theme : 'community';
      excerpt = p.excerpt || '';
      originalDate = p.date || null;
      bodySrc = blocksToMarkdown(p.body || []);
    } finally {
      loadingEdit = false;
    }
  }

  const blocks = $derived(parseBlocks(bodySrc));
  const readMin = $derived(readMinutes(bodySrc));
  const slugPreview = $derived(slug || slugify(title));
  const heading = $derived(isEditing ? 'Edit thread' : 'Start a new thread');
  const authorName = $derived(
    $profile.name || ($principalText ? `${$principalText.slice(0, 5)}…${$principalText.slice(-3)}` : 'Guest')
  );
  const authorHue = $derived(ACCENTS.find((a) => a.key === $profile.accent)?.hue ?? 24);
  const selectedTheme = $derived(getTheme(theme));
  const validationError = $derived(validate());

  $effect(() => {
    if (slugTouched) return;
    slug = slugify(title);
  });

  function validate() {
    if (!title.trim()) return 'Add a title.';
    if (!slugPreview) return 'Slug is empty — fix the title or set one manually.';
    if (!/^[a-z0-9-]+$/.test(slugPreview)) return 'Slug may only contain lowercase letters, numbers, and dashes.';
    if (!excerpt.trim()) return 'Write a short excerpt — it shows on the forum index card.';
    if (excerpt.length > 280) return 'Excerpt is over 280 characters.';
    if (!bodySrc.trim()) return 'Thread body is empty.';
    return null;
  }

  async function submit() {
    err = null;
    const bad = validate();
    if (bad) {
      err = bad;
      return;
    }
    submitting = true;
    const res = await upsertForumPost({
      slug: slugPreview,
      title: title.trim(),
      author: { name: authorName, hue: authorHue, role: 'Community' },
      date: (isEditing && originalDate) || new Date().toISOString().slice(0, 10),
      readMin,
      excerpt: excerpt.trim(),
      theme,
      body: blocks,
      block: 0
    });
    submitting = false;
    if (res.err) {
      err = res.err;
      return;
    }
    savedSlug = stripForumPrefix(res.ok?.slug) || slugPreview;
    clearDraft(draftKey);
    setTimeout(() => goto(`/forums/${savedSlug}`), 500);
  }
</script>

<svelte:head><title>{heading} · Forums · Cafreso</title></svelte:head>

<section class="mx-auto px-4 sm:px-[18px] pt-6 sm:pt-8 pb-24" style="max-width: 820px;">
  <a
    href={isEditing ? `/forums/${editSlug}` : '/forums'}
    class="inline-flex items-center gap-1.5 text-[12.5px] no-underline mb-4"
    style="color: hsl(215 16% 47%);"
  >
    <Icon name="caret-left" size={13} /> {isEditing ? 'Back to thread' : 'Back to Forums'}
  </a>

  <div class="flex items-center gap-2 text-[13px] font-medium mb-3" style="color: hsl(24 48% 28%);">
    <Icon name={isEditing ? 'pencil-line' : 'chats-circle'} size={16} />
    {isEditing ? 'Editing your thread' : 'Community · open to everyone'}
  </div>
  <h1 class="font-bold leading-tight mb-2" style="font-size: clamp(26px, 5vw, 36px); color: hsl(222 47% 11%);">
    {heading}
  </h1>
  <p class="text-[14.5px] leading-[1.55] mb-6 sm:mb-8 max-w-[560px]" style="color: hsl(215 16% 47%);">
    Your principal is your byline. Threads, comments, and tips all land on the
    devlog canister — readers can tip you in $nanas if your take lands.
  </p>

  {#if loadingEdit}
    <div class="rounded-[10px] px-3 py-2 text-[13px] inline-flex items-center gap-2 mb-4"
      style="background: hsl(45 80% 94%); color: hsl(32 56% 25%); border: 1px solid hsl(45 75% 72%);"
    >
      <Icon name="spinner-gap" size={13} /> Loading thread…
    </div>
  {/if}

  {#if !$isAuthenticated}
    <div class="rounded-[14px] p-6 sm:p-8 text-center"
      style="background: hsl(26 40% 98%); border: 1px solid hsl(26 30% 88%);"
    >
      <Icon name="fingerprint" size={28} style="color: hsl(32 56% 35%);" />
      <h2 class="text-[18px] font-bold mt-3 mb-2" style="color: hsl(222 47% 11%);">Sign in to post</h2>
      <p class="text-[13.5px] mb-5 max-w-[380px] mx-auto" style="color: hsl(215 16% 47%);">
        Every thread is signed by your Internet Identity principal.
      </p>
      <Button on:click={login} disabled={$authStatus === 'logging-in'}>
        <Icon name="fingerprint" size={15} /> Sign in
      </Button>
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
      <!-- Author card -->
      <div
        class="rounded-[14px] p-4 sm:p-5 flex items-center gap-3"
        style="background: hsl(26 40% 98%); border: 1px solid hsl(26 30% 88%);"
      >
        <Avatar name={authorName} hue={authorHue} size={40} />
        <div class="min-w-0">
          <div class="text-[11.5px] uppercase tracking-wide font-semibold" style="color: hsl(215 16% 47%);">Posting as</div>
          <div class="font-semibold text-[14px] truncate" style="color: hsl(222 47% 11%);">{authorName}</div>
          <div class="text-[11px]" style="color: hsl(215 16% 47%);">
            Tip: <a href="/profile" class="underline" style="color: hsl(38 85% 30%);">set a display name on /profile</a>.
          </div>
        </div>
      </div>

      <!-- Title + slug -->
      <div class="rounded-[14px] p-4 sm:p-5"
        style="background: hsl(26 40% 98%); border: 1px solid hsl(26 30% 88%);"
      >
        <label class="block text-[11.5px] font-semibold uppercase tracking-wide mb-1.5" style="color: hsl(215 16% 47%);" for="forum-title">Title</label>
        <input
          id="forum-title"
          bind:value={title}
          placeholder="Thought, question, proposal…"
          class="w-full text-[18px] sm:text-[20px] font-bold bg-white rounded-[10px] px-3 py-2.5 outline-none"
          style="border: 1px solid hsl(26 30% 85%); color: hsl(222 47% 11%);"
        />

        <label class="block text-[11.5px] font-semibold uppercase tracking-wide mt-4 mb-1.5" style="color: hsl(215 16% 47%);" for="forum-slug">
          URL slug <span class="font-normal normal-case" style="color: hsl(215 16% 62%);">(auto, editable)</span>
        </label>
        <div class="flex items-center gap-1.5 rounded-[10px] px-2.5 py-2 bg-white" style="border: 1px solid hsl(26 30% 85%);">
          <span class="text-[12.5px] font-mono shrink-0" style="color: hsl(215 16% 47%);">/forums/</span>
          <input
            id="forum-slug"
            bind:value={slug}
            on:input={() => (slugTouched = true)}
            placeholder={slugify(title) || 'my-thread'}
            class="flex-1 min-w-0 text-[13px] font-mono bg-transparent border-none outline-none"
            style="color: hsl(222 47% 11%);"
            disabled={isEditing}
          />
        </div>
      </div>

      <!-- Theme picker -->
      <div class="rounded-[14px] p-4 sm:p-5" style="background: hsl(26 40% 98%); border: 1px solid hsl(26 30% 88%);">
        <div class="text-[11.5px] font-semibold uppercase tracking-wide mb-3" style="color: hsl(215 16% 47%);">
          Thread theme
        </div>
        <div class="grid gap-2" style="grid-template-columns: repeat(auto-fill, minmax(118px, 1fr));">
          {#each FORUM_THEMES as t}
            <button
              type="button"
              on:click={() => (theme = t.key)}
              aria-label={`Select ${t.label} theme`}
              class="rounded-[12px] overflow-hidden text-left cursor-pointer border-2 transition-all"
              style="
                border-color: {theme === t.key ? 'hsl(32 72% 50%)' : 'transparent'};
                box-shadow: {theme === t.key ? '0 0 0 3px hsl(32 72% 50% / 0.18)' : 'none'};
                outline: none;
              "
            >
              <div
                style="
                  height: 44px;
                  background: {t.previewBg};
                  display: flex; align-items: center; justify-content: center;
                  font-size: 20px;
                "
              >{t.emoji}</div>
              <div
                style="
                  padding: 6px 9px 7px;
                  background: {theme === t.key ? 'hsl(32 72% 50%)' : 'white'};
                  border-top: 1px solid hsl(26 30% 88%);
                "
              >
                <div class="text-[11.5px] font-semibold leading-tight"
                  style="color: {theme === t.key ? 'white' : 'hsl(222 47% 11%)'};"
                >{t.label}</div>
              </div>
            </button>
          {/each}
        </div>
      </div>

      <!-- Excerpt -->
      <div class="rounded-[14px] p-4 sm:p-5" style="background: hsl(26 40% 98%); border: 1px solid hsl(26 30% 88%);">
        <div class="flex items-center justify-between mb-1.5">
          <label class="text-[11.5px] font-semibold uppercase tracking-wide" style="color: hsl(215 16% 47%);" for="forum-excerpt">Excerpt</label>
          <span class="text-[11px] tabular-nums" style="color: hsl(215 16% 47%);">{excerpt.length}/280</span>
        </div>
        <textarea
          id="forum-excerpt"
          bind:value={excerpt}
          placeholder="Two or three lines for the forum card."
          rows="3"
          maxlength="280"
          class="w-full text-[13.5px] bg-white rounded-[10px] px-3 py-2 outline-none resize-none"
          style="border: 1px solid hsl(26 30% 85%); color: hsl(222 47% 11%); line-height: 1.55;"
        ></textarea>
      </div>

      <!-- Body with toolbar -->
      <div class="rounded-[14px] p-4 sm:p-5" style="background: hsl(26 40% 98%); border: 1px solid hsl(26 30% 88%);">
        <div class="flex items-center justify-between mb-1.5">
          <label class="text-[11.5px] font-semibold uppercase tracking-wide" style="color: hsl(215 16% 47%);" for="forum-body">Body</label>
          <span class="text-[11px] tabular-nums" style="color: hsl(215 16% 47%);">~{readMin} min read</span>
        </div>

        <!-- Toolbar -->
        <div class="flex flex-wrap gap-1.5 mb-1">
          {#each TOOLBAR_TEXT as btn}
            <button
              type="button"
              on:click={btn.action}
              title={btn.title}
              aria-label={btn.title}
              class="h-8 px-2.5 rounded-[8px] inline-flex items-center gap-1.5 text-[11.5px] font-semibold cursor-pointer"
              style="background: white; border: 1px solid hsl(26 30% 85%); color: hsl(222 47% 11%);"
            >
              <Icon name={btn.icon} size={13} />
              {#if btn.label}{btn.label}{/if}
            </button>
          {/each}

          <span style="width: 1px; height: 28px; align-self: center; background: hsl(26 30% 82%); margin: 0 2px;"></span>

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
        </div>

        <textarea
          id="forum-body"
          bind:this={bodyTextarea}
          bind:value={bodySrc}
          placeholder={`Blank line = new paragraph.\n\n## Heading\n- bullet\n> ⚡ | title | body\n\nOr use toolbar buttons to insert charts, roadmaps, and more.`}
          rows="12"
          class="w-full text-[14px] bg-white rounded-[10px] px-3 py-2.5 outline-none resize-y"
          style="border: 1px solid hsl(26 30% 85%); color: hsl(222 47% 11%); line-height: 1.55; font-family: ui-monospace, 'SF Mono', Consolas, monospace;"
        ></textarea>
        {#if draftSavedAt}
          <div class="mt-2 text-[11px] flex items-center gap-1" style="color: hsl(215 16% 47%);">
            <Icon name="check-circle" size={11} style="color: hsl(142 55% 40%);" />
            Draft saved {new Date(draftSavedAt).toLocaleTimeString()}
          </div>
        {/if}
      </div>

      <!-- Errors + actions -->
      {#if err}
        <div class="rounded-[10px] px-3 py-2 text-[13px]"
          style="background: hsl(0 70% 96%); color: hsl(0 70% 30%); border: 1px solid hsl(0 70% 85%);"
        >
          <Icon name="warning" size={13} /> {err}
        </div>
      {/if}
      {#if savedSlug}
        <div class="rounded-[10px] px-3 py-2 text-[13px] inline-flex items-center gap-2"
          style="background: hsl(142 50% 94%); color: hsl(142 70% 25%); border: 1px solid hsl(142 45% 70%);"
        >
          <Icon name="check-circle" size={13} /> Posted — redirecting…
        </div>
      {/if}

      <div class="flex flex-col sm:flex-row gap-2 items-stretch sm:items-center">
        <Button
          on:click={submit}
          disabled={submitting || !!validationError || !!savedSlug}
          class="flex-1 sm:flex-none"
        >
          {#if submitting}
            <Icon name="spinner-gap" size={15} /> {isEditing ? 'Saving…' : 'Posting…'}
          {:else}
            <Icon name={isEditing ? 'check' : 'paper-plane-tilt'} size={15} />
            {isEditing ? 'Save changes' : 'Post thread'}
          {/if}
        </Button>
        <Button variant="outline" on:click={() => (previewing = !previewing)} class="flex-1 sm:flex-none">
          <Icon name={previewing ? 'pencil-simple' : 'eye'} size={15} />
          {previewing ? 'Hide preview' : 'Preview'}
        </Button>
        {#if validationError}
          <span class="text-[11.5px] self-center" style="color: hsl(215 16% 47%);">
            {validationError}
          </span>
        {/if}
      </div>
    </div>

    <!-- Themed live preview -->
    {#if previewing && !loadingEdit}
      <div class="mt-8 pt-6" style="border-top: 1px dashed hsl(26 30% 80%);">
        <div class="flex items-center gap-2 text-[11.5px] font-semibold uppercase tracking-wide mb-4" style="color: hsl(215 16% 47%);">
          <Icon name="eye" size={13} /> Preview · {selectedTheme.emoji} {selectedTheme.label} theme
        </div>

        <!-- Hero band -->
        <div
          class="rounded-[14px] px-6 sm:px-10 py-8 mb-4"
          style="background: {selectedTheme.hero.bg};"
        >
          <h2
            class="font-bold leading-[1.08] mb-3"
            style="font-size: clamp(22px, 4.5vw, 34px); color: {selectedTheme.hero.text}; letter-spacing: -0.025em;"
          >
            {title || 'Untitled thread'}
          </h2>
          <p class="text-[15px] leading-[1.55]" style="color: {selectedTheme.hero.sub}; max-width: 58ch;">
            {excerpt || 'Excerpt preview will appear here.'}
          </p>
        </div>

        <!-- Themed body -->
        {#if blocks.length > 0}
          <PostRenderer {blocks} theme={selectedTheme} />
        {:else}
          <div
            class="rounded-[14px] py-10 text-center text-[13px] italic"
            style="border: 1px dashed hsl(26 30% 80%); color: hsl(215 16% 55%);"
          >
            Preview will appear once you start writing.
          </div>
        {/if}
      </div>
    {/if}
  {/if}
</section>
