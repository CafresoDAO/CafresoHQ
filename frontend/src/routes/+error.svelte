<script>
  import { page } from '$app/stores';
</script>

<svelte:head>
  <title>{$page.status} · Cafreso</title>
</svelte:head>

<div class="error-page">
  <img
    src="/assets/cafreso-wordmark.png"
    alt="Cafreso"
    class="error-logo"
  />

  <div class="error-status">{$page.status}</div>
  <h1 class="error-title">
    {#if $page.status === 404}
      This page wandered off the farm
    {:else}
      Something went wrong
    {/if}
  </h1>
  <p class="error-message">
    {$page.error?.message ?? 'An unexpected error occurred.'}
  </p>

  <div class="error-links">
    <a href="/" class="error-btn primary">Back home</a>
    <a href="/shop" class="error-btn outline">Shop</a>
    <a href="/blog" class="error-btn outline">Blog</a>
  </div>
</div>

<style>
  .error-page {
    --ink: hsl(222 47% 11%);
    --ink-soft: hsl(222 47% 11% / 0.6);
    --border: hsl(0 0% 88%);
    background: hsl(0 0% 99%);
    min-height: 70vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 56px 24px;
  }
  .error-logo {
    width: min(280px, 70vw);
    height: auto;
    margin-bottom: 32px;
  }
  .error-status {
    font-size: clamp(48px, 12vw, 72px);
    font-weight: 800;
    color: hsl(260 70% 50%);
    line-height: 1;
    letter-spacing: -0.03em;
    margin-bottom: 12px;
  }
  .error-title {
    font-size: clamp(18px, 4vw, 23px);
    font-weight: 700;
    color: var(--ink);
    margin: 0 0 10px;
    letter-spacing: -0.015em;
  }
  .error-message {
    font-size: 14.5px;
    line-height: 1.7;
    color: var(--ink-soft);
    margin: 0 auto 28px;
    max-width: 460px;
  }
  .error-links {
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: 10px;
  }
  .error-btn {
    display: inline-flex;
    align-items: center;
    font-size: 13.5px;
    font-weight: 600;
    padding: 10px 22px;
    border-radius: 10px;
    text-decoration: none;
    transition: all 0.2s;
  }
  .error-btn.primary {
    background: hsl(260 70% 50%);
    color: #fff;
    border: 1.5px solid hsl(260 70% 50%);
  }
  .error-btn.primary:hover {
    background: hsl(260 70% 44%);
    border-color: hsl(260 70% 44%);
  }
  .error-btn.outline {
    background: transparent;
    color: var(--ink);
    border: 1.5px solid var(--border);
  }
  .error-btn.outline:hover {
    border-color: hsl(0 0% 72%);
    background: hsl(0 0% 96%);
  }
</style>
