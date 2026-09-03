#!/usr/bin/env python3
"""The board said "Nothing waiting" over an inbox that was holding work.

Measured live (#154) on Tasks, with one task on the board:

    search box: "zzzznomatch"
    header:     0 OF 1
    INBOX:      "Nothing waiting — hit + NEW to add one."

The first line is a claim about the office and it was being made about the
search box. Then the advice underneath it was followed:

    + NEW → "Order more coffee" → ADD
    header:     0 OF 2
    INBOX:      "Nothing waiting — hit + NEW to add one."

The task was real -- clearing the search showed it sitting in the inbox --
but the only thing that moved on screen was a number in the header, and the
same instruction was still there inviting the boss to do it again. That is a
loop that quietly stacks up duplicates nobody can see.

The board already had a comment about exactly this shape of mistake, one
message over:

    /* `tasks` here is the FILTERED list ... otherwise a search matching
       nothing would greet an established boss with "No tasks yet". */

The onboarding message had been given the unfiltered count to check. The
"Nothing waiting" message next to it never was.

TWO FIXES, ONE FACT -- the board did not know a filter was on:

  · `TasksView` hands down `hiddenByStatus`, a per-COLUMN count of what the
    filters are keeping out, and each empty column says so instead of
    asserting the office is empty. Per column and not board-wide on purpose:
    an empty inbox beside five hidden DONE tasks and an inbox with five
    hidden tasks want opposite messages, and `totalCount - tasks.length`
    cannot tell them apart.
  · Adding a task drops whichever filter would hide it -- and only that one.
    This is not a new rule; it is the rule the highlight effect a few lines
    above already applies to a task arriving from the Calendar ("Whichever
    filter would hide the requested task, drop it").

WHAT THIS FILE CHECKS

It lifts the real `hides`, `filtered`, `hiddenByStatus` and `addVisible` out
of the shipped `TasksView` and runs them under Node -- the actual bodies, not
a restatement of them. Only React's state binding is stubbed: `q` and
`showDone` become plain variables and the setters record what was dropped,
because that is precisely the question ("which filter did the add clear?").

The wrong direction is weighted at least as heavily as the bug. Clearing a
search the boss is still using, or flipping "show completed" back on because
they added something unrelated, would be its own small betrayal.

Run: python3 scripts/test_the_board_admits_it_is_filtering.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / 'views' / 'core.jsx'
FEATURES = ROOT / 'features.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift(src, name):
    """One `const <name> = ...;` from inside TasksView, to its depth-0 `;`.

    Indented, unlike a module-scope const, so the anchor allows leading
    whitespace. Braces, parens and brackets are all counted, because these
    bodies contain object literals, arrow functions and a `useMV(fn, [deps])`
    call whose deps array would otherwise close the scan early.
    """
    m = re.search(r'^[ \t]*const %s = ' % re.escape(name), src, re.M)
    if not m:
        return None
    depth, i = 0, m.end()
    while i < len(src):
        c = src[i]
        if c in '({[':
            depth += 1
        elif c in ')}]':
            depth -= 1
        elif c == ';' and depth == 0:
            return src[m.start():i + 1]
        i += 1
    return None


# The scenarios, and why each one is here. `add` is the task handed to
# `addVisible`; `expect` is which filters must have been dropped.
CASES = [
    dict(name='measured', q='zzzznomatch', showDone=True,
         add=dict(status='inbox', title='Order more coffee', detail=''),
         clearQ=True, clearDone=False,
         why='the live reproduction: a search matching nothing, then + NEW'),
    dict(name='matching-search', q='coffee', showDone=True,
         add=dict(status='inbox', title='coffee grinder filters', detail=''),
         clearQ=False, clearDone=False,
         why='the new task matches, so the search is still doing its job'),
    dict(name='matches-via-detail', q='invoice', showDone=True,
         add=dict(status='inbox', title='Chase Acme', detail='the invoice'),
         clearQ=False, clearDone=False,
         why='the filter reads detail as well as title, and so must this'),
    dict(name='case-insensitive', q='COFFEE', showDone=True,
         add=dict(status='inbox', title='order more coffee', detail=''),
         clearQ=False, clearDone=False,
         why='a boss typing in caps has not stopped matching'),
    dict(name='hidden-done', q='', showDone=False,
         add=dict(status='done', title='Ship it', detail=''),
         clearQ=False, clearDone=True,
         why='completed hidden, and the new task is completed'),
    dict(name='unrelated-toggle', q='', showDone=False,
         add=dict(status='inbox', title='Ship it', detail=''),
         clearQ=False, clearDone=False,
         why='"show completed" is off but hides nothing here — leave it'),
    dict(name='both-filters', q='zzzznomatch', showDone=False,
         add=dict(status='done', title='Ship it', detail=''),
         clearQ=True, clearDone=True,
         why='both filters hide it, so both have to go'),
    dict(name='whitespace-query', q='   ', showDone=True,
         add=dict(status='inbox', title='Order more coffee', detail=''),
         clearQ=False, clearDone=False,
         why='a box holding only spaces filters nothing; `q` and `q.trim()` '
             'must not disagree about that'),
]

# One board, deliberately lopsided: an inbox that a search can empty, and a
# DONE column that the toggle can empty, so a board-wide count could never
# stand in for the per-column ones.
BOARD = [
    dict(id='a', status='inbox', title='Order more coffee', detail=''),
    dict(id='b', status='inbox', title='Chase Acme', detail='the invoice'),
    dict(id='c', status='doing', title='Draft the deck', detail=''),
    dict(id='d', status='done', title='Ship it', detail=''),
    dict(id='e', status='done', title='Old invoice', detail=''),
]

PROBE = r'''
const OUT = { cases: {}, counts: {}, lists: {} };

// Only React's state binding is stubbed. `hides`, `filtered`,
// `hiddenByStatus` and `addVisible` below are the shipped bodies.
const useMV = (fn) => fn();

for (const c of CASES) {
  let q = c.q, showDone = c.showDone;
  const dropped = { q: false, showDone: false };
  const setQ = (v) => { dropped.q = true; q = v; };
  const setShowDone = (v) => { dropped.showDone = true; showDone = v; };
  const added = [];
  const onAdd = (t) => added.push(t);
  const tasks = [];
  __BODIES__
  addVisible(c.add);
  OUT.cases[c.name] = { dropped, added: added.length, q, showDone };
}

// The per-column counts and the list, on one fixed board.
for (const [label, q0, showDone0] of [
  ['no-filter',       '',            true],
  ['search-no-match', 'zzzznomatch', true],
  ['search-invoice',  'invoice',     true],
  ['hide-completed',  '',            false],
]) {
  let q = q0, showDone = showDone0;
  const setQ = () => {}, setShowDone = () => {}, onAdd = () => {};
  const tasks = BOARD;
  __BODIES__
  OUT.counts[label] = hiddenByStatus;
  OUT.lists[label] = filtered.map(t => t.id);
}

// addVisible must not throw on nothing, and must always forward.
{
  let q = 'zzzznomatch', showDone = true;
  const setQ = () => {}, setShowDone = () => {};
  const added = [];
  const onAdd = (t) => added.push(t);
  const tasks = [];
  __BODIES__
  let threw = false;
  try { addVisible(null); } catch (e) { threw = true; }
  OUT.nullSafe = !threw;
  OUT.nullForwarded = added.length;
}
console.log(JSON.stringify(OUT));
'''


def run_probe(bodies):
    tmp = ROOT / '.board-filter-probe-tmp'
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        js = ('const CASES = %s;\nconst BOARD = %s;\n'
              % (json.dumps(CASES), json.dumps(BOARD))) \
            + PROBE.replace('__BODIES__', bodies)
        (tmp / 'probe.js').write_text(js, encoding='utf-8')
        p = subprocess.run([shutil.which('node') or 'node', str(tmp / 'probe.js')],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            return None, 'node: ' + p.stderr.strip()[:400]
        return json.loads(p.stdout.strip().splitlines()[-1]), None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print('the board admits it is filtering')
    if not shutil.which('node'):
        print('  SKIP  node not available — cannot run the real handlers')
        return 0

    core = CORE.read_text(encoding='utf-8')
    parts = []
    for name in ('hides', 'filtered', 'hiddenByStatus', 'addVisible'):
        body = lift(core, name)
        if body is None:
            check(f'`{name}` can be lifted from views/core.jsx', False,
                  'TasksView no longer defines it under that name — this file '
                  'drives the real bodies, so it cannot be repaired by '
                  'guessing what replaced it')
            print('\nboard filtering: nothing to drive')
            return 1
        parts.append(body)
    bodies = '\n'.join(parts)

    r, err = run_probe(bodies)
    if r is None:
        print('  FAIL  could not run the handlers: ' + str(err))
        return 1

    print('1. adding a task drops the filter that would hide it')
    for c in CASES:
        got = r['cases'][c['name']]
        want = {'q': c['clearQ'], 'showDone': c['clearDone']}
        check(f'{c["name"]}: {c["why"]}', got['dropped'] == want,
              f'dropped={got["dropped"]} expected={want}')
        check(f'{c["name"]}: the task still reached the office',
              got['added'] == 1,
              f'onAdd called {got["added"]} times — clearing a filter must '
              'never be at the cost of actually saving the task')

    print('2. …and nothing else')
    check('a null add neither throws nor is swallowed',
          r['nullSafe'] is True and r['nullForwarded'] == 1,
          f'safe={r["nullSafe"]} forwarded={r["nullForwarded"]}')

    print('3. what each column is hiding, counted per column')
    # The whole reason the count is not board-wide: these two rows differ.
    expect = {
        'no-filter':       {},
        'search-no-match': {'inbox': 2, 'doing': 1, 'done': 2},
        'search-invoice':  {'inbox': 1, 'doing': 1, 'done': 1},
        'hide-completed':  {'done': 2},
    }
    for label, want in expect.items():
        check(f'{label}: hidden per column is {want}',
              r['counts'][label] == want, f'got {r["counts"][label]}')
    check('an empty inbox beside hidden DONE work is not the same situation',
          r['counts']['hide-completed'].get('inbox', 0) == 0
          and r['counts']['hide-completed'].get('done', 0) == 2,
          'the two cases a board-wide difference cannot tell apart, which is '
          'why `hiddenByStatus` exists at all')

    print('4. the list and the counts come from the same rule')
    for label, want in (('no-filter', ['a', 'b', 'c', 'd', 'e']),
                        ('search-no-match', []),
                        ('search-invoice', ['b', 'e']),
                        ('hide-completed', ['a', 'b', 'c'])):
        check(f'{label}: the board shows {want}', r['lists'][label] == want,
              f'got {r["lists"][label]}')
    for label in expect:
        shown, hidden = len(r['lists'][label]), sum(r['counts'][label].values())
        check(f'{label}: shown + hidden accounts for every task',
              shown + hidden == len(BOARD),
              f'{shown} + {hidden} != {len(BOARD)} — the list and the counts '
              'have drifted apart, which is the failure `hides` exists to '
              'make impossible')

    print('5. the empty states actually read it')
    feat = FEATURES.read_text(encoding='utf-8')
    code = re.sub(r'/\*[\s\S]*?\*/', '', feat)
    check('the board takes the per-column counts as a prop',
          'hiddenByStatus = null' in code and 'hiddenByStatus || {}' in code,
          'features.jsx: TaskBoard has to be told; it only ever sees the '
          'filtered list')
    check('the view hands them down',
          'hiddenByStatus={hiddenByStatus}' in re.sub(r'/\*[\s\S]*?\*/', '', core),
          'views/core.jsx: computed and then not passed is the same as not '
          'computed')
    check('every empty column checks them before speaking',
          len(re.findall(r'hidden\[key\] > 0', code)) == 2,
          'features.jsx: the inbox message was the one that lied, but the '
          'other columns said nothing about hidden work either — both '
          'branches ask')
    check('"Nothing waiting" is now only reachable when nothing is hidden',
          re.search(r'hidden\[key\] > 0[\s\S]{0,200}?Nothing waiting', code)
          is not None,
          'features.jsx: the claim about the office must sit on the false '
          'side of the filter check, not above it')
    check('the board does not fall back on a board-wide difference',
          'totalCount - tasks.length' not in code,
          'features.jsx: that arithmetic is exactly what cannot tell an '
          'empty inbox from a filtered one')
    check('the new message says what is happening and does not instruct',
          'hidden by the filters above' in code
          and not re.search(r'hidden by the filters above[\s\S]{0,80}\+ NEW', code),
          'features.jsx: "+ NEW" under a filtered-empty column is the advice '
          'that produced an invisible task in the first place')

    print()
    if FAILS:
        print(f'board filtering: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('board filtering: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
