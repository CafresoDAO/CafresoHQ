#!/usr/bin/env python3
"""A failure the boss meets is a sentence — not an errno, a path, or a key.

§7: "Raw error dumps — every failure is one honest sentence plus 'try again /
ask differently / pick another coworker.'"

`## 403` fixed two doors that answered 200 over a failure and left a finding
for whoever held /hermes/provider: its 500 carries a raw errno and an absolute
filesystem path into a body §7 says the boss must not meet. `## 407` swept the
class. Measured against a REAL serve.py, before anything was changed:

    POST /hermes/provider, ~/.hermes unwritable
      -> 500 {"error": "write .env: [Errno 13] Permission denied:
              '/Users/…/.hermes/..env.25a018b7.tmp'"}
    POST /hermes/provider {"key": ""}   (the REMOVAL path)   -> same shape
    POST /hermes/model, config.yaml unreadable
      -> 500 {"error": "read config: [Errno 13] Permission denied: …"}
    PUT  /vault/note, vault folder unwritable
      -> 500 {"error": "[Errno 13] Permission denied:
              '/private/var/…/vault/.x.md.95ug1cbf.tmp'"}

Three things are wrong with each, and the third is the one nobody had named:
the errno is not actionable, the absolute path is the developer's machine
leaking into a browser toast, and the path names a TEMPORARY file that
`_atomic_write` has already unlinked — so the single concrete-looking detail
is also the false one.

Then the worse half, which no AST count would have found because the body is
composed one file away and reaches the door through a variable. Six vault
doors relayed Obsidian's own response body verbatim. Driven against a
stand-in Local REST API that echoes the request it turned down — a shape real
servers ship in debug mode — three of them handed the boss's own Obsidian API
key back to the browser:

    GET    /vault/note -> 401 {"error": "{… \\"Authorization\\": \\"Bearer <THE KEY>\\" …}"}
    PUT    /vault/note -> 401  same
    DELETE /vault/note -> 401  same
    POST   /vault/open -> 401  the same relay, saved only by [:200] truncation

`exporters.py` has had `_scrub(body, api_key)` on its four generate doors
since #322. Nothing else in the server used it, and these six were the doors
that needed it. They do not scrub now — they refuse in a sentence and the
upstream body goes to the SERVER LOG, scrubbed of the key on the way. Keeping
the diagnostic and moving it off the boss's screen is the fix; deleting it
would cost a developer the only description of what Obsidian objected to.

The invariants below are general on purpose, not pinned strings: no error
body a boss can reach may carry an absolute path, an `[Errno N]`, a newline,
more than 90 characters, a bare digit, or a credential. The 90 and the digit
are not fastidiousness — `app/floor.jsx`'s `officeCause` rewrites bare
numbers into sentences about the wrong subject, and `cleanCause` truncates at
90 (app/floor.jsx:720), so a sentence that says what to do in its second half
loses exactly that half. Same two constraints `## 403` wrote its search
refusals under.

Every key in this file is an obvious fake. The Hermes one is of the right
SHAPE because the host's regex gate is part of the path under test; the
Obsidian one is nonsense.

Run: python3 scripts/test_an_error_the_boss_meets_is_a_sentence_not_a_stack.py
"""
import ast
import http.server
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FAKE_OR = 'sk-or-v1-test-not-a-real-key-000000'
FAKE_OBS_KEY = 'obsidianfakekey0000000000000000deadbeef'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# ── the invariant every user-facing error body must satisfy ─────────────
ERRNO = re.compile(r'\[Errno\s*\d+\]')
ABS_PATH = re.compile(r"['\"\s(]/(?:Users|home|private|var|tmp|etc|opt)/")


def offences(body_text, secrets=()):
    """Everything §7 forbids in one place, so every caller checks the same
    list and a new door cannot be held to a weaker rule than an old one."""
    out = []
    try:
        err = json.loads(body_text).get('error')
    except Exception:
        return ['body is not JSON: ' + body_text[:80]]
    if not isinstance(err, str):
        return []                      # no error string to judge
    for s in secrets:
        if s and len(s) >= 8 and s in err:
            out.append('CARRIES A CREDENTIAL')
    if ERRNO.search(err):
        out.append('carries a raw errno')
    if ABS_PATH.search(err):
        out.append('carries an absolute filesystem path')
    if '\n' in err:
        out.append('is more than one line')
    if len(err) > 90:
        out.append('is %d chars — cleanCause truncates at 90' % len(err))
    if any(c.isdigit() for c in err):
        out.append('carries a bare digit — officeCause rewrites those')
    if not err.strip():
        out.append('is empty')
    return out


# ── round 1: structural ─────────────────────────────────────────────────
def structural():
    print('\nRound 1 — the shapes are gone from the source')

    serve = (ROOT / 'serve.py').read_text(encoding='utf-8')
    # The relay shape: an upstream response body sliced, decoded and sent as
    # `error`. Walked as an expression, not grepped, so a reformat cannot
    # hide one.
    relays = []
    for node in ast.walk(ast.parse(serve)):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not (isinstance(f, ast.Attribute) and f.attr == '_send_json'):
            continue
        if len(node.args) < 2:
            continue
        for sub in ast.walk(node.args[1]):
            if (isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == 'decode'
                    and isinstance(sub.func.value, ast.Subscript)):
                relays.append(node.lineno)
    check('serve.py sends no sliced upstream body as an error',
          not relays,
          'still relayed at line(s) %s — refuse in a sentence and log the '
          'body instead' % relays)

    check('_obsidian_refusal exists beside _obsidian_search_refusal',
          '_obsidian_refusal' in serve and '_log_upstream' in serve)

    # Every sentence the two refusal helpers can return, judged by the same
    # rule the live rounds use. Lifted by executing the helpers, so this
    # tracks the real branches rather than a copy of them.
    ns = {}
    for fn in ('_obsidian_refusal', '_obsidian_search_refusal'):
        m = re.search(r'\ndef %s\(.*?\n(?=\n\n|\ndef |\n# )' % fn, serve, re.S)
        if not m:
            check(fn + ' is liftable', False)
            continue
        exec(m.group(0), ns)
    bad = []
    for st in (200, 400, 401, 403, 404, 405, 409, 415, 429, 500, 502, 503):
        for fn in ('_obsidian_refusal', '_obsidian_search_refusal'):
            if fn not in ns:
                continue
            s = ns[fn](st)
            o = offences(json.dumps({'error': s}))
            if o:
                bad.append((fn, st, o))
    check('every obsidian refusal sentence obeys the rule', not bad, bad[:3])

    # drivers/hermes.py: the eight `f'…: {e}'` config errors are gone. They
    # reach a body through `err` -> DriverError -> str(e), which is exactly
    # the variable hop an expression-level pass over serve.py cannot see.
    herm = (ROOT / 'drivers' / 'hermes.py').read_text(encoding='utf-8')
    leftovers = re.findall(r"return False, False,[^\n]*f'[^']*\{e\}", herm) + \
        re.findall(r"return False, False, cfg_p[^\n]*f'[^']*\{e\}", herm)
    check('drivers/hermes.py returns no interpolated exception as an error',
          not leftovers, leftovers[:3])
    check('drivers/hermes.py has a _config_failure that logs and returns prose',
          '_config_failure' in herm and 'sys.stderr.write' in herm)


# ── the live office ─────────────────────────────────────────────────────
def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def req(url, payload=None, method=None):
    r = urllib.request.Request(
        url, data=json.dumps(payload).encode() if payload is not None else None,
        headers={'content-type': 'application/json'},
        method=method or ('POST' if payload is not None else 'GET'))
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:                       # noqa: BLE001
        return 0, str(e)


def boot(home, extra_env=None):
    """A real serve.py on a scratch HOME with a STUB `hermes` first on PATH.

    The stub is not a convenience. `gateway_restart` is a bare
    `subprocess.Popen(['hermes', 'gateway', 'restart'])` — a plain PATH
    lookup, not gated on HERMES_HOME — so on any machine with a real hermes
    installed, a test run would restart the developer's own gateway. It must
    not be able to find one."""
    binp = home / 'bin'
    binp.mkdir(parents=True, exist_ok=True)
    stub = binp / 'hermes'
    stub.write_text('#!/bin/sh\necho "$@" >> "%s/hermes-calls.log"\nexit 0\n' % home,
                    encoding='utf-8')
    stub.chmod(0o755)
    (home / 'work').mkdir(parents=True, exist_ok=True)
    port = free_port()
    env = dict(os.environ, PORT=str(port), HOME=str(home),
               HERMES_HOME=str(home / '.hermes'),
               CAFRESOHQ_HQ_STATE_DIR=str(home / 'state'),
               CAFRESOHQ_VAULT=str(home / 'vault'),
               CAFRESOHQ_ALLOWED_DIRS=str(home / 'work'),
               PATH=str(binp) + ':/usr/bin:/bin')
    for k in ('OPENROUTER_API_KEY', 'GOOGLE_API_KEY', 'GROQ_API_KEY',
              'CAFRESOHQ_VAULT_BACKEND', 'CAFRESOHQ_OBSIDIAN_URL',
              'CAFRESOHQ_OBSIDIAN_KEY'):
        env.pop(k, None)
    env.update(extra_env or {})
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=str(ROOT), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = 'http://127.0.0.1:%d' % port

    def kill():
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    for _ in range(80):
        if req(base + '/hermes/trial-status')[0] == 200:
            return base, kill
        time.sleep(0.25)
    kill()
    return None, (lambda: None)


# ── round 2: a real office that cannot write ────────────────────────────
def unwritable_office():
    print('\nRound 2 — a real office whose files it cannot read or write')
    home = Path(tempfile.mkdtemp(prefix='hq-407-errno-'))
    base, kill = boot(home)
    if not base:
        check('a real serve.py came up on a scratch HOME', False)
        return
    hh = home / '.hermes'
    vault = home / 'vault'
    try:
        hh.mkdir(parents=True, exist_ok=True)
        vault.mkdir(parents=True, exist_ok=True)

        ladder = []

        def drive(label, lock, path, payload, method=None):
            os.chmod(lock, 0o500)
            try:
                s, b = req(base + path, payload, method)
            finally:
                os.chmod(lock, 0o700)
            ladder.append((label, s, b))
            o = offences(b)
            check(label + ' answers a sentence', not o, '%s -> %s %s' % (o, s, b[:140]))

        drive('POST /hermes/provider (new key, folder unwritable)',
              hh, '/hermes/provider', {'provider': 'openrouter', 'key': FAKE_OR})

        (hh / '.env').write_text('OPENROUTER_API_KEY=placeholder\n', encoding='utf-8')
        drive('POST /hermes/provider (removal, folder unwritable)',
              hh, '/hermes/provider', {'provider': 'openrouter', 'key': ''})

        cfg = hh / 'config.yaml'
        cfg.write_text('model:\n  default: placeholder\n', encoding='utf-8')
        os.chmod(cfg, 0o000)
        s, b = req(base + '/hermes/model', {'model': 'openai/gpt-oss-120b:free'})
        os.chmod(cfg, 0o600)
        ladder.append(('POST /hermes/model (config unreadable)', s, b))
        check('POST /hermes/model (config unreadable) answers a sentence',
              not offences(b), '%s %s' % (s, b[:140]))

        drive('PUT /vault/note (vault folder unwritable)',
              vault, '/vault/note?path=x.md', {'content': 'hi'}, 'PUT')

        (vault / 'a.md').write_text('hi', encoding='utf-8')
        drive('POST /vault/rename (vault folder unwritable)',
              vault, '/vault/rename', {'from': 'a.md', 'to': 'b.md'})

        print('\n    the ladder, for the record:')
        for label, s, b in ladder:
            print('      %-52s -> %s %s' % (label[:52], s, b[:96]))
    finally:
        kill()
        subprocess.run(['chmod', '-R', 'u+rwX', str(home)])


# ── round 3: the credential ─────────────────────────────────────────────
class VerboseObsidian(http.server.BaseHTTPRequestHandler):
    """A Local REST API that quotes the request it turned down, headers and
    all. Not a strawman: echoing the offending request is a common debug
    shape, and the Authorization header travels with it."""

    def log_message(self, *a):
        pass

    def _answer(self):
        body = json.dumps({
            'errorCode': 40100,
            'message': 'Authorization failed for request',
            'request': {'path': self.path, 'headers': dict(self.headers)},
        }).encode()
        self.send_response(401)
        self.send_header('content-type', 'application/json')
        self.send_header('content-length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    do_GET = do_PUT = do_POST = do_DELETE = do_PATCH = _answer


def credential_never_travels():
    print('\nRound 3 — a verbose plugin cannot hand the key back to the browser')
    obs_port = free_port()
    obs = http.server.ThreadingHTTPServer(('127.0.0.1', obs_port), VerboseObsidian)
    threading.Thread(target=obs.serve_forever, daemon=True).start()
    home = Path(tempfile.mkdtemp(prefix='hq-407-cred-'))
    base, kill = boot(home, {
        'CAFRESOHQ_VAULT_BACKEND': 'rest',
        'CAFRESOHQ_OBSIDIAN_URL': 'http://127.0.0.1:%d' % obs_port,
        'CAFRESOHQ_OBSIDIAN_KEY': FAKE_OBS_KEY,
    })
    if not base:
        check('a real serve.py came up against a stand-in Obsidian', False)
        obs.shutdown()
        return
    doors = [
        ('GET', '/vault/note?path=a.md', None),
        ('PUT', '/vault/note?path=a.md', {'content': 'hi'}),
        ('DELETE', '/vault/note?path=a.md', None),
        ('GET', '/vault/file?path=a.png', None),
        ('POST', '/vault/open', {'path': 'a.md'}),
        ('GET', '/vault/search?q=x', None),
    ]
    try:
        for m, p, pay in doors:
            s, b = req(base + p, pay, m)
            o = offences(b, secrets=(FAKE_OBS_KEY,))
            check('%s %s refuses without the key' % (m, p.split('?')[0]),
                  not o, '%s -> %s %s' % (o, s, b[:140]))
    finally:
        kill()
        obs.shutdown()
        subprocess.run(['chmod', '-R', 'u+rwX', str(home)])


def main():
    print('§7 — an error the boss meets is a sentence, not a stack')
    structural()
    unwritable_office()
    credential_never_travels()
    print()
    if FAILS:
        print('§7 error bodies: %d FAILED — %s' % (len(FAILS), ', '.join(FAILS[:4])))
        return 1
    print('§7 error bodies: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
