<script>
  import { page } from '$app/stores';
  import Icon from './Icon.svelte';
  import { aiSearchOpen } from '$lib/stores/blog.js';
  import { bankingBraveOrigin, aiCafresoOrigin } from '$lib/links.js';

  // Mobile bottom tab bar — 6 core destinations.
  // "Explore" opens a popover with Dev Log, Forums, Banking, and AI Library.
  // "Search" opens the AI search modal powered by ai.cafreso.com.
  const items = [
    { href: '/',           key: 'home',       icon: 'house',            label: 'Home'    },
    { href: '/shop',       key: 'shop',       icon: 'coffee-bean',      label: 'Shop'    },
    { key: 'ai-search',   icon: 'magnifying-glass', label: 'Search',    aiSearch: true   },
    { key: 'explore',     icon: 'compass',          label: 'Explore',   popover: true    },
    { href: '/governance', key: 'governance', icon: 'gavel',            label: 'DAO', beta: true },
    { href: '/profile',    key: 'profile',    icon: 'user-circle',      label: 'Me'      },
  ];

  let explorePopoverOpen = false;

  $: path = $page.url.pathname;
  $: activeKey = path === '/'
    ? 'home'
    : path.startsWith('/shop') || path.startsWith('/product') || path.startsWith('/checkout') || path.startsWith('/success')
      ? 'shop'
      : path.startsWith('/blog')
        ? 'explore'
        : path.startsWith('/forums')
          ? 'explore'
          : path.startsWith('/governance')
            ? 'governance'
            : path.startsWith('/search')
              ? 'ai-search'
              : path.startsWith('/profile')
                ? 'profile'
                : '';

  $: exploreSub = path.startsWith('/forums') ? 'forums' : path.startsWith('/blog') ? 'devlog' : null;

  function toggleExplorePopover() {
    explorePopoverOpen = !explorePopoverOpen;
  }

  function closeExplorePopover() {
    explorePopoverOpen = false;
  }

  function openAiSearch() {
    closeExplorePopover();
    aiSearchOpen.set(true);
  }
</script>

<!-- Backdrop to close popover when tapping outside -->
{#if explorePopoverOpen}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    on:click={closeExplorePopover}
    style="position: fixed; inset: 0; z-index: 19;"
  ></div>
{/if}

<nav
  class="mobile-only fixed z-20 flex justify-around"
  style="
    left: 10px; right: 10px; bottom: 10px;
    background: hsl(26 45% 98% / 0.92);
    backdrop-filter: blur(20px) saturate(160%);
    -webkit-backdrop-filter: blur(20px) saturate(160%);
    border: 1px solid hsl(26 30% 85%);
    border-radius: 18px; padding: 5px 4px;
    box-shadow: 0 14px 30px -10px hsl(24 35% 15% / 0.28), 0 2px 0 hsl(26 40% 98% / 0.5) inset;
  "
>
  {#each items as it}
    {@const active = activeKey === it.key}

    {#if it.aiSearch}
      <!-- AI Search center button — opens modal -->
      <button
        type="button"
        on:click={openAiSearch}
        class="flex flex-col items-center gap-[2px] py-1.5 px-0.5 font-semibold cursor-pointer transition-colors"
        style="
          flex: 1; min-width: 0; border: none;
          background: {active ? 'hsl(260 70% 50%)' : 'transparent'};
          color: {active ? 'white' : 'hsl(222 47% 11% / 0.6)'};
          border-radius: 11px;
          font-size: 8.5px; letter-spacing: 0em;
          overflow: hidden;
        "
        aria-label="AI Search"
      >
        <span style="position: relative; display: inline-flex; flex-shrink: 0;">
          <Icon name="magnifying-glass" size={17} />
          <!-- AI indicator dot -->
          {#if !active}
            <span style="
              position: absolute; top: -2px; right: -4px;
              width: 6px; height: 6px; border-radius: 50%;
              background: hsl(260 70% 55%);
              border: 1.5px solid hsl(26 45% 98%);
            "></span>
          {/if}
        </span>
        Search
      </button>

    {:else if it.popover}
      <!-- Explore tab with popover -->
      <div style="flex: 1; min-width: 0; position: relative;">
        <button
          type="button"
          on:click={toggleExplorePopover}
          class="flex flex-col items-center gap-[2px] py-1.5 px-0.5 font-semibold cursor-pointer transition-colors relative"
          style="
            width: 100%; border: none;
            background: {active ? 'hsl(222 47% 11%)' : 'transparent'};
            color: {active ? 'white' : 'hsl(222 47% 11% / 0.6)'};
            border-radius: 11px;
            font-size: 8.5px; letter-spacing: 0em;
            overflow: hidden;
          "
        >
          <span style="position: relative; display: inline-flex; flex-shrink: 0;">
            <Icon name={it.icon} size={17} />
          </span>
          {it.label}
        </button>

        <!-- Explore popover bubble -->
        {#if explorePopoverOpen}
          <div
            class="explore-popover"
            style="
              position: absolute; bottom: calc(100% + 10px); left: 50%;
              transform: translateX(-50%);
              min-width: 195px;
              background: hsl(26 45% 98% / 0.96);
              backdrop-filter: blur(18px) saturate(150%);
              -webkit-backdrop-filter: blur(18px) saturate(150%);
              border: 1px solid hsl(26 30% 82%);
              border-radius: 14px; padding: 5px;
              box-shadow: 0 12px 32px -8px hsl(24 35% 15% / 0.3), 0 1px 0 hsl(26 40% 98% / 0.5) inset;
              z-index: 25;
              animation: popUp .18s cubic-bezier(.2,.8,.2,1);
            "
          >
            <!-- Arrow -->
            <div style="
              position: absolute; bottom: -6px; left: 50%; transform: translateX(-50%) rotate(45deg);
              width: 11px; height: 11px;
              background: hsl(26 45% 98% / 0.96);
              border-right: 1px solid hsl(26 30% 82%);
              border-bottom: 1px solid hsl(26 30% 82%);
            "></div>

            <!-- Dev Log -->
            <a
              href="/blog"
              on:click={closeExplorePopover}
              class="popover-item"
              style="
                display: flex; align-items: center; gap: 10px;
                padding: 10px 12px; border-radius: 10px;
                text-decoration: none;
                background: {exploreSub === 'devlog' ? 'hsl(222 47% 11%)' : 'transparent'};
                color: {exploreSub === 'devlog' ? 'white' : 'hsl(222 47% 11%)'};
                font-size: 13px; font-weight: 600;
                transition: background .12s;
              "
            >
              <span style="
                width: 30px; height: 30px; border-radius: 8px;
                display: flex; align-items: center; justify-content: center;
                background: {exploreSub === 'devlog' ? 'hsl(222 30% 22%)' : 'hsl(26 40% 92%)'};
                flex-shrink: 0;
              ">
                <Icon name="article" size={15} />
              </span>
              <div>
                <div>Dev Log</div>
                <div style="font-size: 10px; font-weight: 400; opacity: 0.6; margin-top: 1px;">Posts & updates</div>
              </div>
            </a>

            <!-- Forums -->
            <a
              href="/forums"
              on:click={closeExplorePopover}
              class="popover-item"
              style="
                display: flex; align-items: center; gap: 10px;
                padding: 10px 12px; border-radius: 10px;
                text-decoration: none;
                background: {exploreSub === 'forums' ? 'hsl(222 47% 11%)' : 'transparent'};
                color: {exploreSub === 'forums' ? 'white' : 'hsl(222 47% 11%)'};
                font-size: 13px; font-weight: 600;
                transition: background .12s;
                margin-top: 2px;
              "
            >
              <span style="
                width: 30px; height: 30px; border-radius: 8px;
                display: flex; align-items: center; justify-content: center;
                background: {exploreSub === 'forums' ? 'hsl(222 30% 22%)' : 'hsl(26 40% 92%)'};
                flex-shrink: 0;
              ">
                <Icon name="chats-circle" size={15} />
              </span>
              <div>
                <div>Forums</div>
                <div style="font-size: 10px; font-weight: 400; opacity: 0.6; margin-top: 1px;">Community threads</div>
              </div>
            </a>

            <!-- Divider -->
            <div style="height: 1px; background: hsl(26 30% 88%); margin: 4px 2px;"></div>

            <!-- Banking (external) -->
            <a
              href={bankingBraveOrigin}
              data-sveltekit-reload="on"
              rel="noopener"
              on:click={closeExplorePopover}
              class="popover-item"
              style="
                display: flex; align-items: center; gap: 10px;
                padding: 10px 12px; border-radius: 10px;
                text-decoration: none;
                color: hsl(222 47% 11%);
                font-size: 13px; font-weight: 600;
                transition: background .12s;
                margin-top: 2px;
              "
            >
              <span style="
                width: 30px; height: 30px; border-radius: 8px;
                display: flex; align-items: center; justify-content: center;
                background: hsl(220 78% 92%);
                flex-shrink: 0;
              ">
                <Icon name="bank" size={15} style="color: hsl(220 78% 44%);" />
              </span>
              <div style="flex: 1; min-width: 0;">
                <div style="display: flex; align-items: center; gap: 4px;">
                  Banking
                  <Icon name="arrow-up-right" size={10} style="opacity: 0.45;" />
                </div>
                <div style="font-size: 10px; font-weight: 400; opacity: 0.55; margin-top: 1px;">banking.cafreso.com</div>
              </div>
            </a>

            <!-- AI Library (external) -->
            <a
              href={aiCafresoOrigin}
              data-sveltekit-reload="on"
              rel="noopener"
              on:click={closeExplorePopover}
              class="popover-item"
              style="
                display: flex; align-items: center; gap: 10px;
                padding: 10px 12px; border-radius: 10px;
                text-decoration: none;
                color: hsl(222 47% 11%);
                font-size: 13px; font-weight: 600;
                transition: background .12s;
                margin-top: 2px;
              "
            >
              <span style="
                width: 30px; height: 30px; border-radius: 8px;
                display: flex; align-items: center; justify-content: center;
                background: hsl(260 70% 93%);
                flex-shrink: 0;
              ">
                <Icon name="brain" size={15} style="color: hsl(260 70% 50%);" />
              </span>
              <div style="flex: 1; min-width: 0;">
                <div style="display: flex; align-items: center; gap: 4px;">
                  AI Library
                  <Icon name="arrow-up-right" size={10} style="opacity: 0.45;" />
                </div>
                <div style="font-size: 10px; font-weight: 400; opacity: 0.55; margin-top: 1px;">ai.cafreso.com</div>
              </div>
            </a>
          </div>
        {/if}
      </div>

    {:else}
      <!-- Standard tab link -->
      <a
        href={it.href}
        on:click={closeExplorePopover}
        class="flex flex-col items-center gap-[2px] py-1.5 px-0.5 font-semibold cursor-pointer transition-colors no-underline relative"
        style="
          flex: 1; min-width: 0; border: none;
          background: {active ? 'hsl(222 47% 11%)' : 'transparent'};
          color: {active ? 'white' : 'hsl(222 47% 11% / 0.6)'};
          border-radius: 11px;
          font-size: 8.5px; letter-spacing: 0em;
          overflow: hidden;
        "
      >
        <span style="position: relative; display: inline-flex; flex-shrink: 0;">
          <Icon name={it.icon} size={17} />
          {#if it.beta && !active}
            <span style="
              position: absolute; top: -3px; right: -5px;
              width: 7px; height: 7px; border-radius: 50%;
              background: hsl(260 70% 62%);
              border: 1.5px solid hsl(26 45% 98%);
            "></span>
          {/if}
        </span>
        {it.label}
      </a>
    {/if}
  {/each}
</nav>

<style>
  @keyframes popUp {
    from { opacity: 0; transform: translateX(-50%) translateY(6px) scale(0.95); }
    to   { opacity: 1; transform: translateX(-50%) translateY(0) scale(1); }
  }
  .popover-item:active {
    opacity: 0.75;
  }
</style>
