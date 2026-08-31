#!/usr/bin/env python3
"""One click on a graph node replaced the entire Library with an error.

The links graph legitimately draws OFFICE nodes — agents, tasks,
receipts — alongside notes. Clicking one fed its id ('agent:Llama ·
Generalist') straight into openByPath; the 404 landed in the
view-level error state, and the whole Library — tree, editor, graph —
became "The cabinet won't open." Reproduced live with a single click
on a node the product itself had drawn.

Two fixes, either of which alone would have been enough and both of
which belong:
  1. openGraphNode gates both GraphView onOpenNote call sites — only
     an id the file list actually holds is a note this room can open;
     office nodes keep their engine-side selection and nothing more.
  2. openByPath's catch is a snag toast now, never setErr — the
     view-level error means THE ROOM is broken, and this catch fires
     for one note that wouldn't open (a stale graph id, a note deleted
     elsewhere). One stuck door must not blank the room; the popout's
     cafresohq:openNote event rides this same path.
Verified live: office-node click keeps the view, a note opens, a bad
event path toasts while the open note stays on screen.

Run: python3 scripts/test_an_office_node_cannot_blank_the_library.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('an office node cannot blank the library')
    src = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')

    check('the gate exists and only opens what the file list holds',
          re.search(r'const openGraphNode = \(p, open\) => \{\s*'
                    r'if \(files\.some\(f => f\.path === p\)\) open\(p\);', src))
    check('the mobile graph rides the gate',
          'onOpenNote={(p) => openGraphNode(p, mobileOpenByPath)}' in src)
    check('the desktop graph rides the gate',
          'onOpenNote={p => openGraphNode(p, openByPath)}' in src)
    check('no GraphView call site bypasses it',
          not re.search(r'onOpenNote=\{(?!.*openGraphNode)[^}]*openByPath',
                        src))

    i = src.index('const openByPath = async')
    j = src.index('const saveNote = async', i)
    body = src[i:j]
    check("openByPath's failure is a toast, not the view-level error",
          'snag("Couldn\'t open that note"' in body
          and not re.search(r'catch \(e\) \{ setErr\(', body),
          '— setErr here replaces the ENTIRE Library for one stuck note')

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
