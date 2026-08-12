#!/usr/bin/env python3
""""Missions when they wrap" — the calendar dropped them the moment they did.

The Calendar's tag promises "your business by day · tasks when raised ·
missions when they wrap", and its empty state promises a research mission
"lands here, on the day it's due to wrap up". The filter said:

    if (!m || m.status !== 'running' || !m.startedAt || !m.durationMs) continue;

So the view showed the one thing that had NOT happened yet — a projected
wrap — and dropped the thing that had. A four-hour mission could finish at
3pm and leave no trace on the day it finished, in the view whose entire job
is answering "what did we get done today". The ledger recorded this half as
unverified ("no mission has run in this office"); it could not have passed.

Underneath it was a data gap, which is why the honest version could not
simply be rendered: **no terminal transition recorded a time.** A mission
flipped to done/paused/error and the office never learned when. There are
EIGHT such transitions across two files, and the eighth was found by driving
the app rather than reading it (`onStopAll` sets status inline).

The load-scrub is deliberately different and must stay different: a mission
found 'running' at page load stopped when the PAGE died, which may have been
hours earlier, so it stamps `lastIterationAt` — the last moment the run is
known to have been alive — never `Date.now()`, which would file the run
under whenever the boss next opened the app.

Run: python3 scripts/test_calendar_missions.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / 'views' / 'core.jsx'
MISS = ROOT / 'missions.jsx'
APP = ROOT / 'app.jsx'
ART = ROOT / 'app' / 'artifacts.jsx'
CSS = ROOT / 'styles.css'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract(text, start_marker, end_marker):
    i = text.find(start_marker)
    if i < 0:
        return None
    j = text.find(end_marker, i)
    return text[i:j + len(end_marker)] if j >= 0 else None


def run_js(body):
    """Run the REAL officeDate + the REAL mission-grouping loop under node."""
    office = extract(ART.read_text(encoding='utf-8'),
                     'function officeDate(now) {', '\n}')
    loop = extract(CORE.read_text(encoding='utf-8'),
                   '    for (const m of missions) {', '\n    }')
    if not office or not loop:
        raise SystemExit('could not extract officeDate / the mission loop')
    # The REAL loop, wrapped in a callable. Nothing here restates its rules:
    # if the shipped filter changes, this harness changes with it.
    harness = office + '''
const out = new Map();
const push = (ts, entry) => {
  const key = officeDate(new Date(ts));
  if (!out.has(key)) out.set(key, []);
  out.get(key).push(entry);
};
function collect(missions) {
  out.clear();
''' + loop + '''
  return [...out.entries()].map(([day, items]) =>
    [day, items.map(e => ({ done: e.done, at: e.at }))]);
}
''' + body
    proc = subprocess.run(['node', '--input-type=module', '-e', harness],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('calendar missions — a run that finished is business that happened')
    for f in (CORE, MISS, APP, ART, CSS):
        if not f.is_file():
            print(f'  FAIL  missing {f}')
            return 1
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    core = CORE.read_text(encoding='utf-8')
    miss = MISS.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')

    # ── Behaviour: the real loop, over the four mission shapes ──────────
    HOUR = 3600_000
    out = run_js('''
const R = {};
const DAY = 86400000, HOUR = 3600000;
// A fixed LOCAL wall-clock moment: 11:30 PM tonight. West of UTC this is
// already "tomorrow" in UTC, which is the bug class this guards.
const late = new Date(); late.setHours(23, 30, 0, 0);
const lateMs = late.getTime();

const mk = (o) => Object.assign({ id: 'm1', topic: 't', agentId: 'a',
  startedAt: lateMs - 2 * HOUR, durationMs: 4 * HOUR, intervalMs: 300000 }, o);

R.running  = collect([mk({ status: 'running' })]);
R.doneAt   = collect([mk({ status: 'done',   endedAt: lateMs })]);
R.paused   = collect([mk({ status: 'paused', endedAt: lateMs })]);
R.errored  = collect([mk({ status: 'error',  endedAt: lateMs })]);
R.noEndedAt= collect([mk({ status: 'done' })]);
R.lateMs   = lateMs;
R.projected= lateMs - 2 * HOUR + 4 * HOUR;

/* Timezone probe, kept SEPARATE from the cases above — one of those failed
   for an unrelated reason (its projected wrap legitimately lands on the next
   local day) and blamed UTC for it.

   Two probes, because one is not enough: at 23:30 the UTC date differs only
   WEST of UTC, and at 00:30 only EAST of it. Any non-zero offset moves at
   least one. `discriminating` records whether this machine can see the bug
   at all — at UTC+0 the check is vacuous and must say so rather than pass. */
const pad = (n) => String(n).padStart(2, '0');
// Computed with plain local getters, NOT officeDate — the first version of
// this asked officeDate what the local date was and then checked the
// grouping against it, so reverting officeDate to UTC made both sides agree
// and the probe passed a broken build.
const localKeyOf = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const probe = (h) => {
  const d = new Date(); d.setHours(h, 30, 0, 0);
  const ms = d.getTime();
  const grouped = collect([mk({ status: 'done', endedAt: ms, startedAt: ms - HOUR })]);
  return { local: localKeyOf(new Date(ms)),
           utc: new Date(ms).toISOString().slice(0, 10),
           groupedUnder: grouped[0][0] };
};
R.late = probe(23);
R.early = probe(0);
R.discriminating = (R.late.local !== R.late.utc) || (R.early.local !== R.early.utc);
console.log(JSON.stringify(R));
''')

    check('a finished mission is not dropped',
          len(out['doneAt']) == 1 and out['doneAt'][0][1][0]['done'] is True,
          f"got {out['doneAt']!r} — the whole defect: `status !== 'running' → skip` "
          'erased every completed run from the day it completed')
    check('...and so are stopped and failed runs',
          len(out['paused']) == 1 and len(out['errored']) == 1,
          f"{out['paused']!r} / {out['errored']!r} — a run that went wrong is still "
          'business that happened')
    check('a finished mission is filed at endedAt, not its projected wrap',
          out['doneAt'][0][1][0]['at'] == out['lateMs'] != out['projected'],
          f"got {out['doneAt'][0][1][0]['at']} — projected was {out['projected']}; "
          'filing a real end under a forecast is the same tense error as the copy')
    check('a running mission is still filed at its PROJECTED wrap',
          out['running'][0][1][0]['at'] == out['projected']
          and out['running'][0][1][0]['done'] is False,
          f"got {out['running']!r} — the forecast row is useful and must survive; a "
          'fix that only kept finished runs would trade one gap for another')
    check('a pre-endedAt mission falls back instead of vanishing',
          len(out['noEndedAt']) == 1
          and out['noEndedAt'][0][1][0]['at'] == out['projected'],
          f"got {out['noEndedAt']!r} — missions that ended before the field existed "
          'must still appear')

    # ── The timezone class: this view groups by the BOSS'S day ──────────
    if not out['discriminating']:
        print('  SKIP  timezone probe is vacuous at UTC+0 — this machine cannot '
              'tell a local grouping from a UTC one')
    else:
        for label in ('late', 'early'):
            p = out[label]
            check(f'a mission that ended at {"23:30" if label == "late" else "00:30"} '
                  'groups under the local day',
                  p['groupedUnder'] == p['local'],
                  f"grouped under {p['groupedUnder']!r}; local={p['local']!r} "
                  f"utc={p['utc']!r} — a task raised at 11:30 PM once showed up on "
                  'tomorrow, and a mission row is no different')

    # ── The data gap: EVERY terminal transition must record a time ──────
    terminal = re.findall(r"^.*status: ?'(?:done|paused|error)'.*$", miss + '\n' + app, re.M)
    unstamped = [t.strip()[:90] for t in terminal
                 if 'endedAt' not in t and 'missionsOnLoad' not in t]
    check('every terminal mission transition records when it ended',
          not unstamped,
          f'{len(unstamped)} without endedAt: {unstamped!r} — a status flip with no '
          'timestamp is why the calendar had nothing honest to file')
    check('the early-finish path stamps it too',
          re.search(r"endedAt: completed \? Date\.now\(\)", miss) is not None,
          'missions.jsx: a mission that calls itself finished early still ended')

    # ── ...except the load-scrub, which must NOT claim the load time ────
    scrub = extract(app, 'const missionsOnLoad', '), []);')
    check('the load-scrub uses lastIterationAt, never Date.now()',
          scrub is not None and 'lastIterationAt' in scrub and 'Date.now()' not in scrub,
          f'app.jsx missionsOnLoad: {scrub!r} — this run died with the page, maybe '
          'hours ago; stamping the load time files it under whenever the boss next '
          'opened the app')

    # ── Copy and styling: a forecast must not look like an outcome ──────
    check('a finished row does not say "wraps up"',
          "entry.done ? verb : 'wraps up'" in core,
          'views/core.jsx: "wraps up" over a run that ended hours ago is a tense error')
    check('a failed run is not dressed as a success',
          re.search(r"error:\s*\[.*FAILED", core) is not None
          and re.search(r"done:\s*\[.*DONE", core) is not None,
          'views/core.jsx: done/paused/error need distinct words and pills')
    check('the forward marker is removed from finished rows',
          re.search(r"\.cal-item\.cal-mission\.is-done", CSS.read_text(encoding='utf-8')) is not None,
          'styles.css: .cal-mission\'s left border means "this has not happened yet"; '
          'leaving it on a finished run contradicts the row\'s own words')
    check('the calendar\'s status pills are actually styled',
          re.search(r"\.cal-meta \.status-pill", CSS.read_text(encoding='utf-8')) is not None,
          'styles.css: .status-pill is scoped to .agent-card, so RUNNING rendered as '
          'bare text — and the pill is now what separates a forecast from an outcome')

    print()
    if FAILS:
        print(f'calendar missions: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('calendar missions: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
