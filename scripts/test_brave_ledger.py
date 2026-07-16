#!/usr/bin/env python3
"""Brave quota ledger — the reserve policy is the whole point, so pin it.

Brave allows 1000 queries/month. Three spenders compete for it and they are
deliberately NOT equal: a human waiting on an answer outranks user-requested
deep research, which outranks the 10am cron's machine-invented questions. That
ordering is enforced by a reserve floor per kind, and these tests pin the
boundaries — an off-by-one in the reserve arithmetic would silently let the
cron eat a month of human searches, which is the exact failure the policy exists
to prevent.

Run: python3 scripts/test_brave_ledger.py
"""
import os
import sys
import json
import pathlib
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

FAILS = []


def check(name, cond):
    print('  %-5s %s' % ('ok' if cond else 'FAIL', name))
    if not cond:
        FAILS.append(name)


def main():
    # Keep the worker loop and night scheduler from starting on import.
    os.environ.pop('SEARCH_WORKER', None)
    os.environ['BRAVE_MONTHLY_CAP'] = '1000'
    tmp = tempfile.mkdtemp(prefix='brave-ledger-')
    os.environ['CAFRESOHQ_HQ_STATE_DIR'] = tmp

    import serve

    # Belt and braces: the env var above is read at import time (serve.py:292),
    # but pin the module attribute too so this never writes to a real HQ state
    # dir if that resolution ever changes.
    serve._hq_state_dir = pathlib.Path(tmp)

    def reset(used=0, by=None):
        serve._night_save('brave-usage.json', {
            'month': serve._brave_month(), 'used': used, 'byKind': by or {}})

    print('=== ledger basics ===')
    reset()
    check('fresh month starts at 0', serve._brave_remaining() == 1000)
    check('human spend is counted', serve._brave_spend('human', 1) and
          serve._brave_usage()['used'] == 1)
    check('byKind tracks the spender', serve._brave_usage()['byKind'].get('human') == 1)
    check('remaining reflects the spend', serve._brave_remaining() == 999)

    print('=== month rollover ===')
    serve._night_save('brave-usage.json', {'month': '1999-01', 'used': 999, 'byKind': {'human': 999}})
    check('a stale month resets to 0 rather than blocking forever',
          serve._brave_remaining() == 1000)

    print('=== priority degradation (the reason this exists) ===')
    # gap reserves 35% → it must stop once only 350 remain (used > 650).
    reset(used=640)
    check('gap runs while the month is healthy', serve._brave_spend('gap', 1))
    reset(used=650)
    check('gap STOPS at its 35% reserve — machine questions yield first',
          not serve._brave_spend('gap', 1))
    reset(used=650)
    check('deep still runs where gap stopped', serve._brave_spend('deep', 1))
    reset(used=650)
    check('human still runs where gap stopped', serve._brave_spend('human', 1))

    # deep reserves 15% → stops once only 150 remain (used > 850).
    reset(used=840)
    check('deep runs above its reserve', serve._brave_spend('deep', 1))
    reset(used=850)
    check('deep STOPS at its 15% reserve', not serve._brave_spend('deep', 1))
    reset(used=850)
    check('human still runs where deep stopped', serve._brave_spend('human', 1))

    print('=== human gets the whole quota ===')
    reset(used=999)
    check('human spends the very last query', serve._brave_spend('human', 1))
    reset(used=1000)
    check('human stops at the hard cap', not serve._brave_spend('human', 1))
    check('a refused spend does NOT count', serve._brave_usage()['used'] == 1000)

    print('=== batch reserve (the cron asks for 10 at once) ===')
    reset(used=645)
    check('a 10-query gap batch is refused when only 5 fit under the reserve',
          not serve._brave_spend('gap', 10))
    reset(used=600)
    check('a 10-query gap batch is allowed with room', serve._brave_spend('gap', 10))
    check('batch counts all 10', serve._brave_usage()['used'] == 610)

    print('=== _sw_brave refuses without a network call when dry ===')
    reset(used=1000)
    os.environ['BRAVE_API_KEY'] = 'test-key-not-used'
    calls = []
    real_urlopen = serve.urllib.request.urlopen
    serve.urllib.request.urlopen = lambda *a, **k: calls.append(1)
    try:
        out = serve._sw_brave('anything', None, 'human')
    finally:
        serve.urllib.request.urlopen = real_urlopen
    check('_sw_brave returns None when the month is spent', out is None)
    check('_sw_brave made NO http call — quota is checked before the wire',
          len(calls) == 0)

    print('')
    if FAILS:
        print('brave ledger: %d FAILED — %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('brave ledger: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
