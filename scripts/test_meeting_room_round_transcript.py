#!/usr/bin/env python3
"""The office-floor Meeting Room's second speaker couldn't hear the first.

`features.jsx`'s `MeetingRoom` (the office-floor door, not the chat-thread
modal in `modals/collab.jsx`) runs one round as a sequential loop over
seated participants — visually a real turn-taking conversation, typing
indicator and all. But `transcript` was a `const`, built once from prior
messages plus the boss's new line, BEFORE the loop started. Every
participant's prompt read "Meeting transcript so far: <that same frozen
string>", no matter how many round-mates had already answered in front of
them. The CEO's closing synthesis used the identical frozen `transcript`.

Verified live on a throwaway office (2 seated coworkers, Ollama): asked to
name who spoke before them, the SECOND coworker answered "no one spoke
before me — I'm the first to respond", while the first coworker's reply
sat right there in the room, a few pixels above, already rendered. The
model wasn't wrong to say that — its prompt genuinely contained no trace
of the first reply. After making `transcript` a running accumulator
(`let`, appended after each turn with `\n${name}: ${cleaned}`), the same
probe correctly had the second coworker's reply reference the first's.

This checks the structural fix rather than model output (Ollama replies
aren't byte-stable): `transcript` must be reassignable (`let`, not
`const`), and the loop over participants must append each cleaned reply to
it before the next iteration reads it. Both conditions have to hold or a
partial fix (e.g. `let` with no append, or an append that lands after the
loop) would silently reintroduce the bug.

Run: python3 scripts/test_meeting_room_round_transcript.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURES = ROOT / 'features.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('meeting room — round-mates must hear each other within a round')
    if not FEATURES.is_file():
        print('  FAIL  missing features.jsx')
        return 1

    src = FEATURES.read_text(encoding='utf-8')

    m = re.search(r'function MeetingRoom\(', src)
    check('MeetingRoom is defined in features.jsx', m is not None)
    if not m:
        print('\nmeeting room: 1 FAILED')
        return 1

    # Isolate the function body (up to the next top-level `function ` at
    # column 0, which is how every sibling component in this file is split).
    start = m.start()
    nxt = re.search(r'\nfunction \w', src[start + 10:])
    body = src[start:start + 10 + nxt.start()] if nxt else src[start:]

    check("`transcript` is declared with let, not const — it must be "
          "reassignable across the round",
          re.search(r'\blet\s+transcript\s*=', body) is not None,
          "found `const transcript` (or no declaration) — a const frozen "
          "before the loop is exactly the bug: every participant's prompt "
          "gets the same pre-round snapshot no matter how many round-mates "
          "already answered")

    # The participant loop and the accumulation must both exist, and the
    # accumulation must be textually INSIDE the loop (between its `for` and
    # the CEO's synthesis call that follows it) — not after the loop, which
    # would leave every participant but the last still deaf to the others.
    loop_m = re.search(r'for\s*\(const ph of placeholders\)\s*\{', body)
    ceo_m = re.search(r'await HQ\.ceoStream\(', body)
    check('the participant loop exists', loop_m is not None)
    check("the CEO's synthesis call exists after the loop",
          ceo_m is not None and loop_m is not None and ceo_m.start() > loop_m.start())

    if loop_m and ceo_m and ceo_m.start() > loop_m.start():
        loop_and_after = body[loop_m.start():]
        # end of the for-loop's own block: find the matching close brace by
        # bracket depth, starting right after the loop's opening `{`.
        depth = 0
        i = loop_and_after.index('{')
        loop_body_start = i + 1
        j = i
        while j < len(loop_and_after):
            if loop_and_after[j] == '{':
                depth += 1
            elif loop_and_after[j] == '}':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        loop_body = loop_and_after[loop_body_start:j]

        check('each turn appends its own cleaned reply to `transcript` '
              'before the next iteration reads it',
              re.search(r'transcript\s*\+=.*ph\.agentRef\.name', loop_body) is not None,
              "no `transcript += ...ph.agentRef.name...` found inside the "
              "participant loop's own block — without this, round-mate N+1 "
              "never learns what round-mate N just said")

        # The append must come from the CLEANED reply (post visibleReply),
        # not the raw streaming buffer — a raw marker leaking into what
        # every other participant reads as context would compound, not fix.
        check('the appended text is the cleaned reply, not the raw buffer',
              re.search(r'transcript\s*\+=\s*`[^`]*\$\{cleaned\}', loop_body) is not None
              or re.search(r'const cleaned = HQ\.visibleReply\([^)]*\)[\s\S]{0,120}transcript\s*\+=',
                           loop_body) is not None,
              "expected the append to use the same `cleaned` variable "
              "already passed to updateById(), not `buf`")

    print()
    if FAILS:
        print(f'meeting room: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('meeting room: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
