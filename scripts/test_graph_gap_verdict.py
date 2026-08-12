#!/usr/bin/env python3
""""Weakly connected" is an absolute claim, and it was printed unconditionally.

The Vault analytics panel renders a pink alert box reading

    Structural gap
    Weakly connected: <A> ⟷ <B>

whenever `analyze()` returns a `gap`. The worker used to return one for ANY
graph with two or more communities, because its `score` only ranks pairs
RELATIVELY — there is always a worst pair, so the alert could never not fire.
Measured against the shipped code, that produced two false statements:

  · Two triangles joined by SIX cross edges — about as connected as two
    groups get — were reported as "Weakly connected".
  · Three notes with no links at all produced "Weakly connected: a ⟷ b"
    directly beneath the structure chip's own "Not enough here to read a
    shape yet". One panel, one render, contradicting itself.

Separately, `share` is an INFLUENCE share, and on a graph where nobody
brokers anything (disjoint clusters → every betweenness 0 → totalBc 0) every
share collapsed to 0. "Main topics" showed two equal halves of the map as
"0% · 3 items" and "0% · 3 items".

This runs the REAL `analyze()` — bundled with the project's own esbuild,
since the worker uses bundler-resolved subpath imports bare node ESM cannot
follow — rather than re-implementing its branches, which would agree with
itself perfectly while the shipped code did something else.

Run: python3 scripts/test_graph_gap_verdict.py
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKER = ROOT / 'analytics.worker.js'
VIEW = ROOT / 'views' / 'graph.jsx'

FAILS = []

# Two disjoint triangles, then the joins that vary between cases.
TRI = [['a', 'b'], ['b', 'c'], ['a', 'c'], ['d', 'e'], ['e', 'f'], ['d', 'f']]
CROSS6 = [['a', 'd'], ['b', 'e'], ['c', 'f'], ['a', 'e'], ['b', 'f'], ['c', 'd']]

CASES = {
    'isolated3':  (['a', 'b', 'c'], []),
    'joined6':    ('abcdef', TRI + CROSS6),
    'bridge1':    ('abcdef', TRI + [['c', 'd']]),
    'bridge0':    ('abcdef', TRI),
    'clique':     ('abcd', [['a', 'b'], ['a', 'c'], ['a', 'd'], ['b', 'c'], ['b', 'd'], ['c', 'd']]),
    'lone':       (['a'], []),
    # The real office, measured: one coworker with two receipts attached, and
    # three coworkers nobody has given work to yet.
    'orphans':    ('abcdef', [['a', 'b'], ['a', 'c']]),
    # Two two-item topics, unjoined — the smallest pair that is still a pair.
    'pairs2':     ('abcd', [['a', 'b'], ['c', 'd']]),
    # A vault with nothing in it at all — the N === 0 early return.
    'nograph':    ([], []),
}


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run_analyze():
    """Bundle the worker for node and return per-case {structure, gap, shares}."""
    src = re.sub(r'self\.onmessage[\s\S]*$', '', WORKER.read_text(encoding='utf-8'))
    tmp_src = ROOT / '._gap_src.mjs'
    tmp_out = ROOT / '._gap_bundle.cjs'
    tmp_run = ROOT / '._gap_run.cjs'
    cases = {k: [list(n), e] for k, (n, e) in CASES.items()}
    try:
        tmp_src.write_text(src + '\nexport { analyze };\n', encoding='utf-8')
        subprocess.run(['npx', 'esbuild', tmp_src.name, '--bundle', '--format=cjs',
                        '--platform=node', f'--outfile={tmp_out.name}', '--log-level=error'],
                       cwd=ROOT, check=True, capture_output=True, timeout=180)
        tmp_run.write_text('''
const { analyze } = require('./%s');
const cases = %s;
const out = {};
for (const [k, [nodes, edges]] of Object.entries(cases)) {
  const r = analyze({ nodes: nodes.map(id => ({ id })),
                      edges: edges.map(([s, d]) => ({ source: s, target: d })) });
  out[k] = { structure: r.metrics.structure || null,
             gap: r.gap ? { between: r.gap.between } : null,
             shares: r.clusters.map(c => c.share),
             clusters: r.clusters.length,
             // Which of the labelled metrics came back undefined — a label
             // with nothing after it is what the panel actually renders.
             missing: ['nodes','edges','communityCount','components','avgDegree','structure']
                        .filter(k2 => r.metrics[k2] === undefined),
             topInfluential: r.topInfluential.length };
}
console.log(JSON.stringify(out));
''' % (tmp_out.name, json.dumps(cases)), encoding='utf-8')
        res = subprocess.run(['node', tmp_run.name], cwd=ROOT, check=True,
                             capture_output=True, text=True, timeout=120)
        return json.loads(res.stdout.strip().splitlines()[-1])
    finally:
        for f in (tmp_src, tmp_out, tmp_run):
            try:
                f.unlink()
            except FileNotFoundError:
                pass


def main():
    print('graph gap verdict — "weakly connected" only said when it is true')
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

    # ── The false alarms ────────────────────────────────────────────────
    check('two groups joined by 6 cross edges are not called "weakly connected"',
          got['joined6']['gap'] is None,
          'a densely joined pair still reported a structural gap — the score '
          'ranks pairs relatively, so SOME pair always wins unless a real '
          'threshold gates it')
    check('a shapeless graph reports no gap in its shape',
          got['isolated3']['gap'] is None and got['isolated3']['structure'] == 'unformed',
          f"structure={got['isolated3']['structure']!r} gap={got['isolated3']['gap']!r} — "
          'the panel contradicted its own "not enough here to read a shape yet" '
          'in the same render')
    check('a single-cluster graph reports no gap',
          got['clique']['gap'] is None and got['lone']['gap'] is None,
          'nothing to be weakly connected TO')
    check('an orphan item does not become a "topic" on one side of a gap',
          got['orphans']['gap'] is None,
          f"got {got['orphans']['gap']!r} — this is the real office's own shape "
          '(one coworker with two receipts, three coworkers nobody has given work '
          'to). It picked "Weakly connected: Llama ⟷ Hermes": true, and useless, '
          'because everything is weakly connected to an orphan')

    # ── The other half: real gaps must survive. A fix that returns null ──
    # ── every time would pass everything above.                        ──
    check('a one-bridge pair is still reported as a gap',
          got['bridge1']['gap'] is not None and got['bridge1']['gap']['between'] == 1,
          f"got {got['bridge1']['gap']!r} — the threshold has swallowed a real gap, "
          'which is exactly what a hurried fix would do')
    check('two entirely unconnected groups are still reported as a gap',
          got['bridge0']['gap'] is not None and got['bridge0']['gap']['between'] == 0,
          f"got {got['bridge0']['gap']!r} — same")
    check('two TWO-item topics still qualify — the orphan gate stops at 1',
          got['pairs2']['gap'] is not None,
          f"got {got['pairs2']['gap']!r} — the smallest thing that is genuinely a "
          'pair of topics must still be reportable, or the gate has crept up into '
          'real data')

    # ── Cluster share ───────────────────────────────────────────────────
    check('equal halves of a brokerless graph are not both "0%"',
          all(abs(s - 0.5) < 1e-9 for s in got['bridge0']['shares']),
          f"got {got['bridge0']['shares']!r} — with no brokering anywhere the "
          'influence share is undefined for everyone, and 0% is false for half '
          'the map; it must fall back to size share')
    check('...and shares still sum to 1 where brokering does exist',
          abs(sum(got['bridge1']['shares']) - 1.0) < 1e-6,
          f"got {got['bridge1']['shares']!r}")

    # ── The empty heading ───────────────────────────────────────────────
    check('nothing brokers on a disjoint graph (premise of the next check)',
          got['bridge0']['topInfluential'] == 0,
          f"got {got['bridge0']['topInfluential']} — if this ever becomes non-zero "
          'the heading check below stops testing anything')
    view = VIEW.read_text(encoding='utf-8')
    check('the "Most influential" heading is conditional on having any',
          re.search(r'topInfluential\s*\|\|\s*\[\]\)\.length\s*>\s*0', view) is not None,
          'views/graph.jsx: a bold heading over blank space reads as a surface '
          'that failed to load, not one with nothing true to say yet')
    check('the "Main topics" heading is conditional too',
          re.search(r'clusters\s*\|\|\s*\[\]\)\.length\s*>\s*0', view) is not None,
          'views/graph.jsx: same heading-over-nothing on an empty vault')

    # ── An empty vault must still answer every question the panel asks ──
    check('an empty vault has no unanswered metrics',
          got['nograph']['missing'] == [],
          f"undefined: {got['nograph']['missing']!r} — the panel renders these as "
          'labels with NOTHING after them ("Topics:" / "Separate clusters:"), '
          'which reads as a surface that failed to load')
    check('...and it names itself unformed rather than showing a bare dash',
          got['nograph']['structure'] == 'unformed',
          f"got {got['nograph']['structure']!r} — the chip falls back to '—' with no "
          'sentence under it')
    check('...with no gap, no brokers and no topics claimed',
          (got['nograph']['gap'] is None and got['nograph']['topInfluential'] == 0
           and got['nograph']['clusters'] == 0),
          f"got {got['nograph']!r}")

    # ── Source-level: the guard must be inside the gap block ────────────
    src = WORKER.read_text(encoding='utf-8')
    block = src[src.find('  let gap = null;'):]
    block = block[:block.find('\n\n')]
    check('the unformed guard gates the gap block',
          "structure !== 'unformed'" in block,
          'analytics.worker.js: without it a graph with no shape still gets a '
          'verdict about the shape')
    check('the threshold compares cross-links against the smaller group',
          re.search(r'between\s*>=\s*Math\.min\(', block) is not None,
          'analytics.worker.js: a threshold that cannot be said out loud is how '
          'the relative score got printed as an absolute claim')
    check('...and single-item clusters are excluded by name',
          re.search(r'size\s*<\s*2', block) is not None,
          'analytics.worker.js: without it the pick lands on whichever orphan '
          'happens to sort first')

    print()
    if FAILS:
        print(f'graph gap verdict: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('graph gap verdict: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
