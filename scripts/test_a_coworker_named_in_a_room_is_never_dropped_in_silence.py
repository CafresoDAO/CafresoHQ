#!/usr/bin/env python3
"""The boss @-mentioned two colleagues in a room and only one was asked.

A meeting room's empty state says it in the office's own words: "Type below to
send to all attendees, or @-mention specific people." So the boss does. The
recipient list is `activeRoom.participants.filter(…mentioned…)` — every name
that survives the filter is dispatched, and every name that does not is
dropped with nothing said about it anywhere.

Measured 2026-09-05 against a real `python3 serve.py` and three hired
coworkers on a real local brain (ollama:llama3.1). Meeting "Migration sync",
attendees Kip and Plato; Dax hired, idle, at his desk. The boss typed

    @Kip @Dax in one word, is the migration risky?

and the room's whole record of that turn was two entries:

    {"from": "user",  "name": "You", "target": "@Kip",
     "text": "@Kip @Dax in one word, is the migration risky?"}
    {"from": "agent", "name": "Kip · Deep Research", "text": "KIP The migration
     is not inherently risky, …"}

Dax — a real colleague, addressed by name, one desk away — was never asked and
never mentioned again. The DIRECT thread had already learned this lesson
twice: it prints "(unknown teammate: @X)" when some other mention matched, and
a stray note naming the whole team when none did. The room, the surface whose
entire reason to exist is more than one agent in it, had neither.

The fix is `roomStrayNote` in app/cast.jsx — the same shape those two use,
beside handoffHint where the office's other routing sentences live — plus
parsing the mention against the WHOLE team rather than the attendee list, so a
coworker whose name has a space in it is reported by their whole name.

Run: python3 scripts/test_a_coworker_named_in_a_room_is_never_dropped_in_silence.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAST = ROOT / 'app' / 'cast.jsx'
CHAT = ROOT / 'ui' / 'chat.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('a coworker named in a room is never dropped in silence')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    cast = CAST.read_text(encoding='utf-8')
    chat = CHAT.read_text(encoding='utf-8')

    # The REAL functions run here — lifted, not re-typed. cast.jsx is
    # import-free on purpose so this works (see its header).
    names = re.search(r'const nameList = \(names\) => \([\s\S]*?\n\);', cast)
    stray = re.search(
        r'function roomStrayNote\(targetNames, recipients, roster, kind\) \{'
        r'[\s\S]*?\n\}', cast)
    check('the room note exists as one liftable helper', bool(stray and names),
          'app/cast.jsx: roomStrayNote, beside handoffHint')
    if not (stray and names):
        print()
        print('a dropped coworker: FAILED — could not lift the shipped source')
        return 1

    R = run("""
%s
%s
const A = (n) => ({ id: 'a_' + n.toLowerCase(), name: n, role: 'r' });
const KIP = A('Kip'), PLATO = A('Plato'), DAX = A('Dax'), LOCAL = A('Local Brain');
const TEAM = [KIP, PLATO, DAX, LOCAL];
const R = {};
// The wreck, verbatim: meeting of Kip+Plato, "@Kip @Dax …", Dax hired.
R.measured = roomStrayNote(['Kip', 'Dax'], [KIP], TEAM, 'meeting');
// Nobody by that name at all.
R.unknown  = roomStrayNote(['Kip', 'Zed'], [KIP], TEAM, 'meeting');
// Both kinds at once, in a project room.
R.both     = roomStrayNote(['Kip', 'Dax', 'Zed'], [KIP], TEAM, 'project');
// A coworker whose name has a space in it, reported whole.
R.spaced   = roomStrayNote(['Kip', 'Local Brain'], [KIP], TEAM, 'meeting');
// Two dropped colleagues read as a list, and the verb agrees.
R.twoOut   = roomStrayNote(['Kip', 'Dax', 'Local Brain'], [KIP], TEAM, 'meeting');
// Two asked — "were", not "was".
R.twoAsked = roomStrayNote(['Kip', 'Plato', 'Dax'], [KIP, PLATO], TEAM, 'meeting');
// Everybody named was asked: nothing to say, and the caller emits blindly.
R.clean    = roomStrayNote(['Kip', 'Plato'], [KIP, PLATO], TEAM, 'meeting');
// Case is how the boss typed it; matching is not.
R.cased    = roomStrayNote(['kip', 'DAX'], [KIP], TEAM, 'meeting');
// Junk in, no crash.
R.nulls    = roomStrayNote(null, null, null, null);
R.holey    = roomStrayNote(['Dax'], [null, KIP], [null, DAX], 'meeting');
console.log(JSON.stringify(R));
""" % (names.group(0), stray.group(0)))

    m = R['measured']
    check('the colleague who was left out is named',
          '@Dax' in m,
          f'{m!r} — the measured turn said nothing about Dax anywhere')
    check('...and the reason is the room, not their existence',
          "isn't in this meeting" in m,
          f'{m!r} — Dax is hired and idle; "unknown teammate" would be a lie')
    check('...and who DID get it is stated',
          'only @Kip was asked' in m,
          f'{m!r} — the omission is only legible beside the delivery')
    check('...and there is a way forward',
          'Invite them to the meeting' in m and 'DIRECT thread' in m,
          f'{m!r} — §7: every failure ends in a route out')
    check('a name nobody answers to is told apart from one who is busy elsewhere',
          'nobody here is called @Zed' in R['unknown']
          and "isn't in this" not in R['unknown'],
          f"{R['unknown']!r} — these need different routes: one can be "
          'invited, the other cannot')
    check('both kinds in one turn are both reported',
          '@Dax' in R['both'] and '@Zed' in R['both']
          and 'project room' in R['both'],
          f"{R['both']!r}")
    check('a coworker whose name has a space is reported by their whole name',
          '@Local Brain' in R['spaced'],
          f"{R['spaced']!r} — half a name points at nobody")
    check('two dropped colleagues read as a list',
          '@Dax and @Local Brain' in R['twoOut'] and "aren't in this" in R['twoOut'],
          f"{R['twoOut']!r}")
    check('the verb agrees with how many were asked',
          'only @Kip and @Plato were asked' in R['twoAsked'],
          f"{R['twoAsked']!r}")
    check('a turn where everyone named was asked says nothing at all',
          R['clean'] == '',
          f"{R['clean']!r} — the caller emits blindly, so silence has to be "
          'the empty string')
    check('matching is case-insensitive, echoing is not',
          R['cased'] == '' or '@DAX' in R['cased'],
          f"{R['cased']!r} — @kip must still count as Kip, and @DAX must be "
          'quoted back the way the boss typed it')
    check('...and @kip counted as Kip',
          "@kip isn't" not in R['cased'],
          f"{R['cased']!r}")
    check('junk arguments do not crash a send',
          R['nulls'] == '' and '@Dax' in R['holey'],
          f"{R['nulls']!r} / {R['holey']!r}")

    # ── the wiring, pinned ──────────────────────────────────────────────
    room = chat[chat.index('if (activeRoom && activeRoom.participants.length) {'):]
    room = room[:room.index('/* /brainstorm')]
    def at(needle):
        # -1 when absent, so an ordering pin fails as a check rather than a
        # traceback when the call it orders has gone missing.
        return room.find(needle)

    check('the room path emits the note',
          'roomStrayNote(explicit.targetNames, recipients, agents, activeRoom.kind)'
          in room,
          'ui/chat.jsx: the fan-out inside a room is the one that drops names')
    check('...after the boss\'s own line, so it points at the right turn',
          at('roomStrayNote(') > at("from: 'user', name: 'You'") >= 0,
          'ui/chat.jsx: a note above its own question points at the previous '
          'exchange — the placement #345 already had to fix once for the '
          'publish-door note')
    check('...and before anybody is dispatched',
          0 <= at('roomStrayNote(') < at('onDispatchToAgent('),
          'ui/chat.jsx: the boss must know who was left out while the room is '
          'still filling, not after')
    check('the mention is parsed against the whole team, not the attendees',
          'HQ.extractAllMentions(text, agents.map(a => a.name))' in room,
          'ui/chat.jsx: the roster argument decides only which names read as '
          'one token. Handed the attendees, "@Local Brain" in a room he is '
          'not in parses as "@Local" and the note names half a person')
    check('the room\'s membership is still what decides who is asked',
          'activeRoom.participants.filter(a => explicit.targetNames.some(' in room,
          'ui/chat.jsx: widening the PARSE must not widen the delivery — a '
          'name outside the room is reported, never dispatched to')
    check('the sentence has exactly one writer',
          cast.count('function roomStrayNote') == 1
          and cast.count('in this ${room}') == 1
          and 'only @' not in chat and 'were asked' not in chat,
          'app/cast.jsx: the office already grew two copies of the direct '
          "thread's stray note that drifted apart (see routeOut's note on "
          'the same split); this sentence is written in one place and the '
          'room path only calls it')

    print()
    if FAILS:
        print(f'a dropped coworker: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('a dropped coworker: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
