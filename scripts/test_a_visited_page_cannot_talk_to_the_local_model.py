#!/usr/bin/env python3
"""#331. A page the tester merely had open must not be able to put a prompt to
the office's LOCAL model and read the answer.

`#321` put _state_change_gate in front of every POST/PUT/DELETE and derived its
route list from _KEY_PROTECTED_PREFIXES -- which is every dangerous route
do_POST names explicitly, and none of the one arm of do_POST that names
nothing. A path matching no `if` in do_POST falls through to self._route() and
is proxied verbatim to whatever ROUTES points at: LM Studio on 1234, Ollama on
11434. Those two prefixes are keyless BY DESIGN (the UI's own model-picker
fetches send no X-API-Key), so being off the key list is correct and being off
the gate list was not -- the gate inherited the wrong list.

Measured BEFORE the fix, against a default serve.py -- no CAFRESOHQ_API_KEY,
exactly what a beta tester runs -- with a stub model server behind /lmstudio/,
from Origin: https://evil.example with Content-Type: text/plain, a request any
web page can make with no preflight:

    POST /lmstudio/chat/completions {"messages":[{"role":"user",...}]}
      -> 200, the prompt arrived at the model server,
      -> and the reply came back with Access-Control-Allow-Origin: *,
         so the page could read it.

POST /tools/exec with the identical shape answered 403. Same server, same
request, four lines apart in do_POST.

That is a stranger's tab spending the tester's GPU on its own prompts, and
reading the completions back -- on a box whose local model is loaded precisely
because it is the one trusted with things that must not leave the house.

Section C is the half that decides whether the fix is right rather than merely
strict: the office's own model-picker, the phone on the LAN, and the night
runner's Origin-less self-calls all still reach the model.

The test stands up its own stub upstream on a private port and points
CAFRESOHQ_LMSTUDIO_URL at it, so it never touches a real LM Studio and passes
on a machine that has none.
"""
import http.client
import json
import os
import re
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
    """(status, body, headers). Raw http.client, NOT urllib: urllib rewrites
    the Host header from the URL, which would quietly turn every rebinding
    check below into a no-op."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        conn.request(method, path, body=body, headers=dict(headers or {}))
        r = conn.getresponse()
        return r.status, r.read().decode("utf-8", "replace"), dict(r.getheaders())
    finally:
        conn.close()


class StubModel:
    """Stands in for LM Studio. Records every prompt that actually reached it,
    which is the measurement that matters: a 403 the office answered itself is
    a very different thing from a 403 it answered after asking the model."""

    def __init__(self):
        self.port = free_port()
        self.prompts = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                outer.prompts.append(self.rfile.read(n).decode("utf-8", "replace"))
                out = json.dumps({"choices": [{"message": {
                    "role": "assistant", "content": "STUB-MODEL-COMPLETION"}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def do_OPTIONS(self):
                # do_OPTIONS proxies preflight straight through for a ROUTES
                # prefix, so the stub has to answer it the way a real model
                # server does -- otherwise the check below measures the
                # stub's missing handler, not the office's gate.
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", self.port), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class Server:
    """serve.py on a private port, default (unconfigured) posture, with the
    /lmstudio/ passthrough aimed at the stub above."""

    def __init__(self, upstream_port):
        self.port = free_port()
        self.state_dir = tempfile.mkdtemp(prefix="cafresohq-331-")
        env = dict(os.environ)
        env.pop("CAFRESOHQ_API_KEY", None)
        env.update({
            "CAFRESOHQ_HQ_STATE_DIR": self.state_dir,
            "PORT": str(self.port),
            "CAFRESOHQ_LMSTUDIO_URL": f"http://127.0.0.1:{upstream_port}/v1",
            "CAFRESOHQ_OLLAMA_URL": f"http://127.0.0.1:{upstream_port}/v1",
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


def main():
    model = StubModel()
    srv = Server(model.port)
    if not srv.wait_ready():
        model.close()
        print("serve.py never became ready", file=sys.stderr)
        return 1

    port = srv.port

    def ask(path, headers):
        """The attack request and the app's own request are byte-identical
        apart from the browser-supplied headers. That is the whole point."""
        before = len(model.prompts)
        payload = json.dumps({"model": "local",
                              "messages": [{"role": "user",
                                            "content": "WHO-IS-ASKING-331"}]})
        st, body, hdrs = request(port, "POST", path, payload, headers)
        return st, body, hdrs, len(model.prompts) > before

    try:
        # ---- A. plain cross-origin CSRF -----------------------------------
        print("A. a forged Origin cannot put a prompt to the local model")
        st, body, hdrs, reached = ask("/lmstudio/chat/completions", {
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://evil.example",
        })
        check("POST /lmstudio/ from an unknown Origin is refused",
              st == 403, f"got {st}")
        check("the prompt never reached the model server", not reached,
              "the office asked the model on a stranger's behalf")
        check("no completion is in the body",
              "STUB-MODEL-COMPLETION" not in body, body[:120])
        check("the refusal names the reason", "origin" in body.lower(), body[:120])

        st, _, _, reached = ask("/ollama/chat/completions", {
            "Content-Type": "text/plain",
            "Origin": "https://evil.example",
        })
        check("POST /ollama/ from an unknown Origin is refused too",
              st == 403 and not reached, f"got {st}")

        # ---- B. DNS rebinding ---------------------------------------------
        # Here the page IS same-origin with this server, so an Origin check
        # alone waves it through. What it cannot forge is the Host.
        print("B. a forged Host cannot put a prompt to the local model")
        st, _, _, reached = ask("/lmstudio/chat/completions", {
            "Content-Type": "application/json",
            "Host": f"evil.example:{port}",
        })
        check("a forged Host with NO Origin is refused",
              st == 403 and not reached, f"got {st}")

        st, _, _, reached = ask("/lmstudio/chat/completions", {
            "Content-Type": "application/json",
            "Host": f"evil.example:{port}",
            "Origin": f"http://evil.example:{port}",   # same-origin with itself
        })
        check("a rebound page that is same-origin WITH ITSELF is still refused",
              st == 403 and not reached, f"got {st}")

        # ---- C. the product still works -----------------------------------
        # A gate that locks out a legitimate caller is a wrong fix, not a
        # strict one. Each of these is a real way the office reaches a model.
        print("C. every legitimate caller still reaches the model")

        st, body, _, reached = ask("/lmstudio/chat/completions", {
            "Content-Type": "application/json",
            "Host": f"127.0.0.1:{port}",
            "Origin": f"http://127.0.0.1:{port}",
        })
        check("the office's own same-origin call still reaches the model",
              st == 200 and reached, f"got {st}")
        check("and reads the completion back",
              "STUB-MODEL-COMPLETION" in body, body[:120])

        st, _, _, reached = ask("/ollama/chat/completions", {
            "Content-Type": "application/json",
            "Host": f"localhost:{port}",
            "Origin": f"http://localhost:{port}",
        })
        check("http://localhost is the same office", st == 200 and reached,
              f"got {st}")

        # The LAN/mobile URL the startup banner prints -- in nobody's
        # allowlist, and it is the phone.
        st, _, _, reached = ask("/lmstudio/chat/completions", {
            "Content-Type": "application/json",
            "Host": f"10.0.0.131:{port}",
            "Origin": f"http://10.0.0.131:{port}",
        })
        check("the LAN/mobile IP-literal URL still reaches the model",
              st == 200 and reached, f"got {st} -- this is the phone")

        # curl and the night runner's self-calls send no Origin at all.
        st, _, _, reached = ask("/lmstudio/chat/completions",
                                {"Content-Type": "application/json"})
        check("a caller with no Origin at all still reaches the model",
              st == 200 and reached, f"got {st}")

        # The cross-origin UI/API split, via the base allowlist.
        st, _, _, reached = ask("/lmstudio/chat/completions", {
            "Content-Type": "application/json",
            "Host": f"127.0.0.1:{port}",
            "Origin": "https://ai.cafreso.com",
        })
        check("the allowlisted frontend origin still reaches the model",
              st == 200 and reached, f"got {st}")

        # Reads are untouched: the model picker lists models with no key and
        # no Origin ceremony, and OPTIONS preflight must not be swallowed.
        st, _, _ = request(port, "OPTIONS", "/lmstudio/chat/completions",
                           headers={"Origin": f"http://localhost:{port}"})
        check("OPTIONS preflight is not blocked by the gate",
              st in (200, 204), f"got {st}")

        # ---- D. the list is held, not patched -----------------------------
        # Fixing the two prefixes that exist today and leaving the next one to
        # the next incident is how _HOST_DATA_PREFIXES drifted in the first
        # place. The gate must read the ROUTES table itself.
        print("D. the gate reads the ROUTES table rather than naming its keys")
        src = open(os.path.join(ROOT, "serve.py"), encoding="utf-8").read()
        # Strip docstrings and comments first: this fix's own prose names
        # every identifier being searched for, so grepping raw source would
        # pass whether or not any code changed.
        code = re.sub(r'"""[\s\S]*?"""', '""', src)
        code = re.sub(r"(?m)#.*$", "", code)
        gate = code.split("def _state_change_gate")[1].split("\n    def ")[0]
        check("_state_change_gate still reads _KEY_PROTECTED_PREFIXES",
              "_KEY_PROTECTED_PREFIXES" in gate)
        check("_state_change_gate also reads ROUTES", "ROUTES" in gate,
              "the passthrough prefixes are hand-listed or absent")
        check("it does not re-type the prefixes ROUTES already holds",
              "'/lmstudio/'" not in gate and "'/ollama/'" not in gate)
    finally:
        srv.close()
        model.close()

    print()
    if failures:
        print(f"{len(failures)} FAILED: " + "; ".join(failures))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
