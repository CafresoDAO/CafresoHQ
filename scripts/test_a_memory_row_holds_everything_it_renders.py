#!/usr/bin/env python3
"""The delete button fell out of its row and landed under the tag.

Measured live (#150) on the Memory page, on the very first note saved from
the office's own empty-state prompt ("start typing in the box below"). The
saved row came back looking like this:

    [ NOTE ]  We ship on Fridays, never on Mondays.        JUST NOW   [📌]
    [  ✕   ]

`.memrow` is a CSS grid. Its template said `70px 1fr auto auto` -- four
tracks, one per child -- which held only while the row rendered exactly four
children. It grew a fifth (📌, pin to corkboard) and nobody came back to the
stylesheet. With five children in four columns and the default
`grid-auto-flow: row`, the fifth wraps to a second grid row and is placed in
COLUMN 1: the ✕ delete, stretched to the tag column's fixed 70px, sitting
directly beneath the NOTE/PREF/RULE chip and reading as part of the label.

Two things made it worse than a cosmetic slip:

  · The displaced child is the destructive one. A 70px block in the badge
    column is not where a boss expects "throw this away" to live.
  · The row went from 44px to 75px, and `.memshelf` is a 400px scroller, so
    the shelf showed a little over half the entries it was sized for.

app.jsx's only call site passes `onPin`, so the fifth child was not an edge
case -- it rendered on every entry the boss had ever saved.

The fix is not "change 4 to 5". It is `grid-auto-flow: column` over three
named tracks, so every action button after the date flows into an implicit
column of its own and the row can grow another one without a stylesheet
edit. The count cannot drift again because there is no longer a count.

This file does not match the fix's text. It reads the REAL template out of
styles.css and the REAL child list out of views/core.jsx, then runs CSS
grid's own placement rule over the two to work out which row and column each
child actually lands in -- the same two facts measured in the browser. A
future sixth button, or a revert to a fixed track count, is caught by the
placement, not by a literal.

Run: python3 scripts/test_a_memory_row_holds_everything_it_renders.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / 'styles.css'
CORE = ROOT / 'views' / 'core.jsx'
APP = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(s):
    return re.sub(r'/\*[\s\S]*?\*/', '', s)


def rule_block(css, selector):
    """The declarations of the first `selector { ... }` rule, comments gone.

    Deliberately reads the shipped stylesheet rather than a copy: the bug was
    that the stylesheet and the component disagreed, so a test holding its
    own idea of either would have agreed with itself and missed it.
    """
    src = strip_comments(css)
    m = re.search(r'^\s*%s\s*\{([^}]*)\}' % re.escape(selector), src, re.M)
    if not m:
        return None
    out = {}
    for decl in m.group(1).split(';'):
        if ':' in decl:
            k, v = decl.split(':', 1)
            out[k.strip()] = v.strip()
    return out


def track_count(value):
    """How many columns `grid-template-columns` declares.

    Only the flat forms this stylesheet uses -- a space-separated track list.
    `repeat()` would need real expansion, so it is reported rather than
    guessed at, which keeps a wrong number from silently passing.
    """
    if value is None:
        return 0
    if 'repeat(' in value:
        return None
    return len([t for t in value.split() if t])


def _skip_tag(src, i):
    """Walk from a `<` to just past its `>`. Returns (pos, self_closing).

    A regex cannot do this: JSX attributes hold arbitrary expressions, and
    `onClick={()=>onPin({…})}` contains both a `>` and nested braces. So
    the closing `>` is the first one at brace depth zero.
    """
    brace, j, last = 0, i + 1, ''
    while j < len(src):
        c = src[j]
        if c == '{':
            brace += 1
        elif c == '}':
            brace -= 1
        elif c == '>' and brace == 0:
            return j + 1, last == '/'
        if not c.isspace():
            last = c
        j += 1
    raise ValueError('unterminated tag')


def jsx_children(src, class_name):
    """The element children of the JSX node carrying `className="cls"`.

    Located by the class, not by a literal opening tag -- the first draft of
    this file looked for `<div className="memrow">` and crashed the moment
    it met the real `<div key={m.id} className="memrow">`. A locator that
    breaks on an added attribute reads as a broken test, not a broken app.

    A `{cond && <button …>}` guard counts as one child, because that is
    exactly what it is once it renders -- and the child that was NOT counted
    when the grid template was written is the one that broke the row.
    """
    at = src.index('className="%s"' % class_name)
    start = src.rindex('<', 0, at)
    j, self_closing = _skip_tag(src, start)
    if self_closing:
        return []
    depth, kids, open_at = 0, [], None
    while j < len(src):
        if src[j] != '<':
            j += 1
            continue
        if src.startswith('</', j):
            if depth == 0:
                return kids                      # the node's own closing tag
            depth -= 1
            end, _ = _skip_tag(src, j)
            if depth == 0:
                kids[-1] = (kids[-1][0], src[open_at:end])
            j = end
            continue
        tag = re.match(r'<(\w+)', src[j:])
        if not tag:                              # a bare `<` in a comparison
            j += 1
            continue
        here = j
        j, sc = _skip_tag(src, j)
        if depth == 0:
            kids.append((tag.group(1), src[here:j]))
            open_at = here
        if not sc:
            depth += 1
    raise ValueError('unterminated element')


def place(n_children, cols, auto_flow):
    """CSS grid placement for `n_children` auto-placed items.

    `grid-auto-flow: row` (the default) fills across the explicit columns and
    starts a new row when it runs out -- this is the rule that put the ✕ in
    column 1 of row 2. `column` fills down the (single, implicit) row and
    creates a new implicit column per item instead, which is why the fix
    holds for any number of buttons.

    Returns [(row, col), …], zero-indexed.
    """
    if auto_flow == 'column':
        return [(0, i) for i in range(n_children)]
    if not cols:
        return [(i, 0) for i in range(n_children)]
    return [(i // cols, i % cols) for i in range(n_children)]


def main():
    print('a memory row holds everything it renders')
    css = CSS.read_text(encoding='utf-8')
    core = CORE.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')

    row = rule_block(css, '.memrow')
    if row is None:
        print('  FAIL  no .memrow rule in styles.css')
        return 1

    print('1. what the component actually renders')
    kids = jsx_children(core, 'memrow')
    check('the row still renders tag, text, date and its buttons',
          len(kids) >= 4, f'{[t for t, _ in kids]!r} — could not read the '
          'children back out of views/core.jsx; the placement below would '
          'be a guess')
    check('the last child is the one that deletes the entry',
          bool(kids) and 'onRemove(' in kids[-1][1],
          'the ✕ is what makes a displaced child dangerous rather than '
          'untidy — if it moved, re-read this whole file')
    # The 📌 is behind `onPin &&`, and app.jsx's one call site passes it.
    # That is what made a "conditional" fifth child unconditional in
    # practice, and it is the fact this suite would want to know had
    # changed.
    check('app.jsx still passes onPin, so every entry renders the pin',
          re.search(r'<MemoryPage[^>]*\bonPin=\{', app) is not None,
          'app.jsx: if onPin is dropped the row renders one fewer child and '
          'the old four-track template would start passing again by luck')

    print('2. the grid it is being placed into')
    tpl = row.get('grid-template-columns')
    flow = row.get('grid-auto-flow')
    cols = track_count(tpl)
    check('grid-template-columns is a plain track list this file can read',
          cols is not None, f'{tpl!r} — repeat() needs expanding before the '
          'placement below means anything')
    print(f'         template={tpl!r}  flow={flow!r}  children={len(kids)}')

    print('3. where each child lands')
    spots = place(len(kids), cols, flow)
    on_row_one = [i for i, (r, _) in enumerate(spots) if r != 0]
    check('every child sits on the first grid row',
          not on_row_one,
          f'children at index {on_row_one} wrapped — {len(kids)} children, '
          f'{cols} explicit columns, grid-auto-flow: {flow or "row"}. This '
          'is the measured bug: the ✕ wrapped to row 2.')
    last_r, last_c = spots[-1]
    check('...and the delete control is in the last column, not the first',
          last_c == len(kids) - 1 and last_c != 0,
          f'the ✕ landed at row {last_r}, column {last_c} — column 0 is the '
          '70px tag track, which is where it was found on screen')

    print('4. the fix is structural, not a bigger number')
    # `grid-template-columns: 70px 1fr auto auto auto` would pass §3 today
    # and break again on the next button. The rule that cannot drift is the
    # one that does not count.
    check('actions flow into implicit columns',
          flow == 'column',
          f'grid-auto-flow: {flow!r} — with the default row flow the track '
          'count has to be kept in step with the JSX by hand, which is the '
          'thing that already failed once')
    check('...and those implicit columns are sized',
          row.get('grid-auto-columns') == 'auto',
          f"grid-auto-columns: {row.get('grid-auto-columns')!r}")
    check('the three named tracks are still tag, text, date',
          cols == 3, f'{tpl!r} — the fix keeps exactly the three content '
          'tracks explicit and lets the buttons be implicit')

    print('5. why the height mattered')
    # The wrap doubled the row height inside a fixed-height scroller, so the
    # shelf quietly showed about half the entries it was built to show.
    shelf = rule_block(css, '.memshelf')
    check('.memshelf is still a fixed-height scroller',
          shelf is not None and shelf.get('max-height') == '400px'
          and shelf.get('overflow') == 'auto',
          f'{shelf!r} — if this stopped being a fixed window, the row height '
          'consequence noted above no longer applies and this check can go')

    print()
    if FAILS:
        print(f'memory row: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('memory row: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
