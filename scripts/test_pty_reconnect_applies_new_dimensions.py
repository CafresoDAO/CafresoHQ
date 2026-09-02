#!/usr/bin/env python3
"""Resuming a Terminal PTY session on a differently-sized window never
resized the actual child process.

pty_server.py's WS handler parses `cols`/`rows` fresh from the query
string on every connection (before the "Session resume or new spawn"
branch). When `session_id` matches a still-alive session, it takes the
RECONNECT path: it swaps in the new socket and replays buffered output,
but it never applied those freshly-parsed `cols`/`rows` to the PTY's
kernel-level window size. Those values were silently discarded — the
child process (vim, htop, claude/codex CLI, any TUI) kept whatever
size it was spawned with.

The only other place that ever resizes an existing PTY is the
`{"type":"resize"}` message handler — and the frontend
(views/terminal.jsx) only sends that message from a `ResizeObserver`/
`window resize` listener, reacting to a NEW resize event. It never
sends one on reconnect/resume itself. So: open a PTY tab, resize the
browser window, then let the connection drop and come back (a
background-tab reconnect via `visibilitychange`, or the retry-backoff
path) before the window is resized again — the new connection
recomputes `cols`/`rows` correctly and xterm.js redraws at the new
pixel size, but the underlying process never receives SIGWINCH/
TIOCSWINSZ for it, so output wraps at the wrong column and TUI redraws
garble until the user happens to trigger another browser resize.

Found by a background hunt agent sweeping previously-unswept areas
(terminal/PTY session edge cases — resize, reconnect).

Fix: the reconnect branch now applies the newly-parsed `cols`/`rows` to
the already-running PTY immediately after taking over the socket —
`pty_proc.setwinsize(rows, cols)` on Windows (winpty), or
`fcntl.ioctl(master_fd, termios.TIOCSWINSZ, ...)` on POSIX — mirroring
exactly what the `resize` message handler already does for a live
session, just applied once up front on resume too.

pty_server.py is a raw WebSocket-handling module with side effects at
import (spawns real PTYs) — like this repo's other PTY tests, this
checks the fix's shape directly in source rather than exercising a
live socket.

Run: python3 scripts/test_pty_reconnect_applies_new_dimensions.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PTY_SERVER = ROOT / 'pty_server.py'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("Reconnecting a Terminal PTY session applies the new connection's dimensions")

    src = PTY_SERVER.read_text(encoding='utf-8')

    m = re.search(
        r"if sess is not None and not sess\['stop'\]\.is_set\(\):\n"
        r"(.*?)\n"
        r"        # Replay buffered output collected while the client was away\.",
        src, re.S)
    check("found the reconnect branch (up to the buffered-output replay)",
          m is not None)
    branch = m.group(1) if m else ''

    check("the reconnect branch applies the newly-parsed rows/cols on "
          "Windows via pty_proc.setwinsize(...)",
          re.search(r"sess\['pty_proc'\]\.setwinsize\(rows,\s*cols\)", branch)
          is not None)
    check("the reconnect branch applies them on POSIX via "
          "fcntl.ioctl(..., TIOCSWINSZ, ...) against the session's own "
          "master_fd",
          re.search(r"fcntl\.ioctl\(sess\['master_fd'\],\s*_termios4\.TIOCSWINSZ",
                     branch) is not None)
    check("the ioctl path packs the SAME rows/cols this connection just "
          "parsed (not stale values from the original spawn)",
          re.search(r"struct\.pack\('HHHH',\s*rows,\s*cols,\s*0,\s*0\)", branch)
          is not None)
    check("both resize paths are guarded against failure (a session mid- "
          "teardown, or an OS-level ioctl error, must not crash the "
          "reconnect) — wrapped in try/except",
          re.search(r"try:\s*\n\s*if _is_win:\s*\n\s*sess\['pty_proc'\]\.setwinsize",
                     branch) is not None
          and 'except Exception:' in branch)

    # Confirm this is genuinely the SAME mechanism the live resize-message
    # handler already uses elsewhere (not a look-alike that quietly does
    # something different) — same ioctl request, same struct format.
    resize_handler = re.search(
        r"if isinstance\(msg, dict\) and msg\.get\('type'\) == 'resize':.*?"
        r"_fcntl2\.ioctl\(sess\['master_fd'\],\s*_termios2\.TIOCSWINSZ,\s*\n"
        r"\s*_struct3\.pack\('HHHH',\s*r,\s*c,\s*0,\s*0\)\)",
        src, re.S)
    check("the live resize-message handler (for comparison) uses the "
          "identical ioctl request/struct shape — confirming the "
          "reconnect fix mirrors real, working logic rather than "
          "inventing a new path",
          resize_handler is not None)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
