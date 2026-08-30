#!/usr/bin/env python3
"""The Library holds decks, documents and research — and one flat tree.

Since the vault became the Library (artifacts, ppts, documents, markdown,
research all filed together), the only ways to find "the deck" were to
know its name or to scan the whole tree past every note. Search covers
the first case; nothing covered the second.

The tree now carries kind chips — ALL · NOTES · DECKS · DOCS · DATA ·
MEDIA — that filter which files build the tree. Two honesty properties
are load-bearing and pinned here:

  - a chip only renders when the Library actually holds at least one
    file of its kind (`files.some(pred)`): six chips over a Library of
    three notes would be five buttons that do nothing;
  - the predicates split by what the file IS (extension), reusing the
    same families the binary-file panel's _BIN_KINDS already names, so
    the chip row and the file panel never disagree about what a .pptx
    is.

Both tree mounts (mobile and desktop) read the filtered list; search
hits are not filtered — a search is already a filter, and stacking a
second, half-visible one on top of it produced "no results" lies in
every product that has tried.

Run: python3 scripts/test_the_library_can_show_just_the_decks.py
"""
import json
import re
import shutil
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


def strip_comments(src):
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('the Library can show just the decks')
    vault = strip_comments((ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8'))

    check('the kind table exists with all six kinds',
          re.search(r"const VAULT_KINDS = \[[\s\S]*?'all'[\s\S]*?'notes'[\s\S]*?'decks'"
                    r"[\s\S]*?'docs'[\s\S]*?'data'[\s\S]*?'media'[\s\S]*?\];", vault))
    check('a chip only renders for kinds the Library holds',
          "id === 'all' || files.some(pred)" in vault,
          '— six chips over three notes is five buttons that do nothing')
    check('the active chip announces itself',
          'aria-pressed={kindFilter === id}' in vault)
    check('both tree mounts read the filtered list',
          vault.count('<FolderTree files={kindFiles}') == 2
          and '<FolderTree files={files}' not in vault,
          vault.count('<FolderTree files={kindFiles}'))
    check('both mounts carry the chip row',
          vault.count('{kindChips}') == 2, vault.count('{kindChips}'))
    check('search hits are NOT kind-filtered',
          'hits.filter(kindPred)' not in vault and 'hits.filter(kind' not in vault,
          '— a search is already a filter; stacking a half-visible second '
          'one produces "no results" lies')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH — predicate checks need it')
    else:
        i = vault.index('const VAULT_KINDS = [')
        j = vault.index('];', i) + 2
        js = vault[i:j] + r'''
const F = (p, bin) => ({ path: p, isBinary: bin === undefined ? true : bin });
const files = [
  F('notes/plan.md', false), F('decks/q3.pptx'), F('docs/brief.pdf'),
  F('docs/contract.docx'), F('data/vendors.xlsx'), F('media/chart.png'),
  F('misc/archive.zip'),
];
const by = {};
for (const [id, _l, pred] of VAULT_KINDS) by[id] = files.filter(pred).map(f => f.path);
console.log(JSON.stringify(by));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            check('the kind table runs', False, p.stderr.strip()[:300])
        else:
            by = json.loads(p.stdout.strip().split('\n')[-1])
            check('ALL keeps everything', len(by['all']) == 7, by['all'])
            check('NOTES is the text files', by['notes'] == ['notes/plan.md'], by['notes'])
            check('DECKS finds the deck', by['decks'] == ['decks/q3.pptx'], by['decks'])
            check('DOCS takes documents AND pdf',
                  by['docs'] == ['docs/brief.pdf', 'docs/contract.docx'], by['docs'])
            check('DATA finds the spreadsheet', by['data'] == ['data/vendors.xlsx'], by['data'])
            check('MEDIA finds the chart', by['media'] == ['media/chart.png'], by['media'])
            check('a kind nothing claims stays visible only under ALL',
                  all('misc/archive.zip' not in by[k] for k in
                      ('notes', 'decks', 'docs', 'data', 'media')),
                  '— the archive belongs to no chip, and no chip lies about it')

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
