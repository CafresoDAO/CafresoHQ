#!/usr/bin/env python3
""""Coffee" has a full-size door on a phone, and the door has to stay open.

── What this file used to say, and why it was wrong ────────────────────────
It asserted that `onCoffee` appears in `ui/office.jsx` and NOWHERE in
`views/core.jsx`, and read that pair as proof that the only way to send a
coworker for coffee on a phone was the floor's 12×12 mug.

The grep was accurate. The inference was not. `views/core.jsx` has no
`onCoffee` because it does not need one: every roster card is
`onClick={()=>onInspect(a)}`, `onInspect` is `setInspect(a)` in app.jsx, and
`<InspectPanel>` is handed `onCoffee={onCoffee}` — the same handler the mug
calls. The panel has carried a full-width **☕ COFFEE BREAK** button, already
44px tall, the whole time. Measured at 375×812: 115×44.

This is the second time this ledger has been caught generalising from a grep
without driving the other half — see the Night Shift correction in the same
"Known open" section, where "the headline overnight feature is blocked" was
written from the Research gate and turned out to be false the moment someone
actually scheduled a night shift. Same shape, same section, five days apart.

── What was actually broken ───────────────────────────────────────────────
Driving it at 375×812 found a worse bug than the one being guessed at, and
in a different place. `.inspect` was `position: fixed` with NO height bound:

  · the panel stood **984px tall in an 812px viewport**;
  · nothing in the ancestor chain could scroll to the overflow — `.app` is
    `overflow-y: hidden`, and a fixed element does not extend the document,
    so `scrollIntoView()` on the button moved nothing;
  · **252px hung off the bottom**, and all three of the panel's action
    buttons were in it. `elementFromPoint` at the centre of 💬 MESSAGE,
    ☕ COFFEE BREAK and LET GO each returned **null**.

So the old entry reached a true-sounding conclusion ("the mug is the only
door") for an entirely wrong reason. The door existed, was correctly sized
and correctly labelled — it was 252px below the bottom of the screen.

Two floating surfaces then had to give way, and both were found by measuring
rather than by reading, because both were invisible while the row was:

  · the Apps FAB (`z-index: 321`, fixed bottom-right) stole **1221px²** of
    LET GO — 2 of 5 probes across the button returned the FAB, so the right
    ~40% of a destructive control opened the app switcher instead;
  · the receipts tray shares `--z-window` with `.inspect` by design (see the
    scale at the top of styles.css), so DOM order decided it and `app.jsx`
    renders the tray later. At 1280×800 it covered 80% of COFFEE BREAK and
    **100%** of LET GO.

── What is pinned here ────────────────────────────────────────────────────
Verified live before pinning — panel 64→730 inside 812, clear of the 742
tab bar, body scrolls (853px of content in 531px), all three buttons 44px
and hittable at all five probes; tapped COFFEE BREAK at (214, 697) and got
"COFFEE Cleared Hermes's desk". Also driven at 320×568 and 1280×800.

The checks are static, like the other views/*.jsx and styles.css suites in
this directory — these are media queries and inline styles, not exported
pure functions. Each one guards a thing that would silently re-strand the
button if it were removed:

  1. the roster reaches the panel, and the panel's button calls `onCoffee`;
  2. the panel cannot outgrow the viewport again (height bound + scroller,
     including the `min-height: 0` that makes the scroller actually work);
  3. the action row is OUTSIDE the scroller, so it cannot scroll away;
  4. nothing floats over it — the FAB stands down, the panel outranks the
     tray;
  5. the ledger says what is now true.

It still fires in both directions. Re-strand the row and (2)/(3) break;
delete the corrected ledger entry and (5) breaks; put the panel back under
the tray and (4) breaks.

Run: python3 scripts/test_coffee_reachable_on_mobile.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OFFICE = ROOT / 'ui' / 'office.jsx'
PANELS = ROOT / 'ui' / 'panels.jsx'
CORE = ROOT / 'views' / 'core.jsx'
APP = ROOT / 'app.jsx'
CSS = ROOT / 'styles.css'
DOC = ROOT / 'docs' / 'OFFICE_AS_INTERFACE.md'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def decls(css, selector):
    """The DECLARATIONS of a base (non-media, column-0) rule, comments stripped.

    Stripping matters: these rules are heavily commented, and a check like
    "this block must not name --z-dropdown" otherwise fails against prose
    explaining why the block stays BELOW --z-dropdown. Caught by
    fire-testing — the z-order check failed on its own rationale.
    """
    m = re.search(r'^' + re.escape(selector) + r'\s*\{(.*?)\}', css, re.S | re.M)
    if not m:
        return ''
    return re.sub(r'/\*.*?\*/', '', m.group(1), flags=re.S)


def flat(md):
    """Markdown with wrapping, indentation and `>` quote markers collapsed.

    The ledger hard-wraps at ~72 columns inside indented blockquotes, so any
    claim worth pinning is split across lines with `  > ` in the middle of
    it. Matching raw text therefore forces anchors short enough to be
    useless — fire-testing showed `'12×12' in doc` and `'252px' in doc`
    both survived deleting the sentence that carried them, because the
    numbers recur elsewhere in the entry. Flattening lets each check name
    the whole SENTENCE it cares about.
    """
    return re.sub(r'\s+', ' ', re.sub(r'\n\s*>?\s*', '\n', md).replace('\n', ' '))


def main():
    print('coffee on mobile — the roster door is full-size, and stays reachable')
    for p in (OFFICE, PANELS, CORE, APP, CSS, DOC):
        if not p.is_file():
            print(f'  FAIL  missing {p}')
            return 1
    office = OFFICE.read_text(encoding='utf-8')
    panels = PANELS.read_text(encoding='utf-8')
    core = CORE.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')
    css = CSS.read_text(encoding='utf-8')
    doc = DOC.read_text(encoding='utf-8')

    # ── (1) the path: roster card → panel → the same handler as the mug ────
    # Word-bounded, not `in`: a bare substring test passes against
    # `onCoffeeXX`, so it could not tell "the handler is wired" from "the
    # handler was renamed away". Kept from the original file — that part of
    # it was right, and was itself found by fire-testing.
    has_coffee = lambda s: bool(re.search(r'\bonCoffee\b', s))

    # Scoped to the MUG, not the file. `has_coffee(office)` alone was a
    # decoration: `onCoffee` also appears in OfficeView's prop list, so the
    # check survived rewiring the mug's onClick to a different handler
    # entirely. Fire-testing caught it — the mutation changed the click and
    # nothing failed.
    mug = re.search(r'px-mug[\s\S]{0,600}', office)
    check('the office floor still wires onCoffee — on the mug itself',
          bool(mug) and has_coffee(mug.group(0)),
          'ui/office.jsx: the 12×12 mug is the DESKTOP-precision path to '
          'coffee; if it lost its handler the floor stopped offering it')
    check('the roster card still opens the panel',
          bool(re.search(r'onClick=\{\(\)\s*=>\s*onInspect\(a\)\}', core)),
          "views/core.jsx: this is the phone's route to coffee — tapping a "
          'coworker opens InspectPanel. Without it the roster is a dead end '
          'and the 12×12 mug really would be the only door.')
    check('...and app.jsx hands the panel the same handler the mug calls',
          bool(re.search(r'<InspectPanel[^>]*', app, re.S)) and has_coffee(app),
          'app.jsx: InspectPanel must receive onCoffee={onCoffee} — one '
          'gesture, one handler, two surfaces')
    check('the panel button calls onCoffee and still says COFFEE BREAK',
          has_coffee(panels) and 'COFFEE BREAK' in panels,
          'ui/panels.jsx: this button IS the full-size mobile control')

    # ── (2) the panel cannot outgrow the viewport again ────────────────────
    blk = decls(css, '.inspect')
    check('.inspect carries a height bound',
          'max-height' in blk,
          'styles.css: an unbounded `position: fixed` panel is exactly how '
          'the action row ended up 252px below the fold with nothing able '
          'to scroll to it')
    check('.inspect is a flex column (head / scroller / actions)',
          'flex-direction: column' in blk and 'display: flex' in blk,
          'styles.css: the height bound only helps if one child is '
          'designated as the scroller')
    body = decls(css, '.inspect .body')
    check('.inspect .body is the scroller',
          'overflow-y: auto' in body,
          'styles.css: without this the bound clips the overflow and makes '
          'it MORE unreachable, not less')
    check('...and carries min-height: 0',
          re.search(r'min-height:\s*0', body) is not None,
          'styles.css: a flex child defaults to min-height:auto and refuses '
          'to shrink below its content — without this the panel overflows '
          'exactly as before while LOOKING like it was fixed. This is the '
          'one line whose removal is silent.')

    # ── (3) the action row is outside the scroller ─────────────────────────
    check('the action row is a sibling of .body, not its last child',
          bool(re.search(r'</div>\s*(?:\{/\*.*?\*/\}\s*)?<div className="inspect-actions">',
                         panels, re.S)),
          'ui/panels.jsx: inside .body it scrolls away, and a boss opening '
          'a coworker to STOP them should not have to scroll a performance '
          'review to find the stop')
    check('...and styles.css pins it as a non-shrinking footer',
          'flex: 0 0 auto' in decls(css, '.inspect-actions'),
          'styles.css: .inspect-actions must not be allowed to shrink')

    # ── (4) nothing floats over it ─────────────────────────────────────────
    check('the Apps FAB stands down while a review is open',
          bool(re.search(r'\{!inspect\s*&&\s*<button className="hq-mobile-fab"', app)),
          'app.jsx: the FAB is z-index 321 vs the panel\'s --z-window, so '
          'ungated it covers 1221px² of LET GO — the right ~40% of a '
          'DESTRUCTIVE button silently opening the app switcher')
    check('the panel outranks the receipts tray',
          'calc(var(--z-window) + 1)' in blk,
          'styles.css: the tray shares --z-window with .inspect by design, '
          'and app.jsx renders the tray LATER, so at equal z-index DOM '
          'order handed it the corner — 100% of LET GO at 1280×800')
    check('...without climbing over dropdowns and modals',
          '--z-dropdown' not in blk and '--z-modal' not in blk,
          'styles.css: +1 on --z-window keeps this panel below the topbar '
          'menus (350) and every modal (400), as it has always been')

    # ── (5) the ledger says what is now true ───────────────────────────────
    check('the ledger carries the corrected entry',
          '**The office floor is not touch-sized — but "coffee" always had another door.**' in doc,
          'docs/OFFICE_AS_INTERFACE.md: the floor measurements are still '
          'open and still true; what changed is the reachability claim '
          'built on top of them')
    fdoc = flat(doc)
    check('...and still cites the floor measurements',
          'the coffee mugs are **12×12**, the work-log paperstack 22×26' in fdoc
          and 'tightest gap between two of those small controls is **11px**' in fdoc,
          'docs/OFFICE_AS_INTERFACE.md: the props ARE still under 44px and '
          'Track 6 still carries that as an open P1 — this fix did not '
          'touch the art, and the ledger must not imply it did')
    check('...and records why a blanket hit-area expansion is still unsafe',
          '.px-cab' in doc and '.px-couch' in doc,
          'docs/OFFICE_AS_INTERFACE.md: the 11px cabinet/sofa gap is why '
          'the obvious fix is wrong — losing that turns the entry into an '
          'invitation to break two working controls')
    check('...and states the reachability claim it got wrong',
          '`views/core.jsx` has no `onCoffee` because it does not need one' in fdoc,
          'docs/OFFICE_AS_INTERFACE.md: the correction is the useful part — '
          'a grep over one file was read as proof about a path that runs '
          'through three. Bare "views/core.jsx in doc" does NOT test this; '
          'the string recurs and the check survived deleting the sentence.')
    check('...and records the 252px clipping that was the real bug',
          "**252px hung below the fold, and all three of the panel's actions "
          'were in it**' in fdoc,
          'docs/OFFICE_AS_INTERFACE.md: this is the measurement the fix '
          'rests on; without it the entry is a story')

    print()
    if FAILS:
        print(f'coffee on mobile: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('coffee on mobile: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
