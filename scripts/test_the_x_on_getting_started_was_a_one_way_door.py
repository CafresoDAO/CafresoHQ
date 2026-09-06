#!/usr/bin/env python3
"""The ✕ on the Getting Started checklist was permanent, and took two surfaces.

`## 412.` Driven on a genuinely empty office (own server, own port, own HOME).

`GettingStarted` renders two 14px grey glyphs side by side in its header,
`padding: 2` each, no gap between them: "–" collapses the card and "✕"
dismisses it. Only one of those is reversible.

  - `setGsDismissed(true)` was the ONLY writer of `ks('gettingStartedDone')`
    in the entire repo. Nothing set it back.
  - It is `useStored`, so the click outlived the tab, the session and the
    server.
  - The checklist is the only surface in the office that lists the six things
    a first run consists of.
  - `coachMark` opens with `if (gsDismissed) return null`, so the same click
    ALSO silenced every just-in-time nudge that was supposed to replace the
    checklist — the two onboarding surfaces a first-time boss has, gone
    together, from one unlabelled glyph.
  - The palette's only recovery command, "Replay onboarding tour", recovers
    neither: it sets `tourOpen`, and the checklist's render guard is
    `!gsDismissed && !tourOpen`, so the tour is the surface that hides the
    checklist hardest.

The fix is a door back, not a confirm dialog: `cafresohq:showGettingStarted`,
wired the same way `cafresohq:replayTour` already is, plus a palette entry and
a ✕ tooltip that says the door exists.

The checks below derive what they assert from the source — the event name is
read out of app.jsx's listener and then looked for in the palette, and the
render guard's own identifiers are what the restore handler is checked
against — so renaming either end fails here rather than drifting silently.
Every check returns a bool; none of them index into a string that may be
absent, because a check that raises instead of failing reports nothing about
the checks after it.

Run: python3 scripts/test_the_x_on_getting_started_was_a_one_way_door.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
CMDS = ROOT / 'app' / 'commands.jsx'
ONB = ROOT / 'ui' / 'onboarding.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


app = APP.read_text()
cmds = CMDS.read_text()
onb = ONB.read_text()

print('\n── the premises: one click, two surfaces, no way back ──')

# The checklist's ✕ writes the flag true.
check('the checklist ✕ sets gsDismissed true',
      re.search(r'onDismiss=\{\s*\(\)\s*=>\s*setGsDismissed\(true\)', app) is not None,
      'app.jsx no longer passes setGsDismissed(true) as onDismiss')

# ...and the flag is persisted, so the click outlives the tab.
check('gsDismissed is persisted (useStored), so the click is durable',
      re.search(r'const\s*\[\s*gsDismissed\s*,\s*setGsDismissed\s*\]\s*=\s*useStored\(', app)
      is not None)

# ...and it gates the coach marks as well as the card.
check('the same flag also gates the just-in-time coach marks',
      re.search(r'if\s*\(\s*gsDismissed\s*\)\s*return null', app) is not None,
      'coachMark no longer short-circuits on gsDismissed — re-read this test')

print('\n── the fix: a door back, reachable from the palette ──')

# There is now a writer of the OTHER value. This is the whole bug in one line.
check('something in the app sets gsDismissed back to false',
      re.search(r'setGsDismissed\(\s*false\s*\)', app) is not None,
      'gsDismissed is a one-way door again')

# The restore is event-driven, so a surface with no props path can open it.
listener = re.search(
    r"addEventListener\(\s*'(cafresohq:[A-Za-z]+)'\s*,\s*(\w+)\s*\)", app)
restore_events = re.findall(
    r"const\s+(\w+)\s*=\s*\(\)\s*=>\s*\{[^}]*setGsDismissed\(\s*false\s*\)[^}]*\};?"
    r"\s*window\.addEventListener\(\s*'(cafresohq:[A-Za-z]+)'",
    app)
check('the restore is wired to a window event (like replayTour)',
      len(restore_events) == 1, restore_events)
EVENT = restore_events[0][1] if len(restore_events) == 1 else ''

# ...and the palette dispatches THAT event. Name is derived, never pinned.
check('the command palette dispatches the same event app.jsx listens for',
      bool(EVENT) and ("'" + EVENT + "'") in cmds,
      'palette does not dispatch ' + (EVENT or '<no listener found>'))

# ...from a real, listed Help command.
help_cmd = re.search(
    r"\{\s*id:\s*'([\w.]+)'\s*,\s*label:\s*'([^']+)'\s*,\s*section:\s*'Help'[^}]*?"
    + re.escape(EVENT or '\0') + r"'", cmds, re.S) if EVENT else None
check('it is a listed Help command with a label a person can search for',
      help_cmd is not None and len(help_cmd.group(2)) > 4,
      help_cmd.group(2) if help_cmd else 'no Help command dispatches ' + (EVENT or '?'))

print('\n── the restore has to actually put the card on screen ──')
# Derive the render guard's own negated identifiers, then require the restore
# handler to clear every one of them. Today that is `!gsDismissed && !tourOpen`
# — a restore that only cleared gsDismissed would be a dead command whenever
# the boss ran it from inside the replayed tour.
guard = re.search(r'\{\s*((?:!\w+\s*&&\s*)+)\(?\s*<GettingStarted', app)
gated_on = re.findall(r'!(\w+)', guard.group(1)) if guard else []
check('the <GettingStarted> render guard is readable', len(gated_on) >= 2, guard)
handler = re.search(
    r"const\s+\w+\s*=\s*\(\)\s*=>\s*\{([^}]*setGsDismissed\(\s*false\s*\)[^}]*)\}", app)
body = handler.group(1) if handler else ''
for flag in gated_on:
    setter = 'set' + flag[0].upper() + flag[1:]
    check('the restore clears `' + flag + '` — the guard hides the card while it is true',
          re.search(re.escape(setter) + r'\(\s*false\s*\)', body) is not None,
          'handler body: ' + body.strip()[:160])

print('\n── and the ✕ says the door exists ──')
# `[^}]*?` between them: the button also carries `className: 'gs-dismiss'`
# (the hook the layout harnesses click), and prop order is not the contract.
x_btn = re.search(r"onClick:\s*onDismiss\s*,[^}]*?title:\s*'([^']*)'", onb)
title = x_btn.group(1) if x_btn else ''
check('the ✕ tooltip is more than the bare word "Dismiss"',
      title.strip().lower() not in ('', 'dismiss'), repr(title))
check('the ✕ tooltip names the palette as the way back',
      'palette' in title.lower(), repr(title))
# ...and it still reads as a dismiss, not as something else.
check('the ✕ tooltip still says what the button does',
      'dismiss' in title.lower(), repr(title))

print('\n── general: no palette command dispatches into the void ──')
# The class this bug belongs to: a Help command whose event nobody listens for
# looks like a way out and is not one. Every `cafresohq:` event the palette
# fires must have a listener somewhere in the app's own sources.
sources = '\n'.join(
    p.read_text() for p in [APP, ONB]
    + sorted((ROOT / 'app').glob('*.jsx'))
    + sorted((ROOT / 'ui').glob('*.jsx'))
    + sorted((ROOT / 'views').glob('*.jsx'))
    + sorted((ROOT / 'modals').glob('*.jsx')))
dispatched = sorted(set(re.findall(
    r"CustomEvent\(\s*'(cafresohq:[A-Za-z]+)'", cmds)))
check('the palette dispatches cafresohq events at all (sanity)',
      len(dispatched) >= 2, dispatched)
for ev in dispatched:
    check("something listens for '" + ev + "'",
          ("addEventListener('" + ev + "'") in sources
          or ('addEventListener("' + ev + '"') in sources,
          'dispatched by the palette, heard by nobody')

print()
if FAILS:
    print('FAILED (%d): %s' % (len(FAILS), '; '.join(FAILS)))
    sys.exit(1)
print('All checks passed.')
