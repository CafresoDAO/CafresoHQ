#!/usr/bin/env python3
"""A hovered/selected node that got filtered/hidden away kept acting as focus.

Bug: graph-engine.js's _focusId() returned `this.hovered || this.selected`
unconditionally. Click a node to select it (or hover it), then narrow the
filter box, hide it via the context menu's "Hide node", or shrink local mode
so that node falls outside the kept set — the node itself correctly goes
invisible (_visible() catches it first in _nodeReducer/_edgeReducer), but
_focusId() kept returning its id as "the" focus. Every OTHER still-visible
node then got dimmed to DIM/DIM_LIGHT with its label blanked in
_nodeReducer (it isn't a neighbor of a node nobody can see), and every edge
not touching the invisible focus got hidden outright in _edgeReducer (the
"reveal only the focused node's edges" branch, res.hidden = true) — so
selecting a node and then filtering/hiding/scoping it away silently emptied
the whole edge layer and dimmed every remaining node, with nothing on
screen to explain why, until the user happened to hover or click again.

Fix: _focusId() now checks the candidate id is still on the graph AND still
passes _visible() before returning it; otherwise it returns null, exactly as
if nothing were focused.

This lifts the REAL _focusId/_neighborhood/_visible/_nodeReducer/_edgeReducer
sources out of graph-engine.js into a node harness (brace-balanced
extraction, same technique as
test_graph_filter_speaks_its_own_placeholder_syntax.py) and drives them
against a tiny graphology-free stand-in graph.
Run: python3 scripts/test_a_filtered_out_selection_still_haunted_the_graph.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / 'graph-engine.js'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def extract_method(src, name):
    """Brace-balanced extraction of a class method `NAME(...) { ... }`,
    returned as a standalone `function NAME(...) { ... }`."""
    m = re.search(r'^\s*' + re.escape(name) + r'\s*\(([^)]*)\)\s*\{', src, re.M)
    if not m:
        return None
    depth = 0
    j = src.index('{', m.start())
    start = j
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return 'function %s(%s) %s' % (name, m.group(1), src[start:j + 1])
        j += 1
    return None


def main():
    print("Graph selection — a filtered-out focus must stop haunting the render")
    if not ENGINE.is_file():
        print(f'  FAIL  missing {ENGINE}')
        return 1
    eng_src = ENGINE.read_text(encoding='utf-8')

    names = ['_focusId', '_neighborhood', '_visible', '_nodeReducer', '_edgeReducer']
    methods = {n: extract_method(eng_src, n) for n in names}
    for n in names:
        check(f'{n} lifted from graph-engine.js', methods[n] is not None)
    if FAILS:
        print('\nFAILED: %s' % FAILS)
        return 1

    body = '\n'.join(
        methods[n].replace('function %s' % n, '%s: function' % n, 1) + ','
        for n in names
    )

    harness = '''
const DIM = '#2a2733';
const DIM_LIGHT = '#d8d0c4';
const EDGE_SIZE = 0.9;
const EDGE_SIZE_FOCUS = 1.8;
// Minimal graphology-free stand-in graph: A -> B (A's own link), B -> C
// (an edge that touches neither A nor anything filtered out).
const NODES = {
  A: { label: 'Alpha', _node: { id: 'A', title: 'Alpha' }, _type: 'note', _tags: [] },
  B: { label: 'Beta',  _node: { id: 'B', title: 'Beta' },  _type: 'note', _tags: [] },
  C: { label: 'Gamma', _node: { id: 'C', title: 'Gamma' }, _type: 'note', _tags: [] },
};
const EDGES = {
  'A->B': { s: 'A', t: 'B', color: '#base', size: 0.9 },
  'B->C': { s: 'B', t: 'C', color: '#base', size: 0.9 },
};

const fakeGraph = {
  hasNode: (id) => Object.prototype.hasOwnProperty.call(NODES, id),
  getNodeAttributes: (id) => NODES[id],
  forEachNeighbor: (id, cb) => {
    for (const key in EDGES) {
      const e = EDGES[key];
      if (e.s === id) cb(e.t);
      if (e.t === id) cb(e.s);
    }
  },
  source: (edgeId) => EDGES[edgeId].s,
  target: (edgeId) => EDGES[edgeId].t,
};

const engine = {
  dark: true, hidden: new Set(), localSet: null, filterText: '', filterFn: null,
  hovered: null, selected: null, graph: fakeGraph, _nbrCache: null,
  _edgeBase() { return 'rgba(176,158,214,0.22)'; },
%(body)s
};
for (const n of ['_focusId', '_neighborhood', '_visible', '_nodeReducer', '_edgeReducer']) {
  engine[n] = engine[n].bind(engine);
}

const out = {};

// Baseline: select A while it is still visible — B (A's neighbor) stays
// full-strength, C (not a neighbor) dims, A->B is revealed.
engine.selected = 'A';
out.baseline_focus = engine._focusId();
out.baseline_B_dimmed = engine._nodeReducer('B', NODES.B).color === '#2a2733';
out.baseline_C_dimmed = engine._nodeReducer('C', NODES.C).color === '#2a2733';
out.baseline_edge_hidden = !!engine._edgeReducer('A->B', EDGES['A->B']).hidden;
// B->C touches neither A nor a neighbor of A, so with a real, visible focus
// it is correctly hidden too — "reveal only the focused node's own edges".
out.baseline_unrelated_edge_hidden = !!engine._edgeReducer('B->C', EDGES['B->C']).hidden;

// Now A gets filtered out from under the still-active selection — exactly
// what setFilter()/setHidden()/setLocalMode() do without touching
// this.selected. A itself must be invisible either way; what matters is
// everyone else, including an edge (B->C) that never touched A at all.
engine._nbrCache = null;
engine.filterFn = (rec) => rec.id !== 'A';
out.focus_after_filter = engine._focusId();
out.A_hidden = !!engine._nodeReducer('A', NODES.A).hidden;
out.B_dimmed_after = engine._nodeReducer('B', NODES.B).color === '#2a2733';
out.C_dimmed_after = engine._nodeReducer('C', NODES.C).color === '#2a2733';
out.unrelated_edge_hidden_after = !!engine._edgeReducer('B->C', EDGES['B->C']).hidden;

console.log(JSON.stringify(out));
''' % {'body': body}

    try:
        res = subprocess.run(['node', '-e', harness], capture_output=True, text=True, timeout=30)
    except Exception as e:  # noqa: BLE001
        check('node harness ran', False, str(e))
        print('\nFAILED: %s' % FAILS)
        return 1
    check('node harness ran clean', res.returncode == 0, res.stderr.strip()[:300])
    if res.returncode != 0:
        print('\nFAILED: %s' % FAILS)
        return 1
    out = json.loads(res.stdout.strip().splitlines()[-1])

    check('baseline: selecting visible A focuses the graph', out['baseline_focus'] == 'A', str(out))
    check("baseline: A's neighbor B is not dimmed", not out['baseline_B_dimmed'], str(out))
    check('baseline: non-neighbor C is dimmed', out['baseline_C_dimmed'], str(out))
    check("baseline: A->B is revealed as the focus's own edge, not hidden",
          not out['baseline_edge_hidden'], str(out))
    check("baseline: unrelated edge B->C is correctly hidden while A is focused",
          out['baseline_unrelated_edge_hidden'], str(out))

    check('A is (still, correctly) hidden once filtered out', out['A_hidden'], str(out))
    check('a filtered-out focus no longer reports as the focus',
          out['focus_after_filter'] is None, str(out))
    check('B is no longer dimmed once its filtered-out "focus" stops haunting it',
          not out['B_dimmed_after'], str(out))
    check('C is no longer dimmed once its filtered-out "focus" stops haunting it',
          not out['C_dimmed_after'], str(out))
    check("B->C is no longer hidden — a phantom focus can't blank edges that never touched it",
          not out['unrelated_edge_hidden_after'], str(out))

    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'graph selection ghosting: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
