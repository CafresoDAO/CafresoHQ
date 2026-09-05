#!/usr/bin/env python3
"""Cmd/Ctrl+K opens the command palette and nothing else.

Bug: two independent `window` keydown listeners bound the SAME chord.
`CommandPaletteProvider` (ui/feedback.jsx) toggled the command palette on
Cmd/Ctrl+K; the App-level shortcut handler (app.jsx) toggled the ShortcutHud
on Cmd/Ctrl+K. Neither stopped the other, so:

  press 1 (focus on the page)  -> palette opens AND the shortcuts panel opens
  press 2 (focus now sits in the palette's own input, so app.jsx's
           `e.target.matches('input, textarea, select')` guard returns early)
           -> only the palette closes; the shortcuts panel is left stuck open
              with no Escape of its own
  press 3 -> palette re-opens, shortcuts panel closes

The two toggles drift out of phase, so the chord does something different
every time it is pressed — and the shortcuts panel's own list told the boss
`⌘K — Toggle shortcuts` while the palette's footer and DESIGN_SYSTEM told
them ⌘K meant the palette. One chord, two owners, two contradictory claims.

Fix: the palette owns ⌘K. app.jsx's duplicate branch is gone (the HUD is
still one click away on its floppy button and one entry down in the palette
itself), and the HUD's own row names the chord truthfully.

This lifts the REAL keydown handlers out of both files (brace-balanced
extraction) and fires one synthetic ⌘K into each, asserting that exactly one
panel reacts.
Run: python3 scripts/test_one_chord_never_opens_two_panels.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FEEDBACK = ROOT / 'ui' / 'feedback.jsx'
PANELS = ROOT / 'ui' / 'panels.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def extract_onkeys(src):
    """Every brace-balanced `const onKey = (e) => { ... }` in a source file."""
    out = []
    for m in re.finditer(r'const onKey = \(e\) => \{', src):
        depth = 0
        j = m.end() - 1                      # the opening '{'
        while j < len(src):
            if src[j] == '{':
                depth += 1
            elif src[j] == '}':
                depth -= 1
                if depth == 0:
                    out.append(src[m.start():j + 1] + ';')
                    break
            j += 1
    return out


def chorded_handler(path):
    """The one keydown handler in `path` that reacts to a held meta/ctrl."""
    hits = [fn for fn in extract_onkeys(path.read_text(encoding='utf-8'))
            if 'metaKey' in fn]
    return hits[0] if len(hits) == 1 else None


# Any `(e.metaKey || e.ctrlKey) && …'k'…` binding, however it spells the key.
CHORD_RE = re.compile(
    r'metaKey\s*\|\|\s*e\.ctrlKey\s*\)\s*&&[^\n]*?'
    r"(?:key\.toLowerCase\(\)\s*===\s*'k'|key\s*===\s*'k'|key\s*===\s*'K')")


def main():
    print('one chord, one panel — ⌘K belongs to the command palette')
    for p in (APP, FEEDBACK, PANELS):
        if not p.is_file():
            print(f'  FAIL  missing {p}')
            return 1

    # ── Static: exactly one place in the app binds ⌘/Ctrl+K ──────────────
    owners = []
    for p in sorted(ROOT.glob('*.jsx')) + sorted(ROOT.glob('ui/*.jsx')) \
            + sorted(ROOT.glob('app/*.jsx')) + sorted(ROOT.glob('views/*.jsx')) \
            + sorted(ROOT.glob('modals/*.jsx')):
        if CHORD_RE.search(p.read_text(encoding='utf-8')):
            owners.append(str(p.relative_to(ROOT)))
    check('exactly one file binds ⌘/Ctrl+K', len(owners) == 1, f'bound in {owners}')
    check('and that file is the command palette', owners == ['ui/feedback.jsx'],
          f'bound in {owners}')

    # ── Behavioral: fire ONE ⌘K into BOTH real handlers ──────────────────
    app_fn = chorded_handler(APP)
    pal_fn = chorded_handler(FEEDBACK)
    check('app.jsx shortcut handler extracted', app_fn is not None)
    check('command palette handler extracted', pal_fn is not None)
    if app_fn is None or pal_fn is None:
        print('\nFAILED: %s' % FAILS)
        return 1

    harness = r'''
const opened = [];
const rec = (name) => (...a) => opened.push(name);
// ── app.jsx's office shortcuts ──────────────────────────────────────────
const setShortcutsOpen = rec('shortcuts-hud');
const setHireOpen = rec('hire');
const setSettingsOpen = rec('settings');
const setNight = rec('night');
const onAddSticky = rec('sticky');
const goTo = rec('goTo');
const setFocus = rec('focus');
const onOpenStandup = rec('standup');
const NAV_ITEMS = [['visual'], ['tasks'], ['vault'], ['graph'], ['memory'], ['inbox'], ['calendar'], ['settings']];
const document = { querySelector: () => null };
''' + app_fn.replace('const onKey', 'const appOnKey', 1) + r'''
// ── ui/feedback.jsx's command palette ───────────────────────────────────
const open = false;
const close = rec('palette-close');
const openIt = rec('palette');
''' + pal_fn.replace('const onKey', 'const paletteOnKey', 1) + r'''

const cmdK = () => ({
  key: 'k', metaKey: true, ctrlKey: false, altKey: false,
  // Focus is on the page, not in a field — the case where app.jsx's
  // input/textarea guard does NOT short-circuit it.
  target: { matches: () => false },
  preventDefault: () => {},
});

opened.length = 0;
appOnKey(cmdK());
paletteOnKey(cmdK());
console.log(JSON.stringify({ opened }));
'''
    r = subprocess.run(['node', '-e', harness], capture_output=True, text=True)
    check('both handlers run standalone in node', r.returncode == 0,
          r.stderr.strip()[:300])
    if r.returncode != 0:
        print('\nFAILED: %s' % FAILS)
        return 1
    opened = json.loads(r.stdout)['opened']

    check('⌘K opens the command palette', 'palette' in opened, f'got {opened}')
    check('⌘K does NOT also open the shortcuts panel',
          'shortcuts-hud' not in opened, f'got {opened}')
    check('⌘K opens exactly one panel', len(opened) == 1, f'got {opened}')

    # ── The panel's own list must not claim a chord it does not own ──────
    panels = PANELS.read_text(encoding='utf-8')
    row = re.search(r'<kbd>⌘K</kbd><span>([^<]*)</span>', panels)
    check('the shortcuts panel still lists ⌘K', row is not None)
    if row is not None:
        check('and it no longer claims ⌘K toggles itself',
              'shortcut' not in row.group(1).lower(), f'row reads {row.group(1)!r}')

    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'one chord one panel: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
