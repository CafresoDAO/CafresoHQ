#!/usr/bin/env python3
"""Every [[wikilink]] was an exact-stem recall test with no answer key.

The Library's graph is BUILT from wikilinks, and typing one offered
nothing: no picker, no spelling check, nothing to say a stem was
shared. A mistyped stem is a dead link the boss only discovers when
the graph quietly misses an edge.

Now typing `[[` opens a picker over everything the Library holds —
notes by stem, artifacts by name, folders searchable too. Enter/Tab/
click insert the shortest form that resolves: bare stem when unique,
full path when two files share it (the same tie the graph builder
refuses to guess on). An existing `]]` after the caret is never
doubled, and Escape closes the picker WITHOUT closing the note.
Verified live: `[[re` offered the research brief, Enter inserted
`[[research-brief…]]`, Escape left the note open.

Run: python3 scripts/test_typing_a_wikilink_offers_the_library.py
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
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


HARNESS = r'''
%s
%s
%s

const FILES = [
  { path: 'Research/remote-brief.md' },
  { path: 'Research/chart.png' },
  { path: 'Decks/chart.md' },        // two NOTES share this stem
  { path: 'Old/chart.md' },
  { path: 'notes.md' },
];
const out = {};
out.open = _wikiAcQuery('see [[re', 8);
out.closed = _wikiAcQuery('see [[done]] tail', 17);
out.newline = _wikiAcQuery('see [[a\nb', 9);
out.all = _wikiAcCandidates(FILES, '');
out.re = _wikiAcCandidates(FILES, 're');
out.chart = _wikiAcCandidates(FILES, 'chart');
out.folder = _wikiAcCandidates(FILES, 'decks');
out.many = _wikiAcCandidates(
  Array.from({length: 20}, (_, i) => ({ path: 'n' + i + '.md' })), 'n').length;
out.ins = _wikiAcInsert('see [[re tail', 8, 6, 'remote-brief');
out.insClosed = _wikiAcInsert('see [[re]] tail', 8, 6, 'remote-brief');
console.log(JSON.stringify(out));
'''


def main():
    print('typing a wikilink offers the library')
    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')
    parts = [brace_lift(vault, 'const _wikiAcQuery = (text, caret) => {'),
             brace_lift(vault, 'const _wikiAcCandidates = (files, q) => {'),
             brace_lift(vault, 'const _wikiAcInsert = (content, caret, start, insert) => {')]
    p = subprocess.run(['node', '-e', HARNESS % tuple(parts)],
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    out = json.loads(p.stdout.strip().split('\n')[-1])

    check('an open [[ arms the picker with what was typed so far',
          out['open'] == {'q': 're', 'start': 6}, out['open'])
    check('a finished [[link]] never re-arms it', out['closed'] is None)
    check('a newline ends the armed region', out['newline'] is None)

    check('an empty query offers the whole Library, artifacts included',
          len(out['all']) == 5
          and any(c['path'] == 'Research/chart.png' and not c['note']
                  for c in out['all']), out['all'])
    check('the best stem match ranks first',
          out['re'] and out['re'][0]['label'] == 'remote-brief', out['re'])
    check('a stem two notes share completes as a full path — never a guess',
          {c['insert'] for c in out['chart']}
          == {'Decks/chart', 'Old/chart', 'chart.png'}, out['chart'])
    check("an artifact keeps its extension, so it can't collide with a note",
          any(c['insert'] == 'chart.png' and not c['note']
              for c in out['chart']), out['chart'])
    check('a unique note completes as its bare stem',
          out['re'][0]['insert'] == 'remote-brief', out['re'])
    check('a folder name finds what it holds',
          any(c['path'] == 'Decks/chart.md' for c in out['folder']),
          out['folder'])
    check('the list stays digestible', out['many'] == 8, out['many'])

    check('accepting writes the ]] and parks the caret after it',
          out['ins'] == {'content': 'see [[remote-brief]] tail', 'caret': 20},
          out['ins'])
    check("an existing ]] after the caret is never doubled",
          out['insClosed'] == {'content': 'see [[remote-brief]] tail', 'caret': 20},
          out['insClosed'])

    check('both editor textareas carry the picker wiring',
          vault.count('{...editorExtraProps}') == 2
          and vault.count('_acUpdate(e.target); }} />') == 2)
    check('both layouts render the picker box', vault.count('{acBox}') == 2)
    check('Escape is stopped before the note-closing handler hears it',
          "e.key === 'Escape') { e.stopPropagation(); setAc(null); }" in vault)

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
