#!/usr/bin/env python3
"""A cron question claimed by its own submitter must not be billed twice.

_gap_run/_news_run reserve one Brave query per SUBMITTED question and keep
that reservation — the submit is the payment. But when the same node later
claimed the job, _sw_process spent the query AGAIN through _sw_brave's default
kind='human': the month's `used` counted 2 for 1 real query, /gap/status
byKind billed machine questions as people, and the crons' actual spend rode
the un-floored human lane — bypassing the 35%/40% reserves the priority
budget exists to enforce, all the way into the human-only headroom.

These tests run the REAL _sw_process against a fake Brave HTTP layer and a
captured _sw_call, with the ledger files on a temp dir. No Docker, no network.

Run: python3 scripts/test_a_gap_question_claimed_at_home_is_not_billed_twice.py
"""
import io
import json
import os
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'search_worker_service'))

FAILS = []


def check(name, cond):
    print('  %-5s %s' % ('ok' if cond else 'FAIL', name))
    if not cond:
        FAILS.append(name)


class _FakeResp(io.BytesIO):
    """Just enough of an HTTPResponse for `with urlopen(...) as r: r.read()`."""
    status = 200
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def main():
    # Keep the worker loop and crons from starting on import.
    os.environ.pop('SEARCH_WORKER', None)
    os.environ['BRAVE_MONTHLY_CAP'] = '1000'
    os.environ['BRAVE_API_KEY'] = 'test-key-never-used'
    tmp = tempfile.mkdtemp(prefix='gap-prepaid-')
    os.environ['CAFRESOHQ_HQ_STATE_DIR'] = tmp

    import worker as serve
    serve._operator_config = lambda: {}
    serve._hq_state_dir = pathlib.Path(tmp)

    # Fake Brave HTTP: every urlopen from _sw_brave returns one result row.
    row = {'title': 'A page', 'url': 'https://example.com/a', 'description': 'desc'}
    # Both verticals' shapes: web nests under .web.results, news is top-level.
    brave_body = json.dumps({'web': {'results': [row]}, 'results': [row]})

    def fake_urlopen(req, timeout=None):
        return _FakeResp(brave_body.encode('utf-8'))
    serve.urllib.request.urlopen = fake_urlopen

    # No LLM backend: sources-only answers, zero network.
    serve._sw_backend = lambda: None

    # Capture signed worker calls instead of sending them anywhere.
    calls = []

    def fake_sw_call(op, lines):
        calls.append((op, list(lines)))
        return 200, {'ok': True, 'libraryId': 'lib1'}
    serve._sw_call = fake_sw_call

    def reset(used, by):
        serve._night_save('brave-usage.json', {
            'month': serve._brave_month(), 'used': used, 'byKind': dict(by)})

    GQ = 'what anchors the library graph?'
    NQ = 'what happened at the summit this week?'
    HQ = 'what is the internet computer?'

    print('=== a gap question the cron prefunded is not metered again at claim ===')
    serve._night_save('gap-asked.json', [GQ])
    serve._night_save('news-asked.json', [NQ])
    reset(used=3, by={'gap': 2, 'news': 1})   # the submit-time charges
    calls[:] = []
    serve._sw_process({'id': 'j1', 'q': GQ}, deadline=time.monotonic() + 30)
    u = serve._brave_usage()
    check('used stays what the submit charged (3, not 4)', u.get('used') == 3)
    check('nothing lands in the human lane', not u.get('byKind', {}).get('human'))
    check('the gap lane keeps its submit-time count', u['byKind'].get('gap') == 2)
    check('the job still fulfilled', any(op == 'fulfill' for op, _ in calls))
    ful = next(l for op, l in calls if op == 'fulfill')
    check('engine chip still says ai-gap', 'ai-gap' in ' '.join(ful))

    print('=== a news-cron question is prepaid the same way ===')
    reset(used=3, by={'gap': 2, 'news': 1})
    calls[:] = []
    serve._sw_process({'id': 'j2', 'q': NQ, 'mode': 'news'}, deadline=time.monotonic() + 30)
    u = serve._brave_usage()
    check('news claim adds nothing to used', u.get('used') == 3)
    check('news claim bills no human query', not u.get('byKind', {}).get('human'))

    print('=== a real human question still meters the human lane ===')
    reset(used=3, by={'gap': 2, 'news': 1})
    calls[:] = []
    serve._sw_process({'id': 'j3', 'q': HQ}, deadline=time.monotonic() + 30)
    u = serve._brave_usage()
    check('human claim counts exactly one query', u.get('used') == 4)
    check('and attributes it to human', u['byKind'].get('human') == 1)

    print('=== prepaid work is not starved by the lane floor it already paid ===')
    # gap's 35% floor refuses NEW gap spends past used=650 — but this question
    # was paid for back when the month was healthy, so the claim must proceed.
    serve._night_save('gap-asked.json', [GQ])
    reset(used=700, by={'gap': 100, 'human': 600})
    calls[:] = []
    serve._sw_process({'id': 'j4', 'q': GQ}, deadline=time.monotonic() + 30)
    u = serve._brave_usage()
    check('a tight month does not fail a prefunded job',
          any(op == 'fulfill' for op, _ in calls) and
          not any(op == 'fail' for op, _ in calls))
    check('and it still adds nothing to used', u.get('used') == 700)

    print()
    if FAILS:
        print('FAILED: %d check(s): %s' % (len(FAILS), '; '.join(FAILS)))
        sys.exit(1)
    print('all checks passed')


if __name__ == '__main__':
    main()
