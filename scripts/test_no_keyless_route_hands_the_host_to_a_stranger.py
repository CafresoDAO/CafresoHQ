#!/usr/bin/env python3
"""Two live holes, both measured against a real server, both must stay shut.

A. /agent/stream must sit behind the API key.
   _KEY_PROTECTED_PREFIXES listed '/agents' (plural). '/agent/stream'.startswith
   ('/agents') is False, so the auth gate returned True before it ever reached
   the key check -- and /agent/stream is the route that spawns a real agent CLI
   with Edit/Write and --add-dir on the workspace. Measured before the fix, with
   a key configured and none supplied: /tools/exec 401, /terminal/spawn 401,
   /agent/stream 400 (i.e. it got as far as validating the body).

B. An unknown browser origin must NOT be handed the host's own files.
   The /fs *read* routes are deliberately keyless -- the preview iframe fetches
   /fs/site/<root>/<asset> with no key -- and _cafresohq_allowed_dirs defaults to
   $HOME. The CORS branch used to fall through to 'Access-Control-Allow-Origin:
   *' for every unrecognised origin, so any page the user happened to be visiting
   could read their home directory. Measured before the fix, with a key
   configured: 200 + 'Access-Control-Allow-Origin: *' + the file body.

Since the /fs reads stay keyless on purpose, the absent ACAO header is the whole
defence for the browser threat, which makes it worth a real test rather than a
source-shape assertion. Everything below boots serve.py and speaks HTTP to it.

The file this reads is a decoy this test writes itself. No real secret is ever
read, and it is removed in the finally block.
"""
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
    state_dir = tempfile.mkdtemp(prefix="cafresohq-sectest-")
    # The decoy must live in $HOME -- _cafresohq_allowed_dirs defaults to $HOME,
    # and reading it there is the whole point. But the NAME used to be fixed, so
    # two copies of this suite shared one file: whichever finished first removed
    # it in its finally block, and the other's /fs/file read came back 404 with
    # two checks failing for a reason that had nothing to do with the code under
    # test. The directory is load-bearing; the name is not, so it gets a unique
    # one per process.
    fd, decoy = tempfile.mkstemp(prefix=".cafresohq-regression-decoy-",
                                 dir=os.path.expanduser("~"))
    os.close(fd)
    marker = "DECOY-NOT-A-REAL-SECRET"
    proc = None

    try:
        with open(decoy, "w") as fh:
            fh.write(marker + "\n")

        env = dict(os.environ)
        env.update({
            "CAFRESOHQ_API_KEY": "regression-test-key",
            "CAFRESOHQ_HQ_STATE_DIR": state_dir,
            "PORT": str(port),
            "GAP_CRON": "0", "NEWS_CRON": "0", "TOPICS_CRON": "0",
        })
        proc = subprocess.Popen(
            [sys.executable, "serve.py"], cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
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

        # A. every route that spawns or executes is gated, /agent/stream included.
        print("A. key-gated routes reject a request with no key")
        for route in ("/tools/exec", "/terminal/spawn", "/agent/stream"):
            status, _, _ = request(base + route)
            check(f"{route} -> 401", status == 401, f"got {status}")

        # B. an unknown origin gets no ACAO, so the browser refuses the read.
        #    (urllib, like curl, ignores CORS -- the header's absence is the check.)
        print("B. an unknown origin is not handed the host's files")
        status, headers, body = request(
            f"{base}/fs/file?path={decoy}", origin="https://evil.example"
        )
        check("/fs/file is still keyless (by design, for the preview iframe)",
              status == 200, f"got {status}")
        check("marker present, so this really did read the decoy",
              marker in body)
        check("no Access-Control-Allow-Origin for the unknown origin",
              "Access-Control-Allow-Origin" not in headers,
              f"got {headers.get('Access-Control-Allow-Origin')!r}")

        # C. the app's own origin must still work, or the office breaks.
        #    _app_origins() adds the request's own Host when it names a loopback
        #    literal, and urllib sends 'Host: 127.0.0.1:<port>' -- so THAT is the
        #    allowlisted origin here, not the localhost spelling of the same port.
        print("C. an allowlisted app origin still works")
        app_origin = f"http://127.0.0.1:{port}"
        _, headers, _ = request(f"{base}/fs/file?path={decoy}", origin=app_origin)
        check("allowlisted origin gets ACAO echoed back",
              headers.get("Access-Control-Allow-Origin") == app_origin,
              f"got {headers.get('Access-Control-Allow-Origin')!r}")
        check("allowlisted origin gets credentials",
              headers.get("Access-Control-Allow-Credentials") == "true")

        # D. /health carries no host data and must stay wide open.
        print("D. /health stays public")
        status, headers, _ = request(base + "/health", origin="https://evil.example")
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
        if os.path.exists(decoy):
            os.remove(decoy)
        subprocess.run(["rm", "-rf", state_dir], check=False)

    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures))
        return 1
    print("PASS: no keyless route hands the host to a stranger")
    return 0


if __name__ == "__main__":
    sys.exit(main())
