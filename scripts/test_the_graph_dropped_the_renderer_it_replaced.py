#!/usr/bin/env python3
"""The graph file said its WebGL engine "replaces the legacy Canvas-2D
renderer below" — and the renderer was still below.

`views/graph.jsx`'s GraphView has mounted `window.CafresoGraphEngine`
(sigma.js + graphology) since the WebGL cut-over; nothing in the live app
drew a graph on a 2D canvas any more. But the old engine's parts were never
taken out: `simulate` (the O(n²) force pass, ~110 lines), `connectedComponents`,
`shortestPathBetween`, `neighborInDirection`, and in `views/vault.jsx` the
`useForceGraph` hook that was the only caller of `simulate` — a
requestAnimationFrame loop nobody ever mounted. Grepped across every shipped
.jsx at HEAD before removal: `useForceGraph` had zero call sites, so
`simulate` had zero reachable callers, and the other three had none at all.
`simulate` was even still exported from graph.jsx and imported into
vault.jsx, purely to feed the dead hook.

One correction to the report that flagged this: it listed `graphAdjacency`
as dead too. It is not — `getNeighbors` calls it, and `getNeighbors` is
called from two live sites in GraphView. `graphAdjacency` stays, and this
test pins THAT as firmly as it pins the removals, so a later sweep cannot
take the adjacency map out on the strength of the same stale list.

Removal-only change: no behaviour is touched, the engine mount is untouched,
and the docstring now says what is true.

Run: python3 scripts/test_the_graph_dropped_the_renderer_it_replaced.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / 'views' / 'graph.jsx'
VAULT = ROOT / 'views' / 'vault.jsx'
# Every directory the bundle is built from (package.json's lint globs).
JSX_ROOTS = ['.', 'views', 'ui', 'modals', 'app']

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def shipped_jsx():
    for d in JSX_ROOTS:
        for p in sorted((ROOT / d).glob('*.jsx')):
            yield p


def main():
    print('the graph no longer carries the Canvas-2D renderer it replaced')
    for p in (GRAPH, VAULT):
        if not p.is_file():
            print(f'  FAIL  missing {p.relative_to(ROOT)}')
            return 1
    graph = GRAPH.read_text(encoding='utf-8')
    vault = VAULT.read_text(encoding='utf-8')

    # ── 1. the dead engine parts are gone from graph.jsx ────────────────
    for fn in ('simulate', 'connectedComponents', 'shortestPathBetween',
               'neighborInDirection'):
        check(f'graph.jsx no longer defines {fn}()',
              not re.search(r'^\s*function\s+' + fn + r'\s*\(', graph, re.M),
              'the legacy Canvas-2D renderer is still below the WebGL view')

    m = re.search(r'^export\s*\{([^}]*)\}\s*;?\s*$', graph, re.M)
    exported = [s.strip() for s in (m.group(1).split(',') if m else [])]
    check('graph.jsx exports GraphView and not the dead simulate',
          exported == ['GraphView'], exported)

    # ── 2. the dead hook and its import are gone from vault.jsx ─────────
    check('vault.jsx no longer defines useForceGraph',
          'useForceGraph' not in vault)
    im = re.search(r"^import\s*\{([^}]*)\}\s*from\s*'\./graph\.jsx';", vault, re.M)
    imported = [s.strip() for s in (im.group(1).split(',') if im else [])]
    check("vault.jsx imports only GraphView from './graph.jsx'",
          imported == ['GraphView'], imported)
    check('vault.jsx never calls simulate()',
          not re.search(r'\bsimulate\s*\(', vault))

    # ── 3. nothing shipped reaches for any of them ──────────────────────
    dead = re.compile(r'\b(connectedComponents|shortestPathBetween|'
                      r'neighborInDirection|useForceGraph)\b|\bsimulate\s*\(')
    hits = [f'{p.relative_to(ROOT)}:{i}' for p in shipped_jsx()
            for i, line in enumerate(p.read_text(encoding='utf-8').splitlines(), 1)
            if dead.search(line)]
    check('no shipped .jsx references a removed symbol', not hits, hits[:5])

    # ── 4. over-deletion guards: what the stale list got wrong stays ────
    check('graphAdjacency is still defined — it was reported dead and is not',
          re.search(r'^function graphAdjacency\(', graph, re.M))
    check('getNeighbors still calls graphAdjacency',
          re.search(r'function getNeighbors\([^)]*\)\s*\{[^}]*graphAdjacency\(', graph))
    check('getNeighbors still has live callers in GraphView',
          len(re.findall(r'\bgetNeighbors\(state, focusId\)', graph)) >= 2)
    check('clusterColor is still called',
          re.search(r'\bclusterColor\(idx, isDark\)', graph))

    # ── 5. the replacement is real and the docstring says so ────────────
    check('GraphView still mounts window.CafresoGraphEngine',
          'window.CafresoGraphEngine.mount(' in graph)
    check('the docstring no longer promises a renderer "below"',
          'renderer below' not in graph)

    print()
    if FAILS:
        print(f'graph renderer removal: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('graph renderer removal: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
