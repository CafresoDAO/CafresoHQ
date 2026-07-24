<script>
  /* THE FULL LIBRARY ENTRY — the article-page counterpart to the /library
     drawer. The drawer is a quick-peek popover capped by viewport height and
     clipped; this route is the shareable, linkable, unclipped read: full
     answer, full Coverage Details, every source, the entry's own graph, and
     comments below the fold — closer to a Ground.news article page or a blog
     post than a slide-in panel. The drawer stays for fast in-grid browsing;
     "Open full entry" here is for actually reading one. */
  import { page } from '$app/stores';
  import Icon from '$lib/components/Icon.svelte';
  import CommentThread from '$lib/components/CommentThread.svelte';
  import { listComments, postComment } from '$lib/api/devlog.js';
  import { principalText } from '$lib/stores/auth.js';
  import { profile } from '$lib/stores/profile.js';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { libraryEntry, libraryResearch, libraryIndex } from '$lib/api/searchNetwork.js';
  import { libraryGraphViewerUrl, libraryEntryEnrichment } from '$lib/api/library.js';
  import { fmtNsDate } from '$lib/utils/time.js';
  import { relatedEntries } from '$lib/utils/digest.js';
  import RelatedEntries from '$lib/components/RelatedEntries.svelte';

  let id = null;
  let entry = null;      // null while loading
  let missing = false;
  let enrich = null;     // {byUrl, suggests, favicons} from the entry graph
  let research = null;   // deep entries: {pages:[…]}
  let openPageId = null;
  let comments = [];
  let commentErr = null;
  const libCommentSlug = (eid) => `library-${eid}`;

  // The one extra fetch this page needs for "Related in the library" — the
  // drawer already has the index in memory from the grid page, but a direct
  // /library/<id> visit doesn't. Cheap (one JSON GET) and not on the critical
  // path: the entry itself renders from libraryEntry() without waiting on it.
  let libIndex = null;
  onMount(() => { libraryIndex().then((ix) => { libIndex = ix; }); });
  $: related = entry && libIndex?.entries ? relatedEntries(entry, libIndex.entries) : [];

  $: {
    const p = $page.params.id;
    if (p !== id) { id = p; load(id); }
  }

  async function load(eid) {
    entry = null; missing = false; enrich = null; research = null; comments = []; commentErr = null; openPageId = null;
    if (!eid) return;
    const e = await libraryEntry(eid);
    if (eid !== id) return;
    if (e && e.id) {
      entry = e;
      libraryEntryEnrichment(eid).then((en) => { if (eid === id) enrich = en; });
      listComments(libCommentSlug(eid)).then((c) => { if (eid === id) comments = c || []; });
      if (e.mode === 'deep') {
        const r = await libraryResearch(eid);
        if (eid === id && r && r.pages) research = r;
      }
    } else missing = true;
  }

  async function postEntryComment(text) {
    if (!id) return;
    commentErr = null;
    const author = {
      name: $profile?.name || ($principalText ? `${$principalText.slice(0, 5)}…${$principalText.slice(-3)}` : 'Guest'),
      role: $profile?.bio ? 'Member' : 'Community',
      hue: 24
    };
    const res = await postComment(libCommentSlug(id), author, text);
    if (res?.err) { commentErr = res.err; return; }
    comments = await listComments(libCommentSlug(id));
  }

  // Same two-layer fix as the drawer: srcAges must be read directly inside
  // the {#each} block via {@const}, not through a wrapper function, or
  // Svelte's legacy per-block dependency scan never invalidates the block
  // when the async enrichment fetch resolves.
  $: srcAges = enrich && enrich.byUrl ? enrich.byUrl : new Map();
  $: oldestSourceAge = (() => {
    let oldest = null;
    for (const v of srcAges.values()) {
      if (v.age && /^\d{4}-\d{2}-\d{2}/.test(v.age) && (!oldest || v.age < oldest)) oldest = v.age;
    }
    return oldest;
  })();

  function togglePage(pid) { openPageId = openPageId === pid ? null : pid; }
  function plain(t) { return String(t || '').replace(/<[^>]+>/g, ''); }
  const fmtDate = (ns) => fmtNsDate(ns, 'short');
  function shortPrincipal(p) {
    if (!p) return '';
    return p.length > 12 ? p.slice(0, 5) + '…' + p.slice(-3) : p;
  }
  function domain(url) {
    try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url; }
  }
  // Sources are worker-authored — same untrusted-URL scheme gate as the drawer.
  function safeHref(url) { return /^https?:\/\//i.test(url || '') ? url : '#'; }
  function askedByAi(e) { return /\bai-gap\b/.test(String(e?.engine || '')); }
  function engineLabel(e) { return String(e?.engine || '').replace(/\s*·?\s*\bai-gap\b/, '').trim() || 'brave'; }
</script>

<svelte:head>
  <title>{entry ? plain(entry.query) : 'Library entry'} · Ai Cafreso Search</title>
  {#if entry?.answer}<meta name="description" content={plain(entry.answer).slice(0, 200)} />{/if}
</svelte:head>

<div class="lea-page">
  <a class="lea-back" href="/library"><Icon name="arrow-left" size={13} /> Back to the library</a>

  {#if entry}
    <div class="lea-kicker">Library entry · {entry.id}</div>
    <h1 class="lea-q">{plain(entry.query)}</h1>
    <div class="lea-chips">
      {#if entry.mode === 'deep'}
        <span class="lea-chip lea-chip-deep"><Icon name="tree-structure" size={11} /> Deep research</span>
      {/if}
      {#if askedByAi(entry)}
        <span class="lea-chip lea-chip-ai"
              title="Nobody asked this one. Cafreso read the library, found a gap in what it covers, and asked to fill it.">
          ✦ Asked by Cafreso to fill a gap
        </span>
      {/if}
      {#if entry.model}<span class="lea-chip">🤖 {entry.model}</span>{/if}
      {#if entry.engine}<span class="lea-chip">🔎 {engineLabel(entry)}</span>{/if}
      <span class="lea-chip">📅 {fmtDate(entry.answeredAt || entry.ts)}</span>
      {#if entry.worker}<span class="lea-chip" title={entry.worker}>⚙ {shortPrincipal(entry.worker)}</span>{/if}
    </div>

    {#if entry.sources?.length}
      <div class="lea-coverage">
        <div class="lea-coverage-stat">
          <span class="lea-coverage-n">{entry.sources.length}</span>
          <span class="lea-coverage-label">source{entry.sources.length === 1 ? '' : 's'}</span>
        </div>
        {#if oldestSourceAge}
          <div class="lea-coverage-stat">
            <span class="lea-coverage-n">{oldestSourceAge}</span>
            <span class="lea-coverage-label">oldest source</span>
          </div>
        {/if}
        {#if enrich?.suggests?.length}
          <div class="lea-coverage-stat">
            <span class="lea-coverage-n">{enrich.suggests.length}</span>
            <span class="lea-coverage-label">related question{enrich.suggests.length === 1 ? '' : 's'}</span>
          </div>
        {/if}
        {#if enrich?.favicons?.length}
          <div class="lea-coverage-favs" title="Sites cited in this answer">
            {#each enrich.favicons.slice(0, 10) as f}
              <img src={f} alt="" loading="lazy" on:error={(ev) => { ev.target.style.visibility = 'hidden'; }} />
            {/each}
          </div>
        {/if}
      </div>
    {/if}

    <div class="lea-body">
      <div class="lea-main">
        {#if entry.answer}
          <p class="lea-answer">{plain(entry.answer)}</p>
        {:else}
          <p class="lea-answer lea-muted">Sources were collected for this question, but no summary was written yet.</p>
        {/if}

        {#if entry.mode === 'deep' && research?.pages?.length}
          <div class="lea-kicker" style="margin-top: 30px;">The research tree · {research.pages.length} note pages</div>
          <p class="lea-deep-lede">
            This question was researched from several angles. Open a page to read the note, browse the whole
            thing as a vault of linked markdown files, or explore the tree in the graph below.
          </p>
          <a class="lea-vault-btn" href="/library/vault?e={entry.id}">
            <Icon name="vault" size={15} />
            <span class="lea-vault-btn-t">
              <strong>Browse Research</strong>
              <small>File tree · wikilinks · download as .md for Obsidian</small>
            </span>
            <Icon name="arrow-right" size={14} />
          </a>
          <div class="lea-pages">
            {#each research.pages as p, i}
              <div class="lea-page" class:open={openPageId === p.id}>
                <button class="lea-page-head" on:click={() => togglePage(p.id)} aria-expanded={openPageId === p.id}>
                  <span class="lea-page-n">{i + 1}</span>
                  <span class="lea-page-title">
                    <span class="lea-page-t">{plain(p.title)}</span>
                    {#if p.question}<span class="lea-page-q">{plain(p.question)}</span>{/if}
                  </span>
                  <Icon name={openPageId === p.id ? 'caret-up' : 'caret-down'} size={14} style="flex-shrink: 0; color: hsl(var(--pg-fg-muted));" />
                </button>
                {#if openPageId === p.id}
                  <div class="lea-page-body">
                    <p class="lea-page-note">{plain(p.body)}</p>
                    {#if p.sources?.length}
                      <ol class="lea-sources" style="margin-top: 12px;">
                        {#each p.sources as s, si}
                          <li>
                            <a href={safeHref(s.url)} target="_blank" rel="noopener noreferrer">
                              <span class="lea-src-n">[{si + 1}]</span>
                              <span class="lea-src-t">{plain(s.title)}</span>
                              <span class="lea-src-d">{domain(s.url)}</span>
                            </a>
                          </li>
                        {/each}
                      </ol>
                    {/if}
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        {/if}

        {#if libraryGraphViewerUrl(entry.id)}
          {@const deepEntry = entry.mode === 'deep'}
          {@const gvUrl = libraryGraphViewerUrl(entry.id, { deep: deepEntry })}
          <div class="lea-kicker" style="margin-top: 30px;">{deepEntry ? 'The research tree, explorable' : 'This answer as a graph'}</div>
          <iframe
            src={gvUrl}
            title={deepEntry ? 'The research tree — click a topic to read its note' : 'Graph of this answer'}
            class="lea-graph"
            loading="lazy"
          ></iframe>
          <div class="lea-graph-actions">
            <a class="lea-link" href={gvUrl} target="_blank" rel="noopener noreferrer">
              {deepEntry ? 'Open the research tree' : 'Open graph'} <Icon name="arrow-up-right" size={12} />
            </a>
            <button class="lea-link" style="border: none; background: transparent; cursor: pointer; font: inherit; padding: 0;"
              on:click={() => { try { navigator.clipboard.writeText(location.href); } catch {} }}>
              Copy link
            </button>
          </div>
        {/if}

        <div class="lea-kicker" style="margin-top: 30px;">Discussion</div>
        {#if commentErr}
          <p class="lea-comment-err">{commentErr}</p>
        {/if}
        <CommentThread {comments} onPost={postEntryComment} modSlug={libCommentSlug(entry.id)} />
      </div>

      <aside class="lea-side">
        {#if entry.sources?.length}
          <div class="lea-kicker">Sources</div>
          <ol class="lea-sources">
            {#each entry.sources as s, i}
              {@const age = srcAges.get(s.url)?.age}
              <li>
                <a href={safeHref(s.url)} target="_blank" rel="noopener noreferrer">
                  <span class="lea-src-n">[{i + 1}]</span>
                  <span class="lea-src-t">{plain(s.title)}</span>
                  {#if age}<span class="lea-src-age">{age}</span>{/if}
                  <span class="lea-src-d">{domain(s.url)}</span>
                </a>
              </li>
            {/each}
          </ol>
        {/if}

        {#if enrich?.suggests?.length}
          <div class="lea-kicker" style="margin-top: 22px;">People also wonder</div>
          <p class="lea-ask-lede">Questions the web raised alongside this one.</p>
          <div class="lea-ask-chips">
            {#each enrich.suggests.slice(0, 8) as sug}
              <a class="lea-ask-chip" href="/library?ask={encodeURIComponent(sug.q)}" title={sug.a || sug.q}>
                <span aria-hidden="true">✦</span> {plain(sug.q)}
              </a>
            {/each}
          </div>
        {/if}

        {#if related.length}
          <div style="margin-top: 22px;">
            <RelatedEntries items={related} {plain} onOpen={(rid) => goto(`/library/${rid}`)} />
          </div>
        {/if}
      </aside>
    </div>
  {:else if missing}
    <div class="lea-empty">
      <h2>Entry not found</h2>
      <p>It may have been withdrawn by its author.</p>
    </div>
  {:else}
    <div class="lea-skel" style="width: 30%; height: 12px; margin: 10px 0 18px;"></div>
    <div class="lea-skel" style="width: 80%; height: 34px; margin-bottom: 20px;"></div>
    <div class="lea-skel" style="width: 100%; height: 14px; margin-bottom: 8px;"></div>
    <div class="lea-skel" style="width: 96%; height: 14px; margin-bottom: 8px;"></div>
    <div class="lea-skel" style="width: 70%; height: 14px;"></div>
  {/if}
</div>

<style>
  .lea-page { max-width: 920px; margin: 0 auto; padding: 32px 20px 80px; }
  .lea-back {
    display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 600;
    color: hsl(var(--pg-fg-muted)); text-decoration: none; margin-bottom: 22px;
  }
  .lea-back:hover { color: hsl(45 85% 45%); }
  .lea-kicker {
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .08em;
    color: hsl(45 80% 45%); margin-bottom: 8px;
  }
  .lea-q { font-family: 'Playfair Display', serif; font-size: 30px; line-height: 1.25; margin: 0 0 16px; color: hsl(var(--pg-fg)); }
  .lea-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 20px; }
  .lea-chip {
    display: inline-flex; align-items: center; gap: 4px; font-size: 11.5px; font-weight: 600;
    padding: 4px 9px; border-radius: 999px; background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border));
    color: hsl(var(--pg-fg-muted));
  }
  .lea-chip-deep { background: hsl(266 60% 94%); color: hsl(266 45% 40%); border-color: hsl(266 50% 82%); }
  .lea-chip-ai { background: hsl(45 80% 94%); color: hsl(38 65% 32%); border-color: hsl(45 60% 78%); }
  .lea-coverage {
    display: flex; align-items: center; gap: 26px; flex-wrap: wrap;
    padding: 14px 18px; margin-bottom: 24px; border-radius: 14px;
    background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border));
  }
  .lea-coverage-stat { display: flex; flex-direction: column; gap: 1px; }
  .lea-coverage-n { font-size: 17px; font-weight: 700; color: hsl(var(--pg-fg)); font-family: 'JetBrains Mono', ui-monospace, monospace; }
  .lea-coverage-label { font-size: 10.5px; text-transform: uppercase; letter-spacing: .05em; color: hsl(var(--pg-fg-muted)); }
  .lea-coverage-favs { display: inline-flex; align-items: center; margin-left: auto; }
  .lea-coverage-favs img {
    width: 22px; height: 22px; border-radius: 50%; border: 2px solid hsl(var(--pg-bg));
    background: hsl(var(--pg-surface)); margin-left: -7px; object-fit: cover;
  }
  .lea-coverage-favs img:first-child { margin-left: 0; }

  .lea-body { display: grid; grid-template-columns: 1fr 280px; gap: 40px; align-items: start; }
  @media (max-width: 760px) { .lea-body { grid-template-columns: 1fr; } }
  .lea-main { min-width: 0; }
  .lea-side { min-width: 0; position: sticky; top: 20px; }
  @media (max-width: 760px) { .lea-side { position: static; margin-top: 30px; } }

  .lea-answer { font-size: 16px; line-height: 1.75; color: hsl(var(--pg-fg)); margin: 0; white-space: pre-wrap; }
  .lea-muted { color: hsl(var(--pg-fg-muted)); font-style: italic; }

  .lea-sources { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
  .lea-sources a {
    display: flex; align-items: center; gap: 7px; padding: 8px 10px; border-radius: 9px;
    background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border)); text-decoration: none;
    font-size: 12.5px; color: hsl(var(--pg-fg));
  }
  .lea-sources a:hover { border-color: hsl(45 70% 55%); }
  .lea-src-n { color: hsl(var(--pg-fg-muted)); font-size: 11px; flex-shrink: 0; }
  .lea-src-t { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
  .lea-src-d { color: hsl(var(--pg-fg-muted)); font-size: 11px; font-family: 'JetBrains Mono', monospace; flex-shrink: 0; }
  .lea-src-age {
    font-size: 10.5px; font-family: 'JetBrains Mono', monospace; color: hsl(45 70% 40%);
    background: hsl(45 80% 92%); padding: 1px 5px; border-radius: 5px; flex-shrink: 0;
  }

  .lea-ask-lede { font-size: 12px; line-height: 1.5; color: hsl(var(--pg-fg-muted)); margin: 4px 0 10px; }
  .lea-ask-chips { display: flex; flex-direction: column; gap: 7px; }
  .lea-ask-chip {
    display: block; text-align: left; font-size: 12.5px; line-height: 1.4; padding: 8px 10px;
    border-radius: 9px; border: 1px solid hsl(var(--pg-border)); background: hsl(var(--pg-surface));
    color: hsl(var(--pg-fg)); cursor: pointer; text-decoration: none;
  }
  .lea-ask-chip:hover { border-color: hsl(266 55% 62%); background: hsl(266 65% 95%); }
  .lea-ask-chip span { color: hsl(45 75% 50%); }

  .lea-vault-btn {
    display: flex; align-items: center; gap: 12px; padding: 12px 14px; margin-bottom: 14px;
    border-radius: 12px; border: 1px solid hsl(266 50% 80%); background: hsl(266 60% 97%);
    text-decoration: none; color: hsl(var(--pg-fg));
  }
  .lea-vault-btn:hover { border-color: hsl(266 60% 58%); transform: translateY(-1px); }
  .lea-vault-btn-t { flex: 1; display: flex; flex-direction: column; gap: 1px; }
  .lea-vault-btn-t strong { font-size: 13.5px; }
  .lea-vault-btn-t small { font-size: 11px; color: hsl(266 30% 52%); }
  .lea-deep-lede { font-size: 13px; line-height: 1.6; color: hsl(var(--pg-fg-muted)); margin: 6px 0 12px; }
  .lea-pages { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }
  .lea-page { border: 1px solid hsl(var(--pg-border)); border-radius: 12px; overflow: hidden; background: hsl(var(--pg-surface)); }
  .lea-page.open { border-color: hsl(266 55% 72%); }
  .lea-page-head {
    width: 100%; display: flex; align-items: center; gap: 10px; padding: 12px 14px;
    background: none; border: none; cursor: pointer; text-align: left; font: inherit;
  }
  .lea-page-n {
    flex-shrink: 0; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center;
    justify-content: center; font-size: 11px; font-weight: 700; background: hsl(266 60% 92%); color: hsl(266 45% 40%);
  }
  .lea-page-title { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .lea-page-t { font-size: 13.5px; font-weight: 600; color: hsl(var(--pg-fg)); }
  .lea-page-q { font-size: 11.5px; color: hsl(var(--pg-fg-muted)); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .lea-page-body { padding: 0 14px 14px 46px; }
  .lea-page-note { font-size: 13.5px; line-height: 1.68; color: hsl(var(--pg-fg)); margin: 0; white-space: pre-wrap; }

  .lea-graph { width: 100%; height: 460px; border: 1px solid hsl(var(--pg-border)); border-radius: 14px; display: block; }
  .lea-graph-actions { display: flex; gap: 16px; margin-top: 10px; font-size: 12.5px; }
  .lea-link { color: hsl(45 85% 62%); font-weight: 600; text-decoration: none; display: inline-flex; align-items: center; gap: 3px; }
  .lea-comment-err {
    font-size: 12.5px; color: hsl(0 65% 45%); background: hsl(0 70% 96%); border: 1px solid hsl(0 60% 85%);
    border-radius: 8px; padding: 8px 10px; margin: 6px 0 10px;
  }
  :global(.dark) .lea-comment-err { background: hsl(0 40% 16%); border-color: hsl(0 40% 30%); color: hsl(0 70% 75%); }

  .lea-empty { text-align: center; padding: 80px 10px; }
  .lea-empty h2 { font-family: 'Playfair Display', serif; font-size: 24px; margin: 0 0 8px; color: hsl(var(--pg-fg)); }
  .lea-empty p { font-size: 14px; color: hsl(var(--pg-fg-muted)); }
  .lea-skel { background: linear-gradient(90deg, hsl(var(--pg-surface)) 25%, hsl(var(--pg-border)) 50%, hsl(var(--pg-surface)) 75%);
    background-size: 200% 100%; animation: lea-shimmer 1.4s infinite; border-radius: 6px; }
  @keyframes lea-shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
</style>
