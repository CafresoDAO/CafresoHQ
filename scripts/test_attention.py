#!/usr/bin/env python3
"""The attention queue (app/attention.jsx) — pure-function suite.

"N need you" is the loudest number in the product, and it drives three
surfaces (office pill, Team nav badge, inbox tab). It must answer "how many
things need me", not "how many times was something reported" — the session
that motivated this had 21 unread rows and exactly one decision behind them.

The checks pin both halves of that promise:
  - identical reports from one coworker collapse to one item with a count
  - genuinely different problems NEVER collapse (that would hide work)

Same node-under-Python pattern as the other jsx suites.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app' / 'attention.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def run_js(cases_js):
    text = SRC.read_text(encoding='utf-8')
    src = '\n'.join(ln for ln in text.split('\n')
                    if not ln.startswith('import ') and not ln.startswith('export '))
    proc = subprocess.run(['node', '--input-type=module', '-e', src + '\n' + cases_js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


CASES = r'''
const R = {};
const snag = "hit a snag — that brain isn't signed in yet";
const A = (id, agentId, text, extra) => Object.assign(
  { id, agentId, text, priority: 'attention', unread: true }, extra || {});

// The measured case: one cause, many reports, several coworkers.
const real = [
  A('1','a5', snag), A('2','a5', snag), A('3','a5', snag),
  A('4','a7', snag), A('5','a7', snag),
  A('6','a1', snag),
];
R.realGroups = groupAttention(real).length;
R.realCounts = groupAttention(real).map(g => g.count);
R.realCount  = attentionCount(real, []);

// Newest-first order is preserved, and each group keeps the NEWEST entry —
// that's the one a Retry acts on.
R.firstKeepsNewest = groupAttention(real)[0].entry.id === '1';
R.groupIds         = groupAttention(real)[0].ids;

// Different problems must never merge, even from the same coworker.
const distinct = [
  A('1','a1','failed "Draft the brief" — back to inbox'),
  A('2','a1','failed "Ship the page" — back to inbox'),
];
R.distinctStay = groupAttention(distinct).length;

// Same sentence, different coworkers = different items (each is stuck).
R.perAgent = groupAttention([A('1','a1',snag), A('2','a2',snag)]).length;

// Only unread attention rows count; routine chatter and read rows don't.
const mixed = [
  A('1','a1',snag),
  A('2','a1',snag,{ unread: false }),
  { id:'3', agentId:'a1', text:'picked up "x"', priority:'routine', unread:true },
];
R.mixedCount = attentionCount(mixed, []);

// Approvals are always their own decision, never folded together.
R.withApprovals = attentionCount([A('1','a1',snag)], [{id:'p1'},{id:'p2'}]);

// Degenerate inputs must not throw or invent items.
R.emptyCount = attentionCount([], []);
R.nullCount  = attentionCount(null, null);
R.nullGroups = groupAttention(null).length;
R.holeyGroups = groupAttention([null, A('1','a1',snag), undefined]).length;

// An entry with no agent still groups by its text rather than vanishing.
R.noAgent = groupAttention([
  { id:'1', text:'something', priority:'attention', unread:true },
  { id:'2', text:'something', priority:'attention', unread:true },
]).length;

console.log(JSON.stringify(R));
'''


def main():
    print('attention queue — how many things need the boss')
    if not shutil.which('node'):
        print('  SKIP  node not available')
        return 0
    out = run_js(CASES)

    check('six reports of one cause collapse to three coworkers',
          out['realGroups'] == 3, repr(out['realGroups']))
    check('...each carrying its own repeat count',
          out['realCounts'] == [3, 2, 1], repr(out['realCounts']))
    check('...and the headline number counts problems, not events',
          out['realCount'] == 3, repr(out['realCount']))
    check('a group keeps the NEWEST entry (what Retry acts on)',
          out['firstKeepsNewest'])
    check('...and remembers every entry it stands for',
          out['groupIds'] == ['1', '2', '3'], repr(out['groupIds']))

    check('two different stuck tasks NEVER merge',
          out['distinctStay'] == 2, repr(out['distinctStay']))
    check('same sentence from two coworkers stays two items',
          out['perAgent'] == 2, repr(out['perAgent']))

    check('read rows and routine chatter are not counted',
          out['mixedCount'] == 1, repr(out['mixedCount']))
    check('each pending approval is its own decision',
          out['withApprovals'] == 3, repr(out['withApprovals']))

    check('empty input counts zero', out['emptyCount'] == 0)
    check('null input tolerated', out['nullCount'] == 0)
    check('null list groups to nothing', out['nullGroups'] == 0)
    check('holes in the list are skipped, not counted',
          out['holeyGroups'] == 1, repr(out['holeyGroups']))
    check('an entry with no agent still groups by text',
          out['noAgent'] == 1, repr(out['noAgent']))

    print()
    if FAILS:
        print(f'attention queue: {len(FAILS)} failure(s)')
        return 1
    print('attention queue: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
