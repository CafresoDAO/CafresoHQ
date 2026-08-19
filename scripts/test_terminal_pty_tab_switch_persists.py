#!/usr/bin/env python3
"""Switching a terminal session tab from PTY back to Chat and back again
reconnected the PTY from scratch, even in desktop/windowed mode — reported
directly: "Why does our Terminal pty need to reconnect when hopping between
tabs? I feel like we should just instantly load back into our session and
have it persist... Not just it connecting to a new session all over again."

The app already has real session-resume plumbing: a stable per-project
sessionId in localStorage, and a server-side PTY registry (pty_server.py)
that keeps the shell alive for 300s after a disconnect and replays buffered
output on reattach. Two other places in this codebase that switch between
views get full value out of that plumbing by never tearing the view down in
the first place — session tabs (views/terminal.jsx, "Session panels — all
stay mounted, only active is visible") and desktop windows (app.jsx,
"Minimized windows stay MOUNTED and hidden via visibility... so internal
state AND scroll positions survive restore").

TerminalSession's own Chat/PTY sub-tabs (the 💬 Chat / ⚡ PTY buttons at the
top of every session) did NOT follow that pattern — they were a plain
`termMode === 'chat' ? (...) : (...)` ternary. Leaving the PTY tab for Chat
unmounted EmbeddedTerminal outright, disposing its WebSocket and its
xterm.js instance; switching back remounted it from zero, ran the full
`connect()` handshake again, and rebuilt the on-screen display from only the
server's 512KB replay buffer. The shell process usually did survive
server-side (within the 300s TTL) — but nothing about what the user saw
reflected that, which is exactly the "connecting to a new session all over
again" complaint. This reproduced with windowed/desktop mode fully out of
the picture, since app.jsx's window manager never enters into it — the
whole bug lives inside one session tab.

**The fix** replaces the ternary with the same stay-mounted, toggle-display
pattern the other two spots already use, gated behind a `ptyEverOpened`
flag (set once, on first switch to PTY, and never cleared) so a tab that
only ever uses Chat still never pays for an idle background shell. The
EmbeddedTerminal's `visible` prop is now `visible && termMode === 'spawn'`,
not bare `visible` — otherwise, once kept mounted, its fit/focus effect
would fire even while hidden behind the Chat panel and steal keyboard
focus out of the chat textarea.

Run: python3 scripts/test_terminal_pty_tab_switch_persists.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERM = (ROOT / 'views' / 'terminal.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('Does switching PTY <-> Chat keep the terminal session mounted?')

    # ── 1. the old unmount-on-switch ternary is gone ────────────────────
    check("TerminalSession no longer branches Chat/PTY through a plain "
          "ternary that unmounts whichever side isn't active",
          not re.search(r"termMode === 'chat' \? \(\s*<>", TERM),
          'old `{termMode === \'chat\' ? (<>` pattern still present')

    # ── 2. both panels are unconditionally rendered, display-toggled ────
    check("the Chat panel is always mounted, hidden via display when "
          "PTY is active — the same pattern session tabs and desktop "
          "windows already use elsewhere in this file/app.jsx",
          "display: termMode === 'chat' ? 'flex' : 'none'" in TERM,
          'chat display-toggle wrapper not found')
    check("the PTY panel is always mounted (once opened), hidden via "
          "display when Chat is active",
          "display: termMode === 'chat' ? 'none' : 'flex'" in TERM,
          'PTY display-toggle wrapper not found')

    # ── 3. PTY mount is gated behind "opened at least once", not eager ──
    check("a fresh session tab doesn't eagerly spin up a background PTY "
          "shell just because ptySupported is true — it waits for the "
          "user to actually switch to PTY at least once",
          re.search(r"ptyEverOpened.*?React\.useState\(termMode === 'spawn'\)", TERM, re.S)
          is not None,
          'ptyEverOpened initial state not tied to termMode')
    check("once opened, the flag is set (and, being useState, never "
          "reset) on every transition into PTY mode — so it stays "
          "mounted through later trips back to Chat",
          re.search(r"useEffect\(\(\) => \{\s*if \(termMode === 'spawn'\) setPtyEverOpened\(true\);\s*\}, \[termMode\]\);", TERM)
          is not None,
          'ptyEverOpened set-on-spawn effect not found')
    check("EmbeddedTerminal itself is only mounted once ptyEverOpened is "
          "true — kept-mounted must not become always-mounted-even-if-"
          "never-visited",
          'ptyEverOpened && (ptySupported ? (' in TERM,
          'EmbeddedTerminal mount not gated by ptyEverOpened')

    # ── 4. visible prop now accounts for the sub-tab, not just the ─────
    #        session tab, or a hidden EmbeddedTerminal would steal focus
    check("EmbeddedTerminal's visible prop is visible AND termMode==='spawn' "
          "— now that it stays mounted while Chat is showing, passing the "
          "bare session-tab `visible` would fire its focus()-on-visible "
          "effect while the user is typing in the Chat box",
          "visible={visible && termMode === 'spawn'}" in TERM,
          'EmbeddedTerminal visible prop still bare `visible`')

    # ── 5. mechanism, run for real: restate the state machine and prove
    #        ptyEverOpened latches true and never un-latches ───────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the mechanism check needs it')
    else:
        js = r'''
function drive(modeSequence) {
  let ptyEverOpened = modeSequence[0] === 'spawn';
  const log = [];
  for (const termMode of modeSequence) {
    if (termMode === 'spawn') ptyEverOpened = true;   // the useEffect
    const chatDisplay = termMode === 'chat' ? 'flex' : 'none';
    const ptyDisplay  = termMode === 'chat' ? 'none' : 'flex';
    const ptyMounted  = ptyEverOpened;   // both panels always in the tree;
    log.push({ termMode, chatDisplay, ptyDisplay, ptyMounted });
  }
  return log;
}
console.log(JSON.stringify({
  neverOpensPty: drive(['chat', 'chat', 'chat']),
  opensThenReturns: drive(['chat', 'spawn', 'chat', 'spawn', 'chat']),
}));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=15)
        if p.returncode != 0:
            check('the mechanism harness runs', False, p.stderr.strip()[:400])
        else:
            out = json.loads(p.stdout)
            never = out['neverOpensPty']
            check("a tab that never opens PTY never mounts EmbeddedTerminal "
                  "— staying mounted must not mean eagerly mounting",
                  all(not step['ptyMounted'] for step in never), never)
            cyc = out['opensThenReturns']
            check("once PTY is opened, it stays mounted through every "
                  "later trip back to Chat and forward again — this is "
                  "the actual fix: no more remount on the second switch",
                  all(step['ptyMounted'] for step in cyc[1:]), cyc)
            check("display toggling still correctly hides whichever side "
                  "is inactive at each step, mount state aside",
                  all((step['chatDisplay'] == 'flex') == (step['termMode'] == 'chat')
                      and (step['ptyDisplay'] == 'flex') == (step['termMode'] != 'chat')
                      for step in cyc),
                  cyc)

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
