#!/usr/bin/env python3
"""A panel that refuses has to say what it is refusing on.

The NEW WORKFLOW modal offers "AVAILABLE TASKS" and lists what a workflow
could chain. Its filter excludes on three separate grounds:

    tasks.filter(t => t.status === 'inbox' && !t.workflowId && !steps.includes(t.id))

  1. the task has started, or finished
  2. another workflow already claims it
  3. it is already a step in the workflow being built

All three collapsed into one sentence — "No inbox tasks available." — over a
footer reading "Add at least 2 tasks to create a workflow."

Reproduced 2026-09-03 on a real office (127.0.0.1:8898) holding exactly one
task, `tk_fbevo`, status `done`. The Calendar showed it. The board showed it.
This panel said there were none and asked for two more. A boss who obeys that
instruction adds two tasks and delegates them — which is the next thing the
office invites — and lands back on the same sentence, because `doing` is not
`inbox` either and nothing here ever said so.

This is the tracked shape "a surface answers a question it was not asked"
(#155, #157, #159) with #158's second half attached: the sentence pointed at
the board and the modal had no door to it. On a phone that is not a detail —
the mobile Tools drawer opens this modal and carries no Tasks entry at all.

What this holds:

  1. the empty state names WHICH exclusion emptied the list, and counts it
  2. "you have none" and "you have some, none of them chainable" are never
     the same sentence
  3. the footer only asks for more tasks when more tasks would help — it is
     driven by `steps.length + inboxTasks.length`, the number of steps
     actually reachable from this panel, not by a bare `steps.length < 2`
  4. there is a way out of the panel to the board it is talking about

`inboxTasks`, `startable`, `emptyNote` and the footer expression are lifted
out of modals/collab.jsx and executed under Node, so this drives the real
branch logic rather than a description of it.

Run: python3 scripts/test_the_workflow_panel_says_why_the_list_is_empty.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLLAB = ROOT / 'modals' / 'collab.jsx'
APP = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def component(src, name):
    """`function <Name>(` to the next top-level `\\nfunction `. Located by
    NAME: a locator pinned to a signature or a body fragment reports a
    rename as a regression and hands back an empty slice that satisfies any
    check phrased as a negative (#159)."""
    m = re.search(r'^function %s\(' % re.escape(name), src, re.M)
    if not m:
        raise SystemExit('no `function %s(` in modals/collab.jsx' % name)
    nxt = src.find('\nfunction ', m.end())
    return src[m.start():nxt if nxt != -1 else len(src)]


def lift(src, name, where):
    """One `const <name> = …;` to its depth-0 semicolon, counting all three
    bracket kinds — these bodies hold arrow functions, IIFEs and template
    literals."""
    m = re.search(r'\bconst %s = ' % re.escape(name), src)
    if not m:
        raise SystemExit('no `const %s = ` in %s' % (name, where))
    depth = 0
    for j in range(m.start(), len(src)):
        c = src[j]
        if c in '({[':
            depth += 1
        elif c in ')}]':
            depth -= 1
        elif c == ';' and depth == 0:
            return src[m.start():j + 1]
    raise SystemExit('unterminated `const %s`' % name)


def braced_child(src, anchor):
    """The brace-balanced `{…}` expression that follows `anchor`. Used for
    the footer hint, which is a bare JSX child rather than an attribute."""
    i = src.find(anchor)
    if i == -1:
        raise SystemExit('no %r in the component' % anchor)
    start = src.find('{', src.find('>', i))
    while src.startswith('{/*', start):   # skip a leading JSX comment block
        start = src.find('{', src.find('*/}', start) + 3)
    depth = 0
    for j in range(start, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[start + 1:j]
    raise SystemExit('unbalanced footer hint expression')


def T(tid, status='inbox', wf=None):
    t = {'id': tid, 'status': status, 'title': tid}
    if wf:
        t['workflowId'] = wf
    return t


def main():
    print('The workflow panel says why the list is empty')

    src = COLLAB.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')
    wf = component(src, 'WorkflowModal')
    check('the WorkflowModal component is findable', bool(wf.strip()),
          'every check below it would run against an empty slice')

    inbox_tasks = lift(wf, 'inboxTasks', 'WorkflowModal')
    startable = lift(wf, 'startable', 'WorkflowModal')
    empty_note = lift(wf, 'emptyNote', 'WorkflowModal')
    footer = braced_child(wf, 'className="hint"')

    # --- §1: the branches, driven ---------------------------------------
    harness = '\n'.join([
        'const OUT = [];',
        'for (const [label, tasks, steps] of CASES) {',
        '  ' + inbox_tasks,
        '  ' + startable,
        '  ' + empty_note,
        '  const footer = (%s);' % footer.strip(),
        '  OUT.push([label, emptyNote, footer, inboxTasks.length]);',
        '}',
        'console.log(JSON.stringify(OUT));',
    ])

    # (label, tasks, steps, expected emptyNote, expected footer)
    NEEDS_TWO = 'A workflow needs 2 tasks that have not started yet.'
    CASES = [
        ('a brand-new office with nothing on the board',
         [], [],
         'You have no tasks yet. A workflow chains tasks that have not started.',
         NEEDS_TWO),

        # The measured case. This is the one that read "No inbox tasks
        # available." over "Add at least 2 tasks to create a workflow."
        ('the measured case: one task, already done',
         [T('a', 'done')], [],
         'You have 1 task, but 1 already underway or finished. '
         'A workflow chains tasks that have not started.',
         NEEDS_TWO),

        # And the trap that instruction set: obey it, delegate them, come
        # back. `doing` is not `inbox`. The old copy was identical here.
        ('...and the trap it set — two more tasks, both now running',
         [T('a', 'done'), T('b', 'doing'), T('c', 'doing')], [],
         'You have 3 tasks, but 3 already underway or finished. '
         'A workflow chains tasks that have not started.',
         NEEDS_TWO),

        ('every task is claimed by another workflow — a different reason, '
         'and it says so',
         [T('a', 'inbox', 'wf1'), T('b', 'inbox', 'wf1')], [],
         'You have 2 tasks, but 2 already in another workflow. '
         'A workflow chains tasks that have not started.',
         NEEDS_TWO),

        # Verified live after creating a workflow over two tasks: both
        # exclusions in one office, both named.
        ('both reasons at once, both counted',
         [T('a', 'done'), T('b', 'inbox', 'wf1'), T('c', 'inbox', 'wf1')], [],
         'You have 3 tasks, but 1 already underway or finished and 2 already '
         'in another workflow. A workflow chains tasks that have not started.',
         NEEDS_TWO),

        ('one chainable task and nothing added yet — the list is not empty, '
         'and the footer does not pretend two are reachable',
         [T('a'), T('b', 'done')], [],
         None, NEEDS_TWO),

        ('two chainable tasks — now asking for two is fair',
         [T('a'), T('b')], [],
         None, 'Add 2 more tasks — a workflow needs 2 steps.'),

        ('one added, one still on the list',
         [T('a'), T('b')], ['a'],
         None, 'Add 1 more task — a workflow needs 2 steps.'),

        # The third exclusion, and the one the boss caused: the list is empty
        # because they emptied it. Nothing to go fetch.
        ('one added and nothing else chainable — the list is empty because '
         'it was used, not because the board is',
         [T('a'), T('b', 'done')], ['a'],
         'Every task that could be chained is already a step above.',
         NEEDS_TWO),

        ('both added — ready',
         [T('a'), T('b')], ['a', 'b'],
         'Every task that could be chained is already a step above.',
         '2 steps ready.'),
    ]

    harness = 'const CASES = %s;\n' % json.dumps(
        [[c[0], c[1], c[2]] for c in CASES]) + harness

    proc = subprocess.run(['node', '--input-type=module', '-e', harness],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr.strip()[:2000])
        raise SystemExit('the lifted branch logic did not run under node')
    got = json.loads(proc.stdout.strip().splitlines()[-1])

    for case, (_l, note, foot, n) in zip(CASES, got):
        label, _tasks, _steps, want_note, want_foot = case
        check('%s — the sentence' % label[:60], note == want_note,
              'got %r, expected %r' % (note, want_note))
        check('%s — the footer' % label[:60], foot == want_foot,
              'got %r, expected %r' % (foot, want_foot))

    # --- §2: the rules, over every case ---------------------------------
    # These are the properties the copy exists for. A future rewrite is free
    # to change the wording; it is not free to break these.
    for case, (_l, note, foot, n) in zip(CASES, got):
        label = case[0][:44]
        empty = n == 0
        check('%s — a sentence appears exactly when the list is empty' % label,
              bool(note) == empty,
              'list has %d, note is %r' % (n, note))
        if note:
            check('%s — the sentence distinguishes "none" from "none usable"'
                  % label,
                  ('no tasks yet' in note) == (len(case[1]) == 0),
                  'the office holds %d tasks and the sentence is %r'
                  % (len(case[1]), note))
        # The old footer's failure: asking for tasks that would not help.
        reachable = len(case[2]) + n
        check('%s — the footer only asks for more tasks when more tasks '
              'would help' % label,
              ('more task' in foot) == (2 > len(case[2]) and reachable >= 2),
              'footer %r with %d steps and %d on the list'
              % (foot, len(case[2]), n))

    # No two distinct situations may share a sentence, which is the whole
    # defect: "you have none", "you have some but they've started", "they're
    # claimed", and "you already used them" were one string.
    notes = [g[1] for g in got if g[1]]
    check('every reason gets its own sentence',
          len(set(notes)) == len({
              c[3] for c in CASES if c[3]}),
          'collapsed: %r' % (sorted(set(notes)),))

    # --- §2b: the surface renders what §1 just drove ---------------------
    # Without this, every case above holds against a `const emptyNote` that
    # nothing reads, while the panel still prints one fixed sentence. A break
    # that reverted only the render passed the whole file before this landed.
    block = re.search(r'\{emptyNote && \(([\s\S]*?)\n\s*\)\}', wf)
    check('the empty state is gated on the computed sentence',
          block is not None,
          'modals/collab.jsx: nothing in WorkflowModal renders `emptyNote` — '
          'the branch logic above is dead code')
    if block:
        check('...and prints it, rather than a fixed string beside it',
              '{emptyNote}' in block.group(1),
              'the block renders %r' % block.group(1)[:160])
    check('the one-sentence-for-everything string is gone',
          'No inbox tasks available' not in wf,
          'modals/collab.jsx: the flat empty state is still in the component')

    # --- §3: the door ----------------------------------------------------
    check('the empty state offers a way to the board it is talking about',
          'onOpenBoard' in wf,
          'modals/collab.jsx: the sentence points at the task board and the '
          'modal has no control that reaches it — #158\'s shape')
    check('...and it is only rendered when the caller supplied one',
          re.search(r'onOpenBoard && \(', wf) is not None,
          'an unguarded callback renders a dead link in any other caller')
    check('...and the call site supplies it, closing the modal on the way',
          re.search(r'onOpenBoard=\{\(\) => \{[^}]*setWorkflowOpen\(false\)'
                    r'[^}]*navTo\(\'tasks\'\)', app) is not None,
          'app.jsx: WorkflowModal is rendered without onOpenBoard, or the '
          'door leaves the modal covering the board it just opened')

    # The premise. The drawer that opens this modal has no Tasks entry, which
    # is why the door matters more on a phone than on the desktop.
    office = (ROOT / 'ui' / 'office.jsx').read_text(encoding='utf-8')
    drawer = re.search(r'const toolItems = \[[\s\S]*?\n  \];', office)
    check('the mobile tool drawer still has no Tasks entry — the reason this '
          'modal needs its own door',
          drawer is not None and "'Tasks'" not in drawer.group(0),
          'ui/office.jsx: Tasks reached the drawer; the door here is now a '
          'convenience rather than the only route, which is fine — this '
          'check is a note, not a requirement')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
