<svelte:options runes={true} />

<script>
  import { onMount } from 'svelte';
  import Icon from '$lib/components/Icon.svelte';

  // Draft key patterns:
  //  Blog:  'cafreso:draft:new'  |  'cafreso:draft:edit:{slug}'
  //  Forum: 'cafreso:forum:draft:new'  |  'cafreso:forum:draft:edit:{slug}'

  let drafts = $state([]);
  let loaded = $state(false);

  function fmtAge(ms) {
    const diff = Date.now() - ms;
    if (diff < 60_000)     return 'just now';
    if (diff < 3_600_000)  return `${Math.floor(diff / 60_000)}m ago`;
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
    return `${Math.floor(diff / 86_400_000)}d ago`;
  }

  function wordCount(text = '') {
    return text.trim().split(/\s+/).filter(Boolean).length;
  }

  function readAllDrafts() {
    const found = [];
    if (typeof localStorage === 'undefined') return found;
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key) continue;

      let type = null;
      let editSlug = null;

      if (key === 'cafreso:draft:new') {
        type = 'blog'; editSlug = null;
      } else if (key.startsWith('cafreso:draft:edit:')) {
        type = 'blog'; editSlug = key.replace('cafreso:draft:edit:', '');
      } else if (key === 'cafreso:forum:draft:new') {
        type = 'forum'; editSlug = null;
      } else if (key.startsWith('cafreso:forum:draft:edit:')) {
        type = 'forum'; editSlug = key.replace('cafreso:forum:draft:edit:', '');
      }

      if (!type) continue;

      try {
        const data = JSON.parse(localStorage.getItem(key) || '{}');
        found.push({
          key,
          type,
          editSlug,
          title:     data.title     || '(Untitled)',
          excerpt:   data.excerpt   || '',
          bodySrc:   data.bodySrc   || '',
          theme:     data.theme     || 'standard',
          category:  data.category  || '',
          savedAt:   data.savedAt   || 0,
        });
      } catch {}
    }
    return found.sort((a, b) => b.savedAt - a.savedAt);
  }

  function deleteDraft(key) {
    localStorage.removeItem(key);
    drafts = drafts.filter((d) => d.key !== key);
  }

  function editUrl(d) {
    if (d.type === 'blog') {
      return d.editSlug ? `/blog/new?edit=${d.editSlug}` : '/blog/new';
    }
    return d.editSlug ? `/forums/new?edit=${d.editSlug}` : '/forums/new';
  }

  onMount(() => {
    drafts = readAllDrafts();
    loaded = true;
  });

  const TYPE_META = {
    blog:  { label: 'Dev Log post', icon: 'article',       color: 'hsl(32 72% 50%)',  bg: 'hsl(32 72% 94%)' },
    forum: { label: 'Forum thread', icon: 'chats-circle',  color: 'hsl(112 43% 40%)', bg: 'hsl(112 40% 92%)' },
  };
</script>

<svelte:head>
  <title>My Drafts · Cafreso</title>
  <meta name="robots" content="noindex" />
</svelte:head>

<div style="max-width: 760px; margin: 0 auto; padding: 36px 18px 80px;">
  <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px;">
    <div style="
      width: 36px; height: 36px; border-radius: 10px;
      background: hsl(32 72% 94%); display: flex; align-items: center; justify-content: center;
    ">
      <Icon name="note-pencil" size={18} style="color: hsl(32 72% 44%);" />
    </div>
    <h1 style="font-size: 26px; font-weight: 800; color: hsl(var(--pg-fg)); letter-spacing: -0.02em; margin: 0;">
      My Drafts
    </h1>
  </div>
  <p style="font-size: 14px; color: hsl(var(--pg-fg-muted)); margin: 0 0 28px; padding-left: 46px;">
    Auto-saved locally · content is stored in your browser until you publish
  </p>

  <!-- Quick actions -->
  <div style="display: flex; gap: 10px; margin-bottom: 28px; flex-wrap: wrap;">
    <a href="/blog/new" style="
      display: inline-flex; align-items: center; gap: 6px;
      padding: 8px 16px; border-radius: 10px; text-decoration: none;
      background: hsl(var(--pg-solid)); color: hsl(var(--pg-solid-fg)); font-size: 13px; font-weight: 600;
    ">
      <Icon name="article" size={14} /> New Dev Log post
    </a>
    <a href="/forums/new" style="
      display: inline-flex; align-items: center; gap: 6px;
      padding: 8px 16px; border-radius: 10px; text-decoration: none;
      background: hsl(112 40% 93%); color: hsl(112 43% 22%);
      border: 1px solid hsl(112 40% 75%); font-size: 13px; font-weight: 600;
    ">
      <Icon name="chats-circle" size={14} /> New Forum thread
    </a>
  </div>

  {#if !loaded}
    <div style="text-align: center; padding: 48px; color: hsl(var(--pg-fg-muted)); font-size: 14px;">
      <Icon name="spinner-gap" size={20} style="display: block; margin: 0 auto 8px;" /> Loading drafts…
    </div>
  {:else if drafts.length === 0}
    <div style="
      text-align: center; padding: 56px 24px;
      border-radius: 16px; border: 1.5px dashed hsl(var(--pg-border));
      background: hsl(var(--pg-surface));
    ">
      <Icon name="note-pencil" size={32} style="opacity: 0.25; display: block; margin: 0 auto 12px; color: hsl(var(--pg-fg));" />
      <div style="font-size: 16px; font-weight: 600; color: hsl(var(--pg-fg)); margin-bottom: 6px;">No drafts saved yet</div>
      <div style="font-size: 13px; color: hsl(var(--pg-fg-muted)); margin-bottom: 20px;">
        Start writing a post or forum thread — it'll auto-save here every 600ms.
      </div>
      <a href="/blog/new" style="
        display: inline-flex; align-items: center; gap: 6px;
        padding: 9px 18px; border-radius: 10px; text-decoration: none;
        background: hsl(var(--pg-solid)); color: hsl(var(--pg-solid-fg)); font-size: 13px; font-weight: 600;
      ">
        <Icon name="pencil-simple" size={14} /> Start writing
      </a>
    </div>
  {:else}
    <div style="font-size: 12px; color: hsl(var(--pg-fg-muted)); margin-bottom: 12px; text-align: right;">
      {drafts.length} draft{drafts.length !== 1 ? 's' : ''} saved locally
    </div>
    <div style="display: flex; flex-direction: column; gap: 10px;">
      {#each drafts as d (d.key)}
        {@const tm = TYPE_META[d.type]}
        {@const words = wordCount(d.bodySrc)}
        <div style="
          border-radius: 14px; border: 1px solid hsl(var(--pg-border));
          background: hsl(var(--pg-surface)); padding: 18px 20px;
          display: flex; align-items: flex-start; gap: 14px;
        ">
          <!-- Type icon -->
          <div style="
            width: 38px; height: 38px; border-radius: 10px; flex-shrink: 0;
            background: {tm.bg}; display: flex; align-items: center; justify-content: center;
          ">
            <Icon name={tm.icon} size={17} style="color: {tm.color};" />
          </div>

          <!-- Content -->
          <div style="flex: 1; min-width: 0;">
            <div style="display: flex; align-items: center; gap: 7px; flex-wrap: wrap; margin-bottom: 4px;">
              <span style="
                font-size: 10px; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase;
                color: {tm.color}; background: {tm.bg}; border-radius: 5px; padding: 2px 7px;
              ">{tm.label}</span>
              {#if d.theme && d.theme !== 'standard'}
                <span style="font-size: 10px; color: hsl(var(--pg-fg-subtle)); background: hsl(var(--pg-hover)); border-radius: 4px; padding: 2px 6px;">
                  Theme: {d.theme}
                </span>
              {/if}
              {#if d.category}
                <span style="font-size: 10px; color: hsl(var(--pg-fg-subtle));">· {d.category}</span>
              {/if}
            </div>
            <div style="font-size: 16px; font-weight: 700; color: hsl(var(--pg-fg)); margin-bottom: 4px; letter-spacing: -0.01em;">
              {d.title}
            </div>
            {#if d.excerpt}
              <div style="
                font-size: 12.5px; color: hsl(var(--pg-fg-muted)); margin-bottom: 6px;
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
              ">{d.excerpt}</div>
            {/if}
            <div style="font-size: 11px; color: hsl(var(--pg-fg-subtle)); display: flex; gap: 10px; flex-wrap: wrap;">
              <span>Saved {fmtAge(d.savedAt)}</span>
              {#if words > 0}
                <span>· ~{words} words</span>
              {/if}
            </div>
          </div>

          <!-- Actions -->
          <div style="display: flex; flex-direction: column; gap: 6px; flex-shrink: 0;">
            <a href={editUrl(d)} style="
              display: inline-flex; align-items: center; gap: 5px;
              padding: 7px 12px; border-radius: 8px; text-decoration: none;
              background: hsl(var(--pg-solid)); color: hsl(var(--pg-solid-fg)); font-size: 12px; font-weight: 600;
            ">
              <Icon name="pencil-simple" size={12} /> Continue
            </a>
            <button
              type="button"
              onclick={() => deleteDraft(d.key)}
              style="
                display: inline-flex; align-items: center; justify-content: center; gap: 5px;
                padding: 6px 12px; border-radius: 8px; font-size: 12px; font-weight: 600;
                background: none; border: 1px solid hsl(0 50% 85%); color: hsl(0 62% 48%);
                cursor: pointer; font-family: inherit;
              "
            >
              <Icon name="trash" size={12} /> Delete
            </button>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
