#!/usr/bin/env python3
"""Every stat bar on the performance review read as empty.

Measured live (#152) on Team → click a coworker → PERFORMANCE REVIEW. Four
rows -- Speed, Depth, Code, Cost -- each four segments wide, and every one of
them painted the same flat `rgb(36, 29, 51)`. "Speed: 3 of 4" looked exactly
like 0 of 4, on every coworker, in the office's DEFAULT theme.

The markup was right the whole time:

    <span class="sb-track" aria-label="Speed: 3 of 4">
      <span class="sb-seg on"></span> ... <span class="sb-seg"></span>

so a screen reader was told the truth and the eye was told nothing. The
stylesheet was the liar:

    .sb-seg.on         { background: var(--accent-teal); ... }   (0,2,0)
    body.night .sb-seg { background: #241d33; ... }              (0,2,1)

`body.night .sb-seg` matches a FILLED segment too, and outranks the `.on`
rule, so the night palette repainted both states identically. A night block
is a palette swap for the RESTING state; it has no business outranking a
state modifier. `:not(.on)` says so in the selector.

Why it matters more than a missing colour: these four rows are the only place
the office compares one brain against another, and the boss reads them before
hiring or swapping one. Blank bars do not read as "no data" -- they read as
"these coworkers are the same". Verified after the fix that they are not:
Codex came back Depth 3 / Cost 3 and Llama Depth 2 / Cost 4.

There was a TWIN. Asking which other `body.night .X` rules outrank a state
modifier they share a property with turned up exactly one more: `.pb-seg`,
the same four-bar block on the job-posting card in the hire modal -- the
surface where the boss picks which coworker to bring in, where a flat bar
hides not just a number but the difference the choice is being made on. It
is covered here too, and this file failed on it before it was fixed.

This file does not grep for `:not(.on)`. It resolves the cascade the way a
browser does -- every rule for each bar in the real stylesheet, with real
specificity and real source order -- and asserts that a filled segment and an
empty one cannot land on the same paint, in either theme. Any future rule
that re-flattens them, by any route, fails here. A selector it cannot model
fails too, rather than passing quietly.

Run: python3 scripts/test_a_filled_stat_bar_looks_filled.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / 'styles.css'
PANELS = ROOT / 'ui' / 'panels.jsx'
HIRE = ROOT / 'modals' / 'hire.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def rules_for(css, needle):
    """Every top-level `selector { decls }` whose selector mentions `needle`.

    Source order is preserved, because the cascade's last tie-break is
    "whichever came later in the file" and this bug lived exactly one
    specificity point away from that mattering.
    """
    src = re.sub(r'/\*[\s\S]*?\*/', '', css)
    out = []
    for m in re.finditer(r'([^{}@]+)\{([^{}]*)\}', src):
        sel = m.group(1).strip()
        if needle not in sel:
            continue
        decls = {}
        for d in m.group(2).split(';'):
            if ':' in d:
                k, v = d.split(':', 1)
                decls[k.strip()] = v.strip()
        for one in sel.split(','):
            out.append((one.strip(), decls, m.start()))
    return out


CLS = re.compile(r'\.([A-Za-z0-9_-]+)')
NOT = re.compile(r':not\(([^)]*)\)')


def specificity(sel):
    """(ids, classes, elements) for the simple selectors this file uses.

    `:not(...)` contributes its ARGUMENT's specificity and nothing of its
    own -- which is the detail that made the bug: `body.night .sb-seg` is
    (0,2,1) and beat `.sb-seg.on` at (0,2,0) by one element.
    """
    ids = len(re.findall(r'#[A-Za-z0-9_-]+', sel))
    inner = ' '.join(NOT.findall(sel))
    bare = NOT.sub(' ', sel)
    classes = len(CLS.findall(bare)) + len(CLS.findall(inner))
    classes += len(re.findall(r'\[[^\]]*\]', bare))
    classes += len(re.findall(r':(?!not\()[a-z-]+', bare))
    elements = len(re.findall(r'(?:^|[\s>+~])([a-z][a-z0-9]*)', bare))
    return (ids, classes, elements)


def matches(sel, seg_classes, theme, base):
    """Does `sel` match a `.<base>` segment span in this theme? None = unknown.

    Handles exactly the shapes this stylesheet uses -- an optional
    `body.<theme>` ancestor, then a compound of `.sb-seg` with extra classes
    and `:not(.cls)` guards. Anything else returns None and is REPORTED
    rather than skipped: a selector this file cannot read is a hole the bug
    could come back through, and silence would be worse than a failure.
    """
    parts = sel.split()
    if len(parts) == 2:
        anc, target = parts
        m = re.fullmatch(r'body((?:\.[A-Za-z0-9_-]+)*)', anc)
        if not m:
            return None
        need = set(CLS.findall(m.group(1)))
        if not need <= ({theme} if theme else set()):
            return False
    elif len(parts) == 1:
        target = parts[0]
    else:
        return None

    if not re.fullmatch(r'(?:\.[A-Za-z0-9_-]+|:not\(\.[A-Za-z0-9_-]+\))+', target):
        return None
    if not NOT.sub('', target).startswith('.' + base):
        return None
    for cls in CLS.findall(NOT.sub(' ', target)):
        if cls not in seg_classes:
            return False
    for arg in NOT.findall(target):
        for cls in CLS.findall(arg):
            if cls in seg_classes:
                return False
    return True


def paint(rules, seg_classes, theme, prop, base):
    """The declaration a browser would use for `prop`, or None."""
    best, best_key = None, None
    for sel, decls, pos in rules:
        if prop not in decls:
            continue
        hit = matches(sel, seg_classes, theme, base)
        if hit is None:
            raise ValueError('cannot read selector: ' + sel)
        if not hit:
            continue
        key = (specificity(sel), pos)
        if best_key is None or key > best_key:
            best, best_key = decls[prop], key
    return best


# Both four-segment bars in the product, because the bug was in both.
#
# `.sb-seg` is the PERFORMANCE REVIEW panel; `.pb-seg` is the same widget on
# the job-posting card in the hire modal -- the surface where the boss is
# choosing WHICH coworker to bring in, which is if anything the worse of the
# two places to go blank. Two copies of one widget, two copies of one
# mistake, found by asking which other `body.night .X` rules outrank a state
# modifier they share a property with.
BARS = (
    ('sb-seg', 'the performance review panel', PANELS),
    ('pb-seg', 'the job posting card',         HIRE),
)


def main():
    print('a filled stat bar looks filled')
    css = CSS.read_text(encoding='utf-8')
    panels = PANELS.read_text(encoding='utf-8')

    for base, where, jsx in BARS:
        print(f'--- .{base} — {where} ---')
        rules = rules_for(css, base)

        print('1. the stylesheet can be read at all')
        check(f'there are .{base} rules to resolve', len(rules) >= 2,
              f'{len(rules)} — with fewer than a base and a state rule there '
              'is nothing here to get wrong, and this file is measuring '
              'nothing')
        unreadable = [sel for sel, _d, _p in rules
                      if matches(sel, {base, 'on'}, 'night', base) is None]
        check(f'every .{base} selector is one this file can resolve',
              not unreadable,
              f'{unreadable!r} — a selector this test cannot model is a route '
              'the bug can come back through unnoticed; teach matches() about '
              'it rather than letting it pass silently')
        if unreadable:
            print('\nfilled stat bar: cannot continue with unreadable selectors')
            return 1

        print('2. filled and empty must not land on the same paint')
        # night is the office's default theme, and where it was measured. The
        # un-themed pass is the day palette. The night rule set border-color
        # as well as background, so a fix that restored only the fill would
        # leave a teal block ringed in the empty colour.
        for theme, label in (('night', 'night — the default theme'),
                             (None, 'day')):
            on = paint(rules, {base, 'on'}, theme, 'background', base)
            off = paint(rules, {base}, theme, 'background', base)
            print(f'         {theme or "day"}: on={on!r} off={off!r}')
            check(f'a filled segment paints differently in {label}',
                  on is not None and on != off,
                  f'both segments resolve to {off!r} — "3 of 4" is '
                  'indistinguishable from 0 of 4 on screen')
            on_b = paint(rules, {base, 'on'}, theme, 'border-color', base)
            off_b = paint(rules, {base}, theme, 'border-color', base)
            check(f'...and so does its border in {label}',
                  on_b is not None and on_b != off_b,
                  f'both borders resolve to {off_b!r} — a filled segment '
                  'ringed in the empty colour has its edges rubbed out')

        src = jsx.read_text(encoding='utf-8')
        seg = re.search(
            r"className=\{'%s' \+ \(i <= (\w+) \? ' on' : ''\)\}" % base, src)
        aria = re.search(r'aria-label=\{`\$\{\w+\}: \$\{(\w+)\} of 4`\}', src)
        check('the filled count and the spoken count are the same variable',
              seg is not None and aria is not None
              and seg.group(1) == aria.group(1),
              f'{seg and seg.group(1)!r} vs {aria and aria.group(1)!r} — '
              f'{jsx.name}: the aria-label was the only honest channel while '
              'this was broken, so the two must come from one number')

    print('3. what the bars are still claiming to be')
    check('the bars still say they are a judgement, not a record',
          'not a measurement of their work' in panels,
          'ui/panels.jsx: these four sit above two counted stats; the '
          'tooltip is what keeps a boss from reading all six as earned')

    print()
    if FAILS:
        print(f'filled stat bar: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('filled stat bar: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
