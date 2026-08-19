#!/usr/bin/env python3
"""Floating/draggable "desktop window mode" defaulted to ON for every boss,
on every viewport ≥768px — not just phones.

Reported directly, twice: first "have the default mode be full page changes
instead of small windows... only allow the pop-up version be an advanced
feature in settings" (which ticket for the Terminal tab's own internal
pop-out link, believing that was the whole story), then again once it
turned out the app-wide window manager was untouched: "all things are still
popping-out as windows. I didn't want that. I want the entire screen to
switch to that page for better viewing when not on desktop."

Root cause: app.jsx's `windowsEnabled` flag defaulted to `true` globally.
`desktopMode = windowsEnabled && !isNarrowViewport` is true on ANY viewport
768px or wider — a laptop, a modest desktop browser window, not just a big
monitor — and desktopMode replaces the plain full-page `activeView` render
with a floating-window/dock system (WindowFrame panels with drag/resize/
minimize/maximize/close chrome). Nothing in Settings could turn it off; the
only escape was a small "Exit desktop mode" power icon buried in the dock,
undiscoverable and, once found, one-way (no way back in).

Fixed three ways:
  1. windowsEnabled now defaults to false — full-page by default, matching
     the plain `renderViewBody(activeView)` path, on every viewport.
  2. useStored's own write effect persists the initial value ~300ms after
     mount even with zero user interaction, so almost every browser that
     ever loaded this app already has an EXPLICIT "true" on disk — a code
     default flip alone changes nothing for a returning boss. A one-time
     migration in app/storage.jsx forces the stored value back to false
     once (sentinel-gated, so a real opt-in afterward sticks).
  3. A new Settings -> Appearance -> Advanced toggle ("Desktop window
     mode") lets a boss who wants multitasking on a large screen opt back
     in — the same opt-in-advanced-feature pattern already used for the
     Terminal tab's own pop-out link.

Run: python3 scripts/test_windows_enabled_defaults_off.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
STORAGE = (ROOT / 'app' / 'storage.jsx').read_text(encoding='utf-8')
SETTINGS = (ROOT / 'modals' / 'settings.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('windowsEnabled defaults off (full-page by default)')

    check("windowsEnabled's useStored default is false, not true",
          "useStored(k('windowsEnabled'), false)" in APP)

    check("app.jsx does not still default windowsEnabled to true",
          "useStored(k('windowsEnabled'), true)" not in APP)

    # --- one-time migration in app/storage.jsx --------------------------
    check('storage.jsx has a one-time migration forcing an already-'
          'persisted windowsEnabled back to false',
          '_migrateWindowsEnabledDefault' in STORAGE)

    check('the migration is sentinel-gated so a real opt-in afterward '
          "isn't fought back to false on the next reload",
          "STORE_KEY + ':windowsEnabledDefaultV2'" in STORAGE)

    check('the migration writes k(\'windowsEnabled\') = false, not some '
          'other key',
          re.search(r"localStorage\.setItem\(k\('windowsEnabled'\),\s*JSON\.stringify\(false\)\)", STORAGE)
          is not None)

    k_idx = STORAGE.find("const k = (n) =>")
    mig_idx = STORAGE.find('_migrateWindowsEnabledDefault')
    check("the migration IIFE is defined after `const k` (not before, "
          "which would be a TDZ crash on every page load)",
          k_idx != -1 and mig_idx != -1 and k_idx < mig_idx)

    # --- Settings toggle (opt back in) -----------------------------------
    check('SettingsModal accepts windowsEnabled/setWindowsEnabled as props',
          re.search(r"windowsEnabled\s*=\s*false,\s*setWindowsEnabled\s*=\s*\(\)\s*=>\s*\{\}", SETTINGS)
          is not None)

    check('app.jsx passes windowsEnabled/setWindowsEnabled into '
          '<SettingsModal> — declaring the props is not enough if the '
          'call site never wires them',
          'windowsEnabled={windowsEnabled} setWindowsEnabled={setWindowsEnabled}/>' in APP)

    check('a visible "Desktop window mode" switch flips windowsEnabled, '
          'not just declared and unused',
          "onClick={()=>setWindowsEnabled(v=>!v)}" in SETTINGS)

    check("the switch's on/off visual state reflects the real "
          "windowsEnabled prop",
          "pxswitch ${windowsEnabled?'on':''}" in SETTINGS)

    check('the toggle is searchable from Settings search (SETTINGS_INDEX)',
          "label:'Desktop window mode'" in SETTINGS)

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
