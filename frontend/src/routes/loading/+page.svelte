<script>
  import Icon from '$lib/components/Icon.svelte';
</script>

<svelte:head><title>Cafreso · Loading</title></svelte:head>

<div class="fixed inset-0 flex flex-col items-center justify-center loading-splash">
  <svg viewBox="0 0 1200 800" xmlns="http://www.w3.org/2000/svg" style="width: min(80vw, 600px); height: auto;">
    <rect width="1200" height="800" class="loading-splash-bg" />
    <g transform="translate(600 400)" class="loading-splash-mark" font-family="Georgia, serif" font-style="italic" font-weight="700" text-anchor="middle">
      <text font-size="220" y="40">Cf</text>
    </g>
    <circle cx="600" cy="620" r="8" fill="#2eb872">
      <animate attributeName="opacity" values="0.3;1;0.3" dur="1.6s" repeatCount="indefinite" />
    </circle>
  </svg>
  <div class="mt-4 text-[13px] flex items-center gap-2 loading-splash-caption">
    <Icon name="circle-notch" size={16} class="spin" />
    <span>Brewing…</span>
  </div>
</div>

<style>
  /* Light values are the original literals, kept pixel-identical. The .dark
     class lands on <html> synchronously in app.html's inline script (before
     hydration), so this splash never flashes the wrong theme even though
     it's the very first thing painted — it just had no dark variant at all
     until now. Dark values reuse the ink scale for a coffee/paper splash. */
  .loading-splash, .loading-splash-bg { background: #c9a683; fill: #c9a683; }
  .loading-splash-mark { fill: #0a0f1c; }
  .loading-splash-caption { color: #5a4433; }

  /* --ink-900/--ink-50 swap meaning in .dark (same variables the rest of the
     app uses for body bg / primary text), so this naturally becomes a dark
     coffee background with a pale "Cf" mark instead of re-deriving colors. */
  :global(.dark) .loading-splash, :global(.dark) .loading-splash-bg {
    background: hsl(var(--ink-900)); fill: hsl(var(--ink-900));
  }
  :global(.dark) .loading-splash-mark { fill: hsl(var(--ink-50)); }
  :global(.dark) .loading-splash-caption { color: hsl(var(--ink-400)); }
</style>
