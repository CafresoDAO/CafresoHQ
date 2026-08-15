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

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The worker code moved out of serve.py into the standalone service — these
# tests now run against the copy that actually ships.
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, 'search_worker_service'))
import worker as serve  # noqa: E402

# Never let _sw_model()/_sw_backend() reach for the on-chain operator config.
serve._operator_config = lambda: {}

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
    """Route _sw_llm's direct path at the fake."""
    serve._sw_backend = lambda: serve._Backend(
        url='http://127.0.0.1:%d/v1/chat/completions' % port,
        headers={'Content-Type': 'application/json'},
        model='fake-1', provider='lmstudio')


def _use_none():
    """No backend configured — the worker must degrade to sources-only.
    (The old in-process copy fell back to a co-located hermes gateway here;
    the standalone service deliberately has no gateway tier.)"""
    serve._sw_backend = lambda: None


def _mode(m):
    """Change the fake's personality AND forget the memoised ladder rung.

    _SW_CAPS is sticky per-url per-process on purpose — a real backend doesn't
    change which params it accepts mid-run, so paying for that discovery once is
    the whole point. This test does change it, so it has to say so; otherwise a
    rung learned in the reject_stream case silently rewrites the next case."""
    global MODE
    MODE = m
    serve._SW_CAPS.clear()


class _TickClock:
    """Deterministic stand-in for the worker's `time` module.

    monotonic() advances a fixed tick per CALL, so "elapsed time" becomes a
    function of the code path alone — how many times the worker consulted the
    clock — never of machine load. Everything else delegates to the real
    module. Installed as `serve.time` for one call and restored; the fake
    gateway and the test's own measurements import their own `time` and never
    see it."""

    def __init__(self, tick, base=1000.0):
        self.now = base
        self.tick = tick

    def monotonic(self):
        self.now += self.tick
        return self.now

    def __getattr__(self, name):
        return getattr(time, name)


def test_llm(port, label):
    """The SAME assertion body, run once per path. These only ever assert on
    _sw_llm's return, so both routes must satisfy them identically."""
    global MODE, TOKEN_SLEEP, STALL_AT
    print('llm bounds + salvage [%s]' % label)
    serve._SW_IDLE_TIMEOUT = 3.0          # keep the stall cases quick

    # The deadline lands mid-generation → salvage rather than lose everything.
    #
    # On a FAKE clock, deliberately. The first cut of this case raced real
    # sleeps against a real deadline: TOKEN_SLEEP=0.25 streamed the first
    # complete sentence at ~3s and the deadline fired at 4s, so the whole
    # check hung on ~1s of scheduler slack. On 2026-08-15 it failed inside a
    # full runner pass while a local LLM inference had the box, then went
    # 5/5 standalone — and the service's copy of this suite had ALREADY been
    # padded 4s→5s once for the same reason. Widening a real-time margin
    # trains everyone to re-run rather than read; removing real time from
    # the fixture is the fix.
    #
    # So: the worker's `time` is swapped for a per-call tick clock and the
    # fake streams with NO sleeps. _sw_chat consults the clock at two
    # _sw_left calls, once per readline at the loop top, and once more at
    # the first delta — a fixed sequence for a fixed byte stream — so the
    # loop-top `monotonic() > deadline` break crosses after the same read
    # every run, regardless of load. Measured sweep (2026-08-15): any tick
    # in 0.06–0.14 lands the cut after the first sentence is complete
    # (chunk 12) and before the stream ends (chunk 35); 0.10 is the middle
    # of that plateau, cutting at ~40 clock reads. A worker refactor would
    # have to nearly halve or nearly double the clock reads on this path to
    # escape the window — and if one does, this fails the same way every
    # run, which is the point.
    _mode('slow'); TOKEN_SLEEP = 0.0
    clk = _TickClock(tick=0.10)
    dl = clk.now + 4
    serve.time = clk
    try:
        s, _m, n, tok = serve._sw_llm('what is ICP', R, deadline=dl)
    finally:
        serve.time = time
    check('deadline salvages a real summary', bool(s) and 'blockchain' in s, repr(s)[:70])
    # The stream must really have been CUT, not merely finished fast: a
    # truncated stream never carries the final usage chunk (so tokens fall
    # back to the delta count, never 1234) and loses at least one note.
    # These two carry the job the old wall-clock bound did — with no real
    # sleeps left, a deleted deadline break makes the stream complete in
    # milliseconds and the salvage check alone would still see 'blockchain'.
    check('...and the stream really was cut short', tok != 1234 and len(n) < 3,
          'tok=%s notes=%d — a full stream means the deadline never fired' % (tok, len(n)))
    # The worker came back on its FIRST look at the clock past the deadline —
    # the return-in-time promise, stated in clock reads instead of seconds.
    check('deadline is respected', dl < clk.now <= dl + 2 * clk.tick,
          'clock at return %.2f vs deadline %.2f' % (clk.now, dl))
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
    serve._sw_backend = lambda: serve._Backend(
        url='http://127.0.0.1:9/v1/chat/completions',
        headers={'Content-Type': 'application/json'},
        model='fake-1', provider='lmstudio')
    t = time.monotonic()
    out = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 30)
    check('dead backend degrades to empty', out == ('', '', {}, 0), out)
    check('dead backend fails fast', time.monotonic() - t < 15)


def test_ordering(direct_port, other_port):
    """Exactly one backend, called directly — and NOTHING else gets traffic.
    The second fake exists purely to prove no stray tier (the old in-process
    copy had a gateway fallback) sneaks back in."""
    global MODE
    print('routing')
    MODE = 'slow'
    HITS.clear()
    _use_direct(direct_port)
    s, _m, _n, _t = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('direct path answered', bool(s))
    check('direct backend was called', HITS.get(direct_port, 0) > 0, HITS)
    check('no other endpoint saw traffic', HITS.get(other_port, 0) == 0, HITS)

    # No backend at all → sources-only, quickly and without publishing garbage.
    HITS.clear()
    _use_none()
    out = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('no backend degrades to sources-only', out == ('', '', {}, 0), out)
    check('and makes zero network calls', not HITS, HITS)


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


def test_chip_honesty(port, tmpdir):
    """The chip is written to a PERMANENT PUBLIC on-chain entry, so it must name
    the model that actually decoded.

    A direct backend genuinely runs what it reports, so the chip believes the
    response — but a mismatch against the requested model must be LOGGED, not
    silently papered over."""
    global MODE
    print('chip honesty')
    MODE = 'slow'
    serve._SW_CAPS.clear()
    serve.WORKER_MODEL = 'ghost/not-loaded'      # the fake reports 'fake-1'
    _use_direct(port)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _s, m, _n, _t = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('chip trusts the backend it actually called', m == 'fake-1', m)
    check('the discrepancy is logged', 'asked for ghost/not-loaded' in buf.getvalue(), buf.getvalue()[:80])
    serve.WORKER_MODEL = ''
    _s, m, _n, _t = serve._sw_llm('what is ICP', R, deadline=time.monotonic() + 60)
    check('chip reports the model when nothing was pinned', m == 'fake-1', m)


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
    _use_direct(port)
    test_llm(port, 'direct')
    serve._SW_CAPS.clear()
    test_ordering(port, gw_port)
    test_payload(port)
    test_schema_climbdown(port)
    test_chip_honesty(port, tempfile.mkdtemp())
    test_focus()
    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'search-worker: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
