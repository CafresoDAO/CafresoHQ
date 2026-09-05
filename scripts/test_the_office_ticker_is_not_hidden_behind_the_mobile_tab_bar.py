#!/usr/bin/env python3
"""The office ticker sat entirely underneath the fixed mobile tab bar, and
the building drew straight over it on a short phone.

Two faults, one strip of screen.

1. Clearance. Both mobile blocks in styles.css reserve bottom room for the
   fixed `.mobile-tabbar` by padding the scrolling container of each
   primary tab (base 72px, standalone/PWA 80px). Every tab was named
   except Office: its container is `.office-wrap` (app.jsx ~6645), not a
   `.view-*`, so it was the one primary tab missing from both lists. The
   ticker (`ui/office.jsx` ~1805) is the last thing in that column, so it
   is what landed in the reserved-for-nothing strip. Measured live at
   375x812: `.ticker` ran 770.0 -> 804.0 against a tab bar at 742.0, and
   `document.elementFromPoint` at the ticker's own coordinates returned
   `BUTTON.mtab` — the tab bar — not the ticker. `.view-area` did not
   scroll there (scrollHeight == clientHeight == 760), so the office's
   activity feed was not merely below the fold; it was unreachable.

2. The 420px floor. Adding the padding alone is not enough, because the
   phone block also gave `.pxhq` `min-height: 420px`. `.pxhq` is already
   `flex: 1` inside `.office`, so the floor buys nothing when there IS
   room and overflows when there is not. On a 375x667 phone (iPhone SE)
   the office only had ~328px to give: `.pxhq` measured 285.1 -> 705.1
   while its own container `.office.pxhq-root` ended at 613.0. The
   building hung 92px past its parent and painted over the ticker at
   625.0 -> 659.0 — and that was BEFORE any clearance was reserved.
   Padding the wrap without touching the floor just pushes the collision
   further up the column.

Fix: `.office-wrap` joins both clearance selector lists, and the phone's
`.pxhq` floor becomes `min-height: 0` so the flex line can actually
shrink (`max-height: 62vh` still caps it on tall phones).

Re-measured after the fix. 375x812: ticker 706.0 -> 740.0, clear of the
742.0 tab bar, `elementFromPoint` at it returns `DIV.ticker`. 375x667:
ticker 561.0 -> 595.0 against a 597.0 tab bar, `elementFromPoint`
returns `DIV.ticker`, and `.pxhq` now ends at 547.0 inside a container
that ends at 549.0 — no overhang. #338's meeting door survives both:
scrolled to the bottom of `.px-scene`, `elementFromPoint` at the door's
centre returns `DIV.px-sp px-meetdoor clickable` at 812 and at 667.

Run: python3 scripts/test_the_office_ticker_is_not_hidden_behind_the_mobile_tab_bar.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / 'styles.css'
APP = ROOT / 'app.jsx'
OFFICE = ROOT / 'ui' / 'office.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(css):
    return re.sub(r'/\*.*?\*/', '', css, flags=re.S)


def mobile_blocks(css):
    out = []
    for m in re.finditer(
        r'@media \(max-width: 768px\)|@media all and \(display-mode: standalone\)', css
    ):
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
    return out


def rule_bodies(block, member):
    """Every rule body whose selector LIST names `member` as one of its
    comma-separated parts. Not a substring test — a mention inside some
    longer selector, or in prose, must not count."""
    bodies = []
    for m in re.finditer(r'([.\w,\s>*:()-]+?)\{([^{}]*)\}', block):
        parts = [p.strip() for p in m.group(1).split(',')]
        if member in parts:
            bodies.append(m.group(2))
    return bodies


def main():
    print('The office ticker is not hidden behind the mobile tab bar')

    raw = CSS.read_text(encoding='utf-8')
    css = strip_comments(raw)
    app = APP.read_text(encoding='utf-8')
    office = OFFICE.read_text(encoding='utf-8')

    # --- premises: the shapes this bug is made of are still in the source ---
    check('the Office tab still renders its column as "office-wrap"',
          'className="office-wrap"' in app,
          'app.jsx: rename this and Office drops out of the clearance '
          'lists below exactly the way it was missing from them before')
    check('the office still ends its column with the ticker',
          'className="ticker"' in office,
          'ui/office.jsx: the ticker is what came to rest in the strip '
          'the tab bar covers')

    blocks = mobile_blocks(css)
    check('found the mobile media blocks', bool(blocks))

    # --- fault 1: Office was absent from both clearance lists ---
    base = next((b for b in blocks if 'calc(72px' in b and '.view,' in b), None)
    check('found the base-mobile clearance block (72px)', base is not None)
    if base is not None:
        check('.office-wrap is in the base-mobile clearance selector list',
              any(re.search(r'padding-bottom:\s*calc\(72px', b)
                  for b in rule_bodies(base, '.office-wrap')),
              'styles.css: without this the ticker sits under .mobile-tabbar')

    pwa = next((b for b in blocks if 'calc(80px' in b and '.mobile-chat-view' in b), None)
    check('found the standalone/PWA clearance block (80px)', pwa is not None)
    if pwa is not None:
        check('.office-wrap is in the standalone/PWA clearance list too',
              any(re.search(r'padding-bottom:\s*calc\(80px', b)
                  for b in rule_bodies(pwa, '.office-wrap')),
              'fixing only one block leaves the other viewport class '
              'stranded — the installed app is the one people keep open')

    # --- fault 2: the 420px floor that the clearance would have collided with ---
    phone = '\n'.join(b for b in blocks if 'max-width: 768px' in b)
    pxhq = rule_bodies(phone, '.pxhq')
    check('the phone still has a .pxhq sizing rule', bool(pxhq))
    check('the phone gives .pxhq no fixed pixel floor',
          not any(re.search(r'min-height:\s*\d+px', b) for b in pxhq),
          'styles.css: a px floor on a flex:1 box is not a floor, it is an '
          'overflow — 420px overhung its parent by 92px on a 667px phone')
    check('the phone lets the .pxhq flex line shrink (min-height: 0)',
          any(re.search(r'min-height:\s*0\b', b) for b in pxhq),
          'styles.css: `flex: 1` cannot shrink below its content without '
          'this, so the building grows back past the ticker')
    check('the phone still caps .pxhq with max-height',
          any(re.search(r'max-height:\s*\d', b) for b in pxhq),
          'styles.css: dropping the floor must not also drop the cap, or '
          'the office eats a tall phone whole')

    # --- regression guards ---
    desktop = re.search(r'(?<!\S)\.pxhq\s*\{([^{}]*)\}', css)
    check('the desktop .pxhq rule still keeps its own min-height',
          desktop is not None
          and re.search(r'min-height:\s*\d+px', desktop.group(1)) is not None,
          'styles.css: the floor is correct off the phone — this fix must '
          'not reach the desktop rule')
    check('#338 is intact: the phone still flexes .px-scene, not 100%',
          any(re.search(r'flex:\s*1', b) for b in rule_bodies(phone, '.px-scene'))
          and any(re.search(r'height:\s*auto', b)
                  for b in rule_bodies(phone, '.px-scene')),
          'styles.css: the scene must still end where .pxhq ends, or the '
          'lobby door goes back into the dead strip')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
