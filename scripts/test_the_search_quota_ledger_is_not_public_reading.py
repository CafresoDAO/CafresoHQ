#!/usr/bin/env python3
"""What this office has been searching for is not public reading.

`/gap/status` and `/news/status` proxy the standalone search worker's status:
quota counters and the cron ledger — what the office has been looking up and
how much of its allowance is left. Both were under no prefix list at all, so
the key gate passed over them and `## 333.`'s sweep of `_HOST_DATA_PREFIXES`
did not reach them either, and `_cors` fell through to its public branch.
Measured against a real serve.py with no configuration, `Origin:
https://evil.example` got `200` and `Access-Control-Allow-Origin: *` on both.

This is the third finding in a row in this one list (`## 333.`, `## 341.`, and
this), and every one was found by measuring rather than by reading the list.
So this test measures too: it boots a real server and asks with a stranger's
Origin, rather than asserting on the tuple's contents.
"""
import http.client
import os
import pathlib
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 18893
fails = []


def ok(label, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + label
          + (('  — ' + str(detail)) if detail and not cond else ''))
    if not cond:
        fails.append(label)


def get(path, origin=None):
    """One real request. Returns (status, acao) — acao is None when the
    header is absent, which is the whole point of the exercise."""
    c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=10)
    try:
        c.request('GET', path, headers={'Origin': origin} if origin else {})
        r = c.getresponse()
        r.read()
        return r.status, r.getheader('Access-Control-Allow-Origin')
    finally:
        c.close()


home = tempfile.mkdtemp(prefix='gapstatus-')
env = dict(os.environ, PORT=str(PORT), HOME=home)
env.pop('CAFRESOHQ_API_KEY', None)          # a real first run has no key
env.pop('CAFRESOHQ_ALLOWED_DIRS', None)
proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=str(ROOT), env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(80):
        try:
            get('/health')
            break
        except OSError:
            time.sleep(0.25)
    else:
        print('  FAIL  the server came up')
        print('\nFAILED: server never answered')
        sys.exit(1)
    ok('the server came up', True)

    EVIL = 'https://evil.example'

    # ── A. the operator status routes withhold ACAO from a stranger ──────
    #
    # The status body itself may be a 200 or a 502 depending on whether the
    # worker container happens to be running; either way the office's answer
    # must not be readable by a page the boss merely visited.
    for path in ('/gap/status', '/news/status'):
        status, acao = get(path, EVIL)
        ok(f'{path} answers at all', status in (200, 502), status)
        ok(f'{path} gives a stranger no ACAO', acao is None,
           f'{acao!r} — a visited page can read the search quota ledger')

    # ── B. the operator's own habit still works ──────────────────────────
    #
    # These routes exist for `curl localhost:8787/gap/status`. curl has never
    # needed an ACAO header, and no part of the UI calls them, so withholding
    # it costs nothing — but the route must still ANSWER.
    for path in ('/gap/status', '/news/status'):
        status, _ = get(path)
        ok(f'{path} still answers with no Origin at all', status in (200, 502),
           status)

    # ── C. no collateral: the public probes stay public ──────────────────
    #
    # Over-listing is its own bug — /health exists to answer anyone.
    status, acao = get('/health', EVIL)
    ok('/health still answers a stranger', status == 200, status)
    ok('/health still carries ACAO', acao is not None,
       'a public probe was swept into the host-data list')

    # ── D. the neighbours this finding came from are still closed ────────
    #
    # `## 333.` (the model roster) and the /fs sandbox: pinned here so a
    # future edit to the list cannot quietly reopen one while fixing another.
    for path in ('/lmstudio/models', '/fs/file?path=/etc/hosts'):
        _s, acao = get(path, EVIL)
        ok(f'{path} still gives a stranger no ACAO', acao is None, repr(acao))
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

print()
if fails:
    print('FAILED %d check(s): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('the search quota ledger is not public reading: all checks passed')
