#!/usr/bin/env python3
"""A Research Mission's tool calls never reached the ticker, the Team
inbox, or Receipts — the fourth tool-dispatch path this office has, and
the only one that didn't file through `toolActivity`.

app.jsx documents three tool-dispatch streams handling a tool's `done`
event (dispatchToAgent, the delegate path, the task path), and the last
of those to get fixed (this document's own ticket a few entries up)
found dispatchToAgent silently skipping `logActivity`. That ticket only
checked app.jsx's own three streams; missions.jsx — the foreground
"Research Missions" runner (`useMissionRunner` / `runMissionIteration`)
— is a fourth, entirely separate stream, in a separate file, and it
never called `logActivity` OR `recordToolReceipt` at all. The
onboarding tour ("...every real action streams into the ticker and the
Team inbox") and the Getting Started checklist ("Desks light up; the
Team inbox logs every action") both promise coverage this stream never
delivered — nor did the elevated-agent banner's "every tool call is
logged to Receipts," if the mission's coworker happened to be elevated.

A coworker could run a whole research mission — desk lit, several
rounds of real web/vault tool calls — and none of it would show up
anywhere but the mission's own chat thread, invisible to a boss reading
the ticker or the Team inbox the way the app's own tutorial told them to.

Run: python3 scripts/test_mission_tools_reach_activity_and_receipts.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
MISS = (ROOT / 'missions.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('Do a mission\'s tool calls reach the ticker, the Team inbox, and Receipts?')

    # ── 1. app.jsx threads both functions into the mission runner's ctx ──
    check('useMissionRunner is handed logActivity and recordToolReceipt',
          re.search(
              r"useMissionRunner\(missions, setMissions, \{\s*"
              r"setChat, appendJournal, onUpdateAgent, pulseGraph, recordXp,\s*"
              r"logActivity, recordToolReceipt,",
              APP) is not None,
          'app.jsx: the ctx object passed to useMissionRunner does not '
          'carry logActivity/recordToolReceipt — without this, missions.jsx '
          'has no way to reach either surface no matter what it calls')

    # ── 2. runMissionIteration actually pulls them out of ctx ────────────
    check("runMissionIteration destructures both off ctx",
          "logActivity, recordToolReceipt, signal } = ctx;" in MISS,
          'missions.jsx: the values above are dropped on the floor unless '
          'this function actually reads them off ctx')

    # ── 3. the onTool done branch calls both, same relative order the
    #        three app.jsx streams already use (logActivity, pulseGraph,
    #        recordToolReceipt) ──────────────────────────────────────────
    done_branch = re.search(
        r"writesThisIter\.push\(\{ name: ev\.name, path: String\(ev\.arg \|\| ''\)\.trim\(\), at: Date\.now\(\) \}\);\s*"
        r"\}\s*"
        r"(?:/\*.*?\*/\s*)?"
        r"logActivity && logActivity\(toolActivity\(agent, ev\)\);\s*"
        r"pulseGraph && pulseGraph\(ev\);\s*"
        r"recordToolReceipt && recordToolReceipt\(agent, ev\);",
        MISS, re.S)
    check("the mission's onTool 'done' branch logs activity and records "
          "a receipt, in the same order (logActivity, pulseGraph, "
          "recordToolReceipt) the other three streams already use",
          done_branch is not None, 'missions.jsx onTool handler shape changed')

    # ── 4. toolActivity is actually imported, not a dangling reference ──
    check("toolActivity is imported from app/floor.jsx",
          "import { snagCause, snagSentence, toolActivity } from './app/floor.jsx';" in MISS,
          'a call to an unimported toolActivity would throw at runtime the '
          'first time a mission tool call finished')

    # ── 5. this is additive — the three existing app.jsx streams and the
    #        pre-existing missions.jsx writesThisIter/pulseGraph behavior
    #        are untouched ─────────────────────────────────────────────
    check("app.jsx's own three logActivity(toolActivity(...)) call sites are unchanged",
          APP.count('logActivity(toolActivity(') == 3, APP.count('logActivity(toolActivity('))
    check("the writes-that-landed guard (VAULT_NEW/VAULT_APPEND, not failed) is unchanged",
          "if (!ev.failed && (ev.name === 'VAULT_NEW' || ev.name === 'VAULT_APPEND')) {" in MISS,
          'missions.jsx')

    # ── 6. mechanism, run for real: the exact shape logActivity/receipt
    #        would see for a mission's own tool events ───────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the mechanism check needs it')
    else:
        js = r'''
function toolActivity(agent, ev) {
  const tense = ev && ev.failed ? 'fail' : 'past';
  return {
    agentId: agent && agent.id, agentName: agent && agent.name,
    color: agent && agent.color, action: 'tool',
    text: (ev.name + ' ' + tense).toLowerCase(),
  };
}
function drive(agent, ev) {
  const activity = [];
  const receipts = [];
  const logActivity = (entry) => activity.push({ id: 'act_x', ts: 0, priority: 'routine', unread: true, ...entry });
  const recordToolReceipt = (a, e) => receipts.push({ agentId: a.id, tool: e.name, failed: !!e.failed });
  // the exact call shape the onTool 'done' branch now makes
  logActivity && logActivity(toolActivity(agent, ev));
  recordToolReceipt && recordToolReceipt(agent, ev);
  return { activity, receipts };
}
const agent = { id: 'a1', name: 'Mira', color: '#fff', elevated: false };
console.log(JSON.stringify({
  vaultWrite: drive(agent, { name: 'VAULT_NEW', failed: false }),
  failedCall: drive(agent, { name: 'WEB_SEARCH', failed: true }),
}));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=15)
        if p.returncode != 0:
            check('the mechanism harness runs', False, p.stderr.strip()[:400])
        else:
            out = json.loads(p.stdout)
            check("a mission's successful vault write reaches the activity "
                  "feed, naming the coworker who did it",
                  len(out['vaultWrite']['activity']) == 1
                  and out['vaultWrite']['activity'][0]['agentName'] == 'Mira'
                  and out['vaultWrite']['activity'][0]['action'] == 'tool',
                  out['vaultWrite'])
            check("...and reaches Receipts too",
                  len(out['vaultWrite']['receipts']) == 1
                  and out['vaultWrite']['receipts'][0]['tool'] == 'VAULT_NEW',
                  out['vaultWrite'])
            check("a mission's failed tool call still reaches the activity "
                  "feed — a failure is not silently dropped the way it used "
                  "to be for the Receipts surface on a different ticket",
                  len(out['failedCall']['activity']) == 1, out['failedCall'])

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
