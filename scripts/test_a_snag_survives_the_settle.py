#!/usr/bin/env python3
"""The floor said "standing by" while the board said blocked.

Measured on office 9261, 2026-08-15, task "Empty hands two", a coworker
whose brain streamed a lead-in and nothing else. The run lands on the desk
truthfully — `active · stuck · "came back with nothing"` — and the Tasks
board parks the card in `doing` with a blockedReason. Four seconds later
the settle timer fires and the desk reads `idle · idle · "standing by"`,
blank badge. Sampled:

    0.3s  status active · mood stuck · desk "reporting back" · card doing+blocked
    4.2s  status idle   · mood idle  · desk "standing by"    · card doing+blocked

Two surfaces disagreeing about one run. And this was the only stuck badge
in the office with an expiry date: every error path sets idle+stuck
directly, never calls settle, and keeps its badge until the next dispatch.
The empty-handed run — the one snag that ends still-`active` and rides
settleAfterRun — had its badge erased by a landing hard-coded for success.

The fix reads the mood at fire time: a stuck run keeps its badge and its
story (only `status` drops, and the desk line becomes the snag itself, so
the floor and the board tell one story), any other run gets the original
wipe to "standing by". This suite lifts settleAfterRun out of app.jsx and
drives both landings, the guards that protect a re-dispatch and the error
paths, and the caller coupling that routes the empty-handed run through
settle in the first place.

Run: python3 scripts/test_a_snag_survives_the_settle.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, header):
    i = src.index(header)
    j = src.index('{', i + len(header) - 1)
    d = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces after ' + header)


def strip_comments(src):
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('a snag survives the settle')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    src = APP.read_text(encoding='utf-8')
    code = strip_comments(src)

    # ---- structure: the landing branches on mood, and only status drops ----
    # These read CODE, not comments — a fix that lives in prose is not a fix.
    settle = brace_lift(code, 'const settleAfterRun = (agentId) => ')
    check('the landing reads the mood at fire time',
          "a.mood === 'stuck'" in settle, 'no mood branch in settleAfterRun')
    stuck_branch = ''
    try:
        stuck_branch = brace_lift(settle, "if (a.mood === 'stuck') ")
    except ValueError:
        pass
    check('the stuck landing does not touch the badge',
          stuck_branch and 'mood:' not in stuck_branch,
          repr(stuck_branch[:120]))
    check('the wipe survives for everyone else',
          "task: 'standing by'" in settle, 'produced runs must still sit down')

    # The coupling that makes the landing meaningful: the empty-handed task
    # run is the one snag that ends still-`active` and rides settle. If that
    # caller stops calling settle (or stops landing stuck), the branch above
    # guards a path nothing takes.
    m = re.search(r"mood: produced \? 'done' : 'stuck',", code)
    check('the empty-handed run still lands stuck', bool(m))
    after = code[m.end():m.end() + 600] if m else ''
    check('...and still rides the settle timer',
          'settleAfterRun(agent.id)' in after,
          'no settleAfterRun call after the stuck landing')

    # ---- behaviour: lift settleAfterRun and drive both landings ----
    lifted = brace_lift(src, 'const settleAfterRun = (agentId) => ')
    harness = r'''
const timers = [];
// 1-based handles: browser setTimeout never returns 0, and the code under
// test guards `if (prev)` — a 0-valued stub handle would dodge the clear.
const setTimeout = (fn, ms) => { timers.push({ fn, ms, cleared: false }); return timers.length; };
const clearTimeout = (h) => { if (timers[h - 1]) timers[h - 1].cleared = true; };
const settleTimersRef = { current: new Map() };
let agents = [];
const setAgents = (up) => { agents = up(agents); };
''' + lifted + r''';
function scenario(agent, id) {
  timers.length = 0;
  settleTimersRef.current.clear();
  agents = [agent];
  settleAfterRun(id || 'a1');
  const t = timers[timers.length - 1];
  if (t) t.fn();
  return { ms: t ? t.ms : null, out: agents[0] };
}
const R = {};
R.stuck = scenario({ id: 'a1', status: 'active', mood: 'stuck', task: 'reporting back', recent: 'came back with nothing' });
R.done = scenario({ id: 'a1', status: 'active', mood: 'done', task: 'reporting back', recent: 'The vendor is Acme.' });
R.busy = scenario({ id: 'a1', status: 'busy', mood: 'focused', task: 'drafting the vendor list', recent: '' });
// Non-empty `recent` on purpose: error paths keep whatever the coworker
// last said. If settle's guard ever loses the active check, the stuck
// branch would overwrite this agent's snag sentence with that leftover —
// an empty `recent` would make the trespass invisible.
R.err = scenario({ id: 'a1', status: 'idle', mood: 'stuck', task: 'hit a snag: brain unreachable', recent: 'the last thing they actually said' });
R.other = scenario({ id: 'a2', status: 'active', mood: 'stuck', task: 'reporting back', recent: 'came back with nothing' }, 'a1');
R.bare = scenario({ id: 'a1', status: 'active', mood: 'stuck', task: 'reporting back', recent: '' });
timers.length = 0;
settleTimersRef.current.clear();
agents = [{ id: 'a1', status: 'active', mood: 'done', task: 'reporting back', recent: 'x' }];
settleAfterRun('a1');
settleAfterRun('a1');
R.rearm = { firstCleared: timers[0].cleared, count: timers.length };
timers[timers.length - 1].fn();
R.rearm.out = agents[0];
console.log(JSON.stringify(R));
'''
    proc = subprocess.run(['node', '-e', harness], cwd=ROOT,
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        check('the settle harness runs', False, 'node exited %d' % proc.returncode)
        return 1
    R = json.loads(proc.stdout.strip().split('\n')[-1])

    check('the linger keeps the beat', R['stuck']['ms'] == 4000, R['stuck']['ms'])
    check('a stuck run sits down', R['stuck']['out']['status'] == 'idle',
          R['stuck']['out'])
    check('a stuck run keeps its badge', R['stuck']['out']['mood'] == 'stuck',
          R['stuck']['out'])
    check('the desk line becomes the snag',
          R['stuck']['out']['task'] == 'came back with nothing', R['stuck']['out'])
    check('a produced run still settles to standing by',
          R['done']['out']['status'] == 'idle'
          and R['done']['out']['mood'] == 'idle'
          and R['done']['out']['task'] == 'standing by', R['done']['out'])
    check('a re-dispatch inside the window is left alone',
          R['busy']['out']['status'] == 'busy'
          and R['busy']['out']['task'] == 'drafting the vendor list', R['busy']['out'])
    check("an error-path badge is not settle's to touch",
          R['err']['out']['mood'] == 'stuck'
          and R['err']['out']['task'] == 'hit a snag: brain unreachable',
          R['err']['out'])
    check('another desk is not touched',
          R['other']['out']['status'] == 'active'
          and R['other']['out']['mood'] == 'stuck', R['other']['out'])
    check('an empty snag line falls back to the desk line',
          R['bare']['out']['task'] == 'reporting back', R['bare']['out'])
    check('re-arming clears the earlier timer',
          R['rearm']['firstCleared'] and R['rearm']['count'] == 2
          and R['rearm']['out']['task'] == 'standing by', R['rearm'])

    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
