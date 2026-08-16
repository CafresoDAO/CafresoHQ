#!/usr/bin/env python3
"""A checkbox that granted nothing, and removed nothing.

Reproduced 2026-08-15 on a live office (port 9256, canned brain on 9236).
Hired "Marge" through the hire form with the default tools — Web Search on,
Vault Notes off, Image Gen off — stored as `tools: ['web','files']`. Settings
already carried `imageProvider: 'openai'`. Sent her one message and read the
POST body the brain actually received:

    - [GENERATE_IMAGE: <vault path, e.g. Images/concept.png>]

Her Image Gen box was never ticked. `toolsForAgent` read
`getSettings().imageProvider` and nothing else, so the moment ANY boss picked
an image provider, every coworker in the office got the tool — and un-ticking
the box took it away from nobody. Both directions of the same lie, on a
control the boss is looking straight at.

The two-door shape is the point. The claim (this box) and the provider
(Settings → Media) are separate facts and the tool needs both; the defect was
reading one of them. `app/cast.jsx` already modelled it correctly —
`CAN_DO.img` gated on `CAN_DO_NEEDS.img = 'canMakeImages'` — so the card and
the runtime disagreed, and the runtime was the one that decided.

Second half: with the box now load-bearing, "turn it on from their card in
Settings → Roster" becomes the WRONG door for a coworker whose box is already
on and whose provider is missing. The hint names the shut door, not the
nearest one.

Video rides the same claim deliberately. There is no 'video' id in
TOOLS_CATALOG, so leaving GENERATE_VIDEO on its provider alone would have kept
this exact defect alive for the half with no box — and TOOL_CLAIM_GROUPS has
always answered "Image Gen" for a video reach, which was wrong when it was
written and is true now.

Run: python3 scripts/test_the_image_box_is_a_real_door.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
SETTINGS = (ROOT / 'modals' / 'settings.jsx').read_text(encoding='utf-8')
CAST = (ROOT / 'app' / 'cast.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Every scan below runs on code, never on prose.

    This repo has now shipped four checks that passed by matching an
    explanation written in the same commit — one of them an ASCII diagram.
    The phrases this file looks for ("claimed.has('img')", "Settings →
    Media", "Image Gen") are all over the comments that justify the fix.
    """
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
    """The function body, matched by braces rather than by a line window.

    A regex window has a length in it, and the length is a guess about how
    long the code will stay. Braces are not a guess.

    The body opener is the first `{` at paren depth ZERO. Taking the first
    `{` after the name — which is what the copy of this helper in
    test_the_hints_name_a_box_that_exists.py does — lifts the DESTRUCTURED
    PARAMETER instead: `toolsForAgent(agent, { peers = [] } = {})` balances
    inside its own signature, so the "body" came back as the signature and
    every line-scan over it found nothing. It failed loudly here because
    these are positive checks; the negative half of the same scan would
    have passed on an empty string. Third time this repo has shipped a
    source window that can collapse to nothing (see the `block()` note in
    test_a_preview_link_is_not_published.py) — a window that can collapse
    reports agreement.
    """
    i = src.index(opener)
    parens = 0
    j = None
    for k in range(i, len(src)):
        c = src[k]
        if c == '(':
            parens += 1
        elif c == ')':
            parens -= 1
        elif c == '{' and parens == 0:
            j = k
            break
    if j is None:
        raise AssertionError('no body brace found lifting ' + opener)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


def main():
    print('the Image Gen box is a real door')
    code = strip_comments(RUNTIME)

    # ── 1. the grant reads the claim ────────────────────────────────────
    grant = brace_lift(code, 'async function toolsForAgent(')
    img = [ln.strip() for ln in grant.splitlines()
           if 'TOOL_REGISTRY.generate_image' in ln]
    vid = [ln.strip() for ln in grant.splitlines()
           if 'TOOL_REGISTRY.generate_video' in ln]
    check('toolsForAgent still grants the image tool somewhere', img, img)
    check('...gated on the claim the boss ticks',
          img and all("claimed.has('img')" in ln for ln in img),
          img + ['— this is the whole defect: the shipped line read the '
                 'provider and nothing else, so an unticked box still got '
                 'the tool'])
    check('...and still gated on a provider being picked',
          img and all('imageProvider' in ln for ln in img),
          img + ['— the claim alone would put a marker in the prompt whose '
                 'call comes back "provider required"'])
    check('the video tool rides the same claim',
          vid and all("claimed.has('img')" in ln for ln in vid),
          vid + ["— there is no 'video' id in TOOLS_CATALOG, so a "
                 'provider-only gate here keeps the defect alive for the '
                 'half with no checkbox at all'])
    check('...and its own provider', vid and all('videoProvider' in ln for ln in vid), vid)

    # The catalog id has to exist, or `claimed.has('img')` is a gate nobody
    # can ever open — the failure mode of the four NEVER_WIRED ids, inverted.
    check("'img' is a real catalog id",
          re.search(r"id:\s*'img'\s*,\s*label:\s*'([^']+)'", RUNTIME), 'TOOLS_CATALOG')
    hidden = set()
    for name in ('NEVER_WIRED_TOOL_IDS', 'GRANTED_ELSEWHERE_TOOL_IDS'):
        m = re.search(r'const %s = new Set\(\[([^\]]*)\]' % name, SETTINGS)
        if m:
            hidden |= set(re.findall(r"'([^']+)'", m.group(1)))
    check("...and the box is still rendered on the card", 'img' not in hidden,
          f'hidden ids: {sorted(hidden)} — a load-bearing claim behind a box '
          'the boss cannot see is worse than the inert box it replaced')

    # ── 2. the card and the runtime agree ───────────────────────────────
    # They disagreed, and that disagreement IS the ticket: cast.jsx said the
    # coworker needs both facts, toolsForAgent read one. Pinned in both
    # directions so a later edit to either has to move the other.
    cast_code = strip_comments(CAST)
    check('the coworker card still gates images on a provider',
          re.search(r"img:\s*'canMakeImages'", cast_code),
          "CAN_DO_NEEDS.img — the card's half of the same two-door rule")
    check('...and still only says it for a coworker who claims it',
          re.search(r'for \(const t of \(tools \|\| \[\]\)\)', cast_code),
          'canDoPhrase iterates the claim list; a card built from settings '
          'would introduce every coworker as an image maker')

    # ── 3. Pixel keeps working ──────────────────────────────────────────
    # The one seeded coworker whose entire role is this tool. Before the fix
    # the claim was decorative; after it, removing it silently ends the role.
    pixel = RUNTIME[RUNTIME.index("name: 'Pixel'"):]
    pixel = pixel[:pixel.index('systemPrompt:')]
    check('Pixel still claims the box its job depends on',
          re.search(r"tools:\s*\[[^\]]*'img'", pixel), pixel[-120:])

    # ── 4. the hint names the shut door, run for real ───────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the door checks need it')
    else:
        js = re.search(r'^const TOOLS_CATALOG = \[[\s\S]*?^\];$', RUNTIME, re.M).group(0) + '\n'
        js += re.search(r"^const ELEVATION_DOOR = '[^']*';$", RUNTIME, re.M).group(0) + '\n'
        js += re.search(r'^const TOOL_CLAIM_GROUPS = \[[\s\S]*?^\];$', RUNTIME, re.M).group(0) + '\n'
        # toolClaimGroup first — toolClaimLabel calls it (see #68; the chief
        # of staff's door map needed the same classification without a second
        # copy of TOOL_CLAIM_GROUPS). Lifting the caller alone is a
        # ReferenceError at node time, not a check failure.
        js += brace_lift(RUNTIME, 'function toolClaimGroup(') + '\n'
        js += brace_lift(RUNTIME, 'function toolClaimLabel(') + '\n'
        js += brace_lift(RUNTIME, 'function claimNeedsMediaDoor(') + '\n'
        js += brace_lift(RUNTIME, 'function claimHitsMediaDoor(') + '\n'
        # claimLabels grew a vault door too (see
        # test_the_hint_names_the_door_that_is_shut.py). Lifted only so this
        # harness still runs — TICKED holds 'vault', so an unlifted callee
        # would take every case here down with it.
        js += brace_lift(RUNTIME, 'function claimNeedsVaultDoor(') + '\n'
        js += brace_lift(RUNTIME, 'function claimLabels(') + '\n'
        js += r'''
const TICKED   = { name: 'Pixel', tools: ['img', 'vault'] };
const UNTICKED = { name: 'Marge', tools: ['web', 'files'] };
const R = {
  // box off: the box IS the shut door, so name it and say nothing about
  // the second screen.
  offLabel:  claimLabels(['GENERATE_IMAGE'], UNTICKED),
  offMedia:  claimHitsMediaDoor(['GENERATE_IMAGE'], UNTICKED),
  // box on: the box is not shut. Naming it is the wrong door.
  onLabel:   claimLabels(['GENERATE_IMAGE'], TICKED),
  onMedia:   claimHitsMediaDoor(['GENERATE_IMAGE'], TICKED),
  vidOn:     claimHitsMediaDoor(['GENERATE_VIDEO'], TICKED),
  // a mixed reach keeps the box that IS shut and adds the second screen.
  mixLabel:  claimLabels(['WEB_SEARCH', 'GENERATE_IMAGE'], TICKED),
  mixMedia:  claimHitsMediaDoor(['WEB_SEARCH', 'GENERATE_IMAGE'], TICKED),
  // caller does not know which boxes are ticked.
  unkLabel:  claimLabels(['GENERATE_IMAGE'], null),
  unkMedia:  claimHitsMediaDoor(['GENERATE_IMAGE'], null),
  // nothing to do with media.
  webMedia:  claimHitsMediaDoor(['WEB_SEARCH', 'BASH'], TICKED),
  // the one-argument form every existing caller and test uses.
  legacy:    claimLabels(['WEB_SEARCH', 'GENERATE_IMAGE']),
};
console.log(JSON.stringify(R));
'''
        proc = subprocess.run(['node', '--input-type=module', '-e', js],
                              cwd=ROOT, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            print(proc.stderr, file=sys.stderr)
            raise SystemExit('node harness failed on source lifted from hq-runtime')
        R = json.loads(proc.stdout.strip().split('\n')[-1])

        check('an unticked box is named as the door',
              R['offLabel'] == 'Image Gen' and R['offMedia'] is False,
              R)
        check('a ticked box is NOT named as the door',
              R['onLabel'] == '',
              repr(R['onLabel']) + ' — "turn it on from their card" sends the '
              'boss to a control that is already on; they toggle it, nothing '
              'changes, and the shut door is never mentioned')
        check('...the second screen is named instead', R['onMedia'] is True, R)
        check('a video reach hits the same second screen', R['vidOn'] is True, R)
        check('a mixed reach still names the box that IS shut',
              R['mixLabel'] == 'Web Search' and R['mixMedia'] is True,
              R, )
        check('unknown boxes are not treated as ticked',
              R['unkLabel'] == 'Image Gen' and R['unkMedia'] is False,
              repr(R) + ' — the CEO path has an office, not one coworker; '
              '"we do not know" must not become "it is already on"')
        check('a reach with no media in it never mentions Media',
              R['webMedia'] is False, R)
        check('the one-argument form still behaves as it did',
              R['legacy'] == 'Web Search and Image Gen', repr(R['legacy'])
              + ' — the CEO call site and test_the_hints_name_a_box_that_'
                'exists both pass one argument')

    # ── 5. the sentences themselves ─────────────────────────────────────
    # §6 binds this channel and §7 asks every one of them for a way forward.
    notes = re.findall(r"`_\((.*?)\)_`", code, re.S)
    media_notes = [n for n in notes if 'Settings → Media' in n]
    check('the hint channel gained a Settings → Media sentence', media_notes,
          'the shut door has to be nameable or the fix is source-only')
    # Two sentences mention Media: a clause appended to the Roster sentence
    # (some boxes shut AND no provider) and a standalone one (the box is
    # already on, so Roster is the wrong door). Written first as "no media
    # note also says Roster", which the fire-test walked straight through:
    # deleting the standalone sentence left the appended clause behind, the
    # phrase was still in the file, and the check reported agreement. What
    # has to exist is the sentence for the case the ticket is about, not
    # the phrase.
    standalone = [n for n in media_notes
                  if 'Settings → Roster' not in n and 'already on' in n]
    check('...including a standalone one for a box that is already on',
          standalone,
          media_notes + ['— an already-ticked box is not the shut door, so '
                         'this sentence must not carry the Roster route too'])
    check('...and every one of them names a screen the boss can open',
          all(re.search(r'Settings → (Media|Roster)', n) for n in media_notes),
          media_notes)
    # The one that shipped: a raw tool name in the sentence. Interpolations
    # stripped, because a label arrives through one and a tool name must not.
    bare = [n for n in media_notes
            if re.search(r'\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b', re.sub(r'\$\{[^}]*\}', '', n))]
    check('...in office words, not tool names', not bare, bare)

    print()
    if FAILS:
        print(f'the image door: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('the image door: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
