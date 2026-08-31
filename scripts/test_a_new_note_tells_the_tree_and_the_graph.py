#!/usr/bin/env python3
"""A brand-new note existed on the server and appeared nowhere.

`newNote` opens a dirty buffer; the ONLY thing that ever files it is the
2.5s QUIET autosave — and quiet saves skipped `refresh()` entirely. So
the note was created server-side, sat open in the editor saying
"Saved", and showed up in neither the file tree nor the graph until a
manual ↻. Driven live: create a note, type a [[wikilink]], open the
graph — two nodes, no edge, no tree row; one manual refresh later,
everything was there (so resolution was fine, staleness was the bug).

The fix keeps quiet saves quiet for ordinary edits and adds two precise
exceptions in saveNote:

  - a save that CREATES the file (bridge: no id yet; REST: path not in
    `files`) runs the full refresh() — tree + graph;
  - a quiet save whose [[wikilink]] SET changed refreshes just the
    graph — the signature only moves when the link structure does, so
    prose typing never jolts the layout.

Verified live after: create → type wikilink → wait out the autosave →
tree row, graph node, and edge all present with zero manual refreshes.

Run: python3 scripts/test_a_new_note_tells_the_tree_and_the_graph.py
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
    print('a new note tells the tree and the graph')
    src = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')

    i = src.index('const saveNote = async')
    j = src.index('const saveNoteRef', i)
    body = src[i:j]

    check('saveNote detects a creating save on BOTH backends',
          "const creating = _bridge ? !note.id : !files.some(f => f.path === note.path);" in body)
    check('a creating save refreshes even when quiet',
          re.search(r'if \(creating \|\| !\(opts && opts\.quiet\)\) await refresh\(\);', body),
          '— without this, the quiet autosave that files every new note '
          'leaves the tree and graph stale until a manual ↻')
    check('the wikilink signature is computed from the saved content',
          re.search(r"match\(/\\\[\\\[\[\^\\\]\]\+\\\]\\\]/g\)", body) is not None
          and '.sort().join(' in body)
    check('a quiet save with a changed link set refreshes the graph',
          'else if (linksChanged) refreshGraph();' in body)
    check('the signature is tracked per path across saves — read AND '
          'written back',
          # The write-back is load-bearing: without it every quiet save
          # compares against a stale signature and refreshes the graph on
          # every autosave forever (caught by this file's own fire-test —
          # a read-only substring check stayed green with the assignment
          # deleted).
          'lastLinkSigRef.current[note.path] !== linkSig' in body
          and 'lastLinkSigRef.current[note.path] = linkSig;' in body
          and 'const lastLinkSigRef = React.useRef({});' in src)
    check('ordinary quiet edits still skip the full refresh '
          '(the quiet flag keeps its purpose)',
          'opts && opts.quiet' in body)

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
