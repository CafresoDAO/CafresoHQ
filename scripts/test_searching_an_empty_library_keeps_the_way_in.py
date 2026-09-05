#!/usr/bin/env python3
"""A brand-new boss touched the search box and lost the only door in.

The Library pane has exactly three states and was rendering two of them.
`hits === null` is NO SEARCH RUNNING and the pane belongs to the tree — or,
on a first run, to the greeting `#`-numbered entries have been protecting
since the welcome landed:

    Your Library is empty
    Notes, research, decks, documents and images all live here …
    [ Write your first note ]  [ Upload files ]

A non-empty array is results. An EMPTY array is the third thing — a search
that ran and found nothing — and it was folded into "results", because both
render arms asked the question as

    hits ? ( …results… ) : ( …tree or greeting… )

and `[]` is truthy in JavaScript. Searching an empty Library sets `hits` to
`[]`, so the first exploratory poke at the search box replaced the whole
greeting with

    0 result(s)                                            ✕

A bare zero and a dismiss button. The one call to action a brand-new office
has — the button that was going to get the first note written — was gone,
and nothing on screen said the Library was empty or that the query was not
the problem. The identical shape stood in BOTH layouts (the desktop
three-column pane and the mobile FILES tab), which is why the counts below
are pinned at 2.

`vaultNoHitsNote(query, fileCount)` says the no-match case in words and
splits it: an empty Library is told the Library is why, not the query, and
the greeting is rendered underneath the sentence so the way forward
survives the search. A Library with files in it is told how many it has and
offered the clear.

Run: python3 scripts/test_searching_an_empty_library_keeps_the_way_in.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / 'views' / 'vault.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Comments first — this file's fix is EXPLAINED in a comment that
    quotes the bad pattern verbatim, and the greps below would otherwise
    fail the correct code on its own tombstone."""
    src = re.sub(r'\{/\*.*?\*/\}', '', src, flags=re.S)
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def lift(src, start_marker, end_marker):
    i = src.index(start_marker)
    j = src.index(end_marker, i)
    return src[i:j]


def main():
    print('searching an empty library keeps the way in')
    src = VAULT.read_text(encoding='utf-8')
    bare = strip_comments(src)

    # ── the truthy-empty-array shape is gone from every branch point ────
    check('no render arm asks the two-way question `hits ?` any more',
          not re.search(r'\{hits \?', bare),
          'an empty array is truthy — that arm calls a search that found '
          'nothing "results"')
    check('the three-way is named once and derived from the length',
          re.search(r"const searchState = hits === null \? 'idle' : "
                    r"\(hits\.length \? 'found' : 'none'\)", bare) is not None,
          'searchState must distinguish idle / none / found')
    check('both layouts render results only when there ARE results',
          bare.count("searchState === 'found' ?") == 2,
          'desktop and mobile both had the bug; both have to be fixed')
    check('…and both have a no-match arm of their own',
          bare.count("searchState === 'none' ?") == 2)
    check('…which renders the sentence, not a bare zero',
          bare.count('{noHitsPanel}') == 2)
    check('an empty Library still gets its greeting under the sentence',
          bare.count('{files.length === 0 && emptyTreeState}') == 2,
          'the call to action is the whole point — it must survive a search')

    # The tree arm is untouched: test_an_empty_library_greets_its_first_boss
    # reads both of these out of this file and they must still be here.
    check('the idle arm still swaps the TREE for the greeting, nothing else',
          bare.count('{emptyTreeState || <FolderTree') == 2)
    check('the kind chips still hide when there is nothing to filter',
          bare.count('{files.length > 0 && kindChips}') == 2)

    # Clearing empties the box too, and both ✕ doors go through one place.
    check('clearing the search clears the query as well as the hits',
          re.search(r'const clearSearch = \(\) => \{ setHits\(null\); '
                    r'setQ\(\'\'\); \};', bare) is not None,
          'a query left sitting above a restored tree reads as a live filter')
    check('every ✕ goes through it',
          bare.count('onClick={clearSearch}') == 3
          and 'onClick={()=>setHits(null)}' not in bare,
          bare.count('onClick={clearSearch}'))

    # `setHits([])` on a FAILED search is a different bug this repo already
    # fixed (test_a_failed_search_closed_the_whole_cabinet); an error must
    # still not masquerade as "found nothing".
    check('a failed search still resets to idle, not to no-match',
          "snag('Search failed', e); setHits(null);" in bare
          and 'setHits([])' not in bare,
          'an error is not an empty result set')

    # ── drive the real helper ───────────────────────────────────────────
    if not shutil.which('node'):
        print('  (node not on PATH — skipping the render checks)')
        if FAILS:
            print(f'\nFAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS))
            return 1
        print('\nPASS')
        return 0

    fn = lift(bare, 'function vaultNoHitsNote', '\nfunction ')
    check('the helper is pure and module-level so it can be driven here',
          'return {' in fn and fn.count('return') >= 2 and 'useSV' not in fn,
          len(fn))

    js = ('const SRC = ' + json.dumps(fn) + ';\n' + r'''
const vaultNoHitsNote = new Function(SRC + ' return vaultNoHitsNote;')();
console.log(JSON.stringify({
  brandNew: vaultNoHitsNote('budget', 0),
  // The state the bug actually shipped: the box is poked before anything
  // has ever been typed into a note.
  blankQ:   vaultNoHitsNote('', 0),
  stocked:  vaultNoHitsNote('budget', 12),
  one:      vaultNoHitsNote('budget', 1),
  noQuery:  vaultNoHitsNote(null, 4),
}));
''')
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('the lifted helper runs', False, p.stderr.strip()[:400])
        print('\nFAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    new, stocked, one = r['brandNew'], r['stocked'], r['one']

    check('an empty Library is never told its query failed to match',
          'match for' not in new['title'].lower()
          and 'no match' not in new['title'].lower(), new['title'])
    check('…it is told the Library is the reason',
          'library is empty' in new['sub'].lower(), new['sub'])
    check('…and told plainly that nothing is being hidden from it',
          'hidden' in new['sub'].lower(), new['sub'])
    check('…and the sentence holds up with an empty query too',
          r['blankQ']['title'] == new['title']
          and 'library is empty' in r['blankQ']['sub'].lower()
          and '“”' not in r['blankQ']['sub'],
          r['blankQ'])

    check('a stocked Library IS told the query is what missed',
          'budget' in stocked['title'] and 'no match' in stocked['title'].lower(),
          stocked['title'])
    check('…and how much it is standing in front of',
          '12 files' in stocked['sub'], stocked['sub'])
    check('…singular when there is one of it',
          '1 file ' in one['sub'] and '1 files' not in one['sub'], one['sub'])
    check('…and is offered the clear, which is a route that works',
          'clear the search' in stocked['sub'].lower(), stocked['sub'])
    check('the two situations do not share a sentence',
          new['title'] != stocked['title'] and new['sub'] != stocked['sub'])
    check('a missing query never renders as "undefined"',
          'undefined' not in r['noQuery']['title']
          and 'undefined' not in r['noQuery']['sub'], r['noQuery'])

    print()
    if FAILS:
        print(f'FAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS))
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
