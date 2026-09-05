#!/usr/bin/env python3
"""Every screenshot's default name has spaces; embeds choked on them.

"Screenshot 2026-08-31 at 08.30.png" is the single most common
artifact name there is, and all three embed parsers stopped at
whitespace: the preview rendered a stray '!' plus a link, a
%20-encoded src double-encoded into a dead /vault/file path (%2520),
the graph missed the edge, and a rename left the note behind.

Now all three accept three src spellings — <angle-bracketed>,
%-encoded (decoded before re-encoding), plain — and agree: the
renderer (which sees entity-escaped text, so &lt;…&gt;), the graph
builder, and the rename rewriter, which writes a whitespace-bearing
destination back in the angle form every parser accepts. Verified
live: the uploaded screenshot renders in the note at natural size,
the embeds edge exists, and a rename to "hero shot.png" followed.

Run: python3 scripts/test_a_screenshots_name_is_not_a_parse_error.py
"""
import ast
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import threading
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, opener):
    i = src.index(opener)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise SystemExit('unbalanced braces lifting ' + opener)


SHOT = 'Research/Screenshot 2026-08-31 at 08.30.png'
DOC = ('![a](<' + SHOT + '>)\n\n'
       '![b](Research/Screenshot%202026-08-31%20at%2008.30.png)\n\n'
       '![ext](https://x.io/a%20b.png)\n')
WANT = '/vault/file?path=' + urllib.parse.quote(SHOT, safe='')


def main():
    print("a screenshot's name is not a parse error")

    # ── renderer: both spellings, one resolved path ─────────────────────
    ide = (ROOT / 'views' / 'ide.jsx').read_text(encoding='utf-8')
    fn = brace_lift(ide, 'function renderMarkdown(text, opts)')
    js = fn + '\nconsole.log(JSON.stringify(renderMarkdown(' + json.dumps(DOC) + ', {wikilinks:true})));'
    p = subprocess.run(['node', '-e', js], capture_output=True, text=True,
                       timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    html = json.loads(p.stdout.strip().split('\n')[-1])
    check('the angle form renders as an image',
          html.count('src="' + WANT.replace('"', '&quot;') + '"') == 2, html)
    check("no stray '!' survives either spelling", '!<a' not in html)
    check('a %-encoded src is decoded before re-encoding — never %2520',
          '%2520' not in html)
    check('an external URL keeps its own written form',
          'src="https://x.io/a%20b.png"' in html)

    # ── graph builder: the edge exists, once ────────────────────────────
    import kg_builder
    d = pathlib.Path(tempfile.mkdtemp())
    (d / 'Research').mkdir()
    (d / 'Research' / 'n.md').write_text(DOC)
    # each spelling in its OWN note, so each must resolve unaided — a
    # shared note let the angle form mask a broken %-decode entirely
    (d / 'Research' / 'enc-only.md').write_text(
        '![b](Research/Screenshot%202026-08-31%20at%2008.30.png)\n')
    (d / SHOT).write_bytes(b'\x89PNG')
    nowhere = pathlib.Path(tempfile.mkdtemp())
    kg_builder.init(vault_root=lambda: str(d), state_dir=lambda: nowhere,
                    memory_dir=lambda: nowhere, obsidian_request=None)
    g = kg_builder._build_graph_fs()
    embeds = sorted((e['source'], e['target']) for e in g['edges']
                    if e['type'] == 'embeds')
    check('the graph resolves each spelling on its own',
          embeds == [('Research/enc-only.md', SHOT),
                     ('Research/n.md', SHOT)], embeds)

    # ── rename rewriter: both spellings follow, angle form written ──────
    serve = (ROOT / 'serve.py').read_text(encoding='utf-8')
    tree = ast.parse(serve)
    # #385 routed the rewriter's write through _vault_write_local, serialised
    # by the module-level _vault_write_lock — lift both, and give the
    # namespace a real lock, or the rewriter can't find either name.
    src_fn = '\n\n'.join(
        ast.get_source_segment(serve, n) for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name in ('_vault_write_local', '_vault_rewrite_wikilinks'))
    ns = {'pathlib': pathlib, 're': re, 'urllib': urllib, 'os': os,
          'threading': threading, '_vault_write_lock': threading.Lock(),
          '_vault_root': str(d)}
    exec(src_fn, ns)
    links, files = ns['_vault_rewrite_wikilinks'](SHOT,
                                                  'Research/hero shot.png')
    text = (d / 'Research' / 'n.md').read_text()
    check('a rename follows every spelling in every note',
          links == 3 and files == 2 and text.count('](<Research/hero shot.png>)') == 2,
          text)
    check('...writing the one spelling every parser accepts',
          '](Research/hero shot.png)' not in text)
    check('...and the web URL still stands', 'https://x.io/a%20b.png' in text)
    links2, _ = ns['_vault_rewrite_wikilinks']('Research/hero shot.png',
                                               'Research/plain.png')
    check('a spaceless destination is written plain',
          '](Research/plain.png)' in (d / 'Research' / 'n.md').read_text()
          and links2 == 3)

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
