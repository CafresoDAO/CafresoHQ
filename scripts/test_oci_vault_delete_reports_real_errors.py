#!/usr/bin/env python3
"""DELETE /vault/note (OCI backend) reported success no matter what happened.

    if _vault_backend == 'oci':
        try:
            cli = _oci_object_client()
            cli.delete_object(_oci_vault_namespace, _oci_vault_bucket, _oci_obj_key(rel))
        except Exception:
            pass  # 404 on delete is fine
        return self._send_json(200, {'deleted': rel, 'backend': 'oci'})

A bare `except Exception: pass` covers every failure the same way it covers
the one it names in the comment. `_oci_object_client()` raising because the
SDK isn't installed, a dead bucket, expired credentials, a network timeout,
a permissions error — all of them land here, and every one of them still
answered `{"deleted": rel, "backend": "oci"}`. A boss deletes a note from
the Library, the object is still sitting in the bucket, and the response
they got said it worked.

Reproduced live, no OCI account needed: this dev environment has no `oci`
package installed (confirmed — `import oci` raises ModuleNotFoundError), so
`_oci_object_client()` takes its own documented failure path and raises
`RuntimeError('OCI SDK not installed...')` — a real, non-404 exception, the
same one scripts/test_a_vault_that_works_is_not_reported_missing.py already
measured `PUT /vault/note` turning into a proper 502. `DELETE /vault/note`
hit the identical exception and turned it into a 200.

The fix classifies the way GET /vault/note (OCI) already does a couple
hundred lines up in the same file: 404/NoSuchKey/ObjectNotFound is treated
as "already gone" (matching the local-fs branch's idempotent-delete
semantics, where `target.exists()` being false is also a silent 200);
anything else is a real failure and comes back as a 502 naming what OCI
said.

Run: python3 scripts/test_oci_vault_delete_reports_real_errors.py
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
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVE_RAW = (ROOT / 'serve.py').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    return re.sub(r'^\s*#.*$', '', src, flags=re.M)


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def request(url, method='GET'):
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, None


def get_json(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception:
        return None


def boot(**extra_env):
    tmp = tempfile.mkdtemp(prefix='ocidelete-')
    port = free_port()
    env = dict(os.environ, PORT=str(port),
               CAFRESOHQ_HQ_STATE_DIR=str(Path(tmp) / 'state'))
    for k in ('OCI_VAULT_NAMESPACE', 'OCI_VAULT_BUCKET', 'OCI_VAULT_PREFIX',
              'CAFRESOHQ_VAULT_BACKEND', 'CAFRESOHQ_VAULT',
              'CAFRESOHQ_OBSIDIAN_URL', 'CAFRESOHQ_OBSIDIAN_KEY'):
        env.pop(k, None)
    env.update({k: str(v) for k, v in extra_env.items()})
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=str(ROOT),
                            env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT)
    base = 'http://127.0.0.1:%d' % port

    def kill():
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    for _ in range(80):
        if get_json(base + '/vault/status') is not None:
            return base, kill
        time.sleep(0.25)
    kill()
    return None, (lambda: None)


def main():
    print('DELETE /vault/note (oci): a real failure is not a silent 200')

    # ── 1. the fix, read out of the source ───────────────────────────────
    a = SERVE_RAW.index("if path == '/vault/note' and method == 'DELETE':")
    b = SERVE_RAW.index('# ---------- Rename / move ----------', a)
    delete_handler = SERVE_RAW[a:b]
    oci_arm = delete_handler[delete_handler.index("_vault_backend == 'oci'"):]

    check("the bare 'except Exception: pass' is gone",
          not re.search(r'except Exception:\s*\n\s*pass', oci_arm),
          '— that swallowed every failure mode, not only "already gone"')
    check('a caught delete_object failure is inspected before deciding',
          re.search(r'except Exception as e:', oci_arm) is not None,
          oci_arm[:200])
    check('non-404-shaped errors are reported as a 502 naming what OCI said',
          re.search(r"return self\._send_json\(502, \{'error': f'oci: \{e\}'\}\)",
                     oci_arm) is not None,
          '— PUT and GET on this same door both already do exactly this; '
          'DELETE was the one arm that did not')

    # The classification has to be the SAME idiom GET /vault/note (oci)
    # already uses a couple hundred lines up, or the two copies drift and a
    # future fix to one silently stops matching the other's 404s.
    get_a = SERVE_RAW.index("if path == '/vault/note' and method == 'GET':")
    get_b = SERVE_RAW.index("if _vault_backend == 'oci':", get_a)
    get_oci = SERVE_RAW[get_b:SERVE_RAW.index('try:', get_b + 200) + 600]
    get_markers = set(re.findall(r"'(\d{3}|[A-Za-z]+)' in err", get_oci))
    del_markers = set(re.findall(r"'(\d{3}|[A-Za-z]+)' in err", oci_arm))
    check('found the marker set GET /vault/note (oci) already treats as "not found"',
          len(get_markers) >= 2, get_markers)
    check('DELETE classifies not-found with the exact same marker set as GET',
          get_markers and get_markers == del_markers,
          [sorted(get_markers), sorted(del_markers),
           '— same backend, same SDK, same shape of "already gone"; one '
           'table copied by hand into two places is how they drift'])

    # ── 2. idempotent semantics preserved for the case the comment names ──
    check('a not-found delete still succeeds (matches the local-fs branch, '
          'where target.exists() already false is also a silent 200)',
          re.search(r"# 404 on delete is fine", oci_arm) is not None,
          oci_arm)

    # ── 3. reproduced live: a real, non-404 failure over real HTTP ────────
    # No OCI account needed — this dev environment has no `oci` package
    # installed, so _oci_object_client() takes its own documented
    # ImportError branch and raises RuntimeError('OCI SDK not installed...').
    # scripts/test_a_vault_that_works_is_not_reported_missing.py already
    # measured PUT turning this into a 502; this is the same failure, DELETE.
    try:
        import oci  # noqa: F401
        HAVE_OCI = True
    except ImportError:
        HAVE_OCI = False
    check('reproduction assumption: no oci package on this machine',
          not HAVE_OCI,
          '— if this ever flips true, the live section below no longer '
          'reproduces anything; the static checks above still hold')

    if HAVE_OCI:
        print('  SKIP  live section — oci package is installed here, '
              'RuntimeError(SDK not installed) can no longer be forced')
    else:
        base, kill = boot(CAFRESOHQ_VAULT_BACKEND='oci',
                          OCI_VAULT_NAMESPACE='axhoibfmftgb',
                          OCI_VAULT_BUCKET='cafresohq-fleet-vault')
        try:
            check('the office came up', base is not None)
            if base:
                status, body = request(
                    base + '/vault/note?path=probe.md', method='DELETE')
                check('a real OCI failure is now reported, not silently 200',
                      status == 502,
                      [status, body,
                       '— before the fix this was 200 '
                       '{"deleted": "probe.md", "backend": "oci"} regardless'])
                check('...and names OCI as the source, with the real reason',
                      body and isinstance(body.get('error'), str)
                      and body['error'].startswith('oci: ')
                      and 'OCI SDK not installed' in body['error'],
                      body)
        finally:
            kill()

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
