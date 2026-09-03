#!/usr/bin/env python3
"""A bounded transcript has to say it is bounded — on the surface the boss
reads, not only in the registry behind it.

The message registry already learned this (#see test_a_trimmed_record_says_
it_was_trimmed): a rolling cap is the right call, but spending the boss's
trust on it silently is not, so `persistableMessages` stamps `droppedBefore`
on the oldest survivor and the inbox prints "⋯ N older messages rolled out".
The chat — the surface the boss actually reads, and the only substantive
office state that lives in localStorage rather than a file — had the same two
caps and none of the disclosure.

Reproduced 2026-09-03 on a scratch office (127.0.0.1:8897) seeded with 130
turns in one thread:

    after one reload   screen: 100 turns, opening on "turn 31"
                       storage: 80 turns, opening on "turn 51"
    after two          screen:  80 turns, opening on "turn 51"

Fifty turns gone for good, the screen and the saved copy disagreeing about
how much was left, and nothing anywhere saying so. The thread simply began at
turn 51, which reads exactly like a beginning.

The cap is not the bug and this suite does not ask for it to be removed. What
this holds is:

  1. the count is PER THREAD — the chat interleaves every room and the view
     shows one at a time, so one total would be a second wrong answer
  2. it ACCUMULATES across passes, so it is everything the room has shed and
     not the size of the most recent trim
  3. a room that lost nothing says nothing
  4. the surface reads it off the oldest survivor of the room on screen, and
     stays quiet while a search is spanning every room

`capChatFair` is lifted from app/storage.jsx and executed under Node — the
same function both caps go through, so this exercises the real eviction and
not a description of it.

Run: python3 scripts/test_the_chat_says_where_it_starts.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORAGE = ROOT / 'app' / 'storage.jsx'
CHAT = ROOT / 'ui' / 'chat.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift(src, name, where):
    """One top-level `const <name> = …;` to its depth-0 semicolon. Parens,
    braces and brackets are all counted — these bodies hold arrow functions,
    object literals and Map calls. Located by NAME, never by a signature or
    a body fragment: a locator pinned to text reports a rename as a
    regression and (worse) hands back an empty slice that satisfies any
    check phrased as a negative (see #159)."""
    m = re.search(r'^const %s = ' % re.escape(name), src, re.M)
    if not m:
        raise SystemExit('no top-level `const %s = ` in %s' % (name, where))
    depth = 0
    for j in range(m.start(), len(src)):
        c = src[j]
        if c in '({[':
            depth += 1
        elif c in ')}]':
            depth -= 1
        elif c == ';' and depth == 0:
            return src[m.start():j + 1]
    raise SystemExit('unterminated `const %s`' % name)


def turns(thread, n, start=1):
    return [{'id': '%s%d' % (thread, i), 'thread': thread,
             'text': 'turn %d' % i} for i in range(start, start + n)]


def main():
    print('The chat says where it starts')

    storage = STORAGE.read_text(encoding='utf-8')
    chat_src = CHAT.read_text(encoding='utf-8')

    # --- §1: the real eviction, driven ---------------------------------
    harness = '\n'.join([
        lift(storage, 'capChatFair', 'app/storage.jsx'),
        lift(storage, 'persistableChat', 'app/storage.jsx'),
        'const OUT = [];',
        'for (const c of CASES) {',
        '  const [label, msgs, passes] = c;',
        '  let xs = msgs;',
        # Both caps, in the order a real office applies them: the in-memory
        # ceiling on every render past 120, then the persist transform.
        '  for (let p = 0; p < passes; p++) {',
        '    if (xs.length > 120) xs = capChatFair(xs, 100);',
        '    xs = persistableChat(xs);',
        '  }',
        '  const perThread = {};',
        '  for (const m of xs) {',
        '    const t = m.thread || "direct";',
        '    if (!(t in perThread)) perThread[t] = { first: m.text, dropped: m.droppedBefore || 0, n: 0 };',
        '    perThread[t].n++;',
        '  }',
        '  OUT.push([label, perThread, xs.length]);',
        '}',
        'console.log(JSON.stringify(OUT));',
    ])

    # (label, messages, how many save passes, expectations per thread)
    CASES = [
        ('the measured case: 130 turns in one room, one pass',
         turns('direct', 130), 1,
         {'direct': {'first': 'turn 51', 'dropped': 50, 'n': 80}}),

        ('...and a second pass adds nothing, because nothing more was shed',
         turns('direct', 130), 2,
         {'direct': {'first': 'turn 51', 'dropped': 50, 'n': 80}}),

        ('a room under the cap keeps every turn and says nothing',
         turns('direct', 40), 1,
         {'direct': {'first': 'turn 1', 'dropped': 0, 'n': 40}}),

        ('exactly at the cap is not over it',
         turns('direct', 80), 1,
         {'direct': {'first': 'turn 1', 'dropped': 0, 'n': 80}}),

        ('the quiet room is not charged for the busy one — it keeps its '
         'turns AND its silence',
         turns('direct', 10) + turns('project:x', 120), 1,
         {'direct': {'first': 'turn 1', 'dropped': 0, 'n': 10},
          'project:x': {'first': 'turn 51', 'dropped': 50, 'n': 70}}),

        # Two rooms, one after the other rather than interleaved — the shape
        # a boss produces by talking in one room all morning and another all
        # afternoon. Eviction walks oldest-first, so the morning room pays
        # until it hits its floor of 15 and the afternoon room pays the rest.
        # The numbers are lopsided (15 kept vs 65) and that is the documented
        # behaviour, not a defect: what matters here is that each room reports
        # ITS OWN loss. One shared total would tell the boss standing in the
        # afternoon room that 120 messages were dropped out of it.
        ('two busy rooms, one after the other — each answers for itself even '
         'when the floor makes the split lopsided',
         turns('direct', 100) + turns('team', 100), 1,
         {'direct': {'first': 'turn 86', 'dropped': 85, 'n': 15},
          'team': {'first': 'turn 36', 'dropped': 35, 'n': 65}}),

        # And the shape a live office actually produces: two rooms talking
        # over each other, so eviction alternates between them.
        ('two rooms interleaved — the ordinary case',
         [m for pair in zip(turns('direct', 100), turns('team', 100))
          for m in pair], 1,
         {'direct': {'dropped': 60, 'n': 40},
          'team': {'dropped': 60, 'n': 40}}),
    ]

    harness = 'const CASES = %s;\n' % json.dumps(
        [[c[0], c[1], c[2]] for c in CASES]) + harness

    proc = subprocess.run(['node', '--input-type=module', '-e', harness],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr.strip()[:2000])
        raise SystemExit('the lifted cap did not run under node')
    got = json.loads(proc.stdout.strip().splitlines()[-1])

    for case, (_label, per_thread, total) in zip(CASES, got):
        label, msgs, _passes, want = case
        for thread, w in want.items():
            actual = per_thread.get(thread)
            if actual is None:
                check('%s — %s survived at all' % (label[:52], thread), False,
                      'the room is gone entirely; kept %r' % (list(per_thread),))
                continue
            for field, value in w.items():
                check('%s — %s.%s' % (label[:52], thread, field),
                      actual[field] == value,
                      '%s is %r, expected %r  (room kept %d)'
                      % (field, actual[field], value, actual['n']))

    # The rule, stated once over every case: no room ever claims to have
    # dropped messages it did not, and no room that dropped some stays quiet.
    for case, (_label, per_thread, _total) in zip(CASES, got):
        want = case[3]
        liars = [t for t, a in per_thread.items()
                 if bool(a['dropped']) != bool(want.get(t, {}).get('dropped'))]
        check('%s — every room\'s marker matches whether it actually lost '
              'anything' % case[0][:44], not liars, liars)

    # --- §2: the surface reads it -------------------------------------
    # Whatever the copy is, three things have to hold about where it comes
    # from: the oldest message ON SCREEN, only when there is one, and never
    # while a search is spanning rooms.
    # Located by the ONE thing that cannot change without changing the
    # feature — the JSX block conditioned on `droppedBefore` — and then the
    # gates are asserted separately. Written this way on purpose: pinning
    # the whole condition as a literal would report a reordered `&&` as a
    # missing disclosure, which is the #159 failure mode.
    notice = re.search(r'\{([^\n]*droppedBefore[^\n]*?)&& \(([\s\S]*?)\n\s*\)\}',
                       chat_src)
    check('the scrollback has a disclosure, conditioned on how much this '
          'room dropped', notice is not None,
          'ui/chat.jsx: nothing in the scrollback reads `droppedBefore` — '
          'the cap is silent again')
    if notice:
        cond = notice.group(1)
        check('...gated on the oldest message ON SCREEN, so a room that '
              'lost nothing stays quiet',
              'visibleChat[0].droppedBefore' in cond,
              'the condition reads %r — a total, or another room\'s marker'
              % cond.strip())
        check('...and suppressed while a search is spanning every room, '
              'where the first row is not this room\'s oldest survivor',
              '!searchQuery' in cond,
              'the condition reads %r' % cond.strip())
        check('...and guarded against an empty room',
              'visibleChat.length > 0' in cond or 'visibleChat[0] &&' in cond,
              'the condition reads %r — visibleChat[0] can be undefined'
              % cond.strip())
    if notice:
        # Whitespace-normalised before matching. The first draft of this file
        # looked for the sentence literally and failed on the fix that was
        # already in place, because the copy wraps mid-phrase in the source.
        # A check that reports a line break as a regression is the #159
        # hazard wearing a different hat.
        body = re.sub(r"\s+", " ", notice.group(2))
        check('...and it prints the count rather than a vague "some"',
              'visibleChat[0].droppedBefore' in body,
              'the notice does not render the number it was given')
        check('...and it says the loss is permanent, which is the part a '
              'boss would otherwise assume is recoverable',
              'gone for good' in body,
              'ui/chat.jsx: %r' % body[:200])
        check('...and it says this is not the beginning, which is the '
              'misreading being corrected',
              'not where the conversation started' in body,
              'ui/chat.jsx: %r' % body[:200])

    # Above the list. The dropped ones are the OLDEST and the top is where
    # someone scrolling back stops — the same reasoning the inbox states.
    if notice:
        listpos = chat_src.find('{visibleChat.map(m => {')
        check('the disclosure sits above the list, not under it',
              -1 < notice.start() < listpos,
              'notice at %d, list at %d' % (notice.start(), listpos))

    # --- §3: the premise ------------------------------------------------
    check('the chat is still capped in two places — this disclosure exists '
          'because both of them evict',
          'capChatFair(xs, 80)' in storage
          and re.search(r'capChatFair\(prev, 100\)', (ROOT / 'app.jsx')
                        .read_text(encoding='utf-8')) is not None,
          'app/storage.jsx + app.jsx: the caps moved; re-check what the '
          'notice is counting')
    check('`droppedBefore` survives the persist transform, which strips '
          'other per-render fields off every message',
          re.search(r'\(\{ streaming, error, \.\.\.rest \}\)', storage)
          is not None,
          'app/storage.jsx: persistableChat now strips by allow-list — make '
          'sure droppedBefore is on it')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
