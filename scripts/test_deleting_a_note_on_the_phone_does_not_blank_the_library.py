#!/usr/bin/env python3
"""Deleting the open note on a narrow window left the Library blank.

views/vault.jsx's phone layout (`if (_isMobileV) { ... }`, and `_isMobileV`
is `max-width: 768px` — a narrow DESKTOP window as much as a phone) shows
exactly one pane at a time, chosen by the `vaultTab` state:

    {vaultTab === 'tree'   && ( ...the file tree... )}
    {vaultTab === 'graph'  && ( ...the links graph... )}
    {vaultTab === 'editor' && openNote && ( ...the note... )}

The third guard carries `&& openNote` — but nothing kept `vaultTab` and
`openNote` in step. Only the mobile ✕ button did it by hand
(`if (await closeNote()) setVaultTab('tree')`). Every OTHER path that ends
the open note left `vaultTab` sitting on 'editor' with no note behind it,
and the render then produced a tab bar over an empty flex box: no pane, and
not even a lit tab to explain it, because the 'editor' entry in the tab bar
is gated on `openNote` too and drops out with the note.

The two reachable paths, both in this same file:

  · 🗑 Delete — `deleteNote` awaits the confirm ("This cannot be undone"),
    calls vaultDelete, `setOpenNote(null)`, `refresh()`, and never touches
    `vaultTab`. The boss confirms a delete of ONE note and the whole
    cabinet goes blank on them.
  · Esc — the window-level keydown handler calls `closeNote()` directly,
    which also only `setOpenNote(null)`s. One keypress on a laptop with a
    narrow window.

Fix (views/vault.jsx, inside the mobile branch): derive what gets DRAWN
from the invariant instead of trusting the stored tab —

    const tab = (vaultTab === 'editor' && !openNote) ? 'tree' : vaultTab;

— and render the three panes and the tab-bar highlight off `tab`.
`setVaultTab` still stores the boss's pick; only the drawing falls back, so
any future path that drops a note cannot reopen the hole.

This test executes the extracted derivation in Node over the full truth
table, and checks in source that the panes and the tab-bar highlight
actually read it — plus that the two blanking paths still exist as
described (i.e. the derivation is load-bearing, not decoration).

Run: python3 scripts/test_deleting_a_note_on_the_phone_does_not_blank_the_library.py
(the Node execution check is skipped if `node` is not on PATH; the
source-shape checks run everywhere)
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT_JSX = ROOT / 'views' / 'vault.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok   ' if cond else '  FAIL ') + name)
    if not cond:
        if detail:
            print('         ' + str(detail))
        FAILS.append(name)


src = VAULT_JSX.read_text(encoding='utf-8')

# ── The mobile branch only — the desktop grid below it has no tabs. ────────
try:
    start = src.index('  if (_isMobileV) {')
    end = src.index('  /* ---- Desktop: 3-column grid ---- */')
except ValueError:
    print('FAIL: could not locate the mobile branch in views/vault.jsx')
    sys.exit(1)
mobile = src[start:end]

print('the note can still vanish out from under the tab (the bug is real):')

# deleteNote drops the note and never moves the tab.
m = re.search(r'const deleteNote = async \(\) => \{.*?\n  \};', src, re.S)
check('deleteNote exists', bool(m))
if m:
    body = m.group(0)
    check('deleteNote closes the note', 'setOpenNote(null)' in body, body[-300:])
    check('deleteNote never moves the tab itself', 'setVaultTab' not in body,
          '— if it did, this test is describing the wrong shape')

# The Esc handler closes the note the same way.
check('closeNote drops the note without moving the tab',
      re.search(r'const closeNote = async \(\) => \{(?:(?!setVaultTab).)*?setOpenNote\(null\)',
                src, re.S) is not None)
check('the window Esc handler calls closeNote()',
      re.search(r"e\.key !== 'Escape'.*?closeNote\(\)", src, re.S) is not None)

# The editor pane really is gated on openNote, so a stale 'editor' tab
# draws nothing at all.
check("the editor pane is gated on openNote",
      re.search(r"===\s*'editor'\s*&&\s*openNote\s*&&", mobile) is not None)
check("the editor TAB is gated on openNote too (no lit tab to explain it)",
      re.search(r"\.\.\.\(openNote \? \[\['editor'", mobile) is not None)

print()
print('the drawn tab falls back when there is no note:')

# ── Extract the derivation and run it for real. ───────────────────────────
deriv = re.search(r'^\s*const tab = (.+);\s*$', mobile, re.M)
check('the mobile branch derives what it DRAWS from vaultTab + openNote',
      deriv is not None,
      "— expected `const tab = (vaultTab === 'editor' && !openNote) ? 'tree' : vaultTab;`")

if deriv and shutil.which('node'):
    expr = deriv.group(1)
    js = (
        'const out = [];\n'
        'for (const vaultTab of ["tree", "graph", "editor"]) {\n'
        '  for (const openNote of [null, { path: "n.md" }]) {\n'
        '    out.push([vaultTab, !!openNote, (' + expr + ')]);\n'
        '  }\n'
        '}\n'
        'console.log(JSON.stringify(out));\n'
    )
    proc = subprocess.run(['node', '-e', js], capture_output=True, text=True)
    if proc.returncode != 0:
        check('the derivation runs in Node', False, proc.stderr.strip()[:400])
    else:
        table = {(r[0], r[1]): r[2] for r in json.loads(proc.stdout)}
        check("no note + tab on 'editor' → draws the tree, not a blank pane",
              table[('editor', False)] == 'tree', table)
        check("a note open + tab on 'editor' → still the editor",
              table[('editor', True)] == 'editor', table)
        for t in ('tree', 'graph'):
            for has in (False, True):
                check("'%s' is left alone (note open: %s)" % (t, has),
                      table[(t, has)] == t, table)
elif deriv:
    print('  skip  Node not on PATH — source-shape checks only')

print()
print('every pane and the tab bar read the drawn tab, not the stored one:')

if deriv:
    name = 'tab'
    for label, pat in [
        ("the tree pane", r'\{' + name + r" === 'tree' &&"),
        ("the graph pane", r'\{' + name + r" === 'graph' &&"),
        ("the editor pane", r'\{' + name + r" === 'editor' && openNote &&"),
    ]:
        check(label + ' renders off the drawn tab', re.search(pat, mobile) is not None)
    highlights = re.findall(r'\b(\w+) === key \?', mobile)
    check('the tab-bar highlight reads the drawn tab (%d place(s))' % len(highlights),
          len(highlights) == 3 and set(highlights) == {name},
          highlights)

# Nothing in the tab bar / panes may still compare the RAW stored tab —
# that is exactly the shape the blank pane came from.
# Comments and the derivation line itself name `vaultTab` legitimately; what
# must be gone is any PANE still switching on the raw stored value.
rendered = re.sub(r'/\*.*?\*/', '', mobile, flags=re.S)
rendered = re.sub(r'^\s*const tab = .+;\s*$', '', rendered, flags=re.M)
check('no pane still switches on the raw stored tab',
      len(re.findall(r"vaultTab === '(?:tree|graph|editor)' &&", rendered)) == 0,
      re.findall(r"vaultTab === '(?:tree|graph|editor)' &&", rendered))
check('no tab-bar highlight still reads the raw stored tab',
      'vaultTab === key' not in rendered)

print()
if FAILS:
    print('%d check(s) failed: %s' % (len(FAILS), ', '.join(FAILS)))
    sys.exit(1)
print('all checks passed')
