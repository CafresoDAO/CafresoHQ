#!/usr/bin/env python3
"""Opening the Library twice tells the boss the same thing about it.

`analyze()` calls graphology-communities-louvain, which defaults to
`rng: Math.random` with `randomWalk: true`. The partition therefore came out
of an unseeded draw, and the same library did not get the same answer twice.
Measured on the real office — 23 items, 22 links, nothing touched between
runs — two hundred passes returned:

    171 ×   39% · 9 items    35% · 8 items
     29 ×   43% · 10 items   30% · 7 items

About one open in seven the boss saw a different breakdown of a shelf that
had not changed, with different members named under each topic. Nothing on
that panel is hedged: the counts are exact and the percentages are printed
to the point.

Seeding does not make Louvain right — it is a heuristic, and both partitions
above are defensible readings of the same graph. It makes the office say the
same thing about the same shelf every time it is asked.

The two halves of that are both checked here, because either alone is
satisfiable by something useless: an `analyze()` that ignored its input
would be perfectly stable, and one that reported a fresh guess each time
would be perfectly sensitive.

Runs the REAL analyze(), bundled with the project's own esbuild — the worker
uses subpath imports bare node ESM cannot follow.

Run: python3 scripts/test_the_same_library_gets_the_same_answer.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKER = ROOT / 'analytics.worker.js'

REPEATS = 60

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run_analyze():
    src = re.sub(r'self\.onmessage[\s\S]*$', '', WORKER.read_text(encoding='utf-8'))
    tmp_src = ROOT / '._st_src.mjs'
    tmp_out = ROOT / '._st_bundle.cjs'
    tmp_run = ROOT / '._st_run.cjs'
    try:
        tmp_src.write_text(src + '\nexport { analyze };\n', encoding='utf-8')
        subprocess.run(['npx', 'esbuild', tmp_src.name, '--bundle', '--format=cjs',
                        '--platform=node', f'--outfile={tmp_out.name}',
                        '--log-level=error'],
                       cwd=ROOT, check=True, capture_output=True, timeout=240)
        tmp_run.write_text('''
const { analyze } = require('./%s');

/* Everything the panel prints, in one string. If any of it moves between
   two runs over identical input, the boss saw the office change its mind
   about a shelf nobody touched. */
const fingerprint = (N, edges) => {
  const nodes = Array.from({length: N}, (_, i) => ({ id: 'n' + i }));
  const r = analyze({ nodes, edges: edges.map(([s,t]) => ({source:'n'+s, target:'n'+t})) });
  const m = r.metrics;
  return JSON.stringify({
    structure: m.structure, topics: m.communityCount,
    modularity: +m.modularity.toFixed(12), entropy: +m.entropy.toFixed(12),
    largestShare: +m.largestShare.toFixed(12), components: m.components,
    clusters: r.clusters.map(c => [c.size, +c.share.toFixed(12), c.topNodes]),
    influential: r.topInfluential.map(t => t.id),
    gap: r.gap ? [r.gap.between, r.gap.aTop, r.gap.bTop] : null,
    communities: Object.keys(r.nodeAttrs).sort()
      .map(k => k + ':' + r.nodeAttrs[k].community).join(','),
  });
};

// The live office, anonymised and exact: two hubs sharing seven leaves,
// six items nothing links to yet. This is the map the report came off.
const LIVE = [[6,21],[7,21],[8,21],[9,21],[10,21],[11,21],[12,21],[13,21],
  [14,21],[14,22],[15,21],[15,22],[16,21],[16,22],[17,21],[17,22],[18,21],
  [18,22],[19,21],[19,22],[20,21],[20,22]];
// Two triangles crossed three ways — small, and it flipped between a
// two-topic and a three-topic reading of itself.
const TRI = [[0,1],[1,2],[0,2],[3,4],[4,5],[3,5],[0,3],[1,4],[2,5]];
// A shape with no symmetry to hide behind.
const MIX = [[0,1],[0,2],[1,2],[2,3],[3,4],[4,5],[3,5],[5,6],[6,7],[7,8],
             [6,8],[8,9],[9,10],[10,11],[9,11],[1,4],[7,10]];

const answers = {};
const add = (k, v) => { (answers[k] = answers[k] || {})[v] = (answers[k][v] || 0) + 1; };
for (let i = 0; i < %d; i++) {
  add('live', fingerprint(23, LIVE));
  add('tri',  fingerprint(6,  TRI));
  add('mix',  fingerprint(12, MIX));
}

/* Sensitivity: one more link, and the answer has to move. A stable
   analyze() that had stopped reading its input would pass everything
   above. */
const changed = {
  live: fingerprint(23, LIVE) !== fingerprint(23, LIVE.concat([[0,1]])),
  tri:  fingerprint(6,  TRI)  !== fingerprint(6,  TRI.slice(0, -1)),
  mix:  fingerprint(12, MIX)  !== fingerprint(12, MIX.concat([[0,11]])),
};

console.log(JSON.stringify({
  distinct: Object.fromEntries(Object.entries(answers)
    .map(([k, v]) => [k, Object.keys(v).length])),
  counts: Object.fromEntries(Object.entries(answers)
    .map(([k, v]) => [k, Object.values(v)])),
  changed,
}));
''' % (tmp_out.name, REPEATS), encoding='utf-8')
        p = subprocess.run(['node', tmp_run.name], cwd=ROOT,
                           capture_output=True, text=True, timeout=300)
        if p.returncode != 0:
            print('  node failed:', (p.stderr or '')[-700:])
            return None
        return json.loads(p.stdout.strip().split('\n')[-1])
    finally:
        for f in (tmp_src, tmp_out, tmp_run):
            f.unlink(missing_ok=True)


def main():
    print('the same library gets the same answer')

    # ── 1. the draw is seeded at the source ─────────────────────────────
    w = WORKER.read_text(encoding='utf-8')
    call = re.search(r'louvain\.detailed\(g,\s*\{([^}]*)\}\)', w)
    check('the community pass is given an rng', call is not None
          and 'rng:' in call.group(1),
          'analytics.worker.js — graphology-communities-louvain defaults to '
          'rng: Math.random, so leaving it off is leaving it unseeded')
    if call:
        check('...and it is not the unseeded one',
              'Math.random' not in call.group(1),
              call.group(1).strip())

    # ── 2. what the shipped analyze() actually does, %d times over ──────
    out = run_analyze()
    check('the worker builds and runs', out is not None)
    if not out:
        print('\nthe same library: %d FAILED' % len(FAILS))
        return 1

    for name, n in out['distinct'].items():
        check(f'[{name}] {REPEATS} opens of an untouched library, one answer',
              n == 1,
              f'{n} different answers, seen {out["counts"][name]} times each '
              '— the panel is telling the boss the shelf changed when it did '
              'not')

    # ── 3. ...and it is still reading the shelf ─────────────────────────
    for name, moved in out['changed'].items():
        check(f'[{name}] change the library and the answer changes',
              moved,
              'an analyze() that ignored its input would pass every '
              'stability check above')

    print()
    if FAILS:
        print('the same library: %d FAILED — %s'
              % (len(FAILS), ', '.join(FAILS[:3])))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
