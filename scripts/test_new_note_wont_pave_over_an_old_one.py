#!/usr/bin/env python3
"""NEW NOTE at an existing path erased the existing note in 2.5 seconds.

newNote opened an EMPTY buffer with dirty:true at whatever path the
boss typed. If a note already lived there, the 2.5s quiet autosave
filed the empty buffer over it — the note's whole content gone, zero
keystrokes, no message anywhere. Reproduced live before the fix:
seeded clobber-me.md with real content, typed its path into ➕ New
note, waited four seconds, and the file came back empty.

Now newNote checks the file list first (case-insensitively — the
shipping fs backend sits on a case-insensitive disk, where the write
clobbers either way) and, on a match, says so and opens the existing
note instead. The empty dirty buffer only ever opens at a path no
file holds. Verified live both ways: the existing path warns and
opens intact, a fresh path still creates.

Run: python3 scripts/test_new_note_wont_pave_over_an_old_one.py
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
    print("new note won't pave over an old one")
    src = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')

    i = src.index('const newNote = async')
    j = src.index('const openInObsidian', i)
    body = src[i:j]

    check('newNote looks for an existing file at the typed path',
          'files.find(' in body and 'existing' in body)
    check('the match is case-insensitive (macOS fs clobbers either way)',
          re.search(r'toLowerCase\(\)\s*===\s*norm\.toLowerCase\(\)', body))
    m_guard = re.search(r'if \(existing\) \{[\s\S]*?return;\s*\}', body)
    check('on a match it stops before any dirty buffer opens',
          m_guard and body.index('dirty: true') > m_guard.end(),
          '— the guard must precede setOpenNote({..., dirty: true})')
    check('...opens the existing note instead',
          m_guard and 'openByPath(existing.path)' in m_guard.group(0))
    check('...and says so',
          m_guard and 'already exists' in m_guard.group(0))
    check('a fresh path still opens the new dirty buffer',
          "setOpenNote({ path: norm, id: null, content: '', dirty: true })"
          in body)

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
