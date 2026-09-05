#!/usr/bin/env python3
"""A retry must not race an orphaned original — the /agent/stream,
/claudecode/stream, /cafresohq/stream, /codex/stream and /terminal/stream
family's shared gap between spawning the real CLI subprocess and telling the
client "200, here it comes."

`## 386`'s sweep and the earlier dead-tab fix (see
test_a_closed_tab_takes_the_agents_hands_off_the_keyboard.py) both cover the
window AFTER `self.send_response(200)` succeeds: a broken write inside the
event loop is caught, latched, and reaches `finally: drv.cancel(handle)`.
Neither covers the window BEFORE it. `_agent_stream`, `_agent_stream_legacy`
and pty_server's `_terminal_stream` all do, in this order: start the real
subprocess (Popen — Bash/Edit/Write already live), THEN
`self.send_response(200)` / `send_header` / `end_headers`, and only THEN
enter the try/finally that reaps it. Nothing wrapped those three calls, so a
client already gone by then (claude-client.jsx's fetchStreamHead aborts a
stream whose headers don't arrive within headMs, and ALSO retries on the
resulting network fault — the same policy #384's docstring on night_runner's
llm_call cites, "keep the two in step") turned a broken pipe there into an
uncaught exception that skipped the reaper entirely: the subprocess — a real
coding agent with tool access — kept running, unread and unkilled, while the
retry started a second, fully independent one. Two live processes, one task,
each doing the real thing: not double-billed tokens, a duplicated deliverable
(two edits, two commits, whatever the model decided to do twice).

Reproduced below with a driver whose "subprocess" is a real Python child that
writes a `started:` line to a shared marker file the instant it's up and a
`finished:` line after a short sleep — standing in for a CLI run that has
already begun doing its real work by the time anyone could stop it. Round 1
simulates the client being gone (send_response raises BrokenPipeError, same
as a peer that already sent an RST); pre-fix this either killed the running
request thread with the child never reaped (checked via `poll()` staying
None past the point drv.cancel would have run) or, worse, let it run to
completion unsupervised (both `started:` and `finished:` land, exactly what
a second, independent retry run would also produce — the duplicate). Round 2
is a plain healthy call with no disconnect, confirming the fix changes
nothing about an ordinary request.

Fix: `self.send_response(200)` / `send_header` / `end_headers` in all three
functions are now inside a `try` that calls `drv.cancel(handle)` (or
`proc.kill()` for pty_server's raw Popen) and returns on
`(BrokenPipeError, ConnectionResetError)` — closing the window to
essentially nothing instead of "however long the task takes to finish on
its own." See `## 387` in docs/OFFICE_AS_INTERFACE.md.

Dynamic test: imports serve.py and pty_server.py and drives the REAL
`_agent_stream`, `_agent_stream_legacy` and `_terminal_stream` (same
_FakeHandler pattern as test_a_closed_tab_takes_the_agents_hands_off_the_keyboard.py
and test_night_shift_cancel.py) against a driver/subprocess that is a real
child process, not a mock — the marker file is the ground truth for whether
the real side effect happened once or twice. 3 repeated rounds per route
(subprocess timing, however short, is still timing).

Run: python3 scripts/test_a_client_gone_before_headers_does_not_leave_the_task_running.py
"""
from __future__ import annotations

import inspect
import io
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    print(f'  {"ok  " if cond else "FAIL"}  {label}'
          + (f' — {detail}' if detail and not cond else ''))
    if not cond:
        FAILS.append(label)


# ---------------------------------------------------------------- structural
def structural_checks(serve_src: str, pty_src: str) -> None:
    print('=== structural: headers are sent inside a guarded try ===')
    # _agent_stream and _agent_stream_legacy: the send_response/send_header/
    # end_headers trio must be wrapped in a try that cancels the handle on a
    # broken pipe, PRIOR to the existing event-loop try/finally.
    m = re.search(
        r"def _agent_stream\(self\):.*?"
        r"try:\s*\n\s*self\.send_response\(200\).*?"
        r"except \(BrokenPipeError, ConnectionResetError\):\s*\n\s*drv\.cancel\(handle\)\s*\n\s*return",
        serve_src, re.S)
    check('_agent_stream guards the header write and cancels on a broken pipe',
          bool(m))

    m = re.search(
        r"def _agent_stream_legacy\(self.*?"
        r"try:\s*\n\s*self\.send_response\(200\).*?"
        r"except \(BrokenPipeError, ConnectionResetError\):\s*\n\s*drv\.cancel\(handle\)\s*\n\s*return",
        serve_src, re.S)
    check('_agent_stream_legacy guards the header write and cancels on a broken pipe',
          bool(m))

    m = re.search(
        r"try:\s*\n\s*self\.send_response\(200\)\s*\n\s*"
        r"self\.send_header\('content-type', 'text/event-stream'\)\s*\n\s*"
        r"self\.send_header\('cache-control', 'no-store'\)\s*\n\s*"
        r"self\.end_headers\(\)\s*\n"
        r"    except \(BrokenPipeError, ConnectionResetError\):\s*\n"
        r"        try: proc\.kill\(\)",
        pty_src)
    check('_terminal_stream guards the header write and kills the subprocess on a broken pipe',
          bool(m))


# ------------------------------------------------------------------- helpers
class _FakeHandler:
    """Just what the three functions under test touch on self."""


def _make_handler(fail_headers: bool, body: bytes = b'{}', headers=None,
                  extra=None):
    obj = _FakeHandler.__new__(_FakeHandler)
    obj.headers = headers if headers is not None else {'content-length': str(len(body))}
    obj.rfile = io.BytesIO(body)
    obj.wfile = io.BytesIO()

    def _send_response(*_a, **_k):
        if fail_headers:
            raise BrokenPipeError(32, 'Broken pipe')

    obj.send_response = _send_response
    obj.send_header = lambda *a, **k: None
    obj.end_headers = lambda *a, **k: None
    obj._send_json = lambda *a, **k: None
    obj._agent_task_cwd = lambda body: None
    for k, v in (extra or {}).items():
        setattr(obj, k, v)
    return obj


_CHILD_CODE = (
    "import sys, time\n"
    "open(sys.argv[1], 'a').write('started:' + sys.argv[2] + chr(10))\n"
    "time.sleep({sleep!r})\n"
    "open(sys.argv[1], 'a').write('finished:' + sys.argv[2] + chr(10))\n"
)


def _spawn_marker_child(marker, task_id, sleep_s):
    code = _CHILD_CODE.format(sleep=sleep_s)
    return subprocess.Popen([sys.executable, '-c', code, str(marker), task_id])


def _marker_lines(marker):
    try:
        return pathlib.Path(marker).read_text().splitlines()
    except FileNotFoundError:
        return []


def main() -> int:
    os.environ['GAP_CRON'] = '0'
    os.environ['NEWS_CRON'] = '0'
    os.environ['TOPICS_CRON'] = '0'
    os.environ.pop('SEARCH_WORKER', None)
    os.environ['CAFRESOHQ_HQ_STATE_DIR'] = tempfile.mkdtemp(prefix='client-gone-')
    os.chdir(ROOT)
    import serve
    import pty_server
    from drivers.base import Driver, TaskHandle, ev_done

    serve_src = inspect.getsource(serve.Handler._agent_stream) + '\n' + \
                inspect.getsource(serve.Handler._agent_stream_legacy)
    pty_src = inspect.getsource(pty_server._terminal_stream)
    structural_checks(serve_src, pty_src)

    SLEEP_S = 0.8

    class _RealProcDriver(Driver):
        """start_task spawns a REAL child process (the marker-writer above),
        standing in for a claude/codex CLI already doing real work the
        instant Popen returns. events() is only exercised by the healthy
        round, so it just waits the child out."""
        def __init__(self, marker, task_id):
            self.MANIFEST = {'id': f'real-proc-{task_id}', 'costHint': 'free-local'}
            self.marker = marker
            self.task_id = task_id
            self.cancel_calls = 0

        def start_task(self, task):
            h = TaskHandle()
            h.proc = _spawn_marker_child(self.marker, self.task_id, SLEEP_S)
            return h

        def events(self, handle):
            while handle.proc.poll() is None:
                time.sleep(0.02)
            yield ev_done()

        def cancel(self, handle):
            self.cancel_calls += 1
            super().cancel(handle)

    print('\n=== round: client already gone before headers (x3) ===')
    for round_n in range(1, 4):
        # ---- _agent_stream_legacy ----
        marker = pathlib.Path(tempfile.mkdtemp(prefix='marker-legacy-')) / 'log.txt'
        drv = _RealProcDriver(marker, 'legacy')
        serve._drivers.DRIVERS[drv.MANIFEST['id']] = drv
        handler = _make_handler(fail_headers=True)
        raised = None
        try:
            serve.Handler._agent_stream_legacy(handler, drv.MANIFEST['id'], {}, 'Test')
        except Exception as e:
            raised = e
        check(f'[legacy r{round_n}] the call itself did not blow up on the broken pipe',
              raised is None, f'raised {raised!r}')
        check(f'[legacy r{round_n}] the reaper ran (drv.cancel called)',
              drv.cancel_calls >= 1)
        time.sleep(0.15)
        check(f'[legacy r{round_n}] the child was killed before it could finish',
              'finished:legacy' not in _marker_lines(marker),
              f'marker: {_marker_lines(marker)}')
        time.sleep(SLEEP_S)  # let a would-be survivor finish, if the fix failed
        serve._drivers.DRIVERS.pop(drv.MANIFEST['id'], None)

        # ---- _agent_stream ----
        marker2 = pathlib.Path(tempfile.mkdtemp(prefix='marker-contract-')) / 'log.txt'
        drv2 = _RealProcDriver(marker2, 'contract')
        serve._drivers.DRIVERS[drv2.MANIFEST['id']] = drv2
        body = ('{"driver": "%s", "prompt": "do the thing"}' % drv2.MANIFEST['id']).encode()
        handler2 = _make_handler(fail_headers=True, body=body)
        raised2 = None
        try:
            serve.Handler._agent_stream(handler2)
        except Exception as e:
            raised2 = e
        check(f'[contract r{round_n}] the call itself did not blow up on the broken pipe',
              raised2 is None, f'raised {raised2!r}')
        check(f'[contract r{round_n}] the reaper ran (drv.cancel called)',
              drv2.cancel_calls >= 1)
        time.sleep(0.15)
        check(f'[contract r{round_n}] the child was killed before it could finish',
              'finished:contract' not in _marker_lines(marker2),
              f'marker: {_marker_lines(marker2)}')
        time.sleep(SLEEP_S)
        serve._drivers.DRIVERS.pop(drv2.MANIFEST['id'], None)

        # ---- pty_server._terminal_stream ----
        # No driver abstraction here — _terminal_stream Popen's the resolved
        # "claude" binary directly, so the stand-in is a shebang'd script
        # (real argv, real subprocess) that ignores whatever CLI flags
        # _terminal_stream passes it and just writes the marker.
        marker3 = pathlib.Path(tempfile.mkdtemp(prefix='marker-terminal-')) / 'log.txt'
        cwd3 = tempfile.mkdtemp(prefix='terminal-cwd-')
        shim = pathlib.Path(tempfile.mkdtemp(prefix='shim-')) / 'claude_shim.py'
        shim.write_text('#!' + sys.executable + '\n'
                        + _CHILD_CODE.format(sleep=SLEEP_S).replace(
                              "sys.argv[1]", repr(str(marker3))).replace(
                              "sys.argv[2]", repr('terminal')))
        os.chmod(shim, 0o755)
        import json as _json
        body3 = _json.dumps({
            'cli': 'claude', 'cwd': cwd3,
            'messages': [{'role': 'user', 'content': 'hi'}],
        }).encode()
        handler3 = _make_handler(fail_headers=True, body=body3, extra={
            '_claudecode_resolve': lambda p=str(shim): p,
        })
        raised3 = None
        try:
            pty_server._terminal_stream(handler3)
        except Exception as e:
            raised3 = e
        check(f'[terminal r{round_n}] the call itself did not blow up on the broken pipe',
              raised3 is None, f'raised {raised3!r}')
        time.sleep(0.15)
        check(f'[terminal r{round_n}] the child was killed before it could finish',
              'finished:terminal' not in _marker_lines(marker3),
              f'marker: {_marker_lines(marker3)}')
        time.sleep(SLEEP_S)

    print('\n=== round: a plain healthy call is unaffected ===')
    marker = pathlib.Path(tempfile.mkdtemp(prefix='marker-healthy-')) / 'log.txt'
    drv = _RealProcDriver(marker, 'healthy')
    serve._drivers.DRIVERS[drv.MANIFEST['id']] = drv
    handler = _make_handler(fail_headers=False)
    serve.Handler._agent_stream_legacy(handler, drv.MANIFEST['id'], {}, 'Test')
    check('a healthy call still reaches finished (the driver actually ran)',
          'finished:healthy' in _marker_lines(marker),
          f'marker: {_marker_lines(marker)}')
    check('a healthy call still reaps at the end (cancel called once)',
          drv.cancel_calls == 1, f'called {drv.cancel_calls} times')
    serve._drivers.DRIVERS.pop(drv.MANIFEST['id'], None)

    print()
    if FAILS:
        print(f'FAILED ({len(FAILS)}): ' + '; '.join(FAILS[:8]))
        return 1
    print('PASS: a client gone before headers does not leave the task running')
    return 0


if __name__ == '__main__':
    sys.exit(main())
