<script>
  export let name;
  export let hue = 24;
  export let size = 32;
  $: initials = name
    .replace(/^[@.]/, '')
    .split(/[_.\-]/)
    .map((s) => s[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
</script>

<span
  class="inline-flex items-center justify-center rounded-full text-white font-bold flex-shrink-0"
  style="
    width: {size}px; height: {size}px;
    background: linear-gradient(135deg, hsl({hue} 60% 62%), hsl({(hue + 40) % 360} 55% 48%));
    font-size: {Math.round(size * 0.38)}px;
    border: 2px solid hsl(var(--pg-surface));
    box-shadow: 0 2px 6px hsl(24 30% 20% / 0.15);
  "
>{initials}</span>
