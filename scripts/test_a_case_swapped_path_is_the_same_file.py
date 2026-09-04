#!/usr/bin/env python3
"""A case-swapped path is the same file.

`_static_path_allowed` gates serve.py's key-exempt static fallthrough with
string checks: `endswith('.py')` refuses source, a `startswith(state_root)`
refuses the state dir. But the strings it inspects are the path AS THE
CALLER SPELLED IT, while the filesystem underneath — macOS/APFS by default,
Windows always — opens names case-insensitively. The gate and the open()
disagreed about what "the same file" means.

Measured live on the dev Mac (no API key supplied, canonical paths 404):

    GET /serve.PY              → 200  (this file's source)
    GET /Serve.pY              → 200
    GET /HQ-STATE/tls/key.pem  → 200  (the TLS private key; the vault and
                                       every state JSON are one sibling
                                       request away)

The fix casefolds rules (b) and (c) before comparing. Conservative in the
other direction: on a case-SENSITIVE filesystem a folded match can only
refuse more (a file differing solely in case — none ships), never serve
more.

Probed two ways: the gate function itself (deterministic on any fs), and
the REAL server over actual HTTP, the way an attacker would.

Run: python3 scripts/test_a_case_swapped_path_is_the_same_file.py
"""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def status(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:                                    # noqa: BLE001
        return str(e)


def main():
    print('static fallthrough — case games do not rename the secrets')
    state = tempfile.mkdtemp(dir=ROOT, prefix='hq-state-casetest-')
    state_name = os.path.basename(state)
    swapped_state = state_name.swapcase()
    try:
        os.makedirs(os.path.join(state, 'tls'), exist_ok=True)
        with open(os.path.join(state, 'tls', 'key.pem'), 'w') as f:
            f.write('TEST-PRIVATE-KEY\n')

        # ── Half 1: the gate function itself, deterministic on any fs ────
        os.environ['CAFRESOHQ_HQ_STATE_DIR'] = state
        sys.path.insert(0, str(ROOT))   # serve.py imports sibling modules
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'serve_under_test', str(ROOT / 'serve.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules['serve_under_test'] = mod
        cwd0 = os.getcwd()
        os.chdir(ROOT)   # the gate resolves against cwd, like the server
        try:
            spec.loader.exec_module(mod)
            gate = mod.Handler._static_path_allowed
            check('/serve.PY is refused by the gate',
                  gate(None, '/serve.PY') is False)
            check('/Serve.pY is refused by the gate',
                  gate(None, '/Serve.pY') is False)
            check('a case-swapped state dir is refused by the gate',
                  gate(None, '/%s/tls/key.pem' % swapped_state) is False)
            check('the canonical state dir stays refused',
                  gate(None, '/%s/tls/key.pem' % state_name) is False)
            check('/styles.css still passes the gate',
                  gate(None, '/styles.css') is True)
        finally:
            os.chdir(cwd0)

        # ── Half 2: the real server over real HTTP ───────────────────────
        port = free_port()
        base = 'http://127.0.0.1:%d' % port
        env = dict(os.environ, PORT=str(port), CAFRESOHQ_HQ_STATE_DIR=state)
        proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=ROOT, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(80):
                if status(base, '/health') == 200:
                    break
                time.sleep(0.25)
            else:
                check('server came up', False, 'no /health after 20s')
                return 1

            # On a case-insensitive volume these WERE 200 before the fix;
            # on a case-sensitive one no such file exists — 404 either way.
            check('GET /serve.PY is refused', status(base, '/serve.PY') == 404)
            check('GET /Serve.pY is refused', status(base, '/Serve.pY') == 404)
            check('GET a case-swapped state path is refused',
                  status(base, '/%s/tls/key.pem' % swapped_state) == 404)
            check('GET the canonical state path stays refused',
                  status(base, '/%s/tls/key.pem' % state_name) == 404)
            # A gate that refuses everything would pass all of the above and
            # take the UI shell down with it.
            check('GET /styles.css still serves', status(base, '/styles.css') == 200)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:                                 # noqa: BLE001
                proc.kill()
    finally:
        shutil.rmtree(state, ignore_errors=True)

    print()
    if FAILS:
        print('FAILED: %d — %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
