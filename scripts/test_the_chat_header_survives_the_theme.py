#!/usr/bin/env python3
"""The room you are standing in has to be legible in every palette.

Measured 2026-09-03 on a live office (127.0.0.1:8894) in the SHIPPED
DEFAULT — night mode, no theme class:

    .monitor .bezel   color rgb(34,21,12)  on  rgb(13,15,30)   ratio 1.07
    .composer-mini    color rgb(93,67,50)  on  rgb(16,18,31)   ratio 2.05

The chat panel's header names the room — "DIRECT" — and it was simply not
on screen. Only the smaller "YOU & CAFRESOHQ" under it showed, faintly. The
"Delegate" button beside Send was nearly as bad. A screenshot before and
after confirms both.

The mechanism is that the surface and its text are themed in two different
places. `body.night .bezel` flips the BACKGROUND to #0d0f1e and says nothing
about the colour, which stayed pinned to `--brand-coffee` — the LIGHT
palette's near-black.

styles.css has two families of colour token:

  · `--brand-*`  the master palette. NO palette block redefines these, so
                 they are theme-invariant by construction.
  · `--ink` / `--paper` / `--rule`  legacy aliases which `:root` defines AS
                 the brand tokens, and which every palette block overrides.

A rule that paints text with `--brand-*` on a surface the theme can move has
opted out of the theme system. The fix points the chat header at `--ink`,
which is an IDENTITY in the default light theme — `:root` literally says
`--ink: var(--brand-coffee)` — so the light office is unchanged, and every
other palette starts working for free.

This file holds:

  1. the premise — no palette block themes the brand tokens, and the legacy
     aliases really are defined from them, which is what makes the swap safe
  2. the five repaired rules never go back to brand ink
  3. a ratchet on the rest: 39 rules still paint brand ink on a themable
     surface, and that number may not grow

Dark ink ON a brand ACCENT (banana, peach, plum…) is NOT the defect and is
excluded throughout — a yellow button wants near-black text in every theme.

Run: python3 scripts/test_the_chat_header_survives_the_theme.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / 'styles.css'
FAILS = []

# Brand tokens that are a SURFACE or an ACCENT to sit on. Dark brand ink over
# one of these is correct in every palette, because the fill does not move
# either — both halves are theme-invariant together.
ACCENT = (r'background(?:-color)?:\s*[^;]*var\(--brand-'
          r'(banana[a-z-]*|peach|farm-sky|link-green|plum|icp-gold|leaf|'
          r'cart-badge|coffee[0-9-]*)\)')
INK = r'color:\s*[^;]*var\(--brand-coffee'

# Post-fix measurement. A ratchet, not a target: it may fall, never rise.
BASELINE = 39

REPAIRED = [
    '.monitor .bezel',
    '.monitor .bezel .ceo-label',
    '.monitor .bezel .ceo-label .sub',
    '.composer-mini',
    '.composer-mini:hover',
]


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def rules(css):
    """(selector, body) for every declaration block. Blocks nested in an
    @media/@supports are matched on their own; the grouping line lands in the
    previous selector's text, which is harmless here because we only ever ask
    about declarations."""
    for m in re.finditer(r'([^{}]*)\{([^{}]*)\}', css):
        yield m.group(1).strip().split('\n')[-1].strip(), m.group(2)


def block(css, selector):
    """The body of one rule, found by an EXACT selector match rather than a
    substring — `.composer-mini` must not return `.composer-mini--primary`.
    Located by name so a rename fails loudly instead of silently matching
    nothing (#159)."""
    for sel, body in rules(css):
        if sel == selector or sel.rstrip(',') == selector:
            return body
    return None


def main():
    print('The chat header survives the theme')

    css = CSS.read_text(encoding='utf-8')

    # --- §1: the premise -------------------------------------------------
    palettes = re.findall(r'^body\.(night|theme-[a-z]+(?:\.night)?)\s*\{',
                          css, re.M)
    check('the palettes this has to survive are still here',
          len(set(palettes)) >= 5,
          'styles.css: found %r — fewer palette blocks than the five this '
          'file was written against' % sorted(set(palettes)))

    themed_brand = []
    for sel, body in rules(css):
        if not re.match(r'^body\.(night|theme-)', sel):
            continue
        themed_brand += re.findall(r'(--brand-[a-z0-9-]+)\s*:', body)
    check('no palette block themes the brand tokens — which is exactly why '
          'painting with them opts out of the theme',
          not themed_brand,
          'styles.css: %r are now theme-dependent. That is a fine design, '
          'but it invalidates the reasoning below — re-derive it before '
          'raising the ratchet' % sorted(set(themed_brand)))

    root = block(css, ':root') or ''
    for alias, brand in (('--ink', '--brand-coffee'),
                         ('--ink-2', '--brand-coffee-2'),
                         ('--ink-3', '--brand-coffee-3'),
                         ('--rule', '--brand-rule'),
                         ('--paper', '--brand-paper')):
        check('`%s` is still defined as `%s` in :root — the swap is an '
              'identity in the light office' % (alias, brand),
              re.search(r'%s:\s*var\(%s\)' % (alias, brand), root) is not None,
              'styles.css :root: %s no longer aliases %s, so the repaired '
              'rules now RENDER DIFFERENTLY in the default theme'
              % (alias, brand))

    # --- §2: the repaired rules ------------------------------------------
    check('the night override that caused this is still there — the surface '
          'moves, so the text must too',
          re.search(r'body\.night \.bezel\s*\{[^}]*background:', css)
          is not None,
          'styles.css: `body.night .bezel` no longer repaints the header. If '
          'the surface stopped moving, re-check whether these rules still '
          'need themed ink')

    for selector in REPAIRED:
        body = block(css, selector)
        check('`%s` is findable' % selector, body is not None,
              'styles.css: renamed or gone — every check on it would pass '
              'against nothing')
        if body is None:
            continue
        check('`%s` paints text the theme can move' % selector,
              not re.search(INK, body),
              'styles.css: back to brand ink — invisible in night at ratio '
              '1.07. %r' % body.strip()[:120])

    hover = block(css, '.composer-mini:hover') or ''
    check('...and the hover fill moves with it, rather than staying a '
          'hardcoded light wash under dark-theme ink',
          'var(--paper' in hover and not re.search(r'background:\s*hsl\(',
                                                   hover),
          'styles.css .composer-mini:hover: %r' % hover.strip()[:120])

    # --- §3: the ratchet -------------------------------------------------
    offenders = [sel for sel, body in rules(css)
                 if re.search(INK, body) and not re.search(ACCENT, body)]
    check('the count of rules still opting out of the theme has not grown',
          len(offenders) <= BASELINE,
          '%d rules paint brand ink on a themable surface, baseline is %d. '
          'New ones: this is the defect this file is about — use --ink / '
          '--ink-2 / --ink-3. Offenders now: %r'
          % (len(offenders), BASELINE, offenders[:8]))
    if len(offenders) < BASELINE:
        print('  note   the ratchet can come down: %d < %d — lower BASELINE '
              'in this file' % (len(offenders), BASELINE))
    for selector in REPAIRED:
        check('`%s` is out of that set for good' % selector,
              selector not in offenders,
              'it is back on the list')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
