#!/usr/bin/env python3
"""A filed deck was findable only by scrolling the tree.

Both search arms skipped any file outside _VAULT_TEXT_EXT outright, so
q3-deck.pptx matched nothing — not even "q3-deck". The Library's
charter names artifacts as residents; a resident search can't surface
is filed in a drawer with no label.

Now a non-text file is scored by NAME through the same shared
_vault_search_hit (text='', so the title arm decides — score 3, empty
snippet) and its bytes are never read: the fs arm skips read_text, the
oci arm skips get_object. Content search of text files is unchanged.
Verified live: "q3" and "deck" both surface the deck at score 3,
clicking the hit opens the Presentation panel, and a content query
still ranks the brief with its snippet.

Run: python3 scripts/test_search_finds_what_it_cannot_read.py
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
    print('search finds what it cannot read')
    serve = (ROOT / 'serve.py').read_text(encoding='utf-8')
    ns = {'pathlib': pathlib, 'unicodedata': unicodedata}
    exec(lift(serve, '_fold_accents'), ns)
    exec(lift(serve, '_vault_search_hit'), ns)
    hit = ns['_vault_search_hit']

    r = hit('Research/q3-deck.pptx', '', 'q3', 'q3')
    check('a name-only candidate scores on its title',
          bool(r) and r['score'] == 3 and r['snippet'] == '', r)
    check('...and a name miss is still a miss',
          hit('Research/q3-deck.pptx', '', 'vendor', 'vendor') is None)
    check('the empty text can never produce a phantom count',
          bool(r) and r['title'] == 'q3-deck')

    # ── both arms route non-text files to name-only scoring ─────────────
    fs_arm = serve[serve.index("if path == '/vault/search'"):
                   serve.index('# ---------- Graph (nodes + wikilink edges)')]
    check("the fs arm scores a non-text file by name instead of skipping",
          "_vault_search_hit(rel, '', ql, query)" in fs_arm
          and 'read_text' in fs_arm,
          '— the artifact branch must come after the hidden-part skip')
    check('...and never reads its bytes',
          fs_arm.index("_vault_search_hit(rel, '', ql, query)")
          < fs_arm.index('read_text'))
    oci_arm = lift(serve, '_oci_vault_search')
    check('the oci arm does the same without a get_object',
          "_vault_search_hit(rel, '', ql, query)" in oci_arm
          and oci_arm.index("_vault_search_hit(rel, '', ql, query)")
          < oci_arm.index('get_object('))
    check('dotted parts are still skipped before any scoring',
          fs_arm.index("part.startswith('.')")
          < fs_arm.index("_vault_search_hit(rel, '', ql, query)"))

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
