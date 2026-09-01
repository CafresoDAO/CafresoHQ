#!/usr/bin/env python3
"""Settings -> Appearance -> "Sound FX · pixel blips on action" persisted a
real boolean and rendered a real-looking pixel switch (identical in markup
to the working Scanlines and Night mode toggles right next to it) — but no
audio API call existed anywhere in the codebase. Toggling it flipped its
own boolean and nothing else: no `new Audio(...)`, no `.play()`, no
`AudioContext`, nothing downstream ever read `sound` except the switch
itself. A convincing but fully inert control. Found by a background hunt
agent scanning Settings/Office/onboarding (this session's next-least-
scrutinized areas), confirmed by grepping the whole repo for any audio API
usage and finding none outside the switch's own onClick.

The fix makes it real rather than removing it, since "pixel blips on
action" is a small, well-scoped, completable feature — not a fake control
in search of a home. Every toast in the app already funnels through one
function, `ToastProvider`'s `push()` in ui/feedback.jsx (dozens of call
sites across the whole app, all going through `window.cafresohqToast.*`),
so that's the one choke point that can make every existing toast call site
blip for free, with none of them needing to change. `playToastBlip(kind)`
reads the `sound` setting fresh from localStorage each call (the setting
lives in app.jsx's top-level `useStored`, and ui/feedback.jsx has no
parent/child relationship to that state — it's a cross-cutting preference,
read the same way the persisted key itself is written) and, if enabled,
plays a short synthesized WebAudio tone whose frequency/timbre varies by
toast kind — no audio assets needed, and no network fetch either.

Verified live in the browser: instrumented AudioContext.prototype to log
every oscillator start, flipped the real Settings toggle on, and fired
real toasts through the running app. Confirmed: a success toast played
880Hz sine, an error toast played 180Hz square, and with the toggle off
neither fired anything. Also confirmed the real Settings switch persists
to the exact localStorage key playToastBlip reads.

Run: python3 scripts/test_sound_fx_toggle_actually_makes_sound.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEEDBACK = ROOT / 'ui' / 'feedback.jsx'
APP = ROOT / 'app.jsx'
SETTINGS = ROOT / 'modals' / 'settings.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('Settings\' Sound FX toggle actually makes sound')

    feedback = FEEDBACK.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')
    settings = SETTINGS.read_text(encoding='utf-8')

    check('playToastBlip reads the persisted sound setting from the exact '
          "key useStored writes (cafresohq_hq_v1:sound) — the two sides "
          "of this fix live in different files with no shared import, so "
          "this is the one thing that actually binds them",
          "localStorage.getItem('cafresohq_hq_v1:sound')" in feedback,
          'ui/feedback.jsx: localStorage key changed or removed')
    check('...and treats anything other than a real JSON `true` as off '
          '(covers null/absent, "false", and a corrupted value alike)',
          "JSON.parse(raw) !== true) return;" in feedback,
          'ui/feedback.jsx: sound-enabled check shape changed')

    check('at least two distinct tones are defined, so success and error '
          'are distinguishable by ear the same way they already are by '
          'icon and color',
          re.search(r"success:\s*\{\s*freq:\s*(\d+)", feedback) is not None
          and re.search(r"error:\s*\{\s*freq:\s*(\d+)", feedback) is not None
          and re.search(r"success:\s*\{\s*freq:\s*(\d+)", feedback).group(1)
              != re.search(r"error:\s*\{\s*freq:\s*(\d+)", feedback).group(1),
          feedback)

    # The actual wiring: a toast that is genuinely shown must blip. There
    # are exactly two places a toast transitions to shown — the immediate
    # push() when there's room in the visible stack, and the queue-drain
    # inside dismiss() when a slot frees up. Missing either one means some
    # toasts silently never blip even with the setting on.
    check('push() blips the toast it just added to the visible stack',
          re.search(r"scheduleAutoDismiss\(finalToast\);\s*playToastBlip\(finalToast\.kind\);",
                    feedback) is not None,
          'ui/feedback.jsx: push() no longer blips on immediate show')
    check('dismiss()\'s queue-drain also blips the toast it just surfaced '
          '— otherwise a toast fired while 3 are already visible (the max) '
          'would blip only when THIS bug is fixed for both paths, not one',
          re.search(r"scheduleAutoDismiss\(queued\);\s*playToastBlip\(queued\.kind\);",
                    feedback) is not None,
          'ui/feedback.jsx: dismiss() queue-drain no longer blips')

    # Pin the upstream pieces this all depends on staying in place.
    check("app.jsx still persists `sound` via useStored under the exact "
          "key ('sound', namespaced by k())",
          "useStored(k('sound')" in app,
          "app.jsx: sound state no longer backed by useStored(k('sound'))")
    check('Settings\' Appearance tab still renders the switch bound to '
          'sound/setSound (the boss-facing control this whole fix is for)',
          "sound?'on':''" in settings and 'setSound(!sound)' in settings,
          'modals/settings.jsx: Sound FX switch markup changed')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
