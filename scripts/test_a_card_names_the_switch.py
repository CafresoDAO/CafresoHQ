#!/usr/bin/env python3
"""Pixel's card introduced an image generator by its filing.

The tick before this one stopped the front desk selling capabilities the
app does not have, which was right, and left this behind on a fresh office:

    Pixel  IMAGE GENERATION  CAN READ YOUR NOTES

Every word true. Also the worst first screen in the product. A coworker
whose entire role is image generation, introducing itself by the one
incidental thing it can do, reads as a broken hire rather than an
unconfigured one — and the boss is handed nothing to act on. That tick
recorded it deliberately rather than smoothing it over ("the fix is to make
the card say what turning the provider on would buy, not to go back to
claiming it unconditionally") and left the copy call for later. This is
later.

The card now has three registers, and the whole design is in the ordering:

  present   what the coworker can do now       "work with your files"
  smaller   the true subset, when there is one "read a web page you name"
  future    what a switch would buy            "make images once you …"

Future-tense lines are collected separately and appended, so they can never
push a present-tense one out of the three a card shows. What a coworker can
do today always outranks what it could do after a trip to Settings.

Two boundaries this pins, both of which are the honest part:

- `elevated` gets no future-tense line. It is a property of the candidate,
  fixed by which template you hire, not a switch anyone can flip — "run
  code once you elevate them" would point at a control that does not
  exist, which is the same lie the last tick removed, in the future tense.
- Absent is not false. A caller whose settings store would not open leaves
  the flag off the ctx object entirely, and that must not become "you have
  not picked an image provider" on the card of a boss who picked one
  months ago. Do-not-promise on unknown has a mirror, and this is it.

Run: python3 scripts/test_a_card_names_the_switch.py
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_the_front_desk_sells_what_exists import (  # noqa: E402
    brace_lift, run_js, strip_comments)

CAST = ROOT / 'app' / 'cast.jsx'
HIRE = ROOT / 'modals' / 'hire.jsx'
RUNTIME = ROOT / 'hq-runtime.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('a card that cannot do it yet names the switch')
    cast = CAST.read_text(encoding='utf-8')
    hire = HIRE.read_text(encoding='utf-8')
    bare = strip_comments(cast)

    # ── the shape ────────────────────────────────────────────────────────
    check('the future-tense table exists',
          re.search(r'const CAN_DO_UNLOCK = \{', bare),
          'without it a coworker whose one capability is off has nothing '
          'to say but the incidental leftovers')
    check('...and every entry in it names a condition the card knows about',
          re.search(r'const CAN_DO_UNLOCK = \{', bare) and all(
              k in brace_lift(bare, 'const CAN_DO_NEEDS = {')
              for k in re.findall(r'^\s{2}(\w+):',
                                  brace_lift(bare, 'const CAN_DO_UNLOCK = {'), re.M)),
          'an unlock line for a tool with no condition can never fire — '
          'the tool is already granted')
    # Derived, not spelled out: an unlock entry is wrong for ANY tool whose
    # condition is `elevated`, whatever the tool is called. Checking for the
    # literal word "elevated" inside the table passed happily against an arm
    # that added `code: 'run code once you elevate them'`.
    needs = brace_lift(bare, 'const CAN_DO_NEEDS = {')
    unlock_keys = re.findall(r'^\s{2}(\w+):',
                             brace_lift(bare, 'const CAN_DO_UNLOCK = {'), re.M)
    by_elevation = [k for k in unlock_keys
                    if re.search(r"^\s{2}%s:\s*'elevated'" % k, needs, re.M)]
    check('nothing gated on elevation is offered as a switch', not by_elevation,
          f'{by_elevation} — elevation is fixed by which template you hire; '
          'a card offering to unlock it points at a control that does not '
          'exist, which is the last tick\'s lie in the future tense')
    check('future-tense lines are kept in their own list',
          re.search(r'const pending = \[\];', bare)
          and re.search(r'const all = list\.concat\(pending\);', bare),
          'merged into one list, an unlock line can displace something the '
          'coworker can actually do today')
    check('an unknown fact is not reported as an off switch',
          re.search(r"const established = \(k\) => Object\.prototype\.hasOwnProperty\.call\(ctx, k\);", bare)
          and re.search(r'unlock && established\(need\)', bare),
          'a settings store that would not open would otherwise tell a '
          'boss who configured images to go and configure images')
    # ── the shelf actually reaches the copy ──────────────────────────────
    # Everything above tests canDoPhrase against fixtures I wrote. All of it
    # passed while the live office still read "Pixel · CAN READ YOUR NOTES",
    # because the shelf entry declares `tools: ['vault']` and the fixture
    # declared ['img', 'vault']. The copy was never the whole defect. A tool
    # nothing claims cannot be described by any card in the product.
    runtime = RUNTIME.read_text(encoding='utf-8')
    catalog = runtime[runtime.index('const TOOLS_CATALOG = ['):]
    catalog = catalog[:catalog.index('\n];')]
    for key in unlock_keys:
        check(f'a boss can actually tick "{key}"',
              re.search(r"id: '%s'" % key, catalog),
              'an unlock line for a tool absent from TOOLS_CATALOG can only '
              'ever fire for a hand-edited agent')
    pixel = re.search(r"name: 'Pixel',(.{0,2000}?)\n  \},", runtime, re.S)
    check('the image specialist claims the image tool',
          pixel and re.search(r"tools: \[[^\]]*'img'", pixel.group(1)),
          'this is the whole of the bug this test was written for: the card '
          'copy was right and the shelf entry never claimed img, so Pixel '
          'introduced itself by its vault access')

    check('the hire form still hands over the facts it read',
          re.search(r'f\.canMakeImages = !!\(s && s\.imageProvider\);', hire)
          and re.search(r'canDoPhrase\(t\.tools,\s*capabilityFacts\(t\)\)', hire),
          'the card and toolsForAgent must read one setting, not two')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH for the behavioural arms')
        return 1 if FAILS else 0

    scope = '\n'.join([
        brace_lift(bare, 'const CAN_DO = {'),
        brace_lift(bare, 'const CAN_DO_NEEDS = {'),
        brace_lift(bare, 'const CAN_DO_INSTEAD = {'),
        brace_lift(bare, 'const CAN_DO_UNLOCK = {'),
        brace_lift(bare, 'function canDoPhrase(tools, ctx) {'),
    ])
    # Pixel verbatim from the shelf, plus the cases that define the edges.
    cases = {
        # The measurement: a fresh office, provider unset, fact known.
        'pixel_fresh': (['img', 'vault'], {'elevated': False, 'canMakeImages': False}),
        # Provider on — the future tense must disappear entirely.
        'pixel_ready': (['img', 'vault'], {'elevated': False, 'canMakeImages': True}),
        # Settings store unreadable: the flag never arrives.
        'pixel_unknown': (['img', 'vault'], {'elevated': False}),
        # Three real capabilities plus an unavailable one. The unavailable
        # one is listed FIRST, which is the only ordering that can catch a
        # merged list — with `img` last, a merged and a separated list
        # produce the same three words and the arm sails through.
        'crowded': (['img', 'files', 'vault', 'code'],
                    {'elevated': True, 'canMakeImages': False}),
        # A coworker with nothing but an off switch still gets a route.
        'only_img': (['img'], {'canMakeImages': False}),
        # Elevation is not a switch, so there is no future tense for it.
        'not_elevated': (['code'], {'elevated': False}),
        # The smaller true claim still beats a future-tense one.
        'web_no_key': (['web'], {'canSearch': False}),
    }
    # No tool in the shipped tables has BOTH a smaller-true-claim and an
    # unlock line, so the rule that the present tense wins is currently
    # unexercised by real data — a check on it would pass no matter which
    # order the two branches sit in. Give `web` an unlock entry for one
    # extra case so the ordering is actually tested rather than assumed.
    js = ('const R = {};\n' + '\n'.join(
        'R[%s] = canDoPhrase(%s, %s);' % (json.dumps(k), json.dumps(v[0]), json.dumps(v[1]))
        for k, v in cases.items())
        + "\nCAN_DO_UNLOCK.web = 'search the web once you add a Brave key';\n"
          "R.web_both = canDoPhrase(['web'], { canSearch: false });\n"
          'console.log(JSON.stringify(R));')
    r = run_js(scope + '\n' + js)

    check('Pixel offers images, in the future tense, with the switch named',
          r['pixel_fresh'] == 'read your notes and make images once you pick an image provider',
          f"{r['pixel_fresh']} — measured before this fix as just "
          '"read your notes"')
    check('...and drops the tense entirely once a provider is picked',
          r['pixel_ready'] == 'make images and read your notes',
          f"{r['pixel_ready']} — a card still saying \"once you pick\" "
          'after the boss picked one is the same failure inverted')
    check('...and says nothing about the switch when it could not check',
          r['pixel_unknown'] == 'read your notes',
          f"{r['pixel_unknown']} — absent is not false; do not tell a boss "
          'to set something you never managed to read')
    check('a real capability is never displaced by a future one',
          r['crowded'].startswith('work with your files, read your notes and run code')
          and 'once you pick' not in r['crowded'],
          f"{r['crowded']} — three things it can do today fill the card, "
          'and the unlock line waits its turn')
    check('...and the card still admits it is truncating',
          r['crowded'].endswith('+1 more'),
          f"{r['crowded']} — the overflow count covers the unlock line too; "
          'silently dropping it would make the card look complete')
    check('a coworker with only an off switch still gets a route out',
          r['only_img'] == 'make images once you pick an image provider',
          f"{r['only_img']} — the alternative is \"talk things through\", "
          'which is §7 with the way forward removed')
    check('elevation gets no unlock line',
          r['not_elevated'] == 'talk things through',
          f"{r['not_elevated']} — there is no Settings switch for this, so "
          'naming one would be a new false claim')
    check('a tool with no unlock line keeps its smaller true claim',
          r['web_no_key'] == 'read a web page you name',
          f"{r['web_no_key']} — BROWSER_FETCH works with no key at all")
    check('...and when a tool has both, the present tense wins',
          r['web_both'] == 'read a web page you name',
          f"{r['web_both']} — something the coworker can do right now beats "
          'an errand for the boss, and the branch order in canDoPhrase is '
          'the only thing enforcing it')

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
