#!/usr/bin/env python3
"""/vault/graph is cached behind a cheap stat-only signature: rebuild only
when a vault file or an hq-state JSON changes, otherwise hand back the
cached graph instantly (see kg_builder._hq_state_sig_update).

hq-memory/agents.json — where the CafresoHQ frontend persists hired agents
(name, role, color; see app.jsx's useFileStored(k('agents'), 'memory',
'agents', ...)) — is written to `memory_dir` (hq-state/memory/), a
SUBDIRECTORY of `state_dir`. The signature builder only globbed
`state_dir().glob('*.json')`, which does not descend into memory/, so
agents.json was never part of the cache key.

Consequence: hire an agent, or rename/recolor an existing one, and the
graph the boss is looking at keeps showing the OLD agent node — same name,
same color — until some unrelated tasks/missions/receipts/messages file
happens to change and forces a rebuild. That's stale data served from a
cache that thinks nothing changed.

Run: python3 scripts/test_agent_rename_invalidates_graph_cache.py
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import kg_builder  # noqa: E402

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + ('' if cond else f'  — {detail}'))
    if not cond:
        FAILS.append(name)


def main():
    print('agent-registry edits must invalidate the vault graph cache')
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        vault = root / 'vault'
        state = root / 'hq-state'
        memory = state / 'memory'
        vault.mkdir()
        state.mkdir()
        memory.mkdir()

        # One boring note so the fs walk has something to do.
        (vault / 'note.md').write_text('# Note\n\nJust a note.\n', encoding='utf-8')

        (memory / 'agents.json').write_text(json.dumps([
            {'id': 'a_nykw53', 'name': 'Selvin', 'role': 'Code Gremlin', 'color': '#ff0000'},
        ]), encoding='utf-8')

        kg_builder.init(
            vault_root=lambda: str(vault),
            state_dir=lambda: state,
            memory_dir=lambda: memory,
            obsidian_request=lambda *a, **k: (500, {}, b''),
        )
        # Fresh module-level caches — a prior test run in the same process
        # (or a stale import) must not leak into this one.
        kg_builder._graph_cache['sig'] = None
        kg_builder._graph_cache['graph'] = None

        graph1 = kg_builder._build_graph_fs_cached()
        agent_nodes = [n for n in graph1['nodes'] if n['type'] == 'agent']
        check('agent node present after first build', len(agent_nodes) == 1,
              f'{len(agent_nodes)} agent nodes')
        check('agent title starts as Selvin', agent_nodes and agent_nodes[0]['title'].startswith('Selvin'),
              agent_nodes[0]['title'] if agent_nodes else '(none)')

        # Rename the agent — nothing under state_dir's own *.json files
        # changes, only memory/agents.json.
        (memory / 'agents.json').write_text(json.dumps([
            {'id': 'a_nykw53', 'name': 'Selvin-Renamed', 'role': 'Code Gremlin', 'color': '#ff0000'},
        ]), encoding='utf-8')

        graph2 = kg_builder._build_graph_fs_cached()
        agent_nodes2 = [n for n in graph2['nodes'] if n['type'] == 'agent']
        got_title = agent_nodes2[0]['title'] if agent_nodes2 else '(none)'
        check('graph reflects the rename after agents.json changes',
              got_title.startswith('Selvin-Renamed'),
              f'cache served stale title {got_title!r}')

    print()
    if FAILS:
        print(f'agent cache invalidation: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('agent cache invalidation: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
