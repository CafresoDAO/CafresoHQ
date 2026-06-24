<svelte:options runes={true} />

<script>
  import Icon from '$lib/components/Icon.svelte';
  import Button from '$lib/components/Button.svelte';
  import {
    listProducts,
    upsertProduct,
    deleteProduct,
    listAllOrders,
    updateOrderStatus,
    getTreasury,
    setTreasury
  } from '$lib/api/store.js';
  import { isAuthenticated, principalText, authStatus, login } from '$lib/stores/auth.js';
  import { isDevlogAdmin } from '$lib/data/admins.js';

  // `isDevlogAdmin` is reused as a UI-gate allowlist — the canister still
  // enforces admin on every write. If a principal is on the canister but
  // not on this list they can still call via direct dfx; the form simply
  // won't show for them in the dapp UI.
  const canAdmin = $derived(isDevlogAdmin($principalText));

  let products = $state([]);
  let orders = $state([]);
  let loading = $state(false);
  let err = $state(null);
  let msg = $state(null);
  let treasury = $state(null);
  let treasuryDraft = $state('');

  // Edit drawer state
  let editing = $state(null); // null or product object
  let saving = $state(false);
  let confirmingDelete = $state(null); // slug being deleted

  const CATS = ['coffee', 'accessories', 'dao'];
  const IMAGES = [
    { key: 'roaster', label: 'Roaster illustration' },
    { key: 'placeholder', label: 'Not-yet-available stamp' }
  ];

  async function refresh() {
    loading = true;
    err = null;
    try {
      products = await listProducts();
      if (canAdmin) {
        const res = await listAllOrders();
        if (res.ok) orders = res.ok;
        else orders = [];
        treasury = await getTreasury();
      }
    } catch (e) {
      err = String(e?.message || e);
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    if ($isAuthenticated && canAdmin) refresh();
  });

  function startNew() {
    editing = {
      slug: '',
      title: '',
      excerpt: '',
      cat: 'coffee',
      img: 'roaster',
      price: 0,
      priceCentsUSD: 0,
      soon: false,
      stock: null
    };
  }

  function startEdit(p) {
    editing = { ...p };
  }

  function cancelEdit() {
    editing = null;
  }

  async function saveEdit() {
    if (!editing) return;
    saving = true;
    err = null;
    msg = null;
    const res = await upsertProduct(editing);
    saving = false;
    if (res.err) {
      err = res.err;
      return;
    }
    msg = `Saved "${res.ok.title}"`;
    editing = null;
    await refresh();
    setTimeout(() => (msg = null), 2500);
  }

  async function confirmDelete(slug) {
    const res = await deleteProduct(slug);
    confirmingDelete = null;
    if (res.err) {
      err = res.err;
      return;
    }
    msg = `Deleted "${slug}"`;
    await refresh();
    setTimeout(() => (msg = null), 2500);
  }

  async function changeOrderStatus(order, status, note = '') {
    const res = await updateOrderStatus(order.id, status, note);
    if (res.err) {
      err = res.err;
      return;
    }
    await refresh();
  }

  async function saveTreasury() {
    if (!treasuryDraft) return;
    const res = await setTreasury(treasuryDraft);
    if (res.err) {
      err = res.err;
      return;
    }
    msg = 'Treasury updated';
    treasury = treasuryDraft;
    treasuryDraft = '';
    setTimeout(() => (msg = null), 2500);
  }

  function fmtTime(ms) {
    if (!ms) return '—';
    return new Date(ms).toLocaleString();
  }

  const ORDER_STATUSES = ['pending', 'paid', 'shipped', 'delivered', 'refunded', 'cancelled'];
  const STATUS_COLOR = {
    pending: 'hsl(42 80% 92%)',
    paid: 'hsl(142 50% 94%)',
    shipped: 'hsl(215 40% 96%)',
    delivered: 'hsl(112 45% 92%)',
    refunded: 'hsl(26 30% 92%)',
    cancelled: 'hsl(0 70% 96%)'
  };
</script>

<svelte:head><title>Admin · Store · Cafreso</title></svelte:head>

<section class="mx-auto px-4 sm:px-[18px] pt-6 sm:pt-8 pb-24" style="max-width: 1100px;">
  <div class="flex items-center gap-2 text-[13px] font-medium mb-3" style="color: hsl(24 48% 28%);">
    <Icon name="storefront" size={16} /> Admin tools
  </div>
  <h1 class="font-bold leading-tight mb-2" style="font-size: clamp(26px, 5vw, 36px); color: hsl(222 47% 11%);">
    Store
  </h1>
  <p class="text-[14.5px] leading-[1.55] mb-6 sm:mb-8 max-w-[620px]" style="color: hsl(215 16% 47%);">
    Manage the product catalog, review orders, and configure the $nanas
    treasury principal. All writes are signed by your Internet Identity and
    rejected by the canister for non-admins.
  </p>

  {#if !$isAuthenticated}
    <div
      class="rounded-[14px] p-6 sm:p-8 text-center"
      style="background: hsl(26 40% 98%); border: 1px solid hsl(26 30% 88%);"
    >
      <Icon name="fingerprint" size={28} style="color: hsl(32 56% 35%);" />
      <h2 class="text-[18px] font-bold mt-3 mb-2" style="color: hsl(222 47% 11%);">Sign in to manage the store</h2>
      <Button on:click={login} disabled={$authStatus === 'logging-in'}>
        <Icon name="fingerprint" size={15} /> Sign in
      </Button>
    </div>
  {:else if !canAdmin}
    <div
      class="rounded-[14px] p-5 sm:p-6"
      style="background: hsl(0 70% 96%); border: 1px solid hsl(0 70% 80%); color: hsl(0 70% 30%);"
    >
      <div class="flex items-center gap-2 font-semibold mb-1.5">
        <Icon name="lock" size={16} /> Not on the admin allowlist
      </div>
      <p class="text-[13.5px] leading-[1.55]" style="color: hsl(0 65% 30%);">
        Ask an existing admin to add this principal via the canister's <code>addAdmin</code> method.
      </p>
      <code class="block mt-2 text-[11.5px] font-mono break-all p-2 rounded-[8px]"
        style="background: hsl(0 0% 100%); color: hsl(222 47% 11%); border: 1px solid hsl(0 70% 80%);"
      >{$principalText}</code>
    </div>
  {:else}
    {#if err}
      <div class="rounded-[10px] px-3 py-2 text-[13px] mb-4"
        style="background: hsl(0 70% 96%); color: hsl(0 70% 30%); border: 1px solid hsl(0 70% 85%);"
      >
        <Icon name="warning" size={13} /> {err}
      </div>
    {/if}
    {#if msg}
      <div class="rounded-[10px] px-3 py-2 text-[13px] mb-4 inline-flex items-center gap-2"
        style="background: hsl(142 50% 94%); color: hsl(142 70% 25%); border: 1px solid hsl(142 45% 70%);"
      >
        <Icon name="check-circle" size={13} /> {msg}
      </div>
    {/if}

    {#if treasury == null}
      <a
        href="#treasury"
        class="flex items-center gap-2 rounded-[10px] px-3 py-2.5 text-[13px] mb-4 no-underline"
        style="background: hsl(42 80% 92%); color: hsl(32 56% 25%); border: 1px solid hsl(42 70% 70%);"
      >
        <Icon name="warning" size={14} />
        <span>No treasury principal is set — $nanas checkouts will fail until you configure one below.</span>
      </a>
    {/if}

    <!-- Treasury -->
    <div
      id="treasury"
      class="rounded-[14px] p-4 sm:p-5 mb-6"
      style="background: hsl(26 40% 98%); border: 1px solid hsl(26 30% 88%);"
    >
      <div class="flex items-center gap-2 mb-2">
        <Icon name="vault" size={16} style="color: hsl(24 48% 28%);" />
        <h2 class="text-[14px] sm:text-[15px] font-bold" style="color: hsl(222 47% 11%);">Treasury principal</h2>
      </div>
      {#if treasury}
        <div class="text-[11.5px] font-mono break-all mb-3 p-2 rounded-[8px]"
          style="background: white; border: 1px solid hsl(26 30% 85%); color: hsl(222 47% 11%);"
        >
          {treasury}
        </div>
      {:else}
        <p class="text-[12.5px] italic mb-3" style="color: hsl(215 16% 47%);">
          No treasury set yet. Checkouts will fail until you configure one.
        </p>
      {/if}
      <label for="treasury-principal" class="block text-[11.5px] font-semibold uppercase mb-1" style="color: hsl(215 16% 47%);">Treasury principal</label>
      <div class="flex flex-col sm:flex-row gap-2">
        <input
          id="treasury-principal"
          bind:value={treasuryDraft}
          placeholder="<principal> (e.g. xip3r-…-mae)"
          class="flex-1 text-[13px] font-mono bg-white rounded-[10px] px-3 py-2 outline-none min-w-0"
          style="border: 1px solid hsl(26 30% 85%);"
        />
        <Button on:click={saveTreasury} disabled={!treasuryDraft}>
          <Icon name="check" size={14} /> Update treasury
        </Button>
      </div>
    </div>

    <!-- Products -->
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <Icon name="package" size={16} style="color: hsl(24 48% 28%);" />
        <h2 class="text-[15px] sm:text-[16px] font-bold" style="color: hsl(222 47% 11%);">Products ({products.length})</h2>
      </div>
      <Button size="sm" on:click={startNew}>
        <Icon name="plus" size={13} /> New product
      </Button>
    </div>
    <div
      class="rounded-[14px] overflow-hidden mb-8"
      style="background: hsl(26 40% 98%); border: 1px solid hsl(26 30% 88%);"
    >
      {#if products.length === 0}
        <div class="px-4 py-6 text-center text-[13px]" style="color: hsl(215 16% 47%);">
          {loading ? 'Loading…' : 'No products yet. Create the first one.'}
        </div>
      {:else}
        {#each products as p, i (p.slug)}
          <div
            class="grid grid-cols-[1fr_auto] sm:grid-cols-[1.6fr_120px_100px_90px_auto] gap-3 px-4 sm:px-5 py-3.5 sm:py-4 items-center text-[13.5px]"
            style="{i > 0 ? 'border-top: 1px solid hsl(26 30% 92%);' : ''}"
          >
            <div class="min-w-0">
              <div class="font-semibold truncate" style="color: hsl(222 47% 11%);">{p.title || p.name}</div>
              <div class="font-mono text-[10.5px] truncate" style="color: hsl(215 16% 47%);">/{p.slug}</div>
            </div>
            <div class="hidden sm:block text-[11.5px] capitalize" style="color: hsl(215 16% 47%);">{p.cat || p.tag}</div>
            <div class="hidden sm:block tabular-nums text-right">{Number(p.price).toLocaleString()} nanas</div>
            <div class="hidden sm:block text-right text-[11.5px]" style="color: hsl(215 16% 47%);">
              {p.soon ? 'soon' : p.stock == null ? '∞' : `${p.stock} left`}
            </div>
            <div class="flex gap-1.5">
              <button
                type="button"
                on:click={() => startEdit(p)}
                class="h-8 px-2.5 rounded-[8px] text-[11.5px] font-medium cursor-pointer inline-flex items-center gap-1 bg-transparent border"
                style="border-color: hsl(26 30% 85%); color: hsl(222 47% 11%);"
              >
                <Icon name="pencil-simple" size={12} /> Edit
              </button>
              {#if confirmingDelete === p.slug}
                <button
                  type="button"
                  on:click={() => confirmDelete(p.slug)}
                  class="h-8 px-2.5 rounded-[8px] text-[11.5px] font-semibold cursor-pointer border-none"
                  style="background: hsl(0 72% 42%); color: white;"
                >
                  Confirm
                </button>
                <button
                  type="button"
                  on:click={() => (confirmingDelete = null)}
                  class="h-8 px-2 rounded-[8px] text-[11.5px] cursor-pointer bg-transparent border"
                  style="border-color: hsl(26 30% 85%); color: hsl(215 16% 47%);"
                >
                  ×
                </button>
              {:else}
                <button
                  type="button"
                  on:click={() => (confirmingDelete = p.slug)}
                  class="h-8 w-8 rounded-[8px] cursor-pointer inline-flex items-center justify-center bg-transparent border"
                  style="border-color: hsl(0 70% 80%); color: hsl(0 72% 42%);"
                  aria-label="Delete"
                >
                  <Icon name="trash" size={13} />
                </button>
              {/if}
            </div>
          </div>
        {/each}
      {/if}
    </div>

    <!-- Orders -->
    <div class="flex items-center gap-2 mb-3">
      <Icon name="receipt" size={16} style="color: hsl(24 48% 28%);" />
      <h2 class="text-[15px] sm:text-[16px] font-bold" style="color: hsl(222 47% 11%);">Orders ({orders.length})</h2>
    </div>
    <div
      class="rounded-[14px] overflow-hidden"
      style="background: hsl(26 40% 98%); border: 1px solid hsl(26 30% 88%);"
    >
      {#if orders.length === 0}
        <div class="px-4 py-6 text-center text-[13px]" style="color: hsl(215 16% 47%);">
          No orders yet.
        </div>
      {:else}
        {#each orders as o, i (o.id)}
          <div class="px-4 sm:px-5 py-4 text-[13px]" style="{i > 0 ? 'border-top: 1px solid hsl(26 30% 92%);' : ''}">
            <div class="flex items-center justify-between gap-3 flex-wrap">
              <div class="min-w-0">
                <div class="font-semibold" style="color: hsl(222 47% 11%);">
                  Order #{o.id} · {o.totalNanas.toLocaleString()} nanas
                </div>
                <div class="font-mono text-[10.5px] truncate" style="color: hsl(215 16% 47%);">
                  {o.buyer.slice(0, 5)}…{o.buyer.slice(-3)} · {fmtTime(o.createdAt)}
                </div>
              </div>
              <span
                class="inline-flex items-center text-[11px] font-semibold uppercase px-2 py-1 rounded-full"
                style="background: {STATUS_COLOR[o.status] || 'hsl(26 30% 92%)'}; color: hsl(222 47% 11%);"
              >
                {o.status}
              </span>
            </div>
            <div class="mt-2 text-[12px]" style="color: hsl(215 25% 25%);">
              {o.items.map((it) => `${it.qty}× ${it.slug}`).join(' · ')}
            </div>
            <div class="mt-1 text-[11.5px]" style="color: hsl(215 16% 47%);">
              Ship to: {o.shipping.name} · {o.shipping.street}, {o.shipping.city} {o.shipping.postal}
            </div>
            {#if o.paidBlock != null}
              <div class="mt-1 text-[11.5px] font-mono" style="color: hsl(215 16% 47%);">
                $nanas tx block #{o.paidBlock}
              </div>
            {/if}
            <div class="mt-2.5 flex flex-wrap gap-1.5">
              {#each ORDER_STATUSES.filter((s) => s !== o.status) as next}
                <button
                  type="button"
                  on:click={() => changeOrderStatus(o, next)}
                  class="h-7 px-2 rounded-[7px] text-[10.5px] font-medium cursor-pointer bg-transparent border uppercase"
                  style="border-color: hsl(26 30% 85%); color: hsl(222 47% 11%);"
                >
                  → {next}
                </button>
              {/each}
            </div>
          </div>
        {/each}
      {/if}
    </div>
  {/if}
</section>

<!-- Edit drawer -->
{#if editing}
  <div
    class="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
    style="background: hsl(222 47% 11% / 0.5);"
    on:click={cancelEdit}
  >
    <div
      class="w-full sm:max-w-[520px] rounded-t-[18px] sm:rounded-[16px] p-5 sm:p-6 max-h-[90vh] overflow-y-auto"
      style="background: white; border-top: 1px solid hsl(26 30% 85%);"
      on:click|stopPropagation
    >
      <div class="flex items-center justify-between mb-4">
        <h3 class="font-bold text-[16px]" style="color: hsl(222 47% 11%);">
          {editing.createdAtNs ? 'Edit product' : 'New product'}
        </h3>
        <button
          type="button"
          on:click={cancelEdit}
          class="w-8 h-8 rounded-full flex items-center justify-center cursor-pointer bg-transparent border-none"
          aria-label="Close"
        >
          <Icon name="x" size={16} />
        </button>
      </div>

      <div class="space-y-3">
        <div>
          <label for="product-title" class="block text-[11.5px] font-semibold uppercase mb-1" style="color: hsl(215 16% 47%);">Title</label>
          <input id="product-title" bind:value={editing.title} required class="w-full text-[14px] bg-white rounded-[10px] px-3 py-2 outline-none" style="border: 1px solid hsl(26 30% 85%);" />
        </div>
        <div>
          <label for="product-slug" class="block text-[11.5px] font-semibold uppercase mb-1" style="color: hsl(215 16% 47%);">Slug</label>
          <input id="product-slug" bind:value={editing.slug} required pattern="[a-z0-9-]+" placeholder="url-safe-slug" class="w-full text-[13px] font-mono bg-white rounded-[10px] px-3 py-2 outline-none" style="border: 1px solid hsl(26 30% 85%);" />
          <p class="text-[10.5px] mt-1" style="color: hsl(215 16% 47%);">Lowercase letters, numbers, and hyphens only.</p>
        </div>
        <div>
          <label class="block text-[11.5px] font-semibold uppercase mb-1" style="color: hsl(215 16% 47%);">Excerpt</label>
          <textarea bind:value={editing.excerpt} rows="2" class="w-full text-[13.5px] bg-white rounded-[10px] px-3 py-2 outline-none resize-none" style="border: 1px solid hsl(26 30% 85%);"></textarea>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-[11.5px] font-semibold uppercase mb-1" style="color: hsl(215 16% 47%);">Category</label>
            <select bind:value={editing.cat} class="w-full text-[13.5px] bg-white rounded-[10px] px-2.5 py-2 outline-none" style="border: 1px solid hsl(26 30% 85%);">
              {#each CATS as c}<option value={c}>{c}</option>{/each}
            </select>
          </div>
          <div>
            <label class="block text-[11.5px] font-semibold uppercase mb-1" style="color: hsl(215 16% 47%);">Image</label>
            <select bind:value={editing.img} class="w-full text-[13.5px] bg-white rounded-[10px] px-2.5 py-2 outline-none" style="border: 1px solid hsl(26 30% 85%);">
              {#each IMAGES as i}<option value={i.key}>{i.label}</option>{/each}
            </select>
          </div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-[11.5px] font-semibold uppercase mb-1" style="color: hsl(215 16% 47%);">Price · $nanas</label>
            <input type="number" min="0" bind:value={editing.price} class="w-full text-[13.5px] tabular-nums bg-white rounded-[10px] px-3 py-2 outline-none" style="border: 1px solid hsl(26 30% 85%);" />
          </div>
          <div>
            <label class="block text-[11.5px] font-semibold uppercase mb-1" style="color: hsl(215 16% 47%);">USD cents (display)</label>
            <input type="number" min="0" bind:value={editing.priceCentsUSD} class="w-full text-[13.5px] tabular-nums bg-white rounded-[10px] px-3 py-2 outline-none" style="border: 1px solid hsl(26 30% 85%);" />
          </div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <label class="inline-flex items-center gap-2 text-[13px]" style="color: hsl(222 47% 11%);">
            <input type="checkbox" bind:checked={editing.soon} /> Coming soon
          </label>
          <div>
            <label class="block text-[11.5px] font-semibold uppercase mb-1" style="color: hsl(215 16% 47%);">Stock (blank = ∞)</label>
            <input
              type="number"
              min="0"
              bind:value={editing.stock}
              placeholder="∞"
              class="w-full text-[13.5px] tabular-nums bg-white rounded-[10px] px-3 py-2 outline-none"
              style="border: 1px solid hsl(26 30% 85%);"
            />
          </div>
        </div>
      </div>

      <div class="flex flex-col sm:flex-row gap-2 mt-5">
        <Button on:click={saveEdit} disabled={saving} class="flex-1">
          {#if saving}<Icon name="spinner-gap" size={14} /> Saving…{:else}<Icon name="check" size={14} /> Save{/if}
        </Button>
        <Button variant="ghost" on:click={cancelEdit} class="flex-1">Cancel</Button>
      </div>
    </div>
  </div>
{/if}
