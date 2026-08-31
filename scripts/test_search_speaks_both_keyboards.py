#!/usr/bin/env python3
"""Search split the vault by keyboard layout.

The Library holds research in more than one language, and matching was
a bare substring on .lower(): 'unicas' silently missed 'únicas',
'investigacion' missed 'investigación'. Whoever typed without the
accent — or on the other keyboard — was told the note didn't exist.

Now _vault_search_hit accent-folds both sides (NFD, drop the combining
marks) through _fold_accents, which also returns an index map so the
snippet still comes from the ORIGINAL text, accents intact — the
reader is never shown a folded copy of their own note. Shared scorer,
so the fs and oci arms both fold. Verified live both directions:
'unicas' finds 'únicas', 'únicas' still finds itself, and the snippet
reads 'Ideas únicas sobre la investigación…'.

Run: python3 scripts/test_search_speaks_both_keyboards.py
"""
import ast
import pathlib
import sys
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift(src, name):
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise SystemExit(f'{name} not found in serve.py')


def main():
    print('search speaks both keyboards')
    serve = (ROOT / 'serve.py').read_text(encoding='utf-8')
    ns = {'pathlib': pathlib, 'unicodedata': unicodedata}
    exec(lift(serve, '_fold_accents'), ns)
    exec(lift(serve, '_vault_search_hit'), ns)
    hit = ns['_vault_search_hit']

    text = 'Ideas únicas sobre la investigación solar.'
    r = hit('Research/notas.md', text, 'unicas', 'unicas')
    check("an unaccented query finds the accented word", bool(r), r)
    check('...and the snippet keeps the original accents',
          r and 'únicas' in r['snippet'], r)
    r2 = hit('Research/notas.md', text, 'únicas', 'únicas')
    check('the accented query still finds itself',
          bool(r2) and r2['score'] == r['score'], (r, r2))
    r3 = hit('Research/investigación.md', 'body only', 'investigacion',
             'investigacion')
    check('the TITLE folds too (score 3 for a stem match)',
          bool(r3) and r3['score'] == 3, r3)
    check('a miss is still a miss',
          hit('Research/notas.md', text, 'zanahoria', 'zanahoria') is None)
    check('an all-marks query cannot match everything',
          hit('Research/notas.md', text, '́', '́') is None,
          '— folding a bare combining mark leaves an empty needle')

    folded, idx_map = ns['_fold_accents']('AÑO único')
    check('folding lowers and strips marks in one pass',
          folded == 'ano unico', folded)
    check('...and the map points every folded char home',
          [idx_map[folded.index('u')], idx_map[-1]] == [4, 8], idx_map)

    check('the scorer is still the one every backend arm shares',
          serve.count('_vault_search_hit(') >= 3,
          '— fs and oci must fold identically or the split comes back')

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
