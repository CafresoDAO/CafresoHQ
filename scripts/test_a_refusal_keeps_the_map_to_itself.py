#!/usr/bin/env python3
"""The refusal that guards the sandbox handed out its map.

Measured 2026-08-15 on office 9261, no key supplied:

    GET /fs/browse?path=/etc      403  {"error": "...", "allowed": [<every
    GET /fs/file?path=/etc/hosts  403   configured directory, in full>]}

The /fs read routes are deliberately keyless — serve.py's own comment says
the allowed-dirs boundary "caps the read routes instead", and #79 made that
boundary answer first so a refusal stops being an existence oracle. But the
refusal BODY still carried 'allowed': the complete configured directory
list, served to precisely the caller who had just proved they were asking
about paths they were never allowed to ask about. On a real install that
list is the boss's project and client directories, free to any local
process with no key.

Nothing consumed the field: the picker popup prints only `error`, and no
script or runner reads `allowed` from these responses. The one reader
entitled to the list — the authenticated shell's settings panel — gets it
from /cafresohq/status, which sits behind the API key.

The fix drops the field from both refusal bodies. The refusal names the
rule, never the territory.

What this does NOT close (recorded, not hidden): /fs/browse with no path
still defaults to the FIRST allowed directory and lists it, keyless —
that is the picker's door and the design's documented trade. An outsider
can still learn root one by walking through it; what they no longer get
is the full map bundled with every refusal.

Run: python3 scripts/test_a_refusal_keeps_the_map_to_itself.py
"""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FS = ROOT / 'fs_routes.py'
SERVE = ROOT / 'serve.py'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    return re.sub(r'^\s*#.*$', '', src, flags=re.M)


def send_json_spans(src):
    """Yield the balanced-paren argument span of every _send_json call."""
    for m in re.finditer(r'_send_json\(', src):
        i = m.end() - 1
        d = 0
        for k in range(i, len(src)):
            if src[k] == '(':
                d += 1
            elif src[k] == ')':
                d -= 1
                if d == 0:
                    yield src[m.start():k + 1]
                    break


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def fetch(url):
    """Return (status, raw_body_str)."""
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception:
        return 0, ''


def q(p):
    return urllib.parse.quote(str(p), safe='')


def main():
    print('a refusal keeps the map to itself')

    fs = strip_comments(FS.read_text(encoding='utf-8'))

    # ── 1. the sweep: no response body in the module carries the list ───
    # Stated over EVERY _send_json call rather than the two that were
    # wrong, for #79's reason: naming the doors passes a file whose next
    # door repeats the defect.
    offenders = [span[:90] for span in send_json_spans(fs)
                 if '_cafresohq_allowed_dirs' in span]
    check('no fs response body carries the allow-list',
          not offenders,
          [offenders, '— the refusal names the rule, never the territory'])
    check('the allowed key itself is gone from the module',
          "'allowed'" not in fs and '"allowed"' not in fs,
          'a response key nothing reads, on a keyless route, was pure leak')

    # ── 2. the entitled door still exists, behind the key ───────────────
    serve = SERVE.read_text(encoding='utf-8')
    check('the authenticated shell still gets the list from /cafresohq/status',
          "'allowedDirs'" in serve,
          'dropping the leak must not orphan the settings panel')
    prefixes = serve[serve.index('_KEY_PROTECTED_PREFIXES = ('):]
    prefixes = prefixes[:prefixes.index(')\n')]
    check('...and that door is in the key-protected set',
          "'/cafresohq'" in prefixes, prefixes[:200])

    # ── 3. drive a real server: what an outsider actually receives ──────
    tmp = tempfile.mkdtemp(prefix='hqmap-')
    ws = Path(tmp) / 'ws-SENTINEL-ROOT'
    (ws / 'sub').mkdir(parents=True)
    (ws / 'ok.txt').write_text('hi', encoding='utf-8')

    port = free_port()
    env = dict(os.environ,
               CAFRESOHQ_ALLOWED_DIRS=str(ws),
               CAFRESOHQ_HQ_STATE_DIR=str(Path(tmp) / 'state'),
               CAFRESOHQ_API_KEY='test-key-not-supplied-below',
               PORT=str(port))
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=str(ROOT),
                            env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT)
    base = 'http://127.0.0.1:%d' % port
    try:
        for _ in range(80):
            if fetch(base + '/fs/browse?path=' + q(ws))[0]:
                break
            time.sleep(0.25)
        else:
            check('the server came up', False, 'never answered')
            return 1

        outside_cases = {
            '/fs/browse, an existing dir':  '/fs/browse?path=' + q('/etc'),
            '/fs/file, an existing file':   '/fs/file?path=' + q('/etc/hosts'),
            '/fs/file, an absent path':     '/fs/file?path=' + q('/etc/zzz-nope'),
        }
        bodies = {}
        for label, path in outside_cases.items():
            code, body = fetch(base + path)
            bodies[label] = body
            check('%s refuses without the map' % label,
                  code == 403
                  and 'SENTINEL-ROOT' not in body
                  and str(ws) not in body,
                  [code, body[:160]])
            try:
                keys = sorted(json.loads(body).keys())
            except Exception:
                keys = ['<unparseable>']
            check('...and says nothing but the rule',
                  keys == ['error'], keys)

        # The body must not become the oracle the status code stopped being
        # (#79): every outside refusal on the same route reads identically.
        check('outside refusals are word-for-word identical across paths',
              bodies['/fs/file, an existing file']
              == bodies['/fs/file, an absent path'],
              [bodies['/fs/file, an existing file'][:80],
               bodies['/fs/file, an absent path'][:80]])

        # ── 4. the doors that are owed answers still get them ───────────
        code, body = fetch(base + '/fs/browse?path=' + q(ws))
        check('inside the sandbox, browse still serves the listing',
              code == 200 and 'ok.txt' in body, [code, body[:120]])
        code, body = fetch(base + '/fs/browse')
        check('the picker default start still opens at the first root',
              code == 200 and 'SENTINEL-ROOT' in body,
              [code, '— the design trade this suite records: root one is '
               'the picker\'s door, not part of this leak'])
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    print()
    if FAILS:
        print('map-leak: %d FAILED — ' % len(FAILS) + ', '.join(FAILS[:3]))
        return 1
    print('map-leak: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
