#!/usr/bin/env python3
"""Closing the Stand-up modal mid-run used to leave the run going invisibly.

app.jsx renders `<StandupModal open={standupOpen} .../>` UNCONDITIONALLY —
`open` only gates a `if (!open) return null` inside the component, so the
component instance never actually unmounts while the app is up. `start()`'s
per-agent loop (HQ.agentStream) and the closing HQ.ceoStream summary call
are plain async closures with no tie to React lifecycle, so clicking X /
Escape / the backdrop — all of which just flip `standupOpen` to false —
used to leave the stream running: burning API calls (up to
STANDUP_TIMEOUT_MS per stuck local model) with no UI left to show or stop
it, and reopening the modal showed a fresh render of the same instance with
no sign a run was still going in the background. Same shape as the Terminal
PTY zombie-process leak fixed earlier this session.

Fix: a `useEF` keyed on `open` that aborts (and clears) `abortRef.current`
on the open→false edge — the exact same abort path the existing STOP button
already uses, just triggered automatically by closing instead of requiring
an explicit click first.

Run: python3 scripts/test_standup_close_aborts_the_run.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURES = ROOT / 'features.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('Closing the Stand-up modal mid-run aborts the in-flight streams')

    src = FEATURES.read_text(encoding='utf-8')

    m = re.search(r"function StandupModal\(\{[^}]*\}\) \{(.*?)\n  const start = async", src, re.S)
    check('StandupModal is still present and this test is looking at the right slice', m is not None)
    head = m.group(1) if m else ''

    check('abortRef is declared before the open-edge effect (so the effect can read it)',
          re.search(r"const abortRef = useRF\(null\);", head) is not None)

    check('there is a useEF keyed on [open] (not [] — the component never truly '
          'unmounts, so an unmount-only cleanup would never fire)',
          re.search(r"useEF\(\(\) => \{.*?\}, \[open\]\);", head, re.S) is not None)

    m2 = re.search(r"useEF\(\(\) => \{(.*?)\}, \[open\]\);", head, re.S)
    body = m2.group(1) if m2 else ''
    check('the effect aborts abortRef.current specifically on the open===false edge',
          bool(re.search(r"!open", body)) and 'abortRef.current.abort()' in body)
    check('...and clears abortRef.current afterward, so a stale aborted controller '
          "isn't mistaken for a live run next time start() checks it",
          'abortRef.current = null' in body)

    anchor = 'if (!open && abortRef.current)'
    check('the effect is registered before the `if (!open) return null` early return '
          '(hooks must run unconditionally every render)',
          anchor in head and head.index(anchor) < head.index('if (!open) return null;'))

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
