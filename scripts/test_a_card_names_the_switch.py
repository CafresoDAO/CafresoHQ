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

  OVERTURNED 2026-08-14. That paragraph was wrong on its facts, and this
  test kept it in force for three ticks. There is a switch: every
  coworker's card in Settings → Roster carries a 🛡 File & shell access
  pxswitch, behind a danger-styled confirm, that sets exactly this flag —
  and REQUEST_ELEVATION lets a coworker ask for it mid-job, with the boss
  deciding in the approvals tray. Elevation is not fixed at hire and never
  was. So the effect of the rule was the opposite of its intent: the one
  capability in the whole table with a real, per-agent, boss-operated
  control was the only one the card refused to give a route to. §7 asks
  for a way forward; this withheld a true one out of caution about a
  false one.

  What replaces it is not the opposite opinion. An unlock line may now
  name any control, INCLUDING elevation, provided the label it prints is
  found in the settings source — so the sentence and the switch cannot
  drift apart without this test noticing. That check is what would have
  caught the original error, in either direction.
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
SETTINGS = ROOT / 'modals' / 'settings.jsx'
MEDIA = ROOT / 'modals' / 'providers.jsx'
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
    # This slot used to hold the inverse check — "nothing gated on elevation
    # is offered as a switch" — on the stated grounds that "elevation is
    # fixed by which template you hire". That was never true. Every
    # coworker's card in Settings → Roster carries a 🛡 File & shell access
    # pxswitch that calls `update({ elevated: … })` behind a danger confirm
    # (modals/settings.jsx), and REQUEST_ELEVATION exists so a coworker can
    # ask for it mid-job. So the one capability with a real, per-agent,
    # boss-operated switch was the only one the card refused to name a route
    # to, and this test held that refusal in place. Overturned 2026-08-14.
    #
    # Replaced with the check that would have caught it, and which is
    # stronger than either opinion: an unlock line may only name a control
    # whose printed label actually appears in the settings source. Same rule
    # as the labels in hq-runtime's hint table — a sentence pointing the boss
    # somewhere has to be checkable against the thing it points at, or the
    # two drift and only the boss finds out.
    UNLOCK_MUST_NAME = {
        'files':  ('file & shell access', SETTINGS),
        'code':   ('file & shell access', SETTINGS),
        # Was deliberately loose — the single word 'provider' — and the
        # looseness was itself the finding: the card said "once you pick an
        # image provider" while the Media tab printed a heading and a
        # <select> labelled PROVIDER, so the exact phrase the card promised
        # appeared nowhere a boss could read it. Tightened 2026-08-15 with
        # the rest of the 'img' work: the control is labelled IMAGE
        # PROVIDER now, so the card's words and the label match.
        'img':    ('image provider',      MEDIA),
        'wallet': ('wallet',              SETTINGS),
    }
    unlock_tbl = brace_lift(bare, 'const CAN_DO_UNLOCK = {')
    unlock_keys = re.findall(r'^\s{2}(\w+):', unlock_tbl, re.M)
    unnamed = [k for k in unlock_keys if k not in UNLOCK_MUST_NAME]
    check('every unlock line is pinned to a named control', not unnamed,
          f'{unnamed} — a new future-tense line has to say which control it '
          'is sending the boss to, so this test can go and check the control '
          'is there')
    wrong, missing = [], []
    for k in unlock_keys:
        if k not in UNLOCK_MUST_NAME:
            continue
        label, source = UNLOCK_MUST_NAME[k]
        phrase = re.search(r"^\s{2}%s:\s*'([^']*)'" % k, unlock_tbl, re.M)
        if not phrase or label not in phrase.group(1).lower():
            wrong.append((k, phrase.group(1) if phrase else None, label))
        # Comments stripped, entities decoded. Against the raw file this
        # matched the ASCII-art diagram in the comment that documented the
        # fix, not the rendered label — so renaming the switch left the
        # card still promising the old name and this check still green.
        src_txt = source.read_text(encoding='utf-8')
        src_txt = re.sub(r'/\*[\s\S]*?\*/', '', src_txt)
        src_txt = re.sub(r'^\s*//.*$', '', src_txt, flags=re.M)
        if label not in src_txt.replace('&amp;', '&').lower():
            missing.append((k, label, source.name))
    check('...and names it the way it is printed on the control',
          not wrong, f'{wrong} — (key, line, label it must contain)')
    check('...and that control really exists in the settings source',
          not missing, f'{missing} — (key, label, file searched); this is the '
          'anti-drift half: rename or delete the control and the card stops '
          'being allowed to promise it')
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
    # This loop was called 'a boss can actually tick "<id>"' and measured
    # membership in TOOLS_CATALOG, which was never the same question — the
    # four NEVER_WIRED ids are in the catalog and have never been tickable
    # by anyone. It went on passing for 'code' and 'files' after both were
    # hidden from the rendered grid on 2026-08-14, still reporting that a
    # boss could tick them.
    #
    # The question the unlock line actually depends on is whether any
    # coworker can END UP HOLDING the claim, which has two real sources:
    # the rendered checkbox grid, or a front-desk preset that writes the id
    # at hire. Measured against both, so hiding a checkbox no longer
    # silently invalidates a card's copy, and neither does dropping an id
    # from the presets.
    settings_src = SETTINGS.read_text(encoding='utf-8')
    hidden = set()
    for name in ('NEVER_WIRED_TOOL_IDS', 'GRANTED_ELSEWHERE_TOOL_IDS'):
        m = re.search(r'const %s = new Set\(\[([^\]]*)\]' % name, settings_src)
        if m:
            hidden |= set(re.findall(r"'([^']+)'", m.group(1)))
    tickable = {i for i in re.findall(r"id: '([^']+)'", catalog)} - hidden
    preset_claims = set(re.findall(r"'([^']+)'",
                                   ' '.join(re.findall(r'tools: \[([^\]]*)\]', hire))))
    for key in unlock_keys:
        where = ('the roster grid' if key in tickable else
                 'a front-desk preset' if key in preset_claims else None)
        check(f'a coworker can actually end up claiming "{key}"',
              where is not None,
              f'"{key}" is in neither the rendered checkbox grid (hidden: '
              f'{sorted(hidden)}) nor any FRONT_DESK preset, so its unlock '
              'line can only ever fire for a hand-edited agent')
    # The other direction, and the one that was never asked: a preset may
    # only hand a coworker an id that means something. Four FRONT_DESK
    # cards carried 'shell', which is in no catalog and no CAN_DO table, so
    # the three Coding Agent cards and Hermes silently never said they
    # could run code. Nothing failed; the word was simply read by nobody.
    catalog_ids = set(re.findall(r"id: '([^']+)'", catalog))
    bogus = sorted(preset_claims - catalog_ids)
    check('every tool a front-desk preset hands over is a real id',
          not bogus,
          f'{bogus} appear in FRONT_DESK `tools:` arrays but in no '
          'TOOLS_CATALOG entry, so they are stored on the agent and read '
          'by nothing — not a grant, not a card line, not a stat bar')
    # Bounded by where the object closes, not by a character count. As
    # `{0,2000}?`, this stopped matching on 2026-08-15 when the entry's
    # comment grew — and reported that Pixel had lost a claim it still has.
    pixel = re.search(r"name: 'Pixel',([\s\S]*?)\n  \},", runtime)
    check('the image specialist claims the image tool',
          pixel and re.search(r"tools: \[[^\]]*'img'", pixel.group(1)),
          'this is the whole of the bug this test was written for: the card '
          'copy was right and the shelf entry never claimed img, so Pixel '
          'introduced itself by its vault access')

    # The reader moved to hq-runtime.jsx on 2026-08-16, beside the grant it
    # mirrors, because the coworker card and the inspect panel needed it too
    # and a private copy per surface is the drift this check exists to catch.
    # Both halves still asserted: the fact is read from `imageProvider`, and
    # the shelf still hands what it read to `canDoPhrase`.
    check('the hire form still hands over the facts it read',
          re.search(r'f\.canMakeImages = !!s\.imageProvider;', runtime)
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
        # Elevation IS a switch — one per coworker, on their own card in
        # Settings → Roster — so it gets a future tense like the rest.
        'not_elevated': (['code'], {'elevated': False}),
        # …and stays silent when the caller could not read the flag at all,
        # same mirror rule as pixel_unknown. A boss who granted computer
        # access months ago must not be told to go and switch it on.
        'elev_unknown': (['code'], {}),
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
    check('elevation gets an unlock line naming its switch',
          r['not_elevated'] == 'run code once you switch on their file & shell access',
          f"{r['not_elevated']} — measured as \"talk things through\" before "
          'this fix: the one capability with a real per-agent switch was the '
          'only one the card would not give a route to')
    check('...and says nothing when the elevation flag could not be read',
          r['elev_unknown'] == 'talk things through',
          f"{r['elev_unknown']} — absent is not false, same as pixel_unknown")
    # Counted, not merely present. Two tools ride the elevation switch and
    # both need the line; an existence test stayed green with the `code:`
    # entry deleted, because the `files:` one still carried the string.
    # Same existence-vs-count weakness that let a levelled-down record
    # through in test_the_bubble_gets_the_same_clean.
    n_routes = cast.count('once you switch on their file & shell access')
    check('the old refusal is not silently still in force',
          n_routes >= 2,
          f'{n_routes} of 2 elevation-gated tools name the switch in '
          'cast.jsx — the two checks above run against a lifted copy, so '
          'this one pins the shipped file itself')
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
