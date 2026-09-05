#!/usr/bin/env python3
""""🔑 Your session expired. Reopen HQ from ai.cafreso.com → Launch HQ to sign
back in" — app.jsx, on a tester's FIRST message, on their own machine.

Measured on a brand-new install (empty CAFRESOHQ_HQ_STATE_DIR, empty
localStorage, `python3 serve.py` on localhost): type hello into the composer,
hit Send, and the very first thing the app says to a person who has never seen
it is that a session they never had has ended, above a link that walks them out
of the product they just installed.

The mechanism is claude-client.jsx's `noteAuthFailure`, which fires
`hq:session-expired` off ANY 401 from the API origin. On a self-hosted office
most 401s are not HQ's own hq_session cookie at all — they are an upstream the
office merely PROXIES (the hermes gateway, a cloud provider) refusing for want
of ITS key. Reproduced directly:

    POST /hermes/v1/chat/completions → 401 (Server: aiohttp — the gateway's own)

So the banner is wrong twice over: about what happened (nothing expired; on
localhost there is no hq_session to expire), and about what to do next (§7 — the
only control offered is a link to a different product, which cannot sign in the
local gateway). The offline banner rendered eleven lines below it already learned
exactly this lesson and branches on `runsLocally`; this one did not.

Now: the same branch. A local reader is told what actually refused and gets
"Open Connections", which lands them on Settings → Connections — the page that
holds the sign-in. The managed reader keeps the sign-back-in link, which for
them is the right door.

Run: python3 scripts/test_a_first_run_on_your_own_machine_is_not_told_its_session_expired.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('first run on your own machine — a 401 is not a session that expired')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    src = SRC.read_text(encoding='utf-8')

    start = src.find('{sessionExpired && (')
    check('the session-expiry banner still exists', start >= 0)
    if start < 0:
        print('\nfirst run on your own machine: FAILED')
        return 1
    end = src.find('{backendDown &&', start)
    check('...and the offline banner still follows it (block bounds)', end > start)
    if end <= start:
        print('\nfirst run on your own machine: FAILED')
        return 1
    block = src[start:end]

    # ── the address we are actually calling decides the sentence ───────────
    check('the banner branches on where this office actually runs',
          'runsLocally' in block,
          'app.jsx: the session-expiry banner spoke one sentence to everyone. '
          "The office ten lines down already branches on runsLocally for the "
          'same reason — a self-hoster cannot be helped by ai.cafreso.com.')

    # ── §7: no false claim to a local reader ───────────────────────────────
    # Split at the branch so each half is judged on its own reader.
    # With no branch at all there is one arm and both readers get it, so an
    # unbranched banner must be judged as the LOCAL arm — otherwise the two
    # negative checks below pass on an empty string and the regression that
    # started this ticket reads green.
    _, sep, after = block.partition('runsLocally')
    arms = (after if sep else block).split('\n')
    local_arm, managed_arm, seen_colon = [], [], False
    for line in arms:
        if sep and line.lstrip().startswith(': <>'):
            seen_colon = True
        (managed_arm if seen_colon else local_arm).append(line)
    local_arm = '\n'.join(local_arm)
    managed_arm = '\n'.join(managed_arm)

    check('the local reader is not told a session expired',
          'session expired' not in local_arm.lower(),
          'app.jsx: on localhost there is no hq_session, so "your session '
          'expired" describes a thing that never existed')
    check('...and is told nothing expired',
          'nothing expired' in local_arm,
          'app.jsx: §7 — say what actually happened, not the managed story')
    check('...and is not sent to ai.cafreso.com',
          'ai.cafreso.com' not in local_arm,
          'app.jsx: §3.5 — self-hosting is a first-class path; that link '
          'cannot sign in a gateway running on the reader\'s own machine')

    # ── §7: the way forward has to be reachable from here ──────────────────
    check('the local reader is pointed at Settings → Connections',
          'Settings → Connections' in local_arm,
          'app.jsx: that is the page holding the sign-in this 401 is missing')
    check('...by a control that actually opens it',
          "openSettings('keys')" in block,
          'app.jsx: §7 — a banner whose only button reloads the page is a '
          'dead end when reloading changes nothing')
    check('...and the button says so rather than saying Reload',
          'Open Connections' in block,
          'app.jsx: "Reload" promises a fix it cannot deliver here')

    # ── the managed reader keeps the door that works for them ──────────────
    check('the managed reader still gets the sign-back-in link',
          'ai.cafreso.com/hq' in managed_arm and 'session expired' in managed_arm.lower(),
          'app.jsx: the fix must not cost the hosted boss their recovery path')

    print()
    if FAILS:
        print('first run on your own machine: %d FAILED' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('first run on your own machine: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
