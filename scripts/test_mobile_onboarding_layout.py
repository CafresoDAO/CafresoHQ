#!/usr/bin/env python3
"""Two bottom-anchored onboarding surfaces, one 375px screen — views + styles.

Measured live at 375×812 on the §3.6 first-run path, which §2 aims at the
"capable non-guru" — the audience most likely to be on a phone:

  · `.gs-coach` (the Getting Started checklist) ran to y798 against a mobile
    tab bar starting at y742. Step 6 "Watch them work" and its button sat
    56px underneath the bar, unreachable.
  · The coach-mark pill (app.jsx, inline `bottom:16 zIndex:45`) covered the
    checklist by 155px — its ENTIRE height. The two are always on screen
    together, because `coachMark` returns null only once the checklist is
    dismissed, so on a phone they collided by construction.
  · That pill is a single-line lozenge by design (`borderRadius: 999`). At
    375px its text + CTA + ✕ cannot fit on one line, so it wrapped, and a
    999px radius on a 155px-tall box renders as a blob.

Fixes pinned here:
  1. Both surfaces clear the 70px tab bar on mobile.
  2. The pill stands down on narrow viewports while the checklist is
     EXPANDED (the checklist already lists that step with that CTA), and
     returns once it is collapsed to its mini pill.
  3. When both are up on mobile, the variable-height pill stacks ABOVE the
     fixed-44px `.gs-coach-mini` — the only direction that needs no magic
     number for a box whose height varies with its text.
  4. `bottom` moved out of the inline styles into `.gs-coach`, because an
     inline value silently outranks the breakpoint override that fixes (1).
     The file already did exactly this for `left`, for the same reason.

Static checks — these are inline styles and media queries, not exported
pure functions (same constraint as this session's other views/*.jsx suites).
The geometry itself was verified live in the browser; see the commit.

Run: python3 scripts/test_mobile_onboarding_layout.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
ONB = ROOT / 'ui' / 'onboarding.jsx'
CSS = ROOT / 'styles.css'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(s):
    """Drop /* … */ so prose that MENTIONS a property can't look like one.
    (The card's own comment explains why `bottom` moved out — which would
    otherwise trip the very check that it did.)"""
    return re.sub(r'/\*[\s\S]*?\*/', '', s)


def mobile_block(css):
    """Every @media (max-width: 768px) block, concatenated.

    styles.css has 23 of them, so grabbing "the" first one silently searches
    the wrong 700 lines — which is exactly how this suite first came up red
    against a fix the browser had already confirmed."""
    out = []
    for m in re.finditer(r'@media \(max-width: 768px\)', css):
        i = m.start()
        depth, k = 0, css.index('{', i)
        while k < len(css):
            if css[k] == '{':
                depth += 1
            elif css[k] == '}':
                depth -= 1
                if depth == 0:
                    out.append(css[i:k + 1])
                    break
            k += 1
    return '\n'.join(out)


def rule_bodies(block, selector):
    """All bodies for `selector` in `block` — a selector may be declared more
    than once (mobile `.gs-coach` is: once for `left`, once for `bottom`)."""
    return re.findall(re.escape(selector) + r'\s*\{([^}]*)\}', block)


def any_rule_has(block, selector, pattern):
    return any(re.search(pattern, b) for b in rule_bodies(block, selector))


def main():
    print('mobile onboarding layout — checklist + coach mark on a 375px screen')
    for p in (APP, ONB, CSS):
        if not p.is_file():
            print(f'  FAIL  missing {p}')
            return 1
    app = APP.read_text(encoding='utf-8')
    onb = ONB.read_text(encoding='utf-8')
    css = CSS.read_text(encoding='utf-8')
    mob = mobile_block(css)
    check('found the max-width:768px block that owns mobile geometry', bool(mob))

    # ── (4) bottom must not be inline, or the media query can never win ────
    card = onb[onb.find('  const card = {'):]
    card = strip_comments(card[:card.find('};')])
    check("the expanded card sets no inline `bottom`",
          'bottom' not in card,
          'ui/onboarding.jsx: an inline bottom outranks the mobile override '
          'in styles.css — this is why the card sat under the tab bar')
    mini = onb[onb.find("className: 'gs-coach gs-coach-mini'"):]
    mini = strip_comments(mini[:mini.find('}, ')])
    check('the collapsed mini pill sets no inline `bottom` either',
          'bottom:' not in mini,
          'ui/onboarding.jsx: same reason as the card')
    check('.gs-coach carries the desktop bottom in the stylesheet instead',
          any_rule_has(css, '.gs-coach', r'bottom:\s*14px'),
          'styles.css: moving bottom out of the inline style means the base '
          'rule has to supply it, or desktop loses its 14px anchor')

    # ── (1) both surfaces clear the mobile tab bar ─────────────────────────
    check('.gs-coach clears the 70px tab bar on mobile',
          any_rule_has(mob, '.gs-coach', r'bottom:\s*calc\(70px'),
          'styles.css: the checklist ran 56px under the bar, burying step 6')
    check('.coach-mark clears the tab bar on mobile',
          any_rule_has(mob, '.coach-mark', r'bottom:\s*calc\(138px'),
          'styles.css: 70 bar + 14 gap + 44 mini pill + 10 — the pill stacks '
          'above the fixed-height mini pill, not under the bar')
    check('both mobile offsets respect the iOS safe area',
          mob.count('env(safe-area-inset-bottom') >= 2,
          'styles.css: a home-indicator phone eats another ~34px')

    # ── (3) the pill is a card on mobile, not a wrapped lozenge ────────────
    check('.coach-mark drops the 999px radius on mobile',
          any_rule_has(mob, '.coach-mark', r'border-radius:\s*14px'),
          'styles.css: a 999px radius on a wrapped two-line box is a blob')
    check('...and is allowed to wrap onto its own line',
          any_rule_has(mob, '.coach-mark', r'flex-wrap:\s*wrap')
          and '.coach-mark > span' in mob,
          'styles.css: the text needs its own row at 375px or the CTA is '
          'squeezed to a few characters wide')

    # ── (2) the pill stands down while the checklist is expanded ───────────
    check('app.jsx tracks whether the checklist is collapsed',
          'const [gsCollapsed, setGsCollapsed]' in app
          and 'onCollapsedChange={setGsCollapsed}' in app,
          'app.jsx: it renders BOTH surfaces, so it is the one that has to '
          'know — the state was trapped inside GettingStarted')
    check('GettingStarted reports collapse changes upward',
          'onCollapsedChange' in onb and 'if (onCollapsedChange) onCollapsedChange(v);' in onb,
          'ui/onboarding.jsx: report only — the card still owns the state')
    # This used to be gated `isNarrowViewport &&` — mobile-only. Widened
    # 2026-08-13 (scripts/test_coach_mark_desktop_overlap.py) once the same
    # collision was measured on real desktop widths too (overlap up to
    # ~1510px, not just <768px) — so this check now confirms the pill is
    # suppressed on EVERY viewport while expanded, a strict superset of the
    # phone-only behavior this test originally pinned, not a weakening of it.
    check('the coach mark is suppressed on any viewport while expanded',
          bool(re.search(r'!\(!gsDismissed && !gsCollapsed\)', app))
          and 'isNarrowViewport' not in re.search(
              r'\{!tourOpen && coachMark && [^\n]*?\(\s*\n\s*<div className="coach-mark"', app
          ).group(0),
          'app.jsx: without this the pill covers the checklist by its full '
          'height on any phone, and clips its corner on common desktop '
          'widths (measured: overlap up to ~1510px)')
    check('the coach mark carries a class so the stylesheet can reach it',
          'className="coach-mark"' in app,
          'app.jsx: it was pure inline styles, unreachable from a media query')

    print()
    if FAILS:
        print(f'mobile onboarding layout: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('mobile onboarding layout: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
