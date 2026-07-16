#!/usr/bin/env python3
"""Search-worker tests — answer salvage + the LLM call's timeout discipline.

These cover the two things a future edit is most likely to break silently:

1. `_sw_parse_analysis` salvage. The worker streams `{"summary", "notes"}` with
   summary FIRST on purpose, so a stream the deadline cuts short still yields a
   complete summary. Because library entries are permanent and public, salvage
   refuses to publish a half-thought — it needs a whole sentence. Every case
   below is a shape a real truncated stream produces.
2. `_sw_chat` / `_sw_llm` bounds. The canister's claim lease is 240s and is not
   renewable, so blowing the budget silently discards the work AND burns one of
   the job's 3 attempts. These assert we always come back in time, salvage what
   arrived, and degrade to sources-only rather than publishing garbage.

No network and no GPU: a fake OpenAI-compatible endpoint with scriptable
pathologies stands in for the gateway. Run: python3 scripts/test_search_worker.py
"""
import contextlib
import io
import json
import tempfile
import os
import sys
import threading
import time
import http.server
import socketserver

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('API_SERVER_KEY', 'x')      # make _sw_hermes_key() truthy
import serve  # noqa: E402

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# ── 1. salvage parser ────────────────────────────────────────────────────────
FULL = ('{"summary": "ICP is a blockchain [1]. It runs canisters [2].", '
        '"notes": {"1": "Overview of ICP", "2": "Canister docs", "3": "Tokenomics"}}')


def test_parse():
    print('salvage parser')
    s, n = serve._sw_parse_analysis(FULL)
    check('well-formed summary', s == 'ICP is a blockchain [1]. It runs canisters [2].', s)
    check('well-formed notes', n == {0: 'Overview of ICP', 1: 'Canister docs', 2: 'Tokenomics'}, n)

    # The money case: the deadline lands inside notes → summary intact.
    cut = FULL[:FULL.index('"2": "Canister docs"') + len('"2": "Canister d')]
    s, n = serve._sw_parse_analysis(cut)
    check('cut mid-notes keeps whole summary', s == 'ICP is a blockchain [1]. It runs canisters [2].', s)
    check('cut mid-notes keeps landed notes', n == {0: 'Overview of ICP'}, n)

    s, n = serve._sw_parse_analysis('{"summary": "ICP is a blockchain [1]. It runs can')
    check('cut mid-summary trims to sentence', s == 'ICP is a blockchain [1].', s)
    check('cut mid-summary drops notes', n == {}, n)

    # Permanent + public: a half-thought is worse than an honest sources-only entry.
    check('half-sentence refused', serve._sw_parse_analysis('{"summary": "ICP is a bloc') == ('', {}))
    check('tiny scrap refused', serve._sw_parse_analysis('{"summary": "ICP i') == ('', {}))
    check('one-word sentence refused', serve._sw_parse_analysis('{"summary": "Yes. And the res') == ('', {}))
    check('broken json never published raw', serve._sw_parse_analysis('{"summary": ') == ('', {}))
    check('no-summary json never published raw',
          serve._sw_parse_analysis('{"notes": {"1": "x"}') == ('', {}))

    # …but a model that deliberately writes one terse complete sentence keeps it.
    s, _ = serve._sw_parse_analysis('{"summary": "Yes [1].", "notes": {"1": "sho')
    check('complete terse summary kept', s == 'Yes [1].', s)

    s, _ = serve._sw_parse_analysis('{"summary": "Caf\\u00e9 study [1]. More \\u00e9')
    check('truncated \\uXXXX escape survives', s == 'Café study [1].', s)

    tricky = '{"summary": "He said \\"a}b\\" and {c} [1].", "notes": {"1": "x}y"}}'
    s, n = serve._sw_parse_analysis(tricky)
    check('escaped quotes/braces not confused', s == 'He said "a}b" and {c} [1].', s)
    check('brace inside a note value', n == {0: 'x}y'}, n)
    s, _ = serve._sw_parse_analysis(tricky[:tricky.index('"notes"') + 12])
    check('truncated tricky summary', s == 'He said "a}b" and {c} [1].', s)

    check('empty notes ignores trailing keys',
          serve._sw_parse_analysis('{"summary": "S [1].", "notes": {}, "other": "x"')[1] == {})
    # A model answering in prose instead of JSON is legitimate — keep its text.
    check('plain prose degrades intact', serve._sw_parse_analysis('just some prose') == ('just some prose', {}))


# ── 2. fake gateway ──────────────────────────────────────────────────────────
BODY = ('{"summary": "ICP is a blockchain that runs canister smart contracts [1]. '
        'It offers web-speed finality [2].", "notes": {"1": "Overview of the protocol", '
        '"2": "Benchmarks and finality", "3": "Tokenomics detail"}}')
MODE, TOKEN_SLEEP, STALL_AT, BLOCK_SECS = 'slow', 0.0, 3, 75
REQS = []        # every request body the fake saw, in order
HITS = {}        # port -> request count (proves which path was used)


class _H(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or '{}')
        REQS.append(req)
        port = self.server.server_address[1]
        HITS[port] = HITS.get(port, 0) + 1
        if MODE == 'reject_response_format' and 'response_format' in req:
            self.send_error(400, 'unknown param response_format'); return
        if MODE == 'reject_stream_options' and 'stream_options' in req:
            self.send_error(400, 'unknown param'); return
        if MODE == 'reject_stream' and req.get('stream'):
            self.send_error(400, 'stream unsupported'); return
        if MODE in ('blocking', 'blocking_slow') or not req.get('stream'):
            if MODE == 'blocking_slow':
                time.sleep(BLOCK_SECS)      # real blocking gateways withhold headers
            b = json.dumps({'model': 'fake-1', 'choices': [{'message': {'content': BODY}}],
                            'usage': {'total_tokens': 1234}}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Transfer-Encoding', 'chunked')
        self.end_headers()

        def sse(o):
            d = ('data: ' + json.dumps(o) + '\n\n').encode()
            self.wfile.write(('%x\r\n' % len(d)).encode() + d + b'\r\n')
            self.wfile.flush()
        try:
            for i in range(0, len(BODY), 6):
                if MODE == 'stall' and i // 6 == STALL_AT:
                    time.sleep(90); return
                sse({'model': 'fake-1', 'choices': [{'delta': {'content': BODY[i:i + 6]}}]})
                time.sleep(TOKEN_SLEEP)
            if MODE != 'no_usage':
                sse({'model': 'fake-1', 'choices': [], 'usage': {'total_tokens': 1234}})
            self.wfile.write(b'0\r\n\r\n')
            self.wfile.flush()
        except Exception:
            pass


class _S(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


R = [{'title': 'ICP Overview', 'url': 'https://a.com/x',
      'description': 'The Internet Computer is a blockchain. It runs canisters at web speed. Filler about weather.'},
     {'title': 'Benchmarks', 'url': 'https://b.org/y',
      'description': 'Finality benchmarks for ICP. Query calls resolve in milliseconds.'},
     {'title': 'Tokenomics', 'url': 'https://c.net/z',
      'description': 'ICP token supply and staking mechanics explained in detail here.'}]


def _use_direct(port):
    """Route _sw_llm's DIRECT path at the fake, and make the gateway unreachable
    so anything that reaches it fails loudly rather than passing by accident."""
    import night_runner as nr
    serve._sw_backend = lambda: nr.Backend(
        provider='lmstudio', raw_provider='lmstudio', model='fake-1',
        url='http://127.0.0.1:%d/v1/chat/completions' % port,
        headers={'Content-Type': 'application/json'}, key='', local=True)
    serve.HERMES_HOST, serve.HERMES_PORT = '127.0.0.1', 9


def _use_gateway(port):
    """No direct backend resolvable (e.g. an anthropic operator) → gateway."""
    serve._sw_backend = lambda: None
    serve.HERMES_HOST, serve.HERMES_PORT = '127.0.0.1', port


def _mode(m):
    """Change the fake's personality AND forget the memoised ladder rung.

    _SW_CAPS is sticky per-url per-process on purpose — a real backend doesn't
    change which params it accepts mid-run, so paying for that discovery once is
    the whole point. This test does change it, so it has to say so; otherwise a
    rung learned in the reject_stream case silently rewrites the next case."""
    global MODE
    MODE = m
    serve._SW_CAPS.clear()


def test_llm(port, label):
    """The SAME assertion body, run once per path. These only ever assert on
    _sw_llm's return, so both routes must satisfy them identically."""
    global MODE, TOKEN_SLEEP, STALL_AT
    print('llm bounds + salvage [%s]' % label)
    serve._SW_IDLE_TIMEOUT = 3.0          # keep the stall cases quick

    # The deadline lands mid-generation → salvage rather than lose everything.
    _mode('slow'); TOKEN_SLEEP = 0.25
    t = time.monotonic()
    s, _m, _n, tok = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 4)
    el = time.monotonic() - t
    check('deadline salvages a real summary', bool(s) and 'blockchain' in s, repr(s)[:70])
    check('deadline is respected', el < 7, '%.1fs' % el)
    check('salvage still counts tokens (delta fallback)', tok > 0, tok)

    # Stalled backend: abort on the idle bound, don't burn the whole budget.
    _mode('stall'); TOKEN_SLEEP, STALL_AT = 0.01, 3
    t = time.monotonic()
    s, _m, _n, _tok = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 120)
    el = time.monotonic() - t
    check('idle stall aborts fast', el < 10, '%.1fs' % el)
    check('idle stall on a scrap publishes nothing', s == '', repr(s)[:40])
    STALL_AT = 14
    s, _m, _n, _tok = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 120)
    check('idle stall past a sentence salvages it', bool(s) and s.endswith('.'), repr(s)[:60])
    STALL_AT = 3

    _mode('slow'); TOKEN_SLEEP = 0.0
    s, _m, n, tok = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('full stream parses', 'canister smart contracts [1]' in s, repr(s)[:60])
    check('full stream keeps every note', len(n) == 3, n)
    check('full stream uses reported usage', tok == 1234, tok)

    _mode('blocking')
    s, _m, _n, tok = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('backend ignoring stream still works', 'canister smart contracts [1]' in s and tok == 1234, tok)

    _mode('reject_stream_options')
    s, _m, _n, _t = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('4xx on stream_options climbs down', 'canister smart contracts [1]' in s, repr(s)[:40])

    _mode('reject_stream')
    s, _m, _n, _t = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('4xx on stream falls back to blocking', 'canister smart contracts [1]' in s, repr(s)[:40])

    _mode('no_usage')
    _s, _m, _n, tok = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('missing usage chunk falls back to delta count', tok > 0 and tok != 1234, tok)

    # Regression: a BLOCKING backend withholds headers until it's done, so the
    # open must cover the whole generation. Bounding it by TTFT killed a healthy
    # 75s answer at exactly 60s with budget to spare.
    _mode('blocking_slow')
    t = time.monotonic()
    s, _m, _n, _t2 = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 180)
    el = time.monotonic() - t
    check('blocking backend slower than TTFT still succeeds',
          'canister smart contracts [1]' in s, '%.0fs %r' % (el, s[:30]))
    check('blocking backend was actually waited for', el > 70, '%.1fs' % el)

    # Everything dead: sources + graph are still worth fulfilling, so degrade quietly.
    _mode('slow')
    import night_runner as nr
    serve._sw_backend = lambda: nr.Backend('lmstudio', 'lmstudio', 'fake-1',
                                           'http://127.0.0.1:9/v1/chat/completions',
                                           {'Content-Type': 'application/json'}, '', True)
    serve.HERMES_PORT = 9
    t = time.monotonic()
    out = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 30)
    check('dead backend degrades to empty', out == ('', '', {}, 0), out)
    check('dead backend fails fast', time.monotonic() - t < 15)


def test_ordering(direct_port, gw_port):
    """The one test that catches a regression back to gateway-first. The gateway
    is ~13k prompt tokens per answer and ignores max_tokens/model — if a direct
    backend resolves, nothing should reach it."""
    global MODE
    print('routing')
    MODE = 'slow'
    HITS.clear()
    import night_runner as nr
    serve._sw_backend = lambda: nr.Backend(
        'lmstudio', 'lmstudio', 'fake-1',
        'http://127.0.0.1:%d/v1/chat/completions' % direct_port,
        {'Content-Type': 'application/json'}, '', True)
    serve.HERMES_HOST, serve.HERMES_PORT = '127.0.0.1', gw_port
    s, _m, _n, _t = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('direct path answered', bool(s))
    check('direct backend was called', HITS.get(direct_port, 0) > 0, HITS)
    check('gateway saw ZERO requests when a direct backend exists',
          HITS.get(gw_port, 0) == 0, HITS)

    # An operator we cannot resolve directly (e.g. anthropic — no
    # _PROVIDER_ENDPOINTS entry) must still get answers. Do not delete this path.
    HITS.clear()
    _use_gateway(gw_port)
    s, _m, _n, _t = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('unresolvable backend still answers via the gateway', bool(s))
    check('gateway was used as the fallback', HITS.get(gw_port, 0) > 0, HITS)


def test_payload(port):
    """What we actually send. These params were no-ops on the gateway; going
    direct is the whole point, so pin them."""
    global MODE
    print('request payload')
    MODE = 'slow'
    _use_direct(port)
    REQS.clear()
    serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    req = REQS[0]
    check('max_tokens is sent and is the new default', req.get('max_tokens') == 700, req.get('max_tokens'))
    check('model is the resolved backend model', req.get('model') == 'fake-1', req.get('model'))
    rf = req.get('response_format') or {}
    props = (((rf.get('json_schema') or {}).get('schema') or {}).get('properties') or {})
    check('response_format is a strict json_schema', (rf.get('json_schema') or {}).get('strict') is True, rf)
    # Salvage rescues a truncated answer only because summary is emitted first.
    check('summary precedes notes in the schema', list(props.keys()) == ['summary', 'notes'], list(props.keys()))
    check('a note per source is structurally REQUIRED, not requested',
          (props.get('notes') or {}).get('required') == ['1', '2', '3'],
          (props.get('notes') or {}).get('required'))


def test_schema_climbdown(port):
    """A backend that hates response_format must still answer — and must not
    re-pay for that discovery on every job."""
    global MODE
    print('response_format climb-down')
    MODE = 'reject_response_format'
    _use_direct(port)
    serve._SW_CAPS.clear()
    REQS.clear()
    s, _m, _n, _t = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('still answers without response_format', 'canister smart contracts [1]' in s, repr(s)[:50])
    check('it did climb down', any('response_format' not in r for r in REQS), len(REQS))
    n_first = len(REQS)
    REQS.clear()
    serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('the rung is memoised — no wasted 4xx on the next job',
          all('response_format' not in r for r in REQS), 'first=%d then=%d' % (n_first, len(REQS)))


def test_trial_notice(port, tmp):
    """Uncapped is a DECISION, so pin it: the notice fires, and nothing is
    metered. If someone later adds a bump here, this test fails on purpose."""
    global MODE
    print('trial key notice')
    MODE = 'slow'
    _use_direct(port)
    serve._trial_state = lambda: {'active': True, 'provider': 'openrouter'}
    serve._trial_usage = lambda p: (3, 25)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    out = buf.getvalue()
    check('says it is spending the shared trial key', 'SHARED TRIAL key' in out, out[:90])
    check('says search is not metered', 'NOT metered' in out, out[:90])
    before = serve._night_load('trial-usage.json', {})
    with contextlib.redirect_stdout(io.StringIO()):
        serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('search does NOT consume the trial cap (decided: uncapped)',
          serve._night_load('trial-usage.json', {}) == before)
    serve._trial_state = lambda: {'active': False}


def test_chip_honesty(port, tmpdir):
    """The chip is written to a PERMANENT PUBLIC on-chain entry, so it must name
    the model that actually decoded.

    The trap this pins: the gateway ECHOES the requested model back while running
    config.yaml's. An echo can never disagree with the request, so a naive
    "reported != requested" check passes while the chip lies. On the gateway path
    the config is the truth, not the response."""
    global MODE
    print('chip honesty')
    MODE = 'slow'
    serve._SW_CAPS.clear()
    cfg = os.path.join(tmpdir, 'config.yaml')
    with open(cfg, 'w') as f:
        f.write('model:\n  default: real/loaded-model\n  provider: lmstudio\n'
                '  base_url: http://127.0.0.1:%d/v1\napprovals:\n  mode: manual\n' % port)
    serve._hermes_home = lambda: tmpdir
    os.environ['WORKER_MODEL'] = 'ghost/not-loaded'      # the fake echoes 'fake-1'

    # Gateway path: the fake echoes back whatever we send, exactly like hermes.
    _use_gateway(port)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _s, m, _n, _t = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('gateway chip does NOT parrot the request', 'ghost' not in m, m)
    check('gateway chip reports the config model (what really ran)', m == 'real/loaded-model', m)
    check('the discrepancy is logged', 'asked for ghost/not-loaded' in buf.getvalue(), buf.getvalue()[:80])

    # Direct path: the backend genuinely runs what it says, so believe it.
    _use_direct(port)
    _s, m, _n, _t = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('direct chip trusts the backend it actually called', m == 'fake-1', m)
    del os.environ['WORKER_MODEL']


def test_focus():
    print('focus mode')
    f = serve._sw_focus(R[0]['description'], 'what is ICP', max_chars=60)
    check('trims to query-relevant sentences', len(f) <= 60 and 'weather' not in f, repr(f))
    short = 'Already short.'
    check('short text untouched', serve._sw_focus(short, 'anything') == short)


def main():
    srv = _S(('127.0.0.1', 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    # A second fake so routing can be proven by which port got hit.
    gw = _S(('127.0.0.1', 0), _H)
    threading.Thread(target=gw.serve_forever, daemon=True).start()
    gw_port = gw.server_address[1]

    test_parse()
    # The same bounds/salvage body must hold on BOTH routes.
    _use_direct(port)
    test_llm(port, 'direct')
    serve._SW_CAPS.clear()
    _use_gateway(port)
    test_llm(port, 'gateway fallback')
    serve._SW_CAPS.clear()
    test_ordering(port, gw_port)
    test_payload(port)
    test_schema_climbdown(port)
    test_trial_notice(port, None)
    test_chip_honesty(port, tempfile.mkdtemp())
    test_focus()
    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'search-worker: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
