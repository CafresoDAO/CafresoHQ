#!/usr/bin/env python3
""""RUNNING", and directly underneath it, "paused on reload — resume to continue".

Two fields on a mission speak to the boss from the card: `lastError`, set
when a round fails, and `pauseNote`, set when the mission was stopped for a
reason that is not a failure -- a page reload, or the boss's own STOP. The
comment above the card records that `pauseNote` was once written by two
paths and read by none. The fix wired it up behind `&& !m.lastError`.

That gate was reasoning about the GLYPH -- don't stamp a boss-stop with the
⚠ row, which is for things that went wrong. It became suppression, because
`lastError` was never cleared while a mission lived. One failed round in a
mission's entire history hid its pause note permanently.

Measured live on two missions paused by the same reload, side by side:

    ⚠ that brain is not signed in yet — add it in Settings, or give this…
    paused on reload — resume to continue

Both needed the same click. The card that said so was the one WITHOUT an
old error. The other sent the boss off to sign in a brain that had nothing
to do with why it was stopped -- the suppressed line was the one carrying
the way forward, and the surviving line actively misdirected.

Pulling on it found the same fields had no lifecycle at all:

  · `onResumeMission` reset `errors: 0` -- plainly meaning "clean slate" --
    and left both fields the boss READS untouched. A mission resumed one
    click earlier rendered status RUNNING with "paused on reload — resume
    to continue" beneath it, and a ⚠ from a round that was over.
  · `onStopMission`, the per-card ■ STOP, wrote no note at all. Only STOP
    ALL did. The more common of the two stops was the silent one.

Run: python3 scripts/test_a_paused_mission_says_why.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
MISSIONS = ROOT / 'missions.jsx'
FAILS = []

# A mission that failed a round and kept going, then was stopped. This is
# the state every path below starts from, and the state the old gate made
# unreadable.
FIXTURE = {
    'id': 'm1', 'status': 'running', 'errors': 1,
    'lastError': 'that brain is not signed in yet — add it in Settings',
    'startedAt': 1000, 'lastIterationAt': 4000, 'endedAt': None,
}
# ...and the same mission after a reload paused it. RESUME must be checked
# from HERE, not from FIXTURE: a running mission has no pauseNote to leave
# behind, so testing resume from the running state cannot see the symptom
# this file is named for.
PAUSED = dict(FIXTURE, status='paused', endedAt=4000,
              pauseNote='paused on reload — resume to continue')


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift(src, name):
    """Cut a `const <name> = …;` statement out of app.jsx, whole."""
    i = src.index('const %s = ' % name)
    # These are all single statements ending at the first `: m));` / `m));`
    # line — take to the next top-level `const ` at the same indent instead,
    # which does not depend on counting brackets.
    j = src.index('\n  const ', i + 10)
    return src[i:j]


def run(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from app.jsx')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('a paused mission has to say why, and a running one must not claim to be paused')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    app = APP.read_text(encoding='utf-8')
    miss = MISSIONS.read_text(encoding='utf-8')

    # ── 1. the transitions, run as themselves ───────────────────────────
    # The real statements out of app.jsx, driven through a fake setMissions
    # that just captures the updater. Asserting on the resulting mission is
    # worth more than asserting the field names appear in a literal.
    harness = """
const RUNNING = %s;
const PAUSED  = %s;
let out = null, feed = RUNNING;
const setMissions = (fn) => { out = fn([feed]); };
%s
%s
const R = {};
onStopMission('m1');   R.stopped = out[0];
feed = PAUSED;
onResumeMission('m1'); R.resumed = out[0];
console.log(JSON.stringify(R));
""" % (json.dumps(FIXTURE), json.dumps(PAUSED),
       lift(app, 'onStopMission'), lift(app, 'onResumeMission'))
    R = run(harness)
    stopped, resumed = R['stopped'], R['resumed']

    check('the per-card STOP leaves a note saying the boss did it',
          bool(stopped.get('pauseNote')),
          f'{stopped.get("pauseNote")!r} — only STOP ALL used to write one, so '
          'the stop a boss reaches for more often was the silent one')
    check('...naming them, not the coworker',
          'you stopped' in str(stopped.get('pauseNote', '')).lower(),
          stopped.get('pauseNote'))
    check('...and it still pauses',
          stopped.get('status') == 'paused', stopped.get('status'))

    check('RESUME clears the note about being stopped',
          not resumed.get('pauseNote'),
          f'{resumed.get("pauseNote")!r} — this is the one measured live: a '
          'card reading RUNNING with "paused on reload — resume to continue" '
          'underneath it, one click after the boss resumed it')
    check('RESUME clears the snag from the run that stopped',
          not resumed.get('lastError'),
          f'{resumed.get("lastError")!r} — `errors: 0` was already reset here, '
          'which says what resume was meant to be; the two fields the boss '
          'actually reads were the ones left behind')
    check('...and resume really resumes',
          resumed.get('status') == 'running' and resumed.get('errors') == 0
          and resumed.get('endedAt') is None,
          f'{resumed.get("status")!r} / errors={resumed.get("errors")!r}')

    # ── 2. the reload scrub still explains itself ───────────────────────
    m = re.search(r'const missionsOnLoad = React\.useCallback\([\s\S]*?\), \[\]\);', app)
    check('the reload scrub is still one statement', bool(m), 'app.jsx')
    if m:
        scrubbed = run("""
const React = { useCallback: (f) => f };
%s
console.log(JSON.stringify(missionsOnLoad([%s])[0]));
""" % (m.group(0), json.dumps(FIXTURE)))
        check('a mission paused by a reload says so',
              bool(scrubbed.get('pauseNote')) and scrubbed.get('status') == 'paused',
              f'{scrubbed.get("pauseNote")!r} / {scrubbed.get("status")!r}')
        check('...and says what to do about it',
              'resume' in str(scrubbed.get('pauseNote', '')).lower(),
              f'{scrubbed.get("pauseNote")!r} — a stopped mission with no route '
              'forward is the half of §7 that gets dropped first')

    # ── 3. no path can pause a mission in silence ───────────────────────
    # The property that matters, stated over every transition rather than
    # per-transition: after any of them, the card has SOMETHING to print.
    for label, mission in (('the per-card STOP', stopped),
                           ('the reload scrub', scrubbed if m else stopped)):
        check(f'{label} leaves the card something to say',
              bool(mission.get('pauseNote') or mission.get('lastError')),
              f'{label}: a paused card with neither field renders a stopped '
              'mission and no reason anywhere on it')

    # ── 4. the card prints both, in the right order ─────────────────────
    # `!m.lastError` is the defect itself; the ORDER is the fix's other half,
    # since the pause note is about the mission now and the error is history.
    gate = re.search(r'\{m\.pauseNote && !m\.lastError', miss)
    check('the pause note is not gated on the absence of a snag',
          not gate,
          'missions.jsx: `{m.pauseNote && !m.lastError && …}` — lastError is '
          'never cleared while a mission lives, so this hides the pause note '
          'permanently after a single failed round')
    i_pause = miss.find('{m.pauseNote &&')
    i_err = miss.find('{m.lastError &&')
    check('both lines are rendered at all',
          i_pause > 0 and i_err > 0, f'pauseNote@{i_pause} lastError@{i_err}')
    check('the pause note comes first',
          0 < i_pause < i_err,
          'missions.jsx: the pause note is why the mission is stopped RIGHT '
          'NOW and carries the click that fixes it; the snag is from a round '
          'that already ended')
    check('an old snag beside a pause note is marked as old',
          re.search(r"m\.pauseNote \? 'earlier: ' : ''", miss) is not None,
          "missions.jsx: without this the ⚠ reads as the current reason, "
          'which is exactly how the boss got sent to sign in a brain that '
          'was not why the mission stopped')

    # ── 5. the auto-pause path is not left mute ─────────────────────────
    # It writes no pauseNote, which is correct — it pauses BECAUSE of errors,
    # so lastError is the true reason. Pinned so the fallback stays.
    ap = re.search(r"status: 'paused', endedAt: Date\.now\(\), lastError: x\.lastError \|\| '([^']+)'", miss)
    check('an auto-pause always has a reason to show',
          bool(ap),
          'missions.jsx: the three-errors auto-pause writes no pauseNote — '
          'right, since the errors ARE the reason — so its lastError fallback '
          'is the only thing standing between it and a mute card')

    print()
    if FAILS:
        print(f'a paused mission: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('a paused mission: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
