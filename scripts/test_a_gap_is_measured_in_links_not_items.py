#!/usr/bin/env python3
""""Weakly connected" may only name a pair with little holding it together.

The panel prints, in one render, on the real office:

    Overlapping
    Topics blur into each other — plenty of links cross between them.
    ...
    Structural gap
    Weakly connected: Local Brain · Generalist ⟷ You (boss)

Those two topics hold 8 and 7 links inside themselves and are joined by 7 —
seven of the map's twenty-two links, nearly a third of everything the office
knows, running between exactly the pair being called weakly connected. The
panel said plenty of links cross between them and then said the opposite
four lines down.

The gate was `between >= Math.min(sizeA, sizeB)` → not a gap: a count of
LINKS compared against a count of ITEMS. The units do not match, so the bar
rises with the size of the smaller group while the crossing count does not,
and two big topics stay under it however heavily they are joined. A sibling
suite (test_graph_gap_verdict.py) already establishes why this claim has to
be absolute rather than relative — `score` only ranks pairs, and there is
always a worst pair. This is the same requirement, applied to the units.

So a pair must also carry fewer links across it than either side holds
inside itself. Links against links, and it says out loud without flinching:
these two topics have less holding them together than either of them has
holding itself together.

The invariant is checked by recomputing the crossing and internal counts
here, from the input edges and the communities `analyze()` returns — not by
reading back the worker's own bookkeeping, which would agree with itself
whatever it did.

Run: python3 scripts/test_a_gap_is_measured_in_links_not_items.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKER = ROOT / 'analytics.worker.js'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


FIXTURES = r'''
// LIVE — the office that reported this, anonymised and exact. Two hubs
// (n21 the boss, n22 the coworker) sharing seven of their leaves.
run('live', 23, [[6,21],[7,21],[8,21],[9,21],[10,21],[11,21],[12,21],[13,21],
  [14,21],[14,22],[15,21],[15,22],[16,21],[16,22],[17,21],[17,22],[18,21],
  [18,22],[19,21],[19,22],[20,21],[20,22]]);

// Two triangles and a single bridge — the shape everyone pictures when they
// hear "structural gap". It has to keep being named.
run('bridge1', 6, [[0,1],[1,2],[0,2],[3,4],[4,5],[3,5],[0,3]]);
// The same two triangles with nothing between them at all.
run('bridge0', 6, [[0,1],[1,2],[0,2],[3,4],[4,5],[3,5]]);
// The smallest pair that is still a pair, unjoined.
run('pairs2', 4, [[0,1],[2,3]]);
// Two cliques, three bridges: ten links inside each, three across. Sparse
// by both readings, so still a gap — the fix must not swallow this.
run('cliques3', 10, [[0,1],[0,2],[0,3],[0,4],[1,2],[1,3],[1,4],[2,3],[2,4],[3,4],
                     [5,6],[5,7],[5,8],[5,9],[6,7],[6,8],[6,9],[7,8],[7,9],[8,9],
                     [0,5],[1,6],[2,7]]);
// Two triangles crossed three ways — about as joined as two groups get.
run('crossed3', 6, [[0,1],[1,2],[0,2],[3,4],[4,5],[3,5],[0,3],[1,4],[2,5]]);
'''

SWEEP = r'''
let seed = 20260817;
const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
for (let t = 0; t < 120; t++) {
  const N = 4 + Math.floor(rnd() * 26);
  const p = 0.04 + rnd() * 0.5;
  const edges = [];
  for (let i = 0; i < N; i++)
    for (let j = i + 1; j < N; j++) if (rnd() < p) edges.push([i, j]);
  if (!edges.length) continue;
  run('sweep' + t, N, edges);
}
'''


def run_analyze():
    src = re.sub(r'self\.onmessage[\s\S]*$', '', WORKER.read_text(encoding='utf-8'))
    tmp_src = ROOT / '._gp_src.mjs'
    tmp_out = ROOT / '._gp_bundle.cjs'
    tmp_run = ROOT / '._gp_run.cjs'
    try:
        tmp_src.write_text(src + '\nexport { analyze };\n', encoding='utf-8')
        subprocess.run(['npx', 'esbuild', tmp_src.name, '--bundle', '--format=cjs',
                        '--platform=node', f'--outfile={tmp_out.name}',
                        '--log-level=error'],
                       cwd=ROOT, check=True, capture_output=True, timeout=240)
        tmp_run.write_text('''
const { analyze } = require('./%s');
const out = {};
const run = (name, N, edges) => {
  const nodes = Array.from({length: N}, (_, i) => ({ id: 'n' + i }));
  const r = analyze({ nodes, edges: edges.map(([s,t]) => ({source:'n'+s, target:'n'+t})) });

  /* Recount from the input and the communities analyze() handed back. The
     worker keeps its own tallies; reading those back would prove only that
     it agrees with itself. */
  const comm = (i) => r.nodeAttrs['n' + i].community;
  const intra = {}, inter = {}, size = {};
  for (let i = 0; i < N; i++) size[comm(i)] = (size[comm(i)] || 0) + 1;
  edges.forEach(([s, t]) => {
    const cs = comm(s), ct = comm(t);
    if (cs === ct) { intra[cs] = (intra[cs] || 0) + 1; return; }
    const k = cs < ct ? cs + '|' + ct : ct + '|' + cs;
    inter[k] = (inter[k] || 0) + 1;
  });

  let named = null;
  if (r.gap) {
    const a = r.gap.a, b = r.gap.b;
    const k = a < b ? a + '|' + b : b + '|' + a;
    named = { a, b, between: inter[k] || 0, reported: r.gap.between,
              intraA: intra[a] || 0, intraB: intra[b] || 0,
              sizeA: size[a] || 0, sizeB: size[b] || 0 };
  }
  out[name] = { structure: r.metrics.structure, edges: edges.length,
                sizes: r.clusters.map(c => c.size), gap: named };
};
%s
%s
console.log(JSON.stringify(out));
''' % (tmp_out.name, FIXTURES, SWEEP), encoding='utf-8')
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
    print('a gap is measured in links, not items')

    # ── 1. the source compares links against links ──────────────────────
    w = WORKER.read_text(encoding='utf-8')
    check('the pass over the edges tallies what stays inside a topic',
          re.search(r'if \(cs === ct\) \{ intra\[cs\]', w) is not None,
          'analytics.worker.js — the loop that counts crossings has to count '
          'the internal links too, or there is nothing to compare against')
    check('and a pair is disqualified by that count',
          re.search(r'between >= Math\.min\(intra\[a\][^)]*\)\) continue;', w)
          is not None,
          'analytics.worker.js — the links-vs-items gate alone lets big '
          'heavily-joined topics through')

    out = run_analyze()
    check('the worker builds and runs', out is not None)
    if not out:
        print('\na gap: %d FAILED' % len(FAILS))
        return 1

    # ── 2. THE invariant, recomputed from the input ─────────────────────
    named = {k: v for k, v in out.items() if v['gap']}
    liars = {k: v['gap'] for k, v in named.items()
             if not (v['gap']['between'] < min(v['gap']['intraA'], v['gap']['intraB'])
                     and v['gap']['between'] < min(v['gap']['sizeA'], v['gap']['sizeB']))}
    check('nothing is called weakly connected that is heavily joined',
          not liars,
          f'{list(liars.items())[:3]} — the crossing count has to be under '
          'both what each side holds inside and the smaller side\'s item count')

    check('the worker\'s own crossing count matches a recount',
          all(v['gap']['between'] == v['gap']['reported'] for v in named.values()),
          'the number the panel would print has to be the number that '
          'passed the gate')

    # ── 3. the specific render that reported this ───────────────────────
    live = out['live']
    check('the live office no longer claims a gap between its two topics',
          live['gap'] is None,
          f'{live} — seven of twenty-two links run across that pair')
    check('...and the panel has stopped contradicting itself in one render',
          live['structure'] == 'overlapping' and live['gap'] is None,
          f'{live} — "plenty of links cross between them" and "weakly '
          'connected" cannot both be about the same pair')
    check('the joined-three-ways pair stays unnamed too',
          out['crossed3']['gap'] is None, out['crossed3'])

    # ── 4. the reverse: a real gap is still named ───────────────────────
    for name in ('bridge1', 'bridge0', 'pairs2', 'cliques3'):
        check(f'[{name}] a genuinely sparse pair is still named',
              out[name]['gap'] is not None,
              f'{out[name]} — narrowing the claim must not silence it')

    # A sweep that never produced a gap would prove nothing above.
    swept = [v for k, v in out.items() if k.startswith('sweep')]
    check('the sweep actually produced gaps to check',
          sum(1 for v in swept if v['gap']) >= 3,
          f'{sum(1 for v in swept if v["gap"])} of {len(swept)} — a green '
          'sweep that never reached the branch is not evidence')

    print()
    if FAILS:
        print('a gap: %d FAILED — %s' % (len(FAILS), ', '.join(FAILS[:3])))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
