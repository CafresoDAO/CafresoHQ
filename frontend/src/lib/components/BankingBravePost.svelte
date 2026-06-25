<script>
  import Icon from './Icon.svelte';
  import Avatar from './Avatar.svelte';
  import Button from './Button.svelte';
  import CommentThread from './CommentThread.svelte';
  import { COMMENTS } from '$lib/data/blog.js';
  import { bbModalOpen, burnTarget } from '$lib/stores/blog.js';
  import { principalText } from '$lib/stores/auth.js';
  import { isDevlogAdmin } from '$lib/data/admins.js';

  export let post;

  $: canEdit = isDevlogAdmin($principalText);

  const BB = {
    navy: 'hsl(220 72% 22%)',
    navyDeep: 'hsl(220 78% 14%)',
    gold: 'hsl(43 74% 54%)',
    goldDeep: 'hsl(40 68% 42%)',
    ivory: 'hsl(42 40% 96%)',
    parchment: 'hsl(42 35% 92%)'
  };

  let deposit = 5000;
  let term = 12;
  const apy = 0.0725;

  $: projected = Math.round(deposit * Math.pow(1 + apy, term / 12) - deposit);
  $: monthly = Math.round((deposit * apy) / 12);

  const pillars = [
    { icon: 'lock-key', title: 'Non-custodial by design', body: 'Your $CF stays under your Internet Identity. The vault canister holds a claim, not custody — you can exit atomically at any block.' },
    { icon: 'shield-check', title: 'Audited & open-source', body: 'Motoko source audited by Trail of Bits (Q1 2026). Every canister upgrade requires an on-chain SNS vote with a 72-hour timelock.' },
    { icon: 'gavel', title: 'Governed on-chain', body: 'APY, lock-up terms, and treasury allocation are set by $CF holders. No admin key, no multi-sig shortcut, no hidden levers.' },
    { icon: 'chart-line', title: 'Transparent accounting', body: 'Every deposit, yield payment, and café revenue receipt is publicly queryable on mainnet. Weekly treasury report auto-posts to this dev log.' }
  ];

  const phases = [
    { p: '00', title: 'Foundation', date: 'Q1 2026 · Shipped', status: 'done', items: ['Motoko vault canister', 'Trail of Bits audit', 'SNS-04 governance params'] },
    { p: '01', title: 'Testnet waitlist', date: 'Apr 18, 2026 · Today', status: 'now', items: ['Early-access applications open', 'Stake 500 $CF to reserve a seat', '1,000-member cap'] },
    { p: '02', title: 'Mainnet deposits', date: 'Q2 2026 · Jun', status: 'next', items: ['Public vault opens', '3/6/12/24/36-month terms', 'First yield distribution'] },
    { p: '03', title: 'Café integration', date: 'Q3 2026', status: 'next', items: ['Pay for coffee from vault balance', 'Physical Banking.Brave card', 'In-store QR deposits'] }
  ];

  function tipTeam() {
    burnTarget.set(post.slug);
  }
</script>

<div style="background: hsl(26 30% 74%);">
  <!-- HERO -->
  <div
    class="relative overflow-hidden"
    style="
      background: linear-gradient(180deg, {BB.navyDeep} 0%, {BB.navy} 100%);
      color: {BB.ivory}; border-bottom: 2px solid {BB.gold};
    "
  >
    <div
      class="absolute pointer-events-none"
      style="inset: 14px; border: 1px solid {BB.gold}; opacity: 0.4; border-radius: 2px;"
    ></div>

    <div
      class="mx-auto flex items-center justify-between gap-3 flex-wrap"
      style="max-width: 1280px; padding: 22px 30px 0;"
    >
      <a
        href="/blog"
        class="inline-flex items-center gap-1.5 text-[13px] cursor-pointer no-underline"
        style="color: hsl(42 25% 78%); font-family: inherit;"
      >
        <Icon name="caret-left" size={14} /> Back to Dev Log
      </a>
      {#if canEdit}
        <a
          href="/blog/new?edit={post.slug}"
          class="inline-flex items-center gap-1.5 text-[12px] font-semibold rounded-full px-3 py-1.5 no-underline"
          style="background: hsl(42 25% 22%); border: 1px solid {BB.gold}; color: {BB.ivory};"
        >
          <Icon name="pencil-simple" size={12} /> Edit post
        </a>
      {/if}
    </div>

    <div
      class="mx-auto bb-hero-grid"
      style="
        max-width: 1280px; padding: 40px 30px 54px;
        display: grid; grid-template-columns: 1.4fr 1fr; gap: 40px; align-items: center;
      "
    >
      <div>
        <div
          class="inline-flex items-center gap-2.5 uppercase font-bold mb-4"
          style="font-size: 11px; letter-spacing: 0.22em; color: {BB.gold};"
        >
          <span style="width: 28px; height: 1px; background: {BB.gold};"></span>
          Special Announcement · April 18, 2026
        </div>
        <h1
          class="font-serif-display bb-hero-title"
          style="font-size: 64px; font-weight: 700; line-height: 1.02; letter-spacing: -0.02em; margin: 0 0 18px; text-wrap: balance;"
        >
          Introducing <em style="color: {BB.gold}; font-style: italic;">Banking.Brave</em>
        </h1>
        <p
          class="m-0 mb-6"
          style="font-size: 19px; line-height: 1.5; color: hsl(42 25% 85%); max-width: 54ch; text-wrap: pretty;"
        >
          A sovereign, non-custodial banking protocol on the Internet Computer — powered by the Cafreso DAO treasury. Deposit. Earn. Govern. All on-chain.
        </p>

        <div class="flex items-center gap-3.5 flex-wrap">
          <div class="inline-flex items-center gap-2.5">
            <Avatar name={post.author.name} hue={post.author.hue} size={36} />
            <div class="text-[13px]">
              <div class="font-semibold">{post.author.name}</div>
              <div style="color: hsl(42 20% 65%); font-size: 11.5px;">{post.author.role}</div>
            </div>
          </div>
          <span class="w-px" style="height: 28px; background: hsl(220 30% 38%);"></span>
          <span
            class="inline-flex items-center gap-1.5 font-medium"
            style="
              background: hsl(220 55% 18%); border: 1px solid {BB.gold};
              padding: 4px 10px; border-radius: 999px; font-size: 11px;
              font-family: ui-monospace, monospace; color: hsl(42 25% 85%);
            "
          >
            <img src="/assets/icp.png" alt="" style="width: 13px; filter: brightness(1.3);" />
            <span>{post.canister}</span>
            <span style="color: hsl(42 20% 55%);">·</span>
            <span>#{post.block.toLocaleString()}</span>
          </span>
          <span
            class="inline-flex items-center gap-1 text-white font-semibold"
            style="background: hsl(112 43% 45%); padding: 4px 10px; border-radius: 999px; font-size: 11px;"
          >
            <Icon name="seal-check" size={13} /> Signed by Core team
          </span>
        </div>
      </div>

      <!-- Lion seal -->
      <div class="flex justify-center relative">
        <div
          class="bb-hero-seal relative flex items-center justify-center"
          style="width: 280px; height: 280px;"
        >
          <div
            class="absolute rounded-full"
            style="inset: -20px; border: 1px solid {BB.gold}; opacity: 0.35;"
          ></div>
          <div
            class="absolute rounded-full"
            style="inset: -40px; border: 1px dashed {BB.gold}; opacity: 0.25;"
          ></div>
          <div
            class="rounded-full flex items-center justify-center overflow-hidden"
            style="
              width: 100%; height: 100%;
              background: {BB.ivory};
              border: 3px solid {BB.gold};
              box-shadow: 0 24px 44px -16px {BB.navyDeep}, 0 0 0 1px hsl(0 0% 100% / 0.2) inset;
            "
          >
            <img src="/assets/banking-brave-logo.png" alt="" style="width: 100%; height: 100%; object-fit: contain;" />
          </div>
          <div
            class="absolute inline-flex items-center gap-2 uppercase font-semibold"
            style="
              bottom: -12px; left: 50%; transform: translateX(-50%);
              background: {BB.ivory}; padding: 5px 12px; border-radius: 999px;
              font-size: 10.5px; color: {BB.navyDeep};
              letter-spacing: 0.1em;
              border: 1px solid {BB.gold};
              box-shadow: 0 8px 20px -6px {BB.navyDeep};
              white-space: nowrap;
            "
          >
            <img src="/assets/cf-black.png" alt="" style="width: 16px;" /> Powered by Cafreso DAO
          </div>
        </div>
      </div>
    </div>

    <!-- Headline stat ribbon -->
    <div
      style="
        background: {BB.navyDeep};
        border-top: 1px solid {BB.gold};
        border-bottom: 1px solid {BB.gold};
      "
    >
      <div
        class="mx-auto bb-ribbon"
        style="
          max-width: 1280px; padding: 18px 30px;
          display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px;
        "
      >
        {#each [['7.25%', 'Opening APY'], ['$2.4M', 'Treasury backing'], ['Non-custodial', 'Your keys, your claim'], ['Audited', "Trail of Bits · Q1 '26"]] as [v, l]}
          <div class="text-center" style="color: {BB.ivory};">
            <div
              class="font-serif-display"
              style="font-size: 26px; font-weight: 600; color: {BB.gold}; letter-spacing: -0.01em; line-height: 1.1;"
            >{v}</div>
            <div
              class="uppercase mt-1"
              style="font-size: 10.5px; letter-spacing: 0.14em; color: hsl(42 20% 70%);"
            >{l}</div>
          </div>
        {/each}
      </div>
    </div>
  </div>

  <!-- BODY -->
  <div class="mx-auto" style="max-width: 860px; padding: 48px 24px 80px;">
    <div
      class="bb-article-body relative"
      style="
        background: {BB.ivory}; border: 1px solid {BB.parchment};
        border-radius: 14px; padding: 40px 48px;
        box-shadow: 0 1px 0 hsl(0 0% 100%) inset, 0 20px 40px -24px hsl(220 40% 15% / 0.2);
      "
    >
      <!-- Drop cap -->
      <div style="font-size: 0;">
        <span
          class="float-left font-serif-display"
          style="
            font-size: 86px; font-weight: 700; line-height: 0.85;
            margin: 8px 12px 0 0; color: {BB.navy}; letter-spacing: -0.03em;
          "
        >F</span>
        <p style="font-size: 17px; line-height: 1.7; margin: 0 0 18px; color: hsl(222 30% 20%); text-wrap: pretty;">
          or three years we've been building the Cafreso DAO as an answer to a question: can a coffee farm, a café, and a community genuinely operate on-chain — not as a gimmick, but as infrastructure? Today we take the biggest step yet. We're debuting <strong>Banking.Brave</strong>, a sovereign banking protocol that turns our treasury into a yield-bearing home for $CF.
        </p>
      </div>
      <p style="font-size: 17px; line-height: 1.7; margin: 0 0 18px; color: hsl(222 30% 20%);">
        The name isn't accidental. Banking, because we mean it literally — deposits, yield, withdrawals, statements. Brave, because we're doing it without the shortcuts that have repeatedly failed the DeFi ecosystem: no custodial intermediaries, no opaque off-chain bookkeeping, no admin keys hidden behind a multi-sig.
      </p>
      <p style="font-size: 17px; line-height: 1.7; margin: 0 0 24px; color: hsl(222 30% 20%);">
        Everything that follows — the APY, the lock-up terms, the treasury allocation — is set by $CF holders voting on-chain. Our job as a core team is to ship the canisters. Your job as a DAO is to run the bank.
      </p>

      <!-- Gold divider -->
      <div class="flex items-center gap-3" style="margin: 34px 0;">
        <span class="flex-1" style="height: 1px; background: linear-gradient(90deg, transparent, {BB.gold} 30%, {BB.gold} 70%, transparent);"></span>
        <span style="width: 8px; height: 8px; background: {BB.gold}; transform: rotate(45deg); box-shadow: 0 0 0 3px {BB.navy};"></span>
        <span class="flex-1" style="height: 1px; background: linear-gradient(90deg, transparent, {BB.gold} 30%, {BB.gold} 70%, transparent);"></span>
      </div>

      <!-- Yield vault -->
      <div
        class="relative overflow-hidden"
        style="
          background: {BB.navyDeep}; border-radius: 16px; padding: 32px;
          color: {BB.ivory}; border: 1px solid {BB.gold};
          box-shadow: 0 30px 60px -20px {BB.navyDeep}, 0 0 0 1px hsl(0 0% 100% / 0.05) inset;
        "
      >
        <div
          class="grid items-start"
          style="grid-template-columns: 1fr auto; gap: 24px;"
        >
          <div>
            <div
              class="inline-flex items-center gap-2 uppercase font-bold mb-2.5"
              style="font-size: 10.5px; letter-spacing: 0.22em; color: {BB.gold};"
            >
              <span style="width: 22px; height: 1px; background: {BB.gold};"></span>
              Treasury Vault · Live
            </div>
            <h3
              class="font-serif-display m-0"
              style="font-size: 26px; font-weight: 600; letter-spacing: -0.01em; line-height: 1.15;"
            >Project your DAO-backed yield</h3>
            <p style="font-size: 13.5px; margin: 8px 0 0; color: hsl(42 30% 85%); max-width: 46ch; line-height: 1.55;">
              Deposit $CF into the Banking.Brave vault. APY is set quarterly by SNS governance, paid from farm & café revenue.
            </p>
          </div>
          <div class="text-right flex-shrink-0">
            <div
              class="font-serif-display"
              style="font-size: 48px; font-weight: 700; line-height: 1; color: {BB.gold}; letter-spacing: -0.02em; white-space: nowrap;"
            >
              {(apy * 100).toFixed(2)}<span style="font-size: 24px; margin-left: 2px;">%</span>
            </div>
            <div
              class="uppercase mt-1"
              style="font-size: 10.5px; letter-spacing: 0.12em; color: hsl(42 25% 70%); white-space: nowrap;"
            >APY · SNS-04</div>
          </div>
        </div>

        <div
          class="mt-7 bb-yield-grid"
          style="display: grid; grid-template-columns: 1fr 1fr; gap: 22px;"
        >
          <div>
            <label
              class="flex justify-between uppercase mb-2"
              style="font-size: 12px; color: hsl(42 25% 72%); letter-spacing: 0.06em;"
            >
              <span>Deposit amount</span>
              <span class="font-mono" style="color: {BB.ivory};">{deposit.toLocaleString()} $CF</span>
            </label>
            <input
              type="range"
              min={250}
              max={50000}
              step={250}
              bind:value={deposit}
              style="width: 100%; accent-color: {BB.gold};"
            />
            <div class="flex justify-between mt-1 font-mono text-[10px]" style="color: hsl(42 20% 55%);">
              <span>250</span><span>25,000</span><span>50,000</span>
            </div>
          </div>

          <div>
            <label
              class="flex justify-between uppercase mb-2"
              style="font-size: 12px; color: hsl(42 25% 72%); letter-spacing: 0.06em;"
            >
              <span>Term</span>
              <span class="font-mono" style="color: {BB.ivory};">{term} months</span>
            </label>
            <div class="flex" style="gap: 6px;">
              {#each [3, 6, 12, 24, 36] as m}
                <button
                  on:click={() => (term = m)}
                  class="cursor-pointer transition-colors"
                  style="
                    flex: 1; padding: 10px 0;
                    font-family: inherit; font-size: 13px;
                    background: {term === m ? BB.gold : 'transparent'};
                    color: {term === m ? BB.navyDeep : BB.ivory};
                    border: 1px solid {term === m ? BB.gold : 'hsl(220 40% 44%)'};
                    border-radius: 6px;
                    font-weight: {term === m ? 700 : 500};
                  "
                >{m}m</button>
              {/each}
            </div>
            <div class="mt-2 text-[10.5px]" style="color: hsl(42 20% 55%);">
              Lock-up term. Early exit returns principal minus unvested yield.
            </div>
          </div>
        </div>

        <div class="flex items-center gap-3" style="margin: 28px 0 22px;">
          <span class="flex-1" style="height: 1px; background: linear-gradient(90deg, transparent, {BB.gold} 30%, {BB.gold} 70%, transparent);"></span>
          <span style="width: 8px; height: 8px; background: {BB.gold}; transform: rotate(45deg); box-shadow: 0 0 0 3px {BB.navy};"></span>
          <span class="flex-1" style="height: 1px; background: linear-gradient(90deg, transparent, {BB.gold} 30%, {BB.gold} 70%, transparent);"></span>
        </div>

        <div
          class="grid bb-stats-grid"
          style="grid-template-columns: repeat(3, 1fr); gap: 16px;"
        >
          {#each [['Projected yield', `+${projected.toLocaleString()} $CF`, `over ${term}m at compounded APY`], ['Monthly interest', `${monthly.toLocaleString()} $CF`, 'paid every 30 days'], ['Principal at maturity', `${(deposit + projected).toLocaleString()} $CF`, 'non-custodial, withdraw anytime']] as [label, val, sub]}
            <div
              style="
                background: hsl(220 50% 18%);
                border: 1px solid hsl(220 45% 30%);
                border-radius: 10px; padding: 14px 16px;
              "
            >
              <div
                class="uppercase mb-1.5"
                style="font-size: 10.5px; letter-spacing: 0.1em; color: hsl(42 25% 72%);"
              >{label}</div>
              <div
                class="font-serif-display"
                style="font-size: 22px; font-weight: 600; color: {BB.gold}; line-height: 1.1; letter-spacing: -0.01em;"
              >{val}</div>
              <div class="mt-0.5" style="font-size: 11px; color: hsl(42 20% 62%);">{sub}</div>
            </div>
          {/each}
        </div>

        <div
          class="flex items-center gap-2.5 mt-5.5"
          style="
            padding: 12px 16px;
            background: hsl(220 55% 16%); border: 1px dashed hsl(220 40% 38%);
            border-radius: 8px; font-size: 12px; color: hsl(42 25% 78%);
          "
        >
          <Icon name="info" size={16} style="color: {BB.gold};" />
          <span>
            Yield paid from café + farm revenue. APY governed by $CF holders via SNS proposal —
            <a href="/governance" style="color: {BB.gold}; text-decoration: underline; margin-left: 4px;">proposal #141</a>
          </span>
        </div>
      </div>

      <!-- Why -->
      <h2
        class="font-serif-display"
        style="font-size: 32px; font-weight: 600; margin: 44px 0 10px; letter-spacing: -0.015em; color: {BB.navyDeep};"
      >Why we're building a bank</h2>
      <p style="font-size: 16.5px; line-height: 1.65; margin: 0 0 14px; color: hsl(222 30% 20%);">
        El Salvador made Bitcoin legal tender in 2021. Five years in, the infrastructure that would let everyday Salvadoreños actually <em>save</em> in digital assets — not just speculate — still isn't there. Cafreso operates in San Miguel. We see it every day.
      </p>
      <p style="font-size: 16.5px; line-height: 1.65; margin: 0 0 14px; color: hsl(222 30% 20%);">
        Our café serves coffee. Our farm grows it. Our DAO treasury already generates revenue from both. Banking.Brave is simply the missing layer that lets that revenue flow back to the community as yield — denominated in $CF, auditable on every block.
      </p>

      <!-- Trust pillars -->
      <h2
        class="font-serif-display"
        style="font-size: 32px; font-weight: 600; margin: 38px 0 4px; letter-spacing: -0.015em; color: {BB.navyDeep};"
      >Four promises</h2>
      <p style="font-size: 15px; line-height: 1.6; margin: 0 0 2px; color: hsl(215 16% 45%);">
        These aren't marketing. Each one maps to a specific canister-level guarantee.
      </p>
      <div
        class="grid bb-pillars-grid"
        style="grid-template-columns: repeat(2, 1fr); gap: 14px; margin: 28px 0;"
      >
        {#each pillars as it}
          <div
            class="bg-white"
            style="
              border: 1px solid {BB.parchment}; border-top: 3px solid {BB.navy};
              border-radius: 10px; padding: 18px 20px;
              box-shadow: 0 1px 2px hsl(220 30% 20% / 0.04);
            "
          >
            <div class="flex items-center gap-2.5 mb-2.5">
              <span
                class="inline-flex items-center justify-center"
                style="
                  width: 34px; height: 34px; border-radius: 8px;
                  background: {BB.navy}; color: {BB.gold};
                "
              >
                <Icon name={it.icon} size={18} style="color: {BB.gold};" />
              </span>
              <h4
                class="font-serif-display m-0"
                style="font-size: 19px; font-weight: 600; letter-spacing: -0.005em;"
              >{it.title}</h4>
            </div>
            <p class="m-0" style="font-size: 14px; line-height: 1.55; color: hsl(222 30% 30%);">
              {it.body}
            </p>
          </div>
        {/each}
      </div>

      <!-- Roadmap -->
      <h2
        class="font-serif-display"
        style="font-size: 32px; font-weight: 600; margin: 38px 0 18px; letter-spacing: -0.015em; color: {BB.navyDeep};"
      >Roadmap</h2>
      <div class="relative mt-2" style="padding-left: 28px;">
        <span
          class="absolute rounded-sm"
          style="
            left: 13px; top: 10px; bottom: 10px; width: 2px;
            background: linear-gradient(180deg, {BB.gold}, {BB.navy});
          "
        ></span>
        {#each phases as ph, i}
          <div class="relative" style="margin-bottom: {i === phases.length - 1 ? 0 : 22}px;">
            <span
              class="absolute rounded-full"
              style="
                left: -21px; top: 6px; width: 16px; height: 16px;
                background: {ph.status === 'done' ? BB.gold : ph.status === 'now' ? 'white' : BB.parchment};
                border: 2px solid {ph.status === 'next' ? 'hsl(220 30% 60%)' : BB.navy};
                box-shadow: {ph.status === 'now' ? '0 0 0 4px hsl(43 74% 54% / 0.25)' : 'none'};
              "
            ></span>
            <div
              style="
                background: {ph.status === 'now' ? BB.navy : 'white'};
                color: {ph.status === 'now' ? BB.ivory : 'hsl(222 47% 11%)'};
                border: 1px solid {ph.status === 'now' ? BB.navy : BB.parchment};
                border-radius: 10px; padding: 14px 18px;
              "
            >
              <div class="flex items-baseline justify-between flex-wrap" style="gap: 12px;">
                <div class="flex items-baseline gap-2.5">
                  <span
                    class="font-mono uppercase"
                    style="font-size: 11px; letter-spacing: 0.1em; color: {ph.status === 'now' ? BB.gold : 'hsl(215 16% 47%)'};"
                  >PHASE {ph.p}</span>
                  <h4
                    class="font-serif-display m-0"
                    style="font-size: 20px; font-weight: 600; letter-spacing: -0.005em;"
                  >{ph.title}</h4>
                </div>
                <span style="font-size: 12px; color: {ph.status === 'now' ? 'hsl(42 25% 75%)' : 'hsl(215 16% 47%)'};">
                  {ph.date}
                </span>
              </div>
              <ul
                class="list-disc"
                style="margin: 10px 0 0; padding-left: 18px; font-size: 13.5px; line-height: 1.6; color: {ph.status === 'now' ? 'hsl(42 20% 85%)' : 'hsl(222 30% 30%)'};"
              >
                {#each ph.items as li}
                  <li style="margin: 3px 0;">{li}</li>
                {/each}
              </ul>
            </div>
          </div>
        {/each}
      </div>

      <!-- Burn note -->
      <div
        class="flex items-start gap-4 rounded-xl"
        style="
          margin: 36px 0 0; padding: 22px 26px;
          background: linear-gradient(180deg, hsl(45 85% 94%), hsl(45 80% 88%));
          border: 1px solid hsl(45 75% 72%);
        "
      >
        <span
          class="inline-flex items-center justify-center flex-shrink-0"
          style="
            width: 44px; height: 44px; border-radius: 10px;
            background: hsl(45 95% 62%); border: 1px solid hsl(32 72% 50%);
          "
        >
          <Icon name="fire" size={22} weight="fill" style="color: hsl(24 48% 12%);" />
        </span>
        <div>
          <div class="font-bold mb-1" style="font-size: 16px; color: hsl(24 48% 12%);">
            $nanas still burn. Always.
          </div>
          <div style="font-size: 14.5px; line-height: 1.55; color: hsl(24 48% 18%);">
            Banking.Brave is denominated in $CF, but the café's $nanas economy is untouched. Every coffee, every roaster, every leaderboard tick still burns $nanas — and now a portion of café revenue flows into the Banking.Brave vault to compound yield for depositors. Burn more coffee, earn more interest. Everybody wins.
          </div>
        </div>
      </div>

      <!-- Closing -->
      <h2
        class="font-serif-display"
        style="font-size: 32px; font-weight: 600; margin: 44px 0 10px; letter-spacing: -0.015em; color: {BB.navyDeep};"
      >What comes next</h2>
      <p style="font-size: 16.5px; line-height: 1.65; margin: 0 0 14px; color: hsl(222 30% 20%);">
        Testnet opens May 12 to the first 1,000 seats. We'll publish weekly treasury reports in this dev log. We'll onboard depositors in café-sized cohorts, not investor-sized ones. And when we're confident, we'll flip to mainnet and let the whole DAO in.
      </p>
      <p style="font-size: 16.5px; line-height: 1.65; margin: 0 0 14px; color: hsl(222 30% 20%);">
        If you've been with Cafreso since the first block — thank you. This is the thing we've been quietly working toward. If you're new here, there's never been a better week to join. Stake a seat below.
      </p>
      <p style="font-size: 16.5px; line-height: 1.65; margin: 0 0 2px; color: hsl(222 30% 20%);">
        Coffee, Crypto, and Community. Now also: savings.
      </p>
      <p class="italic" style="font-size: 15px; color: hsl(215 16% 45%); margin: 18px 0 0;">
        — anthony.icp, on behalf of the Cafreso core team
      </p>

      <!-- Waitlist CTA -->
      <div
        class="relative overflow-hidden"
        style="
          margin-top: 32px;
          background: linear-gradient(180deg, {BB.navy} 0%, {BB.navyDeep} 100%);
          border-radius: 16px; padding: 36px 40px;
          color: {BB.ivory};
          border: 1px solid {BB.gold};
        "
      >
        <img
          src="/assets/banking-brave-logo.png"
          alt=""
          class="absolute pointer-events-none"
          style="right: -60px; top: -60px; width: 280px; opacity: 0.08;"
        />
        <div class="relative" style="max-width: 640px; z-index: 1;">
          <div
            class="inline-flex items-center gap-2 uppercase font-bold mb-3.5"
            style="font-size: 10.5px; letter-spacing: 0.22em; color: {BB.gold};"
          >
            <span
              class="inline-flex items-center justify-center rounded-full"
              style="width: 22px; height: 22px; background: {BB.navy}; border: 1.5px solid {BB.gold};"
            >
              <img src="/assets/banking-brave-logo.png" alt="" style="width: 100%; height: 100%; object-fit: contain;" />
            </span>
            Banking.Brave · Testnet Access
          </div>
          <h2
            class="font-serif-display"
            style="font-size: 40px; font-weight: 600; margin: 0 0 14px; line-height: 1.1; letter-spacing: -0.015em;"
          >Reserve your seat among the first 1,000.</h2>
          <p style="font-size: 16px; line-height: 1.6; color: hsl(42 25% 82%); margin: 0 0 6px;">
            Stake 500 $CF to join the testnet cohort. Stake is returned at mainnet launch, plus a founding-member bonus equal to one month of vault yield. No KYC, no waitlist emails — just a signed transaction.
          </p>
          <div class="flex items-center gap-3.5 flex-wrap mt-6">
            <button
              on:click={() => bbModalOpen.set(true)}
              class="cursor-pointer font-serif-display"
              style="
                background: {BB.gold}; color: {BB.navyDeep};
                border: none; font-weight: 600; font-size: 16px;
                padding: 14px 28px; border-radius: 8px;
                letter-spacing: 0.01em;
                box-shadow: 0 8px 20px -6px {BB.goldDeep};
                transition: transform .2s;
              "
              on:mouseenter={(e) => (e.currentTarget.style.transform = 'translateY(-2px)')}
              on:mouseleave={(e) => (e.currentTarget.style.transform = 'none')}
            >Apply for early access →</button>
            <div style="font-size: 12px; color: hsl(42 20% 70%); line-height: 1.5;">
              <div><Icon name="users-three" size={13} /> 614 / 1,000 seats reserved</div>
              <div class="mt-0.5"><Icon name="clock" size={13} /> Testnet opens May 12, 2026</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer strip -->
      <div
        class="flex justify-between items-center flex-wrap gap-3.5 mt-8 pt-5"
        style="border-top: 1px dashed hsl(220 20% 75%); font-size: 13px; color: hsl(215 16% 47%);"
      >
        <span>Content hash <code style="font-size: 11.5px;">0x71ae…4f2b</code> · Signed by SNS-04</span>
        <Button
          variant="default"
          size="sm"
          class="!bg-[hsl(45_95%_62%)] !text-[hsl(24_48%_12%)] !border !border-[hsl(32_72%_50%)]"
          on:click={tipTeam}
        >
          <Icon name="fire" size={14} /> Tip the team
        </Button>
      </div>
    </div>

    <div class="mt-10">
      <CommentThread comments={COMMENTS} />
    </div>
  </div>
</div>
