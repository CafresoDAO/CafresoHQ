#!/usr/bin/env python3
"""A refused export used to file an empty deliverable anyway.

`exporters._vault_binary_path` CLAIMS its answer on disk — O_CREAT|O_EXCL, a
real zero-byte file — before any rendering or provider call starts. That is
correct and deliberate: `test_two_exports_racing_the_same_name_do_not_erase_
each_other.py` is the entry that put it there, because two exports naming the
same path must not be able to erase one another.

What was missing is the other half of the transaction. All five doors
(/export/pptx, /export/docx, /export/pdf, /generate/image, /generate/video)
claim first and can then fail for a dozen ordinary reasons — no provider key,
a provider that is not running, a missing render library, a refusal from
upstream — and every one of those failures left the claim behind. The door
answered 4xx/5xx, the toast said so, and a file the boss never asked for was
sitting in the Library at zero bytes with nothing anywhere saying it existed.

Measured before the fix, on a real serve.py with no provider keys set — which
is the ORDINARY first-run state, since the office ships with no credentials
at all — three refused `/generate/image` calls for `Art/hero.png`:

    HTTP 400 {"error": "OPENAI_API_KEY required"}   vault: hero.png (0 bytes)
    HTTP 400 {"error": "OPENAI_API_KEY required"}   vault: + hero (2).png
    HTTP 400 {"error": "OPENAI_API_KEY required"}   vault: + hero (3).png

so the fourth attempt — the one that finally works, after the tester sets the
key — is filed as `hero (4).png`. The husks win the very race the claim
exists to settle: each one falsely holds the name against the next caller,
and the boss's own deck still points at `hero.png`, which is now a zero-byte
file that renders as a broken image.

Fix (#401): `_unfilled_claim_is_not_a_deliverable`, the export doors' copy of
the move `fs_routes._fs_rename_unclaim` already makes for /fs/rename — undo a
claimed-but-never-filled destination "so a failed rename does not leave a
phantom empty file/folder behind at `to` (which would then itself falsely win
the next claim)". Zero bytes is a measurement, not a guess: every door ends
by writing its rendered bytes into the claim, so a claim still empty when the
door returns is one no deliverable ever reached.

Round 1 is structural and GENERAL rather than pinned to five names: every
function in exporters.py that resolves a vault path through
`self._vault_binary_path(` must carry the guard, so a sixth door added later
fails this check instead of quietly reintroducing the bug.

Round 2 drives a real serve.py on its own free port with an empty temp vault
and every provider key stripped from the environment, and asserts one
INVARIANT over every refusal it can reach without a credential: a door that
does not answer 2xx leaves the vault byte-for-byte as it found it. Round 3
proves the other side — a door that SUCCEEDS still files its deliverable, and
still steps aside onto a numbered variant when the name is genuinely taken.

Run: python3 scripts/test_an_export_that_failed_leaves_nothing_in_the_library.py
"""
from __future__ import annotations

import ast
import base64
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
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILS: list[str] = []

GUARD = '_unfilled_claim_is_not_a_deliverable'


def check(name: str, cond: bool, detail: str = '') -> None:
    print(('  ok    ' if cond else '  FAIL  ') + name
          + ((f'  — {detail}') if not cond and detail else ''))
    if not cond:
        FAILS.append(name)


# ── Round 1: structural, and general over every door ───────────────────────
def structural_checks() -> None:
    print('round 1 — every door that claims a name also owns the undo')
    src = open(os.path.join(ROOT, 'exporters.py'), encoding='utf-8').read()
    tree = ast.parse(src)

    guard = next((n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == GUARD), None)
    check(f'{GUARD} exists', guard is not None)

    remember = next((n for n in tree.body
                     if isinstance(n, ast.FunctionDef)
                     and n.name == '_remember_claim'), None)
    check('_remember_claim exists', remember is not None)

    # _vault_binary_path must actually register what it claimed.
    vbp = next((n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == '_vault_binary_path'), None)
    check('_vault_binary_path is still defined', vbp is not None)
    if vbp is not None:
        calls = [c for c in ast.walk(vbp) if isinstance(c, ast.Call)
                 and isinstance(c.func, ast.Name)]
        names = [c.func.id for c in calls]
        check('_vault_binary_path registers its claim with _remember_claim',
              '_remember_claim' in names, str(sorted(set(names))))
        # It must still CLAIM, not merely check — the race fix this builds on.
        check('…and still claims the name through fs_routes.claim_name '
              '(the race fix is untouched)',
              'claim_name' in src[vbp.lineno:] or 'fs_routes.claim_name' in src)

    # The general half: any function resolving a vault path through
    # self._vault_binary_path( is a door, and every door must be guarded.
    doors, unguarded = [], []
    for n in tree.body:
        if not isinstance(n, ast.FunctionDef):
            continue
        uses_vbp = any(
            isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
            and c.func.attr == '_vault_binary_path'
            for c in ast.walk(n))
        if not uses_vbp:
            continue
        doors.append(n.name)
        decorated = any(
            (isinstance(d, ast.Name) and d.id == GUARD)
            or (isinstance(d, ast.Attribute) and d.attr == GUARD)
            for d in n.decorator_list)
        if not decorated:
            unguarded.append(n.name)
    check('every door found (all five export/generate endpoints)',
          len(doors) >= 5, str(doors))
    check('EVERY function that claims a vault path carries the guard — a '
          'sixth door added later fails here rather than filing husks',
          not unguarded, 'unguarded: ' + str(unguarded))

    # The guard must not swallow the door's own answer.
    if guard is not None:
        body = ast.get_source_segment(src, guard) or ''
        check('the guard returns the door\'s own response unchanged',
              'return door(' in body)
        check('…and does its cleanup in a finally, so a door that raises is '
              'cleaned up too', 'finally:' in body)
        check('…and only removes a claim that is still ZERO bytes',
              'st_size == 0' in body)


# ── plumbing ───────────────────────────────────────────────────────────────
def free_port() -> int:
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def http_request(url, method='GET', body=None, headers=None):
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _make_mock_a1111():
    """A stand-in Automatic1111 that answers with one PNG-shaped image whose
    bytes carry the request's own prompt, so round 3 can tell a real
    deliverable from a husk."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            length = int(self.headers.get('content-length', 0) or 0)
            payload = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
            marker = (payload.get('prompt') or '?').encode('utf-8')
            fake_png = b'\x89PNG\r\n\x1a\n' + marker * 100
            body = json.dumps(
                {'images': [base64.b64encode(fake_png).decode('ascii')]}
            ).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = HTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def vault_listing(vault: str) -> list:
    out = []
    for r, _d, files in os.walk(vault):
        for f in files:
            p = os.path.join(r, f)
            out.append((os.path.relpath(p, vault), os.path.getsize(p)))
    return sorted(out)


# Every refusal reachable with no credential of any kind. Deliberately fake
# keys/URLs only — nothing here reads a real one.
REFUSALS = [
    ('/generate/image', {'path': 'Art/hero.png', 'prompt': 'a cat',
                         'provider': 'openai'},
     'image, openai, no key'),
    ('/generate/image', {'path': 'Art/hero.png', 'prompt': 'a cat',
                         'provider': 'openai'},
     'image, openai, no key (retry — the name must still be free)'),
    ('/generate/image', {'path': 'Art/hero.png', 'prompt': 'a cat',
                         'provider': 'openai'},
     'image, openai, no key (retry 2)'),
    ('/generate/image', {'path': 'Art/hero.png', 'prompt': 'a cat',
                         'provider': 'google'},
     'image, google, no key'),
    ('/generate/image', {'path': 'Art/dragon.png', 'prompt': 'x',
                         'provider': 'a1111', 'baseUrl': 'http://127.0.0.1:9'},
     'image, a1111 not running'),
    ('/generate/image', {'path': 'Art/dragon.png', 'prompt': 'x',
                         'provider': 'nosuchprovider'},
     'image, unsupported provider'),
    ('/generate/video', {'path': 'Clips/promo.mp4', 'prompt': 'x',
                         'provider': 'openai'},
     'video, openai (Sora not wired)'),
    ('/generate/video', {'path': 'Clips/promo.mp4', 'prompt': 'x',
                         'provider': 'fal'},
     'video, fal, no key'),
    ('/generate/video', {'path': 'Clips/promo.mp4', 'prompt': 'x',
                         'provider': 'comfyui', 'baseUrl': 'http://127.0.0.1:9'},
     'video, comfyui not running'),
]


# ── Round 2: the invariant, on a real server ───────────────────────────────
def refusal_leaves_nothing_checks() -> None:
    print('round 2 — a real serve.py: no door that refuses may leave a file')
    port = free_port()
    vault = tempfile.mkdtemp(prefix='cafresohq-husk-vault-')
    state_dir = tempfile.mkdtemp(prefix='cafresohq-husk-state-')
    proc = None
    try:
        env = dict(os.environ)
        env.update({
            'CAFRESOHQ_API_KEY': 'regression-test-key',
            'CAFRESOHQ_HQ_STATE_DIR': state_dir,
            'CAFRESOHQ_VAULT': vault,
            'PORT': str(port),
            'GAP_CRON': '0', 'NEWS_CRON': '0', 'TOPICS_CRON': '0',
        })
        # An unkeyed office is the ordinary first-run state and the one this
        # bug is worst on. Strip anything this machine happens to have set —
        # the test must never touch a real credential.
        for k in ('OPENAI_API_KEY', 'GOOGLE_API_KEY', 'GEMINI_API_KEY',
                  'FAL_KEY', 'ANTHROPIC_API_KEY'):
            env.pop(k, None)
        proc = subprocess.Popen(
            [sys.executable, 'serve.py'], cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f'http://127.0.0.1:{port}'
        headers = {'X-API-Key': 'regression-test-key',
                   'Content-Type': 'application/json'}
        for _ in range(150):
            try:
                http_request(base + '/health')
                break
            except Exception:
                if proc.poll() is not None:
                    check('serve.py stayed up through startup', False,
                          'exited early')
                    return
                time.sleep(0.1)
        else:
            check('serve.py became ready', False, 'timed out')
            return

        # Also exercise the two export doors. Whether the render libraries
        # are installed on this machine decides whether they 503 or 200; the
        # invariant below only speaks about the non-2xx answers, so either
        # outcome is a legitimate observation rather than a skip.
        probes = list(REFUSALS) + [
            ('/export/pptx', {'path': 'Slides/q3.pptx', 'content': ''},
             'pptx, empty content'),
            ('/export/pptx', {'path': 'Slides/q3.pptx',
                              'content': '## Slide 1: Hi\n- a\n'}, 'pptx'),
            ('/export/docx', {'path': 'Docs/memo.docx',
                              'content': '# Memo\n\nbody\n'}, 'docx'),
            ('/export/pdf', {'path': 'Docs/memo.pdf',
                             'content': '# Memo\n\nbody\n'}, 'pdf'),
        ]

        refusals_seen = 0
        for path, payload, label in probes:
            before = vault_listing(vault)
            st, raw = http_request(base + path, 'POST',
                                   json.dumps(payload).encode('utf-8'), headers)
            after = vault_listing(vault)
            answer = raw[:120].decode('utf-8', 'replace')
            if 200 <= st < 300:
                print(f'    {label}: HTTP {st} (succeeded on this machine — '
                      f'not a refusal, skipped)')
                continue
            refusals_seen += 1
            print(f'    {label}: HTTP {st} {answer}  vault {before} -> {after}')
            check(f'refused ({label}) — the Library is exactly as it was',
                  after == before, f'gained {sorted(set(after) - set(before))}')
            check(f'refused ({label}) — and the office told the tester why',
                  bool(json.loads(raw or b'{}').get('error')), answer)

        check('the run actually exercised refusals (the invariant above is '
              'not vacuous)', refusals_seen >= 8, f'only {refusals_seen}')
        check('after every refusal the vault is still completely empty — the '
              'name the boss asked for was never burned',
              vault_listing(vault) == [], str(vault_listing(vault)))
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        subprocess.run(['rm', '-rf', vault, state_dir], check=False)


# ── Round 3: the other side — a door that works still files its work ───────
def success_still_files_checks() -> None:
    print('round 3 — a door that SUCCEEDS still files, and still steps aside')
    port = free_port()
    vault = tempfile.mkdtemp(prefix='cafresohq-husk-ok-vault-')
    state_dir = tempfile.mkdtemp(prefix='cafresohq-husk-ok-state-')
    proc = None
    mock = _make_mock_a1111()
    try:
        env = dict(os.environ)
        env.update({
            'CAFRESOHQ_API_KEY': 'regression-test-key',
            'CAFRESOHQ_HQ_STATE_DIR': state_dir,
            'CAFRESOHQ_VAULT': vault,
            'PORT': str(port),
            'GAP_CRON': '0', 'NEWS_CRON': '0', 'TOPICS_CRON': '0',
        })
        proc = subprocess.Popen(
            [sys.executable, 'serve.py'], cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f'http://127.0.0.1:{port}'
        headers = {'X-API-Key': 'regression-test-key',
                   'Content-Type': 'application/json'}
        for _ in range(150):
            try:
                http_request(base + '/health')
                break
            except Exception:
                if proc.poll() is not None:
                    check('serve.py stayed up through startup', False,
                          'exited early')
                    return
                time.sleep(0.1)
        else:
            check('serve.py became ready', False, 'timed out')
            return

        mock_base = f'http://127.0.0.1:{mock.server_address[1]}'

        def gen(prompt):
            return http_request(
                base + '/generate/image', 'POST',
                json.dumps({'path': 'Art/hero.png', 'prompt': prompt,
                            'provider': 'a1111',
                            'baseUrl': mock_base}).encode('utf-8'),
                headers)

        # A refusal FIRST, so the success below is the retry a tester makes
        # after fixing whatever was wrong. Pre-fix this is the exact sequence
        # that filed the good image as `hero (2).png`.
        http_request(base + '/generate/image', 'POST',
                     json.dumps({'path': 'Art/hero.png', 'prompt': 'x',
                                 'provider': 'a1111',
                                 'baseUrl': 'http://127.0.0.1:9'}
                                ).encode('utf-8'), headers)

        st, raw = gen('first-real-image')
        res = json.loads(raw.decode('utf-8'))
        check('the retry after a failure succeeds', st == 200, raw[:160])
        check('…and is filed under the name the boss actually asked for, not '
              'a variant bumped past the earlier failure\'s husk',
              res.get('path') == 'Art/hero.png', str(res.get('path')))
        p = os.path.join(vault, res.get('path') or 'x')
        check('…and the file holds this run\'s own bytes',
              os.path.isfile(p)
              and b'first-real-image' in open(p, 'rb').read())

        # A genuine collision must still step aside — the race fix stands.
        st2, raw2 = gen('second-real-image')
        res2 = json.loads(raw2.decode('utf-8'))
        check('a SECOND export of the same name still steps aside instead of '
              'replacing the first', res2.get('path') == 'Art/hero (2).png',
              str(res2.get('path')))
        check('…and the first deliverable is untouched',
              open(os.path.join(vault, 'Art/hero.png'), 'rb').read()
              .count(b'first-real-image') > 0)
        check('exactly two files in the Library — the two real ones',
              len(vault_listing(vault)) == 2, str(vault_listing(vault)))
    finally:
        mock.shutdown()
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        subprocess.run(['rm', '-rf', vault, state_dir], check=False)


def main() -> int:
    structural_checks()
    refusal_leaves_nothing_checks()
    success_still_files_checks()
    print()
    if FAILS:
        print(f'{len(FAILS)} check(s) failed:')
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
