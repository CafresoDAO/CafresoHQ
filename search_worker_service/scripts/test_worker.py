#!/usr/bin/env python3
"""search-worker tests — answer salvage + the LLM call's timeout discipline.

Ported from scripts/test_search_worker.py (the version that tested serve.py's
in-monolith worker code) for the standalone search_worker_service/worker.py.
Dropped along with the port: everything that tested the Hermes-agent-gateway
fallback path and the shared-trial-key notice — neither exists in the
standalone service (see worker.py's module docstring for why). Everything
else — the salvage parser, the direct-backend dispatch, payload shape, the
response_format climb-down, focus-mode trimming — is unchanged behavior and
ported as directly as possible.

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
pathologies stands in for the backend. Run:
  python3 search_worker_service/scripts/test_worker.py
"""
import json
import sys
import os
import threading
import time
import http.server
import socketserver

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import worker  # noqa: E402

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
    s, n = worker._sw_parse_analysis(FULL)
    check('well-formed summary', s == 'ICP is a blockchain [1]. It runs canisters [2].', s)
    check('well-formed notes', n == {0: 'Overview of ICP', 1: 'Canister docs', 2: 'Tokenomics'}, n)

    cut = FULL[:FULL.index('"2": "Canister docs"') + len('"2": "Canister d')]
    s, n = worker._sw_parse_analysis(cut)
    check('cut mid-notes keeps whole summary', s == 'ICP is a blockchain [1]. It runs canisters [2].', s)
    check('cut mid-notes keeps landed notes', n == {0: 'Overview of ICP'}, n)

    s, n = worker._sw_parse_analysis('{"summary": "ICP is a blockchain [1]. It runs can')
    check('cut mid-summary trims to sentence', s == 'ICP is a blockchain [1].', s)
    check('cut mid-summary drops notes', n == {}, n)

    check('half-sentence refused', worker._sw_parse_analysis('{"summary": "ICP is a bloc') == ('', {}))
    check('tiny scrap refused', worker._sw_parse_analysis('{"summary": "ICP i') == ('', {}))
    check('one-word sentence refused', worker._sw_parse_analysis('{"summary": "Yes. And the res') == ('', {}))
    check('broken json never published raw', worker._sw_parse_analysis('{"summary": ') == ('', {}))
    check('no-summary json never published raw',
          worker._sw_parse_analysis('{"notes": {"1": "x"}') == ('', {}))

    s, _ = worker._sw_parse_analysis('{"summary": "Yes [1].", "notes": {"1": "sho')
    check('complete terse summary kept', s == 'Yes [1].', s)

    s, _ = worker._sw_parse_analysis('{"summary": "Caf\\u00e9 study [1]. More \\u00e9')
    check('truncated \\uXXXX escape survives', s == 'Café study [1].', s)

    tricky = '{"summary": "He said \\"a}b\\" and {c} [1].", "notes": {"1": "x}y"}}'
    s, n = worker._sw_parse_analysis(tricky)
    check('escaped quotes/braces not confused', s == 'He said "a}b" and {c} [1].', s)
    check('brace inside a note value', n == {0: 'x}y'}, n)
    s, _ = worker._sw_parse_analysis(tricky[:tricky.index('"notes"') + 12])
    check('truncated tricky summary', s == 'He said "a}b" and {c} [1].', s)

    check('empty notes ignores trailing keys',
          worker._sw_parse_analysis('{"summary": "S [1].", "notes": {}, "other": "x"')[1] == {})
    check('plain prose degrades intact', worker._sw_parse_analysis('just some prose') == ('just some prose', {}))


# ── 2. fake backend ──────────────────────────────────────────────────────────
BODY = ('{"summary": "ICP is a blockchain that runs canister smart contracts [1]. '
        'It offers web-speed finality [2].", "notes": {"1": "Overview of the protocol", '
        '"2": "Benchmarks and finality", "3": "Tokenomics detail"}}')
MODE, TOKEN_SLEEP, STALL_AT, BLOCK_SECS = 'slow', 0.0, 3, 75
REQS = []        # every request body the fake saw, in order
HITS = {}        # port -> request count


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
                time.sleep(BLOCK_SECS)
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
    """Point _sw_backend() at the fake — the ONLY dispatch path in the
    standalone service (see worker.py's module docstring: no agent-gateway
    fallback tier exists here)."""
    worker._sw_backend = lambda: worker._Backend(
        url='http://127.0.0.1:%d/v1/chat/completions' % port,
        headers={'Content-Type': 'application/json'}, model='fake-1', provider='direct')


def _use_unconfigured():
    """Nothing resolvable — WORKER_BACKEND_URL unset and no operator-published
    default. Replaces the old test's 'unresolvable backend' gateway-fallback
    case: there is no fallback here, so this must degrade to sources-only."""
    worker._sw_backend = lambda: None


def _mode(m):
    global MODE
    MODE = m
    worker._SW_CAPS.clear()


def test_llm(port):
    global MODE, TOKEN_SLEEP, STALL_AT
    print('llm bounds + salvage')
    worker._SW_IDLE_TIMEOUT = 3.0
    _use_direct(port)

    # 5s, not the original 4s: this standalone process has far fewer background
    # threads than serve.py's monolith (no PTY reaper, night-shift, weather/gap/
    # news crons all in the same process), which measurably shifts scheduler
    # wakeup timing on a tight deadline — confirmed via an A/B run of the SAME
    # dispatch code in-process-with-serve.py vs standalone. The 3s-to-first-
    # complete-sentence math this fixture is built on doesn't change; only the
    # margin does, from ~1s to ~2s, which is what actually needed the padding.
    _mode('slow'); TOKEN_SLEEP = 0.25
    t = time.monotonic()
    s, _m, _n, tok = worker._sw_llm('what is ICP', R, deadline=time.monotonic() + 5)
    el = time.monotonic() - t
    check('deadline salvages a real summary', bool(s) and 'blockchain' in s, repr(s)[:70])
    check('deadline is respected', el < 8, '%.1fs' % el)
    check('salvage still counts tokens (delta fallback)', tok > 0, tok)

    _mode('stall'); TOKEN_SLEEP, STALL_AT = 0.01, 3
    t = time.monotonic()
    s, _m, _n, _tok = worker._sw_llm('what is ICP', R, deadline=time.monotonic() + 120)
    el = time.monotonic() - t
    check('idle stall aborts fast', el < 10, '%.1fs' % el)
    check('idle stall on a scrap publishes nothing', s == '', repr(s)[:40])
    STALL_AT = 14
    s, _m, _n, _tok = worker._sw_llm('what is ICP', R, deadline=time.monotonic() + 120)
    check('idle stall past a sentence salvages it', bool(s) and s.endswith('.'), repr(s)[:60])
    STALL_AT = 3

    _mode('slow'); TOKEN_SLEEP = 0.0
    s, _m, n, tok = worker._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('full stream parses', 'canister smart contracts [1]' in s, repr(s)[:60])
    check('full stream keeps every note', len(n) == 3, n)
    check('full stream uses reported usage', tok == 1234, tok)

    _mode('blocking')
    s, _m, _n, tok = worker._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('backend ignoring stream still works', 'canister smart contracts [1]' in s and tok == 1234, tok)

    _mode('reject_stream_options')
    s, _m, _n, _t = worker._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('4xx on stream_options climbs down', 'canister smart contracts [1]' in s, repr(s)[:40])

    _mode('reject_stream')
    s, _m, _n, _t = worker._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('4xx on stream falls back to blocking', 'canister smart contracts [1]' in s, repr(s)[:40])

    _mode('no_usage')
    _s, _m, _n, tok = worker._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('missing usage chunk falls back to delta count', tok > 0 and tok != 1234, tok)

    _mode('blocking_slow')
    t = time.monotonic()
    s, _m, _n, _t2 = worker._sw_llm('what is ICP', R, deadline=time.monotonic() + 180)
    el = time.monotonic() - t
    check('blocking backend slower than TTFT still succeeds',
          'canister smart contracts [1]' in s, '%.0fs %r' % (el, s[:30]))
    check('blocking backend was actually waited for', el > 70, '%.1fs' % el)

    # No backend configured at all: sources + graph are still worth
    # fulfilling, so degrade quietly rather than raising.
    _mode('slow')
    _use_unconfigured()
    t = time.monotonic()
    out = worker._sw_llm('what is ICP', R, deadline=time.monotonic() + 30)
    check('unconfigured backend degrades to empty', out == ('', '', {}, 0), out)
    check('unconfigured backend fails fast', time.monotonic() - t < 15)


def test_no_gateway_fallback(port):
    """The standalone service has exactly one dispatch tier. Confirm that
    when no backend resolves, nothing is silently reached anywhere else —
    the direct-only claim in worker.py's module docstring, pinned."""
    global MODE
    print('routing (single-tier by design)')
    MODE = 'slow'
    HITS.clear()
    _use_direct(port)
    s, _m, _n, _t = worker._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('direct path answered', bool(s))
    check('direct backend was called', HITS.get(port, 0) > 0, HITS)

    HITS.clear()
    _use_unconfigured()
    s, _m, _n, _t = worker._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('nothing configured -> empty answer, not an exception', s == '')
    check('nothing configured -> zero requests sent anywhere', sum(HITS.values()) == 0, HITS)


def test_payload(port):
    global MODE
    print('request payload')
    MODE = 'slow'
    _use_direct(port)
    REQS.clear()
    worker._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    req = REQS[0]
    check('max_tokens is sent and is the new default', req.get('max_tokens') == 700, req.get('max_tokens'))
    check('model is the resolved backend model', req.get('model') == 'fake-1', req.get('model'))
    rf = req.get('response_format') or {}
    props = (((rf.get('json_schema') or {}).get('schema') or {}).get('properties') or {})
    check('response_format is a strict json_schema', (rf.get('json_schema') or {}).get('strict') is True, rf)
    check('summary precedes notes in the schema', list(props.keys()) == ['summary', 'notes'], list(props.keys()))
    check('a note per source is structurally REQUIRED, not requested',
          (props.get('notes') or {}).get('required') == ['1', '2', '3'],
          (props.get('notes') or {}).get('required'))


def test_schema_climbdown(port):
    global MODE
    print('response_format climb-down')
    MODE = 'reject_response_format'
    _use_direct(port)
    worker._SW_CAPS.clear()
    REQS.clear()
    s, _m, _n, _t = worker._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('still answers without response_format', 'canister smart contracts [1]' in s, repr(s)[:50])
    check('it did climb down', any('response_format' not in r for r in REQS), len(REQS))
    n_first = len(REQS)
    REQS.clear()
    worker._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('the rung is memoised — no wasted 4xx on the next job',
          all('response_format' not in r for r in REQS), 'first=%d then=%d' % (n_first, len(REQS)))


def test_chip_honesty(port):
    """The chip is written to a PERMANENT PUBLIC on-chain entry, so it must
    name the model that actually decoded. Only the direct-path half of the
    original test applies here — the gateway-echo-vs-config-truth half tested
    a path that no longer exists (see worker.py's module docstring)."""
    global MODE
    print('chip honesty')
    MODE = 'slow'
    worker._SW_CAPS.clear()
    os.environ['WORKER_MODEL'] = 'ghost/not-loaded'   # the fake echoes 'fake-1'
    _use_direct(port)
    _s, m, _n, _t = worker._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('direct chip trusts the backend it actually called', m == 'fake-1', m)
    del os.environ['WORKER_MODEL']


def test_focus():
    print('focus mode')
    f = worker._sw_focus(R[0]['description'], 'what is ICP', max_chars=60)
    check('trims to query-relevant sentences', len(f) <= 60 and 'weather' not in f, repr(f))
    short = 'Already short.'
    check('short text untouched', worker._sw_focus(short, 'anything') == short)


def main():
    srv = _S(('127.0.0.1', 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]

    test_parse()
    test_llm(port)
    worker._SW_CAPS.clear()
    test_no_gateway_fallback(port)
    test_payload(port)
    test_schema_climbdown(port)
    test_chip_honesty(port)
    test_focus()
    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'search-worker (standalone): all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
