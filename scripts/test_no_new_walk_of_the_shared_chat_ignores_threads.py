#!/usr/bin/env python3
"""Tripwire: a new unscoped walk of the shared chat array fails the suite.

The chat is ONE array interleaving every room. Three shipped defects came
from code walking it as if it were one conversation:

  - Focus Mode showed cross-thread chatter under the CEO's icon (#44);
  - the Delegate button grabbed its brief from whatever room spoke last
    and filed its whole exchange into Direct (#45);
  - both history caps let the busiest room evict every other room (#46).

Each fix taught ONE consumer the `(m.thread || 'direct')` convention.
This test teaches the file: every scan-type read of `chat` in app.jsx
and ui/chat.jsx — filter/find/some/reverse/slice/map over the shared
array — must either

  (a) scope by thread in the same expression neighborhood,
  (b) be an id-lookup for a specific message (`x.id === m.id` — already
      as scoped as a read can be), or
  (c) be on the explicit allowlist below, with the reason written down.

A new consumer that walks the array blind shows up here as a FAIL with
this docstring attached, instead of shipping as defect #47.

Allowlisted on purpose:
  - `ceoBusy={chat.some(m => m.from === 'ceo' && m.streaming)}` — the CEO
    is one entity across all rooms; "is the CEO mid-stream anywhere" is a
    genuinely global question.
  - `chat.length` — a size read, not a walk.

Run: python3 scripts/test_no_new_walk_of_the_shared_chat_ignores_threads.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


# A scan-type read of the bare shared array. `chatRef.current`,
# `visibleChat`, `recentChat`, `persistableChat` are other names on
# purpose — the ref is the fix for staleness, the rest are already-scoped
# derivatives. `chat.length` is a size read, not a walk.
SCAN = re.compile(
    r'(?<![\w.$])(?:\[\.\.\.chat\]|chat)\s*\.\s*'
    r'(?:filter|find|findIndex|findLast|some|every|reverse|slice|map|forEach|reduce)\s*\(')

ALLOWED = [
    # (marker that must appear in the read's neighborhood, why it is fine)
    # Unparenthesized on purpose: it matches `(m.thread || 'direct') === t`
    # and `const t = m.thread || 'direct';` alike — both are the convention.
    (".thread || 'direct'", 'scoped by thread'),
    ('x.id === m.id', 'id-lookup for one specific message'),
    ("m.from === 'ceo' && m.streaming", 'the CEO is global across rooms'),
]


def main():
    print('no new walk of the shared chat ignores threads')
    offenders = []
    scanned = 0
    for rel in ('app.jsx', 'ui/chat.jsx'):
        src = strip_comments((ROOT / rel).read_text(encoding='utf-8'))
        for m in SCAN.finditer(src):
            scanned += 1
            # Lift the WHOLE call by paren matching — the predicate and any
            # multi-line callback body live inside these parens. A first
            # draft used an 8-line window instead, and a planted unscoped
            # read passed by sitting near a correctly-scoped neighbor;
            # adjacency is not scoping.
            # Follow the whole chain: `[...chat].reverse().find(pred)` keeps
            # its predicate in the SECOND call, so stopping at reverse()'s
            # empty parens would judge the read by the wrong parentheses.
            start = src.index('(', m.end() - 1)
            call = None
            pos = start
            while True:
                depth = 0
                end = None
                for j in range(pos, len(src)):
                    if src[j] == '(':
                        depth += 1
                    elif src[j] == ')':
                        depth -= 1
                        if depth == 0:
                            end = j
                            break
                if end is None:
                    break
                call = src[m.start():end + 1]
                nxt = re.match(r'\s*\.\s*\w+\s*\(', src[end + 1:])
                if not nxt:
                    break
                pos = end + 1 + nxt.end() - 1
            if call is None:
                offenders.append(f'{rel}: unbalanced parens after {m.group(0)!r}')
                continue
            if not any(marker in call for marker, _why in ALLOWED):
                line_no = src[:m.start()].count('\n') + 1
                offenders.append(f'{rel}:~{line_no}: {call.strip()[:100]}')
    check('every scan of the shared chat is scoped, id-bound, or allowlisted',
          not offenders,
          offenders or '')
    # The tripwire must be watching something — if the scan count collapses
    # to zero the regex has drifted off the code, and a green from blindness
    # is the failure mode this suite exists to catch.
    check('...and the tripwire is not vacuous — it found the known reads',
          scanned >= 4, f'{scanned} scan-reads found (expected the known 4+)')
    # The known-good reads it should be seeing:
    app = strip_comments((ROOT / 'app.jsx').read_text(encoding='utf-8'))
    chatui = strip_comments((ROOT / 'ui' / 'chat.jsx').read_text(encoding='utf-8'))
    check('the delegate brief-finder is still thread-scoped',
          "&& (m.thread || 'direct') === t" in app)
    check('the ceoBusy global read is still the only chat.some in app.jsx',
          len(re.findall(r'(?<![\w.$])chat\.some\(', app)) == 1)
    check('"Ask this again" and RETRY still scan by id then by thread',
          chatui.count('const idx = chat.findIndex(x => x.id === m.id);') == 2
          and chatui.count("(chat[i].thread || 'direct') === mThread") == 2,
          [chatui.count('const idx = chat.findIndex(x => x.id === m.id);'),
           chatui.count("(chat[i].thread || 'direct') === mThread")])

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
