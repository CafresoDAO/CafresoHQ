#!/usr/bin/env python3
"""Tripwire: no invented numbers on boss-facing surfaces.

Two bugs of the same shape shipped and survived for months, both on
surfaces §6 renamed specifically to be honest:

  · Payroll multiplied every agent's tokens by ONE hardcoded rate
    (0.0000015), so a free local Ollama was billed $0.0533 and a flat-rate
    subscription hire was billed per word.
  · A FUEL gauge filled toward a hardcoded 1,000,000-token ceiling that
    nothing sets and nothing enforces — a bar with no scale, reading as
    "96% of your budget left" against a budget that does not exist.

Neither was caught by a unit test, because both were *plausible* numbers
in otherwise-correct code. This is a source-level guard instead: the
patterns themselves are banned from UI files, so reintroducing one fails
here with the reason attached.

Not a substitute for judgement — it catches these two shapes, not the idea.
Run: python3 scripts/test_no_invented_numbers.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Files the boss actually looks at. Excludes docs/tests, which quote the
# banned constants on purpose when explaining why they were removed.
UI_GLOBS = ['ui/*.jsx', 'views/*.jsx', 'app/*.jsx', 'modals/*.jsx',
            'app.jsx', 'features.jsx', 'missions.jsx']

BANNED = [
    (re.compile(r'0\.0000015'),
     'a hardcoded per-token price. Brains this office routes to differ by ~2 '
     'orders of magnitude, and local/subscription brains are not billed per '
     'word at all — use payrollLabel() (app/cast.jsx).'),
    (re.compile(r'/\s*1000000\s*\)\s*\*\s*100'),
     'a percentage against a hardcoded 1,000,000-token ceiling. Nothing sets '
     'or enforces that budget, so the bar has no scale — render a gauge only '
     'when a real budget is passed in.'),
    (re.compile(r'budget\s*=\s*1000000'),
     'a default token budget. It made every caller look like it had a budget '
     'when none has ever passed one — default to null and hide the bar.'),
]

# app/cast.jsx explains the payroll bug in a comment and must be allowed to
# name the constant it replaced; same for this file's own docstring.
ALLOW_COMMENTARY = {'app/cast.jsx'}


def strip_comments(text):
    """Crude but adequate: block comments and // lines. A banned constant
    quoted inside a comment is documentation, not a claim on screen."""
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    return re.sub(r'^\s*//.*$', '', text, flags=re.M)


def main():
    print('no invented numbers')
    fails = []
    checked = 0
    for glob in UI_GLOBS:
        for path in sorted(ROOT.glob(glob)):
            rel = str(path.relative_to(ROOT))
            raw = path.read_text(encoding='utf-8')
            body = strip_comments(raw) if rel in ALLOW_COMMENTARY else raw
            checked += 1
            for pattern, why in BANNED:
                for m in pattern.finditer(body):
                    line = body[:m.start()].count('\n') + 1
                    fails.append(f'{rel}:{line} — {m.group(0)!r} is {why}')

    if fails:
        for f in fails:
            print(f'  FAIL  {f}')
        print()
        print(f'no invented numbers: {len(fails)} FAILED')
        return 1
    print(f'  ok    {checked} UI files carry no hardcoded price or phantom budget')
    print()
    print('no invented numbers: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
