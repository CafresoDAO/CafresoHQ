#!/usr/bin/env python3
"""A relative `cwd` on POST /tools/exec must mean the workspace's folder.

serve.py's _workspace_path exists for exactly one reason: a relative path
must anchor to the workspace root (CAFRESOHQ_ALLOWED_DIRS[0]), never to
wherever the server process happens to have been started. Every /fs route
and _tool_exec's own _resolve_arg go through it. The one door that reads a
`cwd` did not: it ran

    cwd_p = pathlib.Path(_client_path(req_cwd)).resolve()

which resolves 'docs' against the SERVER's cwd (the repo). That path is
outside the allowlist, so the whitelist loop matched nothing, `tool_cwd`
silently stayed at the workspace ROOT, and the request proceeded:

  FILE_WRITE arg='marker.txt' cwd='docs'  -> 200, written to <ws>/marker.txt
                                            (the caller asked for <ws>/docs/)
  DIR_LIST   arg=''          cwd='proj'   -> 200, listing of <ws>, not <ws>/proj

No error, no warning — a coworker's file lands in a directory nobody named
and the next FILE_READ of the same relative path reads a different one.

This boots the real serve.py from the repo root with an explicit
CAFRESOHQ_ALLOWED_DIRS pointing at a temp workspace, and uses 'docs' as the
relative cwd on purpose: it is a directory that EXISTS in the repo, so the
buggy resolve() finds a real dir and still throws the request at the wrong
place.
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
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("X-API-Key", "regression-test-key")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def exec_tool(base, **payload):
    st, body = request(base + "/tools/exec", "POST",
                       json.dumps(payload).encode())
    try:
        return st, json.loads(body.decode("utf-8"))
    except Exception:
        return st, {"raw": body[:200].decode("utf-8", "replace")}


def main():
    port = free_port()
    ws = tempfile.mkdtemp(prefix="cafresohq-toolcwd-")
    state_dir = tempfile.mkdtemp(prefix="cafresohq-toolcwd-state-")
    proc = None
    # 'docs' also exists in the repo (the server's own cwd) — that is the point.
    os.makedirs(os.path.join(ws, "docs"), exist_ok=True)
    os.makedirs(os.path.join(ws, "proj"), exist_ok=True)
    with open(os.path.join(ws, "proj", "only_here.txt"), "w") as f:
        f.write("workspace project file\n")

    repo_decoy = os.path.join(ROOT, "docs", "marker-from-tool-exec.txt")

    try:
        env = dict(os.environ)
        env.update({
            "CAFRESOHQ_API_KEY": "regression-test-key",
            "CAFRESOHQ_HQ_STATE_DIR": state_dir,
            "CAFRESOHQ_ALLOWED_DIRS": ws,
            "CAFRESOHQ_ALLOWED_TOOLS": "Read,Glob,Grep,Edit,Write",
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

        # 1. FILE_WRITE with a relative cwd lands inside the workspace's folder.
        st, res = exec_tool(base, tool="FILE_WRITE", arg="marker.txt",
                            cwd="docs", body="hello from the office\n")
        check("FILE_WRITE with relative cwd returned 200",
              st == 200 and res.get("ok"), f"{st} {res}")
        in_project = os.path.join(ws, "docs", "marker.txt")
        at_ws_root = os.path.join(ws, "marker.txt")
        check("the file landed in <workspace>/docs/, the folder named",
              os.path.isfile(in_project), f"result={res.get('result')!r}")
        check("nothing was written to the workspace ROOT instead",
              not os.path.exists(at_ws_root),
              f"stray file at {at_ws_root}")
        check("the server's own repo directory was untouched",
              not os.path.exists(repo_decoy), repo_decoy)

        # 2. FILE_READ of the same relative pair reads that same file back.
        st, res = exec_tool(base, tool="FILE_READ", arg="marker.txt", cwd="docs")
        check("FILE_READ with the same relative cwd reads it back",
              st == 200 and res.get("result") == "hello from the office\n"
              and not res.get("failed"), f"{st} {res}")

        # 3. DIR_LIST with a relative cwd lists that project, not the root.
        st, res = exec_tool(base, tool="DIR_LIST", arg="", cwd="proj")
        listing = res.get("result") or ""
        check("DIR_LIST with relative cwd lists <workspace>/proj",
              st == 200 and "only_here.txt" in listing, f"{st} {res}")
        check("DIR_LIST did not list the workspace root instead",
              "proj/" not in listing, f"listing={listing!r}")

        # 4. An absolute cwd inside the allowlist keeps working unchanged.
        st, res = exec_tool(base, tool="DIR_LIST", arg="",
                            cwd=os.path.join(ws, "proj"))
        check("absolute cwd inside the allowlist still works",
              st == 200 and "only_here.txt" in (res.get("result") or ""),
              f"{st} {res}")

        # 5. A cwd outside the allowlist is still refused the anchor (no escape).
        st, res = exec_tool(base, tool="DIR_LIST", arg="", cwd=ROOT)
        check("an out-of-allowlist absolute cwd does not escape the workspace",
              st == 200 and "serve.py" not in (res.get("result") or ""),
              f"{st} {res}")

    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        if os.path.exists(repo_decoy):
            os.remove(repo_decoy)
        subprocess.run(["rm", "-rf", ws, state_dir], check=False)

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {failures}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
