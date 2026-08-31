#!/usr/bin/env python3
"""A dead wikilink's toast was a dead end.

In a linked library the dead link is where the NEXT note gets born:
you write [[fresh-idea]] mid-thought, then follow it. The preview
door (test_a_wikilink_in_the_preview_is_a_door.py) said '"fresh-idea"
isn't in the Library yet.' and stopped — naming the gap and offering
no way across it.

Now the dead-link branch offers the create: hqConfirm ('— create
it?'), then the same empty dirty buffer newNote opens, autosave files
it. A bare name lands beside the note that links to it; a path goes
where it says; a hidden part is refused exactly as newNote refuses it
(#140) — before any confirm, so a refusal never reads as a choice.
Verified live: confirm asked with the target named, the buffer opened
at Research/fresh-idea.md beside its linker and autosave filed it,
and [[.drafts/secret]] toasted the hidden-folder refusal with zero
confirms asked.

Run: python3 scripts/test_a_dead_link_offers_to_become_a_note.py
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
    print('a dead link offers to become a note')
    src = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')

    i = src.index('const openWikilink = async')
    j = src.index('const renameNote = async', i)
    body = src[i:j]

    # resolution now flows through the shared _wikiResolvePath rule
    check('a live link still just opens',
          'if (hitPath) { await openByPath(hitPath); return; }' in body)
    check('the dead branch asks before creating',
          re.search(r'hqConfirm\(`"\$\{target\}" isn\'t in the Library yet '
                    r'— create it\?`\)', body))
    check('...and a no is a no',
          re.search(r'if \(!\(await window\.hqConfirm[^\n]*\)\) return;', body))
    check('a hidden target is refused BEFORE the confirm',
          body.index('_hiddenPart(target)') < body.index('hqConfirm'),
          '— a refusal must never be dressed as a question')
    check('a bare name is born beside the note that links to it',
          "target.includes('/') ? target : here + target" in body
          and re.search(r"openNoteRef\.current\.path\.includes\('/'\)", body))
    check('the yes opens the same dirty buffer newNote opens',
          re.search(r"setOpenNote\(\{ path: norm, id: null, content: '', "
                    r"dirty: true \}\)", body),
          '— the quiet autosave is what actually files it')
    check('.md is appended when missing',
          "rel.endsWith('.md') ? rel : rel + '.md'" in body)

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
