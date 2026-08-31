#!/usr/bin/env python3
"""A brand-new boss landed on a silently blank tree.

The very first thing a beta tester opens the Library to is nothing:
no files yet, so FolderTree rendered an empty div, and the only doors
in were three tiny toolbar icons. Blank reads as broken — or worse,
after a filter, as "lost your files".

Now an empty Library greets: it names what lives here (notes,
research, decks, documents, images — and coworker deliveries), and
repeats the two real doors as full-size buttons (new note, upload —
the upload door and the drop-hint only off the bridge vault, which
has no upload). A kind filter that empties a NON-empty Library says
so instead of greeting. The kind chips hide when there is nothing to
filter. Both layouts (desktop pane and mobile tree tab) render the
same element in place of the tree only — toolbar and search stay.

The first cut of this crashed the whole app: emptyTreeState was
declared above `const newNote` and the JSX evaluates immediately, so
render died on a TDZ ReferenceError ("Cannot access before
initialization") — reproduced live as a stuck boot screen. The
declaration-order check below is that crash's tombstone.

Run: python3 scripts/test_an_empty_library_greets_its_first_boss.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('an empty library greets its first boss')
    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')

    i = vault.find('const emptyTreeState = ')
    check('the empty state exists', i != -1)
    if i == -1:
        print('\n1 check(s) failed:\n  - the empty state exists')
        return 1
    # the element ends where the next component-level const begins
    j = vault.index('\n  const ', i + 10)
    block = vault[i:j]

    check('it declares AFTER newNote — the TDZ crash tombstone',
          vault.index('const newNote = async') < i)
    check('a truly empty Library is the greeting case',
          'files.length === 0 ?' in block)
    check('a filter that empties a non-empty Library says so instead',
          'kindFiles.length === 0 ?' in block
          and 'pick another chip' in block)
    check('the greeting says what the Library holds',
          'Your Library is empty' in block
          and 'deliveries' in block)
    check('the new-note door is the same newNote the toolbar uses',
          'onClick={newNote}' in block)
    check('the upload door clicks the same hidden input',
          'fileInputRef.current && fileInputRef.current.click()' in block)
    check('upload door and drop-hint stay off the bridge vault',
          block.count('{!_bridge && (') == 2
          and 'drop files anywhere' in block)

    check('both layouts swap the TREE for the greeting, nothing else',
          vault.count('{emptyTreeState || <FolderTree') == 2)
    check('the kind chips hide when there is nothing to filter',
          vault.count('{files.length > 0 && kindChips}') == 2)
    check('the loading moment still belongs to the !status screen',
          'if (!status) {' in vault
          and vault.index('if (!status) {') > i)

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
