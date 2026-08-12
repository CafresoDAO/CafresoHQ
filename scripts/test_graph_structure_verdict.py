#!/usr/bin/env python3
"""An empty cabinet has no shape, and the panel must not invent one.

Opening the Vault on a brand-new office showed, in the analytics panel:

    Dispersed
    Many scattered topics — consider bridging them.
    On the map: 1   Links: 0   Topics: 1

"Many scattered topics" directly above "Topics: 1" — the panel contradicting
itself in the same breath, about a cabinet holding zero notes, as the first
thing a new user sees there.

Mechanism, confirmed rather than guessed: Louvain returns a NaN modularity
for an edgeless graph, and NaN is false against EVERY comparison in the
classifier chain, so it fell past `biased`/`focused`/`diversified` into the
final `else` — the most alarming of the four. Note the initialiser
(`modularity = 0`) would have produced "biased" instead: also wrong, just
quieter. The default was never what kept this honest.

Fix: a fifth state, `unformed`, guarded FIRST — for a non-finite modularity,
no edges, or fewer than three nodes — with copy that says there isn't a shape
yet instead of picking one.

This runs the REAL `analyze()` rather than re-implementing its branches: the
worker is bundled with the project's own esbuild (it uses bundler-resolved
subpath imports that bare node ESM cannot follow) and called directly. A
re-implementation would have happily agreed with itself while the shipped
code did something else.

Run: python3 scripts/test_graph_structure_verdict.py
"""
import json
import re
import shutil
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
    """Bundle the worker for node and return {label: structure} for real graphs."""
    src = re.sub(r'self\.onmessage[\s\S]*$', '', WORKER.read_text(encoding='utf-8'))
    tmp_src = ROOT / '._sv_src.mjs'
    tmp_out = ROOT / '._sv_bundle.cjs'
    tmp_run = ROOT / '._sv_run.cjs'
    try:
        tmp_src.write_text(src + '\nexport { analyze };\n', encoding='utf-8')
        subprocess.run(['npx', 'esbuild', tmp_src.name, '--bundle', '--format=cjs',
                        '--platform=node', f'--outfile={tmp_out.name}', '--log-level=error'],
                       cwd=ROOT, check=True, capture_output=True, timeout=180)
        tmp_run.write_text('''
const { analyze } = require('./%s');
const t = (n, e) => analyze({ nodes: n.map(id => ({ id })),
                              edges: e.map(([s, d]) => ({ source: s, target: d })) }).metrics;
console.log(JSON.stringify({
  empty:   t(['a'], []).structure,
  pair:    t(['a','b'], [['a','b']]).structure,
  chain:   t('abcdef'.split(''), [['a','b'],['b','c'],['d','e'],['e','f']]).structure,
  dense:   t('abcde'.split(''), [['a','b'],['a','c'],['b','c'],['c','d'],['d','e'],['a','e']]).structure,
}));
''' % tmp_out.name, encoding='utf-8')
        out = subprocess.run(['node', tmp_run.name], cwd=ROOT, check=True,
                             capture_output=True, text=True, timeout=120)
        return json.loads(out.stdout.strip().splitlines()[-1])
    finally:
        for f in (tmp_src, tmp_out, tmp_run):
            try:
                f.unlink()
            except FileNotFoundError:
                pass


def main():
    print('graph structure verdict — no shape invented for a graph that has none')
    if not WORKER.is_file() or not VIEW.is_file():
        print('  FAIL  missing source file(s)')
        return 1
    if not shutil.which('npx'):
        print('  SKIP  npx unavailable — cannot bundle the worker for a real call')
        return 0

    try:
        got = run_analyze()
    except Exception as e:                                    # noqa: BLE001
        print(f'  FAIL  could not run the real analyze(): {e}')
        return 1

    check('an edgeless graph is "unformed", not "dispersed"',
          got['empty'] == 'unformed',
          f"got {got['empty']!r} — NaN modularity falling through the chain is "
          f"how a cabinet with no notes got told it had 'many scattered topics'")
    check('a two-node graph is "unformed" too',
          got['pair'] == 'unformed',
          f"got {got['pair']!r} — two nodes cannot have a community structure")

    # The other half: the guard must not eat verdicts on graphs that DO have a
    # shape. A fix that silences everything would pass the checks above.
    check('a real sparse graph still gets a real verdict',
          got['chain'] in ('biased', 'focused', 'diversified', 'dispersed'),
          f"got {got['chain']!r} — the guard has swallowed a classifiable graph")
    check('a real dense graph still gets a real verdict',
          got['dense'] in ('biased', 'focused', 'diversified', 'dispersed'),
          f"got {got['dense']!r} — same")

    # Source-level: the guard has to come FIRST, or NaN reaches the thresholds.
    src = WORKER.read_text(encoding='utf-8')
    chain = src[src.find('  let structure;'):]
    chain = chain[:chain.find('\n\n')]
    check('the unformed guard is the first branch in the chain',
          chain.find('unformed') < chain.find("'biased'"),
          'analytics.worker.js: placed after a threshold, NaN slips past it again')
    check('...and it tests for a non-finite modularity by name',
          'Number.isFinite(modularity)' in chain,
          'analytics.worker.js: the NaN case is the whole reason this exists')

    check('the panel has copy for the unformed state',
          re.search(r'unformed:\s*[\'"]', VIEW.read_text(encoding='utf-8')) is not None,
          'views/graph.jsx: without copy the chip renders a bare word with no '
          'sentence under it')

    print()
    if FAILS:
        print(f'graph structure verdict: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('graph structure verdict: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
