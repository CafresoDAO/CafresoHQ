#!/usr/bin/env python3
"""The graph's right-click menu offered "Open note" on nodes with no note.

The links graph draws office nodes too — task:, agent:, receipt: — and
the context menu put "Open note" on every one of them. Clicking it did
nothing: the Library-side guard (openGraphNode) refuses ids its file
list doesn't hold, which protects the view but leaves the menu lying.
A menu item that silently no-ops teaches the boss the menu can't be
trusted.

Now the open item appears only when the node record carries a path —
the /vault/graph contract gives every real Library file its rel path
and every hq-state node '' — and a filed deck reads "Open file", not
"Open note". Office nodes keep Focus and Hide, which do work.

Run: python3 scripts/test_the_map_menu_offers_doors_that_open.py
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


def bracket_lift(src, opener):
    """Lift a balanced [...] expression starting at `opener`."""
    i = src.index(opener)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '[':
            depth += 1
        elif src[j] == ']':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise SystemExit('unbalanced brackets lifting ' + opener)


HARNESS = r'''
const source = %s;
const ctxMenu = { id: %s };
const rawRef = { current: { byId: %s } };
const onOpenNote = null, setCtxMenu = () => {}, engineRef = { current: null };
const items = %s.map(([label]) => label);
console.log(JSON.stringify(items));
'''


def run(source, node_id, by_id):
    graph = (ROOT / 'views' / 'graph.jsx').read_text(encoding='utf-8')
    arr = bracket_lift(graph, "[...(source === 'links'")
    src = HARNESS % (json.dumps(source), json.dumps(node_id),
                     json.dumps(by_id), arr)
    p = subprocess.run(['node', '-e', src], capture_output=True, text=True,
                       timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(p.stdout.strip().split('\n')[-1])


def main():
    print('the map menu offers doors that open')
    by_id = {
        'Research/brief.md': {'id': 'Research/brief.md', 'path': 'Research/brief.md'},
        'Deliveries/deck.pptx': {'id': 'Deliveries/deck.pptx', 'path': 'Deliveries/deck.pptx'},
        'task:tk_1': {'id': 'task:tk_1', 'path': ''},
    }

    check('a note node offers Open note',
          run('links', 'Research/brief.md', by_id)
          == ['Open note', 'Focus', 'Hide node'])
    check('a filed deck offers Open file — it is not a note',
          run('links', 'Deliveries/deck.pptx', by_id)
          == ['Open file', 'Focus', 'Hide node'])
    check('an office node (task:) gets no door it cannot open',
          run('links', 'task:tk_1', by_id) == ['Focus', 'Hide node'])
    check('a node the data no longer holds crashes nothing',
          run('links', 'gone:xyz', by_id) == ['Focus', 'Hide node'])
    check('the concepts graph never offers Open — terms are not paths',
          run('concepts', 'Research/brief.md', by_id) == ['Focus', 'Hide node'])

    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')
    check('the Library-side guard still stands behind the menu',
          'if (files.some(f => f.path === p)) open(p);' in vault)

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
