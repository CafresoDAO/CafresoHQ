#!/usr/bin/env python3
"""A published graph's analytics panel showed pre-prune counts next to a
post-prune canvas — "Notes 210 · Links 340" sitting right above a canvas
that had just dropped to 150 dots, with nothing on screen explaining the
gap.

graph-viewer.js's maxnodes pruning (?maxnodes=150, baked into every
publish URL by serve.py) drops all but the top-N nodes (by size) from
the render graph `g` via graphology's dropNode. `snap.analytics.metrics`
is computed server-side, in graph-engine.js's _runAnalytics(), over the
FULL pre-publish graph — and the analytics panel a few hundred lines
down reads `snap.analytics.metrics` verbatim, unaware any pruning
happened. The brand-bar title stats, by contrast, already count off the
live post-prune `g` — so only the analytics panel showed the stale,
larger numbers, a narrow but directly observable honesty defect any
time a published graph exceeds 150 nodes.

Run: python3 scripts/test_published_graph_analytics_matches_pruned_canvas.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GV = (ROOT / 'graph-viewer.js').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


MARKER_START = "  // maxnodes: keep the N most influential (by size), drop the rest.\n"
MARKER_END = "\n\n  // Blend the snapshot's own weighting with degree:"


def extract_block():
    i = GV.find(MARKER_START)
    j = GV.find(MARKER_END)
    if i == -1 or j == -1 or j <= i:
        return None
    return GV[i:j]


def main():
    print("Does a published graph's analytics panel agree with the pruned canvas?")

    block = extract_block()
    check('the maxnodes pruning block is found intact between its known markers',
          block is not None,
          'graph-viewer.js: markers moved or the block was restructured — '
          'update MARKER_START/MARKER_END')

    if block is not None:
        check('the block still recomputes snap.analytics.metrics from the '
              'post-prune graph, guarded on analytics being present',
              'if (snap.analytics && snap.analytics.metrics) {' in block
              and 'snap.analytics.metrics.nodes = g.order;' in block
              and 'snap.analytics.metrics.edges = g.size;' in block,
              'the metrics-recompute lines are missing from the extracted block')

    # ── the analytics panel itself still reads snap.analytics.metrics
    #    verbatim (unchanged) — the fix works only because this is true ──
    check('the analytics panel reads snap.analytics.metrics verbatim, so a '
          'corrected metrics object is sufficient (no second fix needed there)',
          'm = snap.analytics.metrics;' in GV,
          'graph-viewer.js: analytics panel rendering changed shape')

    # ── mechanism, run for real: drive the actual extracted block against
    #    the real graphology library (not a mock), the same package the
    #    production file imports ──────────────────────────────────────────
    if block is None:
        print('  SKIP  mechanism check needs the extracted block')
    elif not shutil.which('node'):
        print('  SKIP  node not on PATH — the mechanism check needs it')
    else:
        graphology_dir = ROOT / 'node_modules' / 'graphology'
        if not graphology_dir.exists():
            print('  SKIP  node_modules/graphology not installed')
        else:
            def run(node_count, maxn):
                nodes = [{'key': 'n%d' % i, 'attributes': {'size': float(node_count - i)}}
                          for i in range(node_count)]
                edges = [{'key': 'e%d' % i, 'source': 'n%d' % i, 'target': 'n%d' % (i + 1),
                          'attributes': {}} for i in range(node_count - 1)]
                graph_json = json.dumps({
                    'attributes': {}, 'options': {'type': 'mixed', 'multi': False, 'allowSelfLoops': True},
                    'nodes': nodes, 'edges': edges,
                })
                js = r'''
const Graph = require(%r);
const g = Graph.from(%s);
const snap = { analytics: { metrics: { nodes: 999999, edges: 999999 } } };
const P = (k, d) => (k === 'maxnodes' ? String(%d) : d);
%s
console.log(JSON.stringify({ order: g.order, size: g.size, metrics: snap.analytics.metrics }));
''' % (str(graphology_dir), graph_json, maxn, block)
                p = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=20, cwd=ROOT)
                if p.returncode != 0:
                    return None, p.stderr.strip()[:500]
                return json.loads(p.stdout), None

            out, err = run(node_count=10, maxn=4)
            check('pruning to maxnodes=4 out of 10 drops the render graph to 4 nodes',
                  out is not None and out['order'] == 4, err or out)
            check("...and snap.analytics.metrics.nodes now matches the pruned "
                  "graph's order (4), not the stale pre-prune value (999999) "
                  "the panel would otherwise have shown",
                  out is not None and out['metrics']['nodes'] == 4, out)
            check("...and snap.analytics.metrics.edges matches the pruned "
                  "graph's size, not the stale pre-prune value",
                  out is not None and out['metrics']['edges'] == out['order'] - 1
                  and out['metrics']['edges'] != 999999, out)

            out2, err2 = run(node_count=10, maxn=0)
            check('maxnodes=0 (the default — no cap) leaves the graph and the '
                  'stale metrics.nodes untouched, matching how brand-bar stats '
                  'behave when nothing was pruned',
                  out2 is not None and out2['order'] == 10 and out2['metrics']['nodes'] == 999999,
                  err2 or out2)

            out3, err3 = run(node_count=5, maxn=150)
            check('maxnodes larger than the graph (150 > 5) is a no-op, same '
                  'as the unpublished/small-graph case — metrics stay untouched',
                  out3 is not None and out3['order'] == 5 and out3['metrics']['nodes'] == 999999,
                  err3 or out3)

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
