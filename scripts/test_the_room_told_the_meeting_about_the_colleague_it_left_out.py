#!/usr/bin/env python3
"""The room's "@Dax isn't in this meeting" note was delivered TO the meeting.

`## 350.` gave the multi-agent room the thing it had never had: when the
boss @mentions somebody the room does not seat, the office says so instead
of dropping the name off the end of a filter. Right on the screen. Its own
comment, and the ledger entry with it, then promised something it did not
do:

    Screen-only, and deliberately: `body` has the mentions stripped off
    it, so nobody in the room is being told about a colleague who is not
    here. This is the boss's own routing being narrated back to them.

Stripping the mentions out of `body` was only half of it. The note is its
own bubble in the same `chat` array (`from:'system'`, `name:'HQ'`), every
dispatch reads `chatRef.current.slice(-6)`, and `chatToMessages` — "the
single place stored chat becomes prompt" — walks every bubble in that slice
with no filter on who wrote it. Measured 2026-09-05 under node on the real
`extractAllMentions -> roomStrayNote -> chatToMessages` chain, meeting
"Migration sync" seating Kip and Plato, Dax hired and idle, the boss typing
"@Kip @Dax in one word, is the migration risky?":

    chatToMessages(chat, { selfName: 'Kip' })
      [ { role: 'user', content: '@Kip @Dax in one word, is the migration
                                  risky?' },
        { role: 'user', content: "[HQ]: (@Dax isn't in this meeting — only
                                  @Kip was asked. Invite them to the
                                  meeting, or ask in the DIRECT thread.)" } ]

The absent colleague named to the room after all, and a route-out written
for the boss ("Invite them to the meeting, or ask in the DIRECT thread")
arriving in the slot the model reads as something a participant said. A
meeting takes turns, so the note is on disk and rendered long before
attendee two is dispatched; and it stays in the last six for every turn
after it, in this thread or any other.

This is the class `## 351.` had named one entry earlier — "the office's
report of its OWN actions must not re-enter the model's context as prior
conversation" — and the DIRECT thread's "(unknown teammate: @X)", the note
`## 350.` was modelled on, had been doing it for longer.

Fix: a `officeVoice: true` flag on those two bubbles, honoured at the choke
point. A flag and not a pattern, because these sentences interpolate names
— a regex over them would either miss a coworker called "Meeting" or eat a
coworker's real parenthetical aside.

Two things deliberately keep reaching the model, and this test pins both so
the fix cannot grow into a blanket "drop everything the office wrote":

  * Stage directions — "(dropped … on Vera's desk)", "✓ APPROVED — …" —
    were filed `from:'system'` on purpose so the model would read them
    labelled `[HQ]:` instead of in the boss's voice.
  * The DIRECT thread's "(nobody here is called @X … Sending this to
    CafresoHQ instead.)" is handed to the CEO on purpose, and says so in
    its own comment: "The CEO cannot clarify what it was never told."

Run: python3 scripts/test_the_room_told_the_meeting_about_the_colleague_it_left_out.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAT = ROOT / 'ui' / 'chat.jsx'
CAST = ROOT / 'app' / 'cast.jsx'
FLOOR = ROOT / 'app' / 'floor.jsx'
STORAGE = ROOT / 'app' / 'storage.jsx'
RUNTIME = ROOT / 'hq-runtime.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Scan code, never prose — the comments written with this fix quote the
    leaked envelope line verbatim, flag name and all."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, header):
    """Lift a whole function body by brace matching, so the REAL
    implementation runs in the harness instead of being pattern-matched from
    a distance. Walks the parameter parens first so a destructured-default
    param (`{ omitLastCeo = false } = {}`) is not mistaken for the body."""
    i = src.index(header)
    p = src.index('(', i)
    d = 0
    for k in range(p, len(src)):
        if src[k] == '(':
            d += 1
        elif src[k] == ')':
            d -= 1
            if d == 0:
                p = k
                break
    j = src.index('{', p)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise SystemExit('unbalanced braces lifting ' + header)


def stmt_lift(src, opener):
    """A `const x = …;` declaration, by paren/brace/bracket balance."""
    i = src.index(opener)
    depth = 0
    for k in range(i, len(src)):
        c = src[k]
        if c in '({[':
            depth += 1
        elif c in ')}]':
            depth -= 1
        elif c == ';' and depth == 0:
            return src[i:k + 1]
    raise SystemExit('no statement end lifting ' + opener)


print('the room told the meeting about the colleague it left out')

CHAT_SRC = strip_comments(CHAT.read_text(encoding='utf-8'))
CAST_SRC = strip_comments(CAST.read_text(encoding='utf-8'))
FLOOR_SRC = strip_comments(FLOOR.read_text(encoding='utf-8'))
STORE_SRC = strip_comments(STORAGE.read_text(encoding='utf-8'))
RT_SRC = strip_comments(RUNTIME.read_text(encoding='utf-8'))

# ── The premise: this really is the one door. ───────────────────────────
check('chatToMessages still walks every bubble in the slice it is handed — '
      'there is no per-author filter upstream of it to rely on',
      re.search(r'for \(const m of src\) \{', RT_SRC) is not None)
check('...and the dispatch still hands it a raw tail of the whole chat, not '
      'a thread- or author-filtered one',
      re.search(r'chatRef\.current\.slice\(-6\)',
                strip_comments((ROOT / 'app.jsx').read_text(encoding='utf-8')))
      is not None)

# ── The fix, at the choke point. ────────────────────────────────────────
check('chatToMessages drops a bubble the office flagged as its own voice, '
      'before it can become a turn',
      re.search(r'if \(m && m\.officeVoice\) continue;', RT_SRC) is not None)

# ── Both routing notes carry the flag. ──────────────────────────────────
room_note = re.search(
    r"text: strayRoomNote, thread: activeThread, officeVoice: true", CHAT_SRC)
check("the room's stray note is filed as office voice — the sentence #350 "
      'promised was screen-only', room_note is not None)
unknown_note = re.search(
    r"unknown teammate[\s\S]{0,320}?thread: targetThread, officeVoice: true",
    CHAT_SRC)
check('...and so is the DIRECT thread\'s "(unknown teammate: @X)", the older '
      'twin #350 was modelled on', unknown_note is not None,
      'fixing one of two identical notes leaves the other leaking')

# ── The one that is SUPPOSED to reach the model keeps no flag. ──────────
ceo_stray = re.search(r"nobody here is called [\s\S]{0,400}?\};", CHAT_SRC)
check('the CEO\'s "(nobody here is called @X … Sending this to CafresoHQ '
      'instead.)" is NOT flagged — it is handed to the CEO on purpose, as '
      'the only thing explaining why a message addressed to somebody else '
      'arrived', ceo_stray is not None and 'officeVoice' not in ceo_stray.group(0),
      ceo_stray.group(0)[-120:] if ceo_stray else 'note not found')

# ── Run the real chain. ─────────────────────────────────────────────────
if not shutil.which('node'):
    print('  SKIP  node not on PATH — the envelope checks need it')
else:
    js = FLOOR_SRC.replace('export {', 'const _unused_floor = {') + '\n'
    js += brace_lift(RT_SRC, 'function chatToMessages(') + '\n'
    js += brace_lift(RT_SRC, 'function extractAllMentions(') + '\n'
    js += brace_lift(CAST_SRC, 'function roomStrayNote(') + '\n'
    js += stmt_lift(CAST_SRC, 'const nameList =') + '\n'
    js += stmt_lift(STORE_SRC, 'const capChatFair =') + '\n'
    js += stmt_lift(STORE_SRC, 'const persistableChat =') + '\n'
    js += stmt_lift(STORE_SRC, 'const chatOnLoad =') + '\n'
    js += r'''
/* Migration sync: Kip and Plato are seated, Dax is hired and idle one row
   away, and the boss names Dax. Exactly the turn #350 was written for. */
const ROSTER = ['Kip', 'Dax', 'Plato'].map((n, i) => ({ id: 'a' + i, name: n, role: 'Analyst' }));
const ROOM = ROSTER.filter(a => a.name !== 'Dax');
const TYPED = '@Kip @Dax in one word, is the migration risky?';

/* The room's own routing, lifted verbatim from ui/chat.jsx. */
const explicit = extractAllMentions(TYPED, ROSTER.map(a => a.name));
const recipients = ROOM.filter(a => explicit.targetNames.some(
  n => n.toLowerCase() === a.name.toLowerCase()));
const note = roomStrayNote(explicit.targetNames, recipients, ROSTER, 'meeting');

const THREAD = 'meeting:m1';
const chat = [
  { id: 'u1', from: 'user', name: 'You', text: TYPED, target: '@Kip', thread: THREAD },
  { id: 's1', from: 'system', name: 'HQ', text: note, thread: THREAD, officeVoice: true },
];
/* A stage direction: same author, no flag, and it must survive. */
const staged = [
  { id: 's2', from: 'system', name: 'HQ', text: '(dropped "briefing status check" on Vera\'s desk)', thread: 'direct' },
  { id: 's3', from: 'system', name: 'HQ', text: '✓ APPROVED — Publish site', thread: 'direct' },
];
/* And the CEO's deliberate stray note. */
const ceoStray = [
  { id: 's4', from: 'system', name: 'HQ', thread: 'direct',
    text: '(nobody here is called @Zed — the team is @Kip, @Dax, @Plato. Sending this to CafresoHQ instead.)' },
];
/* Interrupted, written to disk, reloaded: the flag has to come back or the
   leak reopens on the next page load. */
const reloaded = chatOnLoad(persistableChat(chat));

console.log(JSON.stringify({
  note,
  screen: reloaded.map(m => ({ from: m.from, name: m.name, text: m.text })),
  flagSurvives: reloaded.map(m => !!m.officeVoice),
  forAttendee: chatToMessages(chat, { selfName: 'Kip' }),
  forCeo: chatToMessages(chat),
  afterReload: chatToMessages(reloaded, { selfName: 'Kip' }),
  staged: chatToMessages(staged, { selfName: 'Kip' }),
  ceoStray: chatToMessages(ceoStray),
  recipients: recipients.map(a => a.name),
  body: explicit.body,
}, null, 2));
'''
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=90)
    if p.returncode != 0:
        check('the envelope harness runs on source lifted from the app',
              False, p.stderr.strip()[:600])
    else:
        R = json.loads(p.stdout)
        allc = lambda ms: '\n'.join(m['content'] for m in ms)

        # ── The screen: #350's whole point, unchanged. ──────────────────
        check('the room still says out loud that Dax was named and not asked '
              '— #350 is not undone',
              R['note'] == ("(@Dax isn't in this meeting — only @Kip was asked. "
                            'Invite them to the meeting, or ask in the DIRECT thread.)'),
              R['note'])
        check('...and it is still on screen, in the office\'s own voice, after '
              'a write and a reload',
              any(m['from'] == 'system' and m['name'] == 'HQ' and m['text'] == R['note']
                  for m in R['screen']), R['screen'])
        check('...and the room itself was still only handed the mention-free '
              'body, addressed to the one attendee who was asked',
              R['recipients'] == ['Kip']
              and R['body'] == 'in one word, is the migration risky?',
              [R['recipients'], R['body']])

        # ── The prompt: the defect. ────────────────────────────────────
        check('the attendee\'s brain is NOT told about the colleague who was '
              'left out — the boss\'s own words still carry the name, the '
              'office\'s note about it does not',
              R['note'] not in allc(R['forAttendee'])
              and "isn't in this meeting" not in allc(R['forAttendee']),
              R['forAttendee'])
        check('...and is not handed the boss\'s route-out as something a '
              'participant said',
              'Invite them to the meeting' not in allc(R['forAttendee']),
              R['forAttendee'])
        check('...so the envelope is the boss\'s question and nothing else',
              R['forAttendee'] == [{'role': 'user', 'content':
                                    '@Kip @Dax in one word, is the migration risky?'}],
              R['forAttendee'])
        check('the chief of staff\'s envelope is clean too — the leak was not '
              'scoped to attendees',
              R['note'] not in allc(R['forCeo'])
              and R['forCeo'] == R['forAttendee'], R['forCeo'])
        check('and it stays clean across a reload — the flag survives '
              'persistableChat, so the next page load does not reopen it',
              R['flagSurvives'] == [False, True]
              and R['note'] not in allc(R['afterReload'])
              and "isn't in this meeting" not in allc(R['afterReload']),
              [R['flagSurvives'], R['afterReload']])

        # ── Not a blanket drop. ───────────────────────────────────────
        check('a stage direction still reaches the model labelled "[HQ]:" — '
              'the fix did not turn into "drop everything from:system"',
              "[HQ]: (dropped \"briefing status check\" on Vera's desk)"
              in allc(R['staged'])
              and '[HQ]: ✓ APPROVED — Publish site' in allc(R['staged']),
              R['staged'])
        check('...and the CEO is still told why a message addressed to '
              'somebody else arrived',
              'nobody here is called @Zed' in allc(R['ceoStray']),
              R['ceoStray'])

print()
if FAILS:
    print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS))
    sys.exit(1)
print('all checks passed')
