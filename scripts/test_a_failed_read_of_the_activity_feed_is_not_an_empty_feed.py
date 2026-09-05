#!/usr/bin/env python3
"""One bad read at 3am erased the office's activity history.

serve.py's `_night_post_activity` runs after every unattended night shift,
with no browser open. It reads the shared activity feed, puts its own line
on the front, and writes the whole thing back:

    PUT /hq/state/activity   [entry] + cur[:199]

`cur` came from a GET, and any answer that was not a 200 was turned into
`[]`. So a 500 from the file read, a 503 from the state-dir guard, or a
timed-out self-call did not skip the ticker line -- it wrote a feed of ONE
over up to 200 rows of everything the office had done. Every deliverable,
every snag, every approval, gone, replaced by a single cheerful "night
shift: 3 note(s)".

The boss wakes up, opens the office, and the history starts at 3am with
the night shift reporting success. Nothing says a read failed, because from
the runner's side nothing did: it asked, it got an answer it did not check,
and it believed it. Same family as ## 205. and ## 302. -- the unattended
shift treating a bad read as a good one -- except this one is not merely a
false report, it is deletion.

The `null` case is genuinely different and must keep working: _hq_handler
answers a missing state file with 200 + null on purpose ("nothing saved yet
is a NORMAL state"), and a first night really is writing into an empty
feed.

Driven, not grepped: a real HTTP server on localhost, reached through
night_runner's own `_self_call`, with the real `_night_post_activity`
lifted out of serve.py and executed.
"""
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import night_runner as _nr   # noqa: E402

failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}{(' -- ' + detail) if detail else ''}")
        failures.append(label)


def strip_py_comments(src):
    """Drop # comments outside strings, keeping newlines.

    The fix is explained in a comment that names the very bug the sweep at
    the end looks for; without this, that comment passes the test for it.
    """
    out, i, n, q = [], 0, len(src), None
    while i < n:
        c = src[i]
        if q:
            out.append(c)
            if c == '\\' and i + 1 < n:
                out.append(src[i + 1]); i += 2; continue
            if src.startswith(q, i):
                out.append(src[i + 1:i + len(q)]); i += len(q); q = None; continue
            i += 1
            continue
        if src.startswith('"""', i) or src.startswith("'''", i):
            q = src[i:i + 3]; out.append(q); i += 3; continue
        if c in '"\'':
            q = c; out.append(c); i += 1; continue
        if c == '#':
            j = src.find('\n', i); j = n if j == -1 else j
            out.append(' ' * (j - i)); i = j; continue
        out.append(c); i += 1
    return ''.join(out)


SERVE = open(os.path.join(ROOT, 'serve.py')).read()


def lift(src, name):
    """Lift a top-level def, verbatim, from the real serve.py."""
    m = re.search(r'^def %s\(.*?(?=^\S)' % re.escape(name), src,
                  re.M | re.S)
    if not m:
        raise AssertionError('could not lift ' + name)
    return m.group(0)


# ── a real feed server, with a switch for how the read goes ────────────────
STORED = {'value': None}
STATE = {'get_status': 200, 'puts': []}


class Feed(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        s = STATE['get_status']
        body = json.dumps(STORED['value']).encode() if s == 200 else b'{"error":"boom"}'
        self.send_response(s)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self):
        n = int(self.headers.get('content-length', 0) or 0)
        raw = self.rfile.read(n)
        STATE['puts'].append(raw)
        try:
            STORED['value'] = json.loads(raw.decode('utf-8'))
        except Exception:
            pass
        self.send_response(200)
        self.send_header('Content-Length', '2')
        self.end_headers()
        self.wfile.write(b'{}')


def rows(n):
    return [{'id': 'act_%d' % i, 'ts': 1000 + i, 'text': 'row %d' % i}
            for i in range(n)]


def main():
    print("1. the real function, lifted from serve.py")
    try:
        src = lift(SERVE, '_night_post_activity')
    except AssertionError as e:
        print(f"FAILED: {e}")
        return 1
    check("lifted the real _night_post_activity",
          "'/hq/state/activity'" in src and "'PUT'" in src)

    srv = HTTPServer(('127.0.0.1', 0), Feed)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = 'http://127.0.0.1:%d' % srv.server_address[1]
    ctx = _nr.NightContext(base)

    ns = {
        'json': json, 'time': __import__('time'),
        '_night_browser_active': lambda: False,
        '_night_ctx': lambda: ctx,
    }
    # The function does `import night_runner as _nr` itself; ROOT is on the
    # path, so that resolves to the real module and the calls below go out
    # over real HTTP to the server above.
    exec(compile(src, 'serve.py:_night_post_activity', 'exec'), ns)
    post = ns['_night_post_activity']
    run = {'id': 'run_9', 'agentId': 'a1', 'agentName': 'Llama',
           'topic': 'overnight sweep', 'writes': ['n1', 'n2', 'n3']}

    try:
        print("2. a healthy read: the line lands and the history survives")
        STORED['value'] = rows(200)
        STATE['get_status'] = 200
        STATE['puts'] = []
        post(run)
        cur = STORED['value']
        check("the night line was written", len(STATE['puts']) == 1)
        check("...on the FRONT of the feed",
              isinstance(cur, list) and cur and cur[0].get('action') == 'night',
              repr(cur[0]) if isinstance(cur, list) and cur else repr(cur))
        check("...naming the run so it cannot be filed twice",
              isinstance(cur, list) and cur[0].get('id') == 'act_night_run_9')
        check("...and the 200 rows behind it are still there (capped at 199)",
              isinstance(cur, list) and len(cur) == 200
              and cur[1]['id'] == 'act_0', str(len(cur) if isinstance(cur, list) else cur))

        print("3. THE DEFECT: the read fails and the history must survive")
        for status in (500, 503, 404, 403):
            STORED['value'] = rows(200)
            STATE['get_status'] = status
            STATE['puts'] = []
            post(run)
            kept = STORED['value']
            check(f"a {status} on the read does not overwrite the feed",
                  isinstance(kept, list) and len(kept) == 200
                  and kept[0]['id'] == 'act_0',
                  ('feed is now %r' % (kept if not isinstance(kept, list)
                                       else '%d rows, first %s' % (len(kept), kept[0].get('id')))))
            check(f"...and nothing at all is written on a {status}",
                  not STATE['puts'],
                  repr(STATE['puts'][:1]))

        print("4. a first night still writes into a genuinely empty feed")
        # _hq_handler answers a MISSING state file with 200 + null, on
        # purpose. That is the one case where "no rows" is the truth, and
        # refusing to write it would silence the ticker forever.
        STORED['value'] = None
        STATE['get_status'] = 200
        STATE['puts'] = []
        post(run)
        cur = STORED['value']
        check("null (nothing saved yet) is treated as an empty feed",
              isinstance(cur, list) and len(cur) == 1
              and cur[0].get('action') == 'night', repr(cur))

        print("5. a body we cannot read is not a feed we may replace")
        STORED['value'] = {'oops': 'this is not a list'}
        STATE['get_status'] = 200
        STATE['puts'] = []
        post(run)
        check("a non-list body is left alone rather than overwritten",
              STORED['value'] == {'oops': 'this is not a list'}
              and not STATE['puts'], repr(STORED['value']))

        print("6. a live browser still owns the feed")
        ns['_night_browser_active'] = lambda: True
        exec(compile(src, 'serve.py:_night_post_activity', 'exec'), ns)
        STORED['value'] = rows(3)
        STATE['puts'] = []
        ns['_night_post_activity'](run)
        check("nothing is written while somebody is watching",
              not STATE['puts'] and len(STORED['value']) == 3)
    finally:
        srv.shutdown()

    print("7. the shape of the fix, in source")
    body = strip_py_comments(src)
    check("comment stripping bit", '#' not in body.replace('#!', ''),
          'otherwise the sweep below reads the explanation, not the code')
    check("the status is checked before anything is parsed or written",
          re.search(r'if\s+s\s*!=\s*200', body) is not None)
    check("...and a non-200 no longer becomes an empty list",
          not re.search(r'if\s+s\s*==\s*200\s+else\s+\[\]', body))

    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures[:6]))
        return 1
    print("PASS: a failed read of the activity feed is not an empty feed")
    return 0


if __name__ == '__main__':
    sys.exit(main())
