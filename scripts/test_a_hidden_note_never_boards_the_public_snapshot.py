#!/usr/bin/env python3
"""A note the boss hid from the graph must never board the public snapshot.

Bug: graph-engine.js exportSnapshot() returned `this.graph.export()` — the
WHOLE graph. But the canvas the boss was looking at when they pressed
"⤴ Share" is the graph AFTER the reducers: nodes dropped via the
right-click "Hide node" menu (views/graph.jsx feeds engine.setHidden), nodes
excluded by the filter box, nodes outside the local-depth set. Every one of
those — title, path, tags, and the raw backend record riding on `_node`
(which for message-thread nodes includes a body preview) — was serialized
into the publish payload anyway, and serve.py's /graph/snapshot/<slug>
serves that JSON WITHOUT the API key by design (it's the public share
surface). So hiding a private note and then sharing the graph handed that
very note to anyone with the link. The analytics block leaked the same ids
a second way: nodeAttrs keys, topInfluential rows, cluster topNodes
exemplars, and the gap's aTop/bTop endpoints.

Fix: exportSnapshot() now prunes every node _visible() rejects, every edge
touching one, and the pruned nodes' analytics traces, before the payload
leaves the engine. One visibility verdict owns both the canvas and the
snapshot — the export did not grow a second copy of the filter logic.

This lifts the REAL sources — _visible and exportSnapshot out of
graph-engine.js — into a node harness (brace-balanced extraction, same
technique as test_graph_filter_speaks_its_own_placeholder_syntax.py) and
drives the export end-to-end.
Run: python3 scripts/test_a_hidden_note_never_boards_the_public_snapshot.py
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
    print('Publish — the snapshot carries only what the boss could see')
    if not ENGINE.is_file():
        print(f'  FAIL  missing {ENGINE}')
        return 1
    eng_src = ENGINE.read_text(encoding='utf-8')

    visible = extract_method(eng_src, '_visible')
    export = extract_method(eng_src, 'exportSnapshot')
    check('_visible lifted from graph-engine.js', visible is not None)
    check('exportSnapshot lifted from graph-engine.js', export is not None)
    if FAILS:
        print('\nFAILED: %s' % FAILS)
        return 1

    harness = '''
// Minimal engine stand-in carrying only what _visible/exportSnapshot touch.
// Export shape mirrors graphology's graph.export(): {nodes:[{key,attributes}],
// edges:[{key,source,target,attributes}]} — attributes carry the raw record
// on _node exactly as graph-engine.js _build stores it.
const attrs = (n) => ({ label: n.title, _node: n, _type: n.type || 'note',
                        _tags: n.tags || [], _path: n.id });
const N = [
  { id: 'notes/public plan.md', title: 'public plan', type: 'note', tags: [] },
  { id: 'notes/secret salary.md', title: 'secret salary', type: 'note', tags: [] },
  { id: 'notes/roadmap.md', title: 'Roadmap', type: 'note', tags: [] },
];
const rawExport = () => ({
  attributes: {}, options: {},
  nodes: N.map((n) => ({ key: n.id, attributes: attrs(n) })),
  edges: [
    { key: 'e0', source: 'notes/public plan.md', target: 'notes/secret salary.md', attributes: {} },
    { key: 'e1', source: 'notes/secret salary.md', target: 'notes/roadmap.md', attributes: {} },
    { key: 'e2', source: 'notes/public plan.md', target: 'notes/roadmap.md', attributes: {} },
  ],
});
const analytics = () => ({
  metrics: { nodes: 3, edges: 3 },
  nodeAttrs: {
    'notes/public plan.md': { betweenness: 0.5, community: 0 },
    'notes/secret salary.md': { betweenness: 0.9, community: 1 },
    'notes/roadmap.md': { betweenness: 0.2, community: 0 },
  },
  topInfluential: [{ id: 'notes/secret salary.md', bc: 0.9 },
                   { id: 'notes/public plan.md', bc: 0.5 }],
  clusters: [{ community: 0, size: 2, topNodes: ['notes/public plan.md', 'notes/roadmap.md'] },
             { community: 1, size: 1, topNodes: ['notes/secret salary.md'] }],
  gap: { a: 0, b: 1, between: 1, aTop: 'notes/public plan.md', bTop: 'notes/secret salary.md' },
});
const mkEngine = () => {
  const e = {
    hidden: new Set(), localSet: null, filterText: '', filterFn: null,
    analytics: analytics(), opts: { now: 777 },
    graph: { export: rawExport },
    %(visible)s,
    %(export)s,
  };
  e._visible = e._visible.bind(e);
  e.exportSnapshot = e.exportSnapshot.bind(e);
  return e;
};
const ids = (snap) => snap.graph.nodes.map((n) => n.key);
const edgeKeys = (snap) => snap.graph.edges.map((e) => e.key);
const out = {};

// 1. Nothing hidden — everything exports, analytics ride through, ts kept.
let e = mkEngine();
let snap = e.exportSnapshot();
out.full = { ids: ids(snap), edges: edgeKeys(snap), ts: snap.ts,
             top: snap.analytics.topInfluential.length };

// 2. "Hide node" on the secret note — it, its edges, and its analytics traces
//    must all stay home.
e = mkEngine();
e.hidden = new Set(['notes/secret salary.md']);
snap = e.exportSnapshot();
out.hidden = {
  ids: ids(snap), edges: edgeKeys(snap),
  serialized: JSON.stringify(snap).includes('secret salary'),
  nodeAttrKeys: Object.keys(snap.analytics.nodeAttrs),
  top: snap.analytics.topInfluential.map((t) => t.id),
  clusterTops: snap.analytics.clusters.map((c) => c.topNodes),
  gap: snap.analytics.gap,
};

// 3. Filter-box exclusion prunes through the same verdict.
e = mkEngine();
e.filterFn = (n) => n.title !== 'secret salary';
snap = e.exportSnapshot();
out.filtered = { ids: ids(snap),
                 serialized: JSON.stringify(snap).includes('secret salary') };
console.log(JSON.stringify(out));
''' % {'visible': visible.replace('function _visible', '_visible: function', 1),
       'export': export.replace('function exportSnapshot', 'exportSnapshot: function', 1)}

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

    check('with nothing excluded, all three notes and all three links export',
          out['full']['ids'] == ['notes/public plan.md', 'notes/secret salary.md',
                                 'notes/roadmap.md']
          and out['full']['edges'] == ['e0', 'e1', 'e2'], str(out['full']))
    check('...and analytics + ts ride through untouched',
          out['full']['top'] == 2 and out['full']['ts'] == 777, str(out['full']))

    h = out['hidden']
    check('a note hidden via "Hide node" is not among the exported nodes',
          h['ids'] == ['notes/public plan.md', 'notes/roadmap.md'], str(h['ids']))
    check('every edge touching the hidden note is gone; the visible pair keeps theirs',
          h['edges'] == ['e2'], str(h['edges']))
    check('the hidden note appears NOWHERE in the serialized snapshot',
          h['serialized'] is False, 'the note text still rides somewhere in the JSON')
    check('analytics nodeAttrs no longer key the hidden note',
          h['nodeAttrKeys'] == ['notes/public plan.md', 'notes/roadmap.md'],
          str(h['nodeAttrKeys']))
    check('topInfluential no longer lists the hidden note',
          h['top'] == ['notes/public plan.md'], str(h['top']))
    check("clusters' topNodes exemplars no longer name it",
          h['clusterTops'] == [['notes/public plan.md', 'notes/roadmap.md'], []],
          str(h['clusterTops']))
    check('a gap whose endpoint is the hidden note is dropped, not leaked',
          h['gap'] is None, str(h['gap']))

    check('the filter box prunes the export through the same verdict',
          out['filtered']['ids'] == ['notes/public plan.md', 'notes/roadmap.md']
          and out['filtered']['serialized'] is False, str(out['filtered']))

    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'public snapshot pruning: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
