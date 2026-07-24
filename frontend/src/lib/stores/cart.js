import { writable, derived } from 'svelte/store';

function createCart() {
  const { subscribe, set, update } = writable([]);
  return {
    subscribe,
    add(p, qty = 1) {
      update((items) => {
        const ex = items.findIndex((i) => i.slug === p.slug);
        if (ex >= 0) {
          const nx = [...items];
          nx[ex] = { ...nx[ex], qty: nx[ex].qty + qty };
          return nx;
        }
        return [...items, { slug: p.slug, name: p.name, price: p.price, cents: p.priceCentsUSD, qty, img: p.img }];
      });
    },
    remove(ix) {
      update((items) => items.filter((_, i) => i !== ix));
    },
    clear() {
      set([]);
    }
  };
}

export const cart = createCart();
export const cartOpen = writable(false);
export const toast = writable(null);

export const cartCount = derived(cart, ($cart) => $cart.reduce((s, i) => s + i.qty, 0));
export const cartTotal = derived(cart, ($cart) => $cart.reduce((s, i) => s + i.price * i.qty, 0));
// USD cents — the pricing anchor since the gold (sGLDT) switch. Falls back to
// the legacy fixed nanas→cents rate (price × 0.15) for items added pre-switch.
export const cartTotalCents = derived(cart, ($cart) =>
  $cart.reduce((s, i) => s + (i.cents ?? Math.round(i.price * 0.15)) * i.qty, 0)
);

export function showToast(msg, ms = 2000) {
  toast.set(msg);
  setTimeout(() => toast.set(null), ms);
}
