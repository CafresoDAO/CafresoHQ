#!/usr/bin/env python3
"""MeetingRoom kept showing a coworker's OLD name, color and role — and ran
their turn against their OLD brain/tools — for as long as the meeting stayed
open, even after Settings had saved a fresh record for that same id.

app.jsx seeds the room exactly once, at `onOpenMeeting`:

    setMeetingParticipants(agents.filter(a => ids.includes(a.id)));

and hands that captured array straight to the modal:

    <MeetingRoom participants={meetingParticipants} agents={agents} .../>

`features.jsx`'s `MeetingRoom` then rendered every seat card, built every
streaming placeholder, and passed the whole roster to `HQ.ceoStream` straight
off `participants` — the array captured the moment the boss clicked "Start
Meeting". `onUpdateAgent` is immutable (`{ ...a, ...patch }`), so a Settings
edit made while the room stayed open — rename, recolor, switch brain, tick a
tool — lands in `agents` as a brand-new object for that id and never reaches
`participants`. Concretely: seat two coworkers, open Settings -> Roster in
another view, rename one and switch their brain, save — the still-open
Meeting Room keeps the old name on the seat card, and the next turn that
coworker takes still streams against the pre-edit brain/tools, because
`HQ.agentStream`/`HQ.ceoStream` were handed the stale `agentRef` snapshot.

`app.jsx`'s own `FurnishModal` already re-looks its subject up in the live
roster on every render instead of trusting a captured object:

    agents.find(x => x.id === furnishFor.id) || furnishFor

This test extracts the actual `liveParticipants` line `features.jsx` computes
at the top of `MeetingRoom` (not a hand-copied duplicate) and genuinely
executes it under Node against a stale `participants` array (one attendee
edited since the room opened, one dismissed from the roster entirely since)
plus a live `agents` array, confirming the resolved seats carry the freshly
saved record — and that the removed attendee's last-known seat survives via
the `|| p` fallback instead of vanishing mid-meeting.

Run: python3 scripts/test_meeting_room_seats_read_live_agents_not_a_frozen_snapshot.py
(skips the live-execution check if `node` isn't on PATH — the source-shape
checks still run everywhere)
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURES = ROOT / 'features.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("MeetingRoom's seats/turns read the live `agents` roster, not the frozen `participants` snapshot")

    src = FEATURES.read_text(encoding='utf-8')

    m = re.search(
        r"const liveParticipants = (participants\.map\(p => agents\.find\(a => a\.id === p\.id\) \|\| p\)|participants);",
        src)
    check('found the `liveParticipants` line in MeetingRoom', m is not None)
    line_expr = m.group(1) if m else ''

    check('`liveParticipants` re-looks each attendee up in the live '
          '`agents` roster (`agents.find(a => a.id === p.id) || p`), not '
          'the bare frozen `participants` prop — this is the actual '
          'regression',
          line_expr == 'participants.map(p => agents.find(a => a.id === p.id) || p)',
          f'reads `{line_expr}` instead')

    # Every render/turn site should have been switched over to the live
    # array; none of them should still read the raw `participants` prop
    # directly (aside from the one line that derives liveParticipants,
    # and the destructured parameter itself, and the stray prose comment
    # a few hundred lines down that just talks ABOUT participants).
    for needle, label in [
        ('const available = agents.filter(a => !liveParticipants.some(p => p.id === a.id));', 'the "+ Seat" availability filter'),
        ('const placeholders = liveParticipants.map(a => ({', 'the streaming placeholders / agentRef used for the turn'),
        ('{ agents: liveParticipants, signal: controller.signal }', "the roster handed to HQ.ceoStream"),
        ('subtitle={`${liveParticipants.length + 1} in the room', 'the "N in the room" subtitle'),
        ('{liveParticipants.map(p => (', 'the seat card render'),
    ]:
        check(f'{label} reads `liveParticipants`', needle in src, needle)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted '
          'line below)', has_node, 'skipping the live-execution check')

    if has_node and m:
        js = f"""
        // Captured at "Start Meeting" — Vera and Milo as they stood the
        // moment the boss seated them. This is what `participants` state
        // is still holding, unreassigned, for as long as the room stays
        // open.
        const participants = [
          {{ id: 'a_vera', name: 'Vera', role: 'Research', color: 'blue',
             model: 'anthropic:claude-3-haiku', tools: ['web'] }},
          {{ id: 'a_milo', name: 'Milo', role: 'Ops', color: 'green',
             model: 'anthropic:claude-3-haiku', tools: ['web'] }},
        ];
        // Live roster by the time the room re-renders: the boss opened
        // Settings -> Roster mid-meeting, renamed Vera, recolored her,
        // switched her brain and granted her the vault tool — a NEW
        // object for the same id, per onUpdateAgent's `{{ ...a, ...patch }}`
        // — and dismissed Milo from the roster entirely.
        const agents = [
          {{ id: 'a_vera', name: 'Vera Ashworth', role: 'Research',
             color: 'crimson', model: 'anthropic:claude-3-5-sonnet',
             tools: ['web', 'vault'] }},
        ];
        const liveParticipants = {line_expr};
        console.log(JSON.stringify(liveParticipants));
        """
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the extracted line ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-500:])
        if r.returncode == 0:
            resolved = json.loads(r.stdout.strip().splitlines()[-1])
            check('two seats resolved (the dismissed attendee still gets '
                  'a seat via the `|| p` fallback, not dropped)',
                  len(resolved) == 2, resolved)
            vera = next((p for p in resolved if p['id'] == 'a_vera'), {})
            milo = next((p for p in resolved if p['id'] == 'a_milo'), {})
            check('Vera\'s seat carries the FRESHLY SAVED name, not the '
                  'one from the moment the meeting was seated',
                  vera.get('name') == 'Vera Ashworth', vera.get('name'))
            check("...the freshly saved color", vera.get('color') == 'crimson', vera.get('color'))
            check("...the freshly saved brain", vera.get('model') == 'anthropic:claude-3-5-sonnet', vera.get('model'))
            check("...the freshly saved tools (now includes vault)",
                  vera.get('tools') == ['web', 'vault'], vera.get('tools'))
            check("Milo, dismissed from the roster since, keeps his "
                  "last-known seat instead of vanishing mid-meeting",
                  milo.get('name') == 'Milo', milo)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
