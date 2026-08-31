#!/usr/bin/env python3
"""⌘S in the editor opened the browser's save-page dialog.

Save-note muscle memory is universal, and the Library's only keydown
listener answered Escape — so ⌘S mid-keystroke popped the browser's
own dialog over the boss's writing. The quiet autosave makes the
manual save near-redundant; claiming the shortcut is the point, and
answering it with the note's own save (a no-op on a clean buffer)
instead of the page's.

Plain ⌘S/^S only: ⌘⇧S ("save as") and ⌥ combos stay the browser's.
Verified live: a dirtied buffer hit disk within a second of the
keystroke, defaultPrevented true, the shifted combo untouched.

Run: python3 scripts/test_cmd_s_saves_the_note_not_the_page.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, opener):
    i = src.index(opener)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise SystemExit('unbalanced braces lifting ' + opener)


def main():
    print('cmd-s saves the note, not the page')
    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')

    handler = brace_lift(vault, 'const onSaveKey = (e) =>')
    js = ('let saved = 0;\n'
          'const saveNoteRef = {current: () => { saved++; }};\n'
          + handler + '\n'
          'const ev = (o) => { let p = false; return Object.assign({\n'
          "  key: 's', metaKey: false, ctrlKey: false, altKey: false,\n"
          '  shiftKey: false, preventDefault: () => { p = true; },\n'
          '  get prevented() { return p; }}, o); };\n'
          'const cases = {\n'
          '  meta: ev({metaKey: true}),\n'
          '  ctrl: ev({ctrlKey: true}),\n'
          "  metaUpper: ev({metaKey: true, key: 'S'}),\n"
          '  bareS: ev({}),\n'
          '  shifted: ev({metaKey: true, shiftKey: true}),\n'
          '  alted: ev({metaKey: true, altKey: true}),\n'
          "  otherKey: ev({metaKey: true, key: 'k'}),\n"
          '};\n'
          'for (const c of Object.values(cases)) onSaveKey(c);\n'
          'console.log(JSON.stringify({saved,\n'
          '  p: Object.fromEntries(Object.entries(cases)'
          '.map(([k, v]) => [k, v.prevented]))}));')
    p = subprocess.run(['node', '-e', js], capture_output=True, text=True,
                       timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('⌘S and ^S are claimed (shift-key case too)',
          r['p']['meta'] and r['p']['ctrl'] and r['p']['metaUpper'], r)
    check('...and each one saves the note',
          r['saved'] == 3, r['saved'])
    check("a bare 's' while typing is just typing", r['p']['bareS'] is False)
    check("⌘⇧S stays the browser's", r['p']['shifted'] is False)
    check("⌥ combos stay the browser's", r['p']['alted'] is False)
    check('other ⌘ shortcuts pass through', r['p']['otherKey'] is False)

    check('the shortcut goes through saveNoteRef, never a stale closure',
          'saveNoteRef.current();' in handler)
    check('the listener is registered and cleaned up',
          "window.addEventListener('keydown', onSaveKey);" in vault
          and "window.removeEventListener('keydown', onSaveKey);" in vault)

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
