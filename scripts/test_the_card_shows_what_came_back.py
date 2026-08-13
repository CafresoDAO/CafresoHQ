#!/usr/bin/env python3
"""The job finished and the office never showed you what it produced.

`result` is the deliverable — the text a coworker actually wrote. The done
handler stamps it on the task alongside `completedAt` and `completedBy`.
All three had zero readers. The only code that touched `result` was the
delete confirmation:

    Delete "…"? Your coworker's work on it will be lost.

so the office warned the boss they were about to lose work it had never
once let them look at. The DONE column was a wall of titles.

Measured on a live floor before the fix: a done task carrying a 320-char
Q3 summary rendered as `title / assignee / HIGH` and nothing else.

Two smaller things fell out of the same audit:

* `progressLog` was the last of the three write-only task fields. Every
  `[TASK_PROGRESS: …]` note went into a ten-entry array and a toast, and
  the array was never read.
* Clicking a task card toggles `expanded`, and `expanded` only un-clamps
  `-webkit-line-clamp` on the title and detail. For a card with a short
  title and no detail — most cards — the click did nothing at all.
  Measured: 173px before, 173px after, identical text. Putting the result
  and the history behind that click gives the affordance something to do.

Run: python3 scripts/test_the_card_shows_what_came_back.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURES = ROOT / 'features.jsx'
WORKLOG = ROOT / 'app' / 'worklog.jsx'
STYLES = ROOT / 'styles.css'
APP = ROOT / 'app.jsx'
FAILS = []

T0 = 1_000_000
MIN, HOUR, DAY = 60000, 3600000, 86400000


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


def block(src, marker, span=1400):
    """The JSX around `marker`, for the source-level assertions. features.jsx
    cannot be run here without a JSX transform, so the render checks are
    reads of the real source rather than measurements of real output — the
    live half is recorded in the ledger entry instead of implied here.

    Returns '' rather than raising when the marker is gone: deleting the
    whole block is the most likely regression, and a traceback there would
    replace every named check below with a stack trace."""
    i = src.find(marker)
    if i < 0:
        return ''
    return src[max(0, i - 200):i + span]


def main():
    print('a finished job has to show what came of it')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    feats = FEATURES.read_text(encoding='utf-8')
    wl = WORKLOG.read_text(encoding='utf-8')
    styles = STYLES.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')

    # ── 1. when it finished — run for real ──────────────────────────────
    body = '\n'.join(ln for ln in wl.split('\n')
                     if not ln.startswith('import ') and not ln.startswith('export '))
    out = run(body + """
const R = {};
R.hours   = finishedLabel({ completedAt: %d }, %d);
R.fresh   = finishedLabel({ completedAt: %d }, %d);
R.days    = finishedLabel({ completedAt: %d }, %d);
R.unknown = finishedLabel({ status: 'done' }, %d);
R.noTask  = finishedLabel(null, %d);
R.skew    = finishedLabel({ completedAt: %d }, %d);
console.log(JSON.stringify(R));
""" % (T0, T0 + 2 * HOUR, T0, T0 + 30 * 1000, T0, T0 + 3 * DAY,
       T0, T0, T0 + HOUR, T0))

    check('a finished job says how long ago', out['hours'] == '2h ago',
          str(out['hours']))
    check('...and does not say "just now ago"', out['fresh'] == 'just now',
          f"{out['fresh']!r} — durationLabel already returns a phrase that "
          'reads as a time; bolting "ago" onto it produces nonsense')
    check('days read as days', out['days'] == '3 days ago', str(out['days']))
    check('an unstamped finish says nothing rather than guessing',
          out['unknown'] is None,
          f"{out['unknown']!r} — tasks predating completedAt must stay quiet, "
          'the same rule sittingFor follows about createdAt')
    check('a missing task says nothing', out['noTask'] is None)
    check('a clock-skewed future stamp says nothing', out['skew'] is None,
          str(out['skew']))

    # ── 2. the deliverable reaches the card ─────────────────────────────
    check('the card renders the result at all', 't.result &&' in feats,
          'features.jsx: nothing read `result` — that was the defect')
    res = block(feats, 't.result && (()')
    check('...in a tc-detail, which is what un-clamps on expand',
          re.search(r'className="tc-detail"[\s\S]{0,80}String\(t\.result\)', res)
          is not None,
          'the class is load-bearing, not cosmetic: `.task-card.expanded '
          '.tc-detail` is the rule that turns three clamped lines into the '
          'whole deliverable, and it is the only reason clicking a card does '
          'anything at all')
    check('...and the CSS rule it depends on is still there',
          re.search(r'\.task-card\.expanded[^{]*\.tc-detail\s*\{[^}]*line-clamp:\s*unset',
                    styles) is not None,
          'styles.css: without this rule the result is permanently truncated '
          'to three lines and the card click goes back to being a no-op')
    check('the result is not truncated in JS as well',
          'String(t.result)}' in res and 'String(t.result).slice' not in res,
          'a slice here would clip the deliverable before CSS ever got the '
          'chance to reveal it on expand')

    # ── 3. …credited to whoever actually finished it ────────────────────
    check('the name comes from completedBy, not the assignee',
          re.search(r'agents\.find\(x => x\.id === t\.completedBy\)', res)
          is not None,
          'the card can be reassigned after the fact; crediting the current '
          'holder would be the office inventing a fact it does not have (§4)')
    check('...and an unknown finisher gets no name rather than a wrong one',
          re.search(r"by \?[^\n]*finished this[\s\S]{0,40}:\s*'finished'", res)
          is not None, res[-400:])

    # ── 4. what they did on the way — the last write-only field ─────────
    check('the card renders progressLog at all', 't.progressLog ||' in feats,
          'features.jsx: the notes reached a toast and a ten-entry array '
          'nobody opened')
    log = block(feats, "const log = (t.progressLog || [])")
    check('empty notes are dropped, not rendered as bullets',
          'filter(p => p && p.note)' in log, log[:300])
    check('collapsed shows only the most recent note',
          'log.slice(-1)' in log,
          'a card carrying ten notes would otherwise bury the board')
    check('collapsed shows no notes at all once there is a result',
          re.search(r'if \(!open && t\.result\) return null;', log) is not None,
          'once the job produced something, the result is the answer and the '
          'notes are history — they stay one click away')
    check('the "+N earlier" count is derived from what is hidden',
          'log.length - 1' in log and 'log.slice(-1)' in log,
          'the counter and the slice have to agree, or the card advertises a '
          'history that is not there — the one claim on this surface that '
          'can be a lie rather than an omission')
    check('...and only appears when something really is hidden',
          re.search(r'!open && log\.length > 1 &&', log) is not None, log[-400:])
    check('expanding shows every note', "open ? log : log.slice(-1)" in log,
          log[:300])

    # ── 5. the field still has a writer, or none of this renders ────────
    check('progressLog is still written by the progress handler',
          re.search(r'progressLog: log\.slice\(-10\)', app) is not None, 'app.jsx')
    check('completedBy and completedAt are still stamped on done',
          'completedAt: Date.now()' in app and 'completedBy: agent.id' in app,
          'app.jsx')

    print()
    if FAILS:
        print(f'what came back: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('what came back: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
