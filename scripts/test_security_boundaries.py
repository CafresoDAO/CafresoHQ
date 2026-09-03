#!/usr/bin/env python3
"""Regression guard for the request-boundary checks in serve.py.

These three protect a chain that was, in the stock local configuration, remote
code execution reachable from a visited web page:

    a page at http://evil.example.com (DNS → 127.0.0.1)
      → Host: evil.example.com was echoed into the origin allowlist
      → so /terminal/nonce answered it
      → and CAFRESOHQ_API_KEY defaults to empty, which used to mean "allow"
      → so /tools ran subprocess(..., shell=True) with Bash in the default set.

Each link is now closed independently. A failure here means one of them has been
reopened, so treat it as release-blocking rather than a flaky test.

Run: python3 scripts/test_security_boundaries.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f' — {detail}' if detail and not cond else ''))
    if not cond:
        FAILS.append(label)


class _FakeHandler:
    """Minimal stand-in exposing just what the boundary methods read: a
    .headers mapping, .client_address, .path and .connection."""


def main() -> int:
    os.environ['GAP_CRON'] = '0'
    os.environ['NEWS_CRON'] = '0'
    os.environ['TOPICS_CRON'] = '0'
    os.environ.pop('SEARCH_WORKER', None)
    os.environ['CAFRESOHQ_HQ_STATE_DIR'] = tempfile.mkdtemp(prefix='sec-bound-')
    os.chdir(ROOT)
    import serve

    H = serve.Handler

    def handler(host='', origin='', peer='127.0.0.1', path='/tools/exec',
                upgrade='', api_key=''):
        hdrs = {'Host': host, 'Origin': origin, 'Upgrade': upgrade,
                'X-API-Key': api_key}
        obj = _FakeHandler.__new__(_FakeHandler)
        obj.headers = type('H', (), {
            'get': staticmethod(lambda k, d='': hdrs.get(k, d))})()
        obj.client_address = (peer, 12345)
        obj.path = path
        obj.connection = None
        return obj

    print('=== DNS rebinding cannot authorise itself via the Host header ===')
    origins = H._app_origins(handler(host='evil.example.com'))
    check('an attacker hostname is NOT in the origin allowlist',
          'http://evil.example.com' not in origins, repr(sorted(origins)[:3]))
    check('and no scheme variant of it slipped in',
          not any('evil.example.com' in o for o in origins))

    loop = H._app_origins(handler(host='localhost:8787'))
    check('loopback Host is still honoured (local dev keeps working)',
          'http://localhost:8787' in loop)
    ipv4 = H._app_origins(handler(host='127.0.0.1:9999'))
    check('a loopback literal on any port is honoured',
          'http://127.0.0.1:9999' in ipv4)

    prod = H._app_origins(handler(host='hq.cafreso.com'))
    check('the configured production origin survives',
          'https://hq.cafreso.com' in prod)

    print('=== an unset API key means loopback-only, not open ===')
    saved_key = serve.CAFRESOHQ_API_KEY
    serve.CAFRESOHQ_API_KEY = ''
    try:
        check('loopback may reach a protected route',
              H._api_key_ok(handler(peer='127.0.0.1', path='/tools/exec')))
        check('a LAN peer may NOT reach a protected route',
              not H._api_key_ok(handler(peer='192.168.1.50', path='/tools/exec')))
        check('a public peer may NOT reach a protected route',
              not H._api_key_ok(handler(peer='203.0.113.9', path='/terminal/pty')))
        check('unprotected paths stay open to everyone',
              H._api_key_ok(handler(peer='203.0.113.9', path='/health')))
    finally:
        serve.CAFRESOHQ_API_KEY = saved_key

    print('=== with a key set, it is required and header-only ===')
    serve.CAFRESOHQ_API_KEY = 's3cret-key'
    try:
        check('correct key in the header is accepted',
              H._api_key_ok(handler(peer='203.0.113.9', api_key='s3cret-key')))
        check('a wrong key is rejected',
              not H._api_key_ok(handler(peer='203.0.113.9', api_key='nope')))
        check('no key is rejected even from loopback once a key is configured',
              not H._api_key_ok(handler(peer='127.0.0.1')))
        check('?k= is refused on an ordinary request (it leaks via logs/Referer)',
              not H._api_key_ok(handler(peer='203.0.113.9',
                                        path='/tools/exec?k=s3cret-key')))
        check('?k= IS accepted on a WebSocket handshake (headers impossible there)',
              H._api_key_ok(handler(peer='203.0.113.9', upgrade='websocket',
                                    path='/terminal/pty?k=s3cret-key')))
    finally:
        serve.CAFRESOHQ_API_KEY = saved_key

    print('=== /brave/search spends the office\'s own key like any other proxy ===')
    # /brave/search falls back to the server-side BRAVE_API_KEY env var when
    # the caller sends no X-Brave-Key (see _brave_search) — so it MUST sit
    # behind the same CAFRESOHQ_API_KEY gate as every other route that spends
    # a shared credential on the caller's behalf (/hermes, /tools). It used to
    # be entirely absent from _KEY_PROTECTED_PREFIXES: a plain
    # `curl /brave/search?q=x` with zero headers reached api.search.brave.com
    # even with a key configured.
    serve.CAFRESOHQ_API_KEY = 's3cret-key'
    try:
        check('no key at all is rejected once a key is configured',
              not H._api_key_ok(handler(peer='127.0.0.1', path='/brave/search?q=x')))
        check('the correct key is accepted',
              H._api_key_ok(handler(peer='203.0.113.9', path='/brave/search?q=x',
                                    api_key='s3cret-key')))
    finally:
        serve.CAFRESOHQ_API_KEY = saved_key
    serve.CAFRESOHQ_API_KEY = ''
    try:
        check('with no key configured, a LAN peer still cannot reach it',
              not H._api_key_ok(handler(peer='192.168.1.50', path='/brave/search?q=x')))
    finally:
        serve.CAFRESOHQ_API_KEY = saved_key
    check("/brave is listed alongside its key-gated siblings in "
          "_HOST_DATA_PREFIXES (an untrusted Origin must get no ACAO, not '*')",
          '/brave' in serve._HOST_DATA_PREFIXES)

    print('=== Bash is not executable by default ===')
    check('Bash is absent from the default allowed-tools set',
          'Bash' not in serve._cafresohq_allowed_tools,
          repr(serve._cafresohq_allowed_tools))

    print('=== the keyless /fs/site preview is sandboxed off-loopback ===')
    check('loopback gets the relaxed local rules',
          H._site_sandbox_ok(handler(peer='127.0.0.1')))
    check('a LAN peer does not', not H._site_sandbox_ok(handler(peer='10.0.0.42')))

    # strict=True must refuse the local-mode skip that made this an arbitrary read.
    outside = str(pathlib.Path(tempfile.gettempdir()) / 'definitely-outside-sandbox')
    saved_dirs = serve._cafresohq_allowed_dirs
    serve._cafresohq_allowed_dirs = [str(ROOT)]
    try:
        strict_refused = False
        try:
            H._validate_path(handler(), outside, strict=True)
        except PermissionError:
            strict_refused = True
        check('strict=True refuses a path outside the sandbox', strict_refused)

        inside_ok = True
        try:
            H._validate_path(handler(), str(ROOT / 'hq.html'), strict=True)
        except PermissionError:
            inside_ok = False
        check('strict=True still allows a path inside the sandbox', inside_ok)
    finally:
        serve._cafresohq_allowed_dirs = saved_dirs

    print()
    if FAILS:
        print(f'security boundaries: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('security boundaries: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
