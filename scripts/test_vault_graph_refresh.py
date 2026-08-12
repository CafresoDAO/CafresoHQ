#!/usr/bin/env python3
"""The Vault's graph panel didn't know a note was deleted or created — views/vault.jsx.

Found live during a northstar MVP audit pass: opened the Vault, deleted a
stale test delivery note, created a fresh one, then clicked the vault's own
↻ Refresh button. The file tree on the left updated correctly both times.
The "Graph analysis" panel on the right — same window, same refresh click —
kept showing "On the map: 8" and the deleted note's own node the entire
time; the new note never appeared either.

Root cause: GraphView (views/graph.jsx) loads its data once on mount and
again only when its own `source`/`scope` controls change (its data-loading
effect's dependency array is `[source, scope]`) — nothing about a vault
mutation is in that list. It already exposes `window.CafresoHQGraph.refresh()`
for exactly this situation, but nothing in views/vault.jsx ever called it:
`refresh()` there only ever touched its own `files` state.

Fix: a `refreshGraph()` helper that best-effort calls
`window.CafresoHQGraph.refresh()` (swallowed — a graph panel one tick behind
is cosmetic, not worth surfacing as an error), called from both success
branches of vault.jsx's `refresh()` — which every mutation path (save,
delete, rename, upload) already routes through.

Static checks only — these are closures inside VaultView, not exported pure
functions (same constraint as this session's other views/*.jsx suites).

Run: python3 scripts/test_vault_graph_refresh.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'views' / 'vault.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('vault graph refresh — the analysis panel stays in sync with the file tree')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    src = SRC.read_text(encoding='utf-8')

    check('refreshGraph() exists and calls window.CafresoHQGraph.refresh()',
          bool(re.search(r"const refreshGraph = \(\) => \{[\s\S]*?window\.CafresoHQGraph[\s\S]*?\.refresh\(\)", src)),
          'views/vault.jsx: must call the escape hatch GraphView already '
          'exposes for exactly this')
    check('refreshGraph() swallows failures (best-effort, not a hard error)',
          bool(re.search(r"const refreshGraph = \(\) => \{\s*\n\s*try \{ window\.CafresoHQGraph[\s\S]*?\} catch \(_e\) \{\}", src)),
          "views/vault.jsx: a stale graph panel must never surface as a "
          "vault error — it's cosmetic")

    refresh_fn = src[src.find('const refresh = async () => {'):]
    refresh_fn = refresh_fn[:refresh_fn.find('\n  React.useEffect(() => { refresh(); }, []);')]
    check("refresh()'s bridge-mode success path calls refreshGraph()",
          bool(re.search(r"setStatus\(\{ configured: true, exists: true, name: '🔐 Encrypted Vault', backend: 'bridge' \}\);\s*\n\s*refreshGraph\(\);", refresh_fn)),
          'views/vault.jsx: the bridge (encrypted shell) success branch must '
          'refresh the graph too, not just the local-backend branch')
    check("refresh()'s local-backend success path calls refreshGraph()",
          bool(re.search(r"setFiles\(await CafresoHQClient\.vaultList\(\)\);\s*\n\s*refreshGraph\(\);", refresh_fn)),
          'views/vault.jsx: without this, the exact repro (delete a note, '
          'create one, click Refresh) stays broken for every local-backend '
          'install — the common case')

    print()
    if FAILS:
        print(f'vault graph refresh: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('vault graph refresh: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
