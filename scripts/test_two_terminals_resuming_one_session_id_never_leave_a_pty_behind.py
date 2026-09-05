#!/usr/bin/env python3
"""Two clients restoring the same terminal session both spawned a PTY, and
one of them was unreachable forever after.

pty_server.py keeps every persistent terminal in ONE module-level dict,
`_PTY_SESSIONS`, keyed by the session_id the browser persists. serve.py is a
ThreadedServer, so a WebSocket upgrade runs on its own thread, and the
resume-or-spawn decision used to be two separate holds of the registry lock
with the session dict built in the gap between them:

    with _PTY_SESSIONS_LK:
        sess = _PTY_SESSIONS.get(session_id) if session_id else None
    if sess is not None and not sess['stop'].is_set():
        ...resume...
    else:
        sess = { 'stop': threading.Event(), ... }      # <-- the gap
        if session_id:
            with _PTY_SESSIONS_LK:
                _PTY_SESSIONS[session_id] = sess
        ...spawn a CLI on a PTY...

Check-then-act. Two connections carrying the same session_id — a phone and a
desktop both restoring the id they persisted, two tabs reconnecting the
instant serve.py comes back — can both read "nothing under this key" and both
go on to spawn. The second registration overwrites the first, and the first
session is then reachable by nothing:

  * the reaper only walks _PTY_SESSIONS, so it never expires it;
  * /terminal/kill only pops out of _PTY_SESSIONS, so "End session" can't
    reach it;
  * and the teardown at the bottom of _terminal_pty_ws deliberately refuses
    to terminate a session that HAS an id — it assumes the registry is
    holding it for a reconnect (`if not session_id and not ...stop.is_set()`).

So a whole `claude`/`codex` child process, its pty master fd and its reader
thread stay alive for the life of the server. One more every time two clients
race on one id, and nothing in the product can ever end them.

The same key has a second, symmetric hazard: a PTY that exits pops its own id
with a bare `_PTY_SESSIONS.pop(session_id, None)`. If a client has already
reconnected in the meantime, the successor is what sits under that key, and
the dying thread's pop evicts the LIVE session instead — orphaning the new
PTY exactly the way the duplicate spawn orphaned the old one.

The fix is `_pty_claim_session()` (lookup and registration under one hold, so
the loser resumes instead of spawning) and `_pty_drop_session()` (pop only if
the key still maps to the session doing the popping).

The interleaving is forced, not raced: `threading.Event` is stubbed so that
constructing a session dict parks on a barrier. In the fixed code that
construction happens while the registry lock is held, so the barrier can only
ever be reached by one thread and breaks on its timeout; in the pre-fix code
the lock is released first, so every thread arrives together and sails
through — which is the collision itself.

Run: python3 scripts/test_two_terminals_resuming_one_session_id_never_leave_a_pty_behind.py
"""
import os
import pathlib
import re
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_py_comments(src):
    """Drop docstrings and # comments before grepping for a bad pattern —
    the explanations above and in pty_server.py quote the pre-fix code."""
    src = re.sub(r'"""[\s\S]*?"""', '', src)
    src = re.sub(r"'''[\s\S]*?'''", '', src)
    return re.sub(r'#.*$', '', src, flags=re.M)


class _BarrierThreading:
    """Stands in for pty_server's `threading` module. Event() parks on a
    barrier so every thread that reaches session construction at the same
    time is held there together."""

    def __init__(self, barrier):
        self.barrier = barrier
        self.arrivals = []
        self._lk = threading.Lock()

    def Event(self):
        with self._lk:
            self.arrivals.append(threading.current_thread().name)
        try:
            self.barrier.wait(timeout=0.75)
        except threading.BrokenBarrierError:
            pass
        return threading.Event()

    def Lock(self):
        return threading.Lock()

    def Thread(self, *a, **kw):
        return threading.Thread(*a, **kw)


def main():
    print('two terminals resuming one session_id never leave a pty behind')
    print()

    try:
        import pty_server
    except Exception as e:                       # pragma: no cover
        check('pty_server imports', False, e)
        return 1

    claim = getattr(pty_server, '_pty_claim_session', None)
    drop = getattr(pty_server, '_pty_drop_session', None)
    check('the registry has an atomic claim helper', callable(claim),
          '_pty_claim_session is missing — the resume-or-spawn decision is '
          'still a check-then-act across two lock holds')
    check('a session only drops itself', callable(drop),
          '_pty_drop_session is missing — an exiting PTY still pops the key '
          'by name and can evict a live successor')
    if not (callable(claim) and callable(drop)):
        print()
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1

    # ── 1. the forced collision ────────────────────────────────────────
    N = 4
    sid = 'sess-collision'
    pty_server._PTY_SESSIONS.clear()
    barrier = threading.Barrier(N)
    stub = _BarrierThreading(barrier)
    real_threading = pty_server.threading
    results = []
    res_lk = threading.Lock()

    def racer():
        sess, is_new = claim(sid)
        with res_lk:
            results.append((id(sess), is_new, sess))

    pty_server.threading = stub
    try:
        ts = [threading.Thread(target=racer, name='pty-racer-%d' % i)
              for i in range(N)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=20)
    finally:
        pty_server.threading = real_threading

    check('every racing connection came back', len(results) == N,
          '%d of %d threads returned' % (len(results), N))
    spawners = [r for r in results if r[1]]
    check('exactly one of %d connections spawns a PTY' % N,
          len(spawners) == 1,
          '%d connections were told to spawn — %d PTYs, %d of them with no '
          'registry entry, no reaper, and no way for /terminal/kill to '
          'reach them' % (len(spawners), len(spawners),
                          max(0, len(spawners) - 1)))
    check('the others resume the session that exists',
          len({r[0] for r in results}) == 1,
          '%d distinct session objects for one session_id'
          % len({r[0] for r in results}))
    registered = pty_server._PTY_SESSIONS.get(sid)
    check('the registry holds the session every caller got',
          registered is not None and all(r[2] is registered for r in results),
          'a caller is holding a session the registry does not know about — '
          'that is the orphan')
    check('the collision really was simultaneous', len(stub.arrivals) >= 1,
          stub.arrivals)

    # ── 2. a dying PTY must not evict its successor ────────────────────
    pty_server._PTY_SESSIONS.clear()
    sid2 = 'sess-handover'
    old, _ = claim(sid2)
    old['stop'].set()                    # the old PTY has just exited
    new, is_new = claim(sid2)            # the client reconnects, gets a fresh one
    check('a reconnect onto a dead id gets a fresh session',
          is_new and new is not old)
    drop(sid2, old)                      # the dying reader thread cleans up
    check('the dying session does not take the live one with it',
          pty_server._PTY_SESSIONS.get(sid2) is new,
          'the successor was evicted — its PTY is now the orphan')
    drop(sid2, new)
    check('a session still drops itself normally',
          sid2 not in pty_server._PTY_SESSIONS)
    pty_server._PTY_SESSIONS.clear()

    # ── 3. no bare pop survives on the spawn/teardown paths ────────────
    src = strip_py_comments((ROOT / 'pty_server.py').read_text(encoding='utf-8'))
    # /terminal/kill's `sess = _PTY_SESSIONS.pop(session_id, None)` is the one
    # legitimate by-name pop: it takes ownership of whatever is there and then
    # terminates it. The teardown shape is the bad one.
    bare_pops = re.findall(
        r'with _PTY_SESSIONS_LK:\s*_PTY_SESSIONS\.pop\(session_id', src)
    check('no teardown pops the key by name any more',
          len(bare_pops) == 0,
          '%d unguarded pop(session_id) call(s) left on the exit paths'
          % len(bare_pops))
    check('the drop is guarded by identity',
          '_PTY_SESSIONS.get(session_id) is sess' in src)
    two_holds = re.search(
        r'with _PTY_SESSIONS_LK:\s*\n\s*sess = _PTY_SESSIONS\.get\(session_id\)'
        r'[\s\S]{0,400}?\n\s{4}if sess is not None', src)
    check('the handler no longer decides across two lock holds',
          two_holds is None,
          'the check-then-act is back in _terminal_pty_ws')

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
