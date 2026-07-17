import { writable } from 'svelte/store';

/* Which mobile navigation overlay is open, if any.
   'drawer'  — PageHeader's hamburger slide-out
   'explore' — MobileNav's bottom-bar Explore popover
   null      — none

   The marketing layout mounts BOTH PageHeader and MobileNav, and each used to
   own a private boolean. Nothing coordinated them, so the hamburger drawer and
   the Explore popover could sit open simultaneously, stacked in whatever order
   their z-index tiers happened to land in. Routing both through one store makes
   them mutually exclusive by construction: opening either closes the other.

   Note this only fixes the *stacking*. The two surfaces still expose overlapping
   destinations (Projects/Library/Dev Log/Forums are reachable from both) —
   retiring one of them is a product decision, not a refactor. */
export const mobileOverlay = writable(null);

/** Open `which`, closing whatever else was open. Passing the already-open id
    toggles it shut, so a control can call this on every press. */
export function toggleMobileOverlay(which) {
  mobileOverlay.update((current) => (current === which ? null : which));
}

export function closeMobileOverlay() {
  mobileOverlay.set(null);
}
