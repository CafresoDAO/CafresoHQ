#!/usr/bin/env python3
"""A done task and the note it delivered sat on the map as strangers.

When a coworker's answer lands in the Library, the task record keeps
the exact vault path it filed (artifactPath) — and kg_builder ignored
the field, so the graph drew the task node and its deliverable note
with no edge between them. The single most meaningful line the map
could draw for a boss ("this work produced THIS document") was the one
it never drew. Missions' notesWritten already had it; tasks did not.

Now the task loop wires artifactPath → a `produces` edge — the same
type the mission edges wear, so the palette and both renderers already
know it by name. Messy slashes are normalized, a path gone stale after
a move is re-resolved by stem, and a path that resolves nowhere adds
nothing. Verified live: task:tk_fbevo → its filed research brief,
type produces, confidence 1.0.

Run: python3 scripts/test_a_task_points_at_what_it_delivered.py
"""
import json
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


def main():
    print('a task points at what it delivered')
    import kg_builder

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        vault = root / 'vault'
        (vault / 'Research').mkdir(parents=True)
        (vault / 'Research' / 'brief.md').write_text('# The brief\n')
        state = root / 'state'
        state.mkdir()
        (state / 'tasks.json').write_text(json.dumps([
            {'id': 'tk_exact', 'title': 'exact path', 'status': 'done',
             'artifactPath': 'Research/brief.md'},
            {'id': 'tk_messy', 'title': 'messy slashes', 'status': 'done',
             'artifactPath': '/Research\\brief.md'},
            {'id': 'tk_moved', 'title': 'note moved since', 'status': 'done',
             'artifactPath': 'Old/brief.md'},
            {'id': 'tk_gone', 'title': 'deliverable deleted', 'status': 'done',
             'artifactPath': 'gone/nothing.md'},
            {'id': 'tk_none', 'title': 'no deliverable yet', 'status': 'inbox'},
        ]))
        mem = root / 'memory'
        mem.mkdir()

        kg_builder.init(
            vault_root=lambda: str(vault), state_dir=lambda: state,
            memory_dir=lambda: mem,   # a Path — _load_hq_memory does dir / name
            obsidian_request=lambda *a, **k: (500, {}, b''),
        )
        g = kg_builder._build_graph_fs()

        prod = {e['source']: e for e in g['edges'] if e['type'] == 'produces'}
        note = 'Research/brief.md'

        e = prod.get('task:tk_exact')
        check('a filed deliverable becomes a produces edge',
              e and e['target'] == note, e)
        check('…at full confidence — the record names the file outright',
              e and e['confidence'] == 1.0, e)
        check('backslashes and a leading slash still find the note',
              prod.get('task:tk_messy', {}).get('target') == note,
              prod.get('task:tk_messy'))
        check('a path gone stale after a move re-resolves by stem',
              prod.get('task:tk_moved', {}).get('target') == note,
              prod.get('task:tk_moved'))
        check('a deliverable that resolves nowhere adds nothing',
              'task:tk_gone' not in prod, prod.get('task:tk_gone'))
        check('a task with no deliverable has no produces edge',
              'task:tk_none' not in prod, prod.get('task:tk_none'))
        check('all five tasks still stand as nodes',
              sum(1 for n in g['nodes'] if n['type'] == 'task') == 5)

    src = (ROOT / 'views' / 'graph.jsx').read_text(encoding='utf-8')
    check("the renderers' palette knows produces by name",
          'produces:' in src)

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
