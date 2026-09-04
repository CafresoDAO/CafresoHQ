#!/usr/bin/env python3
"""A hidden file never leaves the building.

The static fallthrough in serve.py is deliberately key-exempt — the UI shell
(styles.css, sw.js, assets/) must load without an X-API-Key header, because a
<link> tag cannot send one. `_static_path_allowed` gates that fallthrough,
and until now it blocked exactly three things: paths outside the web root,
`*.py`, and the state dir. Everything else under cwd was served to any
caller who could reach the port.

Measured live (port 8971, no API key supplied):

    GET /.git          → 200  (gitdir pointer; in a plain checkout,
                               /.git/config, /.git/HEAD and the object
                               store are the WHOLE repo — every blocked
                               .py included, one object file at a time)
    GET /.env.example  → 200  (whose own header says: copy to `.env`,
                               gitignored, and fill in the keys)
    GET /.gitignore    → 200

A real `.env` sits at the web root on any install that followed those
instructions, and the LAN URL is printed on every boot. Rule (d) now refuses
any path with a hidden segment; no legitimate UI asset starts with a dot
(the canister's .well-known/ ships from hq-ui/, not through this server).

Exercised against the REAL server: boot serve.py on a free port with an
isolated state dir and ask over actual HTTP, the way an attacker would.

Run: python3 scripts/test_a_hidden_file_never_leaves_the_building.py
"""
import os
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
    print('static fallthrough — hidden files stay hidden')
    port = free_port()
    base = 'http://127.0.0.1:%d' % port
    with tempfile.TemporaryDirectory() as state:
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

            # The bug: every one of these is a committed file at the web
            # root, hidden by name, and none is a UI asset.
            for path in ('/.gitignore', '/.env.example', '/.gitattributes',
                         '/.dockerignore', '/.git'):
                check('%s is refused' % path, status(base, path) == 404)
            # The sharper cases the dot rule exists for: the repo itself and
            # the secrets file the example says to create. Neither may need
            # to exist for the rule to hold, so the rule is what is probed —
            # a 404 whether or not the file is there.
            for path in ('/.git/config', '/.git/HEAD', '/.env'):
                check('%s is refused' % path, status(base, path) == 404)
            # A hidden DIRECTORY hides everything under it, existing or not.
            check('/.github/workflows is refused',
                  status(base, '/.github/workflows') == 404)

            # The other half: a gate that refuses everything would pass all
            # of the above and take the UI shell down with it.
            for path in ('/styles.css', '/sw.js', '/manifest.webmanifest',
                         '/assets/icon-192.png'):
                check('%s still serves' % path, status(base, path) == 200)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:                                 # noqa: BLE001
                proc.kill()

    print()
    if FAILS:
        print('FAILED: %d — %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
