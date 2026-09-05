#!/usr/bin/env python3
"""A page the user is merely visiting must not be able to READ the office.

serve.py has two lists. _KEY_PROTECTED_PREFIXES names the routes that want an
API key. _HOST_DATA_PREFIXES names the routes an unknown browser origin must
never be handed an 'Access-Control-Allow-Origin' for. Its comment claims "the
key-gated members are listed too -- the key already stops them, and defence in
depth costs nothing here", but only 11 of the 24 key-protected prefixes were
actually spelled out, and the key does not stop the browser threat anyway:
CAFRESOHQ_API_KEY is normally UNSET, and with no key configured the gate falls
back to "loopback callers only" -- which a page in the user's own browser
trivially is, because its fetch() to 127.0.0.1 leaves that machine.

Measured against a keyless local instance before the fix, with
Origin: https://evil.example:

    /browser/status            200  Access-Control-Allow-Origin: *
    /agents                    200  Access-Control-Allow-Origin: *
    /approvals/external/list   200  Access-Control-Allow-Origin: *
    /missions/runs             200  Access-Control-Allow-Origin: *

-- the pending tool-approval queue (tool, cwd, arguments), the agent roster,
the night-shift run log, and, through /browser/fetch?url=..., an SSRF read of
any intranet URL the office can reach, all readable by a stranger's tab.

Everything below boots a real serve.py and speaks HTTP to it; urllib, like
curl, ignores CORS, so the ABSENCE of the header is the assertion. The last
section imports serve.py in a subprocess and asserts the invariant itself --
every key-protected prefix is covered by a host-data prefix -- so the next
prefix someone adds cannot quietly reopen this.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = []

# Key-gated routes that answer a plain GET with the office's own data. Each
# must come back 200 (so "no ACAO" is not just an error page) and carry no
# Access-Control-Allow-Origin when an unknown origin asks.
HOST_DATA_ROUTES = (
    "/browser/status",
    "/agents",
    "/approvals/external/list",
    "/missions/runs",
    "/missions/scheduled",
    "/codex/status",
    "/claudecode/status",
)


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


def request(url, origin=None):
    """Return (status, headers, body). Never raises on an HTTP error status."""
    req = urllib.request.Request(url)
    if origin:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")


def main():
    port = free_port()
    state_dir = tempfile.mkdtemp(prefix="cafresohq-corstest-")
    proc = None

    try:
        env = dict(os.environ)
        # NO CAFRESOHQ_API_KEY: this is the shape a beta tester actually runs,
        # and the shape in which the loopback fallback lets a visited page in.
        env.pop("CAFRESOHQ_API_KEY", None)
        env.update({
            "CAFRESOHQ_HQ_STATE_DIR": state_dir,
            "PORT": str(port),
            "GAP_CRON": "0", "NEWS_CRON": "0", "TOPICS_CRON": "0",
        })
        proc = subprocess.Popen(
            [sys.executable, "serve.py"], cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        base = f"http://127.0.0.1:{port}"
        for _ in range(120):
            try:
                request(base + "/health")
                break
            except Exception:
                if proc.poll() is not None:
                    print("serve.py exited during startup", file=sys.stderr)
                    return 1
                time.sleep(0.1)
        else:
            print("serve.py never became ready", file=sys.stderr)
            return 1

        print("A. an unknown origin gets no ACAO on a key-gated data route")
        for route in HOST_DATA_ROUTES:
            status, headers, _ = request(base + route,
                                         origin="https://evil.example")
            acao = headers.get("Access-Control-Allow-Origin")
            check(f"{route} answers with real data (200)",
                  status == 200, f"got {status}")
            check(f"{route} sends no Access-Control-Allow-Origin",
                  acao is None, f"got {acao!r}")

        print("B. the office's own origin still works")
        # _app_origins() adds the request's own Host when it names a loopback
        # literal, and urllib sends 'Host: 127.0.0.1:<port>'.
        app_origin = f"http://127.0.0.1:{port}"
        status, headers, _ = request(base + "/agents", origin=app_origin)
        check("/agents -> 200 for the app origin", status == 200, f"got {status}")
        check("allowlisted origin gets ACAO echoed back",
              headers.get("Access-Control-Allow-Origin") == app_origin,
              f"got {headers.get('Access-Control-Allow-Origin')!r}")
        check("allowlisted origin gets credentials",
              headers.get("Access-Control-Allow-Credentials") == "true")

        print("C. /health carries no host data and stays public")
        status, headers, _ = request(base + "/health",
                                     origin="https://evil.example")
        check("/health -> 200", status == 200, f"got {status}")
        check("/health still ACAO: *",
              headers.get("Access-Control-Allow-Origin") == "*",
              f"got {headers.get('Access-Control-Allow-Origin')!r}")

    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        subprocess.run(["rm", "-rf", state_dir], check=False)

    print("D. the invariant holds for EVERY key-protected prefix, not a hand list")
    probe = (
        "import json, sys; sys.path.insert(0, '.'); import serve; "
        "print(json.dumps([p for p in serve._KEY_PROTECTED_PREFIXES "
        "if not p.startswith(serve._HOST_DATA_PREFIXES)]))"
    )
    r = subprocess.run([sys.executable, "-c", probe], cwd=ROOT,
                       capture_output=True, text=True)
    if r.returncode != 0:
        check("serve.py imports for the prefix probe", False,
              (r.stderr or "").strip()[-300:])
    else:
        uncovered = json.loads(r.stdout.strip().splitlines()[-1])
        check("no key-protected prefix is left out of _HOST_DATA_PREFIXES",
              uncovered == [], f"uncovered: {uncovered}")

    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures))
        return 1
    print("PASS: a stranger can never read a key-gated route")
    return 0


if __name__ == "__main__":
    sys.exit(main())
