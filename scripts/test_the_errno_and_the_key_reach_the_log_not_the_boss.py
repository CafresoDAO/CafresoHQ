#!/usr/bin/env python3
"""#411 — finishing the sweep `## 407` left open, by driving it.

§7: "Raw error dumps — every failure is one honest sentence plus 'try again /
ask differently / pick another coworker.'"

`## 407` AST-walked 357 error-body sites, fixed five errno-and-path bodies and
six Obsidian relays that handed the boss their own API key back, and closed
with the fs and pty columns marked EXPOSED — "sampled, not cleared. Six doors
driven is not a hundred." This is that hundred, driven.

Two things `## 407` predicted, and one it did not.

  Predicted: the table lies. fs_routes.py answered real sentences at every
  door `## 407` reached — and seven doors it did not reach answered the exact
  body `## 403` reported:

      GET  /fs/stat   (unreadable file) -> 500 [Errno 13] Permission denied: '/…'
      POST /fs/mkdir  (unwritable dir)  -> 500 the same
      POST /fs/mkdir  (under a file)    -> 409 cannot create folder here: [Errno 20] …
      POST /fs/rename (unwritable dir)  -> 500 the same, carrying BOTH paths
      POST /fs/delete (unwritable dir)  -> 500 the same
      POST /fs/upload (unwritable dir)  -> 500 mkdir failed: [Errno 13] …
      POST /terminal/stream (bad binary)-> 500 spawn claude: [Errno 13] …

  Not predicted, because no walk of `_send_json(4xx…)` can see it: three more
  carry an errno into a **200** body, as a per-item `reason`/`error` in the
  /fs/collect and /fs/upload receipts. A 200 is still a body the boss reads.

  And the question `## 407` asked and left open — is Obsidian the only
  upstream relayed verbatim? — is answered NO by round 4 below. It was not,
  and the other one is worse.

Round 4 is the finding. `drivers/local_http.py` did `e.read()[:300]` into a
DriverError that /agent/stream sends as `str(e)` — the identical shape, one
file away, reached through a variable. Every OpenAI-compat backend goes
through it and `_headers()` puts the key in `Authorization: Bearer`, so
OpenRouter / Groq / Gemini reach the boss's real paid provider credential
through it, not a local daemon's.

Driven against a stand-in that quotes the request it turned down, the fake key
came back to the browser in full at POST /agent/stream -> 502. With the
stand-in serialising its echo in insertion order it fell one character outside
the 300-slice; `sort_keys=True` — the most ordinary thing a JSON API does —
moved it back inside. That is `## 407`'s /vault/open lesson exactly: a bound
that happens to exclude the secret today is not a defence, so round 4 pins the
sorted case, where the leak is real rather than nearly real.

Every key in this file is an obvious fake.

Run: python3 scripts/test_the_errno_and_the_key_reach_the_log_not_the_boss.py
"""
import ast
import base64
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
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
Q = urllib.parse.quote

FAKE_LM_KEY = 'lmstudiofakekey000000000000000000notreal'
FAKE_HERMES_KEY = 'hermesfakeserverkey00000000000000notreal'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# ── the invariant, identical to `## 407`'s so a new door cannot be held to a
#    weaker rule than an old one ─────────────────────────────────────────────
ERRNO = re.compile(r'\[Errno\s*\d+\]')
ABS_PATH = re.compile(r"['\"\s(:]/(?:Users|home|private|var|tmp|etc|opt)/")


def judge(err, secrets=()):
    out = []
    if not isinstance(err, str):
        return out
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


def offences(body_text, secrets=()):
    """Every string a boss can read out of this body, judged.

    Deliberately NOT just `body['error']`: three of the sites this hunt fixed
    put an errno in a per-item `reason`/`error` inside a 200 receipt, which a
    top-level-only check cannot see. Walks the whole document instead."""
    try:
        doc = json.loads(body_text)
    except Exception:
        return ['body is not JSON: ' + body_text[:80]]
    out = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ('error', 'reason', 'message', 'detail') and isinstance(v, str):
                    for o in judge(v, secrets):
                        out.append('%s.%s %s (%r)' % (path, k, o, v[:70]))
                else:
                    walk(v, path + '.' + str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, '%s[%d]' % (path, i))
    walk(doc, '$')
    return out


# ── round 1: structural ─────────────────────────────────────────────────────
def _interpolates_exception(node, handler_names):
    """True if this expression weaves a caught exception into a string."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.FormattedValue):
            for n in ast.walk(sub.value):
                if isinstance(n, ast.Name) and n.id in handler_names:
                    return True
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                and sub.func.id == 'str' and sub.args
                and isinstance(sub.args[0], ast.Name)
                and sub.args[0].id in handler_names):
            return True
    return False


def structural():
    print('\nRound 1 — the shapes are gone from the source')

    for fn in ('fs_routes.py', 'pty_server.py'):
        src = (ROOT / fn).read_text(encoding='utf-8')
        tree = ast.parse(src)
        # every name bound by an `except … as NAME` in the file
        handlers = {h.name for h in ast.walk(tree)
                    if isinstance(h, ast.ExceptHandler) and h.name}
        bad = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if not (isinstance(f, ast.Attribute)
                    and f.attr in ('_send_json', 'send_error')):
                continue
            st = node.args[0].value if (node.args
                                        and isinstance(node.args[0], ast.Constant)) else None
            if not isinstance(st, int) or st < 400:
                continue
            for a in node.args[1:]:
                if _interpolates_exception(a, handlers):
                    bad.append('%s:%d' % (fn, node.lineno))
        check('%s sends no caught exception in a 4xx/5xx body' % fn,
              not bad, 'still interpolated at %s' % bad[:5])
        check('%s has the log/sentence split' % fn,
              ('_fs_failure' in src if fn == 'fs_routes.py' else '_pty_failure' in src)
              and 'sys.stderr.write' in src)

    # drivers/local_http.py: the verbatim upstream relay. Walked as an
    # expression — `e.read().decode(...)[:N]` reaching a DriverError message —
    # so a reformat cannot hide one, and this is the check that would have
    # caught the bug in the first place had `## 407` pointed it at drivers/.
    lh = (ROOT / 'drivers' / 'local_http.py').read_text(encoding='utf-8')
    relays = []
    for node in ast.walk(ast.parse(lh)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == 'DriverError'):
            continue
        for sub in ast.walk(node):
            if (isinstance(sub, ast.Name) and sub.id == 'detail') or \
               (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == 'read'):
                relays.append(node.lineno)
    check('drivers/local_http.py raises no upstream body as an error',
          not relays, 'still relayed at line(s) %s' % relays)
    check('drivers/local_http.py has _upstream_refusal and _log_upstream',
          '_upstream_refusal' in lh and '_log_upstream' in lh)
    check('the in-band frame relay dropped its whole-dict fallback',
          "e.get('code') or e)" not in lh,
          "_frame_error still stringifies the entire error dict")

    # Every sentence these files can answer, judged by the SAME rule the live
    # rounds use — lifted by executing the helpers, so this tracks the real
    # branches and cannot drift past 90 chars or grow a digit unnoticed.
    ns = {}
    m = re.search(r'\ndef _upstream_refusal\(.*?\n(?=\n\ndef |\n\n# )', lh, re.S)
    check('_upstream_refusal is liftable', bool(m))
    if m:
        exec(m.group(0), ns)
        bad = []
        for st in (400, 401, 403, 404, 405, 409, 415, 422, 429, 500, 502, 503):
            s = ns['_upstream_refusal'](st)
            if judge(s):
                bad.append((st, s, judge(s)))
        check('every upstream refusal sentence obeys the rule', not bad, bad[:3])

    bad = []
    for fn in ('fs_routes.py', 'pty_server.py'):
        src = (ROOT / fn).read_text(encoding='utf-8')
        for name, val in re.findall(r"^([A-Z][A-Z_]{3,})\s*=\s*'([^']*)'$",
                                    src, re.M):
            o = judge(val)
            if o:
                bad.append((fn, name, o))
    check('every refusal constant in fs_routes/pty_server obeys the rule',
          not bad, bad[:3])


# ── the live office ─────────────────────────────────────────────────────────
def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def req(url, payload=None, method=None, raw=None, headers=None):
    h = {'content-type': 'application/json'}
    h.update(headers or {})
    data = raw if raw is not None else (
        json.dumps(payload).encode() if payload is not None else None)
    r = urllib.request.Request(
        url, data=data, headers=h,
        method=method or ('POST' if data is not None else 'GET'))
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:                       # noqa: BLE001
        return 0, str(e)


def boot(home, extra_env=None, hermes_stub=False):
    """A real serve.py on a scratch HOME with an EMPTY bin dir first on PATH.

    Same reason `## 407` gave: `gateway_restart` is a bare
    `Popen(['hermes','gateway','restart'])`, a plain PATH lookup not gated on
    HERMES_HOME, so a test run on a developer box must not be able to find
    their real hermes. Nothing else is on PATH either, which is also what
    makes the CLI-not-found doors reachable.

    `hermes_stub=True` puts an inert `hermes` in that same pinned bin dir —
    which is the pin, not a hole in it. Round 5 needs it because
    `gateway_can_appear()` is `bool(resolve('hermes'))` on a fresh machine, so
    with no binary at all the proxy answers #399's 501 and never opens a
    connection to the upstream: the round would then be measuring the
    short-circuit and reporting it as a clean proxy."""
    binp = home / 'bin'
    binp.mkdir(parents=True, exist_ok=True)
    if hermes_stub:
        stub = binp / 'hermes'
        stub.write_text('#!/bin/sh\necho "$@" >> "%s/hermes-calls.log"\nexit 0\n'
                        % home, encoding='utf-8')
        stub.chmod(0o755)
    (home / 'work').mkdir(parents=True, exist_ok=True)
    port = free_port()
    env = dict(os.environ, PORT=str(port), HOME=str(home),
               HERMES_HOME=str(home / '.hermes'),
               CAFRESOHQ_HQ_STATE_DIR=str(home / 'state'),
               CAFRESOHQ_VAULT=str(home / 'vault'),
               CAFRESOHQ_ALLOWED_DIRS=str(home / 'work'),
               PATH=str(binp) + ':/usr/bin:/bin')
    for k in ('OPENROUTER_API_KEY', 'GOOGLE_API_KEY', 'GEMINI_API_KEY',
              'GROQ_API_KEY', 'API_SERVER_KEY', 'LMSTUDIO_API_KEY',
              'CAFRESOHQ_LMSTUDIO_URL', 'LMSTUDIO_BASE_URL',
              'CAFRESOHQ_OLLAMA_URL', 'CAFRESOHQ_CLAUDE_BIN',
              'CAFRESOHQ_VAULT_BACKEND', 'CAFRESOHQ_OBSIDIAN_URL',
              'CAFRESOHQ_OBSIDIAN_KEY'):
        env.pop(k, None)
    env.update(extra_env or {})
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=str(ROOT), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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


def _fixture(W):
    (W / 'sub').mkdir(exist_ok=True)
    (W / 'plain.txt').write_text('hello', encoding='utf-8')
    (W / 'site').mkdir(exist_ok=True)
    (W / 'site' / 'index.html').write_text('<h1>hi</h1>', encoding='utf-8')
    (W / 'site' / 'locked.html').write_text('x', encoding='utf-8')
    (W / 'locked').mkdir(exist_ok=True)
    (W / 'lockedfile.txt').write_text('x', encoding='utf-8')
    (W / 'nowrite').mkdir(exist_ok=True)
    (W / 'nowrite' / 'kid.txt').write_text('x', encoding='utf-8')
    (W / 'nowrite' / 'kiddir').mkdir(exist_ok=True)
    os.chmod(W / 'site' / 'locked.html', 0o000)
    os.chmod(W / 'locked', 0o000)
    os.chmod(W / 'lockedfile.txt', 0o000)
    os.chmod(W / 'nowrite', 0o500)


def b64(s):
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip('=')


MP = (b'--zz\r\nContent-Disposition: form-data; name="file"; filename="a.txt"\r\n'
      b'Content-Type: text/plain\r\n\r\nhello\r\n--zz--\r\n')
MPH = {'content-type': 'multipart/form-data; boundary=zz'}


# ── rounds 2 + 3: every /fs and /terminal door, driven ──────────────────────
def live_doors():
    print('\nRounds 2+3 — every /fs and /terminal door, driven')
    home = Path(tempfile.mkdtemp(prefix='hq-411-doors-'))
    base, kill = boot(home)
    if not base:
        check('a real serve.py came up on a scratch HOME', False)
        return
    W = home / 'work'
    try:
        _fixture(W)
        R = b64(str(W / 'site'))
        NUL = '/a\x00b'
        doors = [
            # (label, path, payload, method, raw, headers)
            ('GET  /fs/browse  outside',     '/fs/browse?path=' + Q('/etc'), None, None, None, None),
            ('GET  /fs/browse  not a dir',   '/fs/browse?path=' + Q(str(W / 'plain.txt')), None, None, None, None),
            ('GET  /fs/browse  unreadable',  '/fs/browse?path=' + Q(str(W / 'locked')), None, None, None, None),
            ('GET  /fs/browse  bad path',    '/fs/browse?path=' + Q(NUL), None, None, None, None),
            ('GET  /fs/collect no path',     '/fs/collect', None, None, None, None),
            ('GET  /fs/collect outside',     '/fs/collect?path=' + Q('/etc'), None, None, None, None),
            ('GET  /fs/collect bad path',    '/fs/collect?path=' + Q(NUL), None, None, None, None),
            ('GET  /fs/collect unreadable',  '/fs/collect?path=' + Q(str(W)), None, None, None, None),
            ('GET  /fs/file    no path',     '/fs/file', None, None, None, None),
            ('GET  /fs/file    outside',     '/fs/file?path=' + Q('/etc/hosts'), None, None, None, None),
            ('GET  /fs/file    missing',     '/fs/file?path=' + Q(str(W / 'no.txt')), None, None, None, None),
            ('GET  /fs/file    is a folder', '/fs/file?path=' + Q(str(W / 'sub')), None, None, None, None),
            ('GET  /fs/file    unreadable',  '/fs/file?path=' + Q(str(W / 'lockedfile.txt')), None, None, None, None),
            ('GET  /fs/file    bad path',    '/fs/file?path=' + Q(NUL), None, None, None, None),
            ('GET  /fs/stat    no path',     '/fs/stat', None, None, None, None),
            ('GET  /fs/stat    outside',     '/fs/stat?path=' + Q('/etc/hosts'), None, None, None, None),
            ('GET  /fs/stat    missing',     '/fs/stat?path=' + Q(str(W / 'no.txt')), None, None, None, None),
            ('GET  /fs/stat    is a folder', '/fs/stat?path=' + Q(str(W / 'sub')), None, None, None, None),
            ('GET  /fs/stat    UNREADABLE',  '/fs/stat?path=' + Q(str(W / 'lockedfile.txt')), None, None, None, None),
            ('GET  /fs/stat    bad path',    '/fs/stat?path=' + Q(NUL), None, None, None, None),
            ('GET  /fs/site    no root',     '/fs/site/', None, None, None, None),
            ('GET  /fs/site    bad base64',  '/fs/site/!!!!/index.html', None, None, None, None),
            ('GET  /fs/site    root outside', '/fs/site/%s/index.html' % b64('/etc'), None, None, None, None),
            ('GET  /fs/site    traversal',   '/fs/site/%s/%s' % (R, Q('../../../../etc/hosts')), None, None, None, None),
            ('GET  /fs/site    not found',   '/fs/site/%s/zz.html' % R, None, None, None, None),
            ('GET  /fs/site    unreadable',  '/fs/site/%s/locked.html' % R, None, None, None, None),
            ('GET  /fs/site    bad root',    '/fs/site/%s/index.html' % b64(NUL), None, None, None, None),
            ('POST /fs/upload  not multipart', '/fs/upload', {'x': 1}, None, None, None),
            ('POST /fs/upload  empty',       '/fs/upload', None, 'POST', b'', MPH),
            ('POST /fs/upload  outside',     '/fs/upload?path=' + Q('/etc'), None, None, MP, MPH),
            ('POST /fs/upload  not a dir',   '/fs/upload?path=' + Q(str(W / 'plain.txt')), None, None, MP, MPH),
            ('POST /fs/upload  bad path',    '/fs/upload?path=' + Q(NUL), None, None, MP, MPH),
            ('POST /fs/upload  MKDIR DENIED', '/fs/upload?path=' + Q(str(W / 'nowrite' / 'new')), None, None, MP, MPH),
            ('POST /fs/upload  UNDER A FILE', '/fs/upload?path=' + Q(str(W / 'plain.txt' / 'k')), None, None, MP, MPH),
            ('POST /fs/mkdir   bad json',    '/fs/mkdir', None, 'POST', b'{nope', None),
            ('POST /fs/mkdir   no path',     '/fs/mkdir', {}, None, None, None),
            ('POST /fs/mkdir   outside',     '/fs/mkdir', {'path': '/etc/zzz'}, None, None, None),
            ('POST /fs/mkdir   bad path',    '/fs/mkdir', {'path': NUL}, None, None, None),
            ('POST /fs/mkdir   file exists', '/fs/mkdir', {'path': str(W / 'plain.txt')}, None, None, None),
            ('POST /fs/mkdir   DENIED',      '/fs/mkdir', {'path': str(W / 'nowrite' / 'new')}, None, None, None),
            ('POST /fs/mkdir   UNDER A FILE', '/fs/mkdir', {'path': str(W / 'plain.txt' / 'k')}, None, None, None),
            ('POST /fs/rename  bad json',    '/fs/rename', None, 'POST', b'{nope', None),
            ('POST /fs/rename  no args',     '/fs/rename', {}, None, None, None),
            ('POST /fs/rename  from outside', '/fs/rename', {'from': '/etc/hosts', 'to': str(W / 'z')}, None, None, None),
            ('POST /fs/rename  to outside',  '/fs/rename', {'from': str(W / 'plain.txt'), 'to': '/etc/z'}, None, None, None),
            ('POST /fs/rename  bad path',    '/fs/rename', {'from': NUL, 'to': str(W / 'z')}, None, None, None),
            ('POST /fs/rename  missing',     '/fs/rename', {'from': str(W / 'no'), 'to': str(W / 'z')}, None, None, None),
            ('POST /fs/rename  a root',      '/fs/rename', {'from': str(W), 'to': str(W.parent / 'z')}, None, None, None),
            ('POST /fs/rename  exists',      '/fs/rename', {'from': str(W / 'plain.txt'), 'to': str(W / 'sub')}, None, None, None),
            ('POST /fs/rename  DENIED',      '/fs/rename', {'from': str(W / 'nowrite' / 'kid.txt'), 'to': str(W / 'm.txt')}, None, None, None),
            ('POST /fs/rename  INTO LOCKED', '/fs/rename', {'from': str(W / 'plain.txt'), 'to': str(W / 'nowrite' / 'x.txt')}, None, None, None),
            ('POST /fs/delete  bad json',    '/fs/delete', None, 'POST', b'{nope', None),
            ('POST /fs/delete  no path',     '/fs/delete', {}, None, None, None),
            ('POST /fs/delete  outside',     '/fs/delete', {'path': '/etc/hosts'}, None, None, None),
            ('POST /fs/delete  bad path',    '/fs/delete', {'path': NUL}, None, None, None),
            ('POST /fs/delete  missing',     '/fs/delete', {'path': str(W / 'no')}, None, None, None),
            ('POST /fs/delete  a root',      '/fs/delete', {'path': str(W)}, None, None, None),
            ('POST /fs/delete  DENIED',      '/fs/delete', {'path': str(W / 'nowrite' / 'kid.txt')}, None, None, None),
            ('POST /fs/delete  DENIED dir',  '/fs/delete', {'path': str(W / 'nowrite' / 'kiddir')}, None, None, None),
            ('GET  /terminal/nonce  origin', '/terminal/nonce', None, None, None, {'Origin': 'https://evil.example'}),
            ('GET  /terminal/spawn  bad cli', '/terminal/spawn?cli=zzz&cwd=' + Q(str(W)), None, None, None, None),
            ('GET  /terminal/spawn  no cwd', '/terminal/spawn?cli=claude', None, None, None, None),
            ('GET  /terminal/spawn  BAD CWD', '/terminal/spawn?cli=claude&cwd=' + Q(str(W / 'no')), None, None, None, None),
            ('GET  /terminal/spawn  no cli', '/terminal/spawn?cli=claude&cwd=' + Q(str(W)), None, None, None, None),
            ('GET  /terminal/pty    BAD CWD', '/terminal/pty?cli=claude&cwd=' + Q(str(W / 'no')), None, None, None, None),
            ('GET  /terminal/kill   no id',  '/terminal/kill', None, None, None, None),
            ('POST /terminal/stream bad json', '/terminal/stream', None, 'POST', b'{nope', None),
            ('POST /terminal/stream bad cli', '/terminal/stream', {'cli': 'zzz', 'cwd': str(W)}, None, None, None),
            ('POST /terminal/stream no cwd', '/terminal/stream', {'cli': 'claude'}, None, None, None),
            ('POST /terminal/stream BAD CWD', '/terminal/stream',
             {'cli': 'claude', 'cwd': str(W / 'no'), 'messages': [{'role': 'user', 'content': 'hi'}]}, None, None, None),
            ('POST /terminal/stream no prompt', '/terminal/stream', {'cli': 'claude', 'cwd': str(W)}, None, None, None),
            ('POST /terminal/stream no cli', '/terminal/stream',
             {'cli': 'claude', 'cwd': str(W), 'messages': [{'role': 'user', 'content': 'hi'}]}, None, None, None),
        ]
        ladder = []
        bad = []
        for label, path, payload, method, raw, headers in doors:
            s, b = req(base + path, payload, method, raw, headers)
            ladder.append((label, s, b))
            if s == 0:
                bad.append((label, 'no answer at all: ' + b[:60]))
                continue
            o = offences(b) if b.startswith('{') else []
            if o:
                bad.append((label, o))
        check('every /fs and /terminal door answers a sentence (%d driven)'
              % len(doors), not bad, bad[:4])

        # Three of the sites this hunt fixed put an errno in a 200 receipt, so
        # the doors that reach them must be shown to have REACHED them — a
        # clean 200 with an empty `skipped` would satisfy the invariant above
        # while exercising nothing. (`## 404`'s lesson, one step earlier: a
        # check that cannot fail is not a check.)
        _, cb = req(base + '/fs/collect?path=' + Q(str(W)))
        skipped = json.loads(cb).get('skipped') or []
        check('/fs/collect actually skipped an unreadable file', bool(skipped),
              'nothing was skipped — the 200-body errno path went untested')
        _, ub = req(base + '/fs/upload?path=' + Q(str(W / 'nowrite')),
                    None, None, MP, MPH)
        try:
            failed = json.loads(ub).get('failed') or json.loads(ub).get('errors') or []
        except Exception:
            failed = []
        check('/fs/upload actually failed a file into its receipt', bool(failed),
              'nothing failed — the 200-body errno path went untested: ' + ub[:120])
        for label, body in (('collect skipped', json.dumps(skipped)),
                            ('upload failed', json.dumps(failed))):
            o = offences('{"x": %s}' % body)
            check('the %s receipt carries no errno or path' % label, not o, o[:3])

        print('\n    the ladder, for the record:')
        for label, s, b in ladder:
            print('      %-34s -> %-3s %s' % (label, s, b[:74].replace('\n', ' ')))
    finally:
        kill()
        subprocess.run(['chmod', '-R', 'u+rwX', str(home)])


# ── round 4: the credential in another upstream ─────────────────────────────
def _verbose_handler(sort_keys):
    class H(http.server.BaseHTTPRequestHandler):
        """An upstream that quotes the request it turned down, headers and
        all. Not a strawman: echoing the offending request is a common debug
        shape, and the Authorization header travels with it."""
        def log_message(self, *a):
            pass

        def _answer(self):
            n = int(self.headers.get('content-length', 0) or 0)
            if n:
                self.rfile.read(n)
            body = json.dumps({'error': {
                'code': 401, 'message': 'Invalid API key',
                'request': {'path': self.path, 'headers': dict(self.headers)}}},
                sort_keys=sort_keys).encode()
            self.send_response(401)
            self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        do_GET = do_POST = do_PUT = do_DELETE = _answer
    return H


def credential():
    print('\nRound 4 — the other upstream that was relayed verbatim')
    for sort_keys in (True, False):
        up = http.server.ThreadingHTTPServer(('127.0.0.1', free_port()),
                                             _verbose_handler(sort_keys))
        threading.Thread(target=up.serve_forever, daemon=True).start()
        home = Path(tempfile.mkdtemp(prefix='hq-411-key-'))
        base, kill = boot(home, {
            'CAFRESOHQ_LMSTUDIO_URL': 'http://127.0.0.1:%d/v1' % up.server_address[1],
            'LMSTUDIO_API_KEY': FAKE_LM_KEY,
        })
        if not base:
            check('a real serve.py came up for the credential round', False)
            up.shutdown()
            continue
        try:
            s, b = req(base + '/agent/stream',
                       {'driver': 'lmstudio', 'prompt': 'hello'})
            o = offences(b, secrets=(FAKE_LM_KEY,))
            # The key must not be there whatever the upstream's key order.
            # Before the fix, sort_keys=True leaked it in full and
            # sort_keys=False missed by one character — `## 407`'s
            # /vault/open shape, which is a near-miss and not a defence.
            check('POST /agent/stream keeps the key out (upstream sort_keys=%s)'
                  % sort_keys, not o, '%s -> %s %s' % (o, s, b[:150]))
            print('      upstream sort_keys=%-5s -> %s %s'
                  % (sort_keys, s, b[:96].replace('\n', ' ')))
        finally:
            kill()
            up.shutdown()

    # And the sub-8-character hole in exporters._scrub, verified here rather
    # than inherited from `## 407`. It is real: a three-character key is left
    # alone by design, so that a one-character key cannot redact half a
    # sentence. What this round proves is that the hole no longer has a path
    # to the boss — the body is a composed sentence now, so no length of key
    # can ride an upstream body out through /agent/stream.
    up = http.server.ThreadingHTTPServer(('127.0.0.1', free_port()),
                                         _verbose_handler(True))
    threading.Thread(target=up.serve_forever, daemon=True).start()
    home = Path(tempfile.mkdtemp(prefix='hq-411-short-'))
    base, kill = boot(home, {
        'CAFRESOHQ_LMSTUDIO_URL': 'http://127.0.0.1:%d/v1' % up.server_address[1],
        'LMSTUDIO_API_KEY': 'abc',      # three characters: under _scrub's floor
    })
    try:
        if base:
            s, b = req(base + '/agent/stream', {'driver': 'lmstudio', 'prompt': 'x'})
            check('a key too short for _scrub still never reaches the body',
                  'abc' not in json.loads(b).get('error', ''), b[:150])
    finally:
        kill()
        up.shutdown()


# ── round 5: the transparent proxy, measured rather than assumed ────────────
def hermes_proxy():
    """serve.py's `_hermes_proxy` injects `Authorization: Bearer
    API_SERVER_KEY` and relays the gateway's body through untouched. That
    relay is the ROUTE'S PURPOSE — it is an OpenAI-compat pass-through the
    browser client parses — so it cannot be replaced by a refusal sentence
    the way the six vault doors and local_http.py could.

    MEASURED, not assumed: against the same echoing stand-in, POST
    /hermes/v1/chat/completions answers 401 with FAKE_HERMES_KEY in the body.
    So it leaks, and it leaks the key the route injects precisely so that —
    its own docstring — "the key never lives in the browser". The relay
    defeats the property the injection exists to provide.

    It is NOT fixed here, deliberately. The body is relayed by a streaming
    read1() loop so SSE passes through uncompressed; a key can straddle two
    chunks, so scrubbing it is not the small hunk this hunt is allowed to make
    in serve.py, and getting it wrong breaks every streaming reply in the
    office. Reported in `## 411` as EXPOSED for a human.

    What is asserted here is therefore the narrow, true thing: the gateway key
    never reaches a body through any door that is NOT the pass-through."""
    print('\nRound 5 — the transparent proxy, measured not assumed')
    up = http.server.ThreadingHTTPServer(('127.0.0.1', free_port()),
                                         _verbose_handler(True))
    threading.Thread(target=up.serve_forever, daemon=True).start()
    home = Path(tempfile.mkdtemp(prefix='hq-411-proxy-'))
    base, kill = boot(home, {
        'API_SERVER_KEY': FAKE_HERMES_KEY,
        'HERMES_API_HOST': '127.0.0.1',
        'HERMES_API_PORT': str(up.server_address[1]),
    }, hermes_stub=True)
    try:
        if not base:
            check('a real serve.py came up for the proxy round', False)
            return
        s, b = req(base + '/hermes/v1/chat/completions',
                   {'model': 'x', 'messages': [{'role': 'user', 'content': 'hi'}]})
        # This assertion is about the MEASUREMENT, not the result: a 501 means
        # #399's no-brain short-circuit answered and the proxy never dialled
        # the upstream, so any verdict read off that body would be a verdict
        # about a door that was never opened. The first run of this round did
        # exactly that and reported a clean proxy.
        check('round 5 actually reached the proxy (not #399\'s 501)',
              s != 501, 'got 501 — the stub hermes is missing from PATH')
        print('      POST /hermes/v1/chat/completions -> %s  '
              'gateway key in body: %s%s'
              % (s, FAKE_HERMES_KEY in b,
                 '   <-- EXPOSED, see #411 (not fixed here: streaming relay)'
                 if FAKE_HERMES_KEY in b else ''))
        # The doors that are NOT the pass-through must be clean regardless.
        for path in ('/hermes/trial-status', '/hermes/local-models?base_url=x'):
            s2, b2 = req(base + path)
            check('%s keeps the gateway key out' % path,
                  FAKE_HERMES_KEY not in b2, b2[:120])
    finally:
        kill()
        up.shutdown()


def main():
    rounds = int(os.environ.get('ROUNDS', '3'))
    for i in range(rounds):
        print('\n================ round %d/%d ================' % (i + 1, rounds))
        structural()
        live_doors()
        credential()
        hermes_proxy()
    print('\n' + ('FAILED: ' + ', '.join(sorted(set(FAILS))) if FAILS
                  else 'all checks passed'))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
