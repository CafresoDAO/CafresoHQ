#!/usr/bin/env python3
"""A Night Shift run orphaned by a restart must not still read "still running".

The second visit. The boss schedules an overnight mission, closes the laptop,
and comes back the next morning — except the box rebooted, or serve.py was
restarted, somewhere in the middle of the night.

`night_runner.run_mission` creates its record with `finishedAt: 0` and only
stamps a real timestamp after the iteration loop exits. `_night_log_run` is
called PROGRESSIVELY (deliberately — "a crash keeps partial log"). So the
killed night leaves a row on disk saying finishedAt 0, and before this fix
NOTHING ever revisited it:

  * missions.jsx's run row computes `inFlight = !r.finishedAt` and renders
    "▶ … 6 rounds · 3 notes · still running" — the morning after, and every
    morning after that. The server itself knows better: `_night_running` is
    empty in a fresh process and GET /missions/scheduled says `running: []`.
    Two endpoints of the same server disagreeing about the same mission.
  * app.jsx's Gazette filter (`(x.finishedAt||0) > prevSeen`) and its XP loop
    (`if (!(r.finishedAt > 0)) continue`) both gate on the same field, so the
    coworker who really did file three notes that night gets no line on their
    record — permanently, because the experience ledger is append-only and
    that gate never opens again.

Fix: `_night_reconcile_interrupted_runs()` in serve.py, called once at import
BEFORE the scheduler thread starts. A fresh process cannot have inherited a
run, so every unfinished row is definitionally orphaned. It is closed at its
last known-alive stamp (`progressAt`, newly written by `_night_log_run`, else
`startedAt`) — never at boot time, which would date the whole night to
whenever the boss next opened the app — flagged `interruptedByRestart`, and
given prose with no error COUNT behind it, the shape app.jsx already reads as
"ended for a reason on neither side of the ledger".

Run: python3 scripts/test_a_night_that_died_with_the_server_said_it_was_still_running.py
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f' — {detail}' if detail and not cond else ''))
    if not cond:
        FAILS.append(label)


def strip_py_comments(src: str) -> str:
    """Drop # comments and triple-quoted blocks so THIS file's own prose,
    quoted in serve.py's docstrings, can never satisfy a source check."""
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    return re.sub(r'(?m)^\s*#.*$', '', src)


def strip_js_comments(src: str) -> str:
    src = re.sub(r'/\*[\s\S]*?\*/', ' ', src)
    return re.sub(r'(?m)//.*$', '', src)


YESTERDAY = 1756000000000          # a night that started long before this boot
LAST_ALIVE = YESTERDAY + 3600000   # the last progress upsert we ever saw


def seed_state_dir(runs) -> str:
    d = tempfile.mkdtemp(prefix='night-orphan-')
    with open(os.path.join(d, 'mission-runs.json'), 'w', encoding='utf-8') as f:
        json.dump(runs, f)
    return d


def orphan_row(**over):
    row = {
        'id': 'run_%d' % YESTERDAY, 'scheduleId': 's1',
        'agentId': 'a1', 'agentName': 'Pip',
        'topic': 'overnight competitor sweep', 'vaultFolder': 'Research',
        'startedAt': YESTERDAY, 'finishedAt': 0, 'iterations': 6,
        'writes': ['n1', 'n2', 'n3'], 'tokensUsed': 4200,
        'errors': 0, 'lastError': '', 'stoppedByBoss': False, 'summary': '',
    }
    row.update(over)
    return row


def finished_row():
    return {
        'id': 'run_done', 'scheduleId': 's2', 'agentId': 'a2', 'agentName': 'Kip',
        'topic': 'a night that actually ended', 'vaultFolder': 'Research',
        'startedAt': YESTERDAY - 7200000, 'finishedAt': YESTERDAY - 3600000,
        'iterations': 4, 'writes': ['x'], 'tokensUsed': 10,
        'errors': 0, 'lastError': '', 'stoppedByBoss': False, 'summary': 'done',
    }


def main() -> int:
    os.environ['GAP_CRON'] = '0'
    os.environ['NEWS_CRON'] = '0'
    os.environ['TOPICS_CRON'] = '0'
    os.environ.pop('SEARCH_WORKER', None)
    state_dir = seed_state_dir([orphan_row(progressAt=LAST_ALIVE), finished_row()])
    os.environ['CAFRESOHQ_HQ_STATE_DIR'] = state_dir
    os.chdir(ROOT)

    boot_ms_floor = int(__import__('time').time() * 1000)
    import serve   # importing IS the server boot — reconcile runs here

    print('=== the server knows nothing is in flight ===')
    check('a fresh process has an empty _night_running',
          not serve._night_running,
          'the whole premise: nothing on this box is running that mission')

    print('=== GET /missions/runs no longer reports the dead night as live ===')
    captured: dict = {}

    class _FakeHandler:
        pass

    h = _FakeHandler.__new__(_FakeHandler)
    h._send_json = lambda code, payload: captured.update({'code': code, **payload})
    serve.Handler._missions_runs(h)
    rows = {r['id']: r for r in captured.get('runs', [])}
    orphan = rows.get('run_%d' % YESTERDAY, {})
    done = rows.get('run_done', {})

    check('the orphaned run now carries a real finishedAt',
          bool(orphan.get('finishedAt')),
          f'finishedAt={orphan.get("finishedAt")!r} — missions.jsx computes '
          '`inFlight = !r.finishedAt`, so 0 renders "still running" forever')
    check('it is dated at the last moment we KNEW it was alive, not at boot',
          orphan.get('finishedAt') == LAST_ALIVE,
          f'got {orphan.get("finishedAt")!r}, wanted progressAt {LAST_ALIVE}')
    check('boot time was NOT used as the end stamp',
          (orphan.get('finishedAt') or 0) < boot_ms_floor,
          'filing the night at boot time dates it to whenever the boss next '
          'opened the app, not to when it actually stopped')
    check('the run is flagged as interrupted by the restart',
          orphan.get('interruptedByRestart') is True)
    check('it says so in prose the boss can read',
          'restarted' in str(orphan.get('lastError', '')),
          repr(orphan.get('lastError')))
    check('the rounds it really completed are still on the record',
          orphan.get('iterations') == 6 and len(orphan.get('writes') or []) == 3,
          'reconciling must close the run, never erase what it did')
    check('a run that genuinely finished is left untouched',
          done.get('finishedAt') == YESTERDAY - 3600000
          and 'interruptedByRestart' not in done,
          repr(done))

    print('=== the close-out is durable, not recomputed on every read ===')
    with open(os.path.join(state_dir, 'mission-runs.json'), encoding='utf-8') as f:
        on_disk = {r['id']: r for r in json.load(f)}
    check('mission-runs.json on disk holds the closed-out row',
          bool(on_disk.get('run_%d' % YESTERDAY, {}).get('finishedAt')),
          'a fix that only patched the response would leave the lie on disk '
          'for hqsh, the Gazette ingest and every other reader')

    print('=== _night_log_run stamps the last-known-alive time ===')
    serve._night_log_run({'id': 'run_live', 'startedAt': YESTERDAY, 'finishedAt': 0,
                          'iterations': 1, 'writes': []})
    with open(os.path.join(state_dir, 'mission-runs.json'), encoding='utf-8') as f:
        live = {r['id']: r for r in json.load(f)}['run_live']
    check('a progress upsert writes progressAt',
          (live.get('progressAt') or 0) >= boot_ms_floor,
          f'progressAt={live.get("progressAt")!r} — without it an interrupted '
          'run can only be dated by its START, losing hours of known runtime')

    print('=== with no progressAt at all, startedAt is the fallback ===')
    runs2 = serve._night_load('mission-runs.json', [])
    runs2 = [r for r in runs2 if r.get('id') != 'run_live']
    runs2.append(orphan_row(id='run_nostamp'))
    serve._night_save('mission-runs.json', runs2)
    serve._night_reconcile_interrupted_runs()
    ns = {r['id']: r for r in serve._night_load('mission-runs.json', [])}['run_nostamp']
    check('a row with no progressAt closes at startedAt',
          ns.get('finishedAt') == YESTERDAY,
          repr(ns.get('finishedAt')))

    print('=== reconcile runs BEFORE the scheduler thread ===')
    src = strip_py_comments((ROOT / 'serve.py').read_text(encoding='utf-8'))
    # The CALL, not the `def` — `.find()` on the bare name matches the
    # definition line and would go on passing with the call deleted.
    m_call = re.search(r'(?m)^\s*_night_reconcile_interrupted_runs\(\)\s*$', src)
    call_at = m_call.start() if m_call else -1
    thread_at = src.find('target=_night_loop')
    check('serve.py calls the reconcile at import',
          call_at != -1 and thread_at != -1)
    check('the call sits above the night-shift thread start',
          -1 < call_at < thread_at,
          'the first scan can start a NEW run and log it with finishedAt 0 — '
          'reconcile must only ever see rows from a previous process')

    print('=== the browser reads the closed-out run correctly ===')
    app = strip_js_comments((ROOT / 'app.jsx').read_text(encoding='utf-8'))
    m_stopped = re.search(r'const stopped = [^;]+;', app)
    m_failed = re.search(r'const failed = [^;]+;', app)
    check('app.jsx still classifies night runs with `failed` / `stopped`',
          bool(m_stopped and m_failed))
    if m_stopped and m_failed:
        prog = (
            'const r = ' + json.dumps(orphan) + ';\n'
            + m_failed.group(0) + '\n' + m_stopped.group(0) + '\n'
            + 'const outcome = failed ? "snag" : ((r.iterations > 0) ? "done" : null);\n'
            + 'console.log(JSON.stringify({ stopped, outcome }));'
        )
        out = subprocess.run([os.environ.get('NODE', 'node'), '-e', prog],
                             capture_output=True, text=True, cwd=ROOT)
        verdict = json.loads(out.stdout or '{}') if out.returncode == 0 else {}
        check('the XP ledger treats a restart as neither a job nor a snag',
              verdict.get('stopped') is True,
              f'{out.stdout.strip()}{out.stderr.strip()} — prose with no error '
              'COUNT is the shape app.jsx reads as "on neither side of the '
              'ledger"; a power cut is not the coworker\'s snag')

    miss = strip_js_comments((ROOT / 'missions.jsx').read_text(encoding='utf-8'))
    check('missions.jsx still decides the run row from r.finishedAt',
          'const inFlight = !r.finishedAt;' in miss,
          'if this moved, re-derive what the closed-out row renders as')
    check('the closed-out row no longer renders as in flight',
          not (not orphan.get('finishedAt')),
          'inFlight would still be true')

    print()
    if FAILS:
        print(f'FAILED ({len(FAILS)}): ' + '; '.join(FAILS))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
