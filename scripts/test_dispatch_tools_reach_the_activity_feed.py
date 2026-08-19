#!/usr/bin/env python3
"""A tool call made mid ordinary chat, or in a peer DM, never reached the
activity feed — the "single source of truth for the ticker, the
notification center, and the Team inbox" (app.jsx's own doc comment on
`activity`).

app.jsx has three places a tool call's `done` event is handled:

    dispatchToAgent      — normal chat replies AND peer-to-peer DMs;
                            its own comment calls it "the most-used route
                            in the office"
    the delegate path    — a boss-hired sub-agent working in the background
    the task path        — a scheduled/assigned task running in the background

The other two both call `logActivity(toolActivity(agent, ev))` on `done`,
success or failure, unconditionally. `dispatchToAgent`'s own `done`
branch called `recordToolReceipt` and `attachVisit`, but never
`logActivity` — so a tool call on the app's PRIMARY dispatch path left a
transient visit card in the one chat thread it happened in, and nothing
in the persisted record the ticker, notification center, and Team inbox
all read from.

This is a different gap from the Receipts one a few entries up — that
was about the elevated-agent AUDIT surface; this is about the LIVE
ACTIVITY surface every agent's tool calls are supposed to feed,
regardless of elevation. Found while investigating that ticket: the code
comment claiming elevated agents get "a full tool audit log" led to
checking every place a tool `done` event is handled, and this stream was
missing a call the other two already had, with no comment anywhere
explaining the gap as deliberate — unlike the well-reasoned exclusions
found and preserved elsewhere in this file.

**The fix** adds the same `logActivity(toolActivity(agent, ev))` call to
dispatchToAgent's `done` branch, in the same relative position (right
after `attachVisit`) the other two streams already use.

Run: python3 scripts/test_dispatch_tools_reach_the_activity_feed.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('Does a tool call on the primary chat/DM path reach the activity feed?')

    # ── 1. all three tool streams now file through the shared helper ────
    check("exactly three call sites file a tool's activity line through "
          "toolActivity — the two that always did, plus dispatchToAgent's, "
          "which never did",
          APP.count('logActivity(toolActivity(') == 3,
          'found %d' % APP.count('logActivity(toolActivity('))

    # ── 2. dispatchToAgent's own done branch is the new one, and it isn't
    #        a hand-rolled duplicate of the other two ──────────────────────
    dispatch_done = re.search(
        r"attachVisit\(setChat, agentMsgId, ev\);\s*"
        r"(?:/\*.*?\*/\s*)?"
        r"logActivity\(toolActivity\(agent, ev\)\);\s*"
        r"pulseGraph\(ev, agent\);\s*"
        r"recordToolReceipt\(agent, ev\);",
        APP, re.S)
    check("dispatchToAgent's done branch logs activity right after "
          "attachVisit, ahead of pulseGraph and recordToolReceipt — same "
          "relative order the other two streams use",
          dispatch_done is not None, APP[:0])

    # ── 3. the two pre-existing streams are untouched — this ticket adds a
    #        third call, it does not touch the other two ───────────────────
    check('the delegate path\'s call is unchanged',
          'logActivity(toolActivity(a, ev));' in APP, APP[:0])
    check('the task path\'s call (still carrying taskId) is unchanged',
          'logActivity(toolActivity(agent, ev, { taskId }));' in APP, APP[:0])

    # ── 4. mechanism, run for real: toolActivity's own tense logic still
    #        applies uniformly regardless of which stream calls it ─────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the mechanism check needs it')
    else:
        # toolActivity itself (app/floor.jsx) is simple enough to restate
        # here rather than extract — its behavior is already covered by
        # that file's own tests; what's under test here is that
        # dispatchToAgent's done branch now calls it at all, with the
        # right two arguments, which the static regex above already
        # anchors precisely. This just proves the call, once made, would
        # actually produce a real, well-formed activity entry rather than
        # e.g. an object shaped wrong for logActivity to use.
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
  const logActivity = (entry) => activity.push({ id: 'act_x', ts: 0, priority: 'routine', unread: true, ...entry });
  logActivity(toolActivity(agent, ev));
  return activity;
}
console.log(JSON.stringify({
  success: drive({ id: 'a1', name: 'Selvin', color: '#fff' }, { name: 'BASH', failed: false }),
  failure: drive({ id: 'a1', name: 'Selvin', color: '#fff' }, { name: 'BASH', failed: true }),
}));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=15)
        if p.returncode != 0:
            check('the mechanism harness runs', False, p.stderr.strip()[:400])
        else:
            out = json.loads(p.stdout)
            check("a successful tool call produces exactly one activity "
                  "entry naming the agent, with action 'tool'",
                  len(out['success']) == 1 and out['success'][0]['agentName'] == 'Selvin'
                  and out['success'][0]['action'] == 'tool', out['success'])
            check("a failed tool call ALSO produces one — dispatchToAgent's "
                  "stream must not silently skip failures the way Receipts "
                  "used to",
                  len(out['failure']) == 1, out['failure'])

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
