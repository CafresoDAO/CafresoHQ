#!/usr/bin/env python3
"""The chat meeting room promised turn-taking and delivered three monologues.

There are TWO surfaces in this office called a meeting room, and only one
of them was ever fixed. `features.jsx`'s floor-level `MeetingRoom` runs a
real sequential round with a running transcript (pinned by
test_meeting_room_round_transcript.py, after the same bug was found and
fixed there). The CHAT meeting — the one the ROOMS ▸ Meeting rooms door
creates, which owns the `meeting:<id>` thread — was written later and got
none of it.

Driven live 2026-08-13 with three attendees and a scripted brain per
coworker. What actually happened when the boss asked the room a question:

  · all three were dispatched inside 19ms of each other (Promise.all),
  · every prompt was assembled BEFORE anybody had spoken, so no attendee's
    prompt contained one word of any other attendee's reply,
  · and each was told, in the office's own voice, that the others were
    "receiving the SAME request in parallel" and to guess at what a
    teammate was "likely to say".

Meanwhile the seating modal (modals/collab.jsx) says, at the moment the
boss is choosing who to invite:

    Attendees (pick at least one — they'll all see each other's replies)

They never saw each other's replies. Three people answering the same
question in one thread without hearing each other is not a meeting, and
the office called it one on the way in.

The fix makes the promise true rather than softening it: a meeting runs
its attendees in TURN, each handed what the room has actually said so far.
That costs wall-clock, which is what a meeting costs, and it buys the
thing the room exists for — attendee two can disagree with attendee one by
name. Project rooms stay parallel: a broadcast to everyone assigned is a
memo, and nothing there ever promised otherwise.

Verified live after the fix, reading the prompts off the wire: Nova opened
having heard nothing, Pip's prompt carried Nova's exact words, and Rex's
carried Nova's and Pip's, in order.

Run: python3 scripts/test_meeting_thread_takes_turns.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


chat = (ROOT / 'ui' / 'chat.jsx').read_text(encoding='utf-8')
app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
collab = (ROOT / 'modals' / 'collab.jsx').read_text(encoding='utf-8')

print('meeting thread — the room takes turns')

# ── 1. the promise that has to be kept ──────────────────────────────────
# Pinned so the copy and the behaviour cannot drift apart silently. If
# someone deletes this sentence the test should be revisited deliberately,
# not pass by accident because the claim quietly disappeared.
check('the seating modal still promises attendees hear each other',
      "they'll all see each other's replies" in collab,
      'modals/collab.jsx: the promise this whole file exists to keep is gone '
      '— if it was removed on purpose, retire these checks on purpose too')

# ── 2. a meeting is sequential ──────────────────────────────────────────
room = re.search(r"if \(activeRoom && activeRoom\.participants\.length\) \{[\s\S]{0,6000}?\n    \}", chat)
check('the room send path is still where it was', bool(room),
      'ui/chat.jsx: could not find the activeRoom branch')
body = room.group(0) if room else ''

check('a meeting is dispatched one attendee at a time',
      re.search(r"activeRoom\.kind === 'meeting'", body)
      and re.search(r'for \(const a of recipients\) \{[\s\S]{0,900}?await onDispatchToAgent', body),
      'ui/chat.jsx: a meeting must await each attendee in turn — Promise.all '
      'assembles every prompt before anyone has spoken, which is the bug')

# The barrier matters, not just the loop: an unawaited call inside a for-of
# is still parallel, and would pass a naive "is there a loop" check.
meeting_branch = re.search(r"activeRoom\.kind === 'meeting'\)[\s\S]{0,2400}?\n          \} else \{", body)
mb = meeting_branch.group(0) if meeting_branch else ''
check('...and the turn is actually awaited, not merely looped',
      'await onDispatchToAgent' in mb and 'Promise.all' not in mb,
      'ui/chat.jsx: an unawaited dispatch inside a for-of is still parallel')

check('each attendee is handed what the room has already said',
      'heardSoFar' in mb and re.search(r'heardSoFar\.push\(', mb),
      'ui/chat.jsx: the transcript must accumulate between turns')

# A failed or empty turn must not enter the transcript. The next speaker
# would be asked to build on a silence presented as a contribution.
check('only what was actually said is passed on',
      re.search(r'if \(said && String\(said\)\.trim\(\)\)[\s\S]{0,160}heardSoFar\.push', mb),
      'ui/chat.jsx: an empty or failed turn must not enter the transcript')

# One attendee dying must not end the meeting for everyone after them.
check('one attendee bowing out does not end the meeting',
      re.search(r'try \{[\s\S]{0,900}?\} catch \(err\) \{\s*\n\s*bowOut\(a, err\);', mb),
      'ui/chat.jsx: the per-turn catch must be INSIDE the loop, or the first '
      'failure skips everyone still waiting to speak')

# ── 3. a project room is still a broadcast ──────────────────────────────
# Nothing promised turn-taking there, and serialising a project broadcast
# would triple its latency to keep a promise nobody made.
check('a project room still goes out to everyone at once',
      'Promise.all(recipients.map(' in body,
      'ui/chat.jsx: the non-meeting branch must stay parallel')

# ── 4. the prompt has to describe the room it is actually in ────────────
check('dispatchToAgent accepts the transcript and the turn flag',
      re.search(r'heardSoFar = \[\],\s*\n\s*meetingTurn = false,', app),
      'app.jsx: both options must be declared, or they arrive as undefined '
      'and every attendee silently gets the parallel framing again')

note = re.search(r'const heard = \(heardSoFar[\s\S]*?\n    \}\n    // ── DM injection defense', app)
check('the room note branches on which room it is', bool(note),
      'app.jsx: coNote block not found')
nb = note.group(0) if note else ''
check('a speaker who has heard the room is given the words, not the names',
      'here is what has actually been said so far' in nb
      and re.search(r'heard\.map\(h =>', nb),
      'app.jsx: the transcript itself must reach the prompt')
check('the opener is told it is a meeting, not a parallel room',
      re.search(r'meetingTurn && roomList', nb)
      and 'You are opening a meeting with' in nb,
      'app.jsx: the first speaker has heard nothing but is NOT in a parallel '
      'room — telling them so invites a standalone memo from the one person '
      'everyone else is about to answer by name')
check('the parallel wording survives only for a genuine broadcast',
      nb.count('receiving the SAME request in parallel') == 1
      and nb.index('receiving the SAME request in parallel') > nb.index('meetingTurn'),
      'app.jsx: the parallel sentence must be the LAST branch — reachable '
      'only when this is neither a turn nor an opener')

# ── 5. the reply has to come back to the caller ─────────────────────────
# The meeting cannot pass on what it cannot see. dispatchToAgent returned
# undefined, and `cleanBuf` is born inside the try and dies with it.
check('a dispatch hands back what the coworker said',
      re.search(r'\n    return saidAloud;', app)
      and re.search(r"let saidAloud = '';", app)
      and 'saidAloud = cleanBuf;' in app,
      'app.jsx: the reply must be hoisted past the try and returned')
check('a run that threw reports saying nothing, not the last turn\'s words',
      re.search(r"let saidAloud = '';[\s\S]{0,400}?try \{", app),
      'app.jsx: saidAloud must be initialised empty before the try, so a '
      'failed turn cannot report stale text as this turn\'s contribution')

# ── 6. the composer names who will read it ──────────────────────────────
# Smaller, same class: the banner listed three attendees and the box under
# it still said "Message CafresoHQ…", who is not in the room.
ph = re.search(r'placeholder=\{[\s\S]{0,900}?\n\s*/>', chat[chat.index('const send'):])
ph = ph.group(0) if ph else ''
check('the composer addresses the room it is in',
      'activeRoom && activeRoom.participants.length' in ph
      and re.search(r"`Message \$\{activeRoom\.participants\.length === 1", ph),
      'ui/chat.jsx: in a room the message does not go to CafresoHQ')
# Third instance of the same defect, found on the hand-off path: the banner
# above the box said "Talking to Nova" while the box said "Message
# CafresoHQ…", and the next thing typed went to Nova.
check('...and the specialist, once the boss has been handed to one',
      re.search(r'handoffAgent\s*\n?\s*\?\s*`Message \$\{handoffAgent\.name\}', ph),
      'ui/chat.jsx: during a hand-off the message goes to the specialist, '
      'not to CafresoHQ — the banner already says so')
check('...and still addresses CafresoHQ everywhere else',
      "'Message CafresoHQ… (@ mention · ↵ send · /brainstorm for team)'" in chat,
      'ui/chat.jsx: the direct thread must keep its own placeholder as the '
      "ternary's fallback arm — quoted form matters, since a bare attribute "
      'means the room-aware branch was removed rather than added to')

print()
if FAILS:
    print(f'meeting thread: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
    raise SystemExit(1)
print('meeting thread: all checks passed')
