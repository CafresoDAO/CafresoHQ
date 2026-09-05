#!/usr/bin/env python3
"""#318. Three live measurements against a real serve.py, all on the /fs family.

A. A BLANK allowlist must lock the filesystem, not unlock it.
   `_within_allowed_dirs` opened with `if not _cafresohq_allowed_dirs: return
   True`, and called that "the documented opt-out" -- while the module comment
   eleven lines above it, and the startup banner, both said an empty list
   DISABLES the endpoints. So the operator who read the banner, typed
   `CAFRESOHQ_ALLOWED_DIRS=` to shut the thing down, and was told DISABLED, got
   /etc/hosts and a listing of /etc back. Measured before the fix:
       CAFRESOHQ_ALLOWED_DIRS= python3 serve.py
       curl '/fs/file?path=/etc/hosts'  -> 200, "## Host Database"
       curl '/fs/browse?path=/etc'      -> 200, {"entries": [{"name":"apache2" ...
   The opt-out now has a name that says what it does -- and the last section
   here proves that name still works, so this is a rename, not an amputation.

B. The unconfigured default must not reach the dotfiles.
   It was $HOME *and* $HOME/Documents, which is $HOME. ~/.ssh/id_ed25519 came
   back base64 in one /fs/collect. The default is now $HOME/Documents alone:
   the projects the IDE, the FILES tree and the preview pane actually open stay
   reachable with zero configuration; $HOME itself does not.

C. A forged Host must get no body.
   /terminal/nonce four lines up in the same dispatch table consults
   _app_origins and refuses a stranger; the /fs routes consulted nothing at
   all. Measured before the fix, with `Host: evil.example:PORT`:
       /fs/file?path=…  -> 200 + the file's contents
   That is DNS rebinding, and it is why ledger `## 294.`'s CORS fix does not
   cover it: under rebinding the attacker's page is SAME-origin with this
   server, so it never needs an Access-Control-Allow-Origin to read the reply.

   One correction to the audit's framing, measured here: the nonce's gate keys
   off ORIGIN, not Host -- a bare forged Host with no Origin gets 200 from it.
   The gate added to /fs is therefore the stronger of the two, which is the
   right way round for a route that carries no key at all.

Every file read here is a decoy this test writes and removes itself. The real
~/.ssh is never touched -- the point is the boundary, not the secret.
"""
import http.client
import os
import socket
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKER = "DECOY-NOT-A-REAL-SECRET-318"
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


def get(port, path, host=None, headers=None, tolerant=False):
    """(status, body). Raw http.client so a FORGED Host header actually goes on
    the wire -- urllib rewrites Host from the URL, which would quietly turn the
    rebinding check into a no-op.

    tolerant=True turns a transport failure into (0, "") instead of an
    exception. Needed on the checks that are supposed to be REFUSED: with the
    old too-wide default, /fs/collect?path=$HOME is not a 200, it is a walk of
    the entire home directory that outruns the socket timeout. A test that
    dies with a TimeoutError there reports a crash, not the regression."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        hdrs = dict(headers or {})
        if host:
            hdrs["Host"] = host
        conn.request("GET", path, headers=hdrs)
        r = conn.getresponse()
        return r.status, r.read().decode("utf-8", "replace")
    except Exception:
        if tolerant:
            return 0, ""
        raise
    finally:
        conn.close()


class Server:
    """serve.py on a private port with a private state dir."""

    def __init__(self, **extra_env):
        self.port = free_port()
        self.state_dir = tempfile.mkdtemp(prefix="cafresohq-318-")
        env = dict(os.environ)
        env.pop("CAFRESOHQ_ALLOWED_DIRS", None)
        env.pop("CAFRESOHQ_ALLOWED_DIRS_UNRESTRICTED", None)
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
        for _ in range(120):
            try:
                get(self.port, "/health")
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


def write_decoy(directory):
    fd, path = tempfile.mkstemp(prefix=".cafresohq-318-decoy-", dir=directory)
    with os.fdopen(fd, "w") as fh:
        fh.write(MARKER + "\n")
    return path


def main():
    home = os.path.expanduser("~")
    docs = os.path.join(home, "Documents")
    if not os.path.isdir(docs):
        os.makedirs(docs, exist_ok=True)

    home_decoy = write_decoy(home)
    docs_decoy = write_decoy(docs)
    servers = []

    try:
        # ---- A. blank allowlist -> everything refused --------------------
        print("A. CAFRESOHQ_ALLOWED_DIRS= locks the filesystem")
        blank = Server(CAFRESOHQ_ALLOWED_DIRS="")
        servers.append(blank)
        if not blank.wait_ready():
            print("serve.py (blank allowlist) never became ready", file=sys.stderr)
            return 1

        status, body = get(blank.port, "/fs/file?path=/etc/hosts", tolerant=True)
        check("/fs/file?path=/etc/hosts is refused", status == 403, f"got {status}")
        check("/etc/hosts contents are not in the body",
              "Host Database" not in body and "localhost" not in body)

        status, body = get(blank.port, "/fs/browse?path=/etc", tolerant=True)
        check("/fs/browse?path=/etc is refused", status == 403, f"got {status}")
        check("no /etc listing leaks in the refusal", '"entries"' not in body)

        status, body = get(blank.port, "/fs/collect?path=/etc", tolerant=True)
        check("/fs/collect?path=/etc is refused", status == 403, f"got {status}")

        status, _ = get(blank.port, f"/fs/file?path={docs_decoy}", tolerant=True)
        check("a blank allowlist refuses even the decoy in ~/Documents",
              status == 403, f"got {status}")
        blank.close()
        servers.remove(blank)

        # ---- B. the unconfigured default -------------------------------
        print("B. the unconfigured default is ~/Documents, not $HOME")
        default = Server()
        servers.append(default)
        if not default.wait_ready():
            print("serve.py (default) never became ready", file=sys.stderr)
            return 1

        status, body = get(default.port, f"/fs/file?path={docs_decoy}")
        check("a file in ~/Documents is still served out of the box",
              status == 200 and MARKER in body, f"got {status}")

        status, body = get(default.port, f"/fs/file?path={home_decoy}", tolerant=True)
        check("a dotfile sitting directly in $HOME is refused",
              status == 403, f"got {status}")
        check("the $HOME decoy's contents never reach the caller",
              MARKER not in body)

        status, body = get(default.port, f"/fs/collect?path={home}", tolerant=True)
        check("/fs/collect on $HOME itself is refused", status == 403,
              f"got {status}")

        # ---- C. a forged Host gets no body -----------------------------
        print("C. a forged Host header gets 403 and no body")
        evil = f"evil.example:{default.port}"

        status, body = get(default.port, f"/fs/file?path={docs_decoy}", host=evil,
                           tolerant=True)
        check("/fs/file with a forged Host -> 403", status == 403, f"got {status}")
        check("the forged-Host reply carries no file contents", MARKER not in body)

        for route in ("/fs/browse?path=" + docs,
                      "/fs/collect?path=" + docs,
                      "/fs/stat?path=" + docs_decoy):
            status, _ = get(default.port, route, host=evil, tolerant=True)
            check(f"{route.split('?')[0]} with a forged Host -> 403",
                  status == 403, f"got {status}")

        # The sibling, as the control -- and a correction to the audit's
        # framing. /terminal/nonce's gate keys off ORIGIN, not Host: a
        # cross-origin Origin is refused, and a bare forged Host with no
        # Origin at all sails through (measured: 200). The /fs gate added
        # here is the stronger of the two, which is the right way round for
        # a keyless route; the nonce's own Host exposure is left as its own
        # finding rather than widened into this fix.
        status, _ = get(default.port, "/terminal/nonce",
                        headers={"Origin": "https://evil.example"})
        check("/terminal/nonce still refuses a cross-origin Origin",
              status == 403, f"got {status}")

        # And the office itself must keep working: loopback names and bare IP
        # literals are exactly what a rebinding attack cannot produce.
        print("   the office's own requests still work")
        for host in (f"127.0.0.1:{default.port}", f"localhost:{default.port}",
                     f"[::1]:{default.port}"):
            status, body = get(default.port, f"/fs/file?path={docs_decoy}",
                               host=host)
            check(f"Host: {host} still reads the decoy",
                  status == 200 and MARKER in body, f"got {status}")
        default.close()
        servers.remove(default)

        # ---- D. the named opt-out still opens the door ------------------
        print("D. CAFRESOHQ_ALLOWED_DIRS_UNRESTRICTED=1 is the one opt-out")
        loose = Server(CAFRESOHQ_ALLOWED_DIRS_UNRESTRICTED="1")
        servers.append(loose)
        if not loose.wait_ready():
            print("serve.py (unrestricted) never became ready", file=sys.stderr)
            return 1
        status, body = get(loose.port, f"/fs/file?path={home_decoy}")
        check("the explicit opt-out reaches a $HOME file again",
              status == 200 and MARKER in body, f"got {status}")
        status, _ = get(loose.port, f"/fs/file?path={home_decoy}",
                        host=f"evil.example:{loose.port}", tolerant=True)
        check("but the Host gate is NOT part of the opt-out", status == 403,
              f"got {status}")
        loose.close()
        servers.remove(loose)

    finally:
        for s in list(servers):
            s.close()
        for p in (home_decoy, docs_decoy):
            if os.path.exists(p):
                os.remove(p)

    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures))
        return 1
    print("PASS: a blank allowlist locks the filesystem and a forged host gets no body")
    return 0


if __name__ == "__main__":
    sys.exit(main())
