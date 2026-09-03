#!/usr/bin/env python3
"""The office judged the balance of the boss's thinking from one delivery.

Measured live (#147), following the getting-started checklist end to end on a
fresh office: hire Llama, take the FIRST ASSIGNMENT, watch the brief get
written and filed, press "Open it →". The Library opened on the delivered file
and the analytics panel beside it read:

    Biased
    One dominant topic — add contrasting ideas.
    On the map: 3      Topics: 1      Separate clusters: 1

Three nodes: the brief, its file, and the coworker who wrote it. The office's
opening assessment of the boss's first piece of work was that it is biased and
needs correcting.

WHAT THIS IS NOT. The first reading was that "one dominant topic" is vacuous
when there is only one topic, and the first fix a new `unified` state for
every single-community graph. That was wrong, and the suite next door caught
it: test_a_dominant_topic_is_actually_dominant.py pins the promise the chip
makes -- if the panel claims one topic dominates, the topic list under it has
to agree -- and here it does. One topic holding 100% of the map is maximal
dominance, not a missing comparison. A mature library that really has drifted
onto a single theme should be told so; that advice is the point of the panel.
The first fix broke a ten-node clique and a twelve-node star that suite
defends on purpose, and this file was rewritten around the correction.

WHAT IT IS. The evidence is wrong, not the arithmetic. "Add contrasting
ideas" is a judgement about the balance of somebody's thinking, and after one
delivery there is nothing for it to be a balance between. A brand-new office
cannot be anything except single-topic, so the verdict carries no information
about the boss and lands as criticism of their first piece of work.

So the floor rises instead of the line moving, and `unformed` -- which already
says "not enough here to read a shape yet" -- covers it without a sixth state.
The guard is narrow on purpose: single community AND small. Anything with real
topic structure, at any size, is untouched.

Runs the REAL analyze(), bundled with the project's own esbuild, because a
re-implementation would agree with itself while the shipped worker said
something else.

Run: python3 scripts/test_a_first_run_is_not_judged.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKER = ROOT / 'analytics.worker.js'
GRAPH = ROOT / 'views' / 'graph.jsx'
ESBUILD = ROOT / 'node_modules' / '.bin' / 'esbuild'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


PROBE = r'''
import { analyze } from './aw.mjs';
const mk = (n, links) => ({
  nodes: Array.from({length: n}, (_, i) => ({ id: 'n'+i, label: 'n'+i })),
  edges: links.map(([a,b]) => ({ source: 'n'+a, target: 'n'+b })),
});
const clique = (n, off=0) => { const e=[];
  for (let i=0;i<n;i++) for (let j=i+1;j<n;j++) e.push([i+off,j+off]); return e; };
const CASES = {
  // The office as measured: one brief, its file, its author.
  firstRun: mk(3, [[0,1],[0,2]]),
  // A couple more deliveries in, still one thread. A star, not a hub with a
  // tail: the first draft used [[0,1],[0,2],[0,3],[3,4],[4,5]] and Louvain
  // split it in two, so it was never exercising the single-community case
  // this check is about -- and 'focused' was the right answer for it.
  early:    mk(6, Array.from({length:5},(_,i)=>[0,i+1])),
  // The neighbouring suite's fixtures: single-topic maps big enough to mean
  // it. These must keep their verdict.
  clique10: mk(10, clique(10)),
  star12:   mk(13, Array.from({length:12},(_,i)=>[0,i+1])),
  // Small, but with real topic structure: the guard must not touch it.
  twoSmall: mk(6, [...clique(3), ...clique(3,3), [0,3]]),
  // Untouched controls.
  path20:   mk(20, Array.from({length:19},(_,i)=>[i,i+1])),
  unlinked: mk(3, []),
  empty:    mk(0, []),
};
const out = {};
for (const [k, g] of Object.entries(CASES)) {
  const r = analyze(g), m = r.metrics;
  out[k] = { structure: m.structure, nodes: m.nodes, edges: m.edges,
             topics: m.communityCount, clusters: r.clusters.length,
             modularity: m.modularity, largestShare: m.largestShare };
}
console.log(JSON.stringify(out));
'''


def run_analyze():
    """Bundle the real worker and run it. The temp dir lives INSIDE the repo
    so node resolves graphology from the project's own node_modules."""
    tmp = ROOT / '.analytics-probe-tmp'
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        src = WORKER.read_text(encoding='utf-8')
        # The worker ends in a `self.onmessage` binding node has no `self`
        # for. Everything above it is plain module code.
        cut = src.index('self.onmessage')
        (tmp / 'aw.mjs').write_text(src[:cut] + '\nexport { analyze };\n',
                                    encoding='utf-8')
        (tmp / 'probe.mjs').write_text(PROBE, encoding='utf-8')
        # cjs, not esm: graphology's dist is CommonJS and an esm bundle dies
        # on "Dynamic require of events is not supported".
        b = subprocess.run(
            [str(ESBUILD), '--bundle', str(tmp / 'probe.mjs'), '--format=cjs',
             '--platform=node', '--outfile=' + str(tmp / 'out.cjs'),
             '--log-level=error'],
            cwd=ROOT, capture_output=True, text=True, timeout=180)
        if b.returncode != 0:
            return None, 'esbuild: ' + b.stderr.strip()[:300]
        p = subprocess.run([shutil.which('node') or 'node', str(tmp / 'out.cjs')],
                           cwd=ROOT, capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            return None, 'node: ' + p.stderr.strip()[:300]
        return json.loads(p.stdout.strip().splitlines()[-1]), None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print('a first run is not judged')
    if not ESBUILD.exists() or not shutil.which('node'):
        print('  SKIP  node/esbuild not available — cannot run the real worker')
        return 0

    r, err = run_analyze()
    if r is None:
        print('  FAIL  could not run analyze(): ' + str(err))
        return 1

    print('1. the office as measured')
    fr = r['firstRun']
    # Guard the fixture before trusting anything it proves: this must remain
    # the shape that was on screen, or the checks below are about some other
    # graph.
    check('the fixture is still a first run: one community, three nodes',
          fr['clusters'] == 1 and fr['nodes'] == 3,
          f"clusters={fr['clusters']} nodes={fr['nodes']}")
    check('a first delivery is not called biased',
          fr['structure'] != 'biased',
          f"structure={fr['structure']!r} — \"add contrasting ideas\" is a "
          'judgement about the balance of the boss\'s thinking, and one '
          'delivery has nothing to be a balance between')
    check('...it is told there is not enough here to read yet',
          fr['structure'] == 'unformed', repr(fr['structure']))
    check('a few deliveries in, still one thread, still unjudged',
          r['early']['structure'] == 'unformed', repr(r['early']['structure']))

    print('2. the verdict was floored, not deleted')
    # The correction this file was rewritten around. A check that only
    # forbade `biased` on small graphs would also pass on a worker that had
    # dropped the verdict entirely — which is exactly the mistake made here
    # the first time, and which the neighbouring suite caught.
    for key in ('clique10', 'star12'):
        g = r[key]
        check(f'[{key}] a single-topic map big enough to mean it still says so',
              g['structure'] == 'biased',
              f"structure={g['structure']!r} nodes={g['nodes']} "
              f"largestShare={g['largestShare']} — one topic holding the whole "
              'map IS dominance; a library that has drifted onto one theme is '
              'owed that advice. See test_a_dominant_topic_is_actually_'
              'dominant.py, which defends these two on purpose.')

    print('3. the guard is narrow')
    # Small AND single-community. If it ever widens to small alone, a tiny
    # graph with real topic structure loses a true reading.
    ts = r['twoSmall']
    check('a small map with real topic structure is untouched',
          ts['clusters'] >= 2 and ts['structure'] != 'unformed',
          f"clusters={ts['clusters']} structure={ts['structure']!r} — the "
          'floor applies only where there is nothing to compare')
    check('a well-separated map is untouched',
          r['path20']['structure'] == 'diversified', repr(r['path20']['structure']))
    check('an unlinked cabinet still says so plainly',
          r['unlinked']['structure'] == 'unformed', repr(r['unlinked']['structure']))
    check('an empty office still says so plainly',
          r['empty']['structure'] == 'unformed', repr(r['empty']['structure']))

    print('4. the panel can say every verdict the worker reaches')
    # The invariant a new state is most likely to break — and the first fix
    # for this bug added one, so it nearly did.
    code = re.sub(r'/\*[\s\S]*?\*/', '', WORKER.read_text(encoding='utf-8'))
    emitted = set(re.findall(r"structure\s*=\s*'([a-z]+)'", code))
    emitted |= set(re.findall(r"structure:\s*'([a-z]+)'", code))
    # Both arms of the ternaries too — `(C > 0.5) ? 'biased' : 'overlapping'`
    # never matches an assignment pattern, and those are half the states.
    for a, b in re.findall(r"\?\s*'([a-z]+)'\s*:\s*'([a-z]+)'", code):
        emitted |= {a, b}
    gsrc = GRAPH.read_text(encoding='utf-8')
    block = gsrc[gsrc.index('const STRUCT_COPY'):]
    block = re.sub(r'/\*[\s\S]*?\*/', '', block[:block.index('\n  };')])
    have = set(re.findall(r'^\s*([a-z]+):', block, re.M))
    check('the sweep found the states this suite reasons about',
          {'biased', 'unformed'} <= emitted, f'emitted={sorted(emitted)}')
    missing = sorted(emitted - have)
    check('...and every one of them has a sentence in the panel',
          not missing,
          f'{missing} would render an empty sentence under a capitalised chip')

    print()
    if FAILS:
        print(f'first run: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('first run: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
