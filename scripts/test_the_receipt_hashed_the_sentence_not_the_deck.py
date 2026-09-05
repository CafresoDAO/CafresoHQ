#!/usr/bin/env python3
"""The on-chain receipt for a deck hashed the sentence about it.

`recordToolReceipt` files a deliverable receipt for every EXPORT_/GENERATE_
tool that lands, and `anchorWorkReceipt` (app.jsx) writes that receipt
on-chain with two fields: `argHash` and `contentSha256`. Its own comment
says what the second one is meant to be — "real file bytes off /fs/file for
exports/media, the result/arg text otherwise" — and the branch that reaches
for the bytes was fetching the wrong door.

`/fs/file` resolves its `path` through `fs_routes._workspace_path` and then
refuses anything outside CAFRESOHQ_ALLOWED_DIRS. Every EXPORT_/GENERATE_
tool files into the LIBRARY: `exporters._vault_binary_path`, under
CAFRESOHQ_VAULT, which is a different tree and deliberately not inside the
workspace sandbox. Measured on a real serve.py with a deck sitting in the
Library at `Slides/q3.pptx` (round 1 below re-measures it every run):

    GET /fs/file?path=Slides/q3.pptx     404 {"error": "no such file"}
    GET /vault/file?path=Slides/q3.pptx  200 PK\x03\x04…

So the fetch could never succeed for the tools the branch exists for, and
`if (r.ok)` is silent when it doesn't: `content` stayed as `ev.result` and
`contentSha256` went on-chain as the sha256 of the tool's own SENTENCE —
"Saved PowerPoint (5 slides) → Slides/q3.pptx" — for every deck, document,
PDF, image and video the office has ever anchored. Nothing on the receipt,
in the tray, or on-chain distinguishes that from a genuine content hash of
the deliverable, and a boss checking one against the file it names could
never make them agree.

Fix (#410): fetch `/vault/file`, and address it by `ev.arg` — which is
already `meta.filedAs`, the path the SERVER saved to (#180) — falling back
to the sentence-scrape only when `arg` is empty.

Round 1 is the door measurement, on a real serve.py on its own free port
with a temp Library and a temp workspace: an artifact in the Library is
served by /vault/file and is NOT reachable through /fs/file.

Round 2 is the behaviour, on the real lifted `anchorWorkReceipt` + `sha256Hex`
bodies under node, driven against a stub `fetch` that answers exactly as the
server did in round 1. It asserts the anchored `contentSha256` is the hash of
the DECK BYTES, that it is not the hash of the result sentence, and — so the
check cannot pass vacuously — that those two hashes differ. A third arm
proves the non-export path is untouched: VAULT_NEW still anchors the text.

Run: python3 scripts/test_the_receipt_hashed_the_sentence_not_the_deck.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_RAW = (ROOT / 'app.jsx').read_text(encoding='utf-8')

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = '') -> None:
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond and detail else ''))
    if not cond:
        FAILS.append(name)


def lift_arrow(src: str, decl: str) -> str:
    """Lift `const <name> = async (...) => { ... }` by brace-matching its body.

    Returns '' rather than raising when the declaration is absent, so a
    rename shows up as a clean FAIL on every arm instead of a traceback that
    reports nothing about the rest of the file.
    """
    i = src.find(decl)
    if i < 0:
        return ''
    j = src.find('=> {', i)
    if j < 0:
        return ''
    depth = 0
    for k in range(j + 3, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1] + ';'
    return ''


# ── Round 1: which door actually holds an exported deliverable ─────────────
def free_port() -> int:
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def http_get(url: str, key: str):
    req = urllib.request.Request(url, headers={'X-API-Key': key})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def door_checks() -> None:
    print('round 1 — a real serve.py: which door holds an exported deliverable')
    port = free_port()
    vault = tempfile.mkdtemp(prefix='cafresohq-rcpt-vault-')
    state = tempfile.mkdtemp(prefix='cafresohq-rcpt-state-')
    workspace = tempfile.mkdtemp(prefix='cafresohq-rcpt-ws-')
    proc = None
    try:
        env = dict(os.environ)
        env.update({
            'CAFRESOHQ_API_KEY': 'regression-test-key',
            'CAFRESOHQ_HQ_STATE_DIR': state,
            'CAFRESOHQ_VAULT': vault,
            'CAFRESOHQ_ALLOWED_DIRS': workspace,
            'PORT': str(port),
            'GAP_CRON': '0', 'NEWS_CRON': '0', 'TOPICS_CRON': '0',
        })
        # No credential of any kind reaches this child.
        for k in ('OPENAI_API_KEY', 'GOOGLE_API_KEY', 'GEMINI_API_KEY',
                  'FAL_KEY', 'ANTHROPIC_API_KEY', 'BRAVE_API_KEY'):
            env.pop(k, None)
        proc = subprocess.Popen(
            [sys.executable, 'serve.py'], cwd=str(ROOT), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f'http://127.0.0.1:{port}'
        for _ in range(150):
            try:
                http_get(base + '/health', 'regression-test-key')
                break
            except Exception:
                if proc.poll() is not None:
                    check('serve.py stayed up through startup', False, 'exited early')
                    return
                time.sleep(0.1)
        else:
            check('serve.py became ready', False, 'timed out')
            return

        # An exported deck, where the exporters put one: in the Library.
        deck = Path(vault) / 'Slides' / 'q3.pptx'
        deck.parent.mkdir(parents=True, exist_ok=True)
        deck.write_bytes(b'PK\x03\x04fake-deck-bytes-for-the-hash')

        fs_status, fs_body = http_get(
            base + '/fs/file?path=Slides%2Fq3.pptx', 'regression-test-key')
        vt_status, vt_body = http_get(
            base + '/vault/file?path=Slides%2Fq3.pptx', 'regression-test-key')
        print(f'    GET /fs/file?path=Slides/q3.pptx     {fs_status} {fs_body[:60]!r}')
        print(f'    GET /vault/file?path=Slides/q3.pptx  {vt_status} {vt_body[:60]!r}')

        check('/vault/file serves the exported deliverable',
              vt_status == 200 and vt_body == deck.read_bytes(),
              f'status {vt_status}')
        check('/fs/file cannot reach a Library path at all',
              fs_status != 200,
              f'status {fs_status} — the workspace door reached the vault?')
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()


# ── Round 2: the real anchorWorkReceipt, driven ────────────────────────────
HARNESS = r'''
const DECK = new Uint8Array([0x50,0x4b,0x03,0x04,102,97,107,101,45,100,101,99,107]);
const SENTENCE = 'Saved PowerPoint (5 slides) → Slides/q3.pptx';

let fetched = [];
globalThis.fetch = async (url) => {
  fetched.push(String(url));
  const u = String(url);
  /* Exactly what the real server answered in round 1: the workspace door
     cannot see a Library path; the Library door serves the bytes. */
  if (u.indexOf('/vault/file?') >= 0 && u.indexOf('Slides%2Fq3.pptx') >= 0) {
    return { ok: true, arrayBuffer: async () => DECK.buffer.slice(0) };
  }
  return { ok: false, status: 404, arrayBuffer: async () => new ArrayBuffer(0) };
};

const CafresoHQClient = { backendBase: () => 'http://127.0.0.1:9999' };
let anchored = null;
const CafresoHQChain = {
  isAvailable: () => true,
  receipt: { put: async (rec) => { anchored = rec; return { id: 7, verifyUrl: 'x' }; } },
};
const setReceipts = () => {};
const logActivity = () => {};

__LIFTED__

const hex = async (bytes) => {
  const d = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(d), b => b.toString(16).padStart(2, '0')).join('');
};

const agent = { id: 'a1', name: 'Sloan', elevated: false };
const out = {};

anchored = null; fetched = [];
await anchorWorkReceipt(agent, {
  phase: 'done', name: 'EXPORT_PPTX', arg: 'Slides/q3.pptx',
  result: SENTENCE, failed: false,
}, 'rc1', 'Exported Slides/q3.pptx');
out.exportAnchored = anchored;
out.exportFetched = fetched;
out.deckHash = await hex(DECK);
out.sentenceHash = await hex(new TextEncoder().encode(SENTENCE));

anchored = null; fetched = [];
await anchorWorkReceipt(agent, {
  phase: 'done', name: 'VAULT_NEW', arg: 'Research/x.md',
  result: 'Wrote 40 chars → Research/x.md', failed: false,
}, 'rc2', 'Wrote Research/x.md');
out.vaultAnchored = anchored;
out.vaultFetched = fetched;
out.vaultTextHash = await hex(new TextEncoder().encode('Wrote 40 chars → Research/x.md'));

console.log(JSON.stringify(out));
'''


def anchor_checks() -> None:
    print('round 2 — the real anchorWorkReceipt, driven under node')
    sha = lift_arrow(APP_RAW, 'const sha256Hex = async (data) =>')
    anchor = lift_arrow(APP_RAW, 'const anchorWorkReceipt = async (agent, ev, rcId, title) =>')
    check('sha256Hex lifted out of app.jsx', bool(sha))
    check('anchorWorkReceipt lifted out of app.jsx', bool(anchor))
    if not (sha and anchor):
        return

    src = HARNESS.replace('__LIFTED__', sha + '\n' + anchor)
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / 'anchor.mjs'
        f.write_text(src, encoding='utf-8')
        p = subprocess.run([_node(), str(f)], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        check('the harness ran', False, (p.stderr or p.stdout)[-400:])
        return
    check('the harness ran', True)
    try:
        out = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception as e:
        check('the harness printed a result', False, f'{e}: {p.stdout[-300:]}')
        return

    exp = out.get('exportAnchored') or {}
    fetched = out.get('exportFetched') or []
    print('    fetched: ' + json.dumps(fetched))
    print('    anchored contentSha256: ' + str(exp.get('contentSha256'))[:16] + '…')
    print('    deck bytes sha256:      ' + str(out.get('deckHash'))[:16] + '…')
    print('    result sentence sha256: ' + str(out.get('sentenceHash'))[:16] + '…')

    # Non-vacuous: the two candidate hashes must not coincide, or the
    # assertion below could pass without distinguishing anything.
    check('the deck hash and the sentence hash differ',
          out.get('deckHash') and out.get('deckHash') != out.get('sentenceHash'))
    check('an export anchors the DECK BYTES as contentSha256',
          exp.get('contentSha256') == out.get('deckHash'),
          f"got {exp.get('contentSha256')}")
    check('an export does not anchor the hash of its own sentence',
          exp.get('contentSha256') != out.get('sentenceHash'))
    check('the export reached the Library door',
          any('/vault/file?' in u for u in fetched), json.dumps(fetched))
    check('the export did not ask the workspace door',
          not any('/fs/file?' in u for u in fetched), json.dumps(fetched))
    check('the anchor still carries the tool and the agent',
          exp.get('tool') == 'EXPORT_PPTX' and exp.get('agentName') == 'Sloan')

    vault = out.get('vaultAnchored') or {}
    check('a VAULT_NEW anchor is unchanged — still the result text, no fetch',
          vault.get('contentSha256') == out.get('vaultTextHash')
          and not (out.get('vaultFetched') or []),
          f"{vault.get('contentSha256')} / {out.get('vaultFetched')}")


def _node() -> str:
    return os.environ.get('NODE', 'node')


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    door_checks()
    anchor_checks()
    print()
    if FAILS:
        print(f'{len(FAILS)} check(s) failed: ' + ', '.join(FAILS))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
