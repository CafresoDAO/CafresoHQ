#!/usr/bin/env python3
"""The percentage beside a topic's item count is a share of the same map.

"Main topics" prints two numbers per row, touching:

    84%  9 items
    16%  8 items
     0%  1 items
     0%  1 items
     0%  1 items

Read on a live office holding 23 items. Two numbers side by side get read as
one quantity said twice, and these were not: the percentage was an INFLUENCE
share — this cluster's betweenness over the graph's — while the count beside
it was a headcount. Nine items out of twenty-three is 39%, not 84%; the two
biggest topics were the same size and the panel said one was five times the
other; and three topics holding real work were labelled 0% of the map on the
same line as the count proving they were not.

The all-zero half of this was fixed once already — when NOBODY brokered,
every share came out 0 and two equal halves of a map both read "0% · 3
items" — and the note left behind says exactly why that was wrong: "Nobody
reads that percentage as 'share of brokering' — they read it as 'how much of
my work is this', and by that reading 0% is simply false." True; and just as
true when SOME clusters broker, which is the ordinary case. Any office with
one busy thread and a few notes nothing links to yet lands here. Fixing the
degenerate case and leaving the common one is how the same lie ships twice.

So `share` is size / N, always. Nothing is lost: brokering was never named
in the UI as brokering, and the nodes that do it already have their own
section directly above ("Most influential"). E_entropy, which feeds the
diversified/focused verdict, now measures spread of SIZE — which is what
that verdict's own words describe ("one dominant topic", "many scattered
topics") and what its sibling term, largest / N, already measured.

This runs the REAL analyze() — bundled with the project's own esbuild,
because the worker uses bundler-resolved subpath imports bare node ESM
cannot follow — and the REAL label expression lifted out of the panel. A
re-implementation of either would agree with itself while the shipped code
did something else.

Run: python3 scripts/test_a_topic_percentage_is_a_share_of_the_map.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKER = ROOT / 'analytics.worker.js'
VIEW = ROOT / 'views' / 'graph.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run_analyze():
    """Bundle the worker for node and return cluster rows for three graphs."""
    src = re.sub(r'self\.onmessage[\s\S]*$', '', WORKER.read_text(encoding='utf-8'))
    tmp_src = ROOT / '._tp_src.mjs'
    tmp_out = ROOT / '._tp_bundle.cjs'
    tmp_run = ROOT / '._tp_run.cjs'
    try:
        tmp_src.write_text(src + '\nexport { analyze };\n', encoding='utf-8')
        subprocess.run(['npx', 'esbuild', tmp_src.name, '--bundle', '--format=cjs',
                        '--platform=node', f'--outfile={tmp_out.name}', '--log-level=error'],
                       cwd=ROOT, check=True, capture_output=True, timeout=240)
        tmp_run.write_text('''
const { analyze } = require('./%s');
const run = (nodes, edges) => {
  const r = analyze({ nodes: nodes.map(id => ({ id })),
                      edges: edges.map(([s, t]) => ({ source: s, target: t })) });
  return { N: nodes.length, entropy: r.metrics.entropy,
           rows: r.clusters.map(c => ({ share: c.share, size: c.size })) };
};

// MIXED — the shape that reproduced it: one tight core that really does
// broker, a second smaller thread hanging off it, and three lone items.
const mixed = run(
  ['a','b','c','d','e','f','g','lone1','lone2','lone3'],
  [['a','b'],['a','c'],['a','d'],['b','c'],['c','d'],['b','d'],
   ['e','f'],['e','g'],['f','g'],['a','e']]);

// DISJOINT — nobody brokers anything; the case the earlier pass fixed, kept
// here so this fix cannot be written in a way that un-fixes it.
const disjoint = run(['a','b','c','x','y','z'],
                     [['a','b'],['b','c'],['x','y'],['y','z']]);

// LOPSIDED — one big cluster, one small. The percentages have to be able to
// say "one topic dominates"; this is not a test that everything is equal.
// A CLIQUE, not a ring: a ring of eight is not one topic to Louvain, it is
// four pairs, and the first draft of this fixture proved that by producing
// 30/30/20/20 while claiming to be lopsided.
const clique = 'abcdefgh'.split('');
const cliqueEdges = [];
for (let i = 0; i < clique.length; i++)
  for (let j = i + 1; j < clique.length; j++) cliqueEdges.push([clique[i], clique[j]]);
const lopsided = run(clique.concat(['p','q']), cliqueEdges.concat([['p','q']]));

console.log(JSON.stringify({ mixed, disjoint, lopsided }));
''' % tmp_out.name, encoding='utf-8')
        p = subprocess.run(['node', tmp_run.name], cwd=ROOT,
                           capture_output=True, text=True, timeout=180)
        if p.returncode != 0:
            print('  node failed:', (p.stderr or '')[-600:])
            return None
        return json.loads(p.stdout.strip().split('\n')[-1])
    finally:
        for f in (tmp_src, tmp_out, tmp_run):
            f.unlink(missing_ok=True)


def run_label():
    """Evaluate the panel's REAL count-label expression at 1 and at 2."""
    src = VIEW.read_text(encoding='utf-8')
    m = re.search(
        r"React\.createElement\('span', \{ style: \{ color: '#8f8676' \} \},\s*"
        r"(c\.size \+[\s\S]*?)\)\)\),", src)
    if not m:
        return None
    expr = m.group(1).strip().rstrip(')')
    # Re-balance: the lift stops at the span's own closing paren.
    while expr.count('(') > expr.count(')'):
        expr += ')'
    tmp = ROOT / '._tp_label.cjs'
    try:
        tmp.write_text(
            'const label = (size, source) => { const c = { size }; return (%s); };\n'
            'console.log(JSON.stringify({\n'
            '  one: label(1, "items"), two: label(2, "items"),\n'
            '  oneC: label(1, "concepts"), twoC: label(2, "concepts") }));\n' % expr,
            encoding='utf-8')
        p = subprocess.run(['node', tmp.name], cwd=ROOT, capture_output=True,
                           text=True, timeout=60)
        if p.returncode != 0:
            print('  label node failed:', (p.stderr or '')[-400:])
            return None
        return json.loads(p.stdout.strip().split('\n')[-1])
    finally:
        tmp.unlink(missing_ok=True)


def main():
    print('a topic percentage is a share of the map')

    # ── 1. the source says size, not brokering ──────────────────────────
    w = WORKER.read_text(encoding='utf-8')
    check('the cluster share is computed from the cluster size',
          re.search(r'share: members\.length / N', w) is not None,
          'analytics.worker.js — the number printed beside "N items" has to '
          'be derived from that same N')
    check('...and no longer from the graph\'s betweenness total',
          re.search(r'share:\s*totalBc', w) is None
          and re.search(r'let totalBc = 0;', w) is None,
          'analytics.worker.js — a leftover influence share is the defect, '
          'and a leftover accumulator is the invitation to reach for it')

    # ── 2. what the real analyze() actually returns ─────────────────────
    out = run_analyze()
    check('the worker builds and runs', out is not None)
    if not out:
        print()
        print('a topic percentage: %d FAILED' % len(FAILS))
        return 1

    for label, g in out.items():
        rows, N = g['rows'], g['N']
        check(f'[{label}] every topic holding an item has a non-zero share',
              all(r['share'] > 0 for r in rows if r['size'] > 0),
              f'{rows} — "0% · 1 items" is the panel contradicting itself '
              'inside one line')
        check(f'[{label}] each share is that topic\'s own count over the map',
              all(abs(r['share'] - r['size'] / N) < 1e-9 for r in rows),
              f'N={N} {rows} — the two numbers on the row are one quantity '
              'said twice, so they have to come from one place')
        check(f'[{label}] the shares account for the whole map',
              abs(sum(r['share'] for r in rows) - 1.0) < 1e-9,
              f'{rows} — every item is in exactly one cluster')
        check(f'[{label}] the biggest topic is listed first',
              [r['size'] for r in rows] == sorted((r['size'] for r in rows),
                                                  reverse=True),
              f'{rows} — "Main topics" is read top-down')

    # The point of the ordering check is that it can still say "dominant".
    lop = out['lopsided']['rows']
    check('a genuinely dominant topic still reads as dominant',
          lop[0]['share'] >= 0.6 and lop[-1]['share'] <= 0.3,
          f'{lop} — flattening every percentage would be a different lie')

    # ── 3. the verdict reads the same shares ────────────────────────────
    # entropy = -Σ p·ln p over the cluster shares. Recomputing it here from
    # the sizes is the check: if entropy is ever fed a different share than
    # the panel prints, the office's verdict and its topic list are talking
    # about two different graphs.
    import math
    for label, g in out.items():
        want = -sum(r['size'] / g['N'] * math.log(r['size'] / g['N'])
                    for r in g['rows'] if r['size'] > 0)
        check(f'[{label}] the structure verdict is read off those same shares',
              abs(g['entropy'] - want) < 1e-9,
              f"entropy {g['entropy']} vs {want} — 'one dominant topic' and "
              "'many scattered topics' are claims about size")

    # ── 4. the row says "1 item", not "1 items" ─────────────────────────
    lab = run_label()
    check('the panel\'s own count label was liftable', lab is not None,
          'views/graph.jsx — the expression moved; re-point the lift rather '
          'than dropping the check')
    if lab:
        check('one item is one item',
              lab['one'] == '1 item' and lab['oneC'] == '1 concept', lab)
        check('...and two are still plural',
              lab['two'] == '2 items' and lab['twoC'] == '2 concepts', lab)

    print()
    if FAILS:
        print('a topic percentage: %d FAILED — %s'
              % (len(FAILS), ', '.join(FAILS[:3])))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
