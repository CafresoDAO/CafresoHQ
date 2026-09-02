#!/usr/bin/env python3
"""The Library's knowledge-graph filter box (`nodeMatchesFilter`,
views/graph.jsx) missed accented notes the same way vault search used
to, twice, before both were fixed this session.

serve.py's `_vault_search_hit` and `views/vault.jsx`'s `bridgeSearch`
both accent-fold (NFD-decompose, drop combining marks) before matching
— specifically so 'unicas' finds 'únicas' — because the vault holds
research in more than one language. The graph is built from that same
vault content (kg_builder.py extracts titles from notes), but its own
filter box's bare-term fallback matched with plain `.toLowerCase()`:

    const hay = [n.title, n.id, n.path, n.type, ...(n.tags || [])].join(' ').toLowerCase();
    ...
    else ok = hay.includes(low);

Concrete repro: a note titled "Ideas únicas sobre la investigación
solar" appears as a graph node. Typing "unicas" into the graph's filter
box returned no match, while the identical query against /vault/search
or the encrypted bridge vault correctly finds it — the same node,
findable on two search surfaces and not on a third.

Found by a background hunt agent that, having already seen this exact
gap fixed twice (serve.py's own vault search, then views/vault.jsx's
bridgeSearch), went looking for any other search surface built on the
same vault content that never got the same treatment.

Fix: added `_foldAccents` to views/graph.jsx (module-local — vault.jsx
already imports FROM graph.jsx, so importing the other way would be
circular), a plain NFD-fold-and-lowercase (no index map needed here,
since this filter only needs a match/no-match verdict, never a snippet
back into the original text). `nodeMatchesFilter`'s bare-term fallback
now compares a folded `hay` against a folded query term. The
`type:`/`path:`/`tag:`/`file:` structured operators are deliberately
left alone — they compare against their own unfolded values, and
folding just the query side there would silently stop an accented
verbatim match instead of adding a capability.

Run: python3 scripts/test_graph_filter_folds_accents_like_vault_search.py
(skips the live-execution checks if `node` isn't on PATH — the
source-shape checks still run everywhere)
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH_JSX = ROOT / 'views' / 'graph.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("The graph filter box's bare-term search folds accents like vault search does")

    src = GRAPH_JSX.read_text(encoding='utf-8')

    fold_m = re.search(
        r"const _foldAccents = \(s\) => String\(s \|\| ''\)\n"
        r"\s*\.normalize\('NFD'\)\.replace\(/\[([^\]]+)\]/g, ''\)\.toLowerCase\(\);",
        src)
    check('found the _foldAccents helper', fold_m is not None)
    check('_foldAccents drops Unicode combining marks (U+0300-U+036F), '
          'matching serve.py\'s category-Mn strip and vault.jsx\'s own copy',
          fold_m and fold_m.group(1) == '\\u0300-\\u036f',
          fold_m and fold_m.group(1))

    filter_m = re.search(r"function nodeMatchesFilter\(n, filter\) \{(.*?)\n\}", src, re.S)
    check('found nodeMatchesFilter', filter_m is not None)
    body = filter_m.group(1) if filter_m else ''

    check('nodeMatchesFilter computes a folded twin of `hay`',
          bool(re.search(r"const foldedHay = _foldAccents\(hay\);", body)))
    check('the bare-term fallback now compares the folded hay against a '
          'folded query term — the actual regression, previously '
          '`hay.includes(low)` with no folding at all',
          'ok = foldedHay.includes(_foldAccents(low));' in body)
    check('the plain (unfolded) hay/low comparison is gone from the '
          'fallback branch',
          not re.search(r'else ok = hay\.includes\(low\);', body))

    check('the type:/path:/tag:/file: structured operators are left '
          'untouched (still compare against their own unfolded values) '
          '— this fix is scoped to the bare-term fallback only, not a '
          'rewrite of the query language',
          "ok = String(n.type || 'note').toLowerCase() === low.slice(5);" in body
          and "ok = String(n.id || '').toLowerCase().includes(low.slice(5)" in body)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted '
          '_foldAccents helper below)', has_node,
          'skipping the live-execution check')

    if has_node and fold_m:
        js = f"""
        {fold_m.group(0)}
        const hay = ['Ideas \\u00fanicas sobre la investigaci\\u00f3n solar', 'notes/id', 'note', 'note'].join(' ').toLowerCase();
        const foldedHay = _foldAccents(hay);
        const unaccentedQuery = _foldAccents('unicas'.toLowerCase());
        const accentedQuery = _foldAccents('\\u00fanicas'.toLowerCase());
        console.log(JSON.stringify({{
          unaccentedMatches: foldedHay.includes(unaccentedQuery),
          accentedMatches: foldedHay.includes(accentedQuery),
        }}));
        """
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the extracted _foldAccents helper ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-500:])
        if r.returncode == 0:
            import json
            out = json.loads(r.stdout.strip().splitlines()[-1])
            check('an unaccented query ("unicas") now matches a node '
                  'titled with the accented spelling — this is exactly '
                  'what was missing before the fix',
                  out.get('unaccentedMatches') is True, out)
            check('the accented query still matches too (folding must not '
                  'break the case that already worked)',
                  out.get('accentedMatches') is True, out)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
