#!/usr/bin/env python3
"""EmbeddedTerminal's connect() must not open two PTY sockets for one session
(views/terminal.jsx).

Bug: connect() is async. Its only re-entrancy guard was the readyState check
(`rs === OPEN || rs === CONNECTING`) — but that runs BEFORE the
`await fetch('/terminal/nonce')`, and wsRef only becomes CONNECTING after the
`new WebSocket(...)` that follows the await. So during the nonce round-trip
the guard sees the OLD, closed socket and lets a second invocation through.
The onclose retry timer and the visibilitychange handler are independent
triggers of connect(), so this overlap is a normal event, not a corner case:
service blips, a retry is scheduled, the user tabs away and back, and both
paths run connect() concurrently.

Both then open a WebSocket to /terminal/pty with the SAME session_id.
pty_server.py's resume path (`sess['sock'] = client_sock`) hands the PTY to
whichever socket attaches last, while wsRef keeps whichever connect() resumed
last — the fetch completions can order either way. When they disagree,
keystrokes ride the orphan socket and output rides the live one, and after
the next drop the client refuses to reconnect at all because the orphan
still reads OPEN: a silently frozen terminal that only a full tab switch
tears down.

Fix: a synchronous `connecting` flag inside the mount effect — set before
the awaited nonce fetch, cleared once `wsRef.current = ws` makes the
readyState guard authoritative again (and on the cancelled early-return).
Because the flag is flipped synchronously before the first await, a second
connect() invoked during the gap bails at the top.

This lifts the REAL EmbeddedTerminal source out of views/terminal.jsx
(brace-balanced extraction) and checks the invariant's structure directly:
the guard exists, engages before the awaited fetch, and hands back to the
readyState guard only once the new socket is in wsRef.
Run: python3 scripts/test_terminal_reconnect_no_double_socket.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'views' / 'terminal.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def extract_braced(src, head_re):
    """Brace-balanced extraction from the first match of head_re (which must
    end at an opening '{') to its matching close — same technique as
    test_workspace_terminal_key.py."""
    m = re.search(head_re, src)
    if not m:
        return None
    depth = 0
    j = m.end() - 1  # the opening '{'
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
        j += 1
    return None


def main():
    print('EmbeddedTerminal — connect() single-socket re-entrancy guard')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    text = SRC.read_text(encoding='utf-8')

    body = extract_braced(text, r'function\s+EmbeddedTerminal\s*\([^)]*\)\s*\{')
    check('EmbeddedTerminal extracted from views/terminal.jsx', body is not None)
    if body is None:
        print('\n1 failure(s)')
        return 1

    connect = extract_braced(body, r'const\s+connect\s*=\s*async\s*\(\)\s*=>\s*\{')
    check('connect() arrow extracted from EmbeddedTerminal', connect is not None)
    if connect is None:
        print('\n1 failure(s)')
        return 1

    # 1. A synchronous in-flight flag is declared in the effect scope, before
    #    connect() itself — a state/ref would be async or shared-across-mounts;
    #    the flag must be a plain `let` local to the mount effect closure.
    decl = re.search(r'let\s+connecting\s*=\s*false', body)
    check('`let connecting = false` declared in the effect scope',
          decl is not None and decl.start() < body.index('const connect'))

    # 2. connect() bails when the flag is up — and that guard is the FIRST
    #    statement territory, before any await can widen the window.
    guard = re.search(r'if\s*\(\s*cancelled\s*\|\|\s*connecting\s*\)\s*return', connect)
    first_await = re.search(r'\bawait\b', connect)
    check('connect() early-returns on `cancelled || connecting`', guard is not None)
    check('the connecting guard precedes the first await in connect()',
          guard is not None and first_await is not None and guard.start() < first_await.start())

    # 3. The flag is RAISED synchronously before the awaited nonce fetch —
    #    raising it after the await would leave the exact same race window.
    raise_m = re.search(r'connecting\s*=\s*true', connect)
    nonce_await = re.search(r'await\s+fetch\([^;]*terminal/nonce', connect)
    check('`connecting = true` set inside connect()', raise_m is not None)
    check('flag raised BEFORE the awaited /terminal/nonce fetch',
          raise_m is not None and nonce_await is not None and raise_m.start() < nonce_await.start())

    # 4. The flag is LOWERED only once wsRef.current holds the new socket —
    #    from that point readyState CONNECTING covers re-entrancy again.
    assign = re.search(r'wsRef\.current\s*=\s*ws\b', connect)
    lowers = [m for m in re.finditer(r'connecting\s*=\s*false', connect)]
    check('`connecting = false` appears in connect()', len(lowers) > 0)
    check('flag lowered only at/after `wsRef.current = ws` or a cancelled bail-out',
          assign is not None and all(
              m.start() > assign.start() or
              # the cancelled early-return path may also lower it
              'cancelled' in connect[max(0, m.start() - 80):m.start()]
              for m in lowers))
    check('at least one lowering follows the wsRef assignment (normal path)',
          assign is not None and any(m.start() > assign.start() for m in lowers))

    # 5. The readyState guard itself must still be present — the flag
    #    complements it, it does not replace it.
    check('readyState OPEN/CONNECTING guard still present',
          re.search(r'WebSocket\.OPEN\s*\|\|\s*rs\s*===\s*WebSocket\.CONNECTING', connect) is not None)

    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'terminal reconnect single-socket guard: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
