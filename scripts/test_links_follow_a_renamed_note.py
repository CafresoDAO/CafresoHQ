#!/usr/bin/env python3
"""Renaming a linked note silently broke every link to it.

/vault/rename (fs backend — the shipping default) was a bare
os.replace: the file moved, and every [[wikilink]] pointing at it kept
the old name. Driven live before the fix: rename a note another note
links to, the graph edge vanishes and the linking note keeps a dead
target — with no message anywhere. The Library is the product's filing
cabinet; a rename that strands inbound links rots the graph one move
at a time.

Now the fs rename rewrites inbound links across the vault —
[[target]], [[target|alias]], [[target#heading]], by basename or full
path, .md or not — keeping each link's own style, and reports
{linksRewritten, filesTouched} so the UI can say what followed.
Verified live: 3 links rewrote on a basename rename, path-style links
followed a second rename, and a near-miss ([[rename-target-two]])
stayed untouched.

Run: python3 scripts/test_links_follow_a_renamed_note.py
"""
import ast
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift_function(src, name):
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise SystemExit(f'{name} not found in serve.py')


def main():
    print('links follow a renamed note')
    serve = (ROOT / 'serve.py').read_text(encoding='utf-8')

    # ── structure: the route calls the rewriter and reports the counts ──
    check('the fs rename calls the rewriter',
          '_vault_rewrite_wikilinks(src, dst)' in serve)
    check('...best-effort, after the move already succeeded',
          # the folder arm (test_a_folder_moves_as_one_drawer) now sits
          # between the move and the single-file rewrite — window widened
          re.search(r'os\.replace[\s\S]{0,2400}_vault_rewrite_wikilinks', serve))
    check('...and reports what it did',
          "'linksRewritten': rewritten" in serve and "'filesTouched': files_touched" in serve)
    check('the UI tells the boss links followed',
          'followed the rename' in (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8'))

    # ── behavior: lift the real function into a temp vault ──────────────
    fn_src = lift_function(serve, '_vault_rewrite_wikilinks')
    with tempfile.TemporaryDirectory() as td:
        vault = pathlib.Path(td)
        (vault / 'Research').mkdir()
        (vault / 'linker.md').write_text(
            'See [[old-note]] and [[old-note|alias]] and [[old-note#top]].\n'
            'Path: [[Research/old-note]]. Near miss: [[old-note-two]].\n',
            encoding='utf-8')
        (vault / 'Research' / 'other.md').write_text(
            'Also [[old-note.md]] here.\n', encoding='utf-8')
        ns = {'pathlib': pathlib, 're': re, '_vault_root': str(vault)}
        exec(fn_src, ns)
        links, files = ns['_vault_rewrite_wikilinks']('Research/old-note.md',
                                                      'Archive/new-note.md')
        check('every matching link across the vault is rewritten (5)',
              links == 5, links)
        check('both files were touched', files == 2, files)
        linker = (vault / 'linker.md').read_text(encoding='utf-8')
        check('basename links get the new basename',
              '[[new-note]]' in linker and '[[old-note]]' not in linker, linker)
        check('the alias survives', '[[new-note|alias]]' in linker, linker)
        check('the heading survives', '[[new-note#top]]' in linker, linker)
        check('path links get the new path',
              '[[Archive/new-note]]' in linker, linker)
        check('the near miss stays untouched',
              '[[old-note-two]]' in linker, linker)
        check('.md-style links are followed too',
              '[[new-note]]' in (vault / 'Research' / 'other.md').read_text(encoding='utf-8'))
        # idempotence: a second run finds nothing left to rewrite
        links2, files2 = ns['_vault_rewrite_wikilinks']('Research/old-note.md',
                                                        'Archive/new-note.md')
        check('a second pass rewrites nothing (no self-corruption)',
              (links2, files2) == (0, 0), (links2, files2))

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
