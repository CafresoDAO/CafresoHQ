#!/usr/bin/env python3
"""The office told a listening boss it had done everything twice.

The floor ticker scrolls with a `translate -50%` keyframe, which only reads
as a seamless loop if the line is two identical halves. So `segment()` is
rendered twice, deliberately, and the code has said so in a comment since it
was written.

Nothing said it to a screen reader. The second half is the same events in
the same order, with no marker distinguishing it from the first, so the
accessibility tree contains every event on the floor twice:

    Llama · picked up "Research brief: …"
    Llama · picked up "Research brief: …"
    Llama · walked onto the floor
    Llama · walked onto the floor

A sighted boss sees a loop and reads it as a loop. A listening boss is told
the office did each thing two times. Recorded during an earlier tick's DOM
inspection ("the DOM confirms two identical spans"), fixed here.

`aria-hidden` on the duplicate is the entire fix — it stays in the layout
and leaves the accessibility tree, which is exactly what a decorative copy
is. The care is in WHERE it goes. A wrapper element around half B would be
the obvious move and would break the thing the duplicate exists for:
`.ticker-track .line` is `display: flex` with a `gap: 22px`, and every item
is a direct child, so wrapping collapses half B into one flex item at the
wrong width — and the -50% translate is only a loop while both halves
measure the same. The attribute goes on the items themselves.

What this pins, then, is not "an aria-hidden exists somewhere" but the two
facts that make it correct and keep it correct: half B is muted, half A is
NOT (a card nobody can read is not an improvement), and the DOM the two
halves produce is otherwise identical.

Run: python3 scripts/test_the_ticker_says_it_once.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OFFICE = ROOT / 'ui' / 'office.jsx'
CSS = ROOT / 'styles.css'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, header):
    i = src.index(header)
    j = src.index('{', i + len(header) - 1)
    d = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces after ' + header)


def main():
    print('the ticker says each thing once')
    src = OFFICE.read_text(encoding='utf-8')
    ticker = brace_lift(src, 'function Ticker({ items, offline }) {')

    # ── the premise: still two halves, still one flex row ─────────────────
    # If either stops being true the fix is either unnecessary or wrong, and
    # this test should say which rather than passing on into a changed world.
    calls = re.findall(r'\{segment\(([^)]*)\)\}', ticker)
    check('the line is still rendered as two halves', len(calls) == 2,
          f'{calls} — one half needs no aria-hidden; three would need two')
    css = CSS.read_text(encoding='utf-8')
    check('...and they are still direct children of one flex row',
          re.search(r'\.ticker-track \.line \{[^}]*display: flex', css),
          'if .line stops being a flex row the wrapper objection goes away '
          'and this shape can be simplified — deliberately, not by accident')

    # ── which half is muted ──────────────────────────────────────────────
    check('the first half is left audible',
          calls and calls[0].strip() == "'a'",
          f'{calls} — muting both halves silences the ticker completely, '
          'which is not an accessibility fix, it is a deletion')
    check('the second half is muted',
          len(calls) > 1 and re.match(r"^'b',\s*true$", calls[1].strip()),
          f'{calls} — the duplicate is scenery and has to say so')

    # ── the attribute lands on the items, not a wrapper ──────────────────
    check('segment takes the mute flag',
          re.search(r'const segment = \(half, mute\) =>', ticker),
          'a wrapper around half B collapses it into a single flex item at '
          'the wrong width and breaks the -50% loop')
    hidden = re.findall(r'aria-hidden=\{mute \|\| undefined\}', ticker)
    check('every item in a half carries it', len(hidden) == 2,
          f'{len(hidden)} of 2 — the quote spans and the activity spans are '
          'separate maps; muting one leaves the other announced twice')
    check('...and it is undefined rather than false when audible',
          'mute || undefined' in ticker,
          'aria-hidden="false" is a real value with real meaning; the '
          'audible half should carry no attribute at all')
    check('no wrapper element sneaked back in',
          not re.search(r'<span aria-hidden="true">\s*\{segment', ticker),
          'this is the version that breaks the layout — it renders and '
          'looks almost right, which is why it needs its own check')

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
