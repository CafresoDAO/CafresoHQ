#!/usr/bin/env python3
"""Reset onboarding cleared some flags and quietly left others in place.

Reproduced by reading the source: `resetOnboarding()` (modals/settings.jsx —
at the time defined twice, once per settings tab that offered the button;
the second copy died with the never-mounted SystemTab) sweeps
localStorage for keys matching /tourseen|gettingstarted|gsdismissed/i and
deletes every match, then tells the user "onboarding reset" with a count.

The app actually persists FOUR onboarding-gating flags, each via
`useStored(ks('Name'))` in app.jsx:

    tourSeen              (~line 499)
    gettingStartedDone    (~line 565, read into the variable `gsDismissed`)
    firstDeliverySeen     (~line 602)
    coachSeen             (~line 843)

`tourseen` matches tourSeen. `gettingstarted` matches gettingStartedDone.
`gsdismissed` matches nothing at all — no stored key has ever been named
that; it is a stale echo of the `gsDismissed` *variable* name, not the key
it's actually stored under. `coachSeen` and `firstDeliverySeen` were not in
the pattern at all. A user who clicks "Replay the new-user guide" keeps
their contextual coach marks suppressed and never sees the first-delivery
beat again on reload — while the button's own success toast says every
flag was cleared.

Run: python3 scripts/test_reset_onboarding_clears_every_flag_it_claims_to.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
SETTINGS = (ROOT / 'modals/settings.jsx').read_text(encoding='utf-8')
FAILS = []

KNOWN_ONBOARDING_KEYS = ('tourSeen', 'gettingStartedDone', 'firstDeliverySeen', 'coachSeen')


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift_from(src, start_idx, opener='{'):
    """Body by brace matching, starting the scan for `opener` at start_idx."""
    i = src.index(opener, start_idx)
    depth = 0
    for k in range(i, len(src)):
        c = src[k]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return src[start_idx:k + 1]
    raise AssertionError('unbalanced braces lifting from %d' % start_idx)


def main():
    print('reset onboarding clears every flag it claims to')

    # ── 1. the 4 flags, straight from their own source of truth in app.jsx ──
    # Pulled by pattern rather than hardcoded, so this test tracks the real
    # flag list even if one gets renamed — and fails loudly (not silently
    # passing on a stale list) if the count of matches ever changes.
    stored = re.findall(r"useStored\(ks\('(\w+)'\)", APP)
    onboarding_keys = [k for k in stored if k in KNOWN_ONBOARDING_KEYS]
    check('app.jsx still persists exactly the 4 known onboarding flags',
          sorted(onboarding_keys) == sorted(KNOWN_ONBOARDING_KEYS),
          onboarding_keys)

    # ── 2. every resetOnboarding copy must clear every one of them ──────────
    # There used to be two copies — one per settings tab offering the button.
    # The second lived in `SystemTab`, which turned out to be dead code
    # (defined, never mounted) and was deleted when its one real feature was
    # rescued into AccountTab; one copy remains, one button references it.
    starts = [m.start() for m in
              re.finditer(r'const resetOnboarding = async \(\) => ', SETTINGS)]
    check('found the one live resetOnboarding copy', len(starts) == 1, starts)
    check('exactly one button references it',
          SETTINGS.count('onClick={resetOnboarding}') == 1,
          SETTINGS.count('onClick={resetOnboarding}'))

    for i, s in enumerate(starts):
        body = lift_from(SETTINGS, s)
        m = re.search(r"/([^/]+)/i\.test\(k\)", body)
        check('copy #%d has a kill-regex against localStorage keys' % (i + 1),
              m is not None)
        pattern = m.group(1) if m else ''
        for key in KNOWN_ONBOARDING_KEYS:
            hit = bool(pattern) and re.search(pattern, key, re.I) is not None
            check('copy #%d\'s regex clears %s' % (i + 1, key), hit,
                  '— reset would leave this flag in place while telling the '
                  'user it reset onboarding')

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
