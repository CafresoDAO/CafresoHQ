#!/usr/bin/env python3
"""JOB POSTINGS spelled one coworker's name across two lines.

Measured live (#146) on a fresh office, first run, at the step the
getting-started checklist sends you to: "Hire your first specialist". Eleven
cards at the front desk, and one of them read

    Herme
    s        NOT RUNNING

The name element was 29px tall against 14.5px for every other card, and 57.8px
wide for a word that needs 60. Nothing about Hermes is special except the badge
beside it: "NOT RUNNING" is the widest of the status tags, so it squeezed the
name below its own width, and the name -- a flex item -- was free to shrink and
split the word because of a rule it never asked for.

`.modal-body` carries `overflow-wrap: anywhere; word-break: break-word`, shared
with `.chat-bubble` and `.task-card`. It is there so an unbreakable URL in a
message cannot burst its container, and for a URL it is right. But it inherits,
and JOB POSTINGS is a modal body, so it reached the pixel-font proper nouns on
every card. Only the one with the widest badge had the room to show it.

The whole fix is to stop inheriting it on the name. No flex property is
involved: a flex item's default `min-width: auto` already floors it at its
min-content width, and once the word cannot break, min-content IS the whole
word. The name stops shrinking; the badge, which is two words and wraps
honestly, takes the second line instead.

That last point is what this suite mostly defends, because the tempting fixes
are worse than the bug. `white-space: nowrap` with `text-overflow: ellipsis`
also produces one line -- and renders "Herme…", which is not the coworker's
name. Measured: at 9 characters that variant truncated a perfectly ordinary
name. A misspelt name is a worse failure than an ugly one, so the checks below
forbid the clip as firmly as they require the break to stop.

This runs the cascade rather than grepping for a string: the stylesheet is
parsed, the real ancestor chain from the live DOM (modal-body > hire-board >
post-card > post-head > post-name) is walked, and specificity and source order
decide the winner exactly as a browser would.

Run: python3 scripts/test_a_coworker_name_is_never_broken_in_half.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / 'styles.css'
HIRE = ROOT / 'modals' / 'hire.jsx'
FAILS = []

# The chain as the browser reported it on the running office, innermost last.
CHAIN = ['div.app', 'div.backdrop', 'div.modal', 'div.modal-body',
         'div.hire-board', 'div.post-card.frontdesk-card', 'div.post-head',
         'div.post-name']
INHERITED = ('overflow-wrap', 'word-break')
# Properties that produce one line by removing characters rather than by
# leaving the word alone. Each is checked for separately below.
CLIPPING = ('white-space', 'text-overflow', 'overflow', 'max-width', 'width')


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def rules(text):
    """(selector, {prop: value}, order) for every rule, comments stripped."""
    text = re.sub(r'/\*[\s\S]*?\*/', '', text)
    out, i = [], 0
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', text):
        sel_group, body = m.group(1).strip(), m.group(2)
        if sel_group.startswith('@'):
            continue                      # at-rule preludes carry no decls
        decls = {}
        for d in body.split(';'):
            if ':' in d:
                p, _, v = d.partition(':')
                decls[p.strip().lower()] = v.strip().lower()
        if not decls:
            continue
        for sel in sel_group.split(','):
            out.append((sel.strip(), decls, i))
            i += 1
    return out


def specificity(sel):
    """(ids, classes, elements) — enough for the flat selectors in this file."""
    s = re.sub(r'::?[a-z-]+(\([^)]*\))?', '', sel)
    return (len(re.findall(r'#[\w-]+', s)),
            len(re.findall(r'\.[\w-]+', s)) + len(re.findall(r'\[[^\]]+\]', s)),
            len(re.findall(r'(?:^|[\s>+~])([a-z][\w-]*)', s)))


def matches(sel, node):
    """Does this selector's RIGHTMOST compound match `node`?

    Only the subject matters here: every rule in play is a flat class rule,
    and a descendant-combinator rule that matches on its subject is treated
    as applying. That is the permissive direction -- it can only make the
    test believe MORE rules reach the name, never fewer, so it cannot hide
    a break-anywhere that really lands.
    """
    subject = re.split(r'[\s>+~]+', sel.strip())[-1]
    subject = re.sub(r'::?[a-z-]+(\([^)]*\))?', '', subject)
    tag, classes = node.split('.')[0], set(node.split('.')[1:])
    want_classes = set(re.findall(r'\.([\w-]+)', subject))
    want_tag = re.match(r'^([a-z][\w-]*)', subject)
    if want_tag and want_tag.group(1) != tag:
        return False
    if not want_classes and not want_tag:
        return False
    return want_classes <= classes


def winner(all_rules, node, prop):
    """The declaration a browser would apply to `node` for `prop`, or None."""
    best = None
    for sel, decls, order in all_rules:
        if prop not in decls or not matches(sel, node):
            continue
        key = specificity(sel) + (order,)
        if best is None or key > best[0]:
            best = (key, decls[prop], sel)
    return best


def main():
    print('a coworker name is never broken in half')
    all_rules = rules(CSS.read_text(encoding='utf-8'))
    check('the stylesheet parsed into something usable',
          len(all_rules) > 500, f'{len(all_rules)} rules')

    print('1. the rule the name was inheriting still exists')
    # If this ever stops being true the reset below is harmless but pointless,
    # and the next reader deserves to be told rather than to find a mystery.
    source = [(sel, d) for sel, d, _ in all_rules
              if any(d.get(p) in ('anywhere', 'break-word', 'break-all')
                     for p in INHERITED)
              and 'modal-body' in sel]
    check('a modal body still breaks long words anywhere',
          bool(source),
          'styles.css: this is what made the name splittable. If it is gone, '
          'the reset on .post-name is dead weight and this suite is guarding '
          'nothing — delete both together, not one.')

    print('2. …and the name no longer inherits it')
    # Walked as a browser walks it: an inherited property takes the ancestor's
    # value only when nothing sets it on the element itself.
    effective = {}
    for prop in INHERITED:
        value = 'normal'
        for node in CHAIN:
            w = winner(all_rules, node, prop)
            if w:
                value = w[1]
        own = winner(all_rules, CHAIN[-1], prop)
        effective[prop] = (value, own)
    for prop, (value, own) in effective.items():
        check(f'{prop} resolves to a value that keeps a word whole',
              value in ('normal', 'initial', 'unset', 'revert'),
              f'resolves to {value!r} on .post-name — a name is one word and '
              'the office wrote it, so there is nothing to defend against here')
        check(f'...set on the name itself, not left to the ancestors',
              own is not None,
              f'{prop} is inherited from an ancestor; a rule that a chat '
              'bubble needs must not decide how a proper noun is spelled')

    print('3. the fixes that would be worse than the bug')
    # Every one of these also yields "one line", and every one of them does it
    # by removing characters from a name the office chose. Measured: the
    # ellipsis variant truncated a 9-character name.
    for prop in CLIPPING:
        w = winner(all_rules, CHAIN[-1], prop)
        bad = {'white-space': ('nowrap', 'pre'), 'text-overflow': ('ellipsis', 'clip'),
               'overflow': ('hidden', 'clip')}.get(prop)
        if bad:
            check(f'the name is not made to fit by {prop}',
                  w is None or w[1] not in bad,
                  f'{prop}: {w[1] if w else None!r} — this renders "Herme…", '
                  'and a misspelt name is a worse failure than an ugly one')
        else:
            check(f'the name is not given a hard {prop}',
                  w is None,
                  f'{prop}: {w[1] if w else None!r} — a fixed size re-creates '
                  'the squeeze this fix removed, on a different card')
    # The floor that makes the reset sufficient: min-width:auto on a flex item
    # stops the shrink at min-content, which -- once the word cannot break --
    # is the whole word. Measured what min-width:0 actually does rather than
    # assuming, because the first draft of this message assumed and was wrong:
    # the word does NOT split again (it cannot), the box shrinks back to
    # 57.8px and the name OVERFLOWS it. Harmless while nothing clips, and the
    # last letter is gone the moment something does.
    mw = winner(all_rules, CHAIN[-1], 'min-width')
    check('the flex floor that makes the reset work is left alone',
          mw is None or mw[1] == 'auto',
          f'min-width: {mw[1] if mw else None!r} — measured: the box shrinks '
          'back to 57.8px for a 60px word and the name spills out of it, '
          'which any clipping ancestor turns back into a lost letter')

    print('4. the markup this all rests on')
    src = HIRE.read_text(encoding='utf-8')
    check('the cards still render the name in .post-name',
          src.count('className="post-name"') >= 3,
          'modals/hire.jsx: three card kinds share the class; a fourth that '
          'invents its own would not be covered by any of the above')
    check('...beside the badge that squeezed it',
          'className="post-tag"' in src and 'NOT RUNNING' in src,
          'modals/hire.jsx: the widest badge is the reason this showed on '
          'exactly one card')

    print()
    if FAILS:
        print(f'coworker name: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('coworker name: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
