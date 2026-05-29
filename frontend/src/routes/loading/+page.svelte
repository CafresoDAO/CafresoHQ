<script>
  import Icon from '$lib/components/Icon.svelte';
</script>

<svelte:head><title>Cafreso · Loading</title></svelte:head>

<div
  class="fixed inset-0 flex flex-col items-center justify-center"
  style="background: #c9a683;"
>
  <svg viewBox="0 0 1200 800" xmlns="http://www.w3.org/2000/svg" style="width: min(80vw, 600px); height: auto;">
    <rect width="1200" height="800" fill="#c9a683" />
    <g transform="translate(600 400)" fill="#0a0f1c" font-family="Georgia, serif" font-style="italic" font-weight="700" text-anchor="middle">
      <text font-size="220" y="40">Cf</text>
    </g>
    <circle cx="600" cy="620" r="8" fill="#2eb872">
      <animate attributeName="opacity" values="0.3;1;0.3" dur="1.6s" repeatCount="indefinite" />
    </circle>
  </svg>
  <div class="mt-4 text-[13px] flex items-center gap-2" style="color: #5a4433;">
    <Icon name="circle-notch" size={16} class="spin" />
    <span>Brewing…</span>
  </div>
</div>
