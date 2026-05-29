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
        return [...items, { slug: p.slug, name: p.name, price: p.price, qty, img: p.img }];
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

export function showToast(msg, ms = 2000) {
  toast.set(msg);
  setTimeout(() => toast.set(null), ms);
}
