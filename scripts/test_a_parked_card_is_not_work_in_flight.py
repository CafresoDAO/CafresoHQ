#!/usr/bin/env python3
"""The office asked leave to bin work that had already come back empty.

Measured on office 9261, 2026-08-15: Vera's run on "Empty hands three"
ended with nothing, so the card parked in `doing` with a blockedReason —
"Nothing came back from this run — no answer and no file" — and her desk
read idle. Assigning a fresh task and clicking ▶ START raised the danger
dialog:

    Vera is working on "Empty hands three".
    Start "DM relay" instead? "Empty hands three" goes back to the inbox
    and whatever they had done on it so far is lost.

Both claims false. The run had ended — nothing was in flight for
beginAgentRun's abort to kill — and there was nothing "done so far" to
lose. The evidence for "working on" was card status alone, and a blocked
card sits in `doing` BY DESIGN (the board has no blocked column; see
test_a_blocked_card_says_so). So every coworker who ever came back
empty-handed put a false confirm between the boss and their next dispatch
— and on the chain path (opts.auto), a false "still on X" stall note.

The fix is HQ.displacedTask(tasks, agentId, taskId, running): null unless
a run is actually in flight (the caller passes the aborter registry's
answer — the abort is what the dialog warns about, so the abort's own
registry says whether anything can be lost) AND the card is `doing`
without a blockedReason (a parked snag is definitionally a run that
ENDED, so it is never the work a new start would destroy).

This suite lifts displacedTask out of hq-runtime.jsx and drives both
directions, then pins the app.jsx call site to the registry so the pure
function cannot be fed a guess.

Since #129 the caller reads that registry into a named `running` a line
earlier, because one registrant — a pipeline handing over from the tail of
its own finishing step — is not a run this card would displace. The
call-site check follows it there: `running` still has to trace back to the
registry, it is just no longer spelled inline.

Run: python3 scripts/test_a_parked_card_is_not_work_in_flight.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'hq-runtime.jsx'
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
    print('a parked card is not work in flight')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    runtime = RUNTIME.read_text(encoding='utf-8')
    fn = brace_lift(runtime, 'function displacedTask(')

    # ---- behavior: drive the lifted function itself ----
    # Cards mirror the real store shapes: assignedTo (not agentId), and a
    # blocked card is `doing` + blockedReason exactly as the run-end path
    # stamps it.
    live = {'id': 't_live', 'assignedTo': 'a_1', 'status': 'doing',
            'blockedReason': '', 'title': 'cherry'}
    parked = {'id': 't_parked', 'assignedTo': 'a_1', 'status': 'doing',
              'blockedReason': 'Nothing came back from this run — no answer '
                               'and no file.', 'title': 'Empty hands three'}
    done = {'id': 't_done', 'assignedTo': 'a_1', 'status': 'done',
            'blockedReason': '', 'title': 'lime'}
    inbox = {'id': 't_inbox', 'assignedTo': 'a_1', 'status': 'inbox',
             'blockedReason': '', 'title': 'fig'}
    other = {'id': 't_other', 'assignedTo': 'a_2', 'status': 'doing',
             'blockedReason': '', 'title': 'plum'}

    scenarios = {
        # The dialog still guards real work: a live run's card displaces.
        'real_work': {'tasks': [live, done], 'agent': 'a_1',
                      'task': 't_new', 'running': True},
        # The measured lie: idle coworker, parked snag — no dialog.
        'parked_idle': {'tasks': [parked], 'agent': 'a_1',
                        'task': 't_new', 'running': False},
        # Mid-run on something ELSE, snag still parked: the snag is never
        # the run in flight, so it is never what a start would destroy.
        'parked_while_running': {'tasks': [parked], 'agent': 'a_1',
                                 'task': 't_new', 'running': True},
        # No live run at all: nothing can be killed, whatever the cards say.
        'stale_doing_no_run': {'tasks': [live], 'agent': 'a_1',
                               'task': 't_new', 'running': False},
        # Restarting the parked card itself is not its own displacement.
        'restart_self': {'tasks': [live], 'agent': 'a_1',
                         'task': 't_live', 'running': True},
        # Another coworker's run is not this desk's work.
        'other_desk': {'tasks': [other], 'agent': 'a_1',
                       'task': 't_new', 'running': True},
        # Finished and waiting cards never displace.
        'settled_cards': {'tasks': [done, inbox], 'agent': 'a_1',
                          'task': 't_new', 'running': True},
        # A live run picks the live card even with a snag parked beside it.
        'live_beside_parked': {'tasks': [parked, live], 'agent': 'a_1',
                               'task': 't_new', 'running': True},
        # An empty board is quiet.
        'no_cards': {'tasks': [], 'agent': 'a_1',
                     'task': 't_new', 'running': True},
    }

    js = fn + '\nconst S = ' + json.dumps(scenarios) + ';\n'
    js += '''
const out = {};
for (const [k, s] of Object.entries(S)) {
  const d = displacedTask(s.tasks, s.agent, s.task, s.running);
  out[k] = d ? d.id : null;
}
console.log(JSON.stringify(out));
'''
    p = subprocess.run(['node', '--input-type=module', '-e', js], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('lifted displacedTask runs', False, p.stderr.strip()[:300])
        print('FAIL')
        return 1
    got = json.loads(p.stdout.strip().split('\n')[-1])

    check('a live run\'s card still displaces — the dialog guards real work',
          got['real_work'] == 't_live', got)
    check('the measured case: parked snag, idle desk — no dialog',
          got['parked_idle'] is None, got)
    check('a parked snag is never the run in flight, even mid-run',
          got['parked_while_running'] is None, got)
    check('no live run means nothing can be lost, whatever the cards say',
          got['stale_doing_no_run'] is None, got)
    check('restarting the parked card is not its own displacement',
          got['restart_self'] is None, got)
    check('another desk\'s run is not this one\'s work',
          got['other_desk'] is None, got)
    check('done and inbox cards never displace',
          got['settled_cards'] is None, got)
    check('with a snag parked beside a live run, the live card is the one named',
          got['live_beside_parked'] == 't_live', got)
    check('an empty board is quiet', got['no_cards'] is None, got)

    # ---- structure: the function's two gates are in CODE, not prose ----
    fn_code = strip_comments(fn)
    check('the function refuses to displace without a live run',
          re.search(r'if\s*\(\s*!running\s*\)\s*return null', fn_code)
          is not None)
    check('the function reads the card\'s ended-run stamp',
          '!t.blockedReason' in fn_code)

    # ---- call site: the registry answers "running", not a guess ----
    app = strip_comments(APP.read_text(encoding='utf-8'))
    m = re.search(
        r'const displaced = HQ\.displacedTask\(tasks,\s*agent\.id,\s*taskId,'
        r'\s*running\)', app)
    check('START asks whether a run is in flight', m is not None)
    check('...and that answer is the aborter registry\'s, not a guess',
          re.search(r'const priorRun = agentAbortersRef\.current\.get\(agent\.id\);'
                    r'.{0,400}?const running = !!priorRun', app, re.S) is not None,
          '`running` must trace to the registry the abort itself rides')
    check('the old status-only find is gone',
          "t.assignedTo === agent.id && t.status === 'doing');" not in app)
    if m:
        after = app[m.end():m.end() + 2500]
        check('the chain branch still stalls only on real work',
              'if (displaced && opts.auto)' in after)
        check('the danger dialog still sits behind the same answer',
              'if (displaced)' in after
              and 'window.hqConfirm(' in after)

    print('FAIL' if FAILS else 'PASS')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
