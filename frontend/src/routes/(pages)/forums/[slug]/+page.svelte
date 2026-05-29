<svelte:options runes={true} />

<script>
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import Icon from '$lib/components/Icon.svelte';
  import Avatar from '$lib/components/Avatar.svelte';
  import Button from '$lib/components/Button.svelte';
  import CommentThread from '$lib/components/CommentThread.svelte';
  import { fmtDate } from '$lib/data/blog.js';
  import { burnTarget, userBurns } from '$lib/stores/blog.js';
  import { getForumPost, listComments, postComment, forumSlug } from '$lib/api/devlog.js';
  import { isAuthenticated, login, principalText } from '$lib/stores/auth.js';
  import { isDevlogAdmin } from '$lib/data/admins.js';
  import { profile } from '$lib/stores/profile.js';
  import { detectMentions } from '$lib/stores/notifications.js';
  import { get } from 'svelte/store';
  import PostRenderer from '$lib/components/PostRenderer.svelte';
  import MentionAutocomplete from '$lib/components/MentionAutocomplete.svelte';
  import { getTheme } from '$lib/themes.js';

  let post = $state(null);
  let loading = $state(true);
  let comments = $state([]);
  let loadingComments = $state(false);
  let commentDraft = $state('');
  let posting = $state(false);
  let commentErr = $state(null);
  let loadedSlug = null;

  const viewSlug = $derived($page.params.slug);
  const userBurned = $derived($userBurns[forumSlug(viewSlug)] || 0);
  // Forum posts use the 'community' theme — warm peach, welcoming feel.
  const forumTheme = $derived(getTheme('community'));
  const body = $derived(
    post?.body && post.body.length > 0
      ? post.body
      : [{ kind: 'p', text: post?.excerpt || '' }]
  );
  const canEdit = $derived(
    !!post &&
      !!$principalText &&
      (post.canister === $principalText || isDevlogAdmin($principalText))
  );
  const authorHandle = $derived(post?.author?.name || 'Guest');

  $effect(() => {
    if (!viewSlug || viewSlug === loadedSlug) return;
    loadedSlug = viewSlug;
    loadAll(viewSlug);
  });

  async function loadAll(v) {
    loading = true;
    post = null;
    comments = [];
    try {
      const fromCanister = await getForumPost(v);
      if (loadedSlug === v) post = fromCanister;
      await refreshComments();
    } finally {
      if (loadedSlug === v) loading = false;
    }
  }

  async function refreshComments() {
    if (!viewSlug) return;
    loadingComments = true;
    try {
      comments = await listComments(forumSlug(viewSlug));
      // Detect @mentions addressed to the current user and push notifications.
      const myName = get(profile)?.name;
      if (myName && comments.length) {
        detectMentions(comments, myName, `/forums/${viewSlug}`);
      }
    } catch (e) {
      console.warn('[forums] listComments failed', e);
      comments = [];
    } finally {
      loadingComments = false;
    }
  }

  async function submitComment(e) {
    e.preventDefault();
    commentErr = null;
    if (!commentDraft.trim()) {
      commentErr = 'Say something first.';
      return;
    }
    posting = true;
    const author = {
      name: $profile.name || ($principalText ? `${$principalText.slice(0, 5)}…${$principalText.slice(-3)}` : 'Guest'),
      role: $profile.bio ? 'Member' : 'Community',
      hue: 24
    };
    const res = await postComment(forumSlug(viewSlug), author, commentDraft.trim());
    posting = false;
    if (res?.err) {
      commentErr = res.err;
      return;
    }
    commentDraft = '';
    await refreshComments();
  }

  function onTip() {
    burnTarget.set(forumSlug(viewSlug));
  }
</script>

<svelte:head>
  <title>{post ? post.title : 'Thread'} · Forums · Cafreso</title>
</svelte:head>

<div class="mx-auto" style="max-width: 820px; padding: 24px 18px 64px;">
  <div class="flex items-center justify-between gap-3 mb-4 flex-wrap">
    <a href="/forums" class="inline-flex items-center gap-1.5 text-[12.5px] no-underline"
      style="color: hsl(215 16% 47%);"
    >
      <Icon name="caret-left" size={13} /> Back to Forums
    </a>
    {#if canEdit}
      <a
        href="/forums/new?edit={viewSlug}"
        class="inline-flex items-center gap-1.5 text-[12px] font-semibold rounded-full px-3 py-1.5 no-underline"
        style="background: hsl(26 40% 96%); border: 1px solid hsl(26 30% 82%); color: hsl(222 47% 11%);"
      >
        <Icon name="pencil-simple" size={12} /> Edit
      </a>
    {/if}
  </div>

  {#if loading}
    <div class="text-center py-10" style="color: hsl(215 16% 47%);">
      <Icon name="spinner-gap" size={18} /> Loading thread…
    </div>
  {:else if !post}
    <div class="text-center py-10">
      <h1 class="text-[26px] font-bold mb-2">Thread not found</h1>
      <a href="/forums" class="underline" style="color: hsl(38 85% 30%);">Back to Forums</a>
    </div>
  {:else}
    <article>
      <div class="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10.5px] font-semibold uppercase mb-3"
        style="background: hsl(26 40% 94%); color: hsl(24 48% 28%); letter-spacing: 0.05em;"
      >
        <Icon name="chats-circle" size={11} /> Forum thread
      </div>
      <h1 class="font-extrabold leading-[1.05] mb-3" style="font-size: clamp(26px, 6vw, 40px); letter-spacing: -0.025em; color: hsl(222 47% 11%); text-wrap: pretty;">
        {post.title}
      </h1>
      <p class="text-[15px] sm:text-[17px] leading-[1.55] mb-5" style="color: hsl(215 16% 35%); max-width: 62ch;">
        {post.excerpt}
      </p>

      <div class="flex items-center gap-3 flex-wrap mb-6 text-[12.5px]" style="color: hsl(215 16% 47%);">
        <div class="inline-flex items-center gap-2">
          <Avatar name={authorHandle} hue={post.author?.hue || 24} size={28} />
          <span class="font-semibold" style="color: hsl(222 47% 11%);">{authorHandle}</span>
        </div>
        <span>· {fmtDate(post.date)}</span>
        <span>· ~{post.readMin || 1} min</span>
      </div>

      <PostRenderer blocks={body} theme={forumTheme} />

      <div class="rounded-[14px] px-4 sm:px-5 py-4" style="border: 1px solid hsl(26 30% 85%); margin-top: -1px;">
        <div class="flex justify-between items-center flex-wrap gap-3 pt-2"
          style="border-top: 1px dashed hsl(26 25% 80%);"
        >
          <div class="text-[12.5px] inline-flex items-center gap-3 flex-wrap" style="color: hsl(215 16% 47%);">
            <span class="inline-flex items-center gap-1 tabular-nums">
              <Icon name="fire" size={13} /> {post.burned.toLocaleString()} $nanas
            </span>
            {#if userBurned > 0}
              <span class="inline-flex items-center gap-1 text-[11.5px] font-semibold"
                style="color: hsl(38 85% 30%);"
              >
                You tipped {userBurned.toLocaleString()}
              </span>
            {/if}
          </div>
          <Button on:click={onTip} size="sm"
            class="!bg-[hsl(45_95%_62%)] !text-[hsl(24_48%_12%)] !border !border-[hsl(32_72%_50%)]"
          >
            <Icon name="fire" size={13} /> Tip in $nanas
          </Button>
        </div>
      </div>

      <!-- Comments -->
      <div class="mt-8">
        <div class="flex items-center gap-2 mb-3">
          <Icon name="chat-circle" size={16} style="color: hsl(24 48% 28%);" />
          <h2 class="font-bold text-[15.5px]" style="color: hsl(222 47% 11%);">
            Comments ({comments.length})
          </h2>
        </div>

        {#if $isAuthenticated}
          <form on:submit={submitComment} class="mb-4">
            <MentionAutocomplete
              bind:value={commentDraft}
              placeholder="Add to the conversation… type @ to mention someone"
              rows={3}
              maxlength={600}
              className="w-full rounded-[12px] bg-white px-3 py-2.5 text-[14px] outline-none resize-none"
              style="border: 1px solid hsl(26 30% 85%); color: hsl(222 47% 11%); line-height: 1.55; display: block;"
            />
            {#if commentErr}
              <div class="rounded-[10px] px-3 py-2 text-[12.5px] mt-2"
                style="background: hsl(0 70% 96%); color: hsl(0 70% 30%); border: 1px solid hsl(0 70% 85%);"
              >
                {commentErr}
              </div>
            {/if}
            <div class="flex justify-between items-center mt-2 flex-wrap gap-2">
              <span class="text-[11px]" style="color: hsl(215 16% 47%);">
                Posting as <b>{$profile.name || ($principalText ? `${$principalText.slice(0, 5)}…${$principalText.slice(-3)}` : 'Guest')}</b>
              </span>
              <Button type="submit" size="sm" disabled={posting}>
                {#if posting}
                  <Icon name="spinner-gap" size={13} /> Posting…
                {:else}
                  <Icon name="paper-plane-tilt" size={13} /> Post comment
                {/if}
              </Button>
            </div>
          </form>
        {:else}
          <div class="rounded-[12px] px-4 py-3.5 mb-4 text-center text-[13px] flex flex-col sm:flex-row items-center justify-center gap-2"
            style="background: hsl(45 80% 94%); border: 1px solid hsl(45 75% 75%); color: hsl(32 56% 25%);"
          >
            <span>Sign in with Internet Identity to comment.</span>
            <Button size="sm" on:click={login}>
              <Icon name="fingerprint" size={13} /> Sign in
            </Button>
          </div>
        {/if}

        {#if loadingComments}
          <div class="text-[13px] py-3 text-center" style="color: hsl(215 16% 47%);">
            <Icon name="spinner-gap" size={13} /> Loading comments…
          </div>
        {:else if comments.length === 0}
          <div class="text-[13px] py-6 text-center" style="color: hsl(215 16% 47%);">
            No comments yet. Be the first.
          </div>
        {:else}
          <CommentThread {comments} />
        {/if}
      </div>
    </article>
  {/if}
</div>
