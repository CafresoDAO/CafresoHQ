#!/usr/bin/env python3
""""What links here" was answerable only by squinting at the graph.

A research library answers that question constantly — which notes cite
this brief, which notes embed this deck — and the note view had no
answer at all: the knowledge existed, drawn as pixels in the graph
pane, reachable by no click.

Now every open file carries a "⇐ linked from" row of clickable chips,
built by _backlinkSources from the same graph the room already draws
(freshest snapshot first, one vaultGraph fetch as fallback). Note
sources only — office nodes aren't wikilinks; self-links and duplicate
edges are noise. Artifacts get the row too: their inbound embeds are
exactly as load-bearing. Verified live: the brief showed its citing
note, the chip opened it, and the embedded chart showed the same
citer from its binary panel.

Run: python3 scripts/test_a_note_knows_who_links_here.py
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
%s

const G = { edges: [
  { source: 'a.md', target: 'brief.md', type: 'links_to' },
  { source: 'a.md', target: 'brief.md', type: 'mentions' },   // dup source
  { source: 'Research/b.md', target: 'brief.md', type: 'links_to' },
  { source: 'brief.md', target: 'brief.md', type: 'links_to' }, // self
  { source: 'agent:llama', target: 'brief.md', type: 'wrote' }, // office
  { source: 'c.md', target: 'other.md', type: 'links_to' },     // elsewhere
  { source: 'n.md', target: 'Research/deck.pptx', type: 'embeds' },
] };
console.log(JSON.stringify({
  brief: _backlinkSources(G, 'brief.md'),
  deck: _backlinkSources(G, 'Research/deck.pptx'),
  none: _backlinkSources(G, 'lonely.md'),
  noGraph: _backlinkSources(null, 'brief.md'),
}));
'''


def main():
    print('a note knows who links here')
    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')
    fn = brace_lift(vault, 'const _backlinkSources = (g, path) => {')
    p = subprocess.run(['node', '-e', HARNESS % fn], capture_output=True,
                       text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    out = json.loads(p.stdout.strip().split('\n')[-1])

    check('inbound note sources arrive once each, in graph order',
          out['brief'] == ['a.md', 'Research/b.md'], out['brief'])
    check('an office node never makes a chip',
          'agent:llama' not in out['brief'])
    check('a self-link is noise, not a chip', 'brief.md' not in out['brief'])
    check('an artifact lists the notes that embed it',
          out['deck'] == ['n.md'], out['deck'])
    check('no inbound links means no row, not an error',
          out['none'] == [] and out['noGraph'] == [])

    # ── wiring: the row exists in both layouts and the chips are doors ──
    check('both layouts render the backlinks row',
          vault.count('{backlinksRow}') == 2)
    check('the row hides itself when there is nothing to say',
          'backlinks.length ? (' in vault)
    check('a chip is a door to its source note',
          'onClick={() => openByPath(p)}' in vault)
    check('the effect prefers the live snapshot and falls back to one fetch',
          '_lastGraph' in brace_lift(vault, 'React.useEffect(() => {\n    let dead = false;\n    const path = openNote && openNote.path;')
          and 'CafresoHQClient.vaultGraph()' in vault)

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
