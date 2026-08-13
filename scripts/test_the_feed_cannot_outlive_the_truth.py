#!/usr/bin/env python3
""""finished ✓" was filed on turns where nothing landed.

Measured on a live office: a coworker emitted an unclosed
`[MEMORY_WRITE: work/preferences.md]`, nothing was written, the vault was
empty afterwards, and the office correctly told the boss so in the chat
bubble — "nothing was saved to their memory … it is not there however it was
described above." In the same turn the activity feed recorded

    finished "Save a note in your own memory at work/p" ✓

Two office surfaces, one turn, opposite claims. And the feed is the surface
that OUTLIVES the chat: the Gazette reads it back the next morning, and the
boss scrolling a day later is nowhere near the note that contradicts it.

The cause was ordering. The row was written inside the run; the honesty
guards ran after the try/finally, in a block the row could not see. So the
row could not have known, and said ✓ anyway.

Two things had to change together. `doneLine` makes the claim conditional.
And the five guards became ONE call — `HQ.honestyNotes` — because the row
needs their answer before they are shown, and because three hand-copied
blocks had already drifted to five guards, four, and four: `unsentAsk` was
wired into the @mention path only, so a coworker who ACKed "waiting on a
teammate" with an empty delivery queue was called out there and passed in
silence on the Delegate button and on a task run. The old task-path copy
carries a comment recording the PREVIOUS round of exactly this drift, one
guard earlier.

Run: python3 scripts/test_the_feed_cannot_outlive_the_truth.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FLOOR = ROOT / 'app' / 'floor.jsx'
RT = ROOT / 'hq-runtime.jsx'
FAILS = []

GUARDS = ['unsentHandoff', 'unsentElevation', 'unsentBlocks', 'unsentAsk',
          'fabricatedRelay']


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def node(src, cases):
    text = src.read_text(encoding='utf-8')
    body = '\n'.join(ln for ln in text.split('\n')
                     if not ln.startswith('import ') and not ln.startswith('export '))
    proc = subprocess.run(['node', '--input-type=module', '-e', body + '\n' + cases],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('the feed outlives the chat, so it cannot claim more than the chat')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    app = APP.read_text(encoding='utf-8')
    code = re.sub(r'/\*[\s\S]*?\*/', '', app)
    code = re.sub(r'(?m)^\s*//.*$', '', code)

    # ── 1. the row's claim is conditional ────────────────────────────────
    out = node(FLOOR, r'''
const R = {};
R.clean   = doneLine('Save a note', 0);
R.missed  = doneLine('Save a note', 1);
R.several = doneLine('Save a note', 3);
R.noSubjectClean  = doneLine('', 0);
R.noSubjectMissed = doneLine(null, 2);
R.messy = doneLine('  Save   a\nnote  ', 0);
R.long  = doneLine('x'.repeat(80), 0);
console.log(JSON.stringify(R));
''')
    check('a turn where everything landed still reads as done',
          out['clean'] == 'finished "Save a note" ✓', out['clean'])
    check('a turn where something did not land drops the tick',
          '✓' not in out['missed'] and 'not all of it landed' in out['missed'],
          out['missed'])
    check('...and still says what it IS about',
          '"Save a note"' in out['missed'], out['missed'])
    check('the wording does not count the notes',
          out['several'] == out['missed'],
          f"{out['several']!r} vs {out['missed']!r} — the count is of NOTES, "
          'not of lost work, so printing it would invent a number the office '
          'does not have')
    check('a run with no subject keeps its own two forms',
          out['noSubjectClean'] == 'finished and reported back ✓'
          and '✓' not in out['noSubjectMissed'],
          f"{out['noSubjectClean']!r} / {out['noSubjectMissed']!r}")
    check('the subject is still squashed and capped',
          out['messy'] == 'finished "Save a note" ✓' and len(out['long']) < 60,
          f"{out['messy']!r} / {out['long']!r}")

    # ── 2. every guard is in the one table ───────────────────────────────
    rt = RT.read_text(encoding='utf-8')
    fn = re.search(r'function honestyNotes\(raw, opts\) \{[\s\S]*?\n\}', rt)
    check('honestyNotes exists', bool(fn), 'hq-runtime.jsx')
    body = fn.group(0) if fn else ''
    for g in GUARDS:
        check(f'{g} is in the shared table', g in body,
              'hq-runtime.jsx: a guard left out here is a guard no dispatch '
              'path runs — this function is the only caller now')

    # ── 3. …and no path keeps a private copy ─────────────────────────────
    # This is the check that would have caught the original drift. Three
    # copies is how unsentAsk ended up on one path of three.
    for g in GUARDS:
        stray = re.findall(r'HQ\.' + g + r'\s*\(', code)
        check(f'no dispatch path calls {g} on its own', not stray,
              f'{len(stray)} direct call(s) in app.jsx — copies drift, and '
              'the drift is silent because each copy looks complete')

    # ── 4. all three paths ask before they claim ─────────────────────────
    # Each dispatch declares a `honestyFor`; each must run it and feed the
    # result to doneLine rather than hardcoding the tick.
    check('every dispatch path builds its guards',
          len(re.findall(r'const honestyFor = ', code)) == 3,
          f"{len(re.findall(r'const honestyFor = ', code))} — @mention, "
          'Delegate and a task run are the three')
    check('...and every one of them asks before filing the row',
          len(re.findall(r'doneLine\(', code)) == 3,
          f"{len(re.findall(r'doneLine.', code))} doneLine call(s)")
    leftover = re.findall(r'"finished [^"]*✓"|\'finished and reported back ✓\'', code)
    check('no path still hardcodes the tick',
          not leftover,
          f'{leftover!r} — app.jsx: a literal ✓ is a claim made before the '
          'guards have been asked')

    # ── 5. the notes reach the row, not only the bubble ──────────────────
    # The bubble scrolls away; the feed row is what the Gazette reads back.
    check('the row carries WHICH part did not land',
          len(re.findall(r"honesty\.join\(' '\)", code)) == 3,
          "app.jsx: each row's detail should carry the notes, stripped of "
          'the italic markers the chat needs and the feed does not')

    print()
    if FAILS:
        print(f'the feed: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('the feed: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
