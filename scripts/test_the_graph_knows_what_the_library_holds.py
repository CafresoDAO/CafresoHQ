#!/usr/bin/env python3
"""The graph only knew markdown; the Library holds more.

The charter names the residents outright — artifacts, ppts, documents,
markdown files and research — and _build_graph_fs walked `*.md`. A
filed deck or chart was in the tree, in search, behind a click, and
absent from the map: [[deck.pptx]] resolved to nothing, ![](chart.png)
made no edge, and the cache signature statted only .md so even a
future fix would have served stale graphs.

Now non-markdown files ride along as 'artifact' nodes (stat only,
never read), wikilinks resolve to them by exact path or stem — a NOTE
sharing a stem wins it — and a note's ![](embed) becomes an 'embeds'
edge (external/data/rooted srcs stay out, mirroring the preview's
routing). The signature stats every file, so adding or deleting an
artifact invalidates the cache. Verified live: chart.png drawn with 2
inlinks, "1 artifact" in the analytics mix, click opens the file
panel, delete drops it from the next graph.

Run: python3 scripts/test_the_graph_knows_what_the_library_holds.py
"""
import pathlib
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


def build(setup):
    import kg_builder
    d = pathlib.Path(tempfile.mkdtemp())
    setup(d)
    nowhere = pathlib.Path(tempfile.mkdtemp())
    kg_builder.init(vault_root=lambda: str(d), state_dir=lambda: nowhere,
                    memory_dir=lambda: nowhere, obsidian_request=None)
    return d, kg_builder


def main():
    print('the graph knows what the Library holds')

    def seed(d):
        (d / 'Research').mkdir()
        (d / 'Research' / 'brief.md').write_text(
            '![c](Research/chart.png) and [[deck.pptx]] and [[chart]]\n'
            # the external src's BASENAME matches a filed artifact that is
            # referenced nowhere else — without the scheme gate it would
            # stem-resolve into a false edge to logo.png
            '![ext](https://x.io/logo.png) ![rooted](/vault/file?path=x)\n'
            '![again](Research/chart.png)\n')
        (d / 'Research' / 'chart.png').write_bytes(b'\x89PNGfake')
        (d / 'logo.png').write_bytes(b'\x89PNGlogo')
        (d / 'deck.pptx').write_bytes(b'PKfake')
        (d / '.trash').mkdir()
        (d / '.trash' / 'gone.pdf').write_bytes(b'no')

    d, kg = build(seed)
    g = kg._build_graph_fs()
    nodes = {n['id']: n for n in g['nodes']}
    edges = {(e['source'], e['target'], e['type']) for e in g['edges']}
    B = 'Research/brief.md'

    check('a filed deck and chart are artifact nodes',
          nodes.get('deck.pptx', {}).get('type') == 'artifact'
          and nodes.get('Research/chart.png', {}).get('type') == 'artifact',
          sorted(nodes))
    check('a dotted folder stays off the map', 'gone.pdf' not in str(nodes))
    check('[[deck.pptx]] resolves by exact path',
          (B, 'deck.pptx', 'links_to') in edges)
    check('[[chart]] resolves by stem',
          (B, 'Research/chart.png', 'links_to') in edges)
    check('![](embed) is an embeds edge, deduped',
          (B, 'Research/chart.png', 'embeds') in edges
          and sum(1 for e in g['edges'] if e['type'] == 'embeds') == 1)
    check('external and rooted srcs make no edge',
          nodes['logo.png']['inlinks'] == 0
          and not any(e['target'] == 'logo.png' or 'vault/file' in str(e)
                      for e in g['edges']),
          '— a web URL sharing a filed basename must not fake a filing')
    check('inlinks count both kinds of arrival',
          nodes['Research/chart.png']['inlinks'] == 2
          and nodes['deck.pptx']['inlinks'] == 1)
    sig1 = kg._vault_graph_signature()
    (d / 'new-deck.pptx').write_bytes(b'PK2')
    check('adding an artifact changes the cache signature',
          kg._vault_graph_signature() != sig1,
          '— a stale signature serves a map missing the newest filing')

    def seed2(d):
        (d / 'chart.md').write_text('the note about the chart\n')
        (d / 'chart.png').write_bytes(b'\x89PNG')
        (d / 'ref.md').write_text('see [[chart]]\n')

    _d2, kg2 = build(seed2)
    g2 = kg2._build_graph_fs()
    e2 = {(e['source'], e['target'], e['type']) for e in g2['edges']}
    check('a note sharing a stem wins it over the artifact',
          ('ref.md', 'chart.md', 'links_to') in e2
          and ('ref.md', 'chart.png', 'links_to') not in e2, e2)

    graph_jsx = (ROOT / 'views' / 'graph.jsx').read_text(encoding='utf-8')
    check('the map has a color for what it now draws',
          'artifact:' in graph_jsx)

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
