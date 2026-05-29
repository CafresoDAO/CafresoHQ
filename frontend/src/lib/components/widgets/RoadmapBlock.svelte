<script>
  // Renders a ::roadmap widget — a vertical timeline of phases.
  // Status values: 'done' | 'now' | 'next'
  export let phases = []; // [{ num, status, date, title }]
  export let accent = 'hsl(43 74% 54%)';
  export let dark = 'hsl(222 47% 11%)';
  export let bodyBg = 'white';
  export let bodyBorder = 'hsl(26 30% 85%)';

  const STATUS_LABEL = { done: 'Shipped', now: 'Now', next: 'Upcoming' };

  function dotColor(status) {
    if (status === 'done') return accent;
    if (status === 'now') return 'white';
    return 'hsl(215 16% 80%)';
  }
  function dotBorder(status) {
    if (status === 'next') return 'hsl(215 16% 68%)';
    return dark;
  }
  function dotGlow(status) {
    return status === 'now' ? `0 0 0 4px ${accent}44` : 'none';
  }
  function cardBg(status) {
    return status === 'now' ? dark : bodyBg;
  }
  function cardText(status) {
    return status === 'now' ? 'hsl(42 40% 96%)' : 'hsl(222 47% 11%)';
  }
  function cardSub(status) {
    return status === 'now' ? 'hsl(42 20% 72%)' : 'hsl(215 16% 47%)';
  }
</script>

<div class="roadmap-block" style="position: relative; padding-left: 28px; margin: 24px 0;">
  <!-- Vertical spine -->
  <span
    style="
      position: absolute; left: 13px; top: 10px; bottom: 10px; width: 2px;
      background: linear-gradient(180deg, {accent}, {dark} 80%);
      border-radius: 2px;
    "
  ></span>

  {#each phases as ph, i}
    <!-- Timeline dot -->
    <span
      style="
        position: absolute;
        left: 5px;
        top: {22 + i * 78}px;
        width: 18px; height: 18px;
        border-radius: 50%;
        background: {dotColor(ph.status)};
        border: 2.5px solid {dotBorder(ph.status)};
        box-shadow: {dotGlow(ph.status)};
      "
    ></span>

    <div
      style="
        background: {cardBg(ph.status)};
        color: {cardText(ph.status)};
        border: 1px solid {ph.status === 'now' ? dark : bodyBorder};
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: {i === phases.length - 1 ? 0 : 14}px;
      "
    >
      <div style="display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
        <div style="display: flex; align-items: baseline; gap: 10px;">
          <span style="font-size: 10.5px; font-family: ui-monospace, monospace; text-transform: uppercase; letter-spacing: 0.1em; color: {ph.status === 'now' ? accent : 'hsl(215 16% 47%)'};">
            PHASE {ph.num}
          </span>
          <span style="font-size: 17px; font-weight: 700; letter-spacing: -0.01em;">{ph.title}</span>
        </div>
        <span style="font-size: 11.5px; color: {cardSub(ph.status)}; white-space: nowrap;">{ph.date}</span>
      </div>
      <div
        style="
          display: inline-flex; align-items: center; gap: 4px;
          margin-top: 7px;
          font-size: 10.5px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em;
          color: {ph.status === 'now' ? accent : ph.status === 'done' ? 'hsl(142 55% 40%)' : 'hsl(215 16% 55%)'};
        "
      >
        {#if ph.status === 'done'}✓ {/if}{STATUS_LABEL[ph.status] ?? ph.status}
      </div>
    </div>
  {/each}
</div>
