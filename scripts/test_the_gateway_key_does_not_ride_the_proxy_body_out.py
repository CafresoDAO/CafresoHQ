#!/usr/bin/env python3
"""`#416` — the pass-through that undoes its own reason for existing.

`serve.py`'s `_hermes_proxy` injects `Authorization: Bearer API_SERVER_KEY`
server-side and says why in its own docstring: *"so the key never lives in the
browser."*  It then relayed the gateway's response body through untouched, and
`#411` measured the consequence:

    POST /hermes/v1/chat/completions -> 401, gateway key in body: True

An upstream that quotes the request it turned down — a common debug shape,
and the Authorization header travels with it — hands the injected key straight
back to the browser the injection exists to keep it out of.

This suite pins the two halves of the fix and, more importantly, pins the two
things the fix must NOT cost.

  Round 0  `_SecretStream` driven directly at chunk sizes a TCP stack will
           not volunteer — one byte at a time upward.
  Round 1  the measured leak, at BOTH upstream key orders.  `#411` found the
           key one character outside a 300-slice on its first run and reported
           LEAKED=False; a near-miss is not a pass, so both orders are driven.
           Also asserts the round actually REACHED the proxy — `#399`'s 501
           no-brain short-circuit answers without opening a connection, and a
           verdict read off that body is a verdict about a door never opened.
  Round 2  THE STRADDLE.  A 200 stream that splits the key across two TCP
           writes, at every interior offset.  A scrubber without a carry-over
           buffer passes offset 0 and fails every other one.
  Round 3  streaming is still streaming.  `#399` took the office from a
           46-second first message to 25ms; a fix that buffers the body to
           scan it gives that back.  Measures first-byte time and counts the
           chunks the browser actually observes.
  Round 4  content integrity, including near-miss key prefixes parked exactly
           on a chunk boundary — the input that makes a carry-over buffer
           withhold bytes it must eventually emit.
  Round 5  the proxy's own two error bodies (`hermes: {last_err}`) obey §7.

Nothing here touches the mainnet, `main.mo`, or any II value.  PATH is pinned
to a scratch bin dir for the reason `#407` gave: `gateway_restart` is a bare
`Popen(['hermes','gateway','restart'])`, a plain PATH lookup NOT gated on
HERMES_HOME, so a run on a developer box must not be able to find their real
hermes.  Every key in this file is an obvious fake.
"""
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

# Obvious fakes. Length and shape match a real API_SERVER_KEY; the value does
# not exist anywhere. 40 chars, so the straddle round has 39 interior offsets.
FAKE_HERMES_KEY = 'hermesfakeserverkey00000000000000notreal'
FAKE_CLIENT_KEY = 'browserfakekey1111111111111111111notreal'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# ── §7's rule for anything a boss reads, identical to `#407`/`#411`'s ────────
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


def sentence_offences(body_text):
    """Judge every string in the body a boss can end up reading. `message` and
    `hint` are the prose `streamOpenAICompat` shows in place of the braces
    (claude-client.jsx, #399); `error` is the machine's word for the fault
    ('no_brain', 'gateway_refused') and reaches the screen through every
    surface that has not learnt the #399 preference yet, so it is held to the
    same rule rather than exempted. `#411`'s invariant walked the whole
    document for exactly this reason."""
    out = []
    try:
        doc = json.loads(body_text)
    except Exception:
        return [('<not json>', body_text[:120])]
    if not isinstance(doc, dict):
        return [('<not an object>', body_text[:120])]
    for k in ('error', 'message', 'hint'):
        v = doc.get(k)
        if isinstance(v, str):
            for o in judge(v, (FAKE_HERMES_KEY, FAKE_CLIENT_KEY)):
                out.append((k, o))
        elif v is not None:
            # An upstream's `{"error": {...}}` object relayed through is the
            # exact shape a sentence is not, and the first fire test proved a
            # judge that only reads strings waves it through.
            out.append((k, 'is a %s, not a sentence' % type(v).__name__))
    return out


# ── plumbing ────────────────────────────────────────────────────────────────
def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def req(url, payload=None, method=None, headers=None):
    h = {'content-type': 'application/json'}
    h.update(headers or {})
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(url, data=data, headers=h,
                               method=method or ('POST' if data else 'GET'))
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:                                   # noqa: BLE001
        return 0, str(e)


def stream_req(base, path, payload, timeout=30):
    """Raw-socket POST that records WHEN each byte arrived. Returns
    (status, body_bytes, chunks) where chunks is [(seconds_since_send, len)].
    urllib buffers, which is exactly the thing round 3 must be able to see."""
    host, port = base.split('//', 1)[1].split(':')
    data = json.dumps(payload).encode()
    s = socket.create_connection((host, int(port)), timeout=timeout)
    s.sendall(b'POST ' + path.encode() + b' HTTP/1.1\r\nHost: ' + base.split('//', 1)[1].encode()
              + b'\r\nContent-Type: application/json\r\nConnection: close\r\n'
              + b'Content-Length: ' + str(len(data)).encode() + b'\r\n\r\n' + data)
    t0 = time.time()
    s.settimeout(timeout)
    buf = b''
    chunks = []
    while True:
        try:
            part = s.recv(65536)
        except socket.timeout:
            break
        if not part:
            break
        chunks.append((time.time() - t0, len(part)))
        buf += part
    s.close()
    head, _, body = buf.partition(b'\r\n\r\n')
    try:
        status = int(head.split(b' ', 2)[1])
    except Exception:
        status = 0
    # Header bytes land in chunk 0; report body chunks only when the head and
    # the first body bytes arrived together.
    return status, body, chunks


def boot(home, extra_env=None, hermes_stub=True):
    """A real serve.py on a scratch HOME with a pinned bin dir first on PATH.

    `hermes_stub` puts an INERT `hermes` in that dir — that is the pin, not a
    hole in it. Two things need it. `gateway_can_appear()` is
    `bool(resolve('hermes'))`, so without a binary the proxy answers `#399`'s
    501 and never dials the upstream: every round would measure the
    short-circuit. And a real `hermes gateway restart` must be unreachable
    from a test on a developer's machine."""
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


class _Stand:
    """A stand-in `hermes gateway` under the test's control. Each round hands
    it a `plan(handler) -> None` that writes whatever that round needs."""

    def __init__(self, plan):
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *a):
                pass

            def _go(self):
                n = int(self.headers.get('content-length', 0) or 0)
                if n:
                    self.rfile.read(n)
                outer.seen.append(dict(self.headers))
                plan(self)
            do_GET = do_POST = do_PUT = do_DELETE = _go

        self.seen = []
        self.srv = http.server.ThreadingHTTPServer(('127.0.0.1', free_port()), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    @property
    def port(self):
        return self.srv.server_address[1]

    def stop(self):
        self.srv.shutdown()


def _proxy_env(stand):
    return {'API_SERVER_KEY': FAKE_HERMES_KEY,
            'HERMES_API_HOST': '127.0.0.1',
            'HERMES_API_PORT': str(stand.port)}


def _write_split(h, body, at, status=200, ctype='text/event-stream'):
    """Send `body` as TWO TCP writes with a real gap between them, so the
    proxy's read1() loop is guaranteed to see two chunks."""
    h.send_response(status)
    h.send_header('content-type', ctype)
    h.send_header('content-length', str(len(body)))
    h.send_header('connection', 'close')
    h.end_headers()
    h.wfile.write(body[:at])
    h.wfile.flush()
    time.sleep(0.05)
    h.wfile.write(body[at:])
    h.wfile.flush()


# ── round 0: the sieve itself, at chunk sizes no server will ever produce ───
def sieve_unit():
    """`_SecretStream` driven directly, because the live rounds can only offer
    the chunk boundaries a real TCP stack happens to hand them. Here every
    boundary is chosen on purpose, down to one byte at a time — which is the
    case a carry-over of len(secret)-1 exists for and the case a naive
    per-chunk `replace` cannot survive."""
    print('\nRound 0 — the sieve, at every chunk size from one byte up')
    sys.path.insert(0, str(ROOT))
    try:
        import serve                                          # noqa: PLC0415
    except Exception as e:                                    # noqa: BLE001
        check('serve.py imports so _SecretStream can be driven', False, e)
        return
    key = FAKE_HERMES_KEY.encode()
    body = b'lead-' + b'C' * 50 + key + b'-middle-' + key + b'-tail'
    bad = []
    for size in list(range(1, 12)) + [17, 39, 40, 41, 97, 4096]:
        s = serve._SecretStream(key)
        out = b''
        for i in range(0, len(body), size):
            out += s.feed(body[i:i + size])
        out += s.flush()
        if key in out:
            bad.append(size)
        if b'lead-' not in out or not out.endswith(b'-tail'):
            bad.append(('shape', size))
    check('no chunk size lets the key through', not bad, bad[:6])
    # A body with no secret in it must come out byte-identical AND, the part
    # that matters for #399, must not be held back at all.
    clean = b'data: {"delta":"hello world"}\n\n'
    s = serve._SecretStream(key)
    first = s.feed(clean)
    check('a chunk with nothing to hide is emitted whole, immediately',
          first == clean and s.flush() == b'', len(first))
    # The one input that MUST be held: a chunk ending in a prefix of the key.
    s = serve._SecretStream(key)
    held = s.feed(b'xx' + key[:10])
    check('a chunk ending in a key prefix holds back exactly that prefix',
          held == b'xx' and s.feed(key[10:]) + s.flush() == b'<redacted>',
          (held, 'the carry-over is not doing its job'))
    # And an innocent prefix must come back out unchanged at EOF.
    s = serve._SecretStream(key)
    check('an innocent prefix is emitted, not swallowed, at EOF',
          s.feed(b'yy' + key[:10]) + s.flush() == b'yy' + key[:10],
          'an innocent prefix was eaten at EOF')


# ── round 1: the measured leak ──────────────────────────────────────────────
def echoing_refusal():
    print('\nRound 1 — the upstream that quotes the request it turned down')
    for sort_keys in (True, False):
        def plan(h, _sk=sort_keys):
            body = json.dumps({'error': {
                'code': 401, 'message': 'Invalid API key',
                'request': {'path': h.path, 'headers': dict(h.headers)}}},
                sort_keys=_sk).encode()
            h.send_response(401)
            h.send_header('content-type', 'application/json')
            h.send_header('content-length', str(len(body)))
            h.send_header('connection', 'close')
            h.end_headers()
            h.wfile.write(body)

        stand = _Stand(plan)
        home = Path(tempfile.mkdtemp(prefix='hq-416-echo-'))
        base, kill = boot(home, _proxy_env(stand))
        try:
            if not base:
                check('a real serve.py came up (sort_keys=%s)' % sort_keys, False)
                continue
            s, b = req(base + '/hermes/v1/chat/completions',
                       {'model': 'x', 'messages': [{'role': 'user', 'content': 'hi'}]},
                       headers={'Authorization': 'Bearer ' + FAKE_CLIENT_KEY})
            # Not a verdict about a door that was never opened (#411's round 5
            # got #399's 501 on its first run and reported a clean proxy).
            check('sort_keys=%s reached the proxy, not #399\'s 501' % sort_keys,
                  s != 501, 'got 501 — the stub hermes is missing from PATH')
            check('sort_keys=%s the upstream really echoed our Authorization'
                  % sort_keys,
                  any('Bearer ' + FAKE_HERMES_KEY in ' '.join(hd.values())
                      for hd in stand.seen),
                  'the stand-in never saw the injected key — round is vacuous')
            print('      POST /hermes/v1/chat/completions -> %s  '
                  'gateway key in body: %s' % (s, FAKE_HERMES_KEY in b))
            check('sort_keys=%s the gateway key stays out of the body' % sort_keys,
                  FAKE_HERMES_KEY not in b,
                  'LEAKED %s in: %s' % (FAKE_HERMES_KEY, b[:200]))
            check('sort_keys=%s the upstream status survives' % sort_keys,
                  s == 401, s)
            off = sentence_offences(b)
            check('sort_keys=%s what the boss reads is one §7 sentence' % sort_keys,
                  not off, off[:3])
            # The refusal half on its own. With the sieve alone the key is
            # gone but the gateway's own words ("Invalid API key", the echoed
            # request) still reach the screen; the fix's argument is that a
            # refusal is a diagnostic and is NOT relayed, so pin that too —
            # a fire test that reverted only this guard found the suite
            # still green until this check existed.
            check('sort_keys=%s the upstream\'s own words never reach the boss'
                  % sort_keys,
                  'Invalid API key' not in b and '"request"' not in b
                  and '<redacted>' not in b,
                  'relayed upstream body: ' + b[:160])
        finally:
            kill()
            stand.stop()


# ── round 2: THE STRADDLE ───────────────────────────────────────────────────
def straddle():
    print('\nRound 2 — the key split across two chunks, at every interior offset')
    lead = b'data: {"choices":[{"delta":{"content":"' + b'A' * 300
    tail = b'"}}]}\n\ndata: [DONE]\n\n'
    payload = lead + FAKE_HERMES_KEY.encode() + tail
    split_at = len(lead)                       # first byte of the key

    # Every interior offset of the key, plus the two boundaries. A scrubber
    # with no carry-over passes 0 and len(key) and fails all 39 between.
    offsets = list(range(0, len(FAKE_HERMES_KEY) + 1))
    leaked_at = []
    ran = 0

    _cursor = [0]
    stand = _Stand(lambda h: _write_split(h, payload, split_at + _cursor[0]))
    home = Path(tempfile.mkdtemp(prefix='hq-416-straddle-'))
    base, kill = boot(home, _proxy_env(stand))
    try:
        if not base:
            check('a real serve.py came up for the straddle round', False)
            return
        for k in offsets:
            _cursor[0] = k
            st, body, chunks = stream_req(
                base, '/hermes/v1/chat/completions',
                {'model': 'x', 'messages': [{'role': 'user', 'content': 'hi'}]})
            if st == 501:
                check('straddle round reached the proxy, not #399\'s 501', False, st)
                return
            ran += 1
            if FAKE_HERMES_KEY.encode() in body:
                leaked_at.append(k)
            if k == 0:
                # Vacuity guard: the stream must actually have carried the
                # surrounding payload, or "no key found" means nothing.
                check('the straddle stream really flowed (lead text arrived)',
                      b'A' * 300 in body, body[:120])
        check('all %d split offsets were driven' % len(offsets),
              ran == len(offsets), ran)
        print('      split offsets driven: %d   leaked at: %s'
              % (ran, leaked_at if leaked_at else 'none'))
        check('the key survives no split offset', not leaked_at,
              'LEAKED %s when split after byte(s) %s of the key'
              % (FAKE_HERMES_KEY, leaked_at[:6]))
    finally:
        kill()
        stand.stop()


# ── round 3: streaming is still streaming ───────────────────────────────────
def streaming_latency():
    print('\nRound 3 — first-token time and chunk count (#399 bought 25ms)')
    events = [b'data: {"choices":[{"delta":{"content":"tok%d"}}]}\n\n' % i
              for i in range(8)]

    def plan(h):
        h.send_response(200)
        h.send_header('content-type', 'text/event-stream')
        h.send_header('connection', 'close')
        h.end_headers()
        for e in events:
            h.wfile.write(e)
            h.wfile.flush()
            time.sleep(0.08)
        h.wfile.write(b'data: [DONE]\n\n')
        h.wfile.flush()

    stand = _Stand(plan)
    home = Path(tempfile.mkdtemp(prefix='hq-416-stream-'))
    base, kill = boot(home, _proxy_env(stand))
    try:
        if not base:
            check('a real serve.py came up for the streaming round', False)
            return
        st, body, chunks = stream_req(
            base, '/hermes/v1/chat/completions',
            {'model': 'x', 'messages': [{'role': 'user', 'content': 'hi'}]})
        check('streaming round reached the proxy, not #399\'s 501', st != 501, st)
        first = chunks[0][0] if chunks else 99.0
        last = chunks[-1][0] if chunks else 99.0
        print('      status %s   first byte %.0fms   last byte %.0fms   '
              'chunks %d   bytes %d' % (st, first * 1000, last * 1000,
                                        len(chunks), len(body)))
        check('every token arrived', body.count(b'"content":"tok') == 8,
              body[:200])
        # The point of the round. A proxy that buffers the whole body to scan
        # it delivers ONE chunk at the end; a streaming one delivers many, and
        # the first long before the last.
        check('the browser sees the stream in pieces, not one buffered blob',
              len(chunks) >= 4, '%d chunks — the body was buffered' % len(chunks))
        check('first byte beats the last by the upstream\'s own pacing',
              first < last - 0.3, 'first %.0fms last %.0fms' % (first * 1000,
                                                               last * 1000))
        check('first byte is fast (well inside #399\'s budget)', first < 1.0,
              '%.0fms' % (first * 1000))
    finally:
        kill()
        stand.stop()


# ── round 4: content integrity, including near-miss prefixes ────────────────
def integrity():
    print('\nRound 4 — a body that is NOT the key comes through byte-identical')
    # The nastiest input for a carry-over buffer: a proper prefix of the key
    # sitting exactly at the end of a chunk, which must be withheld and then
    # emitted unchanged when the next chunk proves it was innocent.
    near = FAKE_HERMES_KEY[:len(FAKE_HERMES_KEY) - 1].encode()
    payload = (b'data: {"a":"' + b'B' * 100 + near + b'"}\n\n'
               b'data: {"b":"' + near + b'-and-more"}\n\ndata: [DONE]\n\n')
    split_at = payload.index(near) + len(near)   # boundary right after the prefix

    stand = _Stand(lambda h: _write_split(h, payload, split_at))
    home = Path(tempfile.mkdtemp(prefix='hq-416-integrity-'))
    base, kill = boot(home, _proxy_env(stand))
    try:
        if not base:
            check('a real serve.py came up for the integrity round', False)
            return
        st, body, chunks = stream_req(
            base, '/hermes/v1/chat/completions',
            {'model': 'x', 'messages': [{'role': 'user', 'content': 'hi'}]})
        check('integrity round reached the proxy, not #399\'s 501', st != 501, st)
        check('a near-miss prefix on a chunk boundary relays byte-identical',
              body == payload,
              'got %d of %d bytes' % (len(body), len(payload)))
    finally:
        kill()
        stand.stop()


# ── round 5: the proxy's own error bodies ───────────────────────────────────
def own_errors():
    print('\nRound 5 — the proxy\'s own refusals are sentences too')
    home = Path(tempfile.mkdtemp(prefix='hq-416-dead-'))
    dead = free_port()                       # nothing is listening there
    base, kill = boot(home, {'API_SERVER_KEY': FAKE_HERMES_KEY,
                             'HERMES_API_HOST': '127.0.0.1',
                             'HERMES_API_PORT': str(dead)})
    try:
        if not base:
            check('a real serve.py came up for the dead-gateway round', False)
            return
        t0 = time.time()
        s, b = req(base + '/hermes/v1/chat/completions',
                   {'model': 'x', 'messages': [{'role': 'user', 'content': 'hi'}]})
        check('a dead gateway still answers the retryable 502', s == 502, (s, b[:120]))
        off = sentence_offences(b)
        check('the dead-gateway body is a §7 sentence', not off, off[:3])
        print('      dead gateway -> %s in %.1fs   %s' % (s, time.time() - t0, b[:150]))
    finally:
        kill()


def main():
    rounds = int(os.environ.get('ROUNDS', '1'))
    for i in range(rounds):
        print('\n================ round %d/%d ================' % (i + 1, rounds))
        sieve_unit()
        echoing_refusal()
        straddle()
        streaming_latency()
        integrity()
        own_errors()
    print('\n' + ('FAILED: ' + ', '.join(sorted(set(FAILS))) if FAILS
                  else 'all checks passed'))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
