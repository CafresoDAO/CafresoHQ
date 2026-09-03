#!/usr/bin/env python3
"""The workflow panel called a thrown run "not started yet".

Reproduced live 2026-09-03 on a fresh office (127.0.0.1:8902): one hired
coworker, no AI key configured. A two-step workflow ("Docs Pipeline"),
step one dropped on the coworker's desk.

    the coworker's chat bubble   ⚠ No Anthropic API key — open Settings
                                    → Connections. This run failed.
    the task board card          ⚠ Rocky hit a snag on this
    tasks.json (step one)        status "inbox", assignedTo null,
                                  blockedReason "", stalledNote null
    ⛓ Workflows panel            "DOCS PIPELINE · 0/2 done"

Three surfaces agree a run was attempted and failed. The fourth — the one
place a boss goes to ask how their PIPELINE is doing — read the exact same
step as identical to one nobody had ever touched.

The mechanism: onTaskDropOnAgent's catch branch (app.jsx) sends a snagged
run back to `status: 'inbox'` with `assignedTo` and `blockedReason` both
cleared. That is correct — the step must stay re-delegatable, and #86 (see
test_a_stalled_workflow_says_so.py) already established that a task's own
live fields are not where a failure gets remembered once the run ends. What
the office actually keeps is the XP ledger, and the task card already reads
it (`xpLastAttemptText`, app/experience.jsx) to print "Rocky hit a snag on
this" — because this exact gap was fixed once already, on that surface. The
workflow panel's per-pipeline summary (`modals/collab.jsx`) never got the
same fix: it counted `done`, `doing` and `isParked` off `t.status` alone,
and a step that threw is none of those three — it reads as untouched.

The fix pulls the per-workflow summary out into a named function,
`workflowStatusBits(wf, tasks, experience)`, and adds a fourth bucket:
`snagged` — not done, not doing, and the ledger's newest entry for this
task id is an `outcome: 'snag'`. It clears itself the moment a retry
succeeds (a fresh `done` entry outranks the old `snag` one by timestamp) or
starts again (`status: 'doing'` moves the step to `in progress` instead).

This test lifts the real `isParked`, `xpLastAttempt` and `workflowStatusBits`
out of their source files by name and runs them together under Node, so what
is driven is the real bucketing logic, not a description of it.

Run: python3 scripts/test_the_workflow_panel_knows_a_step_failed.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLLAB = (ROOT / 'modals' / 'collab.jsx').read_text(encoding='utf-8')
WORKLOG = (ROOT / 'app' / 'worklog.jsx').read_text(encoding='utf-8')
EXPERIENCE = (ROOT / 'app' / 'experience.jsx').read_text(encoding='utf-8')
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def func(src, name, where):
    """`function <name>(` to ITS OWN balanced closing brace (not the next
    top-level function — these are plain helpers, not components with
    siblings to stop at). A rename or a deleted function is a hard stop:
    a locator pinned to a signature that no longer exists must not hand
    back an empty string that then satisfies every negative check."""
    m = re.search(r'\bfunction %s\(' % re.escape(name), src)
    if not m:
        raise SystemExit('no `function %s(` in %s' % (name, where))
    brace = src.index('{', m.end())
    depth = 0
    for j in range(brace, len(src)):
        c = src[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
    raise SystemExit('unterminated function %s in %s' % (name, where))


def call_block(src, tag):
    """The `<Tag ... />` JSX call, tag to its own closing `/>`."""
    i = src.index('<' + tag)
    j = src.index('/>', i)
    return src[i:j + 2]


def node(js):
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                        cwd=ROOT, capture_output=True, text=True, timeout=90)
    if p.returncode != 0:
        print(p.stdout)
        print(p.stderr[-1500:], file=sys.stderr)
        return None
    return json.loads(p.stdout.strip().split('\n')[-1])


def main():
    print('the workflow panel knows a step failed')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    is_parked_src = func(WORKLOG, 'isParked', 'app/worklog.jsx')
    xp_last_src = func(EXPERIENCE, 'xpLastAttempt', 'app/experience.jsx')
    bits_src = func(COLLAB, 'workflowStatusBits', 'modals/collab.jsx')

    # ── 1. the wiring, statically ────────────────────────────────────────
    check('workflowStatusBits reads the XP ledger, not just t.status',
          'xpLastAttempt(' in bits_src,
          [bits_src, '— the panel this fixes only ever looked at the live task'])
    check('...and the import comes from app/experience.jsx, not re-derived',
          re.search(r"^import \{[^}]*\bxpLastAttempt\b[^}]*\} from '\.\./app/experience\.jsx';",
                    COLLAB, re.M),
          'modals/collab.jsx: a second copy of "what happened last time" is '
          'how the card and the panel start disagreeing')
    check('isParked is still read from worklog.jsx, not re-derived a third time',
          re.search(r"^import \{[^}]*\bisParked\b[^}]*\} from '\.\./app/worklog\.jsx';",
                    COLLAB, re.M),
          'modals/collab.jsx')
    render = COLLAB[COLLAB.index('YOUR WORKFLOWS'):COLLAB.index('YOUR WORKFLOWS') + 1600]
    check('the row in JSX calls the named function, not an inline recompute',
          'workflowStatusBits(wf, tasks, experience)' in render,
          [render, '— a second, inline copy of the bucketing is how the '
           'test and the screen drift apart'])
    call = call_block(APP, 'WorkflowModal')
    check('app.jsx hands the workflow modal the XP ledger',
          re.search(r'experience=\{experience\}', call),
          [call, '— without this prop the function above always sees `[]` '
           'and no step can ever read as failed'])
    check('WorkflowModal accepts it (defaulted, so an older caller still renders)',
          re.search(r'function WorkflowModal\(\{[^}]*\bexperience\s*=\s*\[\][^}]*\}\)', COLLAB),
          'modals/collab.jsx')

    # ── 2. the bucketing, run for real ───────────────────────────────────
    R = node(is_parked_src + '\n' + xp_last_src + '\n' + bits_src + r'''
const T = (id, status, extra) => Object.assign({ id, title: id, status }, extra || {});
const WF = (steps) => ({ id: 'wf1', name: 'P', steps: steps.map(t => t.id) });
const snag = (taskId, at) => ({ agentId: 'a1', kind: 'task', outcome: 'snag', taskId, at });
const done = (taskId, at) => ({ agentId: 'a1', kind: 'task', outcome: 'done', taskId, at });

const out = {};

// Nothing attempted at all — the baseline the bug reported "0/2 done" for
// regardless of what had actually happened.
out.untouched = workflowStatusBits(WF([T('a','inbox'), T('b','inbox')]), [T('a','inbox'), T('b','inbox')], []);

// One finished, one never touched.
out.oneDone = workflowStatusBits(WF([T('a','done'), T('b','inbox')]), [T('a','done'), T('b','inbox')], []);

// One finished, one genuinely running (no blockedReason) — #86's own case,
// must not regress.
out.inProgress = workflowStatusBits(WF([T('a','done'), T('b','doing')]),
  [T('a','done'), T('b','doing')], []);

// One finished, one parked (doing + blockedReason) — the case
// test_a_stalled_workflow_says_so.py already covers; must not regress.
out.parked = workflowStatusBits(WF([T('a','done'), T('b','doing', { blockedReason: 'ran out of turns' })]),
  [T('a','done'), T('b','doing', { blockedReason: 'ran out of turns' })], []);

// THE FIX: a step whose run threw. Back in `inbox`, unassigned,
// blockedReason cleared — exactly the live reading above — with the
// failure recorded only in the XP ledger.
out.failed = workflowStatusBits(WF([T('a','inbox'), T('b','inbox')]),
  [T('a','inbox'), T('b','inbox')], [snag('a', 100)]);

// Two failed steps in the same pipeline.
out.twoFailed = workflowStatusBits(WF([T('a','inbox'), T('b','inbox')]),
  [T('a','inbox'), T('b','inbox')], [snag('a', 100), snag('b', 100)]);

// Retried and it worked: a later `done` entry for the same id outranks the
// old `snag` by timestamp, and the task's own status is 'done' too — must
// read as done, not failed.
out.retriedOk = workflowStatusBits(WF([T('a','done'), T('b','inbox')]),
  [T('a','done'), T('b','inbox')], [snag('a', 100), done('a', 200)]);

// Retried and it is running again right now: status flips to 'doing'
// before a new ledger entry exists. Must read as "in progress", not
// "failed" — `doing` has to win over a stale snag.
out.retrying = workflowStatusBits(WF([T('a','doing'), T('b','inbox')]),
  [T('a','doing'), T('b','inbox')], [snag('a', 100)]);

// A snag entry for a task that ISN'T a step in this workflow must not leak
// in and inflate this pipeline's count.
out.otherTasksSnagIgnored = workflowStatusBits(WF([T('a','inbox'), T('b','inbox')]),
  [T('a','inbox'), T('b','inbox')], [snag('zzz', 100)]);

// A failed step alongside one the boss deleted outright — both named,
// neither one hides the other.
out.failedAndMissing = workflowStatusBits(WF([T('a','inbox'), { id: 'gone' }]),
  [T('a','inbox')], [snag('a', 100)]);

// experience not supplied at all (the default parameter) must not throw.
out.noExperienceArg = (function(){
  try { return workflowStatusBits(WF([T('a','inbox')]), [T('a','inbox')], undefined); }
  catch (e) { return 'THREW: ' + e.message; }
})();

console.log(JSON.stringify(out));
''')
    if R is None:
        check('the workflowStatusBits harness runs', False, 'node failed')
        print()
        print('%d check(s) failed:' % (len(FAILS) or 1))
        return 1

    check('nothing attempted reads as plain 0/2, no extra clause invented',
          R['untouched'] == '0/2 done', R['untouched'])
    check('one finished, one untouched — just the fraction',
          R['oneDone'] == '1/2 done', R['oneDone'])
    check('a genuinely running step still reads "in progress" (no regression)',
          R['inProgress'] == '1/2 done · 1 in progress', R['inProgress'])
    check('a parked step still reads "stopped — needs you" (no regression)',
          R['parked'] == '1/2 done · 1 stopped — needs you', R['parked'])
    check('a step whose run threw reads "failed — needs you" — the fix',
          R['failed'] == '0/2 done · 1 failed — needs you', R['failed'])
    check('two failed steps are both counted',
          R['twoFailed'] == '0/2 done · 2 failed — needs you', R['twoFailed'])
    check('a retry that succeeded is done, not failed — the old snag does not linger',
          R['retriedOk'] == '1/2 done', R['retriedOk'])
    check('a retry in flight right now is "in progress", not "failed"',
          R['retrying'] == '0/2 done · 1 in progress', R['retrying'])
    check("another task's snag entry does not leak into this pipeline's count",
          R['otherTasksSnagIgnored'] == '0/2 done', R['otherTasksSnagIgnored'])
    check('a failed step and a removed step are both named, independently',
          R['failedAndMissing'] == '0/2 done · 1 failed — needs you · 1 removed',
          R['failedAndMissing'])
    check('experience defaults to [] rather than throwing when the prop is absent',
          R['noExperienceArg'] == '0/1 done', R['noExperienceArg'])

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
