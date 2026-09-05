#!/usr/bin/env python3
"""A one-off night the restart cut short must not read "DONE" on its card.

The third visit, and the half of the story the second one did not reach.

scripts/test_a_night_that_died_with_the_server_said_it_was_still_running.py
fixed the RUN ROW: `_night_reconcile_interrupted_runs()` closes an orphaned
row at its last known-alive stamp, flags it `interruptedByRestart`, and gives
it NIGHT_RESTART_NOTE — "the office restarted before this night finished".
That row is right.

The SCHEDULE CARD directly above it is not, and nothing in that fix touched
it. `_night_scan` flips a `once` schedule at DISPATCH:

    else:
        s['enabled'] = False

— saved immediately, before the run thread has done a single round. It is the
right moment to flip it (a once-schedule must never be picked up twice), but
it means `enabled` records that the night was STARTED, and nothing anywhere
records how it went. missions.jsx reads it as an outcome anyway:

    {running.includes(s.id) ? 'RUNNING NOW' : s.enabled ? 'SCHEDULED' : 'DONE'}
    {s.enabled ? `next: …` : `last: ${fmtT(s.lastRunAt)}`}

So the morning after a reboot the Night Shift board reads

    🌙 overnight competitor sweep                            DONE
       Pip · Research/   once · 60m @ 10m   last: Sep 4, 2:00 AM

with the run row underneath it saying the office restarted before that same
night finished. Two surfaces disagreeing about one run — the thing app.jsx's
own note calls out by name — and the one the boss reads first is the one
that is wrong. views/terminal.jsx prints the same verdict as `done` in
`hq night`, so the shell agrees with the lie rather than the record.

DONE is also the word that ends the conversation: the card offers ✕ CANCEL
and nothing else, so a boss told the night is done has no reason to look
further, and the topic they wanted researched is simply never researched.

Fix at the one place that knows: the reconcile already walks every orphaned
run and already knows its `scheduleId`, so it stamps that schedule
`lastRunInterrupted` with the sentence to show, and `_night_scan` clears the
stamp on the next dispatch so it only ever describes the latest run. Both
readers then say the night was cut short, and say what to do about it.

Run: python3 scripts/test_a_night_the_restart_cut_short_does_not_say_done_on_its_card.py
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
    print(f'  {"ok  " if cond else "FAIL"}  {label}'
          + (f' — {detail}' if detail and not cond else ''))
    if not cond:
        FAILS.append(label)


def strip_js_comments(src: str) -> str:
    src = re.sub(r'/\*[\s\S]*?\*/', ' ', src)
    return re.sub(r'(?m)//.*$', '', src)


YESTERDAY = 1756000000000            # the night the box rebooted
LAST_ALIVE = YESTERDAY + 3600000     # last progress upsert before it died


def sched(**over):
    s = {
        'id': 's1', 'type': 'research', 'topic': 'overnight competitor sweep',
        'agentId': 'a1', 'agentName': 'Pip', 'vaultFolder': 'Research',
        'startAt': YESTERDAY, 'recurrence': 'once',
        'durationMs': 3600000, 'intervalMs': 600000,
        'enabled': False, 'lastRunAt': YESTERDAY, 'nextRunAt': YESTERDAY,
        'createdAt': YESTERDAY - 86400000,
    }
    s.update(over)
    return s


def run_row(**over):
    r = {
        'id': 'run_cut', 'scheduleId': 's1', 'agentId': 'a1', 'agentName': 'Pip',
        'topic': 'overnight competitor sweep', 'vaultFolder': 'Research',
        'startedAt': YESTERDAY, 'progressAt': LAST_ALIVE, 'finishedAt': 0,
        'iterations': 6, 'writes': ['n1', 'n2', 'n3'], 'tokensUsed': 4200,
        'errors': 0, 'lastError': '', 'stoppedByBoss': False, 'summary': '',
    }
    r.update(over)
    return r


def seed(scheds, runs) -> str:
    d = tempfile.mkdtemp(prefix='night-cutshort-')
    with open(os.path.join(d, 'scheduled-missions.json'), 'w', encoding='utf-8') as f:
        json.dump(scheds, f)
    with open(os.path.join(d, 'mission-runs.json'), 'w', encoding='utf-8') as f:
        json.dump(runs, f)
    return d


def card_verdicts(cases):
    """Render the Night Shift card's own status/meta expressions, lifted out
    of missions.jsx verbatim — a restatement here would go on passing after
    the real card drifted."""
    src = strip_js_comments((ROOT / 'missions.jsx').read_text(encoding='utf-8'))
    m_status = re.search(r'className="mc-status">\{([^\n]*?)\}</span>', src)
    m_meta = re.search(r'<span>\{s\.enabled \? `next: (?:[^\n]*?)\}</span>', src)
    if not m_status or not m_meta:
        return None, None, None
    status_expr = m_status.group(1)
    meta_expr = m_meta.group(0)[len('<span>{'):-len('}</span>')]
    prog = (
        'const fmtT = (ms) => ms ? "T" + ms : "—";\n'
        'const fmtEta = () => "";\n'
        'const out = [];\n'
        'for (const c of ' + json.dumps(cases) + ') {\n'
        '  const s = c.s, running = c.running || [];\n'
        '  out.push({ name: c.name, status: (' + status_expr + '),'
        ' meta: String(' + meta_expr + ') });\n'
        '}\n'
        'console.log(JSON.stringify(out));\n'
    )
    p = subprocess.run([os.environ.get('NODE', 'node'), '-e', prog],
                       capture_output=True, text=True, cwd=ROOT)
    if p.returncode != 0:
        return None, status_expr, p.stderr.strip()
    return {r['name']: r for r in json.loads(p.stdout)}, status_expr, None


def main() -> int:
    os.environ['GAP_CRON'] = '0'
    os.environ['NEWS_CRON'] = '0'
    os.environ['TOPICS_CRON'] = '0'
    os.environ.pop('SEARCH_WORKER', None)
    # s1: a once-night the restart killed.  s2: a once-night that really ran
    # out its hour.  s3: a nightly schedule, still enabled, untouched here.
    state_dir = seed(
        [sched(), sched(id='s2', topic='a night that actually ended'),
         sched(id='s3', topic='every night', recurrence='daily', enabled=True,
               nextRunAt=YESTERDAY + 86400000)],
        [run_row(),
         run_row(id='run_done', scheduleId='s2', finishedAt=LAST_ALIVE,
                 summary='filed four notes')])
    os.environ['CAFRESOHQ_HQ_STATE_DIR'] = state_dir
    os.chdir(ROOT)

    import serve   # importing IS the boot — the reconcile runs here

    print('=== the schedule of a night that was cut short says so ===')
    rows = {s['id']: s for s in serve._night_load('scheduled-missions.json', [])}
    cut = rows.get('s1', {})
    check('the reconcile marks the schedule whose run it just closed',
          cut.get('lastRunInterrupted') is True,
          f'lastRunInterrupted={cut.get("lastRunInterrupted")!r} — without it '
          'the card has nothing but `enabled`, which was flipped at DISPATCH '
          'and cannot tell a finished night from a killed one')
    check('...with a sentence naming the cause',
          'restart' in str(cut.get('lastRunNote') or ''),
          repr(cut.get('lastRunNote')))
    check('...and a way forward, not just a diagnosis',
          'again' in str(cut.get('lastRunNote') or ''),
          repr(cut.get('lastRunNote')))
    check('a night that genuinely finished is not marked',
          'lastRunInterrupted' not in rows.get('s2', {}),
          repr(rows.get('s2')))
    check('a nightly schedule that never orphaned a run is untouched',
          'lastRunInterrupted' not in rows.get('s3', {})
          and rows.get('s3', {}).get('enabled') is True,
          repr(rows.get('s3')))

    print('=== the mark is durable, and the endpoint serves it ===')
    with open(os.path.join(state_dir, 'scheduled-missions.json'), encoding='utf-8') as f:
        on_disk = {s['id']: s for s in json.load(f)}
    check('scheduled-missions.json on disk holds it',
          on_disk.get('s1', {}).get('lastRunInterrupted') is True,
          'a fix that only patched the response would leave the lie on disk')
    captured: dict = {}

    class _FakeHandler:
        pass

    h = _FakeHandler.__new__(_FakeHandler)
    h._send_json = lambda code, payload: captured.update({'code': code, **payload})
    serve.Handler._missions_scheduled_get(h)
    served = {s['id']: s for s in captured.get('schedules', [])}
    check('GET /missions/scheduled hands the card the mark',
          served.get('s1', {}).get('lastRunInterrupted') is True,
          repr(served.get('s1')))

    print('=== the run row the earlier fix pinned is still right ===')
    runs = {r['id']: r for r in serve._night_load('mission-runs.json', [])}
    check('the orphaned run is still closed at its last-alive stamp',
          runs.get('run_cut', {}).get('finishedAt') == LAST_ALIVE,
          repr(runs.get('run_cut', {}).get('finishedAt')))
    check('...still flagged interruptedByRestart',
          runs.get('run_cut', {}).get('interruptedByRestart') is True)
    check('...and still keeps the rounds it really did',
          runs.get('run_cut', {}).get('iterations') == 6
          and len(runs.get('run_cut', {}).get('writes') or []) == 3)
    check('a run that genuinely finished is still untouched',
          runs.get('run_done', {}).get('finishedAt') == LAST_ALIVE
          and 'interruptedByRestart' not in runs.get('run_done', {}),
          repr(runs.get('run_done')))

    print('=== a fresh dispatch clears the mark ===')
    # The flag describes the LATEST run, so a re-enabled schedule that gets
    # picked up again must not carry the old night's sentence into the new
    # one. `_night_run_one` is stubbed: the scan's job here is the bookkeeping
    # it does before the thread starts, and the real one would go to a brain.
    serve._night_run_one = lambda s: None
    again = rows['s1'].copy()
    again.update(enabled=True, nextRunAt=YESTERDAY)   # due, and asked for again
    serve._night_save('scheduled-missions.json', [again])
    serve._night_scan()
    serve._night_running.clear()
    after = serve._night_load('scheduled-missions.json', [])[0]
    check('the new run does not inherit the old night\'s mark',
          not after.get('lastRunInterrupted') and not after.get('lastRunNote'),
          repr([after.get('lastRunInterrupted'), after.get('lastRunNote')]))
    check('...and the once-schedule is still disabled at dispatch',
          after.get('enabled') is False,
          'a once-night must never be picked up twice — that flip is right, '
          'it just was never an outcome')

    print('=== the card no longer calls a killed night DONE ===')
    verdicts, expr, err = card_verdicts([
        {'name': 'cut', 's': cut},
        {'name': 'finished', 's': rows.get('s2')},
        {'name': 'scheduled', 's': rows.get('s3')},
        {'name': 'runningNow', 's': rows.get('s3'), 'running': ['s3']},
    ])
    if verdicts is None:
        check('the Night Shift card\'s status expression could be lifted',
              False, err or 'mc-status / meta expression not found in missions.jsx')
    else:
        check('a night the restart cut short does not read DONE',
              verdicts['cut']['status'] != 'DONE',
              repr(verdicts['cut']['status']))
        check('...it says it was cut short',
              'CUT' in str(verdicts['cut']['status']).upper()
              or 'SHORT' in str(verdicts['cut']['status']).upper(),
              repr(verdicts['cut']['status']))
        check('...and its meta line does not read as a finished "last:" run',
              not str(verdicts['cut']['meta']).lower().startswith('last:'),
              repr(verdicts['cut']['meta']))
        check('a once-night that really finished still reads DONE',
              verdicts['finished']['status'] == 'DONE',
              repr(verdicts['finished']['status']))
        check('...with its last run time',
              str(verdicts['finished']['meta']).lower().startswith('last:'),
              repr(verdicts['finished']['meta']))
        check('a live schedule still reads SCHEDULED',
              verdicts['scheduled']['status'] == 'SCHEDULED',
              repr(verdicts['scheduled']['status']))
        check('...with its next run time',
              str(verdicts['scheduled']['meta']).lower().startswith('next:'),
              repr(verdicts['scheduled']['meta']))
        check('a schedule in flight still reads RUNNING NOW',
              verdicts['runningNow']['status'] == 'RUNNING NOW',
              repr(verdicts['runningNow']['status']))

    print('=== hqsh agrees with the record, not with the card\'s old word ===')
    term = strip_js_comments((ROOT / 'views' / 'terminal.jsx').read_text(encoding='utf-8'))
    m = re.search(r"s\.enabled \? 'next ' \+ fmtT\(s\.nextRunAt\)[\s\S]*?\}`", term)
    check('`hq night` still decides its word from s.enabled',
          bool(m), 'if this moved, re-derive what the shell prints')
    if m:
        check('...and no longer prints a flat "done" for a cut-short night',
              'lastRunInterrupted' in m.group(0),
              m.group(0).strip())

    print()
    if FAILS:
        print(f'FAILED ({len(FAILS)}): ' + '; '.join(FAILS))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
