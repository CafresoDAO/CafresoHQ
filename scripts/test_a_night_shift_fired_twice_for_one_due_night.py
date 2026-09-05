#!/usr/bin/env python3
"""A Night Shift schedule could fire twice for the same due occurrence.

Three ways this hunt went looking for a double-fire, all in `_night_scan`
(serve.py) — the 30-second poll that picks the one due schedule, mutates
its `nextRunAt`/`enabled`/`lastRunAt`, and dispatches its mission in a
daemon thread that can run for up to four hours:

  1. DOUBLE-FIRE ON RESTART. The old order was mutate → start the
     dispatch thread (the actual fire) → `_night_save(...)` LAST. If the
     process died anywhere in that window — crash, a deploy's SIGKILL,
     the box losing power — the advanced `nextRunAt` never reached disk.
     The schedule was already fired once (the thread had started, real
     tokens already spent), but the file on disk still shows the OLD,
     still-due `nextRunAt`. The next process to boot reads that same
     stale row, sees it due all over again, and fires a "once" mission
     the boss meant fired exactly once for a second time — or, for a
     `daily` schedule, re-fires tonight's run instead of tomorrow's.

  2. CONCURRENT-INSTANCE DOUBLE-FIRE. `_night_running` — the "one
     mission at a time" gate — is an in-memory dict, per-process. Two
     serve.py processes briefly alive at once (an ordinary deploy
     overlap, or two dev instances against the same state dir) each see
     an empty `_night_running`, each read the same due row, and each
     independently dispatch it. Nothing before this fix made "is this
     due?" and "I am the one advancing it" the same operation.

  3. LATE-FIRE PILEUP. Checked and NOT reproduced: `_night_scan` only
     ever dispatches ONE row per call (`break` after the first due
     match), and a `daily` schedule's catch-up `while nxt <= now_ms`
     loop advances the STORED `nextRunAt` past every missed day before
     the row is saved — it does not queue one dispatch per missed
     interval. A schedule that slept through five days across a laptop
     lid still fires exactly once on wake, landing on the correct next
     occurrence, not a five-run burst. No fix needed for this shape;
     recorded here so a future hunt does not re-open it.

Fix, for (1) and (2) together: `_night_save('scheduled-missions.json', …)`
now runs BEFORE the dispatch thread starts, not after — the worst a crash
in that window can now do is lose one dispatch, never duplicate one. And
the whole pick-mutate-persist step is now guarded by
`_night_try_claim_scan()`, an O_CREAT|O_EXCL lock file — the same shape
as `fs_routes.claim_name` — so two processes can no longer both see the
same row as unclaimed. A lock older than `_NIGHT_SCAN_LOCK_STALE_SEC`
(60s) is reclaimed rather than deadlocking every scan forever, since the
guarded section is a few lines of pure Python with no LLM I/O in it (the
mission itself now starts strictly AFTER the lock is released).

Reproduced 2026-09-05 against a scratch `CAFRESOHQ_HQ_STATE_DIR`, in three
rounds:
  - Round 1 (crash-before-persist): monkeypatch `_night_save` to raise on
    its first call, call `_night_scan()` once (the "crash"), then clear
    `_night_running`/`_night_abort` and restore `_night_save` (the
    "restart"), and call `_night_scan()` again. Pre-fix: fired twice.
    Post-fix: the crashed scan fires zero times (nothing persisted yet,
    so nothing was dispatched either) and the restarted scan fires
    exactly once.
  - Round 2 (in-process lock contention): call `_night_try_claim_scan()`
    twice back-to-back without releasing — the second call must return
    False — then release and confirm a third call succeeds, then confirm
    a lock stamped 120s old is reclaimed.
  - Round 3 (real concurrent processes): fork 8 real Python processes
    via `multiprocessing`, all pointed at ONE scratch state dir with ONE
    due schedule, all calling `_night_scan()` at once. Repeated 5 rounds.
    Pre-fix this raced; post-fix exactly one dispatch lands, every round.

Run: python3 scripts/test_a_night_shift_fired_twice_for_one_due_night.py
"""
from __future__ import annotations

import json
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
    print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f' — {detail}' if detail and not cond else ''))
    if not cond:
        FAILS.append(label)


def strip_py_comments(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    return re.sub(r'(?m)^\s*#.*$', '', src)


def _quiet_env():
    os.environ['GAP_CRON'] = '0'
    os.environ['NEWS_CRON'] = '0'
    os.environ['TOPICS_CRON'] = '0'
    os.environ.pop('SEARCH_WORKER', None)


def _seed(state_dir, sched):
    with open(os.path.join(state_dir, 'scheduled-missions.json'), 'w', encoding='utf-8') as f:
        json.dump([sched], f)


def _once_schedule(now_ms, sid='s1'):
    return {'id': sid, 'enabled': True, 'recurrence': 'once',
            'nextRunAt': now_ms - 5000, 'agentId': 'a1', 'agentName': 'Pip', 'topic': 't'}


def round_one_restart_no_longer_duplicates() -> None:
    print('=== round 1: a crash between mutate and persist no longer double-fires ===')
    _quiet_env()
    state_dir = tempfile.mkdtemp(prefix='night-restart-')
    os.environ['CAFRESOHQ_HQ_STATE_DIR'] = state_dir
    now_ms = int(time.time() * 1000)
    _seed(state_dir, _once_schedule(now_ms))

    import serve  # importing IS the server boot

    calls = []
    serve._night_run_one = lambda s: calls.append(s.get('id'))

    orig_save = serve._night_save
    state = {'n': 0}

    def crashy_save(name, data):
        state['n'] += 1
        if state['n'] == 1 and name == 'scheduled-missions.json':
            raise RuntimeError('simulated crash before persisting nextRunAt')
        return orig_save(name, data)

    serve._night_save = crashy_save
    try:
        serve._night_scan()
        crashed = False
    except RuntimeError:
        crashed = True
    check('the simulated crash actually happened (sanity)', crashed)
    check('a scan that crashes before persisting fires NOTHING '
          '(the fix moved the fire to strictly after the persist)',
          calls == [], repr(calls))
    check('and the lock file was not left standing after the crash '
          "(the finally: release still runs even though the try: body "
          'raised)', not serve._night_scan_lock_path().exists())

    with open(os.path.join(state_dir, 'scheduled-missions.json'), encoding='utf-8') as f:
        on_disk = json.load(f)[0]
    check('nothing reached disk either — the row is untouched',
          on_disk.get('enabled') is True and 'lastRunAt' not in on_disk,
          repr(on_disk))

    # Simulate the restart: a fresh process has empty _night_running/_night_abort,
    # and this time _night_save works (the crash is over).
    serve._night_running.clear()
    serve._night_abort.clear()
    serve._night_save = orig_save

    serve._night_scan()
    time.sleep(0.05)
    check('the restarted process fires the schedule exactly once',
          calls == ['s1'], repr(calls))

    with open(os.path.join(state_dir, 'scheduled-missions.json'), encoding='utf-8') as f:
        on_disk2 = json.load(f)[0]
    check('...and the "once" schedule is now durably disabled',
          on_disk2.get('enabled') is False, repr(on_disk2))

    # A SECOND restart (e.g. another bounce a minute later) must not re-fire
    # a schedule that is now honestly disabled on disk.
    serve._night_running.clear()
    serve._night_abort.clear()
    serve._night_scan()
    time.sleep(0.05)
    check('a further restart after the honest disable does not fire again',
          calls == ['s1'], repr(calls))


def round_two_lock_contention() -> None:
    print('=== round 2: the scan lock actually excludes a second holder ===')
    import serve
    serve._night_release_scan_lock()
    check('first claim succeeds', serve._night_try_claim_scan() is True)
    check('a second claim while the first is still held is refused '
          '(simulates a second live process mid-scan)',
          serve._night_try_claim_scan() is False)
    serve._night_release_scan_lock()
    check('a claim after release succeeds', serve._night_try_claim_scan() is True)
    serve._night_release_scan_lock()

    p = serve._night_scan_lock_path()
    fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
    os.close(fd)
    old = time.time() - (serve._NIGHT_SCAN_LOCK_STALE_SEC + 60)
    os.utime(str(p), (old, old))
    check('a lock left behind by a dead process (120s stale) is reclaimed '
          'rather than deadlocking every scan forever',
          serve._night_try_claim_scan() is True)
    serve._night_release_scan_lock()

    fresh_fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
    os.close(fresh_fd)
    check('a lock that is merely YOUNG (not stale) is NOT reclaimed',
          serve._night_try_claim_scan() is False)
    serve._night_release_scan_lock()


_WORKER_SRC = """
import json, os, sys, time
sys.path.insert(0, %(root)r)
os.environ['GAP_CRON'] = '0'
os.environ['NEWS_CRON'] = '0'
os.environ['TOPICS_CRON'] = '0'
os.environ.pop('SEARCH_WORKER', None)
os.environ['CAFRESOHQ_HQ_STATE_DIR'] = %(state_dir)r
import serve
calls = []
serve._night_run_one = lambda s: calls.append(s.get('id'))
serve._night_scan()
time.sleep(0.15)
print(json.dumps(calls))
"""


def round_three_real_concurrent_processes() -> None:
    print('=== round 3: 8 real concurrent OS processes race one due schedule, 5 rounds ===')
    # Real `subprocess`, not `multiprocessing.Process` — a fork of THIS
    # process would inherit `serve` already imported (round 1 imported it
    # module-level), so a child's `import serve` would be a no-op returning
    # the cached module still pointed at round 1's now-exhausted state dir,
    # never re-reading CAFRESOHQ_HQ_STATE_DIR. A genuinely separate
    # interpreter is what a real deploy overlap or two dev instances are.
    for rnd in range(5):
        state_dir = tempfile.mkdtemp(prefix='night-2proc-')
        now_ms = int(time.time() * 1000)
        _seed(state_dir, _once_schedule(now_ms))
        src = _WORKER_SRC % {'root': str(ROOT), 'state_dir': state_dir}
        script = os.path.join(state_dir, 'worker.py')
        with open(script, 'w', encoding='utf-8') as f:
            f.write(src)
        procs = [subprocess.Popen([sys.executable, script],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True) for _ in range(8)]
        total = []
        errs = []
        for p in procs:
            out, err = p.communicate(timeout=15)
            try:
                total.extend(json.loads(out.strip().splitlines()[-1]))
            except (IndexError, ValueError):
                errs.append(err[-300:])
        check(f'round {rnd + 1}/5: 8 concurrent processes fire the one due '
              'schedule EXACTLY once between them',
              total.count('s1') == 1 and len(total) == 1,
              f'calls={total!r}' + (f', worker errors={errs!r}' if errs else ''))


def round_four_source_shape() -> None:
    print('=== round 4: the source still has the fix in the right shape ===')
    src = strip_py_comments((ROOT / 'serve.py').read_text(encoding='utf-8'))
    m = re.search(r'def _night_scan\(\):.*?(?=\ndef _night_loop\(\))', src, re.S)
    check('_night_scan is still findable', m is not None)
    body = m.group(0) if m else ''
    save_at = body.find("_night_save('scheduled-missions.json'")
    thread_at = body.find('threading.Thread(target=_night_run_one')
    check('_night_save runs BEFORE the dispatch thread starts, not after',
          save_at != -1 and thread_at != -1 and save_at < thread_at,
          f'save_at={save_at}, thread_at={thread_at}')
    check('the scan claims a cross-process lock before touching the file',
          '_night_try_claim_scan()' in body)
    check('the lock is released in a finally (a raise inside the guarded '
          'section must not leave the lock standing)',
          'finally:' in body and '_night_release_scan_lock()' in body)


def main() -> int:
    round_one_restart_no_longer_duplicates()
    round_two_lock_contention()
    round_three_real_concurrent_processes()
    round_four_source_shape()

    print()
    if FAILS:
        print(f'FAILED ({len(FAILS)}): ' + '; '.join(FAILS))
        return 1
    print('PASS: a due night shift fires exactly once — across a crash, a '
          'restart, and eight processes racing it at once')
    return 0


if __name__ == '__main__':
    sys.exit(main())
