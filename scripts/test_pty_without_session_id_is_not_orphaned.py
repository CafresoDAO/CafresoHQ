#!/usr/bin/env python3
"""A PTY opened WITHOUT a session_id must not outlive its WebSocket.

pty_server.py's `_terminal_pty_ws` only registers a session in
`_PTY_SESSIONS` when the client supplied a `session_id` query param —
and views/terminal.jsx really does omit it for some tabs
(`...(sessionId ? { session_id: sessionId } : {})`). When such a
connection drops, `ws_to_pty` takes the soft-detach path (socket set to
None, `expires` stamped) exactly like a reconnectable session. But an
unregistered session is invisible to every cleanup mechanism:

  - the `_pty_reaper` thread only iterates `_PTY_SESSIONS`,
  - `/terminal/kill` looks sessions up by session_id,
  - and no client can ever reconnect (there is no id to resume with).

So the spawned CLI process — a real shell-grade process — kept running
FOREVER after the socket closed: one permanently orphaned process (plus
its PTY reader thread and master fd) per session-id-less connection.

Fix: after `t_in.join()` (the WS is gone for good at that point), if
`session_id` is empty and the PTY hasn't already exited on its own,
set the session's stop event and terminate the process — same
pty_proc/proc terminate pattern `_terminal_kill` and the reaper use.

This test is DYNAMIC: it imports the real pty_server, drives
`_terminal_pty_ws` over a real socketpair (fake handler, real WebSocket
handshake bytes, real close frame), with the CLI resolver pointed at a
long-sleeping stub script, and then asserts the spawned process is
actually dead once the handler returns.

Run: python3 scripts/test_pty_without_session_id_is_not_orphaned.py
"""
import base64
import os
import socket
import stat
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('A PTY session opened without a session_id dies with its WebSocket')

    if sys.platform == 'win32':
        print('  ok    (skipped on Windows — POSIX pty path only)')
        return 0

    import pty_server
    pty_server._client_path = lambda p: p

    # Wrap subprocess.Popen (via the module's own name binding) to capture
    # the spawned PTY child without touching the real subprocess module.
    real_subprocess = pty_server.subprocess
    spawned = []

    class _SubprocShim:
        def __getattr__(self, name):
            return getattr(real_subprocess, name)

        def Popen(self, *a, **k):
            p = real_subprocess.Popen(*a, **k)
            spawned.append(p)
            return p

    pty_server.subprocess = _SubprocShim()

    tmpdir = tempfile.mkdtemp(prefix='pty_orphan_test_')
    cli_stub = os.path.join(tmpdir, 'fake_claude.sh')
    with open(cli_stub, 'w') as f:
        f.write('#!/bin/sh\nexec sleep 300\n')
    os.chmod(cli_stub, os.stat(cli_stub).st_mode | stat.S_IXUSR)

    class FakeHandler:
        _WS_GUID = '258EAFA5-E914-47DA-95CA-C11D0C1A2649'

        def __init__(self, conn, path):
            self.connection = conn
            self.wfile = conn.makefile('wb')
            self.path = path
            self.headers = {
                'Sec-WebSocket-Key': base64.b64encode(os.urandom(16)).decode(),
            }
            self.close_connection = False
            self.refusals = []

        def _app_origins(self):
            return []

        def _rebind_host_gate(self):
            # `## 320.` put the whole /terminal family behind the DNS-rebinding
            # Host gate, and _terminal_pty_ws calls it directly. This stub owes
            # the same helper surface as _app_origins above; True is what the
            # real gate returns for these requests anyway, since this harness
            # sends no Host header at all and an absent Host passes. No
            # assertion in this file changes -- it is about session bookkeeping,
            # not about who may connect.
            return True

        def _send_json(self, code, obj):
            self.refusals.append((code, obj))

        def send_error(self, code, msg=''):
            self.refusals.append((code, msg))

        def _claudecode_resolve(self):
            return cli_stub

        def _codex_resolve(self):
            return None

        def _hermes_resolve(self):
            return None

        def _gemini_resolve(self):
            return None

    client_side, server_side = socket.socketpair()
    # NOTE: no session_id in this URL — that is the whole point.
    path = ('/terminal/pty?cli=claude&cols=80&rows=24'
            '&cwd=' + urllib.parse.quote(tmpdir)
            + '&nonce=' + pty_server._PTY_NONCE)
    handler = FakeHandler(server_side, path)

    t = threading.Thread(target=pty_server._terminal_pty_ws,
                         args=(handler,), daemon=True)
    t.start()

    try:
        # Real handshake bytes come back over the socketpair.
        client_side.settimeout(5)
        resp = client_side.recv(4096)
        check('WebSocket handshake completed (101 Switching Protocols)',
              resp.startswith(b'HTTP/1.1 101'),
              resp[:60] or handler.refusals)

        # Client closes: one WS close frame (0x8), then the socket itself.
        client_side.sendall(bytes([0x88, 0x00]))
        client_side.close()

        t.join(timeout=15)
        check('handler returned after the WebSocket closed', not t.is_alive())

        check('exactly one PTY child was spawned', len(spawned) == 1,
              f'{len(spawned)} spawned; refusals={handler.refusals}')

        proc = spawned[0] if spawned else None
        dead = False
        if proc is not None:
            deadline = time.time() + 3
            while time.time() < deadline:
                if proc.poll() is not None:
                    dead = True
                    break
                time.sleep(0.05)
        check('the spawned CLI process is dead once the WS is gone '
              '(no session_id → nothing can ever reconnect or reap it)',
              dead,
              'process still running — orphaned forever '
              f'(pid {proc.pid if proc else "?"})')
    finally:
        for p in spawned:
            try:
                if p.poll() is None:
                    p.kill()
                p.wait(timeout=5)
            except Exception:
                pass
        pty_server.subprocess = real_subprocess
        try:
            server_side.close()
        except OSError:
            pass
        try:
            os.unlink(cli_stub)
            os.rmdir(tmpdir)
        except OSError:
            pass

    # And the control: a session WITH a session_id must keep its soft-detach
    # reconnect grace — the fix must be scoped to the unregistered case.
    src = (ROOT / 'pty_server.py').read_text(encoding='utf-8')
    check('the kill is scoped to sessions without a session_id '
          '(registered sessions keep the reconnect grace period)',
          "if not session_id and not sess['stop'].is_set():" in src)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
