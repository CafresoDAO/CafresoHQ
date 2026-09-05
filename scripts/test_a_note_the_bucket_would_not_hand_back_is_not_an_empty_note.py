#!/usr/bin/env python3
"""PUT /vault/note?mode=append (OCI backend) overwrote the note it failed to read.

A bucket has no append. So the OCI arm of the write door read the object,
glued the new text on the end, and put the whole thing back:

    if mode == 'append':
        try:
            existing = cli.get_object(...).data.content
            existing_text = existing.decode('utf-8', 'replace')
            sep = '' if existing_text.endswith('\\n') else '\\n'
            content = existing_text + sep + body
        except Exception:
            pass  # file doesn't exist yet — treat as write

`content` starts as `body` — the fragment alone. The comment names ONE
reason get_object can raise, and the bare `except Exception: pass` covers
every other one identically: a 503 from a throttled bucket, a 429, an
instance-principal token that expired since bedtime, a socket timeout, an
IAM policy edited at midnight. Each of those fell through to
`put_object(..., content)` and REPLACED the whole note with the one line
being appended — then answered 200 {"path": ..., "mode": "append"}, which
night_runner's VAULT_APPEND renders to the boss as "Appended N chars → path".

Reproduced live over real HTTP, twice, against a real `python3 serve.py`
speaking to a stand-in `oci` SDK backed by one JSON file (this dev box has
no oci package, so nothing shadows a real one):

    healthy office:  write "LINE 1\\nLINE 2\\nLINE 3\\n", append "LINE 4\\n"
                     → bucket holds all four lines            (correct)
    same note, 503 on the read half of the next append:
                     → HTTP 200 {"mode": "append", "size": 7}
                       bucket holds "LINE 5\\n" — three lines of the boss's
                       note deleted by a transient error, reported as a
                       successful append.

Same family as the night ticker's `cur = ... if s == 200 else []` PUT
(## 319.) and the local-fs append's read-modify-write (_vault_append_local):
an unattended writer treating a failed read as an empty one and writing its
optimism to disk. The fix classifies the failure with the exact
404/NoSuchKey/ObjectNotFound test GET and DELETE on this same backend
already use — a note that genuinely isn't there yet still falls through to
a plain write, and anything else is a 502 that writes nothing at all.

Run: python3 scripts/test_a_note_the_bucket_would_not_hand_back_is_not_an_empty_note.py
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


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


# A stand-in for the `oci` SDK: one bucket in a JSON file, plus an
# env-controlled fault on the read half so a transient bucket failure can be
# produced without an OCI account. serve.py reaches it through its own
# documented config-file branch (`oci.config.from_file()`).
FAKE_OCI = '''
import json, os, types

_LOG = os.environ['FAKE_OCI_BUCKET']
_FAIL = os.environ.get('FAKE_OCI_GET_FAILURE', '')


def _read():
    try:
        with open(_LOG, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


class _Resp:
    def __init__(self, content):
        self.data = type('D', (), {'content': content})()


class ObjectStorageClient:
    def __init__(self, *a, **kw):
        pass

    def get_object(self, ns, bucket, key):
        if _FAIL:
            raise Exception(_FAIL)
        objs = _read()
        if key not in objs:
            raise Exception('ServiceError: status=404 code=ObjectNotFound')
        return _Resp(objs[key].encode('utf-8'))

    def put_object(self, ns, bucket, key, put_object_body=None, **kw):
        objs = _read()
        body = put_object_body
        if isinstance(body, bytes):
            body = body.decode('utf-8')
        objs[key] = body
        with open(_LOG, 'w') as f:
            json.dump(objs, f)
        return _Resp(b'')

    def delete_object(self, ns, bucket, key):
        objs = _read()
        objs.pop(key, None)
        with open(_LOG, 'w') as f:
            json.dump(objs, f)


config = types.ModuleType('oci.config')
config.from_file = lambda *a, **kw: {}
config.validate_config = lambda *a, **kw: None
object_storage = types.ModuleType('oci.object_storage')
object_storage.ObjectStorageClient = ObjectStorageClient
'''


def write_fake_sdk(where):
    pkg = Path(where) / 'oci'
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / '__init__.py').write_text(FAKE_OCI, encoding='utf-8')
    return str(where)


def request(url, method='GET', body=None):
    req = urllib.request.Request(
        url, method=method, data=(body.encode('utf-8') if body else None))
    if body:
        req.add_header('Content-Type', 'text/markdown')
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, None


def boot(sdk_dir, bucket_file, get_failure=''):
    tmp = tempfile.mkdtemp(prefix='ociappend-')
    port = free_port()
    env = dict(os.environ, PORT=str(port),
               CAFRESOHQ_HQ_STATE_DIR=str(Path(tmp) / 'state'),
               PYTHONPATH=sdk_dir,
               CAFRESOHQ_VAULT_BACKEND='oci',
               OCI_VAULT_NAMESPACE='ns', OCI_VAULT_BUCKET='bucket',
               FAKE_OCI_BUCKET=bucket_file,
               FAKE_OCI_GET_FAILURE=get_failure)
    # Env-var credentials would take a different branch in
    # _oci_object_client and never reach the config-file one the stand-in
    # answers, so clear them along with the other backends' config.
    for k in ('OCI_VAULT_PREFIX', 'CAFRESOHQ_VAULT',
              'CAFRESOHQ_OBSIDIAN_URL', 'CAFRESOHQ_OBSIDIAN_KEY',
              'OCI_TENANCY_OCID', 'OCI_USER_OCID', 'OCI_FINGERPRINT',
              'OCI_KEY_B64'):
        env.pop(k, None)
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
        try:
            urllib.request.urlopen(base + '/vault/status', timeout=5).read()
            return base, kill
        except Exception:
            time.sleep(0.25)
    kill()
    return None, (lambda: None)


def main():
    print('append on the bucket backend: a read that failed is not an empty note')

    # ── 1. the fix, read out of the source ───────────────────────────────
    a = SERVE_RAW.index("if path == '/vault/note' and method == 'PUT':")
    b = SERVE_RAW.index('# ---------- Delete ----------', a)
    put_handler = SERVE_RAW[a:b]
    oci_arm = put_handler[put_handler.index("if _vault_backend == 'oci':"):
                          put_handler.index('target = _vault_resolve(rel)')]
    code = re.sub(r'^\s*#.*$', '', oci_arm, flags=re.M)

    check("the bare 'except Exception: pass' around the read is gone",
          not re.search(r'except Exception:\s*\n\s*pass', code),
          '— that covered a throttled bucket and an expired token exactly '
          'the way it covered "not there yet", and the note paid for it')
    check('the failed read is inspected before anything is written',
          re.search(r'except Exception as e:', code) is not None,
          code[:300])
    check('a read failure that is not "not found" answers 502',
          re.search(r"self\._send_json\(502, \{\s*'error': f'oci: \{e\}'",
                    code) is not None,
          code)

    # The classification has to be the one this backend's OTHER doors
    # already use, or a note that genuinely does not exist yet stops being
    # creatable by an append — which is the behaviour the old comment was
    # protecting and is worth keeping.
    get_b = SERVE_RAW.index("if _vault_backend == 'oci':",
                            SERVE_RAW.index("if path == '/vault/note' and method == 'GET':"))
    get_oci = SERVE_RAW[get_b:SERVE_RAW.index('target = _vault_resolve(rel)', get_b)]
    get_markers = set(re.findall(r"'(\d{3}|[A-Za-z]+)' in err", get_oci))
    put_markers = set(re.findall(r"'(\d{3}|[A-Za-z]+)' in err", code))
    check('GET /vault/note (oci) has a "not found" marker set to match',
          len(get_markers) >= 2, get_markers)
    check('the append arm classifies not-found with that same marker set',
          get_markers and get_markers == put_markers,
          [sorted(get_markers), sorted(put_markers)])

    # ── 2. reproduced live, over real HTTP ───────────────────────────────
    try:
        import oci  # noqa: F401
        HAVE_OCI = True
    except ImportError:
        HAVE_OCI = False
    check('reproduction assumption: no real oci package on this machine to '
          'shadow the stand-in', not HAVE_OCI)

    if HAVE_OCI:
        print('  SKIP  live section — a real oci SDK is installed here')
    else:
        sdk_dir = write_fake_sdk(tempfile.mkdtemp(prefix='ocisdk-'))
        bucket = os.path.join(tempfile.mkdtemp(prefix='ocibucket-'), 'bucket.json')
        NOTE = 'notes/brief.md'
        KEPT = 'LINE 1\nLINE 2\nLINE 3\n'

        # 2a. a healthy office — write, then append, then append onto a note
        #     that does not exist yet (the case the old comment named).
        base, kill = boot(sdk_dir, bucket)
        try:
            check('the office came up on the bucket backend', base is not None)
            if base:
                request(base + '/vault/note?path=%s&mode=write' % NOTE,
                        'PUT', KEPT)
                st, body = request(
                    base + '/vault/note?path=%s&mode=append' % NOTE,
                    'PUT', 'LINE 4\n')
                check('a healthy append succeeds', st == 200, [st, body])
                objs = json.load(open(bucket))
                check('...and keeps every earlier line',
                      objs.get(NOTE) == KEPT + 'LINE 4\n', objs)
                st, _ = request(
                    base + '/vault/note?path=notes/fresh.md&mode=append',
                    'PUT', 'first line\n')
                objs = json.load(open(bucket))
                check('an append to a note that does not exist yet still '
                      'creates it (a real 404 is still "treat as write")',
                      st == 200 and objs.get('notes/fresh.md') == 'first line\n',
                      [st, objs])
        finally:
            kill()

        # 2b. same bucket, same note — but the read half of the append hits a
        #     transient bucket failure. Nothing may be written.
        base, kill = boot(sdk_dir, bucket, get_failure=(
            'ServiceError: status=503 code=TooManyRequests '
            'message=Slow down, opc-request-id=ABC'))
        try:
            check('the office came up again', base is not None)
            if base:
                st, body = request(
                    base + '/vault/note?path=%s&mode=append' % NOTE,
                    'PUT', 'LINE 5\n')
                check('a 503 on the read half is reported, not answered 200',
                      st == 502,
                      [st, body, '— before the fix this was 200 '
                                 '{"mode": "append", "size": 7}'])
                check('...and names the bucket as the source, with the reason',
                      body and isinstance(body.get('error'), str)
                      and body['error'].startswith('oci: ')
                      and '503' in body['error'], body)
                objs = json.load(open(bucket))
                check('the note the read failed on is UNTOUCHED — no line of '
                      'it was deleted by the failure',
                      objs.get(NOTE) == KEPT + 'LINE 4\n',
                      [objs.get(NOTE),
                       '— before the fix the whole note became "LINE 5\\n"'])
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
