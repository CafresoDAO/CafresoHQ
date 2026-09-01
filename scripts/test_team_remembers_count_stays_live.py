#!/usr/bin/env python3
"""TeamView's "Remembers · N notes" stat froze the moment the tab mounted.

The roster card's vault-note count is built from one shared `vaultList()`
fetch, refetched only when `agents.length` changed (a hire or a dismiss).
Nothing else in TeamView ever called it again. But a coworker's notes
(`Agents/<name>/…` in the vault) change constantly while they work — a
job finishing, a note being appended, a mission writing findings — none
of which touch `agents.length`. The Inbox panel on the SAME screen already
live-logs every vault write via the `activity` feed (app.jsx's onActivity
handler stamps `action: 'vault'`, text prefixed "wrote "/"linked "/"read ").
So a boss sitting on Team, watching a coworker work, would see the Inbox
log "wrote Agents/Hermes/some-note.md" in real time right next to a
"Remembers · 3 notes" stat that never became 4.

Same shape as the vault-standing-search staleness bug fixed for the
Library a few commits earlier — sticky client state built from a vault
snapshot with no seat at refresh — just never applied here too.

Fix: derive `vaultWriteCount` from `activity` (counting only entries whose
action is 'vault' and whose text starts with "wrote ", since a link or a
read doesn't add a note to the cabinet) and add it to the fetch effect's
dependency array alongside `agents.length`.

Verified live: with Team mounted, dispatching a synthetic
`cafresohq:agentActivity` write event fired a fresh GET to /vault/list
without navigating away — confirmed via the network log (two calls where
before there was one).

Run: python3 scripts/test_team_remembers_count_stays_live.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / 'views' / 'core.jsx'
APP = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def slice_to_next_function(src, opener):
    i = src.index(opener)
    j = src.find('\nfunction ', i + len(opener))
    return src[i:] if j == -1 else src[i:j]


def main():
    print("Team's Remembers-note count refetches on a live vault write, "
          "not just on hire/dismiss")

    core = CORE.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')

    team_fn = slice_to_next_function(
        core, 'function TeamView({ agents, activity = [], experience = [], onHire, onInspect, onDismiss, onShowCEO, onOpenTasks, onMarkRead, approvals = [], onApprove, onReject, onRetry }) {')
    check('found TeamView by its declared signature', len(team_fn) > 100,
          'views/core.jsx: TeamView signature changed shape')

    check('TeamView derives a vaultWriteCount from the activity feed, '
          'counting only actual writes (not links or reads)',
          re.search(
              r"vaultWriteCount = React\.useMemo\(\(\) =>\s*"
              r"activity\.reduce\(\(n, e\) => n \+ \(e\.action === 'vault' "
              r"&& typeof e\.text === 'string' && e\.text\.startsWith\('wrote '\) \? 1 : 0\), 0\),\s*"
              r"\[activity\]\);",
              team_fn) is not None,
          team_fn)

    check("the vaultList() refetch effect's dependency array includes "
          "vaultWriteCount alongside agents.length — the actual fix; "
          "without it the effect never reruns on a live write",
          re.search(r"\}, \[agents\.length, vaultWriteCount\]\);", team_fn) is not None,
          'views/core.jsx: fetch effect deps missing vaultWriteCount')

    # Pin the upstream signal this all depends on: app.jsx must still stamp
    # a 'vault' action with a "wrote "-prefixed text for a real write, or
    # vaultWriteCount always reads zero and the fix is inert.
    check("app.jsx's activity handler still stamps action: 'vault' for "
          "agent vault events",
          "action: 'vault'" in app, 'app.jsx: vault activity action renamed')
    check("...and still labels a write as \"wrote \" (not e.g. \"saved \")",
          "d.kind === 'write' ? 'wrote'" in app,
          'app.jsx: write label changed — vaultWriteCount\'s prefix match would silently stop matching')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
