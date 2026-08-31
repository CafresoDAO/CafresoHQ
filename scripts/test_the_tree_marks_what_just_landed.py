#!/usr/bin/env python3
"""The tree gave no answer to "did anything land since I last looked?"

The Library is where coworkers file deliveries, and every row looked
the same age: a deck filed a minute ago and a note untouched since
spring were pixel-identical. The boss's only move was opening files
one by one to check.

Now a file updated within the last day carries a small ● (with an
accessible "Updated in the last day" label — it's information, not
decoration). _isFresh owns the decision: ms mtimes are the contract,
second-resolution mtimes from a lesser backend are normalized rather
than silently never-fresh, a minute of clock skew into the future
still counts, and no mtime just means no dot. Verified live: a
just-filed note showed the dot, the three-day-old brief did not.

Run: python3 scripts/test_the_tree_marks_what_just_landed.py
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, opener):
    i = src.index(opener)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise SystemExit('unbalanced braces lifting ' + opener)


HARNESS = r'''
%s
const NOW = 1788191663588;                    // any fixed ms instant
const H = 3600000, D = 86400000;
console.log(JSON.stringify({
  justNow: _isFresh(NOW - H, NOW),
  edgeIn: _isFresh(NOW - D + H, NOW),
  tooOld: _isFresh(NOW - D - H, NOW),
  seconds: _isFresh(Math.floor((NOW - H) / 1000), NOW),
  skew: _isFresh(NOW + 30000, NOW),
  farFuture: _isFresh(NOW + D, NOW),
  none: _isFresh(undefined, NOW) || _isFresh(0, NOW),
}));
'''


def main():
    print('the tree marks what just landed')
    core = (ROOT / 'views' / 'core.jsx').read_text(encoding='utf-8')
    fn = brace_lift(core, 'function _isFresh(mtime, now) {')
    p = subprocess.run(['node', '-e', HARNESS % fn], capture_output=True,
                       text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    out = json.loads(p.stdout.strip().split('\n')[-1])

    check('an hour-old file is fresh', out['justNow'] is True)
    check('fresh right up to the day boundary', out['edgeIn'] is True)
    check('a day-and-change is not "just landed"', out['tooOld'] is False)
    check('second-resolution mtimes are normalized, not never-fresh',
          out['seconds'] is True)
    check('a minute of clock skew into the future still counts',
          out['skew'] is True)
    check('a far-future mtime is bad data, not news', out['farFuture'] is False)
    check('no mtime means no dot, not a crash', out['none'] is False)

    check('the dot rides the file row with its label',
          '_isFresh(n.mtime, Date.now())' in core
          and 'title="Updated in the last day"' in core
          and 'aria-label="Updated in the last day"' in core)

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
