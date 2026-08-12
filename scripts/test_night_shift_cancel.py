#!/usr/bin/env python3
""""✕ CANCEL" on a RUNNING Night Shift mission must actually stop it — serve.py.

Found live, as a direct side effect of verifying the office floor's Night
Shift board fix: scheduled a real server-side mission, watched it run
(hq-state/mission-runs.json), then clicked "✕ CANCEL" on it (the same button
shown for a merely-*scheduled*, not-yet-started mission — no distinction in
the UI, missions.jsx line ~824). The schedule disappeared from the list as
expected — but a follow-up GET /missions/scheduled showed `schedules: []`
and `running: ["<the same id>"]`. The background thread (`_night_run_one` →
night_runner.run_mission, serve.py) kept executing for the rest of its
configured duration (up to 4 hours), now with zero trace anywhere in the
UI — not the missions list, not the office floor board — silently spending
tokens on a job the boss had just told the app to stop.

Root cause: `run_mission()` (night_runner.py) has always accepted a
`should_abort` callback for exactly this purpose, but serve.py's
`_night_run_one` never passed one — so no Night Shift mission, ever, from
any UI action, could actually be aborted mid-run. `_missions_delete` only
ever touched the persisted schedule file, never the in-memory
`_night_running` dict that tracks what's actually executing.

Fix: a new `_night_abort` set. `_missions_delete` adds the id to it when the
schedule being removed is currently running; `_night_run_one` passes
`should_abort=lambda: sid in _night_abort` into `run_mission`, which already
checks that callback every 5s during its sleep between iterations
(night_runner.py's existing loop) — so an abort now lands within one 5s
slice instead of running out the full remaining duration. Both sets are
cleared for the id when the thread actually exits.

Dynamic test: imports serve.py directly and drives `_missions_delete` and
`_night_run_one` for real (same pattern as test_security_boundaries.py's
_FakeHandler), rather than static source checks — this is exactly the kind
of concurrent-state bug static regex can't catch.

Run: python3 scripts/test_night_shift_cancel.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f' — {detail}' if detail and not cond else ''))
    if not cond:
        FAILS.append(label)


class _FakeHandler:
    """Minimal stand-in exposing just what _missions_delete reads/calls:
    .path, and a stubbed _send_json that captures the payload instead of
    writing to a real socket."""


def make_handler(H, path, captured):
    obj = _FakeHandler.__new__(_FakeHandler)
    obj.path = path
    obj._send_json = lambda code, payload: captured.update({'code': code, **payload})
    return obj


def main() -> int:
    os.environ['GAP_CRON'] = '0'
    os.environ['NEWS_CRON'] = '0'
    os.environ['TOPICS_CRON'] = '0'
    os.environ.pop('SEARCH_WORKER', None)
    os.environ['CAFRESOHQ_HQ_STATE_DIR'] = tempfile.mkdtemp(prefix='night-cancel-')
    os.chdir(ROOT)
    import serve

    H = serve.Handler

    print('=== cancelling a mission that is NOT running ===')
    serve._night_running.clear()
    serve._night_abort.clear()
    resp = {}
    H._missions_delete(make_handler(H, '/missions/scheduled/sched-idle', resp))
    check('reports stopped: False for a non-running schedule', resp.get('stopped') is False, resp)
    check('nothing was added to the abort set', 'sched-idle' not in serve._night_abort)

    print('=== cancelling a mission that IS currently running ===')
    serve._night_running.clear()
    serve._night_abort.clear()
    serve._night_running['sched-live'] = True
    resp = {}
    H._missions_delete(make_handler(H, '/missions/scheduled/sched-live', resp))
    check('reports stopped: True for a running schedule', resp.get('stopped') is True, resp)
    check('the id is flagged in _night_abort so the in-flight thread notices',
          'sched-live' in serve._night_abort,
          'serve.py: _missions_delete must signal the running thread, not '
          'just delete the schedule row — otherwise the mission runs '
          'orphaned for up to 4 hours with nothing in the UI showing it')

    print('=== _night_run_one actually wires should_abort into run_mission ===')
    captured_should_abort = {}

    class _FakeNightRunner:
        NightContext = lambda *a, **kw: object()  # noqa: E731 — _night_ctx() just needs SOMETHING back

        @staticmethod
        def run_mission(ctx, sched, on_progress=None, should_abort=None):
            captured_should_abort['fn'] = should_abort
            # Simulate the real loop: poll should_abort a few times, exit fast if set.
            for _ in range(20):
                if should_abort and should_abort():
                    break
                time.sleep(0.01)
            return {'id': 'run_test', 'scheduleId': sched.get('id', ''),
                    'agentId': '', 'agentName': '', 'topic': '', 'vaultFolder': '',
                    'startedAt': 0, 'finishedAt': 0, 'iterations': 0, 'writes': [],
                    'tokensUsed': 0, 'errors': 0, 'lastError': '', 'summary': ''}

    sys.modules['night_runner'] = _FakeNightRunner
    serve._night_running.clear()
    serve._night_abort.clear()
    serve._night_running['sched-wired'] = True
    serve._night_abort.add('sched-wired')  # abort requested BEFORE the run even starts
    t0 = time.time()
    t = threading.Thread(target=serve._night_run_one, args=({'id': 'sched-wired'},))
    t.start()
    t.join(timeout=5)
    elapsed = time.time() - t0
    check('_night_run_one passed a should_abort callback through',
          captured_should_abort.get('fn') is not None,
          'serve.py: _night_run_one must call run_mission with should_abort=...')
    check('a pre-set abort flag makes the run exit almost immediately, not run the full loop',
          elapsed < 1.0,
          f'took {elapsed:.2f}s — should_abort() should have returned True on the first check')
    check('the running flag is cleared once the thread exits',
          'sched-wired' not in serve._night_running)
    check('the abort flag is cleared too (no stale entry for the next schedule reusing an id)',
          'sched-wired' not in serve._night_abort)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED: ' + ', '.join(FAILS))
        return 1
    print('night shift cancel: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
