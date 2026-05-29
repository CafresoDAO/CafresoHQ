<script>
  import Icon from './Icon.svelte';
  import { bbLinks, aiCafresoOrigin } from '$lib/links.js';

  const shop = [
    { i: 'coffee-bean', t: 'Coffee', href: '/shop' },
    { i: 't-shirt', t: 'Merch', href: '/shop' },
    { i: 'infinity', t: 'SNS', href: '/shop' }
  ];
  // External ecosystem links — force full navigation with data-sveltekit-reload
  // so the SPA router doesn't try to resolve cross-origin URLs in-app.
  const ecosystem = [
    { i: 'coin',          t: 'Mine',        href: bbLinks.mine,        label: 'banking.cafreso.com' },
    { i: 'arrows-left-right', t: 'Exchange', href: bbLinks.exchange,   label: null },
    { i: 'bridge',        t: 'Bridge',      href: bbLinks.bridge,      label: null },
    { i: 'receipt',       t: 'Transactions', href: bbLinks.transactions, label: null },
    { i: 'brain',         t: 'AI Library',  href: aiCafresoOrigin,     label: 'ai.cafreso.com' },
  ];
  const about = [
    { i: 'article', t: 'Dev Log', href: '/blog' },
    { i: 'trophy', t: 'Leaderboard', href: '/leaderboard' },
    { i: 'info', t: 'About', href: '/about' }
  ];
</script>

<footer class="px-[18px] pb-[18px] pt-7 mt-10">
  <div
    class="footer-grid mx-auto relative overflow-hidden rounded-[18px]"
    style="max-width: 1240px;
      background: linear-gradient(180deg, hsl(24 28% 18%), hsl(24 30% 14%));
      padding: 32px 32px 20px;
      display: grid;
      grid-template-columns: 1.2fr 0.9fr 1fr 0.9fr 1.2fr;
      gap: 28px;
      font-size: 14px;
      color: hsl(26 18% 72%);
      box-shadow: 0 20px 40px -24px hsl(24 40% 8% / 0.55);"
  >
    <div
      class="absolute inset-0 pointer-events-none"
      style="background: radial-gradient(ellipse at 0% 0%, hsl(45 95% 62% / 0.08), transparent 55%);"
    ></div>
    <div class="flex flex-col gap-3 relative">
      <div class="inline-flex items-center gap-2.5">
        <img
          src="/assets/cf-gold.png"
          alt=""
          class="w-7 h-7"
          style="filter: drop-shadow(0 1px 2px hsl(0 0% 0% / 0.4));"
        />
        <span
          class="font-semibold text-[15px] tracking-tight"
          style="color: hsl(26 35% 92%);"
        >Cafreso · Minegold</span>
      </div>
      <p class="m-0 leading-[1.55] max-w-[30ch]">
        A DAO-powered café bundled with Minegold DeFi — brew, mine, and refine
        your way into gold-backed wealth on the Internet Computer.
      </p>
    </div>

    <div>
      <h4
        class="text-[11px] font-semibold uppercase m-0 mb-3.5"
        style="letter-spacing: 0.08em; color: hsl(45 60% 85%);"
      >Shop</h4>
      {#each shop as l}
        <a
          href={l.href}
          class="flex items-center gap-2.5 no-underline mb-2.5 cursor-pointer"
          style="color: hsl(26 18% 72%); transition: color .18s, transform .18s;"
        >
          <Icon name={l.i} size={16} style="color: hsl(45 95% 62%);" /> {l.t}
        </a>
      {/each}
    </div>

    <div>
      <h4
        class="text-[11px] font-semibold uppercase m-0 mb-3.5"
        style="letter-spacing: 0.08em; color: hsl(45 60% 85%);"
      >Ecosystem</h4>
      {#each ecosystem as l}
        {#if l.t === 'AI Library'}
          <div style="height: 1px; background: hsl(26 20% 28%); margin: 8px 0 10px;"></div>
        {/if}
        <a
          href={l.href}
          data-sveltekit-reload="on"
          rel="noopener"
          class="flex items-center gap-2.5 no-underline mb-2.5 cursor-pointer"
          style="color: hsl(26 18% 72%);"
        >
          <Icon name={l.i} size={16} style="color: hsl(45 95% 62%);" />
          <span>
            {l.t}
            {#if l.label}
              <span style="display: block; font-size: 10px; opacity: 0.5; line-height: 1.2;">{l.label}</span>
            {/if}
          </span>
        </a>
      {/each}
    </div>

    <div>
      <h4
        class="text-[11px] font-semibold uppercase m-0 mb-3.5"
        style="letter-spacing: 0.08em; color: hsl(45 60% 85%);"
      >Community</h4>
      {#each about as l}
        <a
          href={l.href}
          class="flex items-center gap-2.5 no-underline mb-2.5 cursor-pointer"
          style="color: hsl(26 18% 72%);"
        >
          <Icon name={l.i} size={16} style="color: hsl(45 95% 62%);" /> {l.t}
        </a>
      {/each}
    </div>

    <div>
      <h4
        class="text-[11px] font-semibold uppercase m-0 mb-3.5"
        style="letter-spacing: 0.08em; color: hsl(45 60% 85%);"
      >Connect</h4>
      <a
        href="/"
        class="flex items-center gap-2.5 no-underline mb-2.5 cursor-pointer"
        style="color: hsl(26 18% 72%);"
      >
        <img src="/assets/open-chat.jpg" alt="" class="w-[18px] rounded-[3px]" /> Open Chat
      </a>
      <a
        href="/"
        class="flex items-center gap-2.5 no-underline mb-2.5 cursor-pointer"
        style="color: hsl(26 18% 72%);"
      >
        <img src="/assets/icp.png" alt="" class="w-4" /> Dfinity Forum
      </a>
      <a
        href="/"
        class="flex items-center gap-2.5 no-underline mb-2.5 cursor-pointer"
        style="color: hsl(26 18% 72%);"
      >
        <Icon name="map-pin" size={16} style="color: hsl(45 95% 62%);" /> San Miguel, El Salvador
      </a>
      <a
        href="mailto:Anthony@cafreso.com"
        class="flex items-center gap-2.5 no-underline mb-2.5 cursor-pointer"
        style="color: hsl(26 18% 72%);"
      >
        <Icon name="envelope" size={16} style="color: hsl(45 95% 62%);" /> Anthony@cafreso.com
      </a>
    </div>

    <div
      class="footer-legal flex justify-between items-center text-xs mt-2.5 pt-4"
      style="grid-column: 1 / -1; border-top: 1px solid hsl(26 20% 28%);"
    >
      <span>© 2026 Cafreso DAO × Minegold · Powered by the Internet Computer</span>
      <span class="inline-flex gap-[18px]">
        <a href="/" style="color: hsl(26 18% 72%);" class="no-underline">Privacy</a>
        <a href="/" style="color: hsl(26 18% 72%);" class="no-underline">Terms</a>
      </span>
    </div>
  </div>
</footer>
