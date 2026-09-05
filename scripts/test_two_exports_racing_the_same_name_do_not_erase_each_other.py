#!/usr/bin/env python3
"""Two exports racing the same conventional name used to erase one of them.

exporters.py's `_vault_binary_path` picks the vault path every EXPORT_PPTX /
EXPORT_DOCX / EXPORT_PDF / EXPORT_IMAGE / EXPORT_VIDEO door writes to, and
until now it asked "is this name free?" with a bare `candidate.exists()`
check — fs_routes.free_name's shape — with the actual write (a pptx/docx/pdf
render, or an image-gen call that can sit on a provider's API for up to
three minutes) happening well AFTER, not inside the same atomic step. Two
callers naming the same conventional path — Sloan exporting `Slides/q3.pptx`
twice back to back, two coworkers both told to illustrate the same slide, or
a client retry-after-timeout that resubmits the identical export while the
first is still mid-render — could both see the name free, both proceed, and
whichever `write_bytes`/`.save()` landed last silently erased the other's
deliverable. Both requests still answered 200 with a `path` receipt; one of
those receipts pointed at a file that, moments later, held someone else's
work instead.

This is the exact bug fs_routes.claim_name exists to make unaskable for the
upload doors (`## 337.`-family), and free_name's own docstring says so in
as many words — the export doors just never got the fix.

Fix: `_vault_binary_path` now claims its answer the way claim_name claims a
name — O_CREAT|O_EXCL, before any rendering or network call starts — so a
second caller racing in behind it gets EEXIST and steps to the next numbered
variant instead of landing on the same path.

Round 1: structural — the source really goes through fs_routes.claim_name,
not fs_routes.free_name, and creates the placeholder before any provider
call. Round 2: direct concurrency — 60 threads calling
`exporters._vault_binary_path` for the identical name at once resolve to 60
DISTINCT paths, every one already claimed on disk the instant it's
returned. Round 3: full HTTP race — a real serve.py plus a scratch
"provider" (an /generate/image `a1111` call against a local mock server that
sleeps before answering, widening the window a real provider call already
has) — 10 concurrent /generate/image requests at ONE shared `path`, 5
rounds, checking every round that all ten succeed, ten distinct files land
on disk, and every response's own receipt path holds exactly the bytes that
response's own request produced (no cross-contamination, no loss). Round 4:
a plain single export is unaffected.

Run: python3 scripts/test_two_exports_racing_the_same_name_do_not_erase_each_other.py
"""
from __future__ import annotations

import base64
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok    " if cond else "  FAIL  ") + name
          + ((f"  — {detail}") if not cond and detail else ""))
    if not cond:
        FAILS.append(name)


# ── Round 1: structural ────────────────────────────────────────────────────
def structural_checks() -> None:
    print("round 1 — the fix is really in the source")
    src = open(os.path.join(ROOT, "exporters.py"), encoding="utf-8").read()
    m = re.search(
        r"def _vault_binary_path\(.*?\n(?=\ndef |\Z)", src, re.DOTALL)
    check("_vault_binary_path is still defined", bool(m))
    body = m.group(0) if m else ""
    check("it claims the name via fs_routes.claim_name (O_CREAT|O_EXCL)",
          "fs_routes.claim_name(" in body)
    check("it no longer resolves collisions with a bare exists() + free_name "
          "(the non-atomic shape this bug used to have)",
          "fs_routes.free_name(" not in body)
    check("the claimed placeholder's fd is closed (no fd leak — the actual "
          "write happens later, through the path, by the caller's own code)",
          "os.close(fd)" in body)


# ── Round 2: direct concurrency against the resolver itself ───────────────
def direct_race_checks() -> None:
    print("round 2 — many resolvers racing the identical name at once")
    import exporters  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as td:
        exporters._vault_root = lambda: td
        exporters._vault_hidden_part = lambda rel: None

        N = 60
        results: list = [None] * N

        def worker(i):
            results[i] = exporters._vault_binary_path(
                None, "Slides/deck.pptx", (".pptx",))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        names = [str(p) for p in results]
        check(f"all {N} concurrent resolutions succeeded",
              all(p is not None for p in results))
        check("…and every one resolved to a DIFFERENT path — no two callers "
              "were ever handed the same name to write into",
              len(set(names)) == N, f"only {len(set(names))} distinct of {N}")
        check("…and every resolved path is already claimed on disk (0 bytes, "
              "not merely a would-be name)",
              all(p.is_file() for p in results))


# ── Round 3: full HTTP race, real serve.py + a mock slow provider ─────────
def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def http_request(url, method="GET", body=None, headers=None):
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _make_mock_a1111(delay_s: float):
    """A tiny stand-in for an Automatic1111 server: /sdapi/v1/txt2img sleeps
    `delay_s` (mimicking real provider latency — the real thing can sit on
    this call for up to five minutes) then answers with one PNG-shaped image
    whose bytes are unique to the request's own 'prompt' field, so the test
    can tell whose image ended up on whose file afterward."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            length = int(self.headers.get("content-length", 0) or 0)
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            marker = (payload.get("prompt") or "?").encode("utf-8")
            time.sleep(delay_s)
            fake_png = b"\x89PNG\r\n\x1a\n" + marker * 200  # unique per request
            body = json.dumps(
                {"images": [base64.b64encode(fake_png).decode("ascii")]}
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def full_http_race_checks() -> None:
    print("round 3 — real serve.py, real concurrent /generate/image, one shared name")
    port = free_port()
    vault = tempfile.mkdtemp(prefix="cafresohq-export-race-vault-")
    state_dir = tempfile.mkdtemp(prefix="cafresohq-export-race-state-")
    proc = None
    mock = _make_mock_a1111(delay_s=0.4)
    try:
        env = dict(os.environ)
        env.update({
            "CAFRESOHQ_API_KEY": "regression-test-key",
            "CAFRESOHQ_HQ_STATE_DIR": state_dir,
            "CAFRESOHQ_VAULT": vault,
            "PORT": str(port),
            "GAP_CRON": "0", "NEWS_CRON": "0", "TOPICS_CRON": "0",
        })
        proc = subprocess.Popen(
            [sys.executable, "serve.py"], cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        base = f"http://127.0.0.1:{port}"
        headers = {"X-API-Key": "regression-test-key", "Content-Type": "application/json"}
        for _ in range(100):
            try:
                http_request(base + "/health")
                break
            except Exception:
                if proc.poll() is not None:
                    check("serve.py stayed up through startup", False, "exited early")
                    return
                time.sleep(0.1)
        else:
            check("serve.py became ready", False, "timed out")
            return

        mock_base = f"http://127.0.0.1:{mock.server_address[1]}"
        N = 10
        for rnd in range(5):
            results: list = [None] * N

            def worker(i, _rnd=rnd):
                markers = f"round{_rnd}-caller{i}"
                st, raw = http_request(
                    base + "/generate/image", "POST",
                    json.dumps({
                        "path": "Art/hero.png",
                        "prompt": markers,
                        "provider": "a1111",
                        "baseUrl": mock_base,
                    }).encode("utf-8"),
                    headers,
                )
                try:
                    results[i] = (st, json.loads(raw.decode("utf-8")), markers)
                except Exception:
                    results[i] = (st, {"raw": raw[:200]}, markers)

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            all_ok = all(st == 200 and isinstance(res, dict) and res.get("path")
                          for st, res, _ in results)
            paths = [res.get("path") for st, res, _ in results if isinstance(res, dict)]
            distinct_paths = len(set(paths))
            # every reported path must genuinely exist and hold THIS caller's
            # own marker — never a sibling's, and never nothing.
            content_intact = True
            for st, res, marker in results:
                if not (st == 200 and isinstance(res, dict) and res.get("path")):
                    content_intact = False
                    continue
                fpath = os.path.join(vault, res["path"])
                if not os.path.isfile(fpath):
                    content_intact = False
                    continue
                data = open(fpath, "rb").read()
                if marker.encode("utf-8") not in data:
                    content_intact = False
            print(f"    round {rnd}: all_200={all_ok} distinct_files={distinct_paths}/{N} "
                  f"content_intact={content_intact}")
            check(f"round {rnd}: all {N} concurrent exports to one shared "
                  "name succeeded",
                  all_ok, str([r for r in results if r[0] != 200]))
            check(f"round {rnd}: {N} distinct files landed on disk — no two "
                  "callers shared a path",
                  distinct_paths == N, f"only {distinct_paths}")
            check(f"round {rnd}: every response's own file holds exactly its "
                  "own caller's bytes — nothing spliced or overwritten",
                  content_intact)
    finally:
        mock.shutdown()
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        subprocess.run(["rm", "-rf", vault, state_dir], check=False)


# ── Round 4: plain sanity — a single export is unaffected ─────────────────
def plain_sanity_checks() -> None:
    print("round 4 — a plain single export still works")
    import exporters  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as td:
        exporters._vault_root = lambda: td
        exporters._vault_hidden_part = lambda rel: None
        out = exporters._vault_binary_path(None, "Notes/plain.png", (".png",))
        check("a fresh single resolution lands on the asked-for name",
              out.name == "plain.png", out.name)
        out.write_bytes(b"just one file, no race")
        check("…and the write it enables reads back correctly",
              out.read_bytes() == b"just one file, no race")


def main() -> int:
    print("two exports racing the same name do not erase each other")
    structural_checks()
    direct_race_checks()
    full_http_race_checks()
    plain_sanity_checks()

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED — " + ", ".join(FAILS[:10]))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
