#!/usr/bin/env python3
"""A nightly Night Shift schedule silently drifted by one hour at every
DST transition.

`_night_scan` (serve.py) advances a `daily`-recurrence schedule's
`nextRunAt` by chaining a fixed `+= 86_400_000` (24h in ms) off the
previous UTC epoch timestamp. But the schedule's time-of-day — e.g.
missions.jsx's own default, "2:00 AM" via `nextTwoAm()`'s
`d.setHours(2, 0, 0, 0)` — is a LOCAL wall-clock hour, not a UTC one. A
calendar day that contains a DST transition is 23 or 25 real hours
long, not 24, so a constant ms offset does not preserve "2:00 AM local"
across it: the very next occurrence after a spring-forward lands at
1:00 AM local, and after a fall-back at 3:00 AM — permanently, since
nothing ever re-derives the local hour from the calendar. The Night
Shift card in missions.jsx keeps showing a plausible-looking "next:
<date>, X:XX AM" computed straight from this drifted timestamp, so a
boss has no way to notice their "2 AM" job now fires at 1 AM until they
happen to be awake to see it run at the wrong time.

Found by a background hunt agent sweeping previously-unswept areas
(Night Shift, search, hire/onboarding, exporters, other approval kinds,
chat delegate/handoff, calendar recurrence, vault graph, wallet flows,
missions/terminal lifecycle).

Fix: instead of chaining a constant ms offset, `_night_scan` now
captures the schedule's intended LOCAL hour/minute ONCE — the first
time it sees a schedule missing `dailyHour`/`dailyMinute`, read off
that schedule's current `nextRunAt` via `time.localtime()` — and
persists it on the schedule dict. Every subsequent advance reconstructs
"next calendar day at the intended hour/minute" via `time.mktime(...)`
with `tm_isdst=-1` (so the correct UTC offset for the new date's DST
state is picked up automatically), using that FIXED intended hour/
minute rather than re-reading it off the mutating `nxt`.

That distinction matters: an earlier attempt at this fix re-derived the
hour/minute from `time.localtime(nxt)` on every advance instead of
storing it separately. That looked plausible and even passed a
"lands on 2:00 AM the day after a spring-forward anchor" check — but
direct experimentation proved it was functionally identical to the
original bug. The transition day itself unavoidably forces `nxt` onto
3:00 AM (2:00 AM doesn't exist that day) — but re-deriving the hour
from THAT already-shifted `nxt` on the following day's advance means it
never returns to 2:00 AM, drifting permanently, exactly like the
original `+= 86_400_000` bug just with its onset deferred by one day.
Storing the intended hour/minute immutably is what lets the SECOND
occurrence after a transition self-correct back to 2:00 AM — which is
the property this test actually needs to check, not just the first
(transition-day) occurrence, where a forced shift is unavoidable and
correctness-neutral.

This test genuinely exercises the fixed arithmetic (not just a source
pattern match): it reproduces it standalone against a real US Eastern
DST spring-forward (2024-03-10) transition, using the TZ environment
variable + `time.tzset()`, and confirms the SECOND daily occurrence
after the transition returns to 2:00 AM local (while the flawed
re-derive-from-nxt approach stays stuck at 3:00 AM forever) — then
separately confirms serve.py's own source still contains this exact
fix (a plain `+= 86_400_000` chain, or an hour re-derived straight from
`nxt` with no stored `dailyHour`/`dailyMinute`, reappearing would
silently reintroduce the drift).

Run: python3 scripts/test_night_shift_daily_recurrence_survives_dst.py
(skips the live-arithmetic checks on platforms without time.tzset(),
e.g. native Windows — the source-pattern check still runs everywhere)
"""
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVE = ROOT / 'serve.py'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def advance_correct(nxt_ms, intended_h, intended_m):
    """The FIXED algorithm, reproduced standalone — same logic as the
    edited branch in serve.py's _night_scan. `intended_h`/`intended_m`
    are captured ONCE outside this function (mirroring `s['dailyHour']`/
    `s['dailyMinute']`) and never re-derived from `nxt_ms` itself."""
    lt = time.localtime(nxt_ms / 1000)
    return int(time.mktime((
        lt.tm_year, lt.tm_mon, lt.tm_mday + 1,
        intended_h, intended_m, 0, 0, 0, -1,
    )) * 1000)


def advance_rederive_from_nxt(nxt_ms):
    """An earlier, FLAWED fix attempt: re-derive the hour/minute from
    `nxt_ms` itself on every advance instead of storing it separately.
    Looks plausible and even self-corrects on paper, but a transition
    day forces `nxt_ms` onto a shifted hour, and reading the hour back
    off that same shifted value permanently locks it in — functionally
    identical to the original bug, just with the drift's onset deferred
    to the exact calendar day of the transition."""
    lt = time.localtime(nxt_ms / 1000)
    return int(time.mktime((
        lt.tm_year, lt.tm_mon, lt.tm_mday + 1,
        lt.tm_hour, lt.tm_min, lt.tm_sec, 0, 0, -1,
    )) * 1000)


def advance_one_local_day_BUGGY(nxt_ms):
    """The original algorithm — a flat +24h in ms, for comparison."""
    return nxt_ms + 86_400_000


def local_hour_minute(ms):
    lt = time.localtime(ms / 1000)
    return (lt.tm_hour, lt.tm_min)


def main():
    print("Night Shift's daily recurrence survives a DST transition")

    has_tzset = hasattr(time, 'tzset')
    check('this platform supports time.tzset() (needed to simulate a '
          'real US-Eastern DST transition below)', has_tzset,
          'skipping the live-arithmetic checks on this platform')

    if has_tzset:
        orig_tz = os.environ.get('TZ')
        try:
            os.environ['TZ'] = 'America/New_York'
            time.tzset()

            # 2024-03-09 02:00:00 EST (the night BEFORE the US spring-forward
            # at 2024-03-10 02:00 local, when clocks jump straight to 03:00).
            before_spring = time.mktime((2024, 3, 9, 2, 0, 0, 0, 0, -1)) * 1000
            intended_h, intended_m = local_hour_minute(before_spring)

            # First advance lands ON the transition day itself, where
            # 2:00 AM local genuinely does not exist — every algorithm,
            # correct or not, is forced onto 3:00 AM here. This is
            # expected and correctness-neutral; the real test is what
            # happens the day AFTER.
            correct_day1 = advance_correct(before_spring, intended_h, intended_m)
            rederive_day1 = advance_rederive_from_nxt(before_spring)
            buggy_day1 = advance_one_local_day_BUGGY(before_spring)
            check('sanity: the transition day itself is unavoidably '
                  '3:00 AM for the fixed algorithm too (2:00 AM does '
                  'not exist that day) — confirms this scenario is a '
                  'real DST case',
                  local_hour_minute(correct_day1) == (3, 0),
                  f'got local time {local_hour_minute(correct_day1)}')

            # Second advance is a NORMAL day after the transition — this
            # is where a genuinely correct fix must self-correct back to
            # 2:00 AM, and where the flawed re-derive-from-nxt attempt
            # (and the original bug) stay permanently stuck at 3:00 AM.
            correct_day2 = advance_correct(correct_day1, intended_h, intended_m)
            rederive_day2 = advance_rederive_from_nxt(rederive_day1)
            buggy_day2 = advance_one_local_day_BUGGY(buggy_day1)

            check('the FIXED algorithm (storing intended hour/minute '
                  'separately) self-corrects back to 2:00 AM local on '
                  'the SECOND day after the spring-forward transition',
                  local_hour_minute(correct_day2) == (2, 0),
                  f'got local time {local_hour_minute(correct_day2)}')
            check('the flawed re-derive-from-nxt attempt does NOT '
                  'self-correct — it stays stuck at 3:00 AM forever, '
                  'proving it is functionally the same bug just '
                  'deferred by one day',
                  local_hour_minute(rederive_day2) == (3, 0),
                  f'got local time {local_hour_minute(rederive_day2)} '
                  '(expected it to still be broken/stuck at 3:00 AM)')
            check('the original +86_400_000 algorithm also stays stuck '
                  'at 3:00 AM on this second day (same underlying bug)',
                  local_hour_minute(buggy_day2) == (3, 0),
                  f'got local time {local_hour_minute(buggy_day2)}')
        finally:
            if orig_tz is None:
                os.environ.pop('TZ', None)
            else:
                os.environ['TZ'] = orig_tz
            time.tzset()

    src = SERVE.read_text(encoding='utf-8')
    # #384 wrapped _night_scan's body in a `with _night_lock: ... try:`
    # section (a cross-process scan lock), shifting this branch's
    # indentation in one level (12/16 -> 16/20 spaces) without touching
    # its logic — the pin below matches the current indentation.
    m = re.search(r"if s\.get\('recurrence'\) == 'daily':\n(.*?)\n                else:\n                    s\['enabled'\] = False",
                  src, re.S)
    check("serve.py's _night_scan still has the daily-recurrence branch",
          m is not None)
    branch = m.group(1) if m else ''

    check('the daily-recurrence branch no longer chains a flat '
          '+= 86_400_000 (that literal reappearing would silently '
          'reintroduce the DST drift this fix corrects)',
          '+= 86_400_000' not in branch and 'nxt += 86_400_000' not in branch)
    check("it reconstructs the next occurrence via time.localtime()/"
          "time.mktime() instead, so it can self-correct at each DST "
          "boundary",
          'time.localtime(' in branch and 'time.mktime(' in branch
          and 'tm_mday + 1' in branch)
    check("it stores the intended hour/minute on the schedule dict "
          "('dailyHour'/'dailyMinute') instead of re-deriving them from "
          "the mutating nxt each time — the distinction that actually "
          "makes the fix self-correct instead of permanently drifting "
          "(see the module docstring for why the naive re-derive-from-"
          "nxt version is functionally the same bug)",
          "s['dailyHour']" in branch and "s['dailyMinute']" in branch)
    check("the stored hour/minute is used in the time.mktime(...) call "
          "that reconstructs nxt (not lt.tm_hour/lt.tm_min, which would "
          "silently reintroduce the flawed re-derive-from-nxt behavior)",
          re.search(r"time\.mktime\(\(\s*lt\.tm_year,\s*lt\.tm_mon,\s*"
                    r"lt\.tm_mday \+ 1,\s*s\['dailyHour'\],\s*"
                    r"s\['dailyMinute'\]", branch) is not None)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
