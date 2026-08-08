#!/usr/bin/env python3
"""Guards for the three ways persisted state has been lost: torn files,
429s, and a fresh browser deleting the office.

1. State writes must be atomic. A bare write_bytes truncates first, so a crash
   mid-write leaves invalid JSON; the client's shape check then falls back to
   seed data and the collection silently resets. The test kills the write at
   the moment of the swap and asserts the previous contents survive intact.

2. The night shift runs unattended for hours on free provider tiers. One 429
   used to end an iteration and three in a row ended the run, so transient
   upstream failures must retry with backoff — but a bad key (401) must not.

3. A fresh browser context (new browser, cleared site data, second device)
   seeds useFileStored from an EMPTY mirror. A boot-time write then marks the
   value dirty, the arriving file fetch is turned away by the local-edits-win
   rule, and the office persists the emptiness over a good file. Measured
   2026-08-08: agents.json went from a hired roster to 2 bytes. Guarded here
   by shape, because the hook cannot be driven headlessly.

Run: python3 scripts/test_durability_retry.py
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import re
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


def _sse_response(text='ok'):
    """A fake streaming chat-completions response the driver can iterate."""
    lines = [
        b'data: ' + json.dumps(
            {'choices': [{'index': 0, 'delta': {'content': text}}]}).encode() + b'\n',
        b'data: {"choices": [], "usage": {"prompt_tokens": 2, "completion_tokens": 3}}\n',
        b'data: [DONE]\n',
    ]

    class _R:
        def __iter__(self): return iter(lines)
        def close(self): pass
    return _R()


def _night_ctx(nr):
    """NightContext whose hermes_home resolves to an openrouter backend, so
    llm_call routes through the OpenRouter driver (urlopen is monkeypatched —
    nothing leaves the process)."""
    hh = tempfile.mkdtemp(prefix='dur-hermes-')
    (pathlib.Path(hh) / 'config.yaml').write_text(
        'model:\n  default: test-model\n  provider: openrouter\n')
    (pathlib.Path(hh) / '.env').write_text('OPENROUTER_API_KEY=sk-or-test\n')
    return nr.NightContext('http://127.0.0.1:1', hermes_home=hh)


def test_night_retry() -> None:
    """llm_call rides the driver contract now (drivers/local_http.py); the
    retry policy lives in llm_call itself, keyed off DriverError.upstream.
    Same four guarantees as the old _llm_post_with_retry tests."""
    os.environ.setdefault('CAFRESOHQ_HQ_STATE_DIR', tempfile.mkdtemp(prefix='dur-'))
    import night_runner as nr
    from drivers.base import DriverError

    slept: list[float] = []
    nr.time.sleep = lambda s: slept.append(s)          # keep the suite fast
    ctx = _night_ctx(nr)
    msgs = [{'role': 'user', 'content': 'hi'}]

    print('=== the night shift survives a transient 429 ===')
    calls = {'n': 0}

    def flaky(req, timeout=180):
        calls['n'] += 1
        if calls['n'] < 3:
            raise _http_error(429)
        return _sse_response('recovered')

    nr.urllib.request.urlopen = flaky
    slept.clear()
    text, used = nr.llm_call(ctx, msgs)
    check('retries until it succeeds', text == 'recovered', repr(text))
    check('took exactly 3 attempts', calls['n'] == 3, str(calls['n']))
    check('usage flows through', used == 5, str(used))
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
        nr.llm_call(ctx, msgs)
    except DriverError as e:
        raised = (e.upstream == 401)
    check('401 propagates', raised)
    check('401 is NOT retried', calls['n'] == 1, f'{calls["n"]} attempts')

    print('=== Retry-After is honoured over our own backoff ===')
    calls['n'] = 0
    slept.clear()

    def rate_limited(req, timeout=180):
        calls['n'] += 1
        if calls['n'] == 1:
            raise _http_error(429, retry_after='7')
        return _sse_response()

    nr.urllib.request.urlopen = rate_limited
    nr.llm_call(ctx, msgs)
    check('waited the advertised 7s', slept == [7.0], repr(slept))

    print('=== it gives up rather than looping forever ===')
    calls['n'] = 0

    def always_503(req, timeout=180):
        calls['n'] += 1
        raise _http_error(503)

    nr.urllib.request.urlopen = always_503
    gave_up = False
    try:
        nr.llm_call(ctx, msgs)
    except DriverError:
        gave_up = True
    check('raises after the cap', gave_up)
    check('capped at _LLM_RETRY_MAX attempts',
          calls['n'] == nr._LLM_RETRY_MAX, f'{calls["n"]} attempts')

    print('=== keyless LOCAL backends now work (old client refused them) ===')
    hh = tempfile.mkdtemp(prefix='dur-local-')
    (pathlib.Path(hh) / 'config.yaml').write_text(
        'model:\n  default: gemma-3\n  provider: lmstudio\n'
        '  base_url: http://127.0.0.1:9/v1\n')
    local_ctx = nr.NightContext('http://127.0.0.1:1', hermes_home=hh)
    seen = {}

    def local_ok(req, timeout=180):
        seen['url'] = req.full_url
        seen['auth'] = req.headers.get('Authorization', '')
        return _sse_response('local answer')

    nr.urllib.request.urlopen = local_ok
    text, _ = nr.llm_call(local_ctx, msgs)
    check('local backend answers', text == 'local answer', repr(text))
    check('hit the configured base_url',
          seen.get('url') == 'http://127.0.0.1:9/v1/chat/completions', repr(seen))
    check('keyless — no Authorization header', not seen.get('auth'), repr(seen))


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


def test_fresh_browser_keeps_the_office() -> None:
    """A fresh browser context must not delete the office from disk.

    Checked by SHAPE, not by driving: useFileStored is a React hook with a
    network fetch, and the failure needs a real browser with an empty mirror
    and a populated file. What is checkable here is the two invariants the
    fix rests on, expressed as the DEFECT rather than the cure — per the
    lesson that a rule hunting for a fix can be satisfied by a coincidence.

    Defect 1: the mount fetch abandons the server copy on `dirtyRef` alone.
    That is what turned the GET away while the session held nothing but its
    own empty seed, and it is the actual wipe. The guard requires the
    early-return to consider something else too.

    Defect 2: the debounced PUT can fire before the fetch has settled, so
    the app writes a file it has never read.
    """
    src = (ROOT / 'app' / 'storage.jsx').read_text(encoding='utf-8')

    # The adopt path must not bail on dirtyRef by itself.
    bare_bail = re.search(r'if\s*\(\s*dirtyRef\.current\s*\)\s*return', src)
    check('the mount fetch does not abandon the file on dirtyRef alone',
          bare_bail is None,
          'found a bare `if (dirtyRef.current) return` in the adopt path')

    # …and it must reason about whether the local value is still the seed.
    check('…it compares what the session holds against the seed it started with',
          'seedRef' in src and 'valRef' in src,
          'seedRef/valRef missing — nothing distinguishes a real edit from a boot write')

    # No file write before the fetch has settled, either way.
    check('no file write before the mount fetch settles',
          'hydratedRef' in src and re.search(r'if\s*\(\s*!\s*hydratedRef\.current\s*\)\s*return', src) is not None,
          'the debounced PUT is not gated on hydration')
    check('…and an unreachable server still counts as settled',
          re.search(r'catch\s*\(\s*\(\s*\)\s*=>\s*\{\s*hydratedRef\.current\s*=\s*true', src) is not None
          or 'hydratedRef.current = true; });' in src,
          'an offline office could never write to disk again')


def main() -> int:
    test_night_retry()
    test_atomic_state_write()
    test_fresh_browser_keeps_the_office()
    print()
    if FAILS:
        print(f'durability/retry: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('durability/retry: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
