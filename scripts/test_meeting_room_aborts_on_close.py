#!/usr/bin/env python3
"""Closing the office-floor Meeting Room mid-turn left the in-flight
agentStream/ceoStream calls running as an orphaned closure forever.

`MeetingRoom` (features.jsx) is only mounted while `meetingOpen` is true
(app.jsx renders `{meetingOpen && <MeetingRoom .../>}`), unlike
`StandupModal`, which is rendered unconditionally and only gated by an
`open` prop. So closing the meeting (X, Escape, backdrop — all handled
generically by Modal's onClose) actually unmounts MeetingRoom — but its
per-attendee turn loop (`moderate`'s `for` loop over placeholders, plus
the closing ceoStream synthesis call) is a plain async closure, not tied
to React lifecycle: it kept running after unmount, still calling
onUpdateAgent(busy -> idle) against the live agents state with no UI
left to show or stop it. Worse, this local `abortRef`'s AbortController
was never registered with app.jsx's `agentAbortersRef`, so the STOP ALL
button couldn't reach it either.

The exact same bug shape was already fixed for StandupModal (which
instead aborts on the open->false prop edge, since it never unmounts) —
see the comment right above its `useEF(() => { if (!open && ...) ...
}, [open]);` cleanup. MeetingRoom needed the unmount-shaped version of
the same fix.

Found by a background hunt agent sweeping previously-unswept areas
(Meetings/Rooms, Night Shift, approval/hire flow, search, Settings,
notifications, CEO 1:1, export/publish).

Fix: added a plain unmount cleanup effect right after MeetingRoom's
abortRef declaration that aborts any in-flight controller.

Run: python3 scripts/test_meeting_room_aborts_on_close.py
"""
import re
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
    print('MeetingRoom aborts its in-flight turn when the modal closes')

    src = FEATURES.read_text(encoding='utf-8')

    m = re.search(r"function MeetingRoom\(\{.*?\n\}\n", src, re.S)
    check('MeetingRoom is still present', m is not None)
    body = m.group(0) if m else ''

    check("MeetingRoom still keeps its own abortRef "
          "(the controller the unmount cleanup must abort)",
          "const abortRef = useRF(null);" in body)

    check("an unmount cleanup effect aborts any in-flight controller — "
          "MeetingRoom is conditionally mounted (app.jsx: "
          "`{meetingOpen && <MeetingRoom .../>}`), so a plain-unmount "
          "cleanup (empty deps, no `open` prop to key off) is the "
          "correct shape here, unlike StandupModal's open->false effect",
          re.search(
              r"useEF\(\(\)\s*=>\s*\(\)\s*=>\s*\{\s*if\s*\(abortRef\.current\)\s*"
              r"abortRef\.current\.abort\(\);\s*\},\s*\[\]\);",
              body
          ) is not None,
          "expected a `useEF(() => () => { if (abortRef.current) "
          "abortRef.current.abort(); }, []);` cleanup effect")

    # The cleanup effect must be registered before `moderate` is defined,
    # not buried after — a purely textual ordering check that the fix landed
    # where a reader would expect it (right after abortRef), not orphaned
    # elsewhere in the 150+ line function body.
    abort_ref_pos = body.find("const abortRef = useRF(null);")
    moderate_pos = body.find("const moderate = async () => {")
    cleanup_match = re.search(r"useEF\(\(\)\s*=>\s*\(\)\s*=>", body)
    if abort_ref_pos != -1 and moderate_pos != -1 and cleanup_match:
        check("the cleanup effect sits between the abortRef declaration "
              "and moderate()",
              abort_ref_pos < cleanup_match.start() < moderate_pos)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
