#!/usr/bin/env python3
"""The vacant unit's nameplate has to stay readable — styles.css.

`.px-room.vacant .px-plate` dims its label on purpose: a vacant unit should
read as the inactive one next to occupied rooms. But the whole vacant room is
a control (clicking it hires someone), and its label was `#9a9382` on
`#3c3a4e` — **3.60:1**, under the 4.5:1 WCAG AA floor that 8px text needs.
Track 6 of docs/strategy/06-app-update-todo.md carries contrast as an open
P1; this is one measured instance of it, found by auditing rendered text
rather than reading the palette.

Now `#b3ab98` — 4.82:1, passing, and still less than half the occupied
plate's 9.28:1, so the de-emphasis survives.

This test RECOMPUTES the WCAG ratio from the stylesheet rather than matching
the hex string. A string match would pass just as happily on a colour someone
"tidied" to a failing value, which is the failure mode that matters here.

Run: python3 scripts/test_vacant_plate_contrast.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / 'styles.css'

AA_NORMAL = 4.5

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def rgb(hex_s):
    h = hex_s.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luminance(c):
    def lin(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = c
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def main():
    print('vacant plate contrast — dimmed on purpose, still legible')
    if not CSS.is_file():
        print(f'  FAIL  missing {CSS}')
        return 1
    css = CSS.read_text(encoding='utf-8')

    m = re.search(r'\.px-room\.vacant \.px-plate \{([^}]*)\}', css)
    check('the vacant-plate rule still exists', bool(m))
    if not m:
        print('\nvacant plate contrast: 1 FAILED')
        return 1
    body = m.group(1)

    fg = re.search(r'color:\s*(#[0-9a-fA-F]{6})', body)
    bg = re.search(r'background:\s*(#[0-9a-fA-F]{6})', body)
    check('it declares both a colour and a background', bool(fg and bg), body.strip()[:70])
    if not (fg and bg):
        print('\nvacant plate contrast: FAILED')
        return 1

    fg_c, bg_c = rgb(fg.group(1)), rgb(bg.group(1))
    cr = contrast(fg_c, bg_c)
    check(f'label clears WCAG AA on the plate ({fg.group(1)} on {bg.group(1)} = {cr:.2f}:1)',
          cr >= AA_NORMAL,
          f'needs >= {AA_NORMAL}:1 for 8px text; the whole vacant room is a '
          f'control (it hires), so this label is not decoration')

    # The dimming is intentional and must survive the fix — otherwise a
    # vacant unit stops reading as the inactive one.
    occ = re.search(r'\n\.px-plate \{[^}]*?color:\s*(#[0-9a-fA-F]{6})', css)
    check('the occupied plate colour is still discoverable', bool(occ),
          'styles.css: needed to prove the vacant one is still dimmer')
    if occ:
        occ_cr = contrast(rgb(occ.group(1)), bg_c)
        check(f'vacant stays visibly dimmer than occupied ({cr:.2f} vs {occ_cr:.2f})',
              cr < occ_cr,
              'styles.css: fixing contrast by making the vacant plate as '
              'bright as an occupied one would delete the signal it carries')

    print()
    if FAILS:
        print(f'vacant plate contrast: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('vacant plate contrast: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
