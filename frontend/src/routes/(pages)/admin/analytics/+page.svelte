<svelte:options runes={true} />

<script>
  /* Admin analytics — the SNS-readiness dashboard.
     Every number here is REAL and on-chain: search-network health + library
     growth from the state canister's public JSON, forum/tip activity from the
     devlog canister, and orders from the store canister (admin-gated query).
     No page-view beacons yet — that needs a state-canister upgrade; this page
     aggregates what the chain already proves. */
  import Icon from '$lib/components/Icon.svelte';
  import Button from '$lib/components/Button.svelte';
  import { networkHealth, libraryIndex } from '$lib/api/searchNetwork.js';
  import { listForumPosts, getLeaderboard, appStats, totalBurnedAll } from '$lib/api/devlog.js';
  import { listAllOrders } from '$lib/api/store.js';
  import { isAuthenticated, principalText, authStatus, login } from '$lib/stores/auth.js';
  import { isDevlogAdmin } from '$lib/data/admins.js';
  import { goldFromRaw, fmtGold } from '$lib/gold.js';

  const canAdmin = $derived(isDevlogAdmin($principalText));

  let loading = $state(false);
  let health = $state(null);
  let library = $state(null);
  let threads = $state([]);
  let leaders = $state([]);
  let orders = $state(null); // null = not loaded / not admin; [] = loaded empty
  let stats = $state(null);  // index-canister appStats(): posts/comments/burns/orders/products
  let burnedAll = $state(null); // totalBurned() — every sGLDT unit ever tipped, network-wide
  let err = $state(null);

  async function refresh() {
    loading = true;
    err = null;
    try {
      const [h, lib, th, lb, st, tb] = await Promise.all([
        networkHealth(),
        libraryIndex(),
        listForumPosts(),
        getLeaderboard(50),
        appStats(),
        totalBurnedAll()
      ]);
      health = h; library = lib; threads = th; leaders = lb; stats = st; burnedAll = tb;
      // Orders is a Result — err (e.g. 'admin only') just leaves the card empty.
      const o = await listAllOrders();
      orders = o?.ok ?? (Array.isArray(o) ? o : null);
    } catch (e) {
      err = String(e?.message || e);
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    if (canAdmin) refresh();
  });

  // Library growth — entries per day over the last 14 days, from entry
  // timestamps (nanoseconds). Bars are pure CSS; no chart lib needed.
  const growth = $derived.by(() => {
    const entries = library?.entries || [];
    const days = [];
    const now = Date.now();
    for (let i = 13; i >= 0; i--) {
      const d = new Date(now - i * 86400_000);
      days.push({ key: d.toISOString().slice(0, 10), label: `${d.getMonth() + 1}/${d.getDate()}`, count: 0 });
    }
    const byKey = Object.fromEntries(days.map((d) => [d.key, d]));
    for (const e of entries) {
      const key = new Date(Number(e.ts) / 1e6).toISOString().slice(0, 10);
      if (byKey[key]) byKey[key].count++;
    }
    const max = Math.max(1, ...days.map((d) => d.count));
    return { days, max };
  });

  const forumStats = $derived.by(() => {
    const t = threads || [];
    return {
      threads: t.length,
      comments: t.reduce((s, p) => s + (p.comments || 0), 0),
      tippedGold: t.reduce((s, p) => s + goldFromRaw(p.burned || 0), 0)
    };
  });

  const tipStats = $derived.by(() => {
    const l = leaders || [];
    return {
      tippers: l.length,
      totalGold: l.reduce((s, r) => s + goldFromRaw(r.burned || 0), 0),
      tipCount: l.reduce((s, r) => s + (r.burnCount || 0), 0)
    };
  });

  const orderStats = $derived.by(() => {
    if (!Array.isArray(orders)) return null;
    return { count: orders.length };
  });
</script>

<svelte:head><title>Analytics · Cafreso Admin</title></svelte:head>

<section class="mx-auto w-full max-w-5xl px-5 py-10">
  <header class="mb-8">
    <p class="text-sm font-medium uppercase tracking-wider text-ink-400">Admin</p>
    <h1 class="mt-2 font-serif-display text-3xl font-semibold tracking-tight text-foreground">
      Analytics
    </h1>
    <p class="mt-3 max-w-2xl text-[15px] leading-7 text-ink-500">
      Real on-chain traction — the numbers that decide when the SNS conversation gets serious.
      All figures are read live from the canisters; nothing here is estimated.
    </p>
  </header>

  {#if !$isAuthenticated}
    <div class="rounded-2xl border border-ink-200/60 p-8 text-center dark:border-ink-700/70">
      <p class="mb-4 text-sm text-ink-500">Sign in with Internet Identity to view analytics.</p>
      <Button on:click={login} disabled={$authStatus === 'logging-in'}>
        <Icon name="fingerprint" size={15} /> Sign in
      </Button>
    </div>
  {:else if !canAdmin}
    <div class="rounded-2xl border border-ink-200/60 p-8 text-center text-sm text-ink-500 dark:border-ink-700/70">
      This dashboard is admin-only. Your principal isn't on the admin allowlist.
    </div>
  {:else}
    <div class="mb-4 flex items-center justify-between">
      <span class="text-xs text-ink-400">{loading ? 'Refreshing…' : 'Live from mainnet'}</span>
      <Button variant="outline" size="sm" on:click={refresh} disabled={loading}>Refresh</Button>
    </div>

    {#if err}
      <div class="mb-4 rounded-xl border border-red-300/50 bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">{err}</div>
    {/if}

    <!-- Headline stats -->
    <div class="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <div class="rounded-2xl border border-ink-200/60 p-4 dark:border-ink-700/70">
        <div class="text-xs uppercase tracking-wide text-ink-400">Library entries</div>
        <div class="mt-1 text-2xl font-semibold text-foreground">{library?.count ?? '—'}</div>
        <div class="mt-1 text-xs text-ink-400">{health?.answeredToday ?? 0} answered today</div>
      </div>
      <div class="rounded-2xl border border-ink-200/60 p-4 dark:border-ink-700/70">
        <div class="text-xs uppercase tracking-wide text-ink-400">Search workers</div>
        <div class="mt-1 text-2xl font-semibold text-foreground">{health?.workers ?? '—'}</div>
        <div class="mt-1 text-xs text-ink-400">{health?.activeWorkers ?? 0} active · {health?.pending ?? 0} pending jobs</div>
      </div>
      <div class="rounded-2xl border border-ink-200/60 p-4 dark:border-ink-700/70">
        <div class="text-xs uppercase tracking-wide text-ink-400">Gold tipped</div>
        <div class="mt-1 text-2xl font-semibold text-foreground">{fmtGold(tipStats.totalGold)} <span class="text-sm font-normal text-ink-400">sGLDT</span></div>
        <div class="mt-1 text-xs text-ink-400">{tipStats.tipCount} tips · {tipStats.tippers} tippers</div>
      </div>
      <div class="rounded-2xl border border-ink-200/60 p-4 dark:border-ink-700/70">
        <div class="text-xs uppercase tracking-wide text-ink-400">Shop orders</div>
        <div class="mt-1 text-2xl font-semibold text-foreground">{orderStats ? orderStats.count : '—'}</div>
        <div class="mt-1 text-xs text-ink-400">{orderStats ? 'all-time, on-chain' : 'admin query unavailable'}</div>
      </div>
    </div>

    <!-- Index-canister totals — appStats()/totalBurned(), previously unqueried -->
    <div class="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
      <div class="rounded-2xl border border-ink-200/60 p-4 dark:border-ink-700/70">
        <div class="text-xs uppercase tracking-wide text-ink-400">Posts on-chain</div>
        <div class="mt-1 text-2xl font-semibold text-foreground">{stats?.posts ?? '—'}</div>
        <div class="mt-1 text-xs text-ink-400">dev log + forum threads</div>
      </div>
      <div class="rounded-2xl border border-ink-200/60 p-4 dark:border-ink-700/70">
        <div class="text-xs uppercase tracking-wide text-ink-400">Comments on-chain</div>
        <div class="mt-1 text-2xl font-semibold text-foreground">{stats?.comments ?? '—'}</div>
        <div class="mt-1 text-xs text-ink-400">append-only record</div>
      </div>
      <div class="rounded-2xl border border-ink-200/60 p-4 dark:border-ink-700/70">
        <div class="text-xs uppercase tracking-wide text-ink-400">Tip events</div>
        <div class="mt-1 text-2xl font-semibold text-foreground">{stats?.burns ?? '—'}</div>
        <div class="mt-1 text-xs text-ink-400">{burnedAll != null ? `${fmtGold(goldFromRaw(burnedAll))} sGLDT lifetime` : 'lifetime total'}</div>
      </div>
      <div class="rounded-2xl border border-ink-200/60 p-4 dark:border-ink-700/70">
        <div class="text-xs uppercase tracking-wide text-ink-400">Shop catalog</div>
        <div class="mt-1 text-2xl font-semibold text-foreground">{stats?.products ?? '—'}</div>
        <div class="mt-1 text-xs text-ink-400">{stats ? `${stats.orders} orders recorded` : 'products live'}</div>
      </div>
    </div>

    <!-- Library growth chart -->
    <div class="mt-6 rounded-2xl border border-ink-200/60 p-5 dark:border-ink-700/70">
      <div class="mb-4 flex items-baseline justify-between">
        <h2 class="font-medium text-foreground">Library growth — last 14 days</h2>
        <span class="text-xs text-ink-400">new on-chain entries per day</span>
      </div>
      <div class="flex h-32 items-end gap-1.5">
        {#each growth.days as d}
          <div class="group relative flex h-full flex-1 flex-col items-center justify-end">
            <div
              class="w-full rounded-t bg-brand-500/70 transition-colors group-hover:bg-brand-500"
              style={`height: ${(d.count / growth.max) * 100}%; min-height: ${d.count > 0 ? 4 : 1}px;`}
              title={`${d.key}: ${d.count}`}
            ></div>
            <span class="mt-1 hidden text-[9px] text-ink-400 sm:block">{d.label}</span>
          </div>
        {/each}
      </div>
    </div>

    <!-- Community -->
    <div class="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div class="rounded-2xl border border-ink-200/60 p-5 dark:border-ink-700/70">
        <h2 class="font-medium text-foreground">Forums</h2>
        <dl class="mt-3 space-y-2 text-sm">
          <div class="flex justify-between"><dt class="text-ink-400">Threads</dt><dd class="font-medium text-foreground">{forumStats.threads}</dd></div>
          <div class="flex justify-between"><dt class="text-ink-400">Comments</dt><dd class="font-medium text-foreground">{forumStats.comments}</dd></div>
          <div class="flex justify-between"><dt class="text-ink-400">Gold tipped on threads</dt><dd class="font-medium text-foreground">{fmtGold(forumStats.tippedGold)} sGLDT</dd></div>
        </dl>
      </div>
      <div class="rounded-2xl border border-ink-200/60 p-5 dark:border-ink-700/70">
        <h2 class="font-medium text-foreground">Top tippers</h2>
        {#if leaders.length === 0}
          <p class="mt-3 text-sm text-ink-400">No gold tipped yet — the board restarts in sGLDT.</p>
        {:else}
          <ol class="mt-3 space-y-1.5 text-sm">
            {#each leaders.slice(0, 5) as r, i}
              <li class="flex justify-between gap-3">
                <span class="truncate font-mono text-xs text-ink-500">#{i + 1} {r.principal.slice(0, 12)}…</span>
                <span class="shrink-0 font-medium text-foreground">{fmtGold(goldFromRaw(r.burned))} sGLDT</span>
              </li>
            {/each}
          </ol>
        {/if}
      </div>
    </div>

    <p class="mt-6 text-xs leading-5 text-ink-400">
      Not yet tracked: page views, unique visitors, retention. Those need a lightweight
      hit-counter on the state canister (planned) — everything above is already provable on-chain.
    </p>
  {/if}
</section>
