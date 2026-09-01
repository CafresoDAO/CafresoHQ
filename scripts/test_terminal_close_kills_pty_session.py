#!/usr/bin/env python3
"""Closing a Terminal tab ("End session") used to only tear down the
client-side WebSocket. The backend's `_PTY_SESSIONS` dict treats a
socket close as a disconnect, not a kill — `_PTY_SESSION_TTL` (300s)
keeps the PTY process alive so a dropped connection can reconnect, and
only the background `_pty_reaper` thread (every 30s) ever calls
`.terminate()`, and only once a session is past its `expires` stamp.

That grace period is correct for a real network blip, but an explicit
"End session" click has no way back to the removed tab — so the PTY
process would sit alive, doing nothing, for up to 5 extra minutes per
closed tab. Fix: a new `/terminal/kill` backend endpoint that pops the
session out of `_PTY_SESSIONS` and terminates it immediately, and a
frontend call to it from `closeSession` (views/terminal.jsx) whenever
the closed tab had a real `sessionId` (a plain hqsh/gateway tab without
one is a no-op — the request is best-effort and ignores its result).

Verified live in the browser: opened a real PTY-backed "hqsh" tab,
closed it, and watched the network panel — a
`GET /terminal/kill?session_id=<id>` fired and returned 200 OK.

Run: python3 scripts/test_terminal_close_kills_pty_session.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PTY_SERVER = ROOT / 'pty_server.py'
SERVE = ROOT / 'serve.py'
TERMINAL_JSX = ROOT / 'views' / 'terminal.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("Terminal tab close kills its PTY session instead of waiting on the reaper")

    pty_src = PTY_SERVER.read_text(encoding='utf-8')
    serve_src = SERVE.read_text(encoding='utf-8')
    term_src = TERMINAL_JSX.read_text(encoding='utf-8')

    m = re.search(r"def _terminal_kill\(self\):(.*?)\n(?=def |\Z)", pty_src, re.S)
    check('pty_server.py defines _terminal_kill(self)', m is not None)
    body = m.group(1) if m else ''

    check('it requires session_id and 400s without one',
          "session_id required" in body)
    check('it pops the session out of _PTY_SESSIONS (not just reads it) '
          'so the reaper can never double-terminate it',
          re.search(r"_PTY_SESSIONS\.pop\(session_id", body) is not None)
    check('it terminates the underlying process',
          '.terminate()' in body)
    check('it closes the session socket',
          re.search(r"sock\.close\(\)", body) is not None)
    check('missing session (already gone) still returns ok, killed: False '
          '— matches the frontend\'s best-effort/no-op semantics',
          re.search(r"\{'ok': True, 'killed': False\}", body) is not None)

    check('serve.py routes GET /terminal/kill to _terminal_kill()',
          re.search(r"/terminal/kill['\"].*?\n\s*return self\._terminal_kill\(\)",
                     serve_src, re.S) is not None
          or ("startswith('/terminal/kill')" in serve_src
              and '_terminal_kill()' in serve_src))
    check('serve.py assigns _terminal_kill from the pty_server module',
          re.search(r"_terminal_kill\s*=\s*pty_server\._terminal_kill", serve_src)
          is not None)

    check('views/terminal.jsx fires the kill request from closeSession '
          'when the closed tab had a real sessionId',
          re.search(
              r"closing\s*&&\s*closing\.sessionId\)\s*\{\s*\n\s*fetch\("
              r"[^\n]*'/terminal/kill\?session_id='", term_src) is not None)
    check('...and treats it as best-effort (swallows fetch errors, no await)',
          re.search(
              r"/terminal/kill\?session_id='[^\n]*\)\s*\n\s*\.catch\(\(\)\s*=>\s*\{\}\)",
              term_src) is not None)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
