#!/usr/bin/env python3
"""Third instance of one collision. The getting-started coach is
`position: fixed` and bottom-anchored. It landed on the rail's SETTINGS
button once (fixed by clearing the rail's column), on the mobile tab bar once
(fixed by clearing the bar's height), and — clearing the rail's column put it
straight onto the Chat view's composer, which is bottom-anchored too and
spans the whole remaining width, so there is no column left to clear.

Measured live at 1280x860: the card covered 27% of the message box and 50% of
the DIRECT thread tab, and `elementFromPoint` at the tab's centre and at two
points inside the textarea all returned the coach — at (380,780) it returned a
BUTTON inside the coach, so a click aimed at the message box would have
advanced an onboarding step instead. Worse at 375x812, where Chat is the
primary view: 46% of the composer covered and the textarea's own CENTRE
unhittable. The collapsed pill carries `.gs-coach` too and measured 26% there.

And the coach's step 3 reads "Chat with your team — Say hi to your CEO", with
an "Open chat ->" button. Follow it and the card lands on the composer it just
sent you to.

Not a grep for the fix. This file states the rule the fix has to satisfy —
**whatever positions the coach while the Chat view is up must not be a bottom
offset** — and derives it from the stylesheet, because the composer's height
is not knowable from CSS: the textarea grows from its min-height to its
max-height as you type, and the thread tabs sit under it. Any bottom offset is
a magic number a long message walks back through. Then it checks the rule
actually wins the cascade against the mobile block that sets `.gs-coach`'s
bottom later in the file, by computing specificity rather than trusting source
order.

Run: python3 scripts/test_the_coach_never_covers_the_message_box.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / 'styles.css'
APP = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def parse(css):
    """[(selector, decls, media)] for every simple rule.

    Walks braces rather than matching a flat `sel { ... }` regex, because the
    rules that matter here live inside `@media` blocks and a flat pattern
    reads their contents as top-level rules. Same walker as
    test_the_office_fits_in_the_window.py, for the same reason.
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
                        out.append((one.strip(), decls, media))
                i, head = j, j
                continue
        elif c == '}':
            if stack:
                stack.pop()
            head = i + 1
        i += 1
    return out


def specificity(sel):
    """(ids, classes, elements) for one compound selector.

    `:has(X)` and `:not(X)` contribute their ARGUMENT's specificity and none
    of their own — the same rule #152 turned on for `:not()`. That is the
    whole reason the chat-scoped rule can outrank a plain `.gs-coach` that
    appears later in the file, so it is derived here rather than assumed.
    """
    ids = classes = els = 0
    # pull functional pseudo-classes out first and score their arguments
    for fn, arg in re.findall(r':(has|not|is|where)\(([^()]*)\)', sel):
        if fn != 'where':
            a, b, c = specificity(arg)
            ids += a
            classes += b
            els += c
    rest = re.sub(r':(has|not|is|where)\([^()]*\)', ' ', sel)
    ids += len(re.findall(r'#[\w-]+', rest))
    classes += len(re.findall(r'\.[\w-]+', rest))
    classes += len(re.findall(r'\[[^\]]*\]', rest))
    # pseudo-classes that are left (:hover, :focus…) count as classes;
    # ::pseudo-elements count as elements.
    classes += len(re.findall(r'(?<!:):(?!:)[\w-]+', rest))
    els += len(re.findall(r'::[\w-]+', rest))
    els += len(re.findall(r'(?:^|[\s>+~])([a-zA-Z][\w-]*)', rest))
    return (ids, classes, els)


def main():
    print('The getting-started coach never covers the message box')

    css = CSS.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')
    rules = parse(css)

    coach = [(s, d, m) for (s, d, m) in rules
             if re.search(r'\.gs-coach(?![\w-])', s)]
    check('found the coach rules at all', len(coach) >= 3,
          'styles.css: .gs-coach has stopped being positioned here')

    # --- §1: the premise — the dock's height is not knowable -----------
    ta = [d for (s, d, _m) in rules if s.strip() == '.composer textarea']
    check('the composer textarea really does grow as you type — which is why '
          'no bottom offset can be trusted',
          any('min-height' in d and 'max-height' in d
              and d['min-height'] != d['max-height'] for d in ta),
          'styles.css: .composer textarea min/max-height — %r' % (ta,))

    # --- §2: the rule --------------------------------------------------
    chat = [(s, d, m) for (s, d, m) in coach if 'mobile-chat-view' in s]
    # The uniqueness below is about the rule that ANCHORS the card — the one
    # §2, §3 and §4 go on to interrogate, and the one whose `bottom: auto`
    # must not be contradicted by a second opinion. It used to be stated as
    # `len(chat) == 1`, over the whole chat-scoped set, and that was scaffolding
    # standing in for this: it made `chat[0]` unambiguous and nothing else.
    #
    # `#315` is why the difference matters. Releasing the bottom edge is only
    # half of getting the card off the composer; the mobile `max-height` two
    # rules further down was written for a card anchored at the BOTTOM, and
    # read from `top: 66px` it let the card grow 646px downward to y712, back
    # over a dock starting at y576 — measured, with four of four
    # elementFromPoint probes inside the textarea returning the coach. The
    # phone needs a second chat-scoped rule to re-cap it for a top anchor, and
    # `len(chat) == 1` forbade the fix while every property this test is
    # actually about stayed true. Narrowed to the anchoring rule: one rule
    # still decides where the card starts and ends, and a rule that sets
    # neither `top` nor `bottom` is not competing for that.
    anchor = [(s, d, m) for (s, d, m) in chat if 'top' in d or 'bottom' in d]
    check('something scopes the coach to the Chat view', len(anchor) == 1,
          'expected exactly one chat-scoped .gs-coach rule to anchor it, '
          'found %d (of %d chat-scoped rules)' % (len(anchor), len(chat)))
    if not anchor:
        print()
        print('%d FAILED' % len(FAILS))
        return 1
    csel, cdecls, cmedia = anchor[0]

    check('it applies everywhere, not only on one screen size — the collision '
          'was measured on BOTH desktop and phone', cmedia == '',
          'chat-scoped rule is inside %r' % cmedia)
    check('it releases the bottom edge', cdecls.get('bottom') == 'auto',
          'bottom: %r' % cdecls.get('bottom'))
    check('it anchors from the top instead', 'top' in cdecls
          and cdecls['top'] not in ('auto', ''),
          'top: %r' % cdecls.get('top'))
    # The whole point, stated as the thing that must not come back.
    check('it does NOT reach for a bottom offset — a number tied to a box '
          'whose height this stylesheet cannot know',
          not re.match(r'^-?[\d.]', str(cdecls.get('bottom', 'auto')))
          and 'calc' not in str(cdecls.get('bottom', 'auto')),
          'bottom: %r' % cdecls.get('bottom'))

    # --- §3: it has to actually win ------------------------------------
    # Every other rule that sets a `bottom` on .gs-coach is a competitor,
    # including the mobile block that appears LATER in the file. Source order
    # only decides ties, so compute the specificity.
    mine = specificity(csel)
    losers = []
    for (s, d, m) in coach:
        if s == csel or 'bottom' not in d:
            continue
        if specificity(s) >= mine:
            losers.append((s, m, d.get('bottom')))
    check('the chat rule outranks every other rule that sets the coach\'s '
          'bottom — including the mobile one further down the file',
          not losers, 'these tie or beat it: %r' % (losers,))
    check('...and it does so on specificity, which is what makes the file '
          'position it can be moved to irrelevant',
          mine > (0, 1, 0), 'specificity of %r is %r' % (csel, mine))

    # --- §4: the base behaviour is untouched ---------------------------
    base = [d for (s, d, m) in coach
            if s.strip() == '.gs-coach' and m == '']
    check('outside the Chat view the coach is still bottom-anchored',
          any(d.get('bottom') and d['bottom'] != 'auto' and 'top' not in d
              for d in base),
          'base .gs-coach rules: %r' % (base,))

    # --- §5: the signal is exact ---------------------------------------
    # `:has(.mobile-chat-view)` is only the right hook while that class is
    # rendered for the chat view and nothing else. If a second view starts
    # using it, this rule silently moves the coach on that view too.
    uses = re.findall(r'className="mobile-chat-view"', app)
    check('.mobile-chat-view is rendered exactly once in app.jsx',
          len(uses) == 1, 'found %d render sites' % len(uses))
    idx = app.find('className="mobile-chat-view"')
    before = app[max(0, idx - 400):idx]
    check('...and it is the Chat view that renders it',
          "case 'chat':" in before,
          'the nearest preceding case is not chat — %r' % before[-160:])

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
