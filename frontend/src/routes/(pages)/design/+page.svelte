<script>
  import Icon from '$lib/components/Icon.svelte';
  import Button from '$lib/components/Button.svelte';
  import Input from '$lib/components/Input.svelte';
  import Tag from '$lib/components/Tag.svelte';
  import Logo from '$lib/components/Logo.svelte';
  import Footer from '$lib/components/Footer.svelte';
  import ProductCard from '$lib/components/ProductCard.svelte';
  import { PRODUCTS } from '$lib/data/products.js';

  const sections = [
    { id: 'colors-brand', label: 'Brand colors' },
    { id: 'colors-accent', label: 'Accent colors' },
    { id: 'colors-semantic', label: 'Semantic' },
    { id: 'type-scale', label: 'Type scale' },
    { id: 'type-weights', label: 'Type weights' },
    { id: 'buttons', label: 'Buttons' },
    { id: 'badges', label: 'Badges' },
    { id: 'forms', label: 'Forms' },
    { id: 'icons', label: 'Icons' },
    { id: 'logos', label: 'Logos' },
    { id: 'illustrations', label: 'Illustrations' },
    { id: 'radii', label: 'Radii' },
    { id: 'shadows', label: 'Shadows' },
    { id: 'spacing', label: 'Spacing' },
    { id: 'product-card', label: 'Product card' },
    { id: 'header', label: 'Header' },
    { id: 'footer', label: 'Footer' },
    { id: 'loading', label: 'Loading splash' }
  ];

  const brand = [
    { bg: 'hsl(26 30% 74%)', name: 'Crema / Page BG', val: 'hsl(26 30% 74%)' },
    { bg: 'hsl(18 79% 86%)', name: 'Peach / Footer', val: '#f8cfbc' },
    { bg: 'hsl(24 48% 9%)', name: 'Espresso / Dark BG', val: 'hsl(24 48% 9%)' },
    { bg: 'hsl(222 47% 11%)', name: 'Primary (slate)', val: 'hsl(222 47% 11%)' }
  ];

  const accent = [
    { bg: 'hsl(45 95% 62%)', color: '#2a1800', chip: '$nanas', name: 'Banana', val: 'hsl(45 95% 62%)' },
    { bg: 'hsl(32 72% 50%)', color: '#fff', chip: 'rim', name: 'Banana Rim', val: 'hsl(32 72% 50%)' },
    { bg: 'hsl(43 74% 54%)', color: '#fff', chip: 'CF', name: 'ICP Gold', val: 'hsl(43 74% 54%)' },
    { bg: 'hsl(112 43% 45%)', color: '#fff', chip: 'farm', name: 'Leaf Green', val: 'hsl(112 43% 45%)' },
    { bg: 'hsl(134 61% 70%)', color: '#0a3512', chip: 'CTA', name: 'Mint CTA', val: 'green-300' },
    { bg: 'hsl(142 71% 45%)', color: '#fff', chip: 'hover', name: 'Mint Hover', val: 'green-500' },
    { bg: 'hsl(0 84% 60%)', color: '#fff', chip: '3', name: 'Cart Badge', val: 'red-500' },
    { bg: 'hsl(160 30% 78%)', color: '#133a36', chip: 'sky', name: 'Farm Sky', val: 'hsl(160 30% 78%)' }
  ];

  const semantic = [
    { bg: 'hsl(222 47% 11%)', name: 'primary', val: '222 47% 11%' },
    { bg: 'hsl(210 40% 98%)', name: 'primary-fg', val: '210 40% 98%', bordered: true },
    { bg: 'hsl(210 40% 96%)', name: 'secondary', val: '210 40% 96%' },
    { bg: 'hsl(210 40% 96%)', name: 'accent', val: '210 40% 96%' },
    { bg: 'hsl(0 72% 51%)', name: 'destructive', val: '0 72% 51%' },
    { bg: 'hsl(210 40% 96%)', name: 'muted', val: '210 40% 96%' },
    { bg: 'hsl(215 16% 47%)', name: 'muted-fg', val: '215 16% 47%' },
    { bg: 'hsl(214 32% 91%)', name: 'border', val: '214 32% 91%' },
    { bg: 'white', name: 'card', val: '0 0% 100%', bordered: true },
    { bg: 'hsl(222 84% 5%)', name: 'ring', val: '222 84% 5%' }
  ];

  const weights = [
    { m: 'System sans', s: 'font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif; font-size: 18px;', t: 'The quick brown roaster jumps over the banana coin. — Cafreso Café' },
    { m: '400 Regular', s: 'font-weight: 400; font-size: 18px;', t: 'The quick brown roaster jumps over the banana coin.' },
    { m: '500 Medium', s: 'font-weight: 500; font-size: 18px;', t: 'The quick brown roaster jumps over the banana coin.' },
    { m: '600 Semibold', s: 'font-weight: 600; font-size: 18px;', t: 'The quick brown roaster jumps over the banana coin.' },
    { m: '700 Bold', s: 'font-weight: 700; font-size: 18px;', t: 'The quick brown roaster jumps over the banana coin.' },
    { m: '800 Extrabold', s: 'font-weight: 800; font-size: 18px;', t: 'The quick brown roaster jumps over the banana coin.' }
  ];

  const iconNames = [
    'coffee-bean', 'coffee', 'storefront', 'shopping-cart', 'trophy', 'infinity', 't-shirt', 'piggy-bank',
    'coins', 'chart-pie', 'calendar-check', 'gear', 'info', 'map-pin', 'circle-notch', 'check'
  ];

  const radii = [
    { r: '2px', l: 'sm · 2px' },
    { r: '4px', l: 'md · 4px' },
    { r: '8px', l: 'lg · 8px (base)' },
    { r: '12px', l: 'xl · 12px' },
    { r: '9999px', l: 'full · pill' }
  ];

  const spaces = [
    { k: '1 · 4px', w: 4 },
    { k: '2 · 8px', w: 8 },
    { k: '3 · 12px', w: 12 },
    { k: '4 · 16px', w: 16 },
    { k: '6 · 24px', w: 24 },
    { k: '8 · 32px', w: 32 },
    { k: '14 · 56px', w: 56 }
  ];
</script>

<svelte:head>
  <title>Design System · Cafreso</title>
  <meta name="description" content="The Cafreso design system — color tokens, typography, buttons, badges, forms, icons, logos, and components used across the dapp." />
</svelte:head>

<div class="design-container mx-auto px-6 py-10" style="max-width: 1100px;">
  <header class="mb-8">
    <h1 class="text-[36px] font-extrabold leading-[1.1] m-0 mb-2">Cafreso Design System</h1>
    <p class="text-muted-foreground m-0">Tokens, components, and illustrations used across the dapp.</p>
    <nav class="flex flex-wrap gap-2 mt-5">
      {#each sections as s}
        <a
          href="#{s.id}"
          class="text-[12px] font-medium px-2.5 py-1 rounded-full bg-secondary text-secondary-foreground hover:bg-secondary/80 no-underline"
        >{s.label}</a>
      {/each}
    </nav>
  </header>

  <!-- Brand colors -->
  <section id="colors-brand" class="mb-10">
    <h2 class="text-2xl font-bold mb-4">Brand colors</h2>
    <div class="design-grid-4 grid gap-3" style="grid-template-columns: repeat(4, 1fr);">
      {#each brand as b}
        <div class="bg-white rounded-lg overflow-hidden">
          <div style="height: 80px; background: {b.bg}; border-bottom: 1px solid rgba(0,0,0,.06);"></div>
          <div class="px-3 py-2.5">
            <div class="font-semibold text-[13px]">{b.name}</div>
            <div class="font-mono text-[11px] text-muted-foreground mt-1">{b.val}</div>
          </div>
        </div>
      {/each}
    </div>
  </section>

  <!-- Accent colors -->
  <section id="colors-accent" class="mb-10">
    <h2 class="text-2xl font-bold mb-4">Accent colors</h2>
    <div class="design-grid-4 grid gap-3" style="grid-template-columns: repeat(4, 1fr);">
      {#each accent as a}
        <div class="bg-white rounded-lg overflow-hidden">
          <div class="flex items-center justify-center font-bold text-[13px]" style="height: 80px; background: {a.bg}; color: {a.color};">{a.chip}</div>
          <div class="px-3 py-2.5">
            <div class="font-semibold text-[13px]">{a.name}</div>
            <div class="font-mono text-[11px] text-muted-foreground mt-1">{a.val}</div>
          </div>
        </div>
      {/each}
    </div>
  </section>

  <!-- Semantic -->
  <section id="colors-semantic" class="mb-10">
    <h2 class="text-2xl font-bold mb-4">Semantic colors</h2>
    <div class="design-grid-5 grid gap-2.5" style="grid-template-columns: repeat(5, 1fr);">
      {#each semantic as s}
        <div class="bg-white rounded-lg overflow-hidden text-xs">
          <div style="height: 56px; background: {s.bg}; {s.bordered ? 'border: 1px solid #e5e7eb;' : ''}"></div>
          <div class="px-2.5 py-2">
            <div class="font-semibold">{s.name}</div>
            <div class="font-mono text-[10px] text-muted-foreground mt-0.5">{s.val}</div>
          </div>
        </div>
      {/each}
    </div>
  </section>

  <!-- Type scale -->
  <section id="type-scale" class="mb-10">
    <h2 class="text-2xl font-bold mb-4">Type scale</h2>
    <div class="bg-white px-6 py-5 rounded-lg">
      <div class="text-[36px] font-extrabold leading-[1.1]">Coffee, Crypto, and Community</div>
      <div class="text-[11px] uppercase text-muted-foreground mt-1.5" style="letter-spacing: 0.06em;">H1 / 36px / Extrabold 800 / Page title</div>
      <div class="text-2xl font-bold mt-3.5">Cafreso Community Leaderboard</div>
      <div class="text-[11px] uppercase text-muted-foreground mt-1.5" style="letter-spacing: 0.06em;">H2 / 24px / Bold 700 / Section title</div>
      <div class="text-xl font-bold mt-3.5">How It Works</div>
      <div class="text-[11px] uppercase text-muted-foreground mt-1.5" style="letter-spacing: 0.06em;">H3 / 20px / Bold 700 / Subsection</div>
      <div class="text-base leading-normal mt-3.5 max-w-[620px]">Premium, ethically-sourced coffee delivered to your door — and the chance to stake tokens while you sip.</div>
      <div class="text-[11px] uppercase text-muted-foreground mt-1.5" style="letter-spacing: 0.06em;">Body / 16px / Regular 400 / line-height 1.5</div>
      <div class="text-sm text-muted-foreground mt-2.5">(3,200 Nanas · $4.80 USD)</div>
      <div class="text-[11px] uppercase text-muted-foreground mt-1.5" style="letter-spacing: 0.06em;">Small / 14px / Muted foreground</div>
    </div>
  </section>

  <!-- Type weights -->
  <section id="type-weights" class="mb-10">
    <h2 class="text-2xl font-bold mb-4">Type weights</h2>
    <div class="bg-white px-5 py-5 rounded-lg">
      {#each weights as w, i}
        <div class="flex items-baseline gap-4 py-2" style="border-bottom: {i < weights.length - 1 ? '1px solid #eee' : 'none'};">
          <div class="text-[11px] uppercase text-muted-foreground" style="width: 110px; letter-spacing: 0.05em;">{w.m}</div>
          <div class="flex-1" style={w.s}>{w.t}</div>
        </div>
      {/each}
    </div>
    <p class="text-xs text-muted-foreground mt-2">No custom webfont in production — system sans stack verbatim.</p>
  </section>

  <!-- Buttons -->
  <section id="buttons" class="mb-10">
    <h2 class="text-2xl font-bold mb-4">Buttons</h2>
    <div class="bg-white p-5 rounded-lg">
      <div class="flex gap-2.5 flex-wrap items-start">
        <div class="flex flex-col items-center gap-1.5">
          <Button variant="default"><Icon name="check" size={14} /> Submit Order</Button>
          <div class="text-[10px] font-mono text-muted-foreground">default</div>
        </div>
        <div class="flex flex-col items-center gap-1.5">
          <Button variant="secondary">Cancel</Button>
          <div class="text-[10px] font-mono text-muted-foreground">secondary</div>
        </div>
        <div class="flex flex-col items-center gap-1.5">
          <Button variant="outline">Edit Profile</Button>
          <div class="text-[10px] font-mono text-muted-foreground">outline</div>
        </div>
        <div class="flex flex-col items-center gap-1.5">
          <Button variant="ghost">View details</Button>
          <div class="text-[10px] font-mono text-muted-foreground">ghost</div>
        </div>
        <div class="flex flex-col items-center gap-1.5">
          <Button variant="destructive"><Icon name="trash" size={14} /> Delete</Button>
          <div class="text-[10px] font-mono text-muted-foreground">destructive</div>
        </div>
        <div class="flex flex-col items-center gap-1.5">
          <Button variant="link">Read more</Button>
          <div class="text-[10px] font-mono text-muted-foreground">link</div>
        </div>
      </div>
    </div>
  </section>

  <!-- Badges -->
  <section id="badges" class="mb-10">
    <h2 class="text-2xl font-bold mb-4">Badges &amp; pills</h2>
    <div class="bg-white p-5 rounded-lg flex gap-3.5 items-center flex-wrap">
      <span class="bg-secondary text-secondary-foreground text-xs font-medium px-2.5 py-1 rounded-full">coffee</span>
      <span class="bg-secondary text-secondary-foreground text-xs font-medium px-2.5 py-1 rounded-full">dao</span>
      <span class="bg-secondary text-secondary-foreground text-xs font-medium px-2.5 py-1 rounded-full">accessories</span>
      <span class="text-white text-[11px] font-semibold rounded-full px-1.5 py-0.5" style="background: hsl(0 84% 60%); border: 2px solid white;">3</span>
      <span class="inline-flex items-center gap-1.5 bg-white px-3 py-1.5 rounded-full font-semibold" style="border: 1px solid #eee;">
        3,200 <img src="/assets/nanas-coin.png" alt="" class="w-[18px]" /> Nanas
      </span>
      <span class="inline-flex items-center gap-1.5 text-[13px] font-medium" style="color: hsl(142 71% 35%);">
        <span class="w-2 h-2 rounded-full" style="background: currentColor;"></span> On-chain confirmed
      </span>
    </div>
  </section>

  <!-- Forms -->
  <section id="forms" class="mb-10">
    <h2 class="text-2xl font-bold mb-4">Forms</h2>
    <div class="bg-white p-5 rounded-lg">
      <div class="flex gap-3.5 items-end flex-wrap">
        <Input label="Username" value="coffeefarmer" />
        <Input label="Amount" value="3,200" />
        <Input label="Email" value="bad" error="Enter a valid email." />
      </div>
    </div>
  </section>

  <!-- Icons -->
  <section id="icons" class="mb-10">
    <h2 class="text-2xl font-bold mb-4">Icons · Phosphor regular</h2>
    <div
      class="p-4 rounded-2xl"
      style="background: hsl(26 35% 94% / 0.4); backdrop-filter: blur(22px) saturate(160%); -webkit-backdrop-filter: blur(22px) saturate(160%); border: 1px solid hsl(26 35% 98% / 0.7);"
    >
      <div class="design-grid-8 grid gap-2.5" style="grid-template-columns: repeat(8, 1fr);">
        {#each iconNames as n}
          <div
            class="text-center py-3 px-1.5 rounded-xl cursor-pointer"
            style="background: linear-gradient(180deg, hsl(0 0% 100% / 0.35), hsl(0 0% 100% / 0.12)); border: 1px solid hsl(0 0% 100% / 0.5);"
          >
            <Icon name={n} size={24} />
            <div class="text-[9.5px] font-mono text-muted-foreground mt-1.5">{n}</div>
          </div>
        {/each}
      </div>
    </div>
    <p class="text-[11px] text-muted-foreground mt-2.5 flex items-center gap-2">
      <span class="w-1.5 h-1.5 rounded-full" style="background: hsl(45 95% 55%); box-shadow: 0 0 8px hsl(45 95% 55%);"></span>
      Phosphor · regular weight · 24px · ~100 glyphs registered in <code>icons/index.ts</code>
    </p>
  </section>

  <!-- Logos -->
  <section id="logos" class="mb-10">
    <h2 class="text-2xl font-bold mb-4">Logos</h2>
    <div class="flex gap-[30px] items-center flex-wrap">
      <div class="bg-white p-5 rounded-lg text-center">
        <Logo size={72} variant="black" />
        <div class="text-[11px] font-mono text-muted-foreground mt-2">cf-black.png · light bg</div>
      </div>
      <div class="p-5 rounded-lg text-center" style="background: hsl(24 48% 9%);">
        <Logo size={72} variant="white" />
        <div class="text-[11px] font-mono mt-2" style="color: #ddd;">cf-white.png · dark bg</div>
      </div>
      <div class="p-5 rounded-lg text-center" style="background: hsl(222 47% 11%);">
        <Logo size={72} variant="gold" />
        <div class="text-[11px] font-mono mt-2" style="color: #ddd;">cf-gold.png · celebratory</div>
      </div>
    </div>
  </section>

  <!-- Illustrations -->
  <section id="illustrations" class="mb-10">
    <h2 class="text-2xl font-bold mb-4">Illustrations</h2>
    <div class="flex gap-3.5 flex-wrap">
      <div class="bg-white rounded-lg p-2.5 flex-1" style="min-width: 280px;">
        <img src="/assets/cafreso.webp" alt="" class="w-full rounded-md block" style="height: 200px; object-fit: cover;" />
        <div class="text-[11px] font-mono text-muted-foreground pt-2">cafreso.webp — pixel-art vertical farm hero</div>
      </div>
      <div class="bg-white rounded-lg p-2.5 flex-1" style="min-width: 280px;">
        <img src="/assets/cafreso-roaster.webp" alt="" class="w-full rounded-md block" style="height: 200px; object-fit: contain; background: #fafafa;" />
        <div class="text-[11px] font-mono text-muted-foreground pt-2">cafreso-roaster.webp — pencil sketch</div>
      </div>
    </div>
  </section>

  <!-- Radii -->
  <section id="radii" class="mb-10">
    <h2 class="text-2xl font-bold mb-4">Radii</h2>
    <div class="bg-white p-5 rounded-lg">
      <div class="flex gap-3 items-end">
        {#each radii as r}
          <div class="flex flex-col items-center gap-1.5">
            <div class="bg-primary" style="width: 72px; height: 72px; border-radius: {r.r};"></div>
            <div class="text-[11px] font-mono">{r.l}</div>
          </div>
        {/each}
      </div>
      <div class="text-xs text-muted-foreground mt-3">--radius: 0.5rem — drives rounded-md (buttons), rounded-lg (cards/dialogs).</div>
    </div>
  </section>

  <!-- Shadows -->
  <section id="shadows" class="mb-10">
    <h2 class="text-2xl font-bold mb-4">Shadows</h2>
    <div class="flex gap-5 flex-wrap">
      <div class="bg-white px-4 py-3.5 rounded-lg text-xs font-mono" style="box-shadow: 0 1px 2px rgba(0,0,0,.05);">shadow-sm</div>
      <div class="bg-white px-4 py-3.5 rounded-lg text-xs font-mono" style="box-shadow: 0 4px 6px rgba(0,0,0,.1), 0 2px 4px rgba(0,0,0,.06);">shadow-md</div>
      <div class="bg-white px-4 py-3.5 rounded-lg text-xs font-mono" style="box-shadow: 0 10px 15px rgba(0,0,0,.1), 0 4px 6px rgba(0,0,0,.05);">shadow-lg</div>
      <div class="flex items-center justify-center text-white rounded-lg" style="width: 140px; height: 72px; background: rgba(0,0,0,.4);">bg-black/40 overlay</div>
    </div>
    <div class="text-xs text-muted-foreground mt-3">Shadows are subtle; overlays use bg-black at opacity 0.4 (used behind cart drawer).</div>
  </section>

  <!-- Spacing -->
  <section id="spacing" class="mb-10">
    <h2 class="text-2xl font-bold mb-4">Spacing</h2>
    <div class="bg-white p-4 rounded-lg">
      {#each spaces as s}
        <div class="flex items-center gap-1.5 mb-2">
          <div class="font-mono text-[11px]" style="width: 80px;">{s.k}</div>
          <div style="background: hsl(222 47% 11%); height: 16px; border-radius: 3px; width: {s.w}px;"></div>
        </div>
      {/each}
    </div>
    <div class="text-xs text-muted-foreground mt-2.5">Tailwind 4px baseline. 14 = header h-14 (56px).</div>
  </section>

  <!-- Product card -->
  <section id="product-card" class="mb-10">
    <h2 class="text-2xl font-bold mb-4">Product card</h2>
    <div class="grid gap-6" style="grid-template-columns: repeat(2, 1fr);">
      <ProductCard p={PRODUCTS[0]} />
      <ProductCard p={PRODUCTS[4]} />
    </div>
  </section>

  <!-- Header spec -->
  <section id="header" class="mb-10">
    <h2 class="text-2xl font-bold mb-4">Header</h2>
    <div class="bg-white p-5 rounded-lg">
      <p class="text-sm text-muted-foreground m-0">
        Sticky glass bar at the top of every page. Crema background with backdrop-blur;
        animated pill indicator tracks the active nav item. Cart badge animates in on count change.
      </p>
      <p class="text-sm m-0 mt-3">→ See it on <a href="/" class="underline underline-offset-4">any app route</a>.</p>
    </div>
  </section>

  <!-- Footer spec -->
  <section id="footer" class="mb-10">
    <h2 class="text-2xl font-bold mb-4">Footer</h2>
    <Footer />
  </section>

  <!-- Loading splash -->
  <section id="loading" class="mb-10">
    <h2 class="text-2xl font-bold mb-4">Loading splash</h2>
    <div class="bg-white rounded-lg overflow-hidden">
      <iframe src="/loading" title="Loading splash preview" class="w-full block" style="height: 380px; border: none;"></iframe>
    </div>
    <p class="text-xs text-muted-foreground mt-2">
      Served standalone at <code>/loading</code> — used as the initial canister boot screen.
    </p>
  </section>
</div>
