#!/usr/bin/env python3
"""The bottom ~46px of the office's scroll viewport was outside its own
clipping frame on a phone, and the meeting door lived there.

`.px-scene` (ui/office.jsx ~1286) is the office floor's ONE scroll
container, and it asks for `height: 100%` of `.pxhq`, which is
`overflow: hidden`. On desktop that is exact: every other child of
`.pxhq` is absolutely positioned, so the scene is the whole box.

The mobile block (`@media (max-width: 768px)`) breaks that assumption.
It pulls the Situation Wall — `.pxhq .px-hud.sit-wall`, normally an
absolutely-positioned HUD — into the flow (`position: relative`) so the
telemetry becomes a strip above the tower. The wall then eats ~46px of
`.pxhq`'s content height, but `.px-scene` still asked for the FULL
100%. Measured live at 375x812: `.pxhq` ran 285.1 -> 756.0 while
`.px-scene` ran 331.7 -> 802.5. Those last 46.5px of scroll viewport
are never painted and never hit-tested.

`.px-building` bottom-aligns itself in the scene (`margin-top: auto`),
so what came to rest in that dead strip at maximum scroll was the
LOBBY — and with it `.px-meetdoor` (ui/office.jsx ~1655), the one
control on the floor that seats the team in the meeting room. At
`scrollTop === scrollHeight - clientHeight` the door's centre measured
y=771.7, and `document.elementFromPoint` there returned `BUTTON.mtab`
— the fixed `.mobile-tabbar` — at every scroll position, never the
door. `.pxhq.has-more`'s "there is more office below" hint stayed lit
at maximum scroll, which was the honest reading of it: more office, and
no way down to it.

Fix: `.pxhq` becomes a flex column on mobile and `.px-scene` takes
`flex: 1; min-height: 0; height: auto` instead of `height: 100%`, so
the scene gets exactly the room the wall left over and its bottom edge
is `.pxhq`'s bottom edge. Re-measured after the fix: scene bottom
756.0 == `.pxhq` bottom, door 708.2 -> 742.2, `elementFromPoint` at its
centre returns `DIV.px-sp px-meetdoor clickable`, and dispatching the
click opened `.meeting-modal-body`.

Run: python3 scripts/test_the_office_floor_can_be_scrolled_all_the_way_to_the_lobby_door.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / 'styles.css'
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
    """Same block-walker the tab-bar clearance tests use, narrowed to the
    phone breakpoint."""
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
    return out


def rule_bodies(block, member):
    """Every rule body whose selector LIST names `member` as one of its
    comma-separated parts. Not a substring test — a mention inside some
    longer selector must not count."""
    bodies = []
    for m in re.finditer(r'([.\w,\s>*:()-]+?)\{([^{}]*)\}', block):
        parts = [p.strip() for p in m.group(1).split(',')]
        if member in parts:
            bodies.append(m.group(2))
    return bodies


def main():
    print('The office floor scrolls all the way down to the lobby door')

    css = strip_comments(CSS.read_text(encoding='utf-8'))
    office = OFFICE.read_text(encoding='utf-8')
    blocks = mobile_blocks(css)
    check('found the phone media block (max-width: 768px)', bool(blocks))
    phone = '\n'.join(blocks)

    # --- premises: the shapes this bug is made of are still in the source ---
    check('the office still renders its scroller as "px-scene"',
          'className="px-scene"' in office,
          'ui/office.jsx: rename this and the rules below stop applying')
    check('the lobby still carries the meeting door',
          'px-meetdoor' in office,
          'ui/office.jsx: the control that came to rest in the dead strip')
    check('the phone block still pulls the Situation Wall into the flow',
          any(re.search(r'position:\s*relative', b)
              for b in rule_bodies(phone, '.pxhq .px-hud.sit-wall')),
          'styles.css: this is what costs .pxhq its flow height — if the '
          'wall ever goes back to absolute, this whole rule pair can go')

    # --- the fix itself ---
    pxhq = rule_bodies(phone, '.pxhq')
    check('.pxhq is a flex column on the phone',
          any(re.search(r'display:\s*flex', b) for b in pxhq)
          and any(re.search(r'flex-direction:\s*column', b) for b in pxhq),
          'styles.css: without a column formatting context the scene has '
          'nothing to size against but the full 100%')

    scene = rule_bodies(phone, '.px-scene')
    check('the phone gives .px-scene a flex height instead of 100%',
          any(re.search(r'flex:\s*1', b) for b in scene)
          and any(re.search(r'min-height:\s*0', b) for b in scene),
          'styles.css: `flex: 1; min-height: 0` is what makes the scene '
          'end where .pxhq ends')
    check('the phone cancels the inherited height: 100% on .px-scene',
          any(re.search(r'height:\s*auto', b) for b in scene),
          "styles.css: the base rule's `height: 100%` wins over `flex: 1` "
          'for the definite-height case — it has to be unset here, or the '
          "scene hangs past .pxhq's overflow:hidden edge again")

    # --- regression guard: desktop is untouched ---
    base = re.search(r'(?<!\S)\.px-scene\s*\{([^{}]*)\}', css)
    check('the desktop .px-scene rule still sets height: 100%',
          base is not None and re.search(r'height:\s*100%', base.group(1)) is not None,
          'styles.css: on desktop every other child of .pxhq is absolute, '
          'so 100% is correct there and this fix must not reach it')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
