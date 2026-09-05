#!/usr/bin/env python3
"""A beta tester opens the app on a phone, lands on Chat, and cannot type.

The Getting-started checklist (`.gs-coach`, ui/onboarding.jsx) is expanded by
default and shows until all six steps are ticked — so the state under test is
the ONLY state a first-run tester gets.  Its step 3 is "Chat with your team",
with an "Open chat" button.

styles.css already carries three fixes for this card colliding with something
bottom-anchored.  The third one moved it off the mobile Chat composer with
`.app:has(.mobile-chat-view) .gs-coach { top: 66px; bottom: auto }`.  That rule
is right and it did not work, because the `max-height` the mobile block gives
the card is written for a card anchored at the BOTTOM.  Read from `top: 66px`
it stops being a ceiling on where the card ENDS and becomes a licence to grow
downward.

MEASURED IN A BROWSER at 375x812 (the mobile preset), on the built page, with
the checklist expanded at 0/6:

    .gs-coach          x14..288   y66..712   (height 646 = the max-height)
    composer dock      y576..740  (textarea 66.8px at rest, 140px at its cap)
    textarea           x13..362   y617..684
    overlap of the textarea covered by the card ........ 79%
    elementFromPoint(textarea centre) .................. DIV inside .gs-coach
    elementFromPoint(textarea top-left) ................ .gs-coach
    elementFromPoint(textarea 25% across) .............. BUTTON inside .gs-coach
    elementFromPoint(textarea bottom centre) ........... DIV inside .gs-coach

Four probes, four blocked — and one of them a coach BUTTON, so a tap aimed at
the message box ticked off an onboarding step instead.

AFTER the fix, same page, same viewport:

    .gs-coach          y66..503   (height 437)
    all four probes .................................... textarea
    and again with the textarea forced to its 140px cap  textarea

503 is exactly the dock's floor: the dock measured 237px tall with the textarea
pinned at its own `max-height: 140px`, and the monitor's bottom sits at
viewport - 72 (the view's tab-bar clearance).  So the cap is height-independent
rather than tuned to 812.

This test pins both halves of the fix.  Geometry needs a browser, so what is
asserted here is the CSS that produced the numbers above: the cap that keeps
the card off the dock, and the stacking order that keeps the composer hittable
whatever the dock's height turns out to be.

Run: python3 scripts/test_the_phone_onboarding_card_does_not_sit_on_the_message_box.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STYLES = ROOT / 'styles.css'
ONBOARDING = ROOT / 'ui' / 'onboarding.jsx'
FAILS = []

# Measured in the browser at 375x812 (see the docstring).
VIEW_TAB_CLEARANCE = 72   # .view/.mobile-chat-view padding-bottom on mobile
DOCK_MAX_H = 237          # composer at textarea max-height 140px + thread tabs
COACH_TOP = 66            # .app:has(.mobile-chat-view) .gs-coach { top: 66px }


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(css):
    """Drop /* … */ so this file's own prose can never satisfy a pattern."""
    return re.sub(r'/\*.*?\*/', ' ', css, flags=re.S)


def media_block(css, header_re):
    """The body of the first @media whose prelude matches, brace-balanced."""
    m = re.search(header_re, css)
    if not m:
        return None
    i = css.index('{', m.start())
    d, k = 0, i
    while k < len(css):
        if css[k] == '{':
            d += 1
        elif css[k] == '}':
            d -= 1
            if d == 0:
                break
        k += 1
    return css[i + 1:k]


def decl(block, selector, prop):
    """The value of `prop` in the LAST rule whose selector list matches."""
    found = None
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', block):
        sel = ' '.join(m.group(1).split())
        if sel != selector:
            continue
        for d in m.group(2).split(';'):
            if ':' not in d:
                continue
            k, v = d.split(':', 1)
            if k.strip() == prop:
                found = v.strip()
    return found


def eval_calc(expr, dvh, vh):
    """Numeric value of a `calc(...)` of px / dvh / vh / env(...) terms."""
    body = expr.strip()
    assert body.startswith('calc(') and body.endswith(')'), body
    body = body[5:-1]
    body = re.sub(r'env\([^()]*\)', '0', body)          # safe-area inset = 0
    body = re.sub(r'([\d.]+)dvh', lambda m: repr(float(m.group(1)) * dvh / 100), body)
    body = re.sub(r'([\d.]+)vh', lambda m: repr(float(m.group(1)) * vh / 100), body)
    body = re.sub(r'([\d.]+)px', r'\1', body)
    if not re.fullmatch(r'[\d.\s+\-*/()e]+', body):
        raise ValueError('unevaluable calc: ' + expr)
    return eval(body)  # noqa: S307 — pattern-gated arithmetic only


def main():
    print('the phone onboarding card does not sit on the message box')

    css = strip_comments(STYLES.read_text(encoding='utf-8'))
    onboard = ONBOARDING.read_text(encoding='utf-8')

    mobile = media_block(css, r'@media\s*\(max-width:\s*768px\)\s*(?=\{[^{}]*\.gs-coach\s*\{)')
    if mobile is None:
        # Several ≤768px blocks exist; take the one that styles .gs-coach.
        for m in re.finditer(r'@media\s*\(max-width:\s*768px\)', css):
            b = media_block(css[m.start():], r'@media\s*\(max-width:\s*768px\)')
            if b and '.gs-coach' in b:
                mobile = b
                break
    check('the mobile stylesheet has a ≤768px block that styles the coach',
          mobile is not None, 'no @media (max-width: 768px) block mentions .gs-coach')
    if mobile is None:
        print('\nFAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1

    # ── 1. The cap ────────────────────────────────────────────────────────
    sel = '.app:has(.mobile-chat-view) .gs-coach:not(.gs-coach-mini)'
    cap = decl(mobile, sel, 'max-height')
    check('the chat view re-caps the expanded coach', cap is not None,
          'no `%s { max-height }` on mobile; the bottom-anchored '
          '`max-height` then lets a top:66px card grow to y712 over the '
          'composer' % sel)

    if cap:
        check('the cap is measured against the DYNAMIC viewport',
              'dvh' in cap and not re.search(r'(?<![d])\b[\d.]+vh', cap),
              '`%s` — .app is height:100dvh on mobile, and vh is the LARGE '
              'viewport on a phone, so vh hands the browser-chrome height '
              'straight back to the overlap' % cap)
        check('the cap allows for the safe-area inset',
              'env(safe-area-inset-bottom' in cap, cap)

        # The card starts at COACH_TOP and must end at or above the dock's
        # floor for every viewport height, not just 812.
        worst = []
        for h in (568, 667, 740, 812, 844, 926):
            try:
                bottom = COACH_TOP + eval_calc(cap, dvh=h, vh=h)
            except (AssertionError, ValueError) as exc:
                worst.append('%dpx: %s' % (h, exc))
                continue
            dock_top = h - VIEW_TAB_CLEARANCE - DOCK_MAX_H
            if bottom > dock_top + 0.5:
                worst.append('%dpx: coach ends y%.0f, dock starts y%.0f'
                             % (h, bottom, dock_top))
        check('the capped card clears the composer dock at its FULL height',
              not worst,
              '; '.join(worst) + ' (dock measured %dpx with the textarea at '
              'its 140px max-height)' % DOCK_MAX_H)

    # ── 2. The guarantee that does not depend on the cap ──────────────────
    coach_z = re.search(r'zIndex:\s*(\d+)', onboard)
    check('the coach still declares its z-index inline', coach_z is not None,
          'ui/onboarding.jsx no longer pins .gs-coach zIndex; the constant '
          'this test compares against has moved')
    comp_z = decl(mobile, '.mobile-chat-view .composer', 'z-index')
    check('the mobile composer dock outranks the coach in the stack',
          comp_z is not None and coach_z is not None
          and int(comp_z) > int(coach_z.group(1)),
          'composer z-index=%r vs coach z-index=%r — without this the cap is '
          'the only thing standing between the tester and an untappable '
          'message box, and the cap is a measured number that a new composer '
          'row would invalidate' % (comp_z, coach_z and coach_z.group(1)))

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
