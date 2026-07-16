<script>
  import { onMount } from 'svelte';
  import Icon from '$lib/components/Icon.svelte';
  import { notifications, unreadCount, markAllRead, markRead, notifMeta } from '$lib/stores/notifications.js';

  let open = $state(false);
  let panelEl = $state(null);

  // Close on outside click
  function onDocClick(e) {
    if (open && panelEl && !panelEl.contains(e.target)) {
      open = false;
    }
  }

  onMount(() => {
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  });

  function toggle() {
    open = !open;
  }

  function handleNotifClick(n) {
    markRead(n.id);
    open = false;
    if (n.url && n.url !== '#') {
      window.location.href = n.url;
    }
  }

  function fmtTime(ts) {
    const diff = Date.now() - ts;
    if (diff < 60_000)   return 'just now';
    if (diff < 3600_000) return `${Math.floor(diff / 60_000)}m ago`;
    if (diff < 86400_000) return `${Math.floor(diff / 3600_000)}h ago`;
    return `${Math.floor(diff / 86400_000)}d ago`;
  }
</script>

<div class="bell-wrap" bind:this={panelEl} style="position: relative; display: inline-flex;">

  <!-- Trigger button -->
  <button
    type="button"
    class="bell-btn"
    onclick={toggle}
    aria-label="Notifications"
    style="
      position: relative; background: none; border: none;
      cursor: pointer; padding: 6px; border-radius: 8px;
      color: hsl(var(--pg-fg-muted));
      display: inline-flex; align-items: center; justify-content: center;
    "
  >
    <Icon name="bell" size={20} />
    {#if $unreadCount > 0}
      <span style="
        position: absolute; top: 2px; right: 2px;
        min-width: 16px; height: 16px; padding: 0 3px;
        background: hsl(0 62% 48%); color: white;
        border-radius: 999px; font-size: 10px; font-weight: 700;
        display: flex; align-items: center; justify-content: center;
        line-height: 1; pointer-events: none;
        box-shadow: 0 0 0 2px white;
      ">{$unreadCount}</span>
    {/if}
  </button>

  <!-- Dropdown panel -->
  {#if open}
    <div
      class="notif-panel"
      style="
        position: absolute; top: calc(100% + 8px); right: 0;
        width: 340px; max-height: 480px;
        background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border));
        border-radius: 14px; box-shadow: 0 8px 32px -4px hsl(222 30% 20% / 0.18);
        z-index: 1000; overflow: hidden;
        display: flex; flex-direction: column;
      "
    >
      <!-- Header -->
      <div style="
        display: flex; align-items: center; justify-content: space-between;
        padding: 13px 16px 10px;
        border-bottom: 1px solid hsl(var(--pg-border));
        flex-shrink: 0;
      ">
        <span style="font-size: 14px; font-weight: 700; color: hsl(var(--pg-fg));">Notifications</span>
        {#if $unreadCount > 0}
          <button
            type="button"
            onclick={markAllRead}
            style="
              background: none; border: none; cursor: pointer;
              font-size: 11.5px; font-family: inherit;
              color: hsl(210 80% 48%); font-weight: 600;
              padding: 3px 6px; border-radius: 6px;
            "
          >Mark all read</button>
        {/if}
      </div>

      <!-- List -->
      <div style="overflow-y: auto; flex: 1;">
        {#if $notifications.length === 0}
          <div style="
            padding: 36px 20px; text-align: center;
            color: hsl(var(--pg-fg-subtle)); font-size: 13px;
          ">
            <Icon name="bell-slash" size={28} style="opacity: 0.35; display: block; margin: 0 auto 10px;" />
            No notifications yet
          </div>
        {:else}
          {#each $notifications as n (n.id)}
            {@const meta = notifMeta(n.type)}
            <button
              type="button"
              onclick={() => handleNotifClick(n)}
              style="
                width: 100%; display: flex; gap: 11px; align-items: flex-start;
                padding: 12px 16px; border: none; cursor: pointer;
                background: {n.read ? 'hsl(var(--pg-surface))' : 'hsl(43 70% 55% / 0.12)'};
                border-bottom: 1px solid hsl(var(--pg-border));
                text-align: left; font-family: inherit;
                transition: background 0.1s;
              "
            >
              <!-- Icon pill -->
              <span style="
                width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0;
                background: {meta.color}22;
                display: flex; align-items: center; justify-content: center;
                margin-top: 2px;
              ">
                <Icon name={meta.icon} size={15} style="color: {meta.color};" />
              </span>
              <!-- Content -->
              <div style="flex: 1; min-width: 0;">
                <div style="
                  font-size: 13px; font-weight: {n.read ? 500 : 700};
                  color: hsl(var(--pg-fg)); line-height: 1.35; margin-bottom: 2px;
                ">{n.title}</div>
                {#if n.body}
                  <div style="
                    font-size: 11.5px; color: hsl(var(--pg-fg-muted));
                    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
                  ">{n.body}</div>
                {/if}
                <div style="font-size: 10.5px; color: hsl(var(--pg-fg-subtle)); margin-top: 4px;">
                  {fmtTime(n.createdAt)}
                </div>
              </div>
              <!-- Unread dot -->
              {#if !n.read}
                <span style="
                  width: 8px; height: 8px; border-radius: 50%;
                  background: hsl(0 62% 48%); flex-shrink: 0; margin-top: 6px;
                "></span>
              {/if}
            </button>
          {/each}
        {/if}
      </div>

      <!-- Footer: link to all notifications / activity -->
      <div style="
        border-top: 1px solid hsl(var(--pg-border)); padding: 10px 16px;
        flex-shrink: 0;
      ">
        <a
          href="/profile#audit"
          onclick={() => (open = false)}
          style="
            font-size: 12px; color: hsl(210 80% 48%); font-weight: 600;
            text-decoration: none; display: block; text-align: center;
          "
        >View on-chain activity →</a>
      </div>
    </div>
  {/if}
</div>
