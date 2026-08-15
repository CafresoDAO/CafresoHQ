#!/usr/bin/env python3
"""A reload rewrote the story of a run that already ended.

The mount load-scrub exists for one case: a run lives in the page, so a task
still marked 'doing' at load time is a run that died with the last tab. True
when it was written — and then the settle started PARKING snags in DOING. A
card the run-end path stamps with `blockedReason` (that path is the field's
only writer) is a run that already finished; the reload killed nothing.

The scrub didn't know the difference. Reproduced live before fixing: parked
"Empty hands" in DOING reading

    ✋ Nothing came back from this run — no answer and no file.

reloaded the page, and found it in the INBOX reading

    ↩ the run stopped when the page reloaded — start it again when you want it
    ✋ Nothing came back from this run — no answer and no file.

Two contradictory stories about a single run, stacked on the one surface that
does not scroll away — and the ↩ line is simply false: nothing stopped at
reload. features.jsx's own gate comment calls "start it again" bad advice for
a job that will hit the same wall; the scrub was shipping that exact advice
onto every parked card at every refresh.

The fix is one clause: the scrub only touches a doing card WITHOUT a
`blockedReason`. A parked snag stays parked, wearing the settle's own words.

Run: python3 scripts/test_a_parked_snag_survives_the_reload.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FAILS = []

STAMP = 'the run stopped when the page reloaded — start it again when you want it'


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('a parked snag survives the reload')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    app = APP.read_text(encoding='utf-8')

    # Same lift the blocked-card suite uses: the REAL statement runs here.
    scrub = re.search(r'const tasksOnLoad = React\.useCallback\([\s\S]*?\), \[\]\);', app)
    check('the reload scrub is still one statement', bool(scrub), 'app.jsx')
    if not scrub:
        print()
        print('a parked snag: 1 FAILED — the reload scrub is still one statement')
        return 1

    R = run("""
const React = { useCallback: (f) => f };
%s
const R = {};
R.midRun  = tasksOnLoad([{ id:'t1', status:'doing', assignedTo:'a1' }])[0];
R.parked  = tasksOnLoad([{ id:'t2', status:'doing', assignedTo:'a1',
  blockedReason:'Nothing came back from this run' }])[0];
R.cleared = tasksOnLoad([{ id:'t3', status:'doing', blockedReason:'' }])[0];
R.inbox   = tasksOnLoad([{ id:'t4', status:'inbox', blockedReason:'x' }])[0];
R.done    = tasksOnLoad([{ id:'t5', status:'done' }])[0];
R.nulls   = tasksOnLoad([null, { id:'t6', status:'doing' }]);
R.notArr  = tasksOnLoad('not an array');
console.log(JSON.stringify(R));
""" % scrub.group(0))

    check('a run the reload really killed still goes back to the inbox',
          R['midRun'].get('status') == 'inbox'
          and R['midRun'].get('assignedTo') == 'a1',
          f"{R['midRun']!r} — the scrub's one legitimate job: a doing card "
          'with no blockedReason at load time IS a dead run, and leaving it '
          'in DOING claims work that is not happening')
    check('...and says why, in the exact shipped words',
          R['midRun'].get('stalledNote') == STAMP,
          f"{R['midRun'].get('stalledNote')!r} — this note is only true for a "
          'card the reload actually interrupted; its wording is pinned so it '
          'cannot drift into a claim about some other ending')
    check('a parked snag is not touched at all',
          R['parked'].get('status') == 'doing'
          and R['parked'].get('blockedReason') == 'Nothing came back from this run'
          and not R['parked'].get('stalledNote'),
          f"{R['parked']!r} — doing + blockedReason at load time is a run "
          'that ENDED (the run-end path is the field\'s only writer); the '
          'reload killed nothing, so there is nothing here to clean up')
    check('an empty reason is not a park',
          R['cleared'].get('status') == 'inbox'
          and R['cleared'].get('stalledNote') == STAMP,
          f"{R['cleared']!r} — the field is cleared to '' rather than "
          'deleted (a progress note does this), so a falsy check is the only '
          'correct one; a card mid-run when the tab closed must still scrub')
    check('cards outside DOING are not the scrub\'s business',
          R['inbox'].get('status') == 'inbox'
          and not R['inbox'].get('stalledNote')
          and R['done'].get('status') == 'done',
          f"{R['inbox']!r} / {R['done']!r}")
    check('a null entry does not crash the load',
          R['nulls'][0] is None and R['nulls'][1].get('status') == 'inbox',
          f"{R['nulls']!r}")
    check('a corrupt store loads as an empty board',
          R['notArr'] == [],
          f"{R['notArr']!r}")

    # ── the wiring, pinned ──────────────────────────────────────────────
    check('the discriminator is the parked-card guard itself',
          re.search(r"t\.status === 'doing' && !t\.blockedReason", scrub.group(0)) is not None,
          "app.jsx: the scrub must ask the same question displacedTask asks — "
          'is this card a run in flight, or a snag the settle parked?')
    check('the false note has exactly one writer, behind that guard',
          scrub.group(0).count(STAMP) == 1 and app.count(STAMP) == 1,
          'app.jsx: "the run stopped when the page reloaded" may only ever be '
          'stamped by the scrub, on a card the reload actually interrupted')

    print()
    if FAILS:
        print(f'a parked snag: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('a parked snag: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
