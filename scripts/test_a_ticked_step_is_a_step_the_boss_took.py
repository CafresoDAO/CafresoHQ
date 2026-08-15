#!/usr/bin/env python3
"""The Getting Started checklist ticked a step the boss never did.

Reproduced 2026-08-15 on a fresh office (port 9261, cleared localStorage):

    fresh                                          0/6
    hire Vera onto a local brain                   2/6
    send one `@Vera hello`, never open Tasks       5/6

and the fifth tick was step 4, "✓ Give them a task", over `tasks: []`.
The step whose own hint reads "Add a task, then drop it on a desk to
delegate" marked itself done for a boss who had done neither.

The event behind it is logged for EVERY chat dispatch (app.jsx, the
logActivity above agentStream's peer list):

    action: dmFrom ? 'dm' : 'assigned',
    text:   `picked up "hello…"`

As a feed row that is true — a coworker did pick up a job, and
views/core.jsx maps `assigned` to 📋 to say so. As an answer to "has the
boss created a task and dropped it on a desk" it is a different claim
about a different actor. Two onboarding surfaces asked the second
question and read the first answer.

The second half is the one that matters more. The coach mark reads:

    if (chatted && !assigned && !seen.task)
      return { k: 'task', text: 'Give them something real: drop a task
               on their desk.', ... }

so the same event that ticked the step also SUPPRESSED the pill pointing
at the thing the step was teaching. The office decided the boss had
learned delegation, and on that basis stopped showing them delegation.
Verified both halves live, after the fix: 4/6 with step 4 unticked and
its CTA showing, and the pill back (it is hidden while the checklist is
expanded — app.jsx's coach-mark render — so it was read with the
checklist collapsed).

`taskId` was already on the event and already told the two apart: the
task path passes a real one, the chat path logs null. One shared memo
asks the question once.

Run: python3 scripts/test_a_ticked_step_is_a_step_the_boss_took.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_RAW = (ROOT / 'app.jsx').read_text(encoding='utf-8')
CORE_RAW = (ROOT / 'views' / 'core.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Scan code, never prose. The comment written with this fix quotes
    `action === 'assigned'` twice while explaining why nothing may read
    it — a scanner that counts prose would read the fix as the defect."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def call_args(src, marker):
    """The arguments of a call, by paren matching.

    Sixth suite to need a structural lift. `{0,N}?` windows and naive
    delimiter searches do not report "not found" when the code outgrows
    them — they report a confident false statement about what they did
    reach. The marker ends at the opening paren; matching finds the
    close, and the top-level commas split the args.
    """
    i = src.index(marker)
    j = i + len(marker) - 1
    assert src[j] == '(', marker
    depth = 0
    for k in range(j, len(src)):
        c = src[k]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
            if depth == 0:
                inner = src[j + 1:k]
                break
    else:
        raise AssertionError('unbalanced parens lifting ' + marker)
    args, depth, start = [], 0, 0
    for k, c in enumerate(inner):
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
        elif c == ',' and depth == 0:
            args.append(inner[start:k])
            start = k + 1
    args.append(inner[start:])
    return [a.strip() for a in args]


def main():
    print('a ticked step is a step the boss took')
    app = strip_comments(APP_RAW)
    core = strip_comments(CORE_RAW)

    # ── 1. the question is asked once ───────────────────────────────────
    args = call_args(app, 'const taskDelegated = useMemoA(')
    pred, deps = args[0], args[-1]
    check('there is one shared answer to "has the boss delegated?"',
          len(args) == 2 and pred.startswith('()'),
          args)
    check('...that requires the event to name a task',
          re.search(r"action === 'assigned'\s*&&\s*e\.taskId", pred),
          [pred, "— every chat dispatch logs action:'assigned' with "
           'taskId:null; without the second half a hello ticks the step'])
    check('...and still counts a task that carries an assignee',
          'assignedTo' in pred,
          [pred, '— the tasks board is the primary evidence; activity is '
           'the fallback for a task that was assigned then completed'])
    check('...over both tasks and activity', deps == '[tasks, activity]', deps)

    # The whole point: not two copies of the predicate that can drift.
    # 1a33ca4 was the same shape (four readers of one fact, the boss's
    # one reading the weakest copy); 6c27d29 was two surfaces on one
    # screen. This is two surfaces of the SAME onboarding flow.
    body = app[app.index('const taskDelegated = useMemoA('):]
    copies = len(re.findall(r"action === 'assigned'", body))
    check('no surface re-derives it from the ambiguous event',
          copies == 1,
          [copies, "— one occurrence, inside taskDelegated. A second is a "
           "second opinion about what the boss has done"])

    # ── 2. both readers read that one answer ────────────────────────────
    check('the Getting Started checklist reads the shared answer',
          re.search(r'assigned=\{taskDelegated\}', app),
          'app.jsx GettingStarted props')
    coach = app[app.index('const coachMark = React.useMemo('):]
    coach = coach[:coach.index('\n  }, [') + 200]
    check('...and so does the coach mark',
          re.search(r'const assigned = taskDelegated;', coach), coach[:400])
    check('...and the coach mark re-runs when the answer changes',
          re.search(r'\}, \[[^\]]*taskDelegated[^\]]*\]\);', coach),
          [coach[-200:], '— the memo body no longer reads `tasks`, so a '
           'deps list naming `tasks` instead of `taskDelegated` leaves the '
           'pill showing yesterday\'s answer'])
    check('the pill that teaches delegation is still gated on it',
          re.search(r"if \(chatted && !assigned && !seen\.task\)", coach),
          '— this is the half that was SUPPRESSED, not merely mis-ticked')

    # ── 3. the feed row it was confused with is untouched ───────────────
    # The fix repoints the readers rather than renaming the action,
    # because the feed legitimately consumes it and the row is true.
    check("chat dispatch still logs the 'assigned' feed row",
          re.search(r"action: dmFrom \? 'dm' : 'assigned',", app),
          '— a coworker picking up a job is real; the row says so')
    check('...and the feed still has an icon for it',
          re.search(r"assigned: *'[^']+'", core),
          'views/core.jsx event icons — renaming the action breaks this')
    check('the real task path still passes a task id',
          re.search(r"action: 'assigned', taskId, text: `picked up", app),
          '— the discriminator only works if the honest path supplies it')

    # ── 4. run the predicate against the reproduced sessions ────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the scenario checks need it')
    else:
        # The lifted arrow runs verbatim, closing over the two parameters
        # it reads — rewriting its signature to take them would be the
        # test quietly editing the code it is checking.
        js = 'const mk = (tasks, activity) => (' + pred + ')();\n'
        js += r'''
const q = (tasks, activity) => !!mk(tasks, activity);
const CHAT = { action: 'assigned', taskId: null, text: 'picked up "hello…"' };
const R = {
  // The reproduced session, exactly: one hire, one @mention, no board.
  chatOnly: q([], [CHAT, { action: 'done', taskId: null }]),
  fresh:    q([], []),
  dm:       q([], [{ action: 'dm', taskId: null }]),
  // A task dropped on a desk.
  onDesk:   q([{ id: 't1', title: 'x', assignedTo: 'a1' }], []),
  // Assigned, then completed — `assignedTo` is gone, which is the whole
  // reason the activity fallback exists. It must still count.
  wasOnDesk: q([{ id: 't1', title: 'x', status: 'done' }],
               [{ action: 'assigned', taskId: 't1' }]),
  // A board with unassigned tasks on it is not delegation.
  unassigned: q([{ id: 't1', title: 'x' }], []),
  // Both kinds of evidence at once.
  both:     q([{ id: 't1', assignedTo: 'a1' }], [{ action: 'assigned', taskId: 't1' }]),
};
console.log(JSON.stringify(R));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        if p.returncode != 0:
            check('the scenario harness runs', False, p.stderr.strip()[:400])
        else:
            R = json.loads(p.stdout)
            check('one hello to a coworker is not a delegated task',
                  R['chatOnly'] is False,
                  [R, '— the reproduced 5/6. This is the defect.'])
            check('a fresh office has delegated nothing', R['fresh'] is False, R)
            check('a DM is not a delegated task', R['dm'] is False, R)
            check('a task on a desk is', R['onDesk'] is True, R)
            check('...and stays counted after it is completed',
                  R['wasOnDesk'] is True,
                  [R, '— the fallback exists for exactly this; requiring '
                   'taskId must not cost it'])
            check('a task nobody was given is not delegated',
                  R['unassigned'] is False, R)
            check('both kinds of evidence still answer yes',
                  R['both'] is True, R)

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
