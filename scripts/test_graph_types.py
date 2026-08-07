#!/usr/bin/env python3
"""`_graph_node_type` decides what the knowledge graph thinks a file IS, and
the vault's analysis panel counts those types back to the boss in office
words — "21 conversations · 9 notes · 7 tasks · 4 coworkers".

So a mis-typed file is not a private detail: it is a wrong number on the one
screen that claims to summarise the business.

The rule that brought this file into existence: `'agents/' in path` typed the
WHOLE subtree as a coworker. `Agents/<name>/` is a coworker's private notes
folder, so every note they ever wrote counted as another colleague — an
office with two hired coworkers reported four, the extras being
`Agents/Llama/notes/olives.md` and the boss. It scales with use, which is
what makes it worth a test rather than a fix.

Run: python3 scripts/test_graph_types.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import kg_builder  # noqa: E402

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + ('' if cond else f'  — {detail}'))
    if not cond:
        FAILS.append(name)


CASES = [
    # (path, tags, expected, why)
    ('Agents/Llama/notes/olives.md', [], 'memory',
     "a coworker's own note is theirs, not another coworker"),
    ('Agents/Mika/preferences.md', [], 'memory',
     'still true one level down'),
    ('agents/vera.md', [], 'agent',
     'a file directly in agents/ IS a note about someone'),
    ('Agents/vera.md', [], 'agent',
     '…case-insensitively'),
    ('notes/agent-handbook.md', [], 'agent',
     'the agent- prefix still names a profile'),
    ('anything.md', ['agent'], 'agent',
     'an explicit tag always wins'),
    ('Deliveries/report.md', [], 'note', 'a delivery is a note'),
    ('Research/topic.md', [], 'research', 'research is research'),
    ('Tasks/ship-it.md', [], 'task', 'tasks unaffected'),
    ('Decisions/pricing.md', [], 'decision', 'decisions unaffected'),
]


def main():
    print('graph node types — what the vault says a file is')
    for path, tags, want, why in CASES:
        got = kg_builder._graph_node_type(path, tags)
        check(f'{path} → {want} ({why})', got == want, f'got {got!r}')

    # The bug in one assertion: a coworker with N private notes must still be
    # ONE coworker.
    paths = [f'Agents/Llama/notes/n{i}.md' for i in range(10)]
    agentish = [p for p in paths if kg_builder._graph_node_type(p, []) == 'agent']
    check('ten private notes do not become ten colleagues',
          not agentish, f'{len(agentish)} of 10 typed as coworkers')

    print()
    if FAILS:
        print(f'graph node types: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('graph node types: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
