<script>
  // Generalized yield calculator widget — extracted from BankingBravePost,
  // now themeable and embeddable in any post via ::calculator block.
  let {
    apy = 7.25,
    max = 50000,
    min = 250,
    step = 250,
    currency = 'CF',
    // Theme colors
    bg = 'hsl(220 78% 14%)',
    border = 'hsl(43 74% 54%)',
    accent = 'hsl(43 74% 54%)',
    text = 'hsl(42 40% 96%)',
    sub = 'hsl(42 25% 72%)',
    cardBg = 'hsl(220 50% 18%)',
    cardBorder = 'hsl(220 45% 30%)',
  } = $props();

  let deposit = $state(Math.round((min + max) / 2 / step) * step);
  let term = $state(12);

  const TERMS = [3, 6, 12, 24, 36];
  const apyFrac = $derived(apy / 100);
  const projected = $derived(Math.round(deposit * Math.pow(1 + apyFrac, term / 12) - deposit));
  const monthly   = $derived(Math.round((deposit * apyFrac) / 12));
  const maturity  = $derived(deposit + projected);

  const stats = $derived([
    { label: 'Projected yield', value: `+${projected.toLocaleString()} $${currency}`, sub: `over ${term}m at compounded APY` },
    { label: 'Monthly interest', value: `${monthly.toLocaleString()} $${currency}`, sub: 'paid every 30 days' },
    { label: 'Principal at maturity', value: `${maturity.toLocaleString()} $${currency}`, sub: 'non-custodial, withdraw anytime' },
  ]);
</script>

<div
  class="yield-calc"
  style="
    background: {bg};
    border: 1px solid {border};
    border-radius: 16px;
    padding: 28px 30px;
    color: {text};
    margin: 24px 0;
  "
>
  <!-- Header row -->
  <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 22px;">
    <div>
      <div style="font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.2em; color: {accent}; font-weight: 700; margin-bottom: 6px;">
        Yield Calculator
      </div>
      <div style="font-size: 20px; font-weight: 700; letter-spacing: -0.01em;">
        Project your ${ currency } yield
      </div>
      <div style="font-size: 13px; margin-top: 5px; color: {sub};">
        APY set by SNS governance · compounded monthly
      </div>
    </div>
    <div style="text-align: right; flex-shrink: 0;">
      <div style="font-size: 44px; font-weight: 800; color: {accent}; letter-spacing: -0.03em; line-height: 1;">
        {apy.toFixed(2)}<span style="font-size: 22px;">%</span>
      </div>
      <div style="font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.1em; color: {sub}; margin-top: 2px;">
        Current APY
      </div>
    </div>
  </div>

  <!-- Controls -->
  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
    <div>
      <label style="display: flex; justify-content: space-between; font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.06em; color: {sub}; margin-bottom: 8px;">
        <span>Deposit amount</span>
        <span style="font-family: ui-monospace, monospace; color: {text};">{deposit.toLocaleString()} ${currency}</span>
      </label>
      <input
        type="range"
        {min}
        {max}
        {step}
        bind:value={deposit}
        style="width: 100%; accent-color: {accent};"
      />
      <div style="display: flex; justify-content: space-between; margin-top: 4px; font-size: 10px; font-family: ui-monospace, monospace; color: {sub};">
        <span>{min.toLocaleString()}</span>
        <span>{Math.round((min + max) / 2).toLocaleString()}</span>
        <span>{max.toLocaleString()}</span>
      </div>
    </div>

    <div>
      <label style="display: flex; justify-content: space-between; font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.06em; color: {sub}; margin-bottom: 8px;">
        <span>Lock-up term</span>
        <span style="font-family: ui-monospace, monospace; color: {text};">{term} months</span>
      </label>
      <div style="display: flex; gap: 6px;">
        {#each TERMS as m}
          <button
            onclick={() => (term = m)}
            style="
              flex: 1; padding: 9px 0; font-family: inherit; font-size: 13px;
              background: {term === m ? accent : 'transparent'};
              color: {term === m ? bg : text};
              border: 1px solid {term === m ? accent : 'hsl(220 40% 44%)'};
              border-radius: 6px; font-weight: {term === m ? 700 : 500};
              cursor: pointer;
            "
          >{m}m</button>
        {/each}
      </div>
    </div>
  </div>

  <!-- Divider -->
  <div style="display: flex; align-items: center; gap: 10px; margin: 20px 0;">
    <span style="flex: 1; height: 1px; background: linear-gradient(90deg, transparent, {accent}66 40%, {accent}66 60%, transparent);"></span>
    <span style="width: 8px; height: 8px; background: {accent}; transform: rotate(45deg);"></span>
    <span style="flex: 1; height: 1px; background: linear-gradient(90deg, transparent, {accent}66 40%, {accent}66 60%, transparent);"></span>
  </div>

  <!-- Output stats -->
  <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;">
    {#each stats as s}
      <div style="background: {cardBg}; border: 1px solid {cardBorder}; border-radius: 10px; padding: 14px 16px;">
        <div style="font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.1em; color: {sub}; margin-bottom: 6px;">{s.label}</div>
        <div style="font-size: 20px; font-weight: 700; color: {accent}; letter-spacing: -0.01em; line-height: 1.1;">{s.value}</div>
        <div style="font-size: 11px; color: {sub}; margin-top: 4px;">{s.sub}</div>
      </div>
    {/each}
  </div>
</div>
