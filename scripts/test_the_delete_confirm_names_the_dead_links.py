#!/usr/bin/env python3
"""Deleting a linked note asked a question that hid the real cost.

Renames follow inbound [[wikilinks]] now
(test_links_follow_a_renamed_note.py); deletes can't — the note is
gone, the links point at nothing. The confirm said only 'Delete
"x.md"? This cannot be undone.', which is true of the FILE and silent
about the GRAPH: however many notes still linked to it, they all went
dead without a word.

Now deleteNote counts inbound note→note edges from the graph engine's
last snapshot and names the damage: 'Delete "x.md"? 1 note still
links to it — that link goes dead. This cannot be undone.' Verified
live both ways: the linked case warns with the count, the unlinked
case keeps the plain confirm. Office edges (tasks, receipts) are
excluded — they aren't wikilinks and can't go dead — and the whole
count is best-effort: with no snapshot the plain confirm stands, the
delete never blocks on it.

Run: python3 scripts/test_the_delete_confirm_names_the_dead_links.py
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
    print('the delete confirm names the dead links')
    src = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')

    i = src.index('const deleteNote = async')
    j = src.index('const newNote = async', i)
    body = src[i:j]

    check('the confirm still exists and stays danger-styled',
          re.search(r'window\.hqConfirm\(confirmMsg, \{ danger: true \}\)', body))
    check('inbound links are counted from the graph snapshot',
          '_lastGraph' in body and 'e.target) === n.path' in body)
    check('only note→note edges count (office edges are not wikilinks)',
          re.search(r'\\\.md\$/i\.test\(String\(e\.source\)\)', body),
          '— without this, a task or receipt edge inflates the warning')
    check('sources are deduplicated (one note, many links = one note)',
          'new Set(' in body)
    check('the warning names the damage',
          'dead' in body and 'still link' in body)
    check('best-effort: a missing snapshot falls back to the plain confirm',
          re.search(r'let confirmMsg = `Delete[\s\S]*?try \{', body)
          and 'catch (_e) {}' in body,
          '— the count must never block the delete')

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
