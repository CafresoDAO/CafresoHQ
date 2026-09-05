#!/usr/bin/env python3
"""#321. A page the tester merely had open must not be able to make the office
DO something. Live measurements against a real serve.py, default configuration:
no CAFRESOHQ_API_KEY, no CAFRESOHQ_ALLOWED_DIRS -- exactly what a beta tester
runs.

`## 294.` withheld Access-Control-Allow-Origin from the routes that hand back
the host's own data, so a stranger's tab could not READ the reply. That was
never a defence against a stranger's tab making the CALL. A cross-origin fetch
with a simple content-type is not preflighted at all: the browser sends it, the
handler runs, and only then is the response discarded unread. On a POST, the
unread response is the receipt for a write that already happened.

Measured BEFORE the fix, from Origin: https://evil.example with
Content-Type: text/plain -- a request any web page can make:

    POST /tools/exec {"tool":"FILE_WRITE","arg":"/tmp/PWNED","body":"OWNED"}
      -> 200 {"ok": true, "result": "Wrote 5 chars -> /tmp/PWNED"}
      -> and /tmp/PWNED existed on disk afterwards.

Note the path. /tmp is nowhere near the ~/Documents default allowlist:
_validate_path skips the whitelist entirely in local mode when
CAFRESOHQ_ALLOWED_DIRS is unset, so this is arbitrary file write anywhere the
tester can write. ~/.zshrc is a file the tester can write. That is a shell,
from a web page, with no user interaction beyond having a tab open.

  POST /projects/clone on the same forged Origin ran a real `git clone` into
  ~/Documents (measured: exit 128, "Cloning into '/Users/…/Documents/y'…").

The key gate did not stop any of it, for the third time in three ledger
entries: with no key configured _api_key_ok degrades to "loopback callers
only", and the attacking page's fetch() leaves the victim's own 127.0.0.1.
Loopback is not evidence of anything -- `## 315.` and `#320` say the same.

The gate added here is two conditions, because there are two attacks and each
is blind to the other:
  * a Host check, for DNS rebinding, where the page is genuinely same-origin
    and sends whatever Origin it likes (or none);
  * an Origin allowlist, for plain CSRF, where Host is an honest 127.0.0.1
    and only the Origin gives the attacker away.

Section C is the half that matters most: a gate that locks out a legitimate
caller is a wrong fix, not a strict one. The first attempt at this one DID
lock out the LAN/mobile URL the startup banner prints, and C is what caught
it.

Every file this test writes is a decoy under the system temp dir, removed on
the way out.
"""
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time

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
    """(status, body). Raw http.client, NOT urllib: urllib rewrites the Host
    header from the URL, which would quietly turn every rebinding check below
    into a no-op."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        conn.request(method, path, body=body, headers=dict(headers or {}))
        r = conn.getresponse()
        return r.status, r.read().decode("utf-8", "replace")
    finally:
        conn.close()


class Server:
    """serve.py on a private port, with the default (unconfigured) posture."""

    def __init__(self, **extra_env):
        self.port = free_port()
        self.state_dir = tempfile.mkdtemp(prefix="cafresohq-321-")
        env = dict(os.environ)
        env.pop("CAFRESOHQ_ALLOWED_DIRS", None)
        env.pop("CAFRESOHQ_ALLOWED_DIRS_UNRESTRICTED", None)
        env.pop("CAFRESOHQ_API_KEY", None)
        env.update({
            "CAFRESOHQ_HQ_STATE_DIR": self.state_dir,
            "PORT": str(self.port),
            "GAP_CRON": "0", "NEWS_CRON": "0", "TOPICS_CRON": "0",
        })
        env.update(extra_env)
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
    srv = Server()
    if not srv.wait_ready():
        print("serve.py never became ready", file=sys.stderr)
        return 1

    port = srv.port
    victim = os.path.join(tempfile.gettempdir(), "cafresohq-321-victim.txt")

    def clear():
        if os.path.exists(victim):
            os.remove(victim)

    def write_call(headers):
        """The attack payload and the app's own payload are the SAME request.
        Only the browser-supplied headers differ, which is the whole point."""
        clear()
        payload = json.dumps({"tool": "FILE_WRITE", "arg": victim,
                              "body": "WRITTEN-BY-321"})
        st, body = request(port, "POST", "/tools/exec", payload, headers)
        wrote = os.path.exists(victim)
        clear()
        return st, body, wrote

    try:
        # ---- A. plain cross-origin CSRF -----------------------------------
        # No DNS rebinding needed. Host is an honest 127.0.0.1; the attacker
        # cannot suppress the Origin header, and text/plain means no preflight
        # ever gives the browser a chance to refuse on the office's behalf.
        print("A. a forged Origin cannot make the office write a file")
        st, body, wrote = write_call({
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://evil.example",
        })
        check("POST /tools/exec from an unknown Origin is refused",
              st == 403, f"got {st}")
        check("no file was written on disk", not wrote,
              "the response being unreadable did not stop the write")
        check("the refusal names the reason", "origin" in body.lower(), body[:120])

        # /projects/clone ran a real git clone on this exact request shape.
        st, body = request(port, "POST", "/projects/clone",
                           '{"url":"octocat/Hello-World"}',
                           {"Content-Type": "text/plain",
                            "Origin": "https://evil.example"})
        check("POST /projects/clone from an unknown Origin is refused",
              st == 403, f"got {st}")

        # The state-changing verbs all go through the same gate.
        st, _ = request(port, "PUT", "/hq/state/notes.json", '{"x":1}',
                        {"Content-Type": "text/plain",
                         "Origin": "https://evil.example"})
        check("PUT /hq/ from an unknown Origin is refused", st == 403, f"got {st}")
        st, _ = request(port, "DELETE", "/missions/scheduled/anything", None,
                        {"Origin": "https://evil.example"})
        check("DELETE /missions/scheduled/ from an unknown Origin is refused",
              st == 403, f"got {st}")

        # ---- B. DNS rebinding ---------------------------------------------
        # Here the page IS same-origin with this server, so an Origin check
        # alone waves it through -- it can send a matching Origin, or none at
        # all. What it cannot forge is the Host: the browser sends the
        # attacker's own hostname, because that is what is in the address bar.
        print("B. a forged Host cannot make the office write a file")
        st, body, wrote = write_call({
            "Content-Type": "application/json",
            "Host": f"evil.example:{port}",
        })
        check("POST /tools/exec with a forged Host and NO Origin is refused",
              st == 403, f"got {st}")
        check("no file was written on disk (forged Host)", not wrote)

        st, body, wrote = write_call({
            "Content-Type": "application/json",
            "Host": f"evil.example:{port}",
            "Origin": f"http://evil.example:{port}",   # same-origin with itself
        })
        check("a rebound page that is same-origin WITH ITSELF is still refused",
              st == 403, f"got {st}")
        check("no file was written on disk (rebound same-origin)", not wrote)

        # A rebound page can also just read files back. Same gate, same 403.
        st, body = request(port, "POST", "/tools/exec",
                           json.dumps({"tool": "FILE_READ", "arg": "/etc/hosts"}),
                           {"Content-Type": "application/json",
                            "Host": f"evil.example:{port}"})
        check("a rebound page cannot FILE_READ either", st == 403, f"got {st}")
        check("no file contents leak in the refusal",
              "Host Database" not in body and "localhost" not in body)

        # ---- C. the product still works -----------------------------------
        # This is the half that decides whether the fix is right or merely
        # strict. Each of these is a real way the office is opened.
        print("C. every legitimate caller still gets through")

        st, _, wrote = write_call({
            "Content-Type": "application/json",
            "Host": f"localhost:{port}",
            "Origin": f"http://localhost:{port}",
        })
        check("same-origin http://localhost still writes", st == 200 and wrote,
              f"got {st}")

        st, _, wrote = write_call({
            "Content-Type": "application/json",
            "Host": f"127.0.0.1:{port}",
            "Origin": f"http://127.0.0.1:{port}",
        })
        check("same-origin http://127.0.0.1 still writes", st == 200 and wrote,
              f"got {st}")

        # The LAN/mobile URL the startup banner prints. _app_origins only ever
        # self-adds a LOOPBACK Host, so this one is in nobody's allowlist --
        # the first version of this fix refused it, which would have broken the
        # phone. It is safe because the Host gate ran first: an IP literal is
        # not something a rebinding page can send.
        st, _, wrote = write_call({
            "Content-Type": "application/json",
            "Host": f"10.0.0.131:{port}",
            "Origin": f"http://10.0.0.131:{port}",
        })
        check("the LAN/mobile IP-literal URL still writes", st == 200 and wrote,
              f"got {st} -- this is the phone, do not lock it out")

        # curl, the night runner's self-calls, a same-origin XHR: no Origin at
        # all, on a Host the rebinder cannot forge.
        st, _, wrote = write_call({"Content-Type": "application/json"})
        check("a caller with no Origin at all still writes", st == 200 and wrote,
              f"got {st}")

        # The production gateway terminates TLS and proxies over plain HTTP,
        # so the scheme has to come from X-Forwarded-Proto or the allowlisted
        # https:// origin never matches.
        st, _, wrote = write_call({
            "Content-Type": "application/json",
            "Host": "hq.cafreso.com",
            "Origin": "https://hq.cafreso.com",
            "X-Forwarded-Proto": "https",
        })
        check("the production gateway still writes", st == 200 and wrote,
              f"got {st}")

        # ...and X-Forwarded-Proto grants nothing on its own: the hostname
        # still has to be allowlisted on its own merits.
        st, _, wrote = write_call({
            "Content-Type": "application/json",
            "Host": "evil.example",
            "Origin": "https://evil.example",
            "X-Forwarded-Proto": "https",
        })
        check("X-Forwarded-Proto does not launder an unknown host",
              st == 403 and not wrote, f"got {st}")

        # The cross-origin UI/API split, via the base allowlist.
        st, _, wrote = write_call({
            "Content-Type": "application/json",
            "Host": f"127.0.0.1:{port}",
            "Origin": "https://ai.cafreso.com",
        })
        check("the SvelteKit frontend origin still writes", st == 200 and wrote,
              f"got {st}")

        # Public routes are untouched -- the app shell must still bootstrap.
        st, _ = request(port, "GET", "/health",
                        headers={"Origin": "https://evil.example"})
        check("GET /health stays open to anyone", st == 200, f"got {st}")
        st, _ = request(port, "OPTIONS", "/tools/exec",
                        headers={"Origin": f"http://localhost:{port}"})
        check("OPTIONS preflight is not blocked by the gate",
              st in (200, 204), f"got {st}")

        # ---- D. the gate is derived, not hand-listed ----------------------
        # _HOST_DATA_PREFIXES drifted precisely because it was maintained by
        # hand; the note above it says so. The gate must read the same tuple
        # the key gate reads, so the next added prefix is covered for free.
        print("D. the gate derives its route list rather than repeating it")
        src = open(os.path.join(ROOT, "serve.py"), encoding="utf-8").read()
        # Strip comments and docstrings first: this file's own explanatory
        # prose is full of the strings being searched for, and so is the
        # fix's. Grepping raw source would fail a correct fix.
        code = re.sub(r'"""[\s\S]*?"""', '""', src)
        code = re.sub(r"(?m)#.*$", "", code)
        gate = code.split("def _state_change_gate")[1].split("\n    def ")[0]
        check("_state_change_gate reads _KEY_PROTECTED_PREFIXES",
              "_KEY_PROTECTED_PREFIXES" in gate)
        check("_state_change_gate consults the Host gate",
              "_host_gate_ok" in gate)
        check("_state_change_gate consults the Origin allowlist",
              "_app_origins" in gate)
        for verb in ("do_POST", "do_PUT", "do_DELETE"):
            block = code.split(f"def {verb}(self)")[1].split("\n    def ")[0]
            check(f"{verb} calls the gate", "_state_change_gate" in block)
    finally:
        clear()
        srv.close()

    print()
    if failures:
        print(f"{len(failures)} FAILED: " + "; ".join(failures))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
