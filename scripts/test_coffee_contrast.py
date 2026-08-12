#!/usr/bin/env python3
"""Track 6's contrast P1: --brand-coffee-2/3 must be legible where they're used.

`docs/strategy/06-app-update-todo.md` Track 6 carries "fix `--brand-coffee-2/3`
contrast" as an open P1. Measured live on the running app — 132 coffee-2/-3
text nodes across the office floor, eight views and the Settings modal —
exactly ONE thing failed, and it was not the tokens:

    --brand-coffee-3 | .sep | 3.38:1 (need 4.5)   × 26 separators

`--brand-coffee-3`'s own definition says it was darkened "for WCAG AA 4.5:1 on
paper", and on paper it delivers: the topbar's `.crumbs .sep`, on the light
gradient, measures 5.08:1 and 4.93:1 against the two stops. The ticker is the
one DARK strip in a light app, and its separator reused the paper-tuned
tertiary — the same fault as the vacant desk plate: a token correct for one
surface, used on its opposite.

This pins both halves, because the cheap wrong fix is to lighten
`--brand-coffee-3` globally — which would fix the ticker by degrading every
paper surface the token was tuned for.

Run: python3 scripts/test_coffee_contrast.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / 'styles.css'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def hsl_to_rgb(h, s, ll):
    s, ll = s / 100.0, ll / 100.0
    c = (1 - abs(2 * ll - 1)) * s
    x = c * (1 - abs(((h / 60.0) % 2) - 1))
    m = ll - c / 2
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][int(h // 60) % 6]
    return tuple(round((v + m) * 255) for v in (r, g, b))


def parse_color(v):
    v = v.strip()
    m = re.match(r'hsl\(\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%', v)
    if m:
        return hsl_to_rgb(float(m.group(1)), float(m.group(2)), float(m.group(3)))
    m = re.match(r'#([0-9a-fA-F]{6})$', v)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return None


def lum(c):
    def f(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def ratio(a, b):
    la, lb = lum(a), lum(b)
    return round((max(la, lb) + 0.05) / (min(la, lb) + 0.05), 2)


def token(css, name):
    m = re.search(r'^\s*' + re.escape(name) + r':\s*([^;]+);', css, re.M)
    return parse_color(m.group(1)) if m else None


def main():
    print('coffee contrast — a token tuned for paper is not a token for the dark strip')
    if not CSS.is_file():
        print('  FAIL  missing styles.css')
        return 1
    css = CSS.read_text(encoding='utf-8')

    coffee2 = token(css, '--brand-coffee-2')
    coffee3 = token(css, '--brand-coffee-3')
    paper = token(css, '--brand-paper')
    paper2 = token(css, '--brand-paper-2')
    if not all((coffee2, coffee3, paper, paper2)):
        print(f'  FAIL  could not resolve tokens: {coffee2} {coffee3} {paper} {paper2}')
        return 1

    # ── The tokens themselves, on the surfaces they were tuned for ──────
    for label, fg in (('coffee-2', coffee2), ('coffee-3', coffee3)):
        for sname, bgc in (('paper', paper), ('paper-2', paper2)):
            r = ratio(fg, bgc)
            check(f'{label} on {sname} meets AA for body text',
                  r >= 4.5,
                  f'{r}:1 — Track 6 names these two tokens specifically')

    # ── The dark strip: nothing paper-tuned may be used on it ───────────
    # Anchored at line start on purpose: `body.theme-wallstreet
    # .ticker-track .line .sep` ALSO contains this selector and appears
    # first in the file, so an unanchored search reads the theme override's
    # 8-digit rgba hex and reports "unparsed" — or worse, passes the
    # has-its-own-colour check while never looking at the base rule.
    m = re.search(r'^\.ticker-track \.line \.sep\s*\{\s*color:\s*([^;]+);', css, re.M)
    check('the ticker separator has its own colour',
          m is not None and 'ink-3' not in m.group(1) and 'coffee-3' not in m.group(1),
          f'got {m.group(1).strip()!r} if matched — --ink-3 IS --brand-coffee-3, and on '
          'the ticker\'s dark backdrop it measures 3.38:1 across 26 live separators')

    if m:
        sep = parse_color(m.group(1))
        # The ticker's real painted backdrop, measured in the browser.
        TICKER_BG = (34, 21, 12)
        TICKER_TEXT = (255, 248, 238)
        check('...and it is legible on the ticker',
              sep is not None and ratio(sep, TICKER_BG) >= 4.5,
              f'{ratio(sep, TICKER_BG) if sep else "unparsed"}:1 against rgb(34,21,12)')
        check('...while still reading as a separator, not as content',
              sep is not None and ratio(sep, TICKER_TEXT) >= 2.0,
              f'{ratio(sep, TICKER_TEXT) if sep else "unparsed"}:1 against the ticker\'s '
              'own #fff8ee text — a separator that matches the news it separates has '
              'traded one legibility problem for a noise problem')

    # ── The cheap wrong fix, blocked explicitly ─────────────────────────
    # Lightening coffee-3 globally would "fix" the ticker by degrading every
    # paper surface. The paper checks above already fail if someone does it,
    # but say so by name so the failure explains itself.
    check('coffee-3 has not been lightened to paper over the ticker bug',
          ratio(coffee3, paper) >= 4.5 and ratio(coffee3, (34, 21, 12)) < 4.5,
          f'coffee-3 is {ratio(coffee3, paper)}:1 on paper and '
          f'{ratio(coffee3, (34, 21, 12))}:1 on the ticker. If the second number ever '
          'clears 4.5 the token has been dragged toward the dark strip, which is a '
          'regression for every paper surface it was tuned for — fix the SURFACE, '
          'not the token')

    print()
    if FAILS:
        print(f'coffee contrast: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('coffee contrast: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
