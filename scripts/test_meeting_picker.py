#!/usr/bin/env python3
"""The office-floor Meeting Room door needs a real attendee picker.

Found live while auditing the office floor for the northstar MVP pass (the
turn right after the Calendar-view check): `onOpenMeeting` (app.jsx) seated
the meeting room with `agents.slice(0, 2)` — no boss choice, and no way to
add anyone once the room was open (only an "✕ Excuse" per seat). The CEO
panel's mini-office door was worse: it called `setMeetingOpen(true)`
directly, reusing whatever `meetingParticipants` was left over from the last
time — including empty, on a fresh session, which seats a "meeting" of
nobody but CafresoHQ.

Fix: both doors now go through a `MeetingPicker` (features.jsx) that reuses
the exact `.meeting-attendee-grid` markup the standalone "NEW MEETING ROOM"
chat-thread modal (modals/collab.jsx) already uses, so seating a team reads
the same way everywhere in the app. It preselects the first two agents so a
boss who wants the old one-click behavior still gets it. `MeetingRoom`
itself gained a "+ Seat someone" tile (only shown when a hired coworker
isn't already in the room) that opens the same attendee tiles to add
someone mid-meeting via a new `onAdd` prop.

Static checks only, same constraint as test_report_gate_race.py: these are
JSX closures inside component functions in app.jsx/features.jsx, not
exported pure functions a node harness could import.

Run: python3 scripts/test_meeting_picker.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FEATURES = ROOT / 'features.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('meeting room door — attendee picker + mid-meeting add')
    if not APP.is_file() or not FEATURES.is_file():
        print(f'  FAIL  missing source file(s)')
        return 1
    app_src = APP.read_text(encoding='utf-8')
    feat_src = FEATURES.read_text(encoding='utf-8')

    # ── the office-floor door no longer hard-codes a default seating ──────
    check("onOpenMeeting no longer force-seats agents.slice(0, 2) itself",
          'const defaults = agents.slice(0, 2);' not in app_src,
          'app.jsx: the door must let the boss choose attendees, not force '
          'the first two hired coworkers into every meeting')
    check("onOpenMeeting opens the picker",
          bool(re.search(r'const onOpenMeeting = \(\) => setMeetingPickerOpen\(true\);', app_src)),
          "app.jsx: the door handler should hand off to MeetingPicker, not "
          "seat the room itself")
    check("onStartMeeting exists and builds participants from the picker's selection",
          bool(re.search(r'const onStartMeeting = \(ids\) => \{[\s\S]*?setMeetingParticipants\(agents\.filter\(a => ids\.includes\(a\.id\)\)\)', app_src)),
          'app.jsx: the picker\'s chosen ids must actually become the '
          'meeting\'s participants')

    # ── the CEO panel's mini-office door goes through the same handler ────
    check("the CEO panel's door reuses onOpenMeeting instead of a bare setMeetingOpen(true)",
          bool(re.search(r'<CEOPanel[\s\S]*?onOpenMeeting=\{onOpenMeeting\}', app_src)),
          'app.jsx: the old `onOpenMeeting={() => setMeetingOpen(true)}` '
          'reused whatever meetingParticipants was left over from the last '
          'meeting (including empty on a fresh session) instead of asking '
          'who should be seated')

    # ── MeetingPicker component ────────────────────────────────────────────
    picker = re.search(r'function MeetingPicker\([\s\S]*?\n\}', feat_src)
    check('MeetingPicker exists', bool(picker))
    picker_body = picker.group(0) if picker else ''
    check('MeetingPicker reuses the .meeting-attendee-grid pattern',
          'meeting-attendee-grid' in picker_body and 'meeting-attendee' in picker_body,
          'features.jsx: should look the same as the chat-thread meeting '
          'modal\'s attendee picker (modals/collab.jsx), not a new pattern')
    check('MeetingPicker preselects the first two agents (keeps the old one-click path)',
          bool(re.search(r'setSelectedIds\(agents\.slice\(0, 2\)\.map', picker_body)),
          'features.jsx: a boss who just wants the old default behavior '
          'should still be able to hit Start Meeting immediately')
    check('MeetingPicker requires at least one attendee before starting',
          'selectedIds.length >= 1' in picker_body,
          'features.jsx: an empty-room meeting should not be startable')

    # ── MeetingRoom's mid-meeting "+ Seat" tile ────────────────────────────
    room = re.search(r'function MeetingRoom\([\s\S]*?\n\}\n\n/\* -', feat_src)
    room_body = room.group(0) if room else feat_src[feat_src.find('function MeetingRoom('):]
    check('MeetingRoom accepts an onAdd prop',
          bool(re.search(r'function MeetingRoom\(\{[^}]*onAdd[^}]*\}\)', room_body)),
          'features.jsx: without this there is no way to wire in a seat-'
          'someone action from app.jsx')
    check('MeetingRoom computes the not-yet-seated agents',
          'available = agents.filter(a => !liveParticipants.some(p => p.id === a.id))' in room_body,
          'features.jsx: the add tile needs to know who is left to seat — '
          '#378 renamed the seated-roster read to liveParticipants (a live '
          're-lookup of the same ids), so this must match that name')
    check('MeetingRoom renders a "+ Seat someone" tile that calls onAdd',
          bool(re.search(r'seat-add[\s\S]*?onAdd\(a\.id\)', room_body)),
          "features.jsx: the tile must actually be wired to add the "
          "clicked coworker, not just decorative")

    # ── app.jsx renders MeetingPicker and wires onAdd into MeetingRoom ─────
    check('app.jsx renders <MeetingPicker .../>',
          bool(re.search(r'<MeetingPicker open=\{meetingPickerOpen\}', app_src)),
          'app.jsx: the picker component must actually be mounted for the '
          'door to do anything')
    check('app.jsx passes onAdd={onAddToMeeting} into <MeetingRoom/>',
          bool(re.search(r'<MeetingRoom[\s\S]{0,300}?onAdd=\{onAddToMeeting\}', app_src)),
          'app.jsx: without this the room\'s "+ Seat someone" tile has '
          'nothing to call')
    check('onAddToMeeting exists and is idempotent (no duplicate seats)',
          bool(re.search(r"const onAddToMeeting = \(id\) => setMeetingParticipants\(prev =>\s*\n\s*prev\.some\(p => p\.id === id\) \? prev :", app_src)),
          'app.jsx: clicking the same coworker in the add popover twice '
          'must not seat them twice')

    print()
    if FAILS:
        print(f'meeting room door: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('meeting room door: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
