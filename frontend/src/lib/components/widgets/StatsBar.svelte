<script>
  // Renders a ::stats widget block as a horizontal ribbon of key-value pills.
  // Colors are driven by the parent theme's stats config.
  export let items = [];          // [{ label, value }]
  export let bg = 'hsl(222 47% 11%)';
  export let border = 'hsl(215 30% 24%)';
  export let valueColor = 'hsl(45 95% 62%)';
  export let labelColor = 'hsl(215 20% 62%)';
</script>

<div
  class="stats-bar"
  style="
    background: {bg};
    border: 1px solid {border};
    border-radius: 14px;
    padding: 20px 24px;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 16px;
    margin: 24px 0;
  "
>
  {#each items as item}
    <div class="stat-item" style="text-align: center;">
      <div
        class="stat-value"
        style="
          font-size: clamp(20px, 3vw, 28px);
          font-weight: 700;
          color: {valueColor};
          letter-spacing: -0.01em;
          line-height: 1.1;
          font-variant-numeric: tabular-nums;
        "
      >{item.value}</div>
      <div
        class="stat-label"
        style="
          font-size: 10.5px;
          text-transform: uppercase;
          letter-spacing: 0.13em;
          color: {labelColor};
          margin-top: 5px;
        "
      >{item.label}</div>
    </div>
  {/each}
</div>
