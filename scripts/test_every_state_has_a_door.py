#!/usr/bin/env python3
"""A run the boss stopped on purpose had no chip to find it under.

Measured 2026-08-16, office 9272. The Inbox's filter chips were a
hand-written list — ['active','blocked','failed','completed','all'] —
written when the registry had two terminal states. It has three.
'cancelled' is filed by five call sites: the boss pressing ■ Stop on
their own turn, both dispatch paths, and the @mention and Delegate
catches. `stateCounts` counted every one of those into `c[m.state]` and
no chip ever rendered the number. ACTIVE is "not terminal", so it
excludes them by design; the only way to a run the boss stopped ON
PURPOSE was ALL, mixed in with the whole registry. The empty state
offered "Try widening the state filter" — a widening the chips could
not do.

The fix derives the chips from the one table that decides what terminal
means (MSG_STATES, app/windows.jsx), so a fourth terminal state gets a
door the day it is added rather than the day somebody notices it has
none. The same table now feeds TERMINAL_STATES, which was a second
hand-written copy of the same answer sitting ten lines above the first
— that one happened to be current, but it was one merge away from the
identical bug, and this file no longer holds any hand-written answer to
"is this state finished".

The claim this suite defends is the general one, not the chip: EVERY
state the registry can file is reachable from some filter other than
ALL. So the pills, the derivation and `matchesState` are lifted and run
against the real MSG_STATES table, including a table with a terminal
state that does not exist yet.

Run: python3 scripts/test_every_state_has_a_door.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []

TERM_DECL = re.compile(r'^const TERMINAL_STATES = new Set\((?:.|\n)*?\);', re.M)
PILL_DECL = re.compile(r'^const FILTER_PILLS = .*?;', re.M | re.S)
MATCHES = 'const matchesState = (m) => {'
COUNTS = 'const stateCounts = ('
MAP_SITE = '{FILTER_PILLS.map(s => ('
IMPORT = "import { MSG_STATES } from '../app/windows.jsx';"
# The sentence the chips have to be able to keep. It promises a wider
# filter exists; before this, for a cancelled record, it did not.
HINT = 'Try widening the state filter'


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'\{/\*.*?\*/\}', '', src, flags=re.S)
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_from(src, i):
    """The balanced {…} or (…) block starting at src[i]."""
    if i < 0 or i >= len(src):
        return ''
    close = {'{': '}', '(': ')'}.get(src[i])
    if not close:
        return ''
    depth = 0
    for j in range(i, len(src)):
        if src[j] == src[i]:
            depth += 1
        elif src[j] == close:
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    return ''


def lift_decl(src, decl):
    """`const foo = <opener>…<closer>…;` lifted whole, by its head.

    `decl` ends ON the opening bracket, so the block is taken from that
    same character and the head is re-joined WITHOUT it — glueing a head
    that already ends in `{` to a balanced `{…}` leaves one bracket open,
    and node reports that as a syntax error at the end of the script.
    """
    i = src.find(decl)
    if i < 0:
        return ''
    body = brace_from(src, i + len(decl) - 1)
    return (decl[:-1] + body) if body else ''


def lift_iife(src, head):
    """`const foo = (() => { … })();` — the paren group is brace-matched,
    and the CALL that follows it is re-attached, because the group itself
    stops at its own closing paren and a lifted `(() => {…})` bound to a
    const is a function, not the value the modal reads."""
    i = src.find(head)
    if i < 0:
        return ''
    grp = brace_from(src, i + len(head) - 1)
    return (head[:-1] + grp + '();') if grp else ''


def main():
    print('every state has a door')
    if not shutil.which('node'):
        print('SKIP — node not on PATH')
        return 0

    collab = (ROOT / 'modals' / 'collab.jsx').read_text(encoding='utf-8')
    windows = (ROOT / 'app' / 'windows.jsx').read_text(encoding='utf-8')
    cbare = strip_comments(collab)

    # ── one table decides what "finished" means ─────────────────────────
    check('the inbox reads the state table it filters by', IMPORT in collab,
          'the chips drifted because this file answered terminality itself')
    term = TERM_DECL.search(cbare)
    pills = PILL_DECL.search(cbare)
    check('TERMINAL_STATES is declared once', bool(term)
          and cbare.count('const TERMINAL_STATES') == 1)
    check('FILTER_PILLS is declared once', bool(pills)
          and cbare.count('const FILTER_PILLS') == 1)
    check('both are derived, neither is a hand-written list',
          bool(term) and bool(pills)
          and 'MSG_STATES' in term.group(0)
          and 'TERMINAL_STATES' in pills.group(0)
          and "'completed'" not in term.group(0)
          and "'completed'" not in pills.group(0),
          [term.group(0) if term else None, pills.group(0) if pills else None])

    # A hand-written terminal list anywhere else in the file is the same
    # bug with a different name — that is exactly how this one survived a
    # rename: two copies, ten lines apart, and only one of them updated.
    strays = [a for a in re.findall(r'\[[^\[\]\n]*\]', cbare)
              if "'completed'" in a and "'failed'" in a]
    check('no other hand-written list of finished states survives',
          not strays, strays)

    check('the chips render from the derivation', cbare.count(MAP_SITE) == 1,
          f'{cbare.count(MAP_SITE)} map sites')
    check('the empty state still offers a wider filter', HINT in collab)

    # ── drive the real derivation against the real table ────────────────
    states_at = windows.find('const MSG_STATES = {')
    states_src = lift_decl(windows, 'const MSG_STATES = {')
    check('MSG_STATES lifts', states_at != -1 and states_src.endswith('}'))

    matches_src = lift_decl(cbare, MATCHES)
    counts_src = lift_iife(cbare, COUNTS)
    check('matchesState lifts', matches_src.endswith('}'), matches_src[-40:])
    check('stateCounts lifts', counts_src.endswith('})();'), counts_src[-40:])

    js = ('const STATES_SRC = ' + json.dumps(states_src) + ';\n'
          + 'const TERM_SRC = ' + json.dumps(term.group(0) if term else '') + ';\n'
          + 'const PILL_SRC = ' + json.dumps(pills.group(0) if pills else '') + ';\n'
          + 'const MATCH_SRC = ' + json.dumps(matches_src) + ';\n'
          + 'const COUNT_SRC = ' + json.dumps(counts_src) + ';\n'
          + r'''
/* Re-derive the shipped chips against an arbitrary state table. Both
   declarations read MSG_STATES as a free variable, so handing them a
   different table is the whole experiment. */
const derive = (extra) => new Function('MSG_STATES',
  TERM_SRC + '\n' + PILL_SRC + '\n'
  + 'return { terminal: [...TERMINAL_STATES], pills: FILTER_PILLS };'
)(Object.assign({}, TABLE, extra || {}));

const TABLE = new Function(STATES_SRC + '; return MSG_STATES;')();

/* The filter, exactly as the modal builds it: one closure per chip. */
const filterFor = (filterState, states) => new Function(
  'filterState', 'states',
  MATCH_SRC + ';\n return matchesState;')(filterState, states);

const countsFor = (all, states) => new Function(
  'all', 'states', COUNT_SRC + '\n return stateCounts;')(all, states);

/* One message per state — a registry that has been through everything. */
const oneEach = Object.keys(TABLE).map((s, i) => ({ id: 'm' + i, state: s }));

/* For each state: which chips (other than ALL) would show it? */
const doors = (table, pills) => {
  const out = {};
  for (const s of Object.keys(table)) {
    out[s] = pills.filter(p => p !== 'all'
      && filterFor(p, table)({ state: s }));
  }
  return out;
};

const base = derive(null);
const grown = derive({ archived: { label: 'Archived', color: '#000', terminal: true } });

console.log(JSON.stringify({
  table: Object.keys(TABLE),
  terminal: base.terminal,
  pills: base.pills,
  doors: doors(TABLE, base.pills),
  counts: countsFor(oneEach, TABLE),
  grownPills: grown.pills,
  grownDoors: doors(Object.assign({}, TABLE,
    { archived: { terminal: true } }), grown.pills),
  /* The bug, reproduced against the OLD chip list: with the hardcoded
     pills, a cancelled record had no door but ALL. */
  oldDoors: doors(TABLE, ['active', 'blocked', 'failed', 'completed', 'all']),
}));
''')
    p = subprocess.run(['node', '--input-type=module', '-e',
                        '(async () => {' + js
                        + '})().catch(e => { console.error(e); process.exit(1); });'],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('the lifted chips run', False, p.stderr.strip()[:400])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    # ── the regression itself ───────────────────────────────────────────
    check("a cancelled run has a door that isn't ALL",
          r['doors'].get('cancelled') == ['cancelled'],
          r['doors'].get('cancelled'))
    check('…and the old hardcoded list is why it did not',
          r['oldDoors'].get('cancelled') == [],
          'the repro must still reproduce, or this suite proves nothing')

    # ── the general claim ───────────────────────────────────────────────
    doorless = [s for s, d in r['doors'].items() if not d]
    check('EVERY state the registry can file is reachable without ALL',
          not doorless, doorless)
    check('every terminal state has its own chip',
          all(s in r['pills'] for s in r['terminal']),
          [s for s in r['terminal'] if s not in r['pills']])
    check('the unfinished states ride ACTIVE, and are not each given a chip',
          all(r['doors'][s] == ['active'] for s in r['table']
              if s not in r['terminal'] and s != 'blocked'),
          {s: r['doors'][s] for s in r['table'] if s not in r['terminal']})

    # ── blocked is named on purpose ─────────────────────────────────────
    check('blocked keeps its own chip even though ACTIVE covers it',
          'blocked' in r['pills'] and 'blocked' not in r['terminal']
          and r['doors']['blocked'] == ['active', 'blocked'],
          r['doors'].get('blocked'))

    # ── shape of the row ────────────────────────────────────────────────
    check('ACTIVE leads and ALL closes', r['pills'][0] == 'active'
          and r['pills'][-1] == 'all', r['pills'])
    check('no chip is offered twice', len(set(r['pills'])) == len(r['pills']),
          r['pills'])

    # ── the count and the chip agree ────────────────────────────────────
    # Every number the modal computes must have somewhere to be shown, and
    # every chip that shows a number must be one the counter knows about.
    # A chip with `stateCounts[s] == null` renders a bare label — which is
    # what an undercounted state looked like from the outside.
    counted = {k for k in r['counts'] if k != 'all'}
    check('every chip is a key the counter produces',
          all(p in r['counts'] for p in r['pills']),
          [p for p in r['pills'] if p not in r['counts']])
    check('every counted state is reachable from some chip',
          all(k == 'active' or r['doors'].get(k) for k in counted),
          [k for k in counted if k != 'active' and not r['doors'].get(k)])

    # ── the state that does not exist yet ───────────────────────────────
    check('a terminal state added tomorrow gets a chip with no edit here',
          'archived' in r['grownPills']
          and r['grownDoors'].get('archived') == ['archived'],
          [r['grownPills'], r['grownDoors'].get('archived')])
    check('…and it lands before ALL, not after it',
          r['grownPills'][-1] == 'all', r['grownPills'])

    if FAILS:
        print(f'FAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS))
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
