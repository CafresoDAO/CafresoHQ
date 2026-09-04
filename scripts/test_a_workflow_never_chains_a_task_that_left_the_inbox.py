#!/usr/bin/env python3
"""The NEW WORKFLOW panel could mint a chain pointing at a task that no
longer exists.

`inboxTasks` (modals/collab.jsx) decides what may become a step: it must be
`status === 'inbox'` and not already claimed by another workflow. That check
ran exactly once — at the moment the boss clicked "+ ADD" — and nothing ever
re-ran it. The modal then stays open for as long as it takes to type a name
and a description, while the office behind it keeps moving:

  - a coworker picks that inbox card up and it becomes `doing`, or
  - the boss deletes it from the board.

`steps` still held the id either way, and `submit` shipped it. app.jsx's
`onSave` maps the patches onto `tasks` by id, so the patch for the vanished
step silently no-ops — and its NEIGHBOURS keep the pointers to it:

    step 1  chainTo: "<id of a task that isn't there>"
    step 3  dependsOn: ["<same ghost id>"]

app.jsx already argues, at length, why that state is unrecoverable. Its
delete handler scrubs exactly these two pointers whenever a task is removed,
because a predecessor's chain-advance "would silently find nothing and skip
the whole chain-advance block with no stalledNote and no activity row", and a
successor's dependsOn "would carry a dangling id forever … holding it in the
inbox with no way to ever become unblocked". That scrub runs at DELETE time.
Building the workflow afterwards re-creates the pointer it just removed, and
nothing scrubs a second time — this modal was the one place in the office
that could manufacture the corrupt state the rest of it works to prevent.

The already-`doing` variant is the same shape and is spelled out in the
modal's own comment on `inboxTasks`: a running step wired with `dependsOn`
was never gated by its predecessor, so it either fires the step after it
early, or the hand-off no-ops (`nextTask.status === 'inbox'` is false) with
nothing on screen saying the chain never took.

The status panel would still read "0/3 done" for either wreck.

Fix: the add-time rule is pulled out as `chainableSteps(steps, tasks)` and
re-run in two places — an effect, so the STEPS list, its count and the footer
show only what is really going to be chained (and a line names what was taken
out, rather than the list quietly shrinking), and inside `submit` itself,
because the click is what mints the pointers.

This test lifts the real `chainableSteps` AND the real `submit` body out of
modals/collab.jsx by name and runs them under Node, so what is driven is the
shipped code, not a restatement of it.

Run: python3 scripts/test_a_workflow_never_chains_a_task_that_left_the_inbox.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLLAB_PATH = ROOT / 'modals' / 'collab.jsx'
COLLAB = COLLAB_PATH.read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def _balanced(src, brace_at):
    depth = 0
    for j in range(brace_at, len(src)):
        c = src[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return j
    raise SystemExit('unterminated block in modals/collab.jsx')


def func(name):
    """`function <name>(` to its own balanced closing brace. A rename or a
    deletion is a hard stop: a locator pinned to a signature that no longer
    exists must not hand back an empty string that satisfies every check."""
    m = re.search(r'\bfunction %s\(' % re.escape(name), COLLAB)
    if not m:
        raise SystemExit('no `function %s(` in modals/collab.jsx' % name)
    return COLLAB[m.start():_balanced(COLLAB, COLLAB.index('{', m.end())) + 1]


def arrow(name):
    """`const <name> = () => {` to its own balanced closing brace."""
    m = re.search(r'\bconst %s = \(\) => \{' % re.escape(name), COLLAB)
    if not m:
        raise SystemExit('no `const %s = () => {` in modals/collab.jsx' % name)
    return COLLAB[m.start():_balanced(COLLAB, m.end() - 1) + 1] + ';'


def node(js):
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=90)
    if p.returncode != 0:
        print(p.stdout)
        print(p.stderr[-2000:], file=sys.stderr)
        return None
    return json.loads(p.stdout.strip().split('\n')[-1])


def main():
    print('a workflow never chains a task that left the inbox')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    chainable_src = func('chainableSteps')
    submit_src = arrow('submit')

    # ── 1. the wiring, statically ────────────────────────────────────────
    check('submit re-runs the rule against the live board before it builds '
          'anything',
          'chainableSteps(steps, tasks)' in submit_src,
          [submit_src, '— the click is what mints chainTo/dependsOn; a check '
           'from a render ago is not the board at click time'])
    check('...and the patches are built from the checked list, not raw `steps`',
          re.search(r'taskPatches:\s*live\.map\(', submit_src),
          submit_src)
    check('...and the workflow record itself stores the checked list',
          re.search(r'steps:\s*live\b', submit_src),
          [submit_src, '— otherwise the status panel counts a step nothing '
           'will ever run'])
    check('...and the 2-step minimum is measured on the checked list',
          re.search(r'live\.length < 2', submit_src),
          [submit_src, '— three picked and one still chainable is not a chain'])
    check('an effect re-runs the same rule so the STEPS list, its count and '
          'the footer show what will actually be chained',
          re.search(r'const live = chainableSteps\(steps, tasks\);', COLLAB),
          'modals/collab.jsx')
    check('...and what it took out is named on screen rather than the list '
          'quietly shrinking',
          'droppedSteps' in COLLAB and 'setDroppedSteps' in COLLAB,
          'modals/collab.jsx')
    check('the draft reset clears that note too, so a new workflow does not '
          'open holding the last one\'s warning',
          re.search(r'setSteps\(\[\]\);\s*setAutoDispatch\(false\);\s*setDroppedSteps\(\[\]\);',
                    COLLAB),
          'modals/collab.jsx')

    # ── 2. the rule, run for real ────────────────────────────────────────
    T = ('const T = (id, status, extra) => '
         'Object.assign({ id, title: id.toUpperCase(), status }, extra || {});\n')

    R = node(chainable_src + '\n' + T + r'''
const out = {};
const three = [T('a','inbox'), T('b','inbox'), T('c','inbox')];
out.allFine       = chainableSteps(['a','b','c'], three);
out.deleted       = chainableSteps(['a','b','c'], [T('a','inbox'), T('c','inbox')]);
out.started       = chainableSteps(['a','b','c'], [T('a','inbox'), T('b','doing'), T('c','inbox')]);
out.finished      = chainableSteps(['a','b','c'], [T('a','inbox'), T('b','done'), T('c','inbox')]);
out.claimed       = chainableSteps(['a','b','c'],
  [T('a','inbox'), T('b','inbox',{ workflowId:'wf_other' }), T('c','inbox')]);
out.orderKept     = chainableSteps(['c','a','b'], three);
out.noTasksAtAll  = chainableSteps(['a','b'], []);
out.tasksMissing  = chainableSteps(['a','b'], undefined);
out.noSteps       = chainableSteps([], three);
console.log(JSON.stringify(out));
''')
    if R is None:
        check('chainableSteps runs under node', False, 'see stderr above')
        R = {}

    check('three still-waiting steps all survive',
          R.get('allFine') == ['a', 'b', 'c'], R.get('allFine'))
    check('a step whose task was DELETED from the board is dropped',
          R.get('deleted') == ['a', 'c'], R.get('deleted'))
    check('a step a coworker already STARTED (doing) is dropped',
          R.get('started') == ['a', 'c'], R.get('started'))
    check('a step that already FINISHED is dropped',
          R.get('finished') == ['a', 'c'], R.get('finished'))
    check('a step another workflow claimed in the meantime is dropped',
          R.get('claimed') == ['a', 'c'], R.get('claimed'))
    check('the boss\'s ordering is preserved, not re-sorted into board order',
          R.get('orderKept') == ['c', 'a', 'b'], R.get('orderKept'))
    check('an empty board drops everything rather than throwing',
          R.get('noTasksAtAll') == [], R.get('noTasksAtAll'))
    check('a missing tasks list is survivable, not a crash on the CREATE click',
          R.get('tasksMissing') == [], R.get('tasksMissing'))
    check('no steps stays no steps', R.get('noSteps') == [], R.get('noSteps'))

    # ── 3. submit itself, driven end to end ──────────────────────────────
    S = node(chainable_src + '\n' + T + r'''
const runSubmit = (o) => {
  const name = o.name, desc = o.desc || '', steps = o.steps,
        tasks = o.tasks, autoDispatch = !!o.autoDispatch;
  let saved = null, closed = false;
  const HQ = { uid: (p) => p + '_test' };
  const onSave = (x) => { saved = x; };
  const onClose = () => { closed = true; };
''' + '  ' + submit_src.replace('\n', '\n  ') + r'''
  submit();
  return { saved, closed };
};

/* The whole point of the chain: every pointer a workflow files must land on
   a task that is actually on the board and actually part of this workflow. */
const audit = (r, tasks) => {
  if (!r.saved) return { saved: false };
  const ids = new Set(tasks.map(t => t.id));
  const patched = new Set(r.saved.taskPatches.map(p => p.id));
  const dangling = [];
  for (const p of r.saved.taskPatches) {
    if (!ids.has(p.id)) dangling.push('patch for absent task ' + p.id);
    if (p.chainTo && !ids.has(p.chainTo)) dangling.push(p.id + '.chainTo -> ghost ' + p.chainTo);
    if (p.chainTo && !patched.has(p.chainTo)) dangling.push(p.id + '.chainTo -> unchained ' + p.chainTo);
    for (const d of (p.dependsOn || [])) {
      if (!ids.has(d)) dangling.push(p.id + '.dependsOn -> ghost ' + d);
      if (!patched.has(d)) dangling.push(p.id + '.dependsOn -> unchained ' + d);
    }
  }
  return {
    saved: true, dangling,
    wfSteps: r.saved.workflow.steps,
    order: r.saved.taskPatches.map(p => [p.id, p.chainTo, p.dependsOn]),
  };
};

const out = {};
let tasks = [T('a','inbox'), T('b','inbox'), T('c','inbox')];
out.healthy = audit(runSubmit({ name: 'Pipeline', steps: ['a','b','c'], tasks }), tasks);

// The bug, exactly: step 2 was deleted from the board while this panel sat open.
tasks = [T('a','inbox'), T('c','inbox')];
out.deletedMid = audit(runSubmit({ name: 'Pipeline', steps: ['a','b','c'], tasks }), tasks);

// The bug's twin: step 2 was picked up by a coworker while the panel sat open.
tasks = [T('a','inbox'), T('b','doing'), T('c','inbox')];
out.startedMid = audit(runSubmit({ name: 'Pipeline', steps: ['a','b','c'], tasks }), tasks);

// Only ONE of the three is still chainable — that is not a chain, and the
// office must be left holding no workflow at all rather than a one-step one.
tasks = [T('a','inbox'), T('b','doing'), T('c','done')];
out.tooFewLeft = audit(runSubmit({ name: 'Pipeline', steps: ['a','b','c'], tasks }), tasks);

// The pre-existing guards must still hold.
tasks = [T('a','inbox'), T('b','inbox')];
out.noName = audit(runSubmit({ name: '   ', steps: ['a','b'], tasks }), tasks);
console.log(JSON.stringify(out));
''')
    if S is None:
        check('submit runs under node', False, 'see stderr above')
        S = {}

    h = S.get('healthy') or {}
    check('an untouched three-step pipeline still files all three',
          h.get('saved') and h.get('wfSteps') == ['a', 'b', 'c'], h)
    check('...with every link resolving', h.get('dangling') == [], h.get('dangling'))
    check('...chained head-to-tail in the boss\'s order',
          h.get('order') == [['a', 'b', None], ['b', 'c', ['a']], ['c', None, ['b']]],
          h.get('order'))

    for key, what in (('deletedMid', 'deleted from the board'),
                      ('startedMid', 'picked up by a coworker')):
        r = S.get(key) or {}
        check('a middle step %s never becomes a chain link' % what,
              r.get('saved') and r.get('dangling') == [],
              [r.get('dangling'), '— app.jsx maps patches by id, so the ghost '
               'patch no-ops and its neighbours keep pointing at nothing'])
        check('...and the workflow record lists only the steps that will run',
              r.get('wfSteps') == ['a', 'c'], r.get('wfSteps'))
        check('...with the survivors re-chained to each other, not left with '
              'a hole where step 2 was',
              r.get('order') == [['a', 'c', None], ['c', None, ['a']]],
              r.get('order'))

    check('one chainable step out of three files NO workflow at all',
          (S.get('tooFewLeft') or {}).get('saved') is False,
          S.get('tooFewLeft'))
    check('an unnamed workflow is still refused (pre-existing guard)',
          (S.get('noName') or {}).get('saved') is False, S.get('noName'))

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
