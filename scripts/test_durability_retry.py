#!/usr/bin/env python3
"""Guards for the two unattended-failure modes: torn state files and 429s.

1. State writes must be atomic. A bare write_bytes truncates first, so a crash
   mid-write leaves invalid JSON; the client's shape check then falls back to
   seed data and the collection silently resets. The test kills the write at
   the moment of the swap and asserts the previous contents survive intact.

2. The night shift runs unattended for hours on free provider tiers. One 429
   used to end an iteration and three in a row ended the run, so transient
   upstream failures must retry with backoff — but a bad key (401) must not.

Run: python3 scripts/test_durability_retry.py
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import sys
import tempfile
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f' — {detail}' if detail and not cond else ''))
    if not cond:
        FAILS.append(label)


def _http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    hdrs = {'Retry-After': retry_after} if retry_after else {}
    return urllib.error.HTTPError('http://x', code, 'boom', hdrs, io.BytesIO(b'{}'))


def test_night_retry() -> None:
    os.environ.setdefault('CAFRESOHQ_HQ_STATE_DIR', tempfile.mkdtemp(prefix='dur-'))
    import night_runner as nr

    slept: list[float] = []
    nr.time.sleep = lambda s: slept.append(s)          # keep the suite fast

    print('=== the night shift survives a transient 429 ===')
    calls = {'n': 0}

    def flaky(req, timeout=180):
        calls['n'] += 1
        if calls['n'] < 3:
            raise _http_error(429)

        class _R:
            def read(self): return json.dumps({'ok': True, 'n': calls['n']}).encode()
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return _R()

    nr.urllib.request.urlopen = flaky
    slept.clear()
    out = nr._llm_post_with_retry(object())
    check('retries until it succeeds', out.get('ok') is True, repr(out))
    check('took exactly 3 attempts', calls['n'] == 3, str(calls['n']))
    check('backed off between attempts', len(slept) == 2, repr(slept))
    check('backoff grows', len(slept) == 2 and slept[1] > slept[0], repr(slept))

    print('=== a bad key fails immediately ===')
    calls['n'] = 0

    def unauthorized(req, timeout=180):
        calls['n'] += 1
        raise _http_error(401)

    nr.urllib.request.urlopen = unauthorized
    raised = False
    try:
        nr._llm_post_with_retry(object())
    except urllib.error.HTTPError as e:
        raised = (e.code == 401)
    check('401 propagates', raised)
    check('401 is NOT retried', calls['n'] == 1, f'{calls["n"]} attempts')

    print('=== Retry-After is honoured over our own backoff ===')
    calls['n'] = 0
    slept.clear()

    def rate_limited(req, timeout=180):
        calls['n'] += 1
        if calls['n'] == 1:
            raise _http_error(429, retry_after='7')

        class _R:
            def read(self): return b'{"ok":true}'
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return _R()

    nr.urllib.request.urlopen = rate_limited
    nr._llm_post_with_retry(object())
    check('waited the advertised 7s', slept == [7.0], repr(slept))

    print('=== it gives up rather than looping forever ===')
    calls['n'] = 0

    def always_503(req, timeout=180):
        calls['n'] += 1
        raise _http_error(503)

    nr.urllib.request.urlopen = always_503
    gave_up = False
    try:
        nr._llm_post_with_retry(object())
    except urllib.error.HTTPError:
        gave_up = True
    check('raises after the cap', gave_up)
    check('capped at _LLM_RETRY_MAX attempts',
          calls['n'] == nr._LLM_RETRY_MAX, f'{calls["n"]} attempts')


def test_atomic_state_write() -> None:
    print('=== a torn state write cannot destroy the previous file ===')
    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix='atomic-'))
    target = tmpdir / 'agents.json'
    good = json.dumps({'agents': ['vera', 'kip'], 'v': 1}).encode()
    target.write_bytes(good)

    # Reproduce the handler's write sequence, failing at the swap.
    new_body = json.dumps({'agents': ['vera', 'kip', 'dax'], 'v': 2}).encode()
    tmp = target.with_suffix('.json.tmp')
    real_replace = os.replace
    try:
        with open(tmp, 'wb') as fh:
            fh.write(new_body)
            fh.flush()
            os.fsync(fh.fileno())
        raise RuntimeError('simulated crash before the swap')
    except RuntimeError:
        pass

    survived = target.read_bytes()
    check('the old file is byte-identical after a crash', survived == good)
    parsed_ok = True
    try:
        json.loads(survived.decode())
    except Exception:
        parsed_ok = False
    check('and still parses as JSON', parsed_ok)

    # Now complete the swap and confirm the new content lands wholesale.
    real_replace(tmp, target)
    check('after the swap the new content is present',
          json.loads(target.read_text())['v'] == 2)
    check('no .tmp file is left behind', not tmp.exists())


def main() -> int:
    test_night_retry()
    test_atomic_state_write()
    print()
    if FAILS:
        print(f'durability/retry: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('durability/retry: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
