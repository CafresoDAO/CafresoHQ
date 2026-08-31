#!/usr/bin/env python3
"""An embeds edge drew exactly like a plain wikilink.

kg_builder types Obsidian ![[embeds]] as their own edge kind at 0.95
confidence — and the graph's palette had no entry for them, so they
fell through to the default bucket: a note SHOWING a chart and a note
merely linking one were the same stroke. The semantic type existed
end-to-end and was invisible at the only place the boss looks.

Now EDGE_TYPE_STYLE carries `embeds`: a warm attachment tint, solid,
heavier than a plain link. Both renderers read this one map — the
legacy canvas buckets by it and the sigma engine colors through
edgeColorForType — so one entry lights both. Verified live: the
embed-demo seed produced an embeds edge in the engine snapshot and
the bundle carries the tint.

Run: python3 scripts/test_an_embed_edge_wears_its_own_color.py
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
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
const EDGE_TYPE_STYLE = %s;
%s
console.log(JSON.stringify({
  embeds: EDGE_TYPE_STYLE.embeds || null,
  links: EDGE_TYPE_STYLE.links_to || null,
  embedColor: edgeColorForType('embeds', false),
  unknownColor: edgeColorForType('never_a_type', false),
  linkColor: edgeColorForType('links_to', false),
}));
'''


def main():
    print('an embed edge wears its own color')
    graph = (ROOT / 'views' / 'graph.jsx').read_text(encoding='utf-8')
    kg = (ROOT / 'kg_builder.py').read_text(encoding='utf-8')

    style = brace_lift(graph, 'const EDGE_TYPE_STYLE = {')[len('const EDGE_TYPE_STYLE = '):]
    fn = brace_lift(graph, 'function edgeColorForType(type, isDark) {')
    p = subprocess.run(['node', '-e', HARNESS % (style, fn)],
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    out = json.loads(p.stdout.strip().split('\n')[-1])

    e = out['embeds']
    check('the palette knows the embeds type', bool(e), out)
    check('…with its own solid tint, not the default fallthrough',
          e and e.get('color') and e.get('dash') is None, e)
    check('…heavier than a plain link',
          e and out['links'] and e['widthMul'] > out['links']['widthMul'], e)
    check('the engine palette answers with that tint, not the theme default',
          out['embedColor'] == (e or {}).get('color')
          and out['embedColor'] != out['unknownColor'], out)
    check('plain links still fall through to the theme default',
          out['linkColor'] == out['unknownColor'], out)
    check('the builder still types embeds at 0.95 — the edge this styles',
          "'embeds', 0.95" in kg)

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
