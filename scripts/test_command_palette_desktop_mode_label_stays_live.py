#!/usr/bin/env python3
"""The Command Palette's "Enable/Exit desktop (window) mode" entry went
stale the moment desktop mode was toggled from anywhere OTHER than the
palette itself — e.g. Settings' "Desktop window mode" switch.

`AppGlobalCommands` (app/commands.jsx) builds its `cmds` array fresh on
every render, closing over live `windowsEnabled`/`setWindowsEnabled`/
`onOpenWindow` props — but registers that array with `useCommands(cmds,
[...])`, whose deps array gates when the palette's registered command
list actually gets replaced (ui/feedback.jsx's `useCommands` only
re-registers when a dep changes reference). `windowsEnabled`,
`setWindowsEnabled`, and `onOpenWindow` were used inside `cmds` but never
listed in that deps array, so toggling desktop mode from Settings didn't
trigger a re-registration — the palette kept showing whichever label
("Enable..."/"Exit...") was captured the last time some OTHER listed dep
(activeView, theme, etc.) happened to change.

Concretely: with the palette showing "Enable desktop (window) mode" and
the boss toggling it ON via Settings instead, reopening the palette
(without touching any listed dep) still read "Enable desktop (window)
mode" — clicking it would then have turned desktop mode back OFF,
contradicting the label the boss just read. Found by a background hunt
agent scanning the Terminal pane and Command Palette (this session's
next-least-scrutinized areas), confirmed by checking `useCommands`'s
re-registration gate against the actual deps list.

Fix: added `windowsEnabled, setWindowsEnabled, onOpenWindow` to the
`useCommands` deps array, so a real toggle of any of them forces the
palette to re-register with the current label/state.

Verified live in the browser: with the palette showing "Enable desktop
(window) mode", toggled Desktop window mode ON via Settings (not the
palette), then reopened the palette with ⌘K — it now read "Exit desktop
(window) mode", matching the real state. Toggled back off through the
palette itself to restore the app's starting state.

Run: python3 scripts/test_command_palette_desktop_mode_label_stays_live.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMANDS = ROOT / 'app' / 'commands.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("Command Palette's desktop-mode entry stays live across external toggles")

    src = COMMANDS.read_text(encoding='utf-8')

    m = re.search(r"useCommands\(cmds, \[(.*?)\]\);", src, re.S)
    check('useCommands(cmds, [...]) registration call is still present',
          m is not None, 'app/commands.jsx: useCommands call not found')
    deps = m.group(1) if m else ''

    check('the deps array includes windowsEnabled (the toggle whose '
          "label — Enable/Exit desktop mode — the palette renders)",
          re.search(r"\bwindowsEnabled\b", deps) is not None, deps)
    check('...and setWindowsEnabled (the command\'s own run() closes '
          "over it via `setWindowsEnabled && setWindowsEnabled(...)`, "
          'so a stale reference could also call a stale setter)',
          re.search(r"\bsetWindowsEnabled\b", deps) is not None, deps)
    check('...and onOpenWindow (the "Open in window: X" commands section '
          'closes over it the same way)',
          re.search(r"\bonOpenWindow\b", deps) is not None, deps)

    check('the tog.desktop command itself still reads windowsEnabled '
          'for its label and calls setWindowsEnabled in run() (the '
          'upstream piece this fix depends on)',
          re.search(
              r"label:\s*windowsEnabled \? 'Exit desktop \(window\) mode' : "
              r"'Enable desktop \(window\) mode'", src) is not None
          and "run: () => setWindowsEnabled && setWindowsEnabled(v => !v)" in src,
          'app/commands.jsx: tog.desktop command changed shape')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
