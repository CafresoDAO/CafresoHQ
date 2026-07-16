<script>
  // Renders a ::progress widget — a labelled progress bar with fraction display.
  export let value = 0;
  export let max = 100;
  export let label = '';
  export let sub = '';
  export let accent = 'hsl(43 74% 54%)';
  export let bg = 'hsl(var(--pg-hover))';
  export let border = 'hsl(var(--pg-border))';
  export let textColor = 'hsl(var(--pg-fg))';
  export let subColor = 'hsl(var(--pg-fg-muted))';

  $: pct = Math.min(100, Math.max(0, (value / max) * 100));
  $: trackColor = bg === 'white' ? 'hsl(215 16% 92%)' : 'hsl(0 0% 100% / 0.3)';
</script>

<div
  class="progress-widget"
  style="
    background: {bg};
    border: 1px solid {border};
    border-radius: 14px;
    padding: 20px 24px;
    margin: 24px 0;
  "
>
  <div style="display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 12px;">
    <div style="font-size: 15px; font-weight: 700; color: {textColor}; letter-spacing: -0.01em;">
      {label}
    </div>
    <div style="font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums; color: {textColor}; white-space: nowrap;">
      {value.toLocaleString()} / {max.toLocaleString()}
    </div>
  </div>

  <!-- Track -->
  <div style="height: 10px; background: {trackColor}; border-radius: 999px; overflow: hidden;">
    <div
      style="
        height: 100%;
        width: {pct}%;
        background: {accent};
        border-radius: 999px;
        transition: width 0.6s cubic-bezier(.2,.8,.2,1);
      "
    ></div>
  </div>

  {#if sub}
    <div style="font-size: 11.5px; color: {subColor}; margin-top: 8px;">{sub}</div>
  {/if}
</div>
