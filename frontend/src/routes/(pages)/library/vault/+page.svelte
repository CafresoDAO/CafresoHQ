<script>
  /* THE VAULT — a deep-research entry, explorable the way Obsidian explores a
     vault. Left: the file tree (Overview.md, notes/, Sources.md). Right: a
     reading pane with rendered markdown, clickable [[wikilinks]] (with hover
     previews), backlinks under every note, and prev/next paging. Cmd/Ctrl+P
     opens a quick switcher. "Download vault" exports the same files as a .zip
     that opens unchanged in actual Obsidian.

     URL-addressable: /library/vault?e=<id>&f=<file path>. Everything is
     derived client-side from the entry's public JSON — this page adds a view,
     not state. */
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import Icon from '$lib/components/Icon.svelte';
  import { libraryEntry, libraryResearch } from '$lib/api/searchNetwork.js';
  import { libraryGraphViewerUrl } from '$lib/api/library.js';
  import { buildVault, renderMd, downloadVault } from '$lib/research/vault.js';

  let entryId = null;
  let state = 'loading';        // loading | ready | missing
  let entry = null;
  let vault = null;
  let current = 'Overview.md';  // path of the open file
  let raw = false;              // raw-markdown toggle (very Obsidian)
  let treeOpen = true;          // notes/ folder fold
  let sideOpen = false;         // mobile: tree drawer
  let readerEl;

  // Quick switcher (Cmd/Ctrl+P)
  let switcherOpen = false;
  let switcherQ = '';
  let switcherIx = 0;
  let switcherInput;

  // Wikilink hover preview
  let preview = null;           // { path, html, x, y }
  let previewTimer = null;

  $: {
    const e = $page.url.searchParams.get('e');
    if (e !== entryId) { entryId = e; load(e); }
    const f = $page.url.searchParams.get('f');
    if (vault && f && vault.byPath.has(f) && f !== current) current = f;
  }
  $: file = vault ? vault.byPath.get(current) || vault.files[0] : null;
  $: html = file ? renderMd(file.md, vault) : '';
  $: fileIx = vault && file ? vault.files.indexOf(file) : -1;
  $: backlinks = vault && file ? vault.backlinks.get(file.path) || [] : [];
  $: readMin = file ? Math.max(1, Math.round(file.words / 220)) : 1;
  $: rootFiles = vault ? vault.files.filter((f) => !f.folder) : [];
  $: noteFiles = vault ? vault.files.filter((f) => f.folder === 'notes') : [];
  $: switcherHits = vault
    ? vault.files.filter((f) => f.name.toLowerCase().includes(switcherQ.trim().toLowerCase()))
    : [];
  $: gvUrl = entry ? libraryGraphViewerUrl(entry.id, { deep: true }) : '';

  async function load(id) {
    state = 'loading';
    entry = null; vault = null; preview = null;
    if (!id) { state = 'missing'; return; }
    const [e, r] = await Promise.all([libraryEntry(id), libraryResearch(id)]);
    if (id !== entryId) return;
    if (!e || !e.id) { state = 'missing'; return; }
    entry = e;
    vault = buildVault(e, r);
    const f = $page.url.searchParams.get('f');
    current = f && vault.byPath.has(f) ? f : 'Overview.md';
    state = 'ready';
  }

  function openFile(path, { push = true } = {}) {
    if (!vault || !vault.byPath.has(path)) return;
    current = path;
    raw = false;
    preview = null;
    sideOpen = false;
    if (push) {
      const u = new URL(location.href);
      u.searchParams.set('f', path);
      goto(`${u.pathname}${u.search}`, { noScroll: true, keepFocus: true, replaceState: false });
    }
    if (readerEl) readerEl.scrollTop = 0;
  }

  // Rendered-markdown click/hover delegation: wikilinks carry data-path.
  function onReaderClick(ev) {
    const a = ev.target.closest?.('a.v-wiki');
    if (!a) return;
    ev.preventDefault();
    openFile(a.dataset.path);
  }
  function onReaderOver(ev) {
    const a = ev.target.closest?.('a.v-wiki');
    if (!a || !vault) { return; }
    const path = a.dataset.path;
    clearTimeout(previewTimer);
    previewTimer = setTimeout(() => {
      const f = vault.byPath.get(path);
      if (!f) return;
      const r = a.getBoundingClientRect();
      /* Clamp into the viewport on BOTH axes. The old `Math.min(r.left,
         innerWidth - 380)` had no lower bound, so any viewport under ~380px
         produced a negative x and pushed the card off-screen left; 380 also
         didn't match the card's real width. Measured against PREVIEW_W/H,
         which mirror the .v-preview rule below. Recomputed per hover, and the
         card is transient (it closes on mouseout), so no resize listener. */
      const PREVIEW_W = Math.min(360, window.innerWidth * 0.9);
      const PREVIEW_H = 300;
      const M = 8;
      const flipsAbove = r.bottom + M + PREVIEW_H > window.innerHeight;
      preview = {
        path,
        html: renderMd(f.md.split('\n').slice(0, 14).join('\n'), vault),
        x: Math.max(M, Math.min(r.left, window.innerWidth - PREVIEW_W - M)),
        y: flipsAbove
          ? Math.max(M, r.top - PREVIEW_H - M)
          : r.bottom + M
      };
    }, 250);
  }
  function onReaderOut(ev) {
    if (ev.target.closest?.('a.v-wiki')) {
      clearTimeout(previewTimer);
      previewTimer = setTimeout(() => { preview = null; }, 200);
    }
  }
  function holdPreview() { clearTimeout(previewTimer); }
  function releasePreview() { previewTimer = setTimeout(() => { preview = null; }, 150); }

  function onKeydown(e) {
    if ((e.metaKey || e.ctrlKey) && (e.key === 'p' || e.key === 'k')) {
      e.preventDefault();
      switcherOpen = !switcherOpen;
      switcherQ = ''; switcherIx = 0;
      if (switcherOpen) setTimeout(() => switcherInput?.focus(), 30);
      return;
    }
    if (switcherOpen) {
      if (e.key === 'Escape') { switcherOpen = false; return; }
      if (e.key === 'ArrowDown') { e.preventDefault(); switcherIx = Math.min(switcherIx + 1, switcherHits.length - 1); return; }
      if (e.key === 'ArrowUp') { e.preventDefault(); switcherIx = Math.max(switcherIx - 1, 0); return; }
      if (e.key === 'Enter' && switcherHits[switcherIx]) {
        switcherOpen = false;
        openFile(switcherHits[switcherIx].path);
      }
      return;
    }
    if (e.key === 'Escape' && preview) { preview = null; return; }
    // The mobile tree drawer was closable only by the burger or a scrim click —
    // Escape is what every other overlay in the app answers to, so it answers too.
    if (e.key === 'Escape' && sideOpen) { sideOpen = false; return; }
    // ←/→ page through the vault when nothing focused wants the keys.
    const tag = document.activeElement?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    if (e.key === 'ArrowRight' && fileIx < vault?.files.length - 1) openFile(vault.files[fileIx + 1].path);
    if (e.key === 'ArrowLeft' && fileIx > 0) openFile(vault.files[fileIx - 1].path);
  }

  function plainQ(t) { return String(t || '').replace(/<[^>]+>/g, ''); }
</script>

<svelte:head>
  <title>{vault ? `${vault.name} — Vault` : 'Research vault'} — Ai Cafreso</title>
  <meta name="description" content="A deep-research entry as an explorable vault of linked markdown notes." />
</svelte:head>

<svelte:window on:keydown={onKeydown} />

{#if state === 'loading'}
  <div class="v-empty">
    <div class="v-skel" style="width: 200px;"></div>
    <div class="v-skel" style="width: 320px;"></div>
  </div>
{:else if state === 'missing'}
  <div class="v-empty">
    <h2>Vault not found</h2>
    <p>This entry doesn't exist or isn't reachable. <a href="/library" class="v-link">Back to the library</a></p>
  </div>
{:else}
  <div class="vault">
    <!-- ── Top bar ─────────────────────────────────────────────────────────── -->
    <header class="v-top">
      <button class="v-burger" on:click={() => (sideOpen = !sideOpen)} aria-label="Toggle file tree">
        <Icon name="list" size={16} />
      </button>
      <a href="/library?e={entryId}" class="v-crumb"><Icon name="arrow-left" size={13} /> Library</a>
      <span class="v-crumb-sep">/</span>
      <span class="v-vaultname" title={vault.name}><Icon name="vault" size={13} /> {vault.name}</span>
      <span class="v-flex"></span>
      <button class="v-act" on:click={() => (switcherOpen = true) && setTimeout(() => switcherInput?.focus(), 30)} title="Quick switcher (⌘P)">
        <Icon name="magnifying-glass" size={13} /> <kbd>⌘P</kbd>
      </button>
      {#if gvUrl}
        <a class="v-act" href={gvUrl} target="_blank" rel="noopener noreferrer" title="Open the research tree as a graph">
          <Icon name="tree-structure" size={13} /> <span class="v-act-label">Graph</span>
        </a>
      {/if}
      <button class="v-act v-act-primary" on:click={() => downloadVault(vault)} title="Download as a folder of .md files — opens in Obsidian">
        <Icon name="download-simple" size={13} /> <span class="v-act-label">Download vault</span>
      </button>
    </header>

    <div class="v-body">
      <!-- ── File tree ──────────────────────────────────────────────────────── -->
      <nav class="v-tree" class:open={sideOpen} aria-label="Vault files">
        <div class="v-tree-head">{vault.files.length} files · {noteFiles.length} notes</div>
        {#each rootFiles as f (f.path)}
          {#if f.path === 'Overview.md'}
            <button class="v-file" class:on={current === f.path} on:click={() => openFile(f.path)}>
              <Icon name="file-text" size={14} /> <span>{f.name}<em>.md</em></span>
            </button>
          {/if}
        {/each}
        {#if noteFiles.length}
          <button class="v-folder" on:click={() => (treeOpen = !treeOpen)} aria-expanded={treeOpen}>
            <Icon name={treeOpen ? 'caret-down' : 'caret-right'} size={12} />
            <Icon name="folder-simple" size={14} /> notes
          </button>
          {#if treeOpen}
            {#each noteFiles as f (f.path)}
              <button class="v-file v-file-nested" class:on={current === f.path} on:click={() => openFile(f.path)}>
                <Icon name="file-text" size={14} /> <span>{f.name}<em>.md</em></span>
              </button>
            {/each}
          {/if}
        {/if}
        {#each rootFiles as f (f.path)}
          {#if f.path === 'Sources.md'}
            <button class="v-file" class:on={current === f.path} on:click={() => openFile(f.path)}>
              <Icon name="link-simple" size={14} /> <span>{f.name}<em>.md</em></span>
            </button>
          {/if}
        {/each}

        <div class="v-tree-foot">
          Stored on-chain · <a href="/library?e={entryId}" class="v-link">entry {entryId}</a>
        </div>
      </nav>
      {#if sideOpen}
        <!-- Tap-outside-to-close: a pointer convenience only. Keyboard users
             close with Escape (see onKeydown) or the burger, both of which are
             real buttons — so this scrim is deliberately not exposed to AT. -->
        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <!-- svelte-ignore a11y-no-static-element-interactions -->
        <div class="v-tree-scrim" on:click={() => (sideOpen = false)}></div>
      {/if}

      <!-- ── Reading pane ───────────────────────────────────────────────────── -->
      <section class="v-pane">
        <div class="v-tabbar">
          <span class="v-tab" title={file.path}>
            <Icon name="file-text" size={13} /> {file.name}.md
          </span>
          <span class="v-flex"></span>
          <button class="v-mode" class:on={!raw} on:click={() => (raw = false)} title="Reading view">
            <Icon name="book-open" size={13} />
          </button>
          <button class="v-mode" class:on={raw} on:click={() => (raw = true)} title="Raw markdown">
            <Icon name="code" size={13} />
          </button>
        </div>

        <!-- These handlers DELEGATE for the rendered markdown: the wikilinks
             inside are real <a> elements, so they're tab-focusable and Enter
             fires a click that bubbles here. The div isn't itself a control,
             hence no role/keyhandler of its own. -->
        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <!-- svelte-ignore a11y-no-static-element-interactions -->
        <div class="v-reader" bind:this={readerEl}
             on:click={onReaderClick} on:mouseover={onReaderOver} on:mouseout={onReaderOut}>
          {#if raw}
            <pre class="v-raw">{file.md}</pre>
          {:else}
            <article class="v-md">{@html html}</article>

            {#if backlinks.length}
              <div class="v-backlinks">
                <div class="v-bl-head"><Icon name="arrow-u-up-left" size={12} /> Linked mentions</div>
                {#each backlinks as bp}
                  <button class="v-bl" on:click={() => openFile(bp)}>{vault.byPath.get(bp)?.name}</button>
                {/each}
              </div>
            {/if}

            <div class="v-pager">
              {#if fileIx > 0}
                <button class="v-page-btn" on:click={() => openFile(vault.files[fileIx - 1].path)}>
                  <Icon name="arrow-left" size={13} /> {vault.files[fileIx - 1].name}
                </button>
              {:else}<span></span>{/if}
              {#if fileIx < vault.files.length - 1}
                <button class="v-page-btn v-page-next" on:click={() => openFile(vault.files[fileIx + 1].path)}>
                  {vault.files[fileIx + 1].name} <Icon name="arrow-right" size={13} />
                </button>
              {/if}
            </div>
          {/if}
        </div>

        <footer class="v-status">
          <span>{file.words} words · {readMin} min read</span>
          <span class="v-status-hint">←/→ to page · ⌘P to jump · hover a link to peek</span>
        </footer>
      </section>
    </div>
  </div>

  <!-- ── Wikilink hover preview ──────────────────────────────────────────────── -->
  {#if preview}
    <!-- Hover card: mouseenter/leave only, no click target. It exists to keep
         itself open while the pointer is inside; keyboard users reach the same
         note by activating the link itself. -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div class="v-preview" style="left: {preview.x}px; top: {preview.y}px;"
         on:mouseenter={holdPreview} on:mouseleave={releasePreview}>
      <div class="v-md v-md-mini">{@html preview.html}</div>
      <button class="v-preview-open" on:click={() => openFile(preview.path)}>Open note →</button>
    </div>
  {/if}

  <!-- ── Quick switcher (⌘P) ────────────────────────────────────────────────── -->
  {#if switcherOpen}
    <!-- Same as the tree scrim: pointer convenience; Escape closes the
         switcher for everyone else. -->
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div class="v-sw-scrim" on:click={() => (switcherOpen = false)}></div>
    <div class="v-switcher" role="dialog" aria-label="Quick switcher">
      <input bind:this={switcherInput} bind:value={switcherQ} on:input={() => (switcherIx = 0)}
             placeholder="Jump to a note…" aria-label="Find a file" />
      <div class="v-sw-list">
        {#each switcherHits as f, i (f.path)}
          <button class="v-sw-hit" class:on={i === switcherIx}
                  on:mouseenter={() => (switcherIx = i)}
                  on:click={() => { switcherOpen = false; openFile(f.path); }}>
            <Icon name="file-text" size={13} /> {f.name}
            <span class="v-sw-path">{f.path}</span>
          </button>
        {:else}
          <div class="v-sw-none">No matching file</div>
        {/each}
      </div>
    </div>
  {/if}
{/if}

<style>
  /* ── Frame ─────────────────────────────────────────────────────────────── */
  .vault {
    display: flex; flex-direction: column;
    height: calc(100dvh - 130px); min-height: 480px;
    border: 1px solid hsl(var(--pg-border)); border-radius: 18px;
    background: hsl(var(--pg-surface)); overflow: hidden;
  }
  .v-flex { flex: 1; }
  .v-link { color: hsl(38 65% 35%); font-weight: 600; text-decoration: none; }
  :global(.dark) .v-link { color: hsl(45 85% 66%); }

  .v-top {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 14px; border-bottom: 1px solid hsl(var(--pg-border));
    background: hsl(var(--pg-elevated)); flex-shrink: 0;
  }
  .v-burger {
    display: none; border: none; background: transparent; cursor: pointer;
    color: hsl(var(--pg-fg-muted)); padding: 4px;
  }
  .v-crumb {
    display: inline-flex; align-items: center; gap: 5px; text-decoration: none;
    font-size: 12.5px; font-weight: 600; color: hsl(var(--pg-fg-muted));
  }
  .v-crumb:hover { color: hsl(var(--pg-fg)); }
  .v-crumb-sep { color: hsl(var(--pg-fg-subtle)); font-size: 12px; }
  .v-vaultname {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 13px; font-weight: 700; color: hsl(var(--pg-fg));
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 34ch;
  }
  .v-act {
    display: inline-flex; align-items: center; gap: 6px; cursor: pointer; text-decoration: none;
    border: 1px solid hsl(var(--pg-border)); background: hsl(var(--pg-surface));
    color: hsl(var(--pg-fg)); border-radius: 9px; padding: 6px 10px;
    font: 600 12px Inter, system-ui, sans-serif;
    transition: border-color .14s;
  }
  .v-act:hover { border-color: hsl(266 55% 60%); }
  .v-act kbd {
    font: 600 10px 'JetBrains Mono', monospace; color: hsl(var(--pg-fg-muted));
    border: 1px solid hsl(var(--pg-border)); border-radius: 4px; padding: 1px 4px;
  }
  .v-act-primary { background: hsl(266 60% 46%); border-color: hsl(266 60% 46%); color: white; }
  .v-act-primary:hover { border-color: hsl(266 60% 46%); filter: brightness(1.1); }

  /* ── Tree ──────────────────────────────────────────────────────────────── */
  .v-body { display: flex; flex: 1; min-height: 0; }
  .v-tree {
    width: 240px; flex-shrink: 0; overflow-y: auto;
    border-right: 1px solid hsl(var(--pg-border));
    background: hsl(var(--pg-elevated));
    padding: 10px 8px; display: flex; flex-direction: column; gap: 1px;
  }
  .v-tree-head {
    font: 700 10px 'JetBrains Mono', monospace; letter-spacing: .08em; text-transform: uppercase;
    color: hsl(var(--pg-fg-subtle)); padding: 2px 8px 8px;
  }
  .v-folder, .v-file {
    display: flex; align-items: center; gap: 7px; width: 100%; text-align: left;
    border: none; background: transparent; cursor: pointer; border-radius: 7px;
    padding: 6px 8px; font: 500 12.5px Inter, system-ui, sans-serif;
    color: hsl(var(--pg-fg-muted));
  }
  .v-folder { font-weight: 700; color: hsl(var(--pg-fg)); }
  .v-file span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .v-file span em { font-style: normal; opacity: .45; }
  .v-file:hover, .v-folder:hover { background: hsl(var(--pg-hover)); }
  .v-file.on { background: hsl(266 60% 46% / 0.14); color: hsl(266 60% 44%); font-weight: 600; }
  :global(.dark) .v-file.on { background: hsl(266 55% 40% / 0.3); color: hsl(266 85% 84%); }
  .v-file-nested { padding-left: 30px; }
  .v-tree-foot {
    margin-top: auto; padding: 12px 8px 4px; font-size: 10.5px; line-height: 1.5;
    color: hsl(var(--pg-fg-subtle));
  }
  .v-tree-scrim { display: none; }

  /* ── Reading pane ──────────────────────────────────────────────────────── */
  .v-pane { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .v-tabbar {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 16px; border-bottom: 1px solid hsl(var(--pg-border)); flex-shrink: 0;
  }
  .v-tab {
    display: inline-flex; align-items: center; gap: 6px;
    font: 600 12px 'JetBrains Mono', monospace; color: hsl(var(--pg-fg-muted));
  }
  .v-mode {
    border: none; background: transparent; cursor: pointer; border-radius: 6px;
    padding: 5px 7px; color: hsl(var(--pg-fg-subtle));
  }
  .v-mode.on { background: hsl(var(--pg-hover)); color: hsl(var(--pg-fg)); }
  @media (pointer: coarse) {
    .v-mode { min-width: 40px; min-height: 40px; display: grid; place-items: center; }
  }

  .v-reader { flex: 1; overflow-y: auto; padding: 26px clamp(18px, 5vw, 56px) 30px; }
  .v-raw {
    font: 12.5px/1.7 'JetBrains Mono', ui-monospace, monospace;
    color: hsl(var(--pg-fg)); white-space: pre-wrap; margin: 0;
  }

  .v-md { max-width: 72ch; }
  .v-md :global(h1) {
    font-family: 'Playfair Display', serif; font-size: 27px; font-weight: 700;
    line-height: 1.2; color: hsl(var(--pg-fg)); margin: 0 0 14px;
  }
  .v-md :global(h2) {
    font-size: 16px; font-weight: 700; color: hsl(var(--pg-fg));
    margin: 26px 0 10px; padding-bottom: 6px; border-bottom: 1px solid hsl(var(--pg-border));
  }
  .v-md :global(h3) { font-size: 14px; font-weight: 700; color: hsl(var(--pg-fg)); margin: 20px 0 8px; }
  .v-md :global(p) { font-size: 14.5px; line-height: 1.75; color: hsl(var(--pg-fg)); margin: 0 0 12px; }
  .v-md :global(ul), .v-md :global(ol) { margin: 0 0 12px; padding-left: 22px; }
  .v-md :global(ul) { list-style: disc; }     /* Tailwind preflight zeroes these */
  .v-md :global(ol) { list-style: decimal; }
  .v-md :global(li) { font-size: 14px; line-height: 1.7; color: hsl(var(--pg-fg)); margin: 4px 0; }
  .v-md :global(blockquote) {
    border-left: 3px solid hsl(266 55% 62%); margin: 0 0 12px; padding: 2px 0 2px 14px;
    color: hsl(var(--pg-fg-muted)); font-size: 14px; line-height: 1.7;
  }
  .v-md :global(hr) { border: none; border-top: 1px solid hsl(var(--pg-border)); margin: 22px 0; }
  .v-md :global(code) {
    font: 12.5px 'JetBrains Mono', monospace; background: hsl(var(--pg-hover));
    border-radius: 5px; padding: 1px 5px;
  }
  .v-md :global(a.v-ext) { color: hsl(38 65% 35%); font-weight: 600; text-decoration: none; border-bottom: 1px dotted currentColor; }
  :global(.dark) .v-md :global(a.v-ext) { color: hsl(45 85% 66%); }
  .v-md :global(a.v-wiki) {
    color: hsl(266 60% 44%); font-weight: 600; text-decoration: none;
    border-bottom: 1px solid hsl(266 60% 44% / 0.35); cursor: pointer;
  }
  :global(.dark) .v-md :global(a.v-wiki) { color: hsl(266 85% 80%); border-bottom-color: hsl(266 85% 80% / 0.35); }
  .v-md :global(.v-wiki-missing) { color: hsl(var(--pg-fg-subtle)); border-bottom: 1px dashed currentColor; }
  .v-md :global(.v-callout) {
    border: 1px solid hsl(266 55% 62% / 0.4); border-radius: 12px;
    background: hsl(266 60% 60% / 0.07); padding: 12px 14px; margin: 0 0 14px;
  }
  .v-md :global(.v-callout-info) { border-color: hsl(45 80% 55% / 0.5); background: hsl(45 85% 58% / 0.08); }
  .v-md :global(.v-callout-t) {
    font-size: 11px; font-weight: 800; letter-spacing: .07em; text-transform: uppercase;
    color: hsl(266 60% 48%); margin-bottom: 5px;
  }
  :global(.dark) .v-md :global(.v-callout-t) { color: hsl(266 85% 80%); }
  .v-md :global(.v-callout-info .v-callout-t) { color: hsl(38 65% 38%); }
  :global(.dark) .v-md :global(.v-callout-info .v-callout-t) { color: hsl(45 88% 70%); }
  .v-md :global(.v-callout-b p) { margin: 0; font-size: 13.5px; }
  .v-md-mini :global(h1) { font-size: 17px; margin-bottom: 8px; }
  .v-md-mini :global(p), .v-md-mini :global(li) { font-size: 12.5px; }

  /* ── Backlinks / pager / status ────────────────────────────────────────── */
  .v-backlinks {
    max-width: 72ch; margin-top: 26px; padding: 12px 14px;
    border: 1px dashed hsl(var(--pg-border)); border-radius: 12px;
  }
  .v-bl-head {
    display: flex; align-items: center; gap: 6px;
    font-size: 10.5px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase;
    color: hsl(var(--pg-fg-subtle)); margin-bottom: 8px;
  }
  .v-bl {
    display: inline-flex; margin: 0 8px 4px 0; cursor: pointer;
    border: 1px solid hsl(var(--pg-border)); background: hsl(var(--pg-elevated));
    border-radius: 999px; padding: 4px 11px; font: 600 12px Inter, sans-serif;
    color: hsl(var(--pg-fg-muted));
  }
  .v-bl:hover { border-color: hsl(266 55% 60%); color: hsl(var(--pg-fg)); }
  .v-pager {
    max-width: 72ch; display: flex; justify-content: space-between; gap: 10px; margin-top: 20px;
  }
  .v-page-btn {
    display: inline-flex; align-items: center; gap: 7px; cursor: pointer;
    border: 1px solid hsl(var(--pg-border)); background: hsl(var(--pg-elevated));
    border-radius: 10px; padding: 9px 14px; font: 600 12.5px Inter, sans-serif;
    color: hsl(var(--pg-fg)); max-width: 48%;
  }
  .v-page-btn:hover { border-color: hsl(266 55% 60%); }
  .v-status {
    display: flex; justify-content: space-between; gap: 10px; flex-shrink: 0;
    padding: 7px 16px; border-top: 1px solid hsl(var(--pg-border));
    font: 500 11px 'JetBrains Mono', monospace; color: hsl(var(--pg-fg-subtle));
  }

  /* ── Hover preview ─────────────────────────────────────────────────────── */
  .v-preview {
    position: fixed; z-index: 70; width: min(360px, 90vw); max-height: 300px; overflow: hidden;
    background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border));
    border-radius: 14px; padding: 14px 16px 10px;
    box-shadow: 0 18px 50px -18px hsl(24 40% 8% / 0.45);
    animation: v-pop .12s ease-out;
  }
  @keyframes v-pop { from { opacity: 0; transform: translateY(4px); } }
  .v-preview::after {
    content: ''; position: absolute; inset: auto 0 34px 0; height: 60px; pointer-events: none;
    background: linear-gradient(transparent, hsl(var(--pg-elevated)));
  }
  .v-preview-open {
    position: relative; z-index: 1; margin-top: 6px; cursor: pointer;
    border: none; background: transparent; padding: 4px 0;
    font: 700 12px Inter, sans-serif; color: hsl(266 60% 46%);
  }
  :global(.dark) .v-preview-open { color: hsl(266 85% 80%); }

  /* ── Quick switcher ────────────────────────────────────────────────────── */
  .v-sw-scrim { position: fixed; inset: 0; z-index: 71; background: hsl(24 48% 8% / 0.4); backdrop-filter: blur(2px); }
  .v-switcher {
    position: fixed; z-index: 72; top: 18vh; left: 50%; transform: translateX(-50%);
    width: min(520px, 92vw);
    background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border));
    border-radius: 16px; overflow: hidden;
    box-shadow: 0 30px 80px -24px hsl(24 40% 8% / 0.55);
  }
  .v-switcher input {
    width: 100%; border: none; outline: none; background: transparent;
    padding: 14px 16px; font: 500 15px Inter, sans-serif; color: hsl(var(--pg-fg));
    border-bottom: 1px solid hsl(var(--pg-border)); box-sizing: border-box;
  }
  .v-sw-list { max-height: 300px; overflow-y: auto; padding: 6px; }
  .v-sw-hit {
    display: flex; align-items: center; gap: 8px; width: 100%; text-align: left;
    border: none; background: transparent; cursor: pointer; border-radius: 9px;
    padding: 9px 10px; font: 600 13px Inter, sans-serif; color: hsl(var(--pg-fg));
  }
  .v-sw-hit.on { background: hsl(266 60% 46% / 0.12); }
  :global(.dark) .v-sw-hit.on { background: hsl(266 55% 40% / 0.3); }
  .v-sw-path { margin-left: auto; font: 500 10.5px 'JetBrains Mono', monospace; color: hsl(var(--pg-fg-subtle)); }
  .v-sw-none { padding: 14px; font-size: 13px; color: hsl(var(--pg-fg-muted)); text-align: center; }

  /* ── Empty / loading ───────────────────────────────────────────────────── */
  .v-empty {
    text-align: center; padding: 90px 20px; display: flex; flex-direction: column; gap: 12px; align-items: center;
    background: hsl(var(--pg-surface)); border: 1px dashed hsl(var(--pg-border)); border-radius: 1.75rem;
  }
  .v-empty h2 { font-family: 'Playfair Display', serif; font-size: 24px; margin: 0; color: hsl(var(--pg-fg)); }
  .v-empty p { font-size: 14px; color: hsl(var(--pg-fg-muted)); margin: 0; }
  .v-skel {
    display: inline-block; height: 14px; border-radius: 6px;
    background: linear-gradient(90deg, hsl(var(--pg-hover)) 25%, hsl(var(--pg-border)) 50%, hsl(var(--pg-hover)) 75%);
    background-size: 200% 100%; animation: v-shimmer 1.4s ease-in-out infinite;
  }
  @keyframes v-shimmer { to { background-position: -200% 0; } }

  /* ── Mobile: tree becomes an overlay drawer ───────────────────────────── */
  @media (max-width: 760px) {
    .vault { height: calc(100dvh - 110px); border-radius: 14px; }
    .v-burger { display: inline-flex; }
    .v-act-label, .v-act kbd, .v-crumb-sep, .v-vaultname { display: none; }
    .v-tree {
      position: absolute; z-index: 40; top: 49px; bottom: 0; left: 0;
      transform: translateX(-105%); transition: transform .2s ease;
      box-shadow: 20px 0 40px -20px hsl(24 40% 8% / 0.4);
    }
    .v-tree.open { transform: translateX(0); }
    .v-tree-scrim { display: block; position: absolute; z-index: 39; inset: 49px 0 0 0; background: hsl(24 48% 8% / 0.35); }
    .vault { position: relative; }
    .v-status-hint { display: none; }
  }

  @media (prefers-reduced-motion: reduce) {
    .v-skel, .v-preview { animation: none; }
    .v-tree { transition: none; }
  }
</style>
