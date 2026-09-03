#!/usr/bin/env python3
"""A day heading has to say when.

The Calendar's headings printed a weekday and a date and stopped — no year,
and no line between a day that has happened and a day that has not.

Reproduced 2026-09-03 on a live office (127.0.0.1:8896) seeded with one
running mission on a 5-day duration, one task from Aug 13, and one from
Sep 2 of the PREVIOUS year:

    Tue, Sep 8    🔬 Competitor pricing sweep — stopped
    Thu, Aug 13   Research brief: …
    Tue, Sep 2    Last year's kickoff notes

Two lies in three lines.

  · "Tue, Sep 8" is five days out — a forecast, at the TOP of a view whose
    tag reads "your business by day", with nothing saying it has not
    happened. The row under it is written in the past tense.
  · "Tue, Sep 2" is 2025, rendered character-for-character the way 2026
    would be. A correctly sorted list therefore reads as scrambled: Sep 8,
    Aug 13, Sep 2. The only tell was the weekday — Sep 2 is a Tuesday in
    2025 and a Wednesday in 2026 — which is not what anyone reads a date
    for.

The sort is not the defect and this file does not ask for it to change.
What it holds:

  1. Today, Tomorrow and Yesterday are named, because those are the days a
     boss checks by name
  2. a day in the future is MARKED as one, on the heading, in words
  3. a day outside the current year carries its year, and one inside it
     does not — the noise that got the year dropped in the first place
  4. the day math is done at local noon, so it survives a DST boundary
  5. the heading stays readable: `.cal-day-head.ahead` may not paint a
     pattern through the date

`dayLabel` is lifted out of views/core.jsx and executed under Node against
a pinned `officeDate`, so this drives the real branch logic.

Run: python3 scripts/test_the_calendar_says_which_day_it_means.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / 'views' / 'core.jsx'
CSS = ROOT / 'styles.css'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def component(src, name):
    m = re.search(r'^function %s\(' % re.escape(name), src, re.M)
    if not m:
        raise SystemExit('no `function %s(` in views/core.jsx' % name)
    nxt = src.find('\nfunction ', m.end())
    return src[m.start():nxt if nxt != -1 else len(src)]


def lift(src, name, where):
    """`const <name> = …;` to its depth-0 semicolon. Located by NAME — a
    locator pinned to the body reports a rename as a regression and hands
    back an empty slice that satisfies any negative check (#159)."""
    m = re.search(r'\bconst %s = ' % re.escape(name), src)
    if not m:
        raise SystemExit('no `const %s = ` in %s' % (name, where))
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


def css_rule(src, selector):
    i = src.find(selector + ' {')
    if i == -1:
        i = src.find(selector + '{')
    if i == -1:
        return None
    return src[i:src.find('}', i) + 1]


def main():
    print('The calendar says which day it means')

    core = CORE.read_text(encoding='utf-8')
    css = CSS.read_text(encoding='utf-8')
    view = component(core, 'CalendarView')
    check('the CalendarView component is findable', bool(view.strip()),
          'every check below would run against an empty slice')

    day_label = lift(view, 'dayLabel', 'CalendarView')

    # --- §1: the labels, driven ------------------------------------------
    harness = '\n'.join([
        # The office runs on the boss's clock, not UTC (app/artifacts.jsx).
        # Pinned here so "today" is an input rather than the wall clock.
        'let TODAY = "2026-09-03";',
        'const officeDate = () => TODAY;',
        'const OUT = [];',
        'for (const [label, today, key] of CASES) {',
        '  TODAY = today;',
        '  ' + day_label,
        '  OUT.push([label, dayLabel(key)]);',
        '}',
        'console.log(JSON.stringify(OUT));',
    ])

    # (label, today, day key, exact text or None, ahead, year must show)
    CASES = [
        ('today is named', '2026-09-03', '2026-09-03', 'Today', False, False),
        ('tomorrow is named — and is still the future',
         '2026-09-03', '2026-09-04', 'Tomorrow', True, False),
        ('yesterday is named', '2026-09-03', '2026-09-02', 'Yesterday',
         False, False),

        # The measured rows.
        ('the measured forecast: a mission wrapping in five days',
         '2026-09-03', '2026-09-08', None, True, False),
        ('the measured past day', '2026-09-03', '2026-08-13', None,
         False, False),
        ('the measured trap: the same month and day, a year earlier',
         '2026-09-03', '2025-09-02', None, False, True),

        ('a day next year carries its year AND is marked ahead',
         '2026-09-03', '2027-01-04', None, True, True),
        ('January of the current year does not carry it',
         '2026-09-03', '2026-01-01', None, False, False),
        ('nor does December of the current year, ahead though it is',
         '2026-09-03', '2026-12-31', None, True, False),

        # Both sides are built at local noon, so a 23- or 25-hour day cannot
        # round the difference to 0 or 2. US DST ends Nov 1 2026.
        ('a DST boundary does not turn tomorrow into today',
         '2026-11-01', '2026-11-02', 'Tomorrow', True, False),
        ('...nor yesterday into the day before',
         '2026-11-01', '2026-10-31', 'Yesterday', False, False),
        ('...and the spring-forward side too', '2026-03-08', '2026-03-09',
         'Tomorrow', True, False),
    ]

    harness = 'const CASES = %s;\n' % json.dumps(
        [[c[0], c[1], c[2]] for c in CASES]) + harness

    proc = subprocess.run(['node', '--input-type=module', '-e', harness],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr.strip()[:2000])
        raise SystemExit('the lifted dayLabel did not run under node')
    got = json.loads(proc.stdout.strip().splitlines()[-1])

    for case, (_l, res) in zip(CASES, got):
        label, today, key, want_text, want_ahead, want_year = case
        if want_text:
            check('%s — the words' % label[:58], res['text'] == want_text,
                  'got %r for %s (today %s)' % (res['text'], key, today))
        check('%s — future or not' % label[:58], res['ahead'] == want_ahead,
              '%s is marked ahead=%r with today=%s'
              % (key, res['ahead'], today))
        year = key[:4]
        check('%s — the year' % label[:58],
              (year in res['text']) == want_year,
              'got %r, year %s should%s appear'
              % (res['text'], year, '' if want_year else ' not'))

    # The rule, over every case: a named day never also prints a date, and
    # every unnamed day prints something a human can locate in a month.
    for case, (_l, res) in zip(CASES, got):
        named = res['text'] in ('Today', 'Tomorrow', 'Yesterday')
        check('%s — a heading is either a name or a date, never both'
              % case[0][:52],
              named or bool(re.search(r'\d', res['text'])),
              'got %r' % res['text'])

    # --- §2: the surface -------------------------------------------------
    check('the heading takes its class from the same value it takes its '
          'words from',
          re.search(r"'cal-day-head' \+ \(label\.ahead \? ' ahead' : ''\)",
                    view) is not None,
          'views/core.jsx: the ahead class is computed separately from the '
          'label, so the two can disagree about the same day')
    check('...and a future day says so in words, not only in styling',
          re.search(r'\{label\.ahead && <span className="cal-ahead">'
                    r'([^<]+)</span>\}', view) is not None,
          'views/core.jsx: nothing renders `cal-ahead` — a boss reading the '
          'date alone is back where they started')
    m = re.search(r'className="cal-ahead">([^<]+)<', view)
    if m:
        check('...and the words say the day has not happened, not merely '
              'that it is soon',
              'HAPPENED' in m.group(1).upper()
              or 'YET' in m.group(1).upper()
              or 'AHEAD' in m.group(1).upper(),
              'the chip reads %r' % m.group(1))
    check('the old year-less, tense-less formatter is gone',
          not re.search(r'const fmt = \(k\)', view),
          'views/core.jsx: `fmt` is still there — two formatters, one of '
          'them the one this file exists about')
    check('"today" still comes from the office clock, not UTC',
          'officeDate()' in day_label and 'toISOString' not in day_label,
          'views/core.jsx: dayLabel derives today from UTC, so west of it '
          'the calendar names the wrong day (see the officeDate scar in '
          'app/artifacts.jsx)')
    check('both sides of the day arithmetic are built at local noon',
          day_label.count("T12:00:00") == 2,
          'views/core.jsx: a DST day is 23 or 25 hours long; anchoring at '
          'midnight makes tomorrow round to today')

    # --- §3: the heading stays readable ----------------------------------
    ahead = css_rule(css, '.cal-day-head.ahead')
    check('a future heading is painted differently from a settled one',
          ahead is not None,
          'styles.css: no `.cal-day-head.ahead` rule — the words carry it '
          'alone')
    if ahead:
        check('...and does not run a pattern under the date',
              'repeating-linear-gradient' not in ahead
              and 'url(' not in ahead,
              'styles.css: %r — the first pass used hazard stripes and they '
              'cut straight through "Tue, Sep 8" in night mode' % ahead)
        check('...and overrides the settled fill rather than inheriting it',
              'background' in ahead,
              'styles.css: %r' % ahead)
    chip = css_rule(css, '.cal-day-head .cal-ahead')
    check('the chip is a chip — it does not wrap the heading onto two lines',
          chip is not None and 'white-space: nowrap' in chip,
          'styles.css: %r' % chip)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
