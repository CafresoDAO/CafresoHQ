#!/usr/bin/env python3
"""Double-clicking a toast's ✕ silently evicted a still-visible one.

`ToastProvider.dismiss(id)` (ui/feedback.jsx) had no guard against being
called twice for the same toast, and nothing stops it from being called
twice: the ✕ button never disables itself during the 220ms exit
animation — `.is-leaving` is CSS-only, no `pointer-events: none` — so a
double-click (or a click racing the toast's own auto-dismiss timer firing
at nearly the same moment) calls `dismiss()` twice for the same id before
either's delayed `setTimeout` has fired.

Both calls used to schedule their own independent `setTimeout`, and BOTH
unconditionally did `queueRef.current.shift()` — one user action (one
click, however doubled) drained TWO toasts off the pending queue instead
of one. The second dequeue's `[...stack, queued].slice(-TOAST_VISIBLE_MAX)`
then evicts whichever toast is oldest in the visible stack — which can be
a toast the user never touched, that was never auto-dismissed, and whose
own timer is still running. It vanishes from the screen with no
dismissal of its own: a silent loss on a surface whose entire job is to
be a reliable record of "something happened".

Fix: a `dismissingRef` Set guards re-entry — a second `dismiss(id)` call
for an id already mid-exit is a no-op, so exactly one queue slot is
consumed per toast that is actually dismissed once.

This test reimplements `dismiss`'s actual logic with minimal useState/
useRef stand-ins (real React hooks can't run outside a component tree
under plain Node) so the extracted code is genuinely executed, not just
pattern-matched.

Run: python3 scripts/test_toast_dismiss_double_click_does_not_evict_a_live_toast.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEEDBACK = ROOT / 'ui' / 'feedback.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, header):
    i = src.index(header)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '(':
            depth += 1
        elif src[j] == ')':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise ValueError('unbalanced parens for ' + header)


def main():
    print("double-clicking a toast's close button does not evict a live toast")
    src = FEEDBACK.read_text(encoding='utf-8')

    check("dismissingRef is declared alongside stack/queue/timers refs",
          re.search(r"const dismissingRef = useRef\(new Set\(\)\)", src) is not None)

    dismiss_src = brace_lift(src, 'React.useCallback((id) => {')
    check("dismiss() bails out early if this id is already mid-dismissal — "
          "the actual fix: without it, a second call before the 220ms exit "
          "timer fires schedules a SECOND setTimeout for the same toast",
          bool(re.search(r"if \(dismissingRef\.current\.has\(id\)\) return;", dismiss_src)))
    check("...and marks the id as dismissing before doing anything else, so "
          "a synchronous re-entrant call sees it immediately",
          bool(re.search(
              r"if \(dismissingRef\.current\.has\(id\)\) return;\s*\n\s*"
              r"dismissingRef\.current\.add\(id\);", dismiss_src)))
    check("...and clears it again once the exit animation actually completes, "
          "so the SAME toast id can be dismissed again on a future toast reuse",
          bool(re.search(r"dismissingRef\.current\.delete\(id\)", dismiss_src)))

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted dismiss())',
          has_node, 'skipping the live-execution check')
    if not has_node:
        print()
        if FAILS:
            print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
            return 1
        print('all checks passed')
        return 0

    js = f"""
    // Minimal useState/useRef stand-ins — enough for `dismiss` to run for
    // real, not a full React runtime. `dismiss` never reads `stack` (a
    // stale-closure concern doesn't apply here), only writes it via the
    // setter, so a bare {{current: []}}-style holder is sufficient.
    let _stack = [];
    const setStack = (updater) => {{ _stack = updater(_stack); }};
    const useRef = (init) => ({{ current: init }});
    const React = {{ useCallback: (fn) => fn }};
    const timersRef = useRef(new Map());
    const dismissingRef = useRef(new Set());
    const queueRef = useRef([{{id:'D', kind:'info'}}, {{id:'E', kind:'info'}}]);
    const TOAST_VISIBLE_MAX = 3;
    let scheduleAutoDismissCalls = [];
    const scheduleAutoDismiss = (t) => {{ scheduleAutoDismissCalls.push(t.id); }};
    const playToastBlip = () => {{}};

    const dismiss = {dismiss_src};

    _stack = [{{id:'A', kind:'info'}}, {{id:'B', kind:'info'}}, {{id:'C', kind:'info'}}];

    // The double-click: both calls happen synchronously, well inside the
    // 220ms exit window, before either's setTimeout has fired.
    dismiss('A');
    dismiss('A');

    setTimeout(() => {{
      const ids = _stack.map(t => t.id);
      const remainingQueue = queueRef.current.slice();
      console.log(JSON.stringify({{ ids, remainingQueue, scheduleAutoDismissCalls }}));
    }}, 260);
    """
    r = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=10)
    check('the extracted dismiss() ran without a Node error',
          r.returncode == 0, (r.stderr or '').strip()[-800:])
    if r.returncode == 0:
        out = json.loads(r.stdout.strip().splitlines()[-1])
        check('exactly one toast (A) was actually dismissed and exactly one '
              'queued toast (D) took its place — this is the regression: a '
              'double-click used to dequeue BOTH D and E for one dismissal',
              out['ids'] == ['B', 'C', 'D'], out)
        check("B — a toast the user never touched, never auto-dismissed — "
              "is still on screen. Before the fix, the second dismiss() call's "
              "own queue-pull evicted it via slice(-3) even though it was "
              "never the oldest logical entry to go",
              'B' in out['ids'], out)
        check('the queue still holds E, not drained twice by one click',
              out['remainingQueue'] == [{'id': 'E', 'kind': 'info'}], out)
        check('exactly one auto-dismiss timer was armed for the dequeued toast',
              out['scheduleAutoDismissCalls'] == ['D'], out)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
