#!/usr/bin/env python3
"""Calendar drew a task row for every task on the books — same shape as a
Task Board row — but wired NOTHING to it. Mission rows next to it at least
say "wraps up" or "finished"; a task row was pixel-inert: no onClick, no
role, no cursor. The one existing "go look at tasks" door (AgentInbox's
"Open task board ->") only opens the BOARD, never the one task that
prompted the click — fine with one task on the books, useless with twenty.

Third instance this session of the same bug class: a surface DRAWS an
entity but wires no working action to it (Graph's "Open note" on
unopenable nodes; Add-project accepting paths the reading door couldn't
serve; now Calendar's task rows).

Fix, three files:
  - app.jsx: `highlightTaskId` state + `goToTask(id)` (sets it, then calls
    the existing `goTo('tasks')` — deliberately NOT threaded through goTo's
    own signature, which has many other call sites).
  - views/core.jsx: CalendarView's task row gets onClick/onKeyDown/role/
    tabIndex wired to the new `onOpenTask` prop. TasksView gets an effect
    that clears the search query and forces "show completed" on whenever a
    valid highlightTaskId arrives — otherwise a stale query or an unchecked
    filter could hide the very card the click was supposed to land on.
  - features.jsx: TaskBoard expands the matching card, scrolls it into
    view, and applies a brief flash outline, then calls onConsumeHighlight
    so a later plain visit to Tasks doesn't replay the flash on a stale id.

That last piece hid a real bug, caught only by driving it live in the
browser rather than reading the diff: the flash-clear timer and the
highlight-consume call were scheduled inside the SAME effect, keyed off
`highlightTaskId`. Consuming the highlight sets `highlightTaskId` back to
null almost immediately, which reruns that effect's cleanup — and the
cleanup cancelled the flash-clear timer along with everything else. The
flash lit up once and then stayed lit forever; nothing ever turned it back
off. Splitting the flash-clear into its own effect keyed on `flashId`
(independent of `highlightTaskId`'s lifecycle) fixed it. Verified live:
outline appears immediately on click, clears a few seconds later, and does
not reappear on a plain revisit to Tasks.

Run: python3 scripts/test_calendar_task_row_opens_the_right_card.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
CORE = ROOT / 'views' / 'core.jsx'
FEATURES = ROOT / 'features.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, opener):
    i = src.index(opener)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise SystemExit('unbalanced braces lifting ' + opener)


def slice_to_next_function(src, name):
    # brace_lift's naive counter breaks on template literals like
    # `${t.status}` — they carry their own unbalanced { } — which several
    # of these components use. Slicing to the next top-level function
    # declaration is good enough for containment checks like these.
    #
    # Located by NAME. This used to take the component's entire parameter
    # list as a literal, and adding one prop to TaskBoard (#154's
    # `hiddenByStatus`) made `src.index` raise ValueError — a crash, which
    # reads as a broken test rather than a broken app, from a change that
    # broke nothing this file is about. A locator has to survive the edits
    # the code it locates is expected to receive.
    m = re.search(r'^function %s\(' % re.escape(name), src, re.M)
    if not m:
        raise SystemExit('no top-level `function %s(` in this source' % name)
    i = m.start()
    j = src.find('\nfunction ', m.end())
    return src[i:] if j == -1 else src[i:j]


def main():
    print('Calendar task rows open the right task, and the highlight '
          'flash actually turns itself off')

    app = APP.read_text(encoding='utf-8')
    core = CORE.read_text(encoding='utf-8')
    features = FEATURES.read_text(encoding='utf-8')

    # --- app.jsx: highlightTaskId + goToTask ---------------------------
    check('app.jsx declares highlightTaskId state',
          re.search(r"const \[highlightTaskId, setHighlightTaskId\] = useStateA\(null\)", app) is not None,
          'app.jsx: highlightTaskId state missing or renamed')
    check('goToTask sets the highlight then reuses the existing goTo(\'tasks\') '
          '— not a new parallel view-switch path',
          "setHighlightTaskId(taskId)" in app and "goTo('tasks')" in app,
          'app.jsx: goToTask shape changed')
    check('consumeHighlightTask clears the id (so a later visit does not replay it)',
          "setHighlightTaskId(null)" in app,
          'app.jsx: consumeHighlightTask missing')
    check('the tasks case wires the highlight + consume callback into TasksView',
          'highlightTaskId={highlightTaskId}' in app and 'onConsumeHighlight={consumeHighlightTask}' in app,
          'app.jsx: tasks render site not wired')
    check('the calendar case wires goToTask in as onOpenTask',
          'onOpenTask={goToTask}' in app,
          'app.jsx: calendar render site not wired')

    # --- views/core.jsx: CalendarView task row -------------------------
    cal_fn = slice_to_next_function(core, 'CalendarView')
    check('CalendarView accepts onOpenTask',
          'onOpenTask = null' in cal_fn.splitlines()[0], cal_fn.splitlines()[0])
    row = "className={`cal-item status-${t.status}`}"
    check('found the task row by its cal-item status marker', row in cal_fn,
          'views/core.jsx: CalendarView task row shape changed')
    row_block = cal_fn[cal_fn.index(row): cal_fn.index(row) + 500]
    check('the task row is keyboard-operable and click-wired to onOpenTask',
          "role={onOpenTask ? 'button' : undefined}" in row_block
          and 'tabIndex={onOpenTask ? 0 : undefined}' in row_block
          and 'onClick={onOpenTask ? () => onOpenTask(t.id) : undefined}' in row_block
          and "onKeyDown={onOpenTask ?" in row_block
          and "e.key === 'Enter'" in row_block and "e.key === ' '" in row_block,
          row_block)

    # --- views/core.jsx: TasksView filter-override effect --------------
    tasks_fn = slice_to_next_function(core, 'TasksView')
    # Same relaxation as TaskBoard's below, for the same reason: the fact is
    # that both props are accepted, not that nothing was ever added between
    # them.
    tasks_sig = tasks_fn.splitlines()[0]
    check('TasksView accepts highlightTaskId/onConsumeHighlight',
          'highlightTaskId = null' in tasks_sig
          and 'onConsumeHighlight = null' in tasks_sig,
          tasks_sig)
    check('TasksView clears the search query and forces "show completed" on '
          'when a valid highlighted task arrives — so the filter can never '
          'hide the very card the click was meant to land on',
          re.search(r"if \(!highlightTaskId\) return;\s*"
                     r"if \(!tasks\.some\(t => t\.id === highlightTaskId\)\) return;\s*"
                     r"setQ\(''\);\s*setShowDone\(true\);", tasks_fn) is not None,
          tasks_fn)
    check('TasksView threads highlightTaskId/onConsumeHighlight down into TaskBoard',
          'highlightTaskId={highlightTaskId}' in tasks_fn and 'onConsumeHighlight={onConsumeHighlight}' in tasks_fn,
          tasks_fn)

    # --- features.jsx: TaskBoard highlight/flash ------------------------
    tb_fn = slice_to_next_function(features, 'TaskBoard')
    # The fact, not its neighbours: both props are accepted with a default.
    # Pinning them as an adjacent pair made this a second hostage to any
    # prop added between or beside them.
    sig = tb_fn.splitlines()[0]
    check('TaskBoard accepts highlightTaskId/onConsumeHighlight',
          'highlightTaskId = null' in sig and 'onConsumeHighlight = null' in sig,
          sig)
    check('the task card carries a data-task-id for the flash effect to find',
          'data-task-id={t.id}' in tb_fn,
          'features.jsx: task card no longer carries data-task-id')

    # The actual bug: the highlight-consuming effect and the flash-clearing
    # effect MUST be two separate hooks. If a single effect both schedules
    # the flash-clear timer AND fires onConsumeHighlight, then consuming the
    # highlight (which flips highlightTaskId back to null) reruns that same
    # effect's cleanup — cancelling its own flash-clear timer before it
    # ever fires. The flash would light up once and never turn off.
    highlight_effects = re.findall(r'useEF\(\(\) => \{.*?\}, \[[^\]]*\]\);', tb_fn, re.DOTALL)
    check('TaskBoard has (at least) two separate useEF hooks touching the '
          'highlight/flash state', len(highlight_effects) >= 2,
          f'found {len(highlight_effects)} — expected the consume-effect and '
          'the flash-clear effect to be split apart')

    consume_effect = next((e for e in highlight_effects if 'onConsumeHighlight' in e), None)
    flash_effect = next((e for e in highlight_effects if 'setFlashId(null)' in e), None)
    check('found the highlight-consume effect (keyed on highlightTaskId)',
          consume_effect is not None and '[highlightTaskId]' in consume_effect,
          tb_fn)
    check('found the flash-clear effect, independently keyed on flashId',
          flash_effect is not None and '[flashId]' in flash_effect,
          tb_fn)
    check('the two effects are NOT the same hook '
          '(this is the exact bug that shipped once and was caught live)',
          consume_effect is not None and flash_effect is not None
          and consume_effect != flash_effect,
          'a single merged effect would cancel its own flash-clear timer '
          'the moment it consumes the highlight')
    check('the highlight-consume effect\'s cleanup does NOT clear the '
          "flash timer (no t1/setFlashId reference in its cleanup)",
          consume_effect is not None
          and 'return () => { cancelAnimationFrame(raf); clearTimeout(t2); };' in consume_effect,
          consume_effect)
    check('the flash-clear effect actually clears flashId after a delay',
          flash_effect is not None
          and 'setTimeout(() => setFlashId(null), 2600)' in flash_effect,
          flash_effect)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
