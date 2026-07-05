/* Svelte action: keep Tab/Shift-Tab cycling inside the node while it's
   mounted, focus the first autofocus-marked (or first focusable) element on
   mount, and restore focus to the previously-focused element on destroy.
   Used by every modal/dialog in the shell — without it Tab walks out of the
   dialog into the page behind it, which is both a WCAG failure and, for the
   signing sheet, a way to "approve" something you can no longer see.
   Usage: <div use:trapFocus role="dialog" …> */
const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function trapFocus(node) {
  const previouslyFocused =
    typeof document !== 'undefined' ? document.activeElement : null;

  function focusables() {
    return Array.from(node.querySelectorAll(FOCUSABLE)).filter(
      (el) => el.offsetParent !== null || el === document.activeElement
    );
  }

  // Initial focus: an element marked data-autofocus wins, else first focusable,
  // else the node itself (so Escape handlers still fire).
  const initial = node.querySelector('[data-autofocus]') || focusables()[0];
  if (initial) initial.focus();
  else { node.tabIndex = -1; node.focus(); }

  function onKeydown(e) {
    if (e.key !== 'Tab') return;
    const els = focusables();
    if (!els.length) { e.preventDefault(); return; }
    const first = els[0];
    const last = els[els.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault(); last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault(); first.focus();
    }
  }

  node.addEventListener('keydown', onKeydown);
  return {
    destroy() {
      node.removeEventListener('keydown', onKeydown);
      if (previouslyFocused && previouslyFocused.focus) previouslyFocused.focus();
    }
  };
}
