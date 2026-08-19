#!/usr/bin/env python3
"""Terminal tabs opened into a native OS popup window by default, and on
stock macOS that popup didn't even work.

Two bugs, found together:

1. views/terminal.jsx's TerminalSession defaulted a brand-new tab's mode to
   'spawn' (the PTY/native-window path), not 'chat'. When the backend PTY
   bridge isn't available (ptySupported=false) — the common case, this is a
   HTTP-request round-trip, not a real terminal — 'spawn' mode's ONLY offer
   was a button that launches a separate OS window. A fresh tab dead-ended
   into "leave the app" before the boss did anything. Reported directly:
   "have the default mode be full page changes instead of small windows...
   only allow the pop-up version be an advanced feature in settings."

   Fixed by defaulting to 'chat' (always works, always in-app), and by
   hiding the PTY tab entirely unless it can do something Chat can't: the
   real embedded terminal (ptySupported), or — now opt-in — the native
   window (popoutAllowed, off by default, flipped on in Settings →
   Appearance → Advanced). A session persisted at 'spawn' from before this
   setting existed falls back to 'chat' rather than rendering a tab that's
   gone.

2. Ticket #12: the fallback panel's only CTA hardcoded "Windows Terminal"
   as the window it opens, on every platform. And pty_server.py's
   _terminal_spawn() backing it never had a macOS branch — its non-Windows
   path only tries x-terminal-emulator/gnome-terminal/kitty/xterm, none of
   which exist on stock macOS (confirmed live with `which` on this exact
   box: sys.platform == 'darwin', all four absent) — so on a Mac, clicking
   LAUNCH always 503'd with "no terminal emulator found", regardless of
   what the button said. Fixed with an osascript/Terminal.app branch and a
   platform-neutral label.

Run: python3 scripts/test_terminal_tabs_defaulted_into_a_popup_window.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERM = (ROOT / 'views' / 'terminal.jsx').read_text(encoding='utf-8')
PTY = (ROOT / 'pty_server.py').read_text(encoding='utf-8')
SETTINGS = (ROOT / 'modals' / 'settings.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('terminal tabs defaulted into a popup window')

    # --- part 1: default mode + advanced-setting gating -------------------
    m = re.search(r"useStoredV\(sKey\('mode'\),\s*'(\w+)'\)", TERM)
    check("new terminal tabs default to 'chat', not 'spawn'",
          m is not None and m.group(1) == 'chat',
          m.group(1) if m else 'pattern not found')

    check('a global (session-independent) popoutAllowed flag gates the '
          'native-window path',
          "useStoredV('cafresohq_terminal:popoutAllowed', false)" in TERM)

    check('the PTY tab is hidden unless it offers the embedded terminal or '
          'the boss opted into pop-outs',
          re.search(r"ptyTabVisible\s*=\s*spawnSupported\s*&&\s*\(ptySupported\s*\|\|\s*popoutAllowed\)", TERM)
          is not None)

    check('a session persisted at spawn mode before this setting existed '
          "falls back to 'chat' once its tab is no longer visible",
          re.search(r"termModeRaw\s*===\s*'spawn'\s*&&\s*!ptyTabVisible\)\s*\?\s*'chat'", TERM)
          is not None)

    check("the mode switcher only renders the PTY tab when ptyTabVisible",
          "ptyTabVisible ? [['spawn', '⚡', 'PTY']]" in TERM)

    check('the pop-out footer button (native window, embedded-terminal '
          'case) requires the advanced setting too, not just ptySupported',
          re.search(r"\{ptySupported\s*&&\s*popoutAllowed\s*&&\s*\(", TERM) is not None)

    check('Settings → Appearance reads/writes the same localStorage key '
          "views/terminal.jsx's useStoredV reads (not useStoredV itself — "
          'importing it here creates a circular import through '
          'features.jsx -> modals.jsx back to this file, which crashed '
          "the app on load with 'Modal' undefined)",
          "POPOUT_KEY = 'cafresohq_terminal:popoutAllowed'" in SETTINGS)

    check('the Settings toggle is wired to a visible switch control, not '
          'just declared and unused',
          'onClick={toggleTerminalPopout}' in SETTINGS)

    check("modals/settings.jsx does not import useStoredV from "
          "views/core.jsx — that path is circular (core.jsx -> "
          "features.jsx -> modals.jsx barrel -> settings.jsx) and left "
          "'./base.jsx' Modal undefined at module-eval time, hard-crashing "
          'the whole app before a single view could render',
          "from '../views/core.jsx'" not in SETTINGS)

    # --- part 2 (ticket #12): label + macOS spawn support ------------------
    check('the fallback launch panel no longer hardcodes "Windows Terminal" '
          'as the window it opens',
          'Windows Terminal</strong> window' not in TERM)

    check('the fallback panel describes the window generically instead',
          "<strong style={{ color: 'var(--ink)' }}>terminal window</strong>" in TERM)

    fn = re.search(r"def _terminal_spawn\(self\):.*?(?=\ndef |\Z)", PTY, re.S)
    check('found _terminal_spawn in pty_server.py', fn is not None)
    body = fn.group(0) if fn else ''

    check("_terminal_spawn has a dedicated sys.platform == 'darwin' branch",
          "sys.platform == 'darwin'" in body)

    check('the darwin branch shells out via osascript (Terminal.app), not '
          'the Linux terminal-emulator list that is always absent on macOS',
          "shutil.which('osascript')" in body)

    check('cwd_path is shell-quoted before being embedded in the '
          "AppleScript do-script command (shlex.quote)",
          re.search(r"shlex\.quote\(str\(cwd_path\)\)", body) is not None)

    check('the shell command is also escaped for the AppleScript string '
          'literal itself (backslash and double-quote)',
          ".replace('\\\\\\\\', '\\\\\\\\\\\\\\\\').replace('\"', '\\\\\\\\\"')" in body
          or ('replace(' in body and 'as_literal' in body))

    check('shlex is imported at module scope for the quoting above',
          re.search(r"^import shlex$", PTY, re.M) is not None)

    check('the darwin branch is a real elif alongside win32 (not folded '
          'into the generic Linux-emulator else, where it would never run '
          'because darwin never matches win32 either)',
          re.search(r"elif sys\.platform == 'darwin':", body) is not None)

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
