#!/usr/bin/env python3
"""#348. A 429's `Retry-After` must survive the trip out to the office's own UI.

`#341` took the whole `access-control-*` family away from the upstream, because
who may read this office's answers is the OFFICE's decision. Correct, and it
took one thing too many with it. `Access-Control-Allow-Origin` says WHO may
read; `Access-Control-Expose-Headers` says WHICH HEADERS. `_cors` re-made the
first decision and never made the second, so a cross-origin reader was left
with the six CORS-safelisted response headers and nothing else -- and three
headers the office's own client reads are outside that six:

  * `Retry-After` -- claude-client.jsx's `_retryDelayMs` honours it on a 429
    ("it knows better than we do") rather than guessing. EVERY LLM stream
    funnels through that helper.
  * `X-File-Mtime` / `X-File-Hash` -- fsReadText's conflict metadata, which is
    the whole reason the Workspace editor reads /fs/file instead of FILE_READ.

Measured BEFORE the fix, against a real serve.py with a stub answering 429 the
way a throttled provider does, from the allowlisted CROSS-origin the
ai.cafreso.com -> hq.cafreso.com split is what `_app_origins` exists for:

    POST /lmstudio/chat/completions   Origin: https://ai.cafreso.com
      -> 429
      -> Retry-After: 42
      -> Access-Control-Allow-Origin: https://ai.cafreso.com
      -> Access-Control-Allow-Credentials: true
      -> and NO Access-Control-Expose-Headers at all

So the header is on the wire and the browser hands back null for it. The office
had been told exactly how long to wait and threw the number away, falling back
to jittered exponential backoff. Before `#341` the upstream's own
`Access-Control-Expose-Headers: Retry-After` rode through the relay loop and
the header was readable -- the fix that stopped an upstream voting on WHO also
dropped its vote on WHICH, and nothing took over the second decision.

Section C is the half that decides whether the fix is right rather than merely
generous: exposing a header must not hand a stranger's tab anything, so the
origin that gets no ACAO must get no expose list either.

Stands up its own stub upstream on a private port and points
CAFRESOHQ_LMSTUDIO_URL at it, so it never touches a real LM Studio.
"""
import http.client
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}{(' -- ' + detail) if detail else ''}")
        failures.append(label)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def request(port, method, path, body=None, headers=None):
    """(status, body, headers-lowercased). Raw http.client, NOT urllib, so the
    Host header stays exactly what the caller wrote."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        conn.request(method, path, body=body, headers=dict(headers or {}))
        r = conn.getresponse()
        return (r.status,
                r.read().decode("utf-8", "replace"),
                {k.lower(): v for k, v in r.getheaders()})
    finally:
        conn.close()


class StubThrottled:
    """A provider that is rate-limiting and says for how long. It ALSO sends
    its own permissive Access-Control-Expose-Headers, the way a real one does
    -- that is what used to carry Retry-After through, and `#341` is right to
    drop it. The office has to say it itself now."""

    def __init__(self):
        self.port = free_port()

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _go(self):
                n = int(self.headers.get("Content-Length", 0) or 0)
                if n:
                    self.rfile.read(n)
                out = b'{"error":"rate limited"}'
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", "42")
                self.send_header("X-File-Mtime", "1700000000")
                self.send_header("Access-Control-Allow-Origin",
                                 self.headers.get("Origin", "*"))
                self.send_header("Access-Control-Expose-Headers", "Retry-After")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            do_GET = do_POST = do_OPTIONS = _go

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", self.port), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class Server:
    """serve.py on a private port, default (unconfigured) posture."""

    def __init__(self, upstream_port):
        self.port = free_port()
        self.state_dir = tempfile.mkdtemp(prefix="cafresohq-348-")
        env = dict(os.environ)
        env.pop("CAFRESOHQ_API_KEY", None)
        env.update({
            "CAFRESOHQ_HQ_STATE_DIR": self.state_dir,
            "PORT": str(self.port),
            "CAFRESOHQ_LMSTUDIO_URL": f"http://127.0.0.1:{upstream_port}/v1",
            "GAP_CRON": "0", "NEWS_CRON": "0", "TOPICS_CRON": "0",
        })
        self.proc = subprocess.Popen(
            [sys.executable, "serve.py"], cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def wait_ready(self):
        for _ in range(150):
            try:
                request(self.port, "GET", "/health")
                return True
            except Exception:
                if self.proc.poll() is not None:
                    return False
                time.sleep(0.1)
        return False

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        subprocess.run(["rm", "-rf", self.state_dir], check=False)


APP_ORIGIN = "https://ai.cafreso.com"      # in _app_origins' base set
EVIL = "https://evil.example"


def names(expose_value):
    return {n.strip().lower() for n in (expose_value or "").split(",") if n.strip()}


def main():
    up = StubThrottled()
    srv = Server(up.port)
    if not srv.wait_ready():
        up.close()
        print("serve.py never became ready", file=sys.stderr)
        return 1
    port = srv.port

    try:
        # ── A. the measurement from the docstring ────────────────────────
        st, _, h = request(port, "POST", "/lmstudio/chat/completions",
                           body="{}", headers={"Host": f"127.0.0.1:{port}",
                                               "Origin": APP_ORIGIN,
                                               "Content-Type": "application/json"})
        check("the throttled upstream's 429 reaches the caller", st == 429, str(st))
        check("Retry-After is on the wire", h.get("retry-after") == "42",
              repr(h.get("retry-after")))
        check("the allowlisted app origin may read the body at all",
              h.get("access-control-allow-origin") == APP_ORIGIN,
              repr(h.get("access-control-allow-origin")))
        exposed = names(h.get("access-control-expose-headers"))
        check("...and is told it may READ Retry-After",
              "retry-after" in exposed,
              "no expose list, so the browser hands _retryDelayMs null and it "
              "guesses instead of waiting the 42 seconds it was told")

        # ── B. the office says WHICH, not the upstream ───────────────────
        #
        # The stub sends its own expose list naming only Retry-After. If the
        # office were merely relaying it again, the other two would be absent
        # -- which is `#341` undone.
        check("X-File-Mtime is exposed too (fsReadText's conflict metadata)",
              "x-file-mtime" in exposed, sorted(exposed))
        check("X-File-Hash is exposed too", "x-file-hash" in exposed,
              sorted(exposed))
        st, _, hf = request(port, "GET", "/health",
                            headers={"Host": f"127.0.0.1:{port}",
                                     "Origin": APP_ORIGIN})
        check("the expose list is the office's, not any one upstream's "
              "(a route with no upstream sends it too)",
              "retry-after" in names(hf.get("access-control-expose-headers")),
              repr(hf.get("access-control-expose-headers")))

        # ── C. it widens nothing `#333`/`#341` closed ────────────────────
        st, _, he = request(port, "POST", "/lmstudio/chat/completions",
                            body="{}", headers={"Host": f"127.0.0.1:{port}",
                                                "Origin": EVIL,
                                                "Content-Type": "text/plain"})
        check("a visited page still cannot POST to the local model", st == 403,
              str(st))
        st, _, he = request(port, "GET", "/lmstudio/models",
                            headers={"Host": f"127.0.0.1:{port}",
                                     "Origin": EVIL})
        check("a visited page still gets no ACAO for the model roster",
              "access-control-allow-origin" not in he,
              repr(he.get("access-control-allow-origin")))
        check("...and no expose list either -- naming headers to an origin "
              "that may not read the reply is the same mistake one field over",
              "access-control-expose-headers" not in he,
              repr(he.get("access-control-expose-headers")))
        check("the upstream's OWN access-control-* is still dropped "
              "(`#341` intact)",
              "access-control-allow-credentials" not in he, sorted(he))

        # ── D. an ordinary public route is unchanged for a stranger ──────
        st, _, hp = request(port, "GET", "/health",
                            headers={"Host": f"127.0.0.1:{port}",
                                     "Origin": EVIL})
        check("/health stays readable by anyone (ACAO '*')",
              hp.get("access-control-allow-origin") == "*",
              repr(hp.get("access-control-allow-origin")))
        check("...and its expose list names headers literally, never '*' "
              "(a wildcard is ignored outright on the credentialed branch)",
              "*" not in (hp.get("access-control-expose-headers") or ""),
              repr(hp.get("access-control-expose-headers")))
    finally:
        srv.close()
        up.close()

    print()
    if failures:
        print("FAILED %d check(s): %s" % (len(failures), ", ".join(failures)))
        return 1
    print("a throttled upstream can still say how long to wait: all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
