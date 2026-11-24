#!/usr/bin/env python3
"""A coworker's rank is counted from finished jobs in the ledger and nothing else.

The ladder is the public agent card's (Rookie, Working, Proven, Veteran, Legend at
0, 1, 3, 15 and 50 jobs), so a coworker reads the same in the office and on its
card. Snags never move it, and the day's quest counts come from the same ledger.
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = r"""
import { xpRank, xpToday, xpStats } from './experience.bundle.mjs';
const out = {};
out.ranks = [0, 1, 2, 3, 14, 15, 49, 50, 500].map(n => { const r = xpRank(n); return [n, r.name, r.tier, r.toNext, r.pct]; });
out.junk = [xpRank(-3).name, xpRank('x').name, xpRank(2.9).name];
const now = new Date(2026, 10, 24, 15, 0, 0).getTime();
const day = 86400000;
const ledger = [
  { at: now - 3 * day, agentId: 'a', kind: 'task', outcome: 'done' },
  { at: now - 2 * day, agentId: 'a', kind: 'task', outcome: 'snag' },
  { at: now - 3600000, agentId: 'a', kind: 'brief', outcome: 'done' },
  { at: now - 1800000, agentId: 'a', kind: 'brief', outcome: 'done' },
  { at: now - 1000, agentId: 'b', kind: 'task', outcome: 'snag' },
];
out.rankA = xpRank(xpStats(ledger, 'a').jobs).name;
out.rankB = xpRank(xpStats(ledger, 'b').jobs).name;
out.today = xpToday(ledger, [{ status: 'inbox' }, { status: 'doing' }, { status: 'done' }], [{ id: 'a', name: 'Ada' }, { id: 'b', name: 'Bo' }], now);
out.empty = xpToday(null, null, null, now);
console.log(JSON.stringify(out));
"""
FAILS = []


def check(name, ok, detail=''):
    print(('  ok    ' if ok else '  FAIL  ') + name + ('' if ok else f' — {detail}'))
    if not ok:
        FAILS.append(name)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        bundle = os.path.join(tmp, 'experience.bundle.mjs')
        subprocess.run(['npx', '--no-install', 'esbuild', os.path.join(ROOT, 'app', 'experience.jsx'), '--bundle',
                        '--format=esm', '--log-level=error', f'--outfile={bundle}'], cwd=ROOT, check=True)
        with open(os.path.join(tmp, 'run.mjs'), 'w', encoding='utf-8') as f:
            f.write(JS)
        res = subprocess.run(['node', 'run.mjs'], cwd=tmp, capture_output=True, text=True, check=True)
    out = json.loads(res.stdout)
    names = {n: name for n, name, *_ in out['ranks']}
    check('the ladder turns at 1, 3, 15 and 50 finished jobs',
          [names[n] for n in (0, 1, 2, 3, 14, 15, 49, 50, 500)] ==
          ['Rookie', 'Working', 'Working', 'Proven', 'Proven', 'Veteran', 'Veteran', 'Legend', 'Legend'], names)
    by = {n: (to, pct) for n, _, _, to, pct in out['ranks']}
    check('a Proven coworker with 3 jobs is 12 from Veteran and 0% along', by[3] == [12, 0] or tuple(by[3]) == (12, 0), by[3])
    check('the top rank is full and asks for nothing more', tuple(by[500]) == (0, 100), by[500])
    check('nonsense counts as no jobs, and a part-job is not a job', out['junk'] == ['Rookie', 'Rookie', 'Working'], out['junk'])
    check('a snag does not move a rank: three done and one snag is Proven', out['rankA'] == 'Proven', out['rankA'])
    check('only snags is still a Rookie', out['rankB'] == 'Rookie', out['rankB'])
    t = out['today']
    check('the quest strip counts open, in progress, finished today and all time',
          (t['open'], t['active'], t['today'], t['total']) == (2, 1, 2, 3), t)
    check('the best streak names its coworker', t['best'] == {'name': 'Ada', 'streak': 2}, t['best'])
    e = out['empty']
    check('an empty office reads as zeros, not an error', (e['open'], e['active'], e['today'], e['total'], e['best']) == (0, 0, 0, 0, None), e)
    print()
    if FAILS:
        print(f'rank: {len(FAILS)} FAILED')
        sys.exit(1)
    print('rank: all checks passed')


if __name__ == '__main__':
    main()
