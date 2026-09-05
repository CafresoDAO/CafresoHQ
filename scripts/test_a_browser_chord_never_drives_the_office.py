#!/usr/bin/env python3
"""A browser chord (Cmd+F, Ctrl+S, Cmd+D, ...) must never drive the office shortcuts (app.jsx).

Bug: the App-level window keydown handler maps bare letters to office
actions — h hires, s opens Settings, d flips night mode, n mints a sticky,
f toggles focus, m jumps to memory, u opens the stand-up — but only the
digit branch ever checked for a held modifier (`!e.metaKey && !e.ctrlKey &&
!e.altKey`). So every browser combo that shares a letter also drove the
office: Cmd+F (find in page) flipped focus mode, Cmd+S/Ctrl+S (save) opened
the Settings modal under the save dialog, Cmd+D (bookmark) toggled night,
Ctrl+H (history) opened the hire modal, Ctrl+N minted a sticky note. The
boss reached for a browser habit and the office rearranged itself
underneath it.

Fix: one guard — a held meta/ctrl/alt returns before any letter branch can
fire. Plain letters and the digit jumps behave exactly as before.

(This handler used to claim Cmd/Ctrl+K for the shortcuts HUD as well, ahead
of that guard. It no longer does: the command palette in ui/feedback.jsx
binds the same chord on its own window listener, so both panels opened at
once — see scripts/test_one_chord_never_opens_two_panels.py. The chord now
falls through to the palette like any other browser-shaped combo.)

This lifts the REAL onKey handler out of app.jsx (brace-balanced
extraction) and drives it in Node with recording shims, firing plain and
modified keystrokes and asserting which office actions ran.
Run: python3 scripts/test_a_browser_chord_never_drives_the_office.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def extract_onkey(src):
    """Brace-balanced extraction of `const onKey = (e) => { ... };` — same
    technique test_tour_keys_dont_fire_while_typing.py uses."""
    m = re.search(r'const onKey = \(e\) => \{', src)
    if not m:
        return None
    depth = 0
    j = m.end() - 1  # the opening '{'
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1] + ';'
        j += 1
    return None


def main():
    print('App shortcuts — a held modifier hands the keystroke back to the browser')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    text = SRC.read_text(encoding='utf-8')

    fn = extract_onkey(text)
    check('onKey handler extracted from app.jsx', fn is not None)
    if fn is None:
        print('\nFAILED: %s' % FAILS)
        return 1

    # ── Behavioral: run the REAL handler in Node with recording shims ──
    harness = r'''
const calls = [];
const rec = (name) => (...a) => calls.push(name + (a.length && typeof a[0] !== 'function' ? ':' + String(a[0]) : ''));
const setShortcutsOpen = rec('shortcuts');
const setHireOpen = rec('hire');
const setSettingsOpen = rec('settings');
const setNight = rec('night');
const onAddSticky = rec('sticky');
const goTo = rec('goTo');
const setFocus = rec('focus');
const onOpenStandup = rec('standup');
const NAV_ITEMS = [['visual'], ['tasks'], ['vault'], ['graph'], ['memory'], ['inbox'], ['calendar'], ['settings']];
const document = { querySelector: () => null };

''' + fn + r'''

const ev = (key, mods = {}) => ({
  key,
  metaKey: !!mods.meta, ctrlKey: !!mods.ctrl, altKey: !!mods.alt,
  target: { matches: () => false },
  preventDefault: () => {},
});

const fire = (key, mods) => {
  calls.length = 0;
  onKey(ev(key, mods));
  return calls.slice();
};

console.log(JSON.stringify({
  plain_h:  fire('h'),
  plain_f:  fire('f'),
  plain_d:  fire('d'),
  plain_3:  fire('3'),
  cmd_k:    fire('k', { meta: true }),
  ctrl_k:   fire('k', { ctrl: true }),
  cmd_f:    fire('f', { meta: true }),
  cmd_s:    fire('s', { meta: true }),
  ctrl_s:   fire('s', { ctrl: true }),
  cmd_d:    fire('d', { meta: true }),
  ctrl_h:   fire('h', { ctrl: true }),
  ctrl_n:   fire('n', { ctrl: true }),
  alt_m:    fire('m', { alt: true }),
  cmd_u:    fire('u', { meta: true }),
  cmd_3:    fire('3', { meta: true }),
}));
'''
    r = subprocess.run(['node', '-e', harness], capture_output=True, text=True)
    check('handler runs standalone in node', r.returncode == 0, r.stderr.strip()[:200])
    if r.returncode != 0:
        print('\nFAILED: %s' % FAILS)
        return 1
    got = json.loads(r.stdout)

    # Plain keys keep working — the office's own shortcuts are untouched.
    check("plain h still opens the hire modal", got['plain_h'] == ['hire:true'],
          f"got {got['plain_h']}")
    check("plain f still toggles focus mode", got['plain_f'] == ['focus'],
          f"got {got['plain_f']}")
    check("plain d still toggles night mode", got['plain_d'] == ['night'],
          f"got {got['plain_d']}")
    check("plain 3 still jumps to the third view", got['plain_3'] == ['goTo:vault'],
          f"got {got['plain_3']}")
    # ⌘K belongs to the command palette (ui/feedback.jsx) — this handler must
    # leave it alone, or one press opens two panels.
    check("Cmd+K leaves the chord to the command palette", got['cmd_k'] == [],
          f"got {got['cmd_k']}")
    check("Ctrl+K leaves the chord to the command palette", got['ctrl_k'] == [],
          f"got {got['ctrl_k']}")
    # Browser chords belong to the browser — no office action fires.
    check("Cmd+F (find in page) does not flip focus mode", got['cmd_f'] == [],
          f"got {got['cmd_f']}")
    check("Cmd+S (save page) does not open Settings", got['cmd_s'] == [],
          f"got {got['cmd_s']}")
    check("Ctrl+S (save page) does not open Settings", got['ctrl_s'] == [],
          f"got {got['ctrl_s']}")
    check("Cmd+D (bookmark) does not toggle night mode", got['cmd_d'] == [],
          f"got {got['cmd_d']}")
    check("Ctrl+H (history) does not open the hire modal", got['ctrl_h'] == [],
          f"got {got['ctrl_h']}")
    check("Ctrl+N (new window) does not mint a sticky note", got['ctrl_n'] == [],
          f"got {got['ctrl_n']}")
    check("Alt+M does not navigate to memory", got['alt_m'] == [],
          f"got {got['alt_m']}")
    check("Cmd+U (view source) does not open the stand-up", got['cmd_u'] == [],
          f"got {got['cmd_u']}")
    # The digit guard that always existed keeps holding.
    check("Cmd+3 (browser tab jump) does not change views", got['cmd_3'] == [],
          f"got {got['cmd_3']}")

    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'browser chords: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
