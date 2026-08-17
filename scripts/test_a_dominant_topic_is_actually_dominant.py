#!/usr/bin/env python3
"""The verdict may only claim one dominant topic when one topic dominates.

Read off the live office, 23 items, one render:

    Biased
    One dominant topic — add contrasting ideas.
    On the map: 23 · Links: 22 · Topics: 8
    Main topics
      39%  9 items
      35%  8 items
       4%  1 item   (×3)

Nothing dominates 39% of a map, and the panel says so itself four lines
below the sentence claiming it does. The chip was decided by modularity
alone — `modularity < 0.2 → 'biased'` — and modularity is a claim about
SEPARATION, not dominance. This office is two hubs (the boss, the one
coworker) sharing seven leaves: two near-equal topics, heavily interleaved.
`C = largest / N` — the number that does measure dominance — was already
computed a few lines above and this branch never read it.

So the low-modularity band splits at the same half-the-map line the
`diversified` branch already draws: above it, "one dominant topic" is true;
below it the honest reading is `overlapping`, which is what the shape says.

The invariant this pins is not the split itself but the promise the chip
makes: if the panel says one topic dominates, the topic list underneath it
has to agree. Checked on fixtures AND on a seeded sweep of random shapes,
because a property that only holds for the graphs someone thought of is not
a property.

Runs the REAL analyze() (bundled with the project's own esbuild — the worker
uses subpath imports bare node ESM cannot follow) and the REAL copy map
lifted out of the panel. A re-implementation of either would agree with
itself while the shipped code said something else.

Run: python3 scripts/test_a_dominant_topic_is_actually_dominant.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKER = ROOT / 'analytics.worker.js'
VIEW = ROOT / 'views' / 'graph.jsx'

# One topic dominates when it holds more of the map than every other topic
# put together. Half exactly is a tie, not a win — see the `tied` fixture.
DOMINANT = 0.5

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# ── the real analyze(), over shapes chosen to sit on both sides ──────────
FIXTURES = r'''
// LIVE — the office that reported this, anonymised and exact: two hubs
// (n21 the boss, n22 the coworker) sharing seven of their leaves, plus six
// items nothing links to yet. Modularity 0.18, largest topic 39%.
run('live', 23, [[6,21],[7,21],[8,21],[9,21],[10,21],[11,21],[12,21],[13,21],
  [14,21],[14,22],[15,21],[15,22],[16,21],[16,22],[17,21],[17,22],[18,21],
  [18,22],[19,21],[19,22],[20,21],[20,22]]);

// CLIQUE10 — one topic, and it is the whole map. The verdict has to still
// be able to say "dominant", or this fix is just deleting the branch.
const cl = []; for (let i=0;i<10;i++) for (let j=i+1;j<10;j++) cl.push([i,j]);
run('clique10', 10, cl);

// CLIQUE+3 — dominant WITHOUT being the only topic: nine items in one, four
// in another. 69% of the map. The interesting side of the line.
run('clique+3', 13, cl.concat([[0,10],[0,11],[0,12]]));

// STAR12 — a hub and twelve leaves. One topic, low modularity, dominant.
run('star12', 13, Array.from({length:12}, (_, i) => [12, i]));

// TIED — the boundary, and the reason the comparison is strict. Two hubs
// covering eight leaves each, six of them shared: two topics of six in a
// map of twelve, dead equal. C is 0.500 on the nose, and "one dominant
// topic" over two equal halves is this same defect at its smallest.
run('tied', 12, [[0,10],[1,10],[2,10],[3,10],[4,10],[5,10],[6,10],[7,10],
                 [2,11],[3,11],[4,11],[5,11],[6,11],[7,11],[8,11],[9,11]]);

// TWO-HUBS — cleanly separated, so it never enters the low-modularity band
// at all. A control: this fix must not move the verdicts above the band.
run('two-hubs', 14, [[0,6],[1,6],[2,6],[3,6],[4,6],[5,6],
                     [7,13],[8,13],[9,13],[10,13],[11,13],[12,13],[6,13]]);
'''

SWEEP = r'''
// A seeded sweep. The invariant is about every shape the office can hold,
// not the five somebody sat down and imagined.
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
    tmp_src = ROOT / '._dom_src.mjs'
    tmp_out = ROOT / '._dom_bundle.cjs'
    tmp_run = ROOT / '._dom_run.cjs'
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
  out[name] = { structure: r.metrics.structure, modularity: r.metrics.modularity,
                largestShare: r.metrics.largestShare, topics: r.metrics.communityCount,
                N, topShare: r.clusters.length ? r.clusters[0].share : 0,
                sizes: r.clusters.map(c => c.size) };
};
%s
%s
console.log(JSON.stringify(out));
''' % (tmp_out.name, FIXTURES, SWEEP), encoding='utf-8')
        p = subprocess.run(['node', tmp_run.name], cwd=ROOT,
                           capture_output=True, text=True, timeout=240)
        if p.returncode != 0:
            print('  node failed:', (p.stderr or '')[-700:])
            return None
        return json.loads(p.stdout.strip().split('\n')[-1])
    finally:
        for f in (tmp_src, tmp_out, tmp_run):
            f.unlink(missing_ok=True)


def classifier_classes():
    """Every class name the shipped classifier chain can assign."""
    src = WORKER.read_text(encoding='utf-8')
    m = re.search(r'\n  let structure;\n([\s\S]*?)\n\n', src)
    if not m:
        return None
    return sorted(set(re.findall(r"structure = [^;\n]*?'([a-z]+)'", m.group(1)))
                  | set(re.findall(r"\? '([a-z]+)' : '([a-z]+)'", m.group(1))[0]
                        if re.search(r"\? '[a-z]+' : '[a-z]+'", m.group(1)) else []))


def struct_copy():
    """The panel's REAL copy map, keys and sentences."""
    src = VIEW.read_text(encoding='utf-8')
    m = re.search(r'const STRUCT_COPY = \{([\s\S]*?)\n  \};', src)
    if not m:
        return None
    body = re.sub(r'/\*[\s\S]*?\*/', '', m.group(1))
    return dict(re.findall(r"(\w+):\s*'((?:[^'\\]|\\.)*)'", body))


def main():
    print('a dominant topic is actually dominant')

    copy = struct_copy()
    check('the panel\'s copy map was liftable', copy is not None,
          'views/graph.jsx — STRUCT_COPY moved; re-point the lift rather than '
          'dropping the check')
    classes = classifier_classes()
    check('the classifier chain was liftable', bool(classes),
          'analytics.worker.js — the `let structure;` chain moved')
    if copy is None or not classes:
        print('\na dominant topic: %d FAILED' % len(FAILS))
        return 1

    # ── 1. no verdict the worker can publish renders a blank sentence ────
    # The panel does `STRUCT_COPY[m.structure] || ''`, so a class with no
    # entry shows the chip with nothing under it. That is exactly the way a
    # sixth verdict would ship half-finished.
    missing = [c for c in classes if c not in copy]
    check('every verdict the worker can publish has a sentence',
          not missing,
          f'{missing} — the chip renders, the line under it is empty')

    # ── 2. only a verdict gated on dominance is allowed to claim it ──────
    claims = sorted(k for k, v in copy.items() if 'dominant' in v.lower())
    check('exactly one verdict claims a dominant topic', claims == ['biased'],
          f'{claims} — "dominant" is a measurable word; it belongs to the '
          'one class that checks the measurement')

    # ── 3. what the real analyze() publishes ─────────────────────────────
    out = run_analyze()
    check('the worker builds and runs', out is not None)
    if not out:
        print('\na dominant topic: %d FAILED' % len(FAILS))
        return 1

    # THE invariant: the chip's promise, checked against the topic list the
    # panel prints directly under it.
    liars = {k: v for k, v in out.items()
             if v['structure'] == 'biased' and not v['topShare'] > DOMINANT}
    check('nothing reads "one dominant topic" without a dominant topic',
          not liars,
          f'{list(liars.items())[:3]} — the sentence and the list under it '
          'are one screen')

    check('the top topic\'s share is the share the verdict was judged on',
          all(abs(v['topShare'] - v['largestShare']) < 1e-9 for v in out.values()),
          'largestShare feeds the verdict, clusters[0].share is printed — '
          'they have to be the same number')

    # ── 4. the specific shape that reported this ─────────────────────────
    live = out['live']
    check('the live office no longer reads as one dominant topic',
          live['structure'] != 'biased',
          f'{live} — 39% of a map is not dominance')
    check('...and the sentence it gets instead does not claim one either',
          'dominant' not in copy.get(live['structure'], '').lower()
          and copy.get(live['structure'], '') != '',
          f"{live['structure']}: {copy.get(live['structure'])!r}")
    check('...and it is still read as low separation, not clean topics',
          live['modularity'] < 0.2 and live['structure'] == 'overlapping',
          f'{live} — the shape did not change, only the word for it')

    # ── 5. the boundary: half the map is a tie, not a win ────────────────
    tied = out['tied']
    check('two topics of the same size, and neither is called dominant',
          tied['structure'] != 'biased' and tied['sizes'][:2] == [6, 6]
          and abs(tied['topShare'] - 0.5) < 1e-9,
          f'{tied} — a strict comparison is the whole difference here')

    # ── 6. the reverse: dominance is still sayable ───────────────────────
    for name in ('clique10', 'clique+3', 'star12'):
        g = out[name]
        check(f'[{name}] a map one topic really does own still says so',
              g['structure'] == 'biased' and g['topShare'] > DOMINANT,
              f'{g} — narrowing the claim must not silence it')

    # ── 6. the band above low modularity is untouched ────────────────────
    check('[two-hubs] a cleanly separated map is unaffected',
          out['two-hubs']['structure'] == 'focused',
          f"{out['two-hubs']} — this fix only splits the low-modularity band")

    # The sweep is worthless if it never produced the case under test.
    seen = {v['structure'] for k, v in out.items() if k.startswith('sweep')}
    check('the sweep actually exercised the low-modularity band',
          {'biased', 'overlapping'} & seen,
          f'{sorted(seen)} — a green sweep that never reached the branch is '
          'not evidence')

    print()
    if FAILS:
        print('a dominant topic: %d FAILED — %s'
              % (len(FAILS), ', '.join(FAILS[:3])))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
