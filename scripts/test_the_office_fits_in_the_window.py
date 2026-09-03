#!/usr/bin/env python3
"""The office shell grew taller than the window it declares it fits in.

Measured live (#153) at 1024x700, the Chat view:

    .app  height: 100vh          -> box is 700px
    .app  grid-template-rows     -> (not declared)
    computed grid-template-rows  -> 723.219px

`height` sets the BOX. It does not size the ROWS. With no
`grid-template-rows` the shell had one implicit `auto` track, and an auto
track is sized to its content's max-content height no matter what the box
says -- so the track resolved to 723.219px inside a 700px box and `overflow:
visible` spilled the excess off the bottom of the screen, where there is no
scrollbar to reach it. Both columns went over the edge together:

    .rail  .me         bottom 707   the boss's own identity chip, clipped
    .thread-tabs       bottom 722   DIRECT / TEAM / RESEARCH, 13px of a
                                    35px button left on screen

The rail is what wants the 723: its content is 707px plus 16px of padding.
And `.rail .me` is `margin-top: auto` -- it is written to sit ON the window's
bottom edge, which is only meaningful if the rail cannot grow past it.

The second casualty is the one that costs something. The thread switcher is
how a boss gets from talking to their CEO to talking to the whole team, and
to Research; a 1366x768 or 1280x800 laptop lands inside the broken band once
browser chrome is taken off the top, and there is no scrollbar, no clipping
cue, nothing to suggest the row is there at all.

Two existing comments in this stylesheet already ASSUMED the fix:

    /* fixed height so descendants can use height:100% */
    /* With .app at 100dvh this row gets the full remaining height. */

Neither was true. The mobile blocks had reached for `overflow: hidden`, which
hides the spill without recovering the content, and desktop had neither.

WHAT THIS FILE CHECKS

Not a grep for the fix. It implements the grid track-sizing rule that caused
the bug -- "does this track grow with its content?" -- and runs it over the
real declarations for every full-window grid shell in the real stylesheet, in
each media context that stylesheet actually defines. Any shell that pins its
height to the viewport and then leaves a content-sized row track fails here,
whether or not it is the one that was fixed.

Then it holds the rail to the three facts that make the containment work:
something inside it must be able to give (and it must be the nav, not the
brand or the SETTINGS door), the give must not be `.rail` itself while
`.rail-toggle` deliberately overhangs its edge, and `.me` must still be
bottom-pinned -- because if that stops being true, this file is measuring a
layout that no longer exists and should be reconsidered rather than kept
passing.

Run: python3 scripts/test_the_office_fits_in_the_window.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / 'styles.css'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# ── reading the stylesheet ────────────────────────────────────────────────
def parse(css):
    """[(selector, decls, media, source_pos)] for every simple rule.

    Walks braces rather than matching a regex against the whole file, because
    the rules that matter here live inside `@media` blocks and a flat
    `sel { ... }` pattern reads their contents as top-level rules.
    """
    css = re.sub(r'/\*[\s\S]*?\*/', '', css)
    out, stack, i, head = [], [], 0, 0
    while i < len(css):
        c = css[i]
        if c == '{':
            prelude = css[head:i].strip()
            if prelude.startswith('@'):
                stack.append(prelude)
                head = i + 1
            else:
                depth, j = 1, i + 1
                while j < len(css) and depth:
                    if css[j] == '{':
                        depth += 1
                    elif css[j] == '}':
                        depth -= 1
                    j += 1
                decls = {}
                for d in css[i + 1:j - 1].split(';'):
                    if ':' in d:
                        k, v = d.split(':', 1)
                        decls[k.strip()] = v.strip()
                media = ' and '.join(stack)
                for one in prelude.split(','):
                    if one.strip():
                        out.append((one.strip(), decls, media, i))
                i, head = j, j
                continue
        elif c == '}':
            if stack:
                stack.pop()
            head = i + 1
        i += 1
    return out


def applies(media, width):
    """Does this at-rule context apply at `width`? Unknown -> False.

    Only the width queries this stylesheet uses are modelled. Anything else
    is treated as not applying, which is the conservative direction: a shell
    is judged on the contexts we can actually resolve, and never excused by
    one we cannot read.
    """
    if not media:
        return True
    for part in media.split(' and '):
        part = part.strip()
        if not part.startswith('@media'):
            return False
        for cond in re.findall(r'\(([^)]*)\)', part):
            m = re.fullmatch(r'\s*(max|min)-width\s*:\s*(\d+)px\s*', cond)
            if not m:
                return False
            n = int(m.group(2))
            if m.group(1) == 'max' and width > n:
                return False
            if m.group(1) == 'min' and width < n:
                return False
    return True


def resolve(rules, sel, width):
    """The declarations in force for `sel` at `width`, in cascade order.

    `!important` is not modelled beyond source order, which is enough here:
    the shell's overrides are all later in the file than what they override.
    """
    out = {}
    for s, decls, media, _pos in rules:
        if s == sel and applies(media, width):
            for k, v in decls.items():
                out[k] = v
    return out


# ── the rule that caused the bug ──────────────────────────────────────────
CONTENT_SIZED = ('auto', 'min-content', 'max-content')


def grows_with_content(track):
    """Would this row track stretch past a definite container to fit content?

    This is the whole bug in one function. A grid track only stays inside a
    definite-height container if its MINIMUM is definite:

      · `auto`, `min-content`, `max-content`   -> yes, grows
      · a bare `<flex>` such as `1fr`          -> yes: `1fr` means
        `minmax(auto, 1fr)`, so its floor is the content, which is the trap
        that makes "I gave it 1fr" feel safe when it is not
      · `fit-content(x)`                       -> yes, floor is min-content
      · `minmax(auto|min-content|max-content, ...)` -> yes
      · `minmax(0, ...)`, `<length>`, `<percentage>` -> no
    """
    t = track.strip()
    if not t:
        return True
    if t.startswith('fit-content'):
        return True
    m = re.fullmatch(r'minmax\(\s*([^,]+?)\s*,\s*(.+?)\s*\)', t)
    if m:
        lo = m.group(1).strip()
        return lo in CONTENT_SIZED or lo.endswith('fr')
    if t in CONTENT_SIZED:
        return True
    if re.fullmatch(r'[\d.]+fr', t):
        return True
    if re.fullmatch(r'[\d.]+(px|em|rem|vh|dvh|svh|lvh|%)', t):
        return False
    return True          # anything unmodelled counts as unsafe, not as fine


def split_tracks(value):
    """`minmax(0, 1fr) auto` -> ['minmax(0, 1fr)', 'auto'], depth-aware."""
    out, depth, cur = [], 0, ''
    for ch in value:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch.isspace() and depth == 0:
            if cur:
                out.append(cur)
            cur = ''
        else:
            cur += ch
    if cur:
        out.append(cur)
    return [t for t in out if not t.startswith('[')]   # drop line names


VIEWPORT_H = re.compile(r'\b100(vh|dvh|svh|lvh)\b')

# The two widths this stylesheet actually branches on either side of. 1280 is
# a desktop with the rail; 375 is the phone, where the rail is gone and the
# tab bar owns the bottom. A shell has to survive both.
CONTEXTS = ((1280, 'desktop'), (375, 'mobile'))


def main():
    print('the office fits in the window')
    rules = parse(CSS.read_text(encoding='utf-8'))

    print('1. the app shell is pinned to the window it declares')
    for width, label in CONTEXTS:
        d = resolve(rules, '.app', width)
        check(f'.app is still a grid with a viewport height at {label}',
              d.get('display', '').startswith('grid')
              and VIEWPORT_H.search(d.get('height', '')) is not None,
              f'display={d.get("display")!r} height={d.get("height")!r} — if '
              'the shell stopped being a full-window grid this file is '
              'measuring the wrong thing and should be rewritten, not deleted')
        rows = d.get('grid-template-rows')
        check(f'.app declares its row tracks at {label}', rows is not None,
              'styles.css: with none declared the shell gets ONE implicit '
              '`auto` row, which is exactly what resolved to 723.219px '
              'inside a 700px box and put the rail and the thread switcher '
              'off the bottom of the screen')
        if rows:
            bad = [t for t in split_tracks(rows) if grows_with_content(t)]
            check(f'no .app row track grows with its content at {label}',
                  not bad,
                  f'{bad!r} in {rows!r} — a content-sized track ignores the '
                  'container height, and `overflow: visible` spills the '
                  'excess where no scrollbar can reach it')

    print('2. and so is every other full-window grid in the stylesheet')
    # The sweep, not just the one that was fixed: any selector that anywhere
    # pins itself to the viewport height AND is a grid is the same shape of
    # thing and can fail the same way.
    shells = sorted({s for s, decls, _m, _p in rules
                     if VIEWPORT_H.search(decls.get('height', ''))})
    print(f'         candidates: {shells!r}')
    check('the sweep found something to sweep', len(shells) >= 1,
          'no selector pins itself to the viewport height — either the shell '
          'was rebuilt or this scan stopped reading the file')
    for sel in shells:
        for width, label in CONTEXTS:
            d = resolve(rules, sel, width)
            if not d.get('display', '').startswith('grid'):
                continue
            if not VIEWPORT_H.search(d.get('height', '')):
                continue
            rows = d.get('grid-template-rows', '')
            bad = [t for t in split_tracks(rows) if grows_with_content(t)] \
                if rows else ['(implicit auto row)']
            check(f'{sel} holds its rows to the window at {label}', not bad,
                  f'{bad!r} — same shape as the .app bug: a box pinned to the '
                  'viewport whose tracks are free to be taller than it')

    print('3. the rail has somewhere to give')
    # Pinning the shell means that on a short screen something in the rail
    # must shrink. Which one it is matters: the brand, the SETTINGS door and
    # the identity chip are what a boss reaches for when the office confuses
    # them, and they must not be the parts that scrolled away.
    givers = sorted({s for s, decls, _m, _p in rules
                     if s.startswith('.rail')
                     and decls.get('min-height') == '0'
                     and decls.get('overflow-y', decls.get('overflow', '')) in ('auto', 'scroll')})
    check('exactly one thing inside the rail can shrink and scroll',
          givers == ['.rail nav'],
          f'{givers!r} — expected just `.rail nav`; the rail is a fixed-height '
          'flex column and needs one designated give, and it has to be the '
          'nav list rather than the brand, the door or the identity chip')

    print('4. …and it is not the rail itself, because the toggle overhangs')
    # Derived, not assumed: read the toggle's own inset. A scroll container
    # clips BOTH axes, so `overflow-y: auto` on `.rail` would cut the collapse
    # handle in half at whatever negative offset it is actually using.
    tog = resolve(rules, '.rail-toggle', 1280)
    insets = [(k, tog.get(k)) for k in ('left', 'right', 'top', 'bottom')
              if tog.get(k) and tog[k].strip().startswith('-')]
    check('.rail-toggle still hangs outside the rail',
          tog.get('position') == 'absolute' and bool(insets),
          f'position={tog.get("position")!r} insets={insets!r} — if the handle '
          'stopped overhanging, the constraint below is no longer load-bearing '
          'and the scroll could move up to `.rail`')
    rail = resolve(rules, '.rail', 1280)
    if insets:
        check('.rail keeps visible overflow so the handle is not clipped',
              rail.get('overflow', 'visible') == 'visible'
              and rail.get('overflow-y', 'visible') == 'visible'
              and rail.get('overflow-x', 'visible') == 'visible',
              f'overflow={rail.get("overflow")!r} — a scroll container clips '
              f'both axes, and the handle sits at {insets!r}')

    print('5. why the rail ending at the window edge is the point')
    me = resolve(rules, '.rail .me', 1280)
    check('the identity chip is still pinned to the bottom of the rail',
          me.get('margin-top') == 'auto',
          f'margin-top={me.get("margin-top")!r} — `margin-top: auto` is the '
          'evidence that the rail is meant to end exactly at the window edge; '
          'without it the containment above is arbitrary rather than intended')

    print()
    if FAILS:
        print(f'office fits: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('office fits: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
