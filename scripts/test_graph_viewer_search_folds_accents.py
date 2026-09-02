#!/usr/bin/env python3
"""The standalone public graph viewer's search box missed accented notes —
the same bug already fixed three times this session in other search
surfaces built on the same vault content (serve.py's vault search,
views/vault.jsx's bridgeSearch, views/graph.jsx's nodeMatchesFilter),
just missed in this one remaining file.

graph-viewer.js (the standalone/embeddable graph-viewer.html script —
the Library's "watch it grow" shareable link, not internal-only
tooling) powers its search box with `bestMatch()` and `apply()`, both
of which used to compare labels with plain `.toLowerCase()`:

    const label = String(fullLabel.get(id) || g.getNodeAttribute(id, 'label') || '').toLowerCase();
    ...
    g.forEachNode((id, a) => { if (String(fullLabel.get(id) || a.label || '').toLowerCase().includes(q)) searchSet.add(id); });

Concrete repro: a node titled "...investigación..." exists in a shared
graph. Typing "investigacion" (no accent — the natural way to type it
on a US keyboard) into the graph-viewer's search box would not find it,
though the identical query already works against /vault/search, the
encrypted bridge vault, and the Library's own in-app graph filter.

Found by a hunt agent re-verifying a gap flagged (but not yet fixed) by
an earlier hunt this session.

Fix: added a module-level `foldAccents` helper (same NFD-decompose,
drop U+0300-U+036F combining marks, lowercase algorithm as
views/graph.jsx's `_foldAccents` / serve.py's `_fold_accents`), and
used it in place of the bare `.toLowerCase()` calls at every label/query
comparison site: `bestMatch`'s label scoring, `apply`'s label matching
and query normalization, and the Enter-key handler's call into
`bestMatch`.

Run: python3 scripts/test_graph_viewer_search_folds_accents.py
(skips the live-execution checks if `node` isn't on PATH — the
source-shape checks still run everywhere)
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH_VIEWER_JS = ROOT / 'graph-viewer.js'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("graph-viewer.js's search box folds accents like every other vault-backed search surface")

    src = GRAPH_VIEWER_JS.read_text(encoding='utf-8')

    fold_m = re.search(
        r"function foldAccents\(s\) \{ return String\(s \|\| ''\)"
        r"\.normalize\('NFD'\)\.replace\(/\[([^\]]+)\]/g, ''\)\.toLowerCase\(\); \}",
        src)
    check('found the foldAccents helper', fold_m is not None)
    check('foldAccents drops Unicode combining marks (U+0300-U+036F), '
          "matching serve.py's _fold_accents and views/graph.jsx's _foldAccents",
          fold_m and fold_m.group(1) == '\\u0300-\\u036f',
          fold_m and fold_m.group(1))

    best_m = re.search(r"const bestMatch = \(q\) => \{(.*?)\n    \};", src, re.S)
    check('found bestMatch', best_m is not None)
    best_body = best_m.group(1) if best_m else ''
    check('bestMatch folds the label instead of a bare .toLowerCase() — '
          'the actual regression',
          'foldAccents(fullLabel.get(id) || g.getNodeAttribute(id, \'label\') || \'\')' in best_body)

    apply_m = re.search(r"const apply = \(\) => \{(.*?)\n    \};", src, re.S)
    check('found apply', apply_m is not None)
    apply_body = apply_m.group(1) if apply_m else ''
    check('apply folds the query before using it',
          "const q = foldAccents(searchInput.value.trim());" in apply_body)
    check('apply folds each label before matching against the folded query',
          "foldAccents(fullLabel.get(id) || a.label || '').includes(q)" in apply_body)

    check('the Enter-key handler folds its query before calling bestMatch '
          '(not just .toLowerCase(), which would leave bestMatch comparing '
          'a folded label against an unfolded query)',
          'bestMatch(foldAccents(searchInput.value.trim()))' in src)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted '
          'foldAccents/bestMatch logic below)', has_node,
          'skipping the live-execution check')

    if has_node and fold_m and best_m:
        js = f"""
        {fold_m.group(0)}
        {best_m.group(0).replace('const bestMatch', 'const bestMatch')}
        // 'b' is a much bigger node (baseSize) than 'a', so bestMatch only
        // picks 'a' if the prefix-match bonus (which needs folded equality
        // between the query and 'a's folded label) actually fires.
        const fullLabel = new Map([['a', 'Investigaci\\u00f3n solar'], ['b', 'Otro nodo, mucho mas grande']]);
        const baseSize = new Map([['a', 5], ['b', 50]]);
        const g = {{ getNodeAttribute: () => null }};
        const searchSet = new Set(['a', 'b']);

        const unaccentedQuery = foldAccents('investigacion');
        const accentedQuery = foldAccents('investigaci\\u00f3n');
        const hitUnaccented = bestMatch(unaccentedQuery);
        const hitAccented = bestMatch(accentedQuery);
        const noQueryMatch = bestMatch(foldAccents('something else entirely'));
        console.log(JSON.stringify({{ hitUnaccented, hitAccented, noQueryMatch }}));
        """
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the extracted foldAccents/bestMatch logic ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-800:])
        if r.returncode == 0:
            out = json.loads(r.stdout.strip().splitlines()[-1])
            check('an unaccented query ("investigacion") now finds a node '
                  'titled with the accented spelling — this is exactly '
                  'what was missing before the fix',
                  out.get('hitUnaccented') == 'a', out)
            check('the accented query still matches too (folding must not '
                  'break the case that already worked)',
                  out.get('hitAccented') == 'a', out)
            check('a query with no prefix match falls back to the bigger '
                  "node (baseSize tiebreak) — sanity check the harness's "
                  'scoring isn\'t a tautology that always returns "a"',
                  out.get('noQueryMatch') == 'b', out)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
