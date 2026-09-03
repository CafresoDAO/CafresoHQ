#!/usr/bin/env python3
"""The Calendar's tag promises "missions when they wrap" — a mission that
had not yet STARTED never got that far.

Night Shift (missions.jsx's NightShiftSection) lets a boss schedule a
research mission for any future moment — "STARTS" + a datetime-local input,
same modal that ships "runs even with this tab closed." Schedule one for two
days out and it is genuinely saved: `serve.py`'s `/missions/schedule` writes
it to scheduled-missions.json with a real `nextRunAt`, and the Missions
modal's own Night Shift list shows it as SCHEDULED with a countdown.

The Calendar — the one view whose whole job is "your business by day" —
showed nothing. Not a wrong day, not a hidden row behind a filter: nothing,
anywhere, until the moment `_night_scan` actually started the run. Reproduced
live against a real `serve.py` (isolated hq-state dir, port 8912): POSTed a
schedule with `startAt` 2 days out, confirmed `/missions/scheduled` answers
with the schedule in `schedules` and an empty `running` list — and the
pre-fix `nightShiftBoard` computation in app.jsx (`schedules.filter(s =>
runningIds.has(s.id))`) is exactly the filter that produces an empty board
from that same response. `nightShiftBoard` is the ONLY schedule data
`CalendarView` ever received; a schedule the office has not started running
yet had no path into the view at all.

The fix adds the other half of the same poll: `nightShiftPending` (app.jsx)
captures every enabled, not-currently-running schedule — the complement of
`nightShiftBoard`'s filter, from data the poll was already fetching — and
`CalendarView` (views/core.jsx) files each one at its own `nextRunAt`, the
same way a running mission is filed at its projected wrap: a forecast row,
under the `ahead` heading the calendar already knows how to mark. Copy stays
distinct on purpose — "starts" / "SCHEDULED", not "wraps up" / "RUNNING" —
so a merely-scheduled mission can never be read as one already in flight.

This suite pins, by lifting the REAL code (never a re-implementation):
  §1 the `board`/`pending` split in app.jsx's poll, and the day-filing loop
     in CalendarView, driven under Node across the shapes that must and must
     not produce a pending row (not-yet-run, already-running, already-fired
     one-time, a re-armed daily schedule, and a schedule missing a runnable
     time);
  §2 the wiring: CalendarView's signature and app.jsx's call site actually
     carry the new prop, and the render branch's copy cannot drift back
     towards the in-flight forecast's words;
  §3 live: a real `serve.py` on an ephemeral port, a real POST to
     `/missions/schedule` for something 2 days out, a real GET of
     `/missions/scheduled` — then the REAL lifted app.jsx + CalendarView code
     run against that REAL response, filing the schedule on the correct day
     (re-derived from the REAL `officeDate`, not restated).

Run: python3 scripts/test_the_calendar_didnt_know_a_mission_was_coming.py
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / 'views' / 'core.jsx'
APP = ROOT / 'app.jsx'
ART = ROOT / 'app' / 'artifacts.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract(text, start_marker, end_marker, start=0):
    i = text.find(start_marker, start)
    if i < 0:
        return None
    j = text.find(end_marker, i)
    return text[i:j + len(end_marker)] if j >= 0 else None


def lift_const(src, name):
    """`const <name> = …;` to its depth-0 semicolon — located by NAME, so a
    rename reports itself instead of silently lifting an empty slice."""
    m = re.search(r'\bconst %s = ' % re.escape(name), src)
    if not m:
        raise SystemExit('no `const %s = ` found' % name)
    depth = 0
    for j in range(m.start(), len(src)):
        c = src[j]
        if c in '({[':
            depth += 1
        elif c in ')}]':
            depth -= 1
        elif c == ';' and depth == 0:
            return src[m.start():j + 1]
    raise SystemExit('unterminated `const %s`' % name)


def run_js(script, timeout=60):
    proc = subprocess.run(['node', '--input-type=module', '-e', script],
                          cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def build_harness(app_src, core_src, art_src):
    """The REAL board/pending split (app.jsx), the REAL day-filing loop
    (views/core.jsx), and the REAL office clock (app/artifacts.jsx), wired
    into one callable. Nothing here restates their rules — if the shipped
    code changes shape, this harness changes with it."""
    office = extract(art_src, 'function officeDate(now) {', '\n}')
    board_block = lift_const(app_src, 'board')
    pending_block = lift_const(app_src, 'pending')
    pending_loop = extract(core_src,
                           '    for (const s of (nightShiftPending',
                           '\n    }')
    if not office or not board_block or not pending_block or not pending_loop:
        raise SystemExit('could not extract officeDate / board / pending / '
                          'the nightShiftPending day-filing loop')
    return office + '''
function fromPoll(schedulesArg, runningArg) {
  const schedules = schedulesArg;
  const runningIds = new Set(runningArg);
''' + board_block + '\n' + pending_block + '''
  return { board, pending };
}
function fileOnCalendar(nightShiftPendingArg) {
  const nightShiftPending = nightShiftPendingArg;
  const out = new Map();
  const push = (ts, entry) => {
    const key = officeDate(new Date(ts));
    if (!out.has(key)) out.set(key, []);
    out.get(key).push(entry);
  };
''' + pending_loop + '''
  return [...out.entries()].map(([day, items]) =>
    [day, items.sort((a, b) => b.at - a.at)]).sort((a, b) => b[0].localeCompare(a[0]));
}
function dayKeyOf(ms) { return officeDate(new Date(ms)); }
'''


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def http_get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, {'error': str(e)}


def http_post(url, obj):
    req = urllib.request.Request(url, data=json.dumps(obj).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'},
                                 method='POST')
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {'error': str(e)}


def boot(state_dir):
    port = free_port()
    env = dict(os.environ, PORT=str(port),
               CAFRESOHQ_HQ_STATE_DIR=str(state_dir),
               CAFRESOHQ_TLS_AUTO='0')
    for k in ('OCI_VAULT_NAMESPACE', 'OCI_VAULT_BUCKET', 'OCI_VAULT_PREFIX',
              'CAFRESOHQ_VAULT_BACKEND', 'CAFRESOHQ_OBSIDIAN_URL',
              'CAFRESOHQ_OBSIDIAN_KEY', 'CAFRESOHQ_API_KEY'):
        env.pop(k, None)
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=str(ROOT), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = 'http://127.0.0.1:%d' % port

    def kill():
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    for _ in range(80):
        if http_get(base + '/missions/scheduled')[0] == 200:
            return base, kill
        time.sleep(0.25)
    kill()
    raise SystemExit('serve.py never came up')


def main():
    print("The Calendar didn't know a mission was coming")
    for f in (CORE, APP, ART):
        if not f.is_file():
            print(f'  FAIL  missing {f}')
            return 1
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    app_src = APP.read_text(encoding='utf-8')
    core_src = CORE.read_text(encoding='utf-8')
    art_src = ART.read_text(encoding='utf-8')
    harness = build_harness(app_src, core_src, art_src)

    DAY = 86400000
    HOUR = 3600000
    now = int(time.time() * 1000)

    # ── §1: the real split + the real filing loop, over every shape ──────
    print('\n[behaviour — the real code, synthetic schedules]')

    def run(cases_js):
        return run_js(harness + cases_js)

    out = run('''
const R = {};
const now = Date.now();
const HOUR = 3600000;
const DAY = 86400000;
const future = %d;
const soon = %d;

// (a) never run, not currently running — the whole defect.
R.notYetRun = fromPoll(
  [{ id: 's1', enabled: true, nextRunAt: future, startAt: future,
     topic: 'competitor sweep', agentId: 'ag1', agentName: 'Vera', recurrence: 'once' }],
  []);

// (b) currently running — must NOT double up with `board`.
R.currentlyRunning = fromPoll(
  [{ id: 's2', enabled: true, nextRunAt: soon, startAt: soon,
     topic: 'x', agentId: 'ag1', agentName: 'Vera', recurrence: 'once' }],
  ['s2']);

// (c) a one-time schedule that already fired — serve.py flips `enabled`
//     to false the instant _night_scan starts it. Already represented by
//     nightShiftBoard/nightShiftRuns; must not resurrect here.
R.alreadyFiredOnce = fromPoll(
  [{ id: 's3', enabled: false, nextRunAt: now - HOUR, startAt: now - 2 * HOUR,
     topic: 'x', agentId: 'ag1', recurrence: 'once' }],
  []);

// (d) a daily schedule that just finished last night's run and re-armed —
//     `enabled` stays true, `nextRunAt` already advanced to tomorrow.
R.dailyReArmed = fromPoll(
  [{ id: 's4', enabled: true, nextRunAt: future, startAt: now - DAY,
     topic: 'nightly digest', agentId: 'ag1', agentName: 'Vera', recurrence: 'daily' }],
  []);

// (e) a schedule with no runnable time at all — must not crash the filing
//     loop or file a phantom row at the epoch.
R.noRunnableTime = fromPoll(
  [{ id: 's5', enabled: true, nextRunAt: 0, startAt: 0, topic: 'x', agentId: 'ag1' }],
  []);

R.groupsNotYetRun = fileOnCalendar(R.notYetRun.pending);
R.groupsAlreadyRunning = fileOnCalendar(R.currentlyRunning.pending);
R.groupsNoRunnableTime = fileOnCalendar(R.noRunnableTime.pending);
R.dayKeyFuture = dayKeyOf(future);
console.log(JSON.stringify(R));
''' % (now + 2 * DAY, now + 5 * 60000))

    check('a schedule that has not run yet is captured as PENDING',
          len(out['notYetRun']['pending']) == 1
          and out['notYetRun']['pending'][0]['id'] == 's1',
          f"got {out['notYetRun']['pending']!r} — this is the whole defect: "
          'the only other consumer, `board`, filters this schedule OUT')
    check('...and `board` stays empty for it — nightShiftBoard alone never '
          'saw this schedule, which is exactly why the calendar was blind '
          'to it',
          out['notYetRun']['board'] == [],
          f"got {out['notYetRun']['board']!r}")
    check('...and it files onto the calendar at its own nextRunAt, on the '
          'correct day',
          len(out['groupsNotYetRun']) == 1
          and out['groupsNotYetRun'][0][0] == out['dayKeyFuture']
          and out['groupsNotYetRun'][0][1][0]['kind'] == 'mission-pending'
          and out['groupsNotYetRun'][0][1][0]['at'] == now + 2 * DAY,
          f"got {out['groupsNotYetRun']!r}, wanted day {out['dayKeyFuture']!r}")

    check('a schedule already running is NOT double-counted as pending',
          out['currentlyRunning']['pending'] == []
          and len(out['currentlyRunning']['board']) == 1,
          f"pending={out['currentlyRunning']['pending']!r} "
          f"board={out['currentlyRunning']['board']!r} — a mission already "
          'in flight must show once, as the running forecast, not twice')
    check('...and it never reaches the calendar filing loop either',
          out['groupsAlreadyRunning'] == [],
          f"got {out['groupsAlreadyRunning']!r}")

    check('a one-time schedule that already fired does not resurrect as '
          'pending',
          out['alreadyFiredOnce']['pending'] == [],
          f"got {out['alreadyFiredOnce']['pending']!r} — `enabled: false` "
          'means it already ran; it belongs to nightShiftRuns, not here')

    check('a daily schedule that re-armed after last night\'s run shows up '
          'pending at its NEW nextRunAt',
          len(out['dailyReArmed']['pending']) == 1
          and out['dailyReArmed']['pending'][0]['nextRunAt'] == now + 2 * DAY,
          f"got {out['dailyReArmed']['pending']!r}")

    check('a schedule with no runnable time does not crash the filing loop '
          'or file a phantom row',
          out['noRunnableTime']['pending'] != []
          and out['groupsNoRunnableTime'] == [],
          f"pending={out['noRunnableTime']['pending']!r} "
          f"groups={out['groupsNoRunnableTime']!r} — the loop's own "
          '`if (!s || !s.nextRunAt) continue;` must be what keeps this off '
          'the calendar, not a filter one layer up silently eating it too')

    # ── §2: the wiring can't quietly fall back apart ─────────────────────
    print('\n[wiring]')
    cal_sig_line = next((l for l in core_src.splitlines()
                         if l.startswith('function CalendarView(')), '')
    check("CalendarView's own signature accepts the new prop — the filing "
          'loop above references it, so a signature without it would '
          'ReferenceError at runtime even if the body were otherwise correct',
          'nightShiftPending = []' in cal_sig_line,
          'views/core.jsx: CalendarView signature missing nightShiftPending')
    check('CalendarView is actually passed the new prop',
          'nightShiftPending={nightShiftPending}' in app_src,
          "app.jsx: CalendarView's call site still only passes the old two "
          'night-shift props')
    check('a dedicated state holds the pending list, polled alongside the '
          'existing board/runs',
          'const [nightShiftPending, setNightShiftPending] = useStateA([]);' in app_src
          and 'if (!stop) setNightShiftPending(pending);' in app_src,
          'app.jsx: nightShiftPending state/poll not found')
    check("the pending filter is `board`'s own complement — enabled and not "
          'currently running — computed from the SAME `schedules`/'
          '`runningIds` the board line above already derived, not a second '
          'fetch',
          '.filter(s => s && s.enabled !== false && !runningIds.has(s.id))' in app_src,
          'app.jsx: pending filter drifted from the board filter it must '
          'complement')

    branch = extract(core_src, "if (entry.kind === 'mission-pending') {",
                     "\n              }")
    check('the pending row is findable in the render loop', bool(branch),
          'views/core.jsx: no mission-pending branch — every check below '
          'runs against an empty slice')
    if branch:
        title_line = next((l for l in branch.splitlines()
                           if 'cal-title' in l), '')
        check('a pending row says it STARTS, never that it "wraps up" — '
              'that phrase is reserved for a mission already in flight '
              '(checked on the rendered title itself, not the branch\'s own '
              'comment, which uses the same words to explain the contrast)',
              'starts' in title_line and 'wraps up' not in title_line,
              title_line)
        check('a pending row is pilled SCHEDULED, never RUNNING — that '
              "class already means something else on this same view",
              'SCHEDULED' in branch and 'RUNNING' not in branch,
              branch)
        check('the pending row keys off the SCHEDULE id, not a mission id '
              '— it has no mission yet',
              "'pending-' + s.id" in branch,
              branch)

    # ── §3: live — a real serve.py, a real POST, a real GET ──────────────
    print('\n[live: a real serve.py, a real POST/GET round trip]')
    tmp = Path(tempfile.mkdtemp(prefix='cal-night-pending-'))
    (tmp / 'hq').mkdir()
    base, kill = boot(tmp / 'hq')
    try:
        future_start = int(time.time() * 1000) + 2 * DAY
        status, res = http_post(base + '/missions/schedule', {
            'topic': 'Repro: future night shift schedule',
            'agentId': 'test_agent', 'agentName': 'Test Agent',
            'startAt': future_start, 'recurrence': 'once',
            'durationMs': 3600000, 'intervalMs': 600000,
        })
        check('scheduling a mission 2 days out succeeds',
              status == 200 and res.get('ok') is True, (status, res))

        gstatus, gres = http_get(base + '/missions/scheduled')
        check('the schedule reaches /missions/scheduled',
              gstatus == 200 and len(gres.get('schedules', [])) == 1,
              (gstatus, gres))
        check("...and 'running' is empty — it has not started, which is "
              "precisely the case nightShiftBoard's own filter drops",
              gres.get('running') == [], gres)

        live = run_js(harness + '''
const res = %s;
const out = fromPoll(res.schedules, res.running);
out.groups = fileOnCalendar(out.pending);
console.log(JSON.stringify(out));
''' % json.dumps(gres))

        check('fed through the REAL app.jsx poll logic, the live schedule '
              'produces an empty board (the pre-fix reality: nothing '
              'anywhere)',
              live['board'] == [], live['board'])
        check('...and a real pending entry, carrying the topic that was '
              'actually POSTed',
              len(live['pending']) == 1
              and live['pending'][0]['topic'] == 'Repro: future night shift schedule'
              and live['pending'][0]['nextRunAt'] == future_start,
              live['pending'])
        check('...which files onto the REAL CalendarView day-grouping at '
              'the correct day — the calendar now says something about a '
              'mission that has not started yet',
              len(live['groups']) == 1
              and live['groups'][0][1][0]['kind'] == 'mission-pending'
              and live['groups'][0][1][0]['sched']['id'] == res['schedule']['id'],
              live['groups'])
    finally:
        kill()

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
