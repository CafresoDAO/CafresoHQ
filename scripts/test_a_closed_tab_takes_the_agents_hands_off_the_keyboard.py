#!/usr/bin/env python3
"""Closing the tab (or pressing Stop) mid-run must actually stop the legacy
elevated stream — serve.py's _agent_stream_legacy.

The disconnect is only ever observable as a failed write: the server learns
the client is gone when wfile raises BrokenPipeError. _agent_stream_legacy's
write_sse dutifully returned False on that — and only the `token` branch
listened. tool_call, tool_result, error, usage and done all discarded the
return value, so on /codex/stream (render_tools=True: tool activity IS the
frame traffic between tokens) a run whose client had left kept pulling
driver events to the very end. The codex subprocess kept executing — editing
files in the workspace, burning tokens — with nobody watching, and
drv.cancel() only ran once the task finished on its own. The contract-native
POST /agent/stream next door breaks on ANY failed frame; the legacy route
regressed exactly the property the Stop button sells.

Fix: write_sse latches the dead pipe in `dead['pipe']` and the event loop
breaks at its head, so the first failed write of ANY frame type ends the
loop within one event and the finally's drv.cancel(handle) reaps the
subprocess.

Dynamic test: imports serve.py and drives the REAL _agent_stream_legacy
(same _FakeHandler pattern as test_night_shift_cancel.py) with a scripted
driver whose stream is one token followed by a storm of tool frames, against
a wfile that dies right after the first write. No network, no subprocess.

Run: python3 scripts/test_a_closed_tab_takes_the_agents_hands_off_the_keyboard.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    print(f'  {"ok  " if cond else "FAIL"}  {label}'
          + (f' — {detail}' if detail and not cond else ''))
    if not cond:
        FAILS.append(label)


class _DeadAfterFirstWrite:
    """A wfile that accepts exactly `live` writes, then reports the peer gone
    — which is how a closed tab actually presents to the server."""
    def __init__(self, live=1):
        self.live = live
        self.writes = 0

    def write(self, data):
        self.writes += 1
        if self.writes > self.live:
            raise BrokenPipeError(32, 'Broken pipe')

    def flush(self):
        pass


class _FakeHandler:
    """Just what _agent_stream_legacy touches on self."""


def make_handler(wfile):
    obj = _FakeHandler.__new__(_FakeHandler)
    obj.wfile = wfile
    obj.send_response = lambda *a, **k: None
    obj.send_header = lambda *a, **k: None
    obj.end_headers = lambda *a, **k: None
    obj._send_json = lambda *a, **k: None
    return obj


def main() -> int:
    os.environ['GAP_CRON'] = '0'
    os.environ['NEWS_CRON'] = '0'
    os.environ['TOPICS_CRON'] = '0'
    os.environ.pop('SEARCH_WORKER', None)
    os.environ['CAFRESOHQ_HQ_STATE_DIR'] = tempfile.mkdtemp(prefix='dead-tab-')
    os.chdir(ROOT)
    import serve
    from drivers.base import (Driver, TaskHandle, ev_done, ev_token,
                              ev_tool_call, ev_tool_result)

    TOOL_FRAMES = 40

    class _ScriptedDriver(Driver):
        """One token, then a long tool-only phase, then done — the shape of an
        elevated codex run doing real work between narrations."""
        MANIFEST = {'id': 'scripted-legacy', 'costHint': 'free-local'}

        def __init__(self):
            self.consumed = 0
            self.cancelled = False

        def start_task(self, task):
            return TaskHandle()

        def events(self, handle):
            script = [ev_token('on it — ')]
            for i in range(TOOL_FRAMES):
                script.append(ev_tool_call(f'c{i}', 'bash', {'cmd': f'step {i}'}))
                script.append(ev_tool_result(f'c{i}', True, f'did step {i}'))
            script.append(ev_done('all steps ran'))
            for ev in script:
                self.consumed += 1
                yield ev

        def cancel(self, handle):
            self.cancelled = True
            super().cancel(handle)

    drv = _ScriptedDriver()
    serve._drivers.DRIVERS[drv.MANIFEST['id']] = drv
    total = 1 + TOOL_FRAMES * 2 + 1

    print('=== a healthy client gets the whole stream ===')
    wfile = _DeadAfterFirstWrite(live=10**9)
    serve.Handler._agent_stream_legacy(
        make_handler(wfile), 'scripted-legacy', {}, 'Scripted',
        render_tools=True, done_sentinel=True)
    check('every scripted event was consumed', drv.consumed == total,
          f'consumed {drv.consumed} of {total}')
    check('tool frames + done summary + [DONE] all hit the wire',
          wfile.writes == total + 1, f'{wfile.writes} writes')
    check('the driver was still reaped afterwards', drv.cancelled)

    print('=== the client leaves after the first token, mid tool storm ===')
    drv = _ScriptedDriver()
    serve._drivers.DRIVERS[drv.MANIFEST['id']] = drv
    wfile = _DeadAfterFirstWrite(live=1)
    serve.Handler._agent_stream_legacy(
        make_handler(wfile), 'scripted-legacy', {}, 'Scripted',
        render_tools=True, done_sentinel=True)
    check('the loop stops pulling work within a couple of events',
          drv.consumed <= 4,
          f'consumed {drv.consumed} of {total} — the stream loop kept the '
          'agent working for a client that had already left; only token '
          'frames used to notice the dead socket')
    check('no further frames were attempted on the dead socket',
          wfile.writes <= 3, f'{wfile.writes} writes after the pipe broke')
    check('the subprocess reaper ran (finally → drv.cancel)', drv.cancelled)

    serve._drivers.DRIVERS.pop('scripted-legacy', None)
    print()
    if FAILS:
        print(f'FAILED ({len(FAILS)}): ' + '; '.join(FAILS[:6]))
        return 1
    print('PASS: a closed tab takes the agent\'s hands off the keyboard')
    return 0


if __name__ == '__main__':
    sys.exit(main())
