#!/usr/bin/env python3
"""`## 320.` Live measurements against a real serve.py, on the /terminal family.

THE HOLE. /terminal/nonce gated on Origin, and only when an Origin was present:

    _origin = self.headers.get('Origin', '').strip()
    if _origin and _origin not in self._app_origins():
        return self._send_json(403, ...)
    return self._send_json(200, {'nonce': _PTY_NONCE})

Its docstring called that "same-origin callers only", on the reasoning that a
same-origin XHR sends no Origin header. True, and useless: under DNS rebinding
the attacker's page IS same-origin with this server. A page at
http://evil.example whose name resolves to 127.0.0.1 sends NO Origin on its
fetch to /terminal/nonce, skips the check, gets the nonce, and opens
/terminal/pty?cli=claude&cwd=... with it. That is a shell on the machine of
anyone who visited the page. Measured before the fix, with
`Host: evil.example:PORT` and no Origin at all:

    /terminal/nonce  -> 200 {"nonce":"<64 hex>"}
    /terminal/status -> 200
    /terminal/pty    -> reached the nonce check, and the nonce was in hand

`## 315.`'s gate did not cover this: it was dispatched on `/fs/` only, and its
own comment recorded the belief that /terminal/nonce "already had" a Host gate.
It had an Origin check, which is a different question with a different answer.

Every request here is raw http.client, NOT urllib: urllib rewrites Host from
the URL, which would silently turn the whole point of this file into a no-op.

The four callers that must keep working are measured too -- same-origin
localhost, the LAN/mobile bare-IP URL the startup banner prints, the production
gateway hq.cafreso.com, and an operator's CAFRESOHQ_ALLOWED_WS_ORIGINS entry.
The terminal is the product; a gate that breaks any of those is a wrong fix.
"""
import http.client
import json
import os
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


def req(port, path, method="GET", host=None, headers=None, body=None,
        tolerant=False):
    """(status, body). Raw http.client so a FORGED Host actually goes on the
    wire. tolerant=True turns a transport failure into (0, "")."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        hdrs = dict(headers or {})
        if host:
            hdrs["Host"] = host
        conn.request(method, path, body=body, headers=hdrs)
        r = conn.getresponse()
        return r.status, r.read().decode("utf-8", "replace")
    except Exception:
        if tolerant:
            return 0, ""
        raise
    finally:
        conn.close()


WS_HEADERS = {
    "Upgrade": "websocket",
    "Connection": "Upgrade",
    "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
    "Sec-WebSocket-Version": "13",
}


class Server:
    def __init__(self, **extra_env):
        self.port = free_port()
        self.state_dir = tempfile.mkdtemp(prefix="cafresohq-320-")
        env = dict(os.environ)
        env.pop("CAFRESOHQ_API_KEY", None)          # the normal local config:
        env.pop("CAFRESOHQ_ALLOWED_WS_ORIGINS", None)  # keyless -> loopback-only
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
                req(self.port, "/health")
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


def nonce_in(body):
    try:
        return (json.loads(body) or {}).get("nonce") or ""
    except Exception:
        return ""


def main():
    servers = []
    try:
        srv = Server()
        servers.append(srv)
        if not srv.wait_ready():
            print("serve.py never became ready", file=sys.stderr)
            return 1
        port = srv.port
        evil = f"evil.example:{port}"

        # ---- A. the office's own callers first, so a refusal below is a
        #         gate doing its job and not a dead server ------------------
        print("A. the four legitimate callers still get the nonce")

        # 1. same-origin http://localhost:8787 -- the case that made the hole
        #    look safe: a same-origin XHR sends NO Origin header.
        status, body = req(port, "/terminal/nonce", host=f"localhost:{port}")
        real_nonce = nonce_in(body)
        check("same-origin localhost with NO Origin header still gets a nonce",
              status == 200 and len(real_nonce) == 64, f"got {status}")

        status, body = req(port, "/terminal/nonce", host=f"127.0.0.1:{port}",
                           headers={"Origin": "http://localhost:8787"})
        check("the loopback literal with a loopback Origin still gets a nonce",
              status == 200 and nonce_in(body) == real_nonce, f"got {status}")

        # 2. the LAN/mobile URL the startup banner prints. A bare IP literal is
        #    something a rebinding attack cannot send -- the victim's address
        #    bar holds the attacker's HOSTNAME, which is the whole point.
        status, body = req(port, "/terminal/nonce", host=f"10.0.0.131:{port}")
        check("the LAN/mobile bare-IP host still gets a nonce",
              status == 200 and nonce_in(body) == real_nonce, f"got {status}")

        # 3. the production gateway. Caddy passes Host: hq.cafreso.com through
        #    on a PLAINTEXT hop, so the gate must match on hostname and not on
        #    a synthesised http://hq.cafreso.com that is not in the allowlist.
        status, body = req(port, "/terminal/nonce", host="hq.cafreso.com",
                           headers={"Origin": "https://hq.cafreso.com"})
        check("the production gateway host still gets a nonce",
              status == 200 and nonce_in(body) == real_nonce, f"got {status}")

        status, _ = req(port, "/terminal/status", host="hq.cafreso.com",
                        headers={"Origin": "https://hq.cafreso.com"})
        check("/terminal/status still answers the production gateway",
              status == 200, f"got {status}")

        # ---- B. a rebound page: forged Host, NO Origin at all -------------
        print("B. a forged Host with no Origin gets nothing")

        status, body = req(port, "/terminal/nonce", host=evil, tolerant=True)
        check("/terminal/nonce with a forged Host -> 403", status == 403,
              f"got {status}")
        check("the refusal carries no nonce",
              not nonce_in(body) and real_nonce not in body)

        for path in ("/terminal/status",
                     "/terminal/kill?sessionId=x",
                     "/terminal/spawn?cli=claude&cwd=" + ROOT):
            status, body = req(port, path, host=evil, tolerant=True)
            check(f"{path.split('?')[0]} with a forged Host -> 403",
                  status == 403, f"got {status}")

        # The WebSocket, holding a nonce the page could have read. Gating the
        # nonce and not the socket would be worth nothing, and vice versa.
        status, _ = req(port, f"/terminal/pty?cli=claude&cwd={ROOT}"
                              f"&nonce={real_nonce}",
                        host=evil, headers=WS_HEADERS, tolerant=True)
        check("/terminal/pty with a forged Host and a VALID nonce -> 403",
              status == 403, f"got {status}")

        status, _ = req(port, "/terminal/stream", method="POST", host=evil,
                        headers={"Content-Type": "application/json",
                                 "Content-Length": "2"},
                        body="{}", tolerant=True)
        check("POST /terminal/stream with a forged Host -> 403", status == 403,
              f"got {status}")

        # ---- C. the checks that were already there still work -------------
        print("C. the pre-existing Origin and nonce gates are untouched")

        status, body = req(port, "/terminal/nonce", host=f"127.0.0.1:{port}",
                           headers={"Origin": "https://evil.example"},
                           tolerant=True)
        check("a cross-origin Origin is still refused on a good Host",
              status == 403, f"got {status}")
        check("that refusal carries no nonce either", not nonce_in(body))

        # The bad-nonce path answers by DROPPING the connection rather than by
        # sending a 403 (measured: RemoteDisconnected, no response line, for
        # both a WS handshake and a plain GET). That is pre-existing behaviour
        # and it is still a refusal -- no 101, no PTY -- so this asserts the
        # refusal, not a particular status code. The forged-Host case above is
        # the one that must be a clean 403, and it is.
        status, _ = req(port, f"/terminal/pty?cli=claude&cwd={ROOT}"
                              "&nonce=deadbeef",
                        host=f"127.0.0.1:{port}", headers=WS_HEADERS,
                        tolerant=True)
        check("a good Host with a WRONG nonce still gets no PTY",
              status in (0, 403), f"got {status}")
        srv.close()
        servers.remove(srv)

        # ---- D. the operator's own allowlist entry ------------------------
        print("D. CAFRESOHQ_ALLOWED_WS_ORIGINS is honoured by the Host gate")
        canister = Server(
            CAFRESOHQ_ALLOWED_WS_ORIGINS="https://cqyto-example.icp0.io")
        servers.append(canister)
        if not canister.wait_ready():
            print("serve.py (allowlist) never became ready", file=sys.stderr)
            return 1

        status, body = req(canister.port, "/terminal/nonce",
                           host="cqyto-example.icp0.io",
                           headers={"Origin": "https://cqyto-example.icp0.io"})
        check("a configured canister origin still gets a nonce",
              status == 200 and len(nonce_in(body)) == 64, f"got {status}")

        status, _ = req(canister.port, "/terminal/nonce",
                        host=f"evil.example:{canister.port}", tolerant=True)
        check("configuring an allowlist does not reopen the forged Host",
              status == 403, f"got {status}")
        canister.close()
        servers.remove(canister)

    finally:
        for s in list(servers):
            s.close()

    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures))
        return 1
    print("PASS: a rebound page gets no pty nonce and no shell")
    return 0


if __name__ == "__main__":
    sys.exit(main())
