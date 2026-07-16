<script>
  // Pure SVG area/line/bar chart for embedding in blog posts.
  // Intentionally dependency-free — no D3, works with adapter-static + ICP.
  export let points = [];      // [{ label: string, value: number }]
  export let chartType = 'area'; // 'area' | 'line' | 'bar'
  export let title = '';
  export let color = 'hsl(43 74% 54%)';
  export let bodyBg = 'hsl(var(--pg-elevated))';
  export let bodyBorder = 'hsl(var(--pg-border))';
  export let textColor = 'hsl(var(--pg-fg))';

  const W = 520;
  const H = 168;
  const padL = 8;
  const padR = 8;
  const padT = 16;
  const padB = 36;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;

  $: minV = points.length ? Math.min(...points.map((p) => p.value)) : 0;
  $: maxV = points.length ? Math.max(...points.map((p) => p.value)) : 1;
  $: range = maxV - minV || 1;

  $: xStep = chartW / Math.max(1, points.length - 1);
  $: xPos  = (i) => padL + i * xStep;
  $: yPos  = (v) => padT + chartH - ((v - minV) / range) * chartH;

  $: linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${xPos(i).toFixed(1)},${yPos(p.value).toFixed(1)}`).join(' ');
  $: areaPath = points.length
    ? `${linePath} L${xPos(points.length - 1).toFixed(1)},${padT + chartH} L${xPos(0).toFixed(1)},${padT + chartH}Z`
    : '';

  $: barW = points.length ? chartW / points.length * 0.55 : 20;
  $: barX  = (i) => padL + (i / points.length) * chartW + (chartW / points.length) * 0.225;
  $: barH  = (v) => ((v - minV) / range) * chartH;
  $: barY  = (v) => padT + chartH - barH(v);

  const gradId = `chart-grad-${Math.random().toString(36).slice(2, 7)}`;
</script>

<div
  class="chart-block"
  style="
    background: {bodyBg};
    border: 1px solid {bodyBorder};
    border-radius: 14px;
    padding: 20px 22px 16px;
    margin: 24px 0;
  "
>
  {#if title}
    <div
      class="chart-title"
      style="font-size: 13px; font-weight: 600; color: {textColor}; margin-bottom: 14px; letter-spacing: -0.01em;"
    >{title}</div>
  {/if}

  {#if points.length < 2}
    <div style="font-size: 13px; color: hsl(var(--pg-fg-muted)); padding: 24px 0; text-align: center;">
      Add at least 2 data points to render the chart.
    </div>
  {:else}
    <svg viewBox="0 0 {W} {H}" style="width: 100%; height: auto; display: block; overflow: visible;">
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color={color} stop-opacity="0.28" />
          <stop offset="100%" stop-color={color} stop-opacity="0.02" />
        </linearGradient>
      </defs>

      {#if chartType === 'bar'}
        {#each points as p, i}
          <rect
            x={barX(i)}
            y={barY(p.value)}
            width={barW}
            height={barH(p.value)}
            rx="3"
            fill={color}
            fill-opacity="0.85"
          />
        {/each}
      {:else}
        {#if chartType === 'area'}
          <path d={areaPath} fill="url(#{gradId})" />
        {/if}
        <path
          d={linePath}
          fill="none"
          stroke={color}
          stroke-width="2.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        {#each points as p, i}
          <circle cx={xPos(i)} cy={yPos(p.value)} r="4.5" fill={color} stroke={bodyBg} stroke-width="2" />
        {/each}
      {/if}

      <!-- Baseline -->
      <line
        x1={padL} y1={padT + chartH}
        x2={W - padR} y2={padT + chartH}
        stroke="hsl(var(--pg-border))"
        stroke-width="1"
      />

      <!-- X-axis labels -->
      {#each points as p, i}
        <text
          x={chartType === 'bar' ? barX(i) + barW / 2 : xPos(i)}
          y={H - 6}
          text-anchor="middle"
          style="font-size: 10px; fill: hsl(var(--pg-fg-muted)); font-family: inherit;"
        >{p.label}</text>
      {/each}
    </svg>
  {/if}
</div>
