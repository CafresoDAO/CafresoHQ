#!/usr/bin/env python3
"""Renaming an embedded artifact broke every note that shows it.

Renames follow inbound [[wikilinks]] — but ![](embeds) were never
rewritten, and the ✎ rename button is offered on binary files too. So
renaming chart.png left every `![c](Research/chart.png)` pointing at a
dead path: broken image in the preview, embed edge gone from the
graph, no message anywhere.

Now _vault_rewrite_wikilinks rewrites embeds too, matched by EXACT
vault-relative src — the same way the preview resolves them through
/vault/file — keeping the alt text. Scheme'd/rooted srcs stand as
written even when their basename matches (a web URL is not a filing).
The stem-form [[chart]] is deliberately NOT rewritten for an artifact:
a note named chart.md wins that stem, so rewriting it for the artifact
would corrupt the other resolution. Verified live: rename reported
linksRewritten 1, the note's embed now names the new path, the
external URL beside it untouched, /vault/file serves the moved file.

Run: python3 scripts/test_a_renamed_artifact_keeps_its_pictures.py
"""
import ast
import pathlib
import re
import sys
import tempfile
import urllib.parse

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
    print('a renamed artifact keeps its pictures')
    serve = (ROOT / 'serve.py').read_text(encoding='utf-8')

    d = pathlib.Path(tempfile.mkdtemp())
    (d / 'Research').mkdir()
    (d / 'Research' / 'a.md').write_text(
        '![the chart](Research/chart.png)\n'
        '![ext](https://x.io/chart.png) ![rooted](/vault/file?p=chart.png)\n'
        '[[chart.png]] and plain [link](Research/chart.png)\n')
    (d / 'other.md').write_text('no references here\n')

    ns = {'pathlib': pathlib, 're': re, 'urllib': urllib,
          '_vault_root': str(d)}
    exec(lift(serve, '_vault_rewrite_wikilinks'), ns)
    links, files = ns['_vault_rewrite_wikilinks'](
        'Research/chart.png', 'Research/q3-chart.png')

    text = (d / 'Research' / 'a.md').read_text()
    check('the embed follows the rename, alt intact',
          '![the chart](Research/q3-chart.png)' in text, text)
    check('a web URL sharing the basename stands as written',
          '![ext](https://x.io/chart.png)' in text)
    check('a rooted src stands as written',
          '![rooted](/vault/file?p=chart.png)' in text)
    check('the basename wikilink follows too',
          '[[q3-chart.png]]' in text, text)
    check('a plain [link]() is not an embed and stands as written',
          '[link](Research/chart.png)' in text, text)
    check('the counts include both kinds',
          links == 2 and files == 1, (links, files))
    check('an untouched note is never rewritten',
          (d / 'other.md').read_text() == 'no references here\n')

    # The .md rename path that always worked must still work.
    (d / 'b.md').write_text('see [[a]] and ![inline](Research/a.md)\n')
    links2, _ = ns['_vault_rewrite_wikilinks']('Research/a.md', 'Research/z.md')
    text2 = (d / 'b.md').read_text()
    check('note renames still rewrite wikilinks and now embeds',
          '[[z]]' in text2 and '![inline](Research/z.md)' in text2
          and links2 == 2, text2)

    check('the rename route still calls the rewriter',
          '_vault_rewrite_wikilinks(src, dst)' in serve)

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
