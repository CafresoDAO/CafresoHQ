#!/usr/bin/env python3
"""A brand-new office opened 📬 INBOX and was told its filter was hiding things.

`📬 INBOX` is a topbar button rendered from the first page load, so a boss
who has hired nobody and sent nothing reaches this room long before it can
hold anything. `MessageRegistry.list()` answers `[]`, every filter chip
above the panel reads 0, the header reads

    0 threads · 0 messages total

— and the panel underneath read:

    No messages match this filter.
    Try widening the state filter, or @-mention a coworker to start a
    thread.

Nothing was being filtered. "match" asserts that messages exist and that
this filter is what keeps them off screen, which the counts on the same
screen deny; and the way out it named cannot work, because ALL is already
0 — widening the filter shows the identical nothing. modals/collab.jsx has
been here before and says so in its own comment about the `cancelled`
records no chip could reach: "the empty state told them to 'try widening
the state filter' — a widening the chips could not do." That was fixed by
giving the state a chip; the case where there is no state to reach at all
was left standing.

The second route failed the same way one level down: "@-mention a
coworker" on an office with nobody on the roster — the shape
`noCrewNote(agents)` was written for on the missions form.

`inboxEmptyNote(total, filtered, agents)` splits the three situations and
is driven here verbatim under node against an empty registry, an empty
registry with a crew, and a real registry behind a filter.

Run: python3 scripts/test_an_empty_inbox_does_not_blame_the_filter.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []

# The sentence that was wrong on an empty registry. It stays in the file —
# it is right, and only right, when a filter really is narrowing the view —
# so this is pinned by CONTEXT below, not by absence.
FILTER_HINT = 'Try widening the state filter'


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Comments first — this file's own explanation quotes the bad copy."""
    src = re.sub(r'\{/\*.*?\*/\}', '', src, flags=re.S)
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def lift(src, start_marker, end_marker):
    i = src.index(start_marker)
    j = src.index(end_marker, i)
    return src[i:j]


def main():
    print('an empty inbox does not blame the filter')
    if not shutil.which('node'):
        print('SKIP — node not on PATH')
        return 0

    collab_src = (ROOT / 'modals' / 'collab.jsx').read_text(encoding='utf-8')
    app_src = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    bare = strip_comments(collab_src)
    app_bare = strip_comments(app_src)

    # ── the room is wired to the thing that answers it ──────────────────
    check('the empty panel asks one helper what to say',
          'inboxEmptyNote(all.length, isFiltered, agents)' in bare,
          'the empty state is hand-written inline again')
    check('the helper is pure and module-level so it can be driven here',
          re.search(r'^function inboxEmptyNote\(total, filtered, agents\)',
                    bare, re.M) is not None,
          'inboxEmptyNote must not close over component state')
    check('the modal is handed the roster',
          re.search(r'function InboxModal\(\{[^}]*agents = \[\]', bare) is not None,
          'without it the empty room cannot tell a hired office from an empty one')
    check('…and app.jsx actually passes it',
          re.search(r'<InboxModal\b(?:(?!/>).)*agents=\{agents\}', app_bare, re.S)
          is not None,
          'app.jsx renders the inbox with no roster — the prop default would '
          'silently make every office look unhired')

    # The old copy must not survive as a literal anywhere in the render: the
    # bug was one sentence standing in for three situations.
    render = bare[bare.index('function InboxModal'):]
    check('no unconditional "@-mention a coworker" is left in the room',
          '@-mention a coworker to start a thread' not in render,
          'that route was printed to offices with nobody on the roster')

    # ── drive the real function ─────────────────────────────────────────
    fn = lift(bare, 'function inboxEmptyNote', 'function InboxModal')
    check('the helper lifts', 'return {' in fn and fn.count('return') >= 3, len(fn))

    js = ('const SRC = ' + json.dumps(fn) + ';\n' + r'''
const inboxEmptyNote = new Function(SRC + ' return inboxEmptyNote;')();
const CREW = [{ id: 'a1', name: 'Mira' }];
console.log(JSON.stringify({
  fresh:     inboxEmptyNote(0, false, []),
  freshCrew: inboxEmptyNote(0, false, CREW),
  filtered:  inboxEmptyNote(7, true, CREW),
  filtered1: inboxEmptyNote(1, true, CREW),
  // A missing roster must read as "we did not look", never as "empty" —
  // but the sentence still has to be safe, so it takes the no-crew branch
  // only when the roster is genuinely an empty array.
  noRoster:  inboxEmptyNote(0, false, undefined),
  weird:     inboxEmptyNote(3, false, CREW),
}));
''')
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('the lifted helper runs', False, p.stderr.strip()[:400])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    fresh, fresh_crew = r['fresh'], r['freshCrew']
    filtered, filtered1 = r['filtered'], r['filtered1']

    check('an empty registry does not claim anything failed to match',
          'match' not in fresh['title'].lower()
          and 'match' not in fresh['sub'].lower(),
          fresh)
    check('…and says out loud that no filter is hiding anything',
          'no filter' in fresh['sub'].lower()
          and 'hiding' in fresh['sub'].lower(), fresh['sub'])
    check('…and never sends an empty registry to widen the filter',
          FILTER_HINT not in fresh['sub'] and FILTER_HINT not in fresh_crew['sub'],
          [fresh['sub'], fresh_crew['sub']])

    check('an office with nobody hired is told to hire, not to @-mention',
          'hire' in fresh['sub'].lower() and '@-mention' not in fresh['sub'],
          fresh['sub'])
    check('an office WITH a coworker gets the route it can actually take',
          '@-mention' in fresh_crew['sub'] and 'hire' not in fresh_crew['sub'].lower(),
          fresh_crew['sub'])
    check('the two empty-registry sentences differ only in the route',
          fresh['title'] == fresh_crew['title'] and fresh['sub'] != fresh_crew['sub'],
          [fresh['title'], fresh_crew['title']])

    # The sentence that WAS wrong is right here, and has to survive: two
    # existing tests (test_every_state_has_a_door,
    # test_the_inbox_header_counts_one_thing) read it out of this file.
    check('a real filter over a real registry still names the filter',
          filtered['title'] == 'No messages match this filter.'
          and FILTER_HINT in filtered['sub'], filtered)
    check('…and now says how many the filter is standing in front of',
          '7 messages are in here' in filtered['sub'], filtered['sub'])
    check('…singular when there is one of it',
          '1 message is in here' in filtered1['sub'], filtered1['sub'])

    check('an absent roster is not read as an unhired office by accident',
          r['noRoster']['sub'] == fresh['sub'],
          'undefined and [] are the same claim here — both mean no coworker '
          'to @-mention')
    check('the impossible case says what is known instead of blaming a filter '
          'that is off',
          FILTER_HINT not in r['weird']['sub'] and '3 messages' in r['weird']['sub'],
          r['weird'])

    print()
    if FAILS:
        print(f'FAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS))
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
