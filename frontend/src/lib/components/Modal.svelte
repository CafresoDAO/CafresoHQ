<script>
  /* The shared overlay primitive: backdrop + dismiss semantics + focus trap +
     Escape + dialog roles, in one place.

     Six overlays each hand-rolled this and drifted apart — CartDrawer had no
     dialog role, no focus trap and no Escape at all; BBWaitlistModal had no
     trap and no Escape; SendTokenModal put role="dialog" on the *backdrop*
     rather than the panel. Only ApprovalSheet got every axis right, so its
     behavior is what this component encodes.

     Deliberate choices inherited from ApprovalSheet:
      · Backdrop dismisses on MOUSEDOWN, not click, and only when the press
        starts on the backdrop itself — a drag that begins inside the panel and
        releases outside must never dismiss (it's how you lose a filled-in form).
      · Escape calls stopPropagation so a modal over another surface doesn't
        also close what's behind it.
      · trapFocus focuses [data-autofocus] first, else the first focusable, and
        restores focus to the invoker on destroy. Mark the SAFE control (Cancel)
        with data-autofocus in destructive dialogs — a reflexive Enter must not
        confirm.

     Content goes in the default slot; this owns only the chrome. Callers keep
     their own panel styling via panelClass/panelStyle.

     Usage:
       <Modal open={isOpen} on:close={() => (isOpen = false)}
              ariaLabel="Cart" placement="drawer-right" z={20}>
         …panel content…
       </Modal>
  */
  import { createEventDispatcher } from 'svelte';
  import { trapFocus } from '$lib/actions/trapFocus.js';

  export let open = false;
  /** Element id of the panel's heading. Prefer this over ariaLabel when the
      dialog has a visible title. */
  export let labelledby = null;
  export let ariaLabel = null;
  /** 'center'       — panel centred in the scrim (most dialogs)
      'drawer-right' — full-height panel pinned to the right edge (CartDrawer)
      'pinned'       — caller positions the panel itself via panelStyle; the
                       primitive adds no layout (AISearchModal's bottom sheet,
                       which anchors above the mobile tab bar with env() insets) */
  export let placement = 'center';
  /** Stacking tier. See Z below — pass a token name, not a raw number. */
  export let z = 'modal';
  /** false pins the dialog open (in-flight work that must not be interrupted). */
  export let dismissible = true;
  export let panelClass = '';
  export let panelStyle = '';
  /** Extra classes for the backdrop. */
  export let backdropClass = '';
  /** Inline scrim override — some overlays are branded (BBWaitlistModal's navy)
      rather than the default coffee scrim, so the tint stays caller-owned. */
  export let backdropStyle = '';

  const dispatch = createEventDispatcher();

  /* One ladder instead of the old ad-hoc 15/20/50/60/70 spread. `sheet` sits
     top because the signing sheet may legitimately open over any other. */
  const Z = { drawer: 40, modal: 50, sheet: 70 };
  $: zIndex = typeof z === 'number' ? z : (Z[z] ?? Z.modal);

  function close() {
    if (dismissible) dispatch('close');
  }
  function onKeydown(e) {
    if (e.key === 'Escape') {
      e.stopPropagation();
      close();
    }
  }
  function onBackdrop(e) {
    if (e.target === e.currentTarget) close();
  }
</script>

{#if open}
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <!-- The backdrop is intentionally NOT a button: it carries no accessible
       action of its own (Escape and the panel's own close control are the
       real affordances), so exposing it to AT would just add noise. -->
  <div
    class="fixed inset-0 {placement === 'center' ? 'grid place-items-center p-4' : ''} {backdropStyle ? '' : 'bg-ink-900/60 backdrop-blur-sm'} {backdropClass}"
    style="z-index: {zIndex}; {backdropStyle}"
    on:mousedown={onBackdrop}
    on:keydown={onKeydown}
  >
    <div
      use:trapFocus
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelledby}
      aria-label={labelledby ? null : ariaLabel}
      class="{placement === 'drawer-right' ? 'fixed right-0 top-0 bottom-0 flex flex-col' : ''} {panelClass}"
      style={panelStyle}
    >
      <slot />
    </div>
  </div>
{/if}
