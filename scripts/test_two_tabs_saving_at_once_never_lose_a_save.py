#!/usr/bin/env python3
"""Concurrent PUTs to the same /hq/state/<name> must all land, none torn.

serve.py is a ThreadingMixIn server, and every open tab, the night runner's
self-calls and hqsh all PUT the same small set of state names (activity,
projects, receipts...). The PUT handler wrote through a tmp file named
'<name>.json.tmp' -- ONE name per state file, shared by every concurrent
writer. Two simultaneous saves then collided on that single tmp: each
open('wb') truncated the other's half-written bytes, and whichever
os.replace ran second raised FileNotFoundError, surfacing as a 500 for a
save the client composed correctly. Measured before the fix on this exact
scenario: 129 of 240 concurrent PUTs came back 500, and the tmp a winner
installed could be one a loser had already truncated -- i.e. a corrupt or
empty state file where a whole collection used to live. useFileStored's
GET-side shape check then silently resets that collection to seed data,
which is exactly the data loss the atomic-write comment says it prevents.

The fix gives every write its own mkstemp tmp; os.replace stays
all-or-nothing and last-writer-wins. This boots the real serve.py and
hammers one state name from six threads: every PUT must return 200, and
after every round the file must read back as ONE writer's complete body.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
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


def request(url, method="GET", body=None):
    """Return (status, bytes). Never raises on an HTTP error status."""
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("X-API-Key", "regression-test-key")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main():
    port = free_port()
    state_dir = tempfile.mkdtemp(prefix="cafresohq-racetest-")
    proc = None
    bad_puts = []
    torn = []

    ROUNDS = 25
    WRITERS = 6
    PAD = "x" * 200000  # big enough that a truncated sibling is visible

    try:
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

        def writer(wid, rnd, barrier):
            payload = json.dumps({"writer": wid, "round": rnd, "pad": PAD}).encode()
            barrier.wait()  # release all writers into the handler together
            st, body = request(f"{base}/hq/state/race-target", "PUT", payload)
            if st != 200:
                bad_puts.append((rnd, wid, st, body[:100]))

        for rnd in range(ROUNDS):
            barrier = threading.Barrier(WRITERS)
            threads = [threading.Thread(target=writer, args=(w, rnd, barrier))
                       for w in range(WRITERS)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            st, body = request(f"{base}/hq/state/race-target")
            if st != 200:
                torn.append((rnd, f"GET -> {st}"))
                continue
            try:
                data = json.loads(body.decode("utf-8"))
                if not (isinstance(data, dict) and data.get("pad") == PAD):
                    torn.append((rnd, "not one writer's complete body"))
            except Exception as e:
                torn.append((rnd, f"unparseable JSON on disk: {e}"))

        total = ROUNDS * WRITERS
        check(f"every concurrent PUT returned 200 ({total} PUTs, 6 at a time)",
              not bad_puts, f"{len(bad_puts)} failed, e.g. {bad_puts[:2]}")
        check("the state file read back whole after every round",
              not torn, f"{len(torn)} torn, e.g. {torn[:2]}")

        # And no tmp debris left behind for the winner to have installed later.
        leftovers = [n for n in os.listdir(state_dir) if n.endswith(".tmp")]
        check("no tmp files left in hq-state", not leftovers, repr(leftovers[:3]))

    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        subprocess.run(["rm", "-rf", state_dir], check=False)

    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures))
        return 1
    print("PASS: two tabs saving at once never lose a save")
    return 0


if __name__ == "__main__":
    sys.exit(main())
