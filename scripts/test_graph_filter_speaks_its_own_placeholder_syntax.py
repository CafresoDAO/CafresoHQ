#!/usr/bin/env python3
"""The graph filter box must actually speak the syntax its placeholder advertises.

Bug: the WebGL GraphView (views/graph.jsx) shows a filter input whose
placeholder promises the legacy grammar — "Filter  (tag:x  type:y  -term)" —
but it forwarded the raw text to graph-engine.js setFilter, and the engine's
_visible() matched the WHOLE query as one lowercased substring over
label/path/type/tags. So typing the placeholder's own example ("tag:project")
hid every node (no hay contains the literal text "tag:project"), a negation
("-daily") blanked the graph instead of excluding, two words in the wrong
order ("planning meeting" vs a note titled "meeting planning") found nothing,
and the accent folding nodeMatchesFilter carries (its comment block sits at
the very top of graph.jsx) never ran on this renderer at all.

Fix: graph-engine.js setFilter() now accepts a predicate over the raw node
record (falling back to the old string/substring path for plain strings), and
GraphView wraps its filter text with filterMatcher(), a closure over the
grammar-aware nodeMatchesFilter that both call sites (mountData's re-apply
and the [filter] effect) pass to the engine. One matcher owns the grammar;
the engine did not grow a second copy of the syntax.

This lifts the REAL sources — _visible/setFilter out of graph-engine.js and
_foldAccents/filterMatcher/nodeMatchesFilter out of views/graph.jsx — into a
node harness (brace-balanced extraction, same technique as
test_workspace_terminal_key.py) and drives the engine's visibility verdict
end-to-end for the advertised operators.
Run: python3 scripts/test_graph_filter_speaks_its_own_placeholder_syntax.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / 'graph-engine.js'
VIEW = ROOT / 'views' / 'graph.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def extract_function(src, name):
    """Brace-balanced extraction of `function NAME(...) { ... }`."""
    m = re.search(r'function\s+' + re.escape(name) + r'\s*\([^)]*\)\s*\{', src)
    if not m:
        return None
    depth = 0
    j = m.end() - 1
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
        j += 1
    return None


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


def extract_const_arrow(src, name):
    """Extraction of `const NAME = (…) => …;` up to the terminating `;`
    at paren/brace depth 0 (both graph.jsx arrows are single expressions)."""
    m = re.search(r'const\s+' + re.escape(name) + r'\s*=', src)
    if not m:
        return None
    depth = 0
    j = m.end()
    while j < len(src):
        c = src[j]
        if c in '({[':
            depth += 1
        elif c in ')}]':
            depth -= 1
        elif c == ';' and depth == 0:
            return src[m.start():j + 1]
        j += 1
    return None


def main():
    print('Graph filter — engine honors the advertised grammar via nodeMatchesFilter')
    for p in (ENGINE, VIEW):
        if not p.is_file():
            print(f'  FAIL  missing {p}')
            return 1
    eng_src = ENGINE.read_text(encoding='utf-8')
    view_src = VIEW.read_text(encoding='utf-8')

    # ── Structural: the shell passes the matcher, not the raw string ──────
    check('GraphView defines filterMatcher over nodeMatchesFilter',
          bool(re.search(r'const\s+filterMatcher\s*=.*nodeMatchesFilter', view_src)))
    check("mountData re-applies the matcher (not the raw ref) on remount",
          'eng.setFilter(filterMatcher(filterRef.current))' in view_src)
    check('the [filter] effect passes the matcher too',
          'e.setFilter(filterMatcher(filter))' in view_src)
    check('no call site still hands the engine the raw filter string',
          not re.search(r'setFilter\(\s*filter(?:Ref\.current)?\s*\)', view_src))

    # ── Behavioral: drive the REAL engine verdict through node ────────────
    visible = extract_method(eng_src, '_visible')
    set_filter = extract_method(eng_src, 'setFilter')
    fold = extract_const_arrow(view_src, '_foldAccents')
    matcher = extract_const_arrow(view_src, 'filterMatcher')
    nmf = extract_function(view_src, 'nodeMatchesFilter')
    check('_visible lifted from graph-engine.js', visible is not None)
    check('setFilter lifted from graph-engine.js', set_filter is not None)
    check('_foldAccents lifted from views/graph.jsx', fold is not None)
    check('filterMatcher lifted from views/graph.jsx', matcher is not None)
    check('nodeMatchesFilter lifted from views/graph.jsx', nmf is not None)
    if FAILS:
        print('\nFAILED: %s' % FAILS)
        return 1

    harness = '''
%(fold)s
%(nmf)s
%(matcher)s
// Minimal engine stand-in carrying only what _visible/setFilter touch.
const engine = {
  hidden: new Set(), localSet: null, filterText: '', filterFn: null,
  _refreshReducers() {},
  %(visible)s,
  %(set_filter)s,
};
engine._visible = engine._visible.bind(engine);
engine.setFilter = engine.setFilter.bind(engine);

// Engine-attr shape mirrors graph-engine.js _build (raw record on _node).
const attrs = (n) => ({ label: n.title || n.id, _node: n, _type: n.type || 'note',
                        _tags: n.tags || [], _path: n.id, _mtime: n.mtime || 0 });
const nodes = [
  { id: 'notes/meeting planning.md', title: 'meeting planning', type: 'note', tags: [] },
  { id: 'projects/roadmap.md', title: 'Roadmap', type: 'note', tags: ['#project'] },
  { id: 'daily/2026-08-30.md', title: 'daily log', type: 'note', tags: ['#daily'] },
  { id: 'notes/investigacion.md', title: 'La investigaci\\u00f3n', type: 'note', tags: [] },
];
const visibleIds = () => nodes.filter((n) => engine._visible(n.id, attrs(n))).map((n) => n.id);

const out = {};
engine.setFilter(filterMatcher('tag:project'));
out.tagOp = visibleIds();
engine.setFilter(filterMatcher('-daily'));
out.negation = visibleIds();
engine.setFilter(filterMatcher('planning meeting'));
out.wordOrder = visibleIds();
engine.setFilter(filterMatcher('investigacion'));
out.accents = visibleIds();
engine.setFilter(filterMatcher(''));
out.cleared = visibleIds().length;
engine.setFilter('roadmap');            // plain-string fallback path intact
out.stringFallback = visibleIds();
console.log(JSON.stringify(out));
''' % {'fold': fold, 'nmf': nmf, 'matcher': matcher,
       'visible': visible.replace('function _visible', '_visible: function', 1),
       'set_filter': set_filter.replace('function setFilter', 'setFilter: function', 1)}

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

    check("tag:project shows exactly the #project note (the placeholder's own example)",
          out['tagOp'] == ['projects/roadmap.md'], str(out['tagOp']))
    check('-daily excludes the daily note and keeps the other three',
          out['negation'] == ['notes/meeting planning.md', 'projects/roadmap.md',
                              'notes/investigacion.md'], str(out['negation']))
    check('"planning meeting" still finds the note titled "meeting planning"',
          out['wordOrder'] == ['notes/meeting planning.md'], str(out['wordOrder']))
    check("unaccented 'investigacion' finds the accented title",
          out['accents'] == ['notes/investigacion.md'], str(out['accents']))
    check('clearing the filter shows every node again', out['cleared'] == 4, str(out['cleared']))
    check('a plain string still works as the substring fallback',
          out['stringFallback'] == ['projects/roadmap.md'], str(out['stringFallback']))

    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'graph filter grammar: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
