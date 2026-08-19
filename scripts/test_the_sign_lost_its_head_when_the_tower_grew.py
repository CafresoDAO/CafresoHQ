#!/usr/bin/env python3
"""The CAFRESO HQ neon sign was clipped at the top of the office view.

Reproduced live in the browser, then confirmed with getBoundingClientRect:
`.px-sign` is absolutely positioned inside `.px-rooftop` (height: 76px),
anchored `bottom: 10px`. The sign sprite itself is 96px tall (scale 2), so
by design it stands 30px taller than the rooftop band and is meant to rise
above the roofline — normal for building signage.

That's fine as long as `.px-building`'s `margin-top: auto` (bottom-aligns
it in `.px-scene`) has room to push the building down, leaving sky above
the rooftop for the sign's overshoot. But an auto margin resolves to 0 the
moment the building is taller than the scene — which is the ordinary case,
not an edge case: it was already true with just 4 hired coworkers. At
margin-top:0 the sign's top 30px render above `.px-scene`'s own top edge
and get clipped by its overflow-y. Measured live: signTop was 30px above
sceneTop — clipped — before the fix, and 10px+ below it — clear — after.

The fix reserves that overshoot as permanent headroom via padding-top on
`.px-scene`, so the sign never depends on the building happening to fit.

Run: python3 scripts/test_the_sign_lost_its_head_when_the_tower_grew.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / 'styles.css').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('the sign lost its head when the tower grew')

    m = re.search(r"\.px-scene\s*\{([^}]*)\}", CSS)
    check('found .px-scene', m is not None)
    scene_body = m.group(1) if m else ''

    check('.px-scene still scrolls (overflow-y: auto) — this fix must not '
          'trade the scroll cue away',
          re.search(r"overflow-y:\s*auto", scene_body) is not None)

    pad = re.search(r"padding-top:\s*(\d+)px", scene_body)
    check('.px-scene reserves top headroom via padding-top',
          pad is not None)
    if pad:
        px = int(pad.group(1))
        # The sign overshoots its rooftop band by 30px at desktop scale (96px
        # sign, 76px rooftop, bottom:10px anchor: 96-(76-10)=30). Anything
        # less than that still clips the top of the letters.
        check('padding-top is enough to clear the sign\'s 30px overshoot '
              '(96px sign - (76px rooftop - 10px bottom anchor))',
              px >= 30, 'padding-top: %dpx' % px)

    # margin-top:auto is still what bottom-aligns the building when it DOES
    # fit in the viewport — the fix adds headroom, it doesn't replace the
    # alignment mechanism.
    b = re.search(r"\.px-building\s*\{([^}]*)\}", CSS)
    check('.px-building still bottom-aligns via margin-top: auto when it fits',
          b is not None and 'margin-top: auto' in b.group(1))

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
