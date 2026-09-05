#!/usr/bin/env python3
"""A night the boss STOPPED was filed as a night that finished, and paid for.

night_runner.py writes two different fields depending on how a night ends:

  clean finish   errors 0   lastError ''                     -> a good night
  failed round   errors N   lastError '<what went wrong>'     -> a bad night
  boss stopped   errors 0   lastError 'you stopped this one'  -> NEITHER

app.jsx's XP loop keyed on `errors > 0`. A night the boss cancelled -- STOP
ALL at 6am, or deleting the schedule -- has errors 0 and iterations > 0, so
it fell through to `done`: full Jobs credit and a streak day for hours that
never ran. The three sibling surfaces that render the same rows
(features.jsx's Gazette night-shift story, missions.jsx's run-list icon and
its one-line summary) all read `lastError`, so the office showed the boss a
warning triangle over the very run its own record had filed as finished.

The ledger is append-only and the loop skips any run it has already seen by
`taskId`, so that credit could not be taken back the next morning.

`lastError` is the field to read -- it is set on a failure, on a refused
vault and on a stop, while `errors` misses the stop entirely -- but reading
it ALONE is the mirror-image bug: it docks the coworker a snag for the
boss's own decision, which is exactly what app.jsx's STOP ALL comment says
§5 forbids. So a stop is recognised first and recorded on neither side --
from the flag run_mission now stamps, and from the shape only a stop can
produce, prose with no failure count behind it. That second reading is what
covers the runs already sitting in mission-runs.json from before the flag
existed, and it costs no comparison against the sentence, whose wording
test_gazette_prints_the_correction deliberately keeps free.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}{(' -- ' + detail) if detail else ''}")
        failures.append(label)


def strip_js_comments(src):
    """Blank comment bodies, preserving newlines so offsets stay usable.

    Quote-aware, and non-negotiable here: the fix is explained in a comment
    that quotes `errors > 0` verbatim, so an unstripped sweep finds the
    documentation of the bug and reports the bug.
    """
    out, i, n, q = [], 0, len(src), None
    while i < n:
        c = src[i]
        if q:
            out.append(c)
            if c == '\\' and i + 1 < n:
                out.append(src[i + 1]); i += 2; continue
            if c == q:
                q = None
            i += 1
            continue
        if c in '"\'`':
            q = c; out.append(c); i += 1; continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2); j = n if j == -1 else j + 2
            out.append(''.join(x if x == '\n' else ' ' for x in src[i:j])); i = j; continue
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i); j = n if j == -1 else j
            out.append(' ' * (j - i)); i = j; continue
        out.append(c); i += 1
    return ''.join(out)


APP_RAW = open(os.path.join(ROOT, 'app.jsx')).read()
APP = strip_js_comments(APP_RAW)
NR = open(os.path.join(ROOT, 'night_runner.py')).read()


def lift_classifier(src):
    """Lift the real XP loop body out of app.jsx, from the poll onwards.

    Anchored on the ledger guard rather than on any one spelling of the
    outcome, so this test keeps running the REAL classifier however it is
    later reworded.
    """
    anchor = src.index("if (experienceRef.current.some(e => e.taskId === r.id)) continue;")
    end = src.index("recordXp({", anchor)
    end = src.index("});", end) + 3
    return src[anchor:end]


def main():
    check("comment stripping removed every block comment",
          APP_RAW.count('/*') > 100 and APP.count('/*') == 0,
          f"{APP_RAW.count('/*')} raw, {APP.count('/*')} left")
    check("...without moving any line", len(APP) == len(APP_RAW))

    print("1. what the runner actually writes on each of the three endings")
    # Establish the premise in the runner's own source before asserting
    # anything about the browser: `errors` is bumped only next to a real
    # error, and the stop path touches neither it nor the counter.
    stop_i = NR.index("if should_abort and should_abort():")
    stop_blk = NR[stop_i:NR.index("res = run_iteration(", stop_i)]
    check("the boss-stop path writes lastError", "run['lastError']" in stop_blk)
    check("...and does NOT bump errors -- this is the whole defect",
          "run['errors']" not in stop_blk)
    check("...and stamps a flag the browser can key on",
          "run['stoppedByBoss'] = True" in stop_blk)
    err_i = NR.index("if res['error']:")
    err_blk = NR[err_i:NR.index("else:", err_i)]
    check("a failed round writes BOTH errors and lastError",
          "run['errors'] += 1" in err_blk and "run['lastError']" in err_blk,
          "if this ever stops being true, `lastError` alone is not a superset")
    check("a fresh run starts clean on all three fields",
          "'errors': 0," in NR and "'lastError': ''," in NR
          and "'stoppedByBoss': False," in NR)

    print("2. the classifier itself, lifted from app.jsx and run")
    try:
        body = lift_classifier(APP)
    except ValueError as e:
        print(f"FAILED: could not lift the XP loop ({e})")
        return 1
    check("the lifted code is the real classifier, not a stub",
          "recordXp({" in body and "r.iterations" in body)

    harness = """
function classify(r) {
  let recorded = null;
  const recordXp = (e) => { recorded = e; };
  const experienceRef = { current: [] };
  const runs = [r];
  for (const r of runs) {
    if (!r || !r.id || !(r.finishedAt > 0)) continue;
    %s
  }
  return recorded;
}
const mk = (o) => Object.assign({ id: 'run_1', agentId: 'a1', topic: 'T',
  finishedAt: 2, iterations: 4, errors: 0, lastError: '',
  stoppedByBoss: false }, o);
const STOP = 'you stopped this one \\u2014 the rest of the night did not run';
const out = (o) => { const x = classify(mk(o)); return x ? x.outcome : null; };
console.log(JSON.stringify({
  clean:      out({}),
  failed:     out({ errors: 2, lastError: 'brain refused' }),
  stopped:    out({ stoppedByBoss: true, lastError: STOP }),
  stoppedOld: out({ lastError: STOP }),
  stoppedEarly: out({ stoppedByBoss: true, lastError: STOP, iterations: 0 }),
  vaultShut:  out({ errors: 1, iterations: 0,
                    lastError: 'the vault is not reachable' }),
  neverRan:   out({ iterations: 0 }),
  countNoProse: out({ errors: 3, lastError: '' }),
  kind:       (classify(mk({})) || {}).kind,
  taskId:     (classify(mk({})) || {}).taskId,
}));
""" % body

    tmp = tempfile.mkdtemp(prefix='night-outcome-')
    r = {}
    try:
        p = os.path.join(tmp, 'c.mjs')
        with open(p, 'w') as fh:
            fh.write(harness)
        proc = subprocess.run([shutil.which('node') or 'node', p],
                              capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            print("  FAIL node harness errored: " + proc.stderr.strip()[:400])
            failures.append("node harness")
        else:
            r = json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if r:
        check("a clean night is credited", r.get('clean') == 'done',
              repr(r.get('clean')))
        check("...as a mission, keyed on the run id so it is credited once",
              r.get('kind') == 'mission' and r.get('taskId') == 'run_1')
        check("a night with failed rounds is a snag", r.get('failed') == 'snag',
              repr(r.get('failed')))
        check("A NIGHT THE BOSS STOPPED IS NOT FILED AS DONE",
              r.get('stopped') != 'done', repr(r.get('stopped')))
        check("...and is not docked as a snag either -- the boss stopped it",
              r.get('stopped') is None, repr(r.get('stopped')))
        # Runs written to mission-runs.json before the flag existed carry the
        # sentence and nothing else. They are still on disk and still poll
        # through this loop every 15 seconds.
        check("a stop logged before the flag existed is read the same way",
              r.get('stoppedOld') is None, repr(r.get('stoppedOld')))
        check("a stop before the first round is silent too",
              r.get('stoppedEarly') is None, repr(r.get('stoppedEarly')))
        # errors 1 / iterations 0: run_mission's own vault-not-ready exit.
        # `iterations > 0` must not be what decides this one.
        check("a night that never started because the vault was shut is a snag",
              r.get('vaultShut') == 'snag', repr(r.get('vaultShut')))
        check("a run that finished without ever starting records nothing",
              r.get('neverRan') is None, repr(r.get('neverRan')))
        # The mirror of the stop shape. `errors` is still read, so a row
        # carrying a count and no prose -- what older fixtures and any
        # future caller that forgets the sentence produce -- is not
        # silently downgraded to a clean night.
        check("a failure counted but not described is still a snag",
              r.get('countNoProse') == 'snag', repr(r.get('countNoProse')))

    print("3. the classifier agrees with the surfaces that draw the same rows")
    # The disagreement WAS the bug: one row, two verdicts, on two screens.
    for fname, label in (('features.jsx', "the Gazette's night-shift story"),
                         ('missions.jsx', "the run list")):
        src = strip_js_comments(open(os.path.join(ROOT, fname)).read())
        check(f"{label} reads lastError", 'r.lastError' in src)
    check("the XP loop reads the same field the surfaces do",
          'r.lastError' in body,
          '`errors` alone cannot see the ending all three of them can')
    check("...and no longer decides the whole night on `errors` alone",
          not re.search(r'outcome\s*=\s*\(?r\.errors\s*>\s*0', body))
    # The wording of the stop sentence has to stay free (the rule
    # test_gazette_prints_the_correction pins). Recognising the stop by
    # matching its prose would have quietly taken that freedom away.
    check("...without comparing against the boss-stop sentence",
          'you stopped this one' not in body, repr(body[-200:]))

    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures[:6]))
        return 1
    print("PASS: a cancelled night is not a finished one")
    return 0


if __name__ == '__main__':
    sys.exit(main())
