#!/usr/bin/env python3
"""Gap cron — the 10am ET schedule and the human-weighted proposal loop.

The schedule tests are the important ones. _night_scan rolls a daily job with
`nextRunAt += 86_400_000`, which holds UTC constant and therefore drifts an hour
against wall-clock time across a DST boundary. "10am every day" has to mean 10am
in November too, so these pin both DST transitions explicitly — that bug is
invisible for ~8 months of the year and then wrong every day.

Run: python3 scripts/test_gap_cron.py
"""
import os
import sys
import json
import pathlib
import tempfile
import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

FAILS = []


def check(name, cond):
    print('  %-5s %s' % ('ok' if cond else 'FAIL', name))
    if not cond:
        FAILS.append(name)


def main():
    os.environ.pop('SEARCH_WORKER', None)
    os.environ['GAP_CRON'] = '0'          # don't start the thread on import
    os.environ['BRAVE_MONTHLY_CAP'] = '1000'
    tmp = tempfile.mkdtemp(prefix='gap-cron-')
    os.environ['CAFRESOHQ_HQ_STATE_DIR'] = tmp

    import serve
    serve._hq_state_dir = pathlib.Path(tmp)
    from zoneinfo import ZoneInfo
    ET = ZoneInfo('America/New_York')

    def at(y, mo, d, h, mi=0):
        return int(datetime.datetime(y, mo, d, h, mi, tzinfo=ET).timestamp() * 1000)

    def et(ms):
        return datetime.datetime.fromtimestamp(ms / 1000.0, ET)

    print('=== the schedule always lands on 10:00 ET ===')
    nxt = et(serve._gap_next_run_ms(at(2026, 7, 15, 9, 0)))
    check('9am → same-day 10am', nxt.hour == 10 and nxt.day == 15)
    nxt = et(serve._gap_next_run_ms(at(2026, 7, 15, 10, 30)))
    check('after 10am → next day 10am', nxt.hour == 10 and nxt.day == 16)
    nxt = et(serve._gap_next_run_ms(at(2026, 7, 15, 10, 0)))
    check('exactly 10:00 → next day (never double-fires)', nxt.day == 16)
    nxt = et(serve._gap_next_run_ms(at(2026, 12, 31, 23, 0)))
    check('crosses a year boundary', nxt.year == 2027 and nxt.month == 1 and nxt.hour == 10)

    print('=== DST — what the +86_400_000 roll gets wrong ===')
    # US DST 2026: starts Sun Mar 8, ends Sun Nov 1.
    before = serve._gap_next_run_ms(at(2026, 3, 7, 11, 0))    # → Mar 8, EDT begins
    check('spring forward: still 10:00 local', et(before).hour == 10)
    check('spring forward: the UTC instant SHIFTS (a fixed +24h roll would not)',
          (before - at(2026, 3, 7, 10, 0)) != 86_400_000)
    after = serve._gap_next_run_ms(at(2026, 10, 31, 11, 0))   # → Nov 1, EST returns
    check('fall back: still 10:00 local', et(after).hour == 10)
    check('fall back: the UTC instant shifts the other way',
          (after - at(2026, 10, 31, 10, 0)) != 86_400_000)
    # A whole ordinary day IS 24h — proves the above isn't just always-true.
    mid = serve._gap_next_run_ms(at(2026, 7, 15, 11, 0))
    check('an ordinary day is exactly 24h apart',
          (mid - at(2026, 7, 15, 10, 0)) == 86_400_000)

    print('=== human vs AI questions are told apart ===')
    serve._night_save('gap-asked.json', ['what is a canister?'])
    idx = [{'q': 'what is a canister?'}, {'q': 'how fast is ICP finality?'}, {'q': ''}]
    real_urlopen = serve.urllib.request.urlopen

    class _R:
        def __init__(s, b): s._b = b
        def read(s): return s._b
        def __enter__(s): return s
        def __exit__(s, *a): return False
    serve.urllib.request.urlopen = lambda *a, **k: _R(json.dumps(idx).encode())
    try:
        all_qs, human_qs = serve._gap_library()
    finally:
        serve.urllib.request.urlopen = real_urlopen
    check('all questions collected (blank dropped)', all_qs == ['what is a canister?',
                                                               'how fast is ICP finality?'])
    check('a previously AI-asked question is NOT counted as human demand',
          human_qs == ['how fast is ICP finality?'])

    print('=== budget is reserved before any work ===')
    serve._night_save('brave-usage.json',
                      {'month': serve._brave_month(), 'used': 995, 'byKind': {}})
    serve._gap_run()
    runs = serve._night_load('gap-runs.json', [])
    check('a tight month produces a logged no-op, not a crash',
          len(runs) == 1 and 'too tight' in runs[-1]['note'])
    check('nothing was submitted', runs[-1]['submitted'] == [])

    # 650 used → 350 left, gap reserve is 350 → it may not spend at all.
    serve._night_save('brave-usage.json',
                      {'month': serve._brave_month(), 'used': 650, 'byKind': {}})
    check('gap refuses exactly at its reserve floor', not serve._brave_spend('gap', 1))

    print('=== proposals are filtered ===')
    serve._night_save('brave-usage.json',
                      {'month': serve._brave_month(), 'used': 0, 'byKind': {}})
    real_backend, real_key = serve._sw_backend, serve._sw_hermes_key
    serve._sw_backend = lambda: None
    serve._sw_hermes_key = lambda: ''
    check('no reachable model → no questions, no crash',
          serve._gap_propose(['a'], ['b'], 10, None) == [])

    print('=== end to end: propose → dedup → submit → provenance ===')
    serve._night_save('gap-asked.json', [])
    serve._night_save('gap-runs.json', [])
    serve._night_save('brave-usage.json',
                      {'month': serve._brave_month(), 'used': 0, 'byKind': {}})
    library = ['how fast is ICP finality?']
    prompts = []

    class _B:
        url = 'http://fake/v1/chat/completions'
        headers = {}
        model = 'fake-model'
        provider = 'fake'
    serve._sw_backend = lambda: _B()
    # The model proposes 4: one duplicate of the library, one over the 400-char
    # canister cap, two good.
    serve._sw_stream_or_block = lambda url, headers, payload, deadline: (
        prompts.append(payload['messages'][0]['content']),
        (json.dumps({'questions': [
            'How fast is ICP finality?',          # dup (case-insensitive)
            'x' * 401,                            # over LIB_MAX_QUERY
            'What is a subnet on the Internet Computer?',
            'How does chain-key cryptography work?',
        ]}), 'fake-model', 10, False))[1]
    submitted = []
    serve._gap_submit = lambda q: (submitted.append(q), 'queued')[1]
    real_lib = serve._gap_library
    serve._gap_library = lambda: (list(library), list(library))
    try:
        serve._gap_run()
    finally:
        serve._gap_library = real_lib
        serve._sw_backend, serve._sw_hermes_key = real_backend, real_key

    check('only the 2 valid, non-duplicate questions were submitted',
          submitted == ['What is a subnet on the Internet Computer?',
                        'How does chain-key cryptography work?'])
    check('the duplicate was skipped case-insensitively',
          any('already covered' == s['why'] for s in
              serve._night_load('gap-runs.json', [])[-1]['skipped']))
    check('the over-cap question never reached submit',
          not any(len(q) > 400 for q in submitted))
    check('submitted questions are recorded for provenance',
          serve._night_load('gap-asked.json', []) == submitted)
    check('the prompt anchors on real human demand',
          'demand signal' in prompts[0] and 'how fast is ICP finality?' in prompts[0])
    # Reserve 10, submit 2 → the other 8 MUST come back. Without the refund a
    # mature library (where dedup drops most proposals) leaks ~240 queries a
    # month and the cron starves against its own reserve having done no work.
    check('unused reservation is refunded — ledger charges only what shipped',
          serve._brave_usage()['byKind'].get('gap') == 2)
    check('total used matches actual submits', serve._brave_usage()['used'] == 2)

    print('=== every early exit refunds too ===')
    serve._night_save('brave-usage.json',
                      {'month': serve._brave_month(), 'used': 0, 'byKind': {}})
    serve._gap_library = lambda: (None, None)
    try:
        serve._gap_run()
    finally:
        serve._gap_library = real_lib
    check('an unreachable library index refunds the whole batch',
          serve._brave_usage()['used'] == 0)

    serve._night_save('brave-usage.json',
                      {'month': serve._brave_month(), 'used': 0, 'byKind': {}})
    serve._gap_library = lambda: (['a'], ['a'])
    real_propose = serve._gap_propose
    serve._gap_propose = lambda *a, **k: []
    try:
        serve._gap_run()
    finally:
        serve._gap_library, serve._gap_propose = real_lib, real_propose
    check('a day with no proposals refunds the whole batch',
          serve._brave_usage()['used'] == 0)

    print('=== the worker marks those entries as AI-asked ===')
    check('a gap question fulfills as ai-gap',
          'What is a subnet on the Internet Computer?' in set(serve._gap_asked()))
    check('a human question is NOT marked',
          'how fast is ICP finality?' not in set(serve._gap_asked()))

    print('')
    if FAILS:
        print('gap cron: %d FAILED — %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('gap cron: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
