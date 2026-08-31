#!/usr/bin/env python3
"""Obsidian's own embed syntax rendered as a stray '!' plus a chip.

The vault ships an Obsidian backend, and Obsidian writes every image
as ![[file]] — but the renderer's [[ arm ate the brackets and
stranded the '!', the graph filed the relationship as a generic link,
and nothing ever showed the picture.

Now the renderer has a ![[ ]] arm that runs FIRST: a target the
caller can resolve to an image renders through /vault/file; anything
else becomes the same door chip a wikilink gets — never a stray '!'.
Resolution is opts.resolveEmbed, backed by _wikiResolvePath — the ONE
matching rule the click-time opener uses, so what a click opens and
what an embed shows can never disagree. kg_builder types a '!'-
prefixed wikilink as an `embeds` edge, same as ![](src). Verified
live: ![[obsidian shot.png]] rendered the image by bare basename,
![[no-such-deck|the deck]] showed its alias chip, no '!' anywhere.

Run: python3 scripts/test_an_obsidian_embed_is_an_image_not_a_stray_bang.py
"""
import json
import pathlib
import subprocess
import sys
import tempfile

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


HARNESS = r'''
%s
%s

const FILES = [{ path: 'Research/shot.png' }, { path: 'Research/deck.pptx' },
               { path: 'Research/brief.md' }];
const resolveEmbed = (t) => _wikiResolvePath(FILES, t);
const DOC = 'a ![[shot.png]] b ![[shot.png|My chart]] c ![[deck.pptx]] '
          + 'd ![[missing]] e [[brief]]';
const out = {};
out.lib = renderMarkdown(DOC, { wikilinks: true, resolveEmbed });
out.plain = renderMarkdown('x ![[shot.png]] y', {});
out.resolve = {
  base: _wikiResolvePath(FILES, 'shot.png'),
  stem: _wikiResolvePath(FILES, 'brief'),
  path: _wikiResolvePath(FILES, 'Research/brief'),
  caseless: _wikiResolvePath(FILES, 'SHOT.PNG'),
  miss: _wikiResolvePath(FILES, 'nope'),
};
console.log(JSON.stringify(out));
'''


def main():
    print("an obsidian embed is an image, not a stray '!'")
    ide = (ROOT / 'views' / 'ide.jsx').read_text(encoding='utf-8')
    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')
    parts = (brace_lift(ide, 'function renderMarkdown(text, opts)'),
             brace_lift(vault, 'const _wikiResolvePath = (files, target) => {'))
    p = subprocess.run(['node', '-e', HARNESS % parts],
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    out = json.loads(p.stdout.strip().split('\n')[-1])

    lib = out['lib']
    check('a resolvable image embed renders the image by bare basename',
          'src="/vault/file?path=Research%2Fshot.png"' in lib, lib)
    check('the |alias becomes the alt text', 'alt="My chart"' in lib)
    check('a resolvable NON-image embed is a door chip, not a broken img',
          'data-wikilink="deck.pptx"' in lib and 'deck.pptx</span>' in lib
          and 'src="/vault/file?path=Research%2Fdeck.pptx"' not in lib, lib)
    check('an unresolvable embed is a door chip too (where notes get born)',
          'data-wikilink="missing"' in lib)
    check("no stray '!' survives any spelling",
          '!<' not in lib and '! <' not in lib, lib)
    check('a plain [[wikilink]] beside them is untouched',
          'data-wikilink="brief"' in lib)
    check('outside the Library the embed is an inert chip, still no bang',
          '<span class="md-tag">shot.png</span>' in out['plain']
          and '!<' not in out['plain'], out['plain'])

    r = out['resolve']
    check('one matching rule: base / stem / path / caseless resolve, junk misses',
          r == {'base': 'Research/shot.png', 'stem': 'Research/brief.md',
                'path': 'Research/brief.md', 'caseless': 'Research/shot.png',
                'miss': None}, r)

    # ── the graph types ![[x]] as an embed, not a mention ───────────────
    import kg_builder
    d = pathlib.Path(tempfile.mkdtemp())
    (d / 'Research').mkdir()
    (d / 'Research' / 'n.md').write_text('see ![[shot.png]] and [[other]]\n')
    (d / 'Research' / 'shot.png').write_bytes(b'\x89PNG')
    (d / 'other.md').write_text('x\n')
    nowhere = pathlib.Path(tempfile.mkdtemp())
    kg_builder.init(vault_root=lambda: str(d), state_dir=lambda: nowhere,
                    memory_dir=lambda: nowhere, obsidian_request=None)
    g = kg_builder._build_graph_fs()
    kinds = {(e['source'], e['target']): e['type'] for e in g['edges']}
    check('![[x]] is an embeds edge in the graph',
          kinds.get(('Research/n.md', 'Research/shot.png')) == 'embeds', kinds)
    check('a bare [[x]] beside it still classifies as a link',
          kinds.get(('Research/n.md', 'other.md'), '').startswith('links'),
          kinds)

    check('both Library previews hand the renderer the resolver',
          vault.count('resolveEmbed: (tg) => _wikiResolvePath(files, tg)') == 2)
    check('the click-time opener uses the SAME rule',
          '_wikiResolvePath(files, target)' in vault)

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
