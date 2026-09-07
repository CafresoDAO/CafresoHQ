#!/usr/bin/env python3
"""#417 — the office that lived in the container.

A fleet container has no persistent volume. Every /hq/state and /hq/memory
file — tasks, receipts, workflows, chat, the agent roster — lived in
`/data/hq-state` and died with the container; a fleet roll is a container
death. Only the vault in Object Storage survived one.

serve.py now mirrors every successful /hq PUT into the same bucket under a
dot-folder (`.hq-state/<scope>/<name>.json`, which every vault list and
search already skips) and, on a boot whose state dir is EMPTY, restores from
that mirror before answering the first /hq request.

Rounds, each against a real serve.py subprocess and a stand-in `oci` SDK
(one bucket in a JSON file):

  1. a PUT lands in the bucket under the dot-folder, after the debounce,
     and a burst of PUTs to one name costs one object carrying the newest body
  2. a second server, empty state dir, same bucket: GET returns the mirrored
     body — for state AND memory
  3. disk wins: a server whose state dir already holds a file is not rolled
     back by a stale mirror
  4. a bucket that refuses the put still answers the PUT with 200 (the office
     never sees a failed save), and /health counts the failure
  5. the mirrored objects are invisible to /vault/search (dot-folder)
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


FAKE_OCI = '''
import json, os, types

_LOG = os.environ['FAKE_OCI_BUCKET']
_PUT_FAIL = os.environ.get('FAKE_OCI_PUT_FAILURE', '')


def _read():
    try:
        with open(_LOG, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


class _Resp:
    def __init__(self, content):
        self.data = type('D', (), {'content': content})()


class _Obj:
    def __init__(self, name):
        self.name = name


class _ListResp:
    def __init__(self, names):
        self.data = type('D', (), {'objects': [_Obj(n) for n in names]})()


class ObjectStorageClient:
    def __init__(self, *a, **kw):
        pass

    def get_object(self, ns, bucket, key):
        objs = _read()
        if key not in objs:
            raise Exception('ServiceError: status=404 code=ObjectNotFound')
        return _Resp(objs[key].encode('utf-8'))

    def put_object(self, ns, bucket, key, put_object_body=None, **kw):
        if _PUT_FAIL:
            raise Exception(_PUT_FAIL)
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

    def list_objects(self, ns, bucket, prefix='', fields=None, limit=1000, **kw):
        return _ListResp([k for k in _read() if k.startswith(prefix or '')])


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
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode('utf-8')
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, None


def boot(sdk_dir, bucket_file, state_dir, put_failure=''):
    port = free_port()
    env = dict(os.environ, PORT=str(port),
               CAFRESOHQ_HQ_STATE_DIR=str(state_dir),
               CAFRESOHQ_HQ_MIRROR_DELAY='0.3',
               PYTHONPATH=sdk_dir,
               CAFRESOHQ_VAULT_BACKEND='oci',
               OCI_VAULT_NAMESPACE='ns', OCI_VAULT_BUCKET='bucket',
               OCI_VAULT_PREFIX='user-abc',
               FAKE_OCI_BUCKET=bucket_file,
               FAKE_OCI_PUT_FAILURE=put_failure)
    for k in ('CAFRESOHQ_VAULT', 'CAFRESOHQ_MEMORY_DIR',
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


def bucket(bucket_file):
    try:
        return json.loads(Path(bucket_file).read_text(encoding='utf-8'))
    except Exception:
        return {}


def wait_for(pred, seconds=6.0):
    end = time.time() + seconds
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.1)
    return pred()


def main():
    print('#417 — the office survives its container')
    check('serve.py mirrors /hq PUTs',
          '_hq_mirror_schedule(scope, name, body)' in SERVE_RAW)
    check('serve.py restores on boot',
          "target=_hq_state_restore_from_bucket" in SERVE_RAW)
    check('mirror lives in a dot-folder the vault list skips',
          "_HQ_MIRROR_ROOT = '.hq-state/'" in SERVE_RAW)

    work = tempfile.mkdtemp(prefix='hqmirror-')
    sdk = write_fake_sdk(Path(work) / 'sdk')
    bucket_file = str(Path(work) / 'bucket.json')
    Path(bucket_file).write_text('{}', encoding='utf-8')

    # ── round 1: the PUT lands in the bucket ─────────────────────────────
    state1 = Path(work) / 'state1'
    base, kill = boot(sdk, bucket_file, state1)
    check('round 1: server booted', base is not None)
    if base:
        tasks = json.dumps([{'id': 't1', 'title': 'ship the beta'}])
        st, body = request(base + '/hq/state/tasks', 'PUT', tasks)
        check('round 1: PUT tasks -> 200', st == 200 and body and body.get('ok'),
              (st, body))
        # a burst to the same name: newest wins, one object
        for i in range(5):
            request(base + '/hq/state/notes', 'PUT',
                    json.dumps({'v': i, 'text': 'draft %d' % i}))
        roster = json.dumps([{'id': 'a1', 'name': 'Scout'}])
        st, body = request(base + '/hq/memory/agents', 'PUT', roster)
        check('round 1: PUT memory/agents -> 200', st == 200, (st, body))

        key_tasks = 'user-abc/.hq-state/state/tasks.json'
        key_notes = 'user-abc/.hq-state/state/notes.json'
        key_agents = 'user-abc/.hq-state/memory/agents.json'
        landed = wait_for(lambda: key_agents in bucket(bucket_file)
                          and key_notes in bucket(bucket_file)
                          and key_tasks in bucket(bucket_file))
        b = bucket(bucket_file)
        check('round 1: tasks mirrored under the dot-folder, prefixed',
              landed and b.get(key_tasks) == tasks, sorted(b))
        check('round 1: memory/agents mirrored', b.get(key_agents) == roster)
        check('round 1: burst to one name → newest body',
              json.loads(b.get(key_notes, '{}')).get('v') == 4, b.get(key_notes))
        check('round 1: nothing but the three objects in the bucket',
              len(b) == 3, sorted(b))
        st, h = request(base + '/health')
        m = (h or {}).get('hq_state_mirror') or {}
        check('round 1: /health reports the mirror',
              m.get('mirrored') == 3 and m.get('failed') == 0, m)
        # the mirror must be invisible to the vault's own listing
        st, s = request(base + '/vault/search?q=ship')
        hits = (s or {}).get('hits') or (s or {}).get('results') or []
        check('round 5: /vault/search does not see the mirror',
              st == 200 and not hits, (st, s))
        kill()

    # ── round 2: a fresh container restores ──────────────────────────────
    state2 = Path(work) / 'state2'
    base, kill = boot(sdk, bucket_file, state2)
    check('round 2: fresh server booted', base is not None)
    if base:
        st, body = request(base + '/hq/state/tasks')
        check('round 2: GET tasks on an EMPTY state dir returns the mirrored office',
              st == 200 and body == json.loads(tasks), (st, body))
        st, body = request(base + '/hq/state/notes')
        check('round 2: notes restored with the newest body',
              st == 200 and (body or {}).get('v') == 4, (st, body))
        st, body = request(base + '/hq/memory/agents')
        check('round 2: memory/agents restored',
              st == 200 and body == json.loads(roster), (st, body))
        st, body = request(base + '/hq/state/never-written')
        check('round 2: a name never written is still null', st == 200 and body is None,
              (st, body))
        check('round 2: restored files are on disk',
              (state2 / 'tasks.json').exists() and (state2 / 'memory' / 'agents.json').exists())
        st, h = request(base + '/health')
        m = (h or {}).get('hq_state_mirror') or {}
        check('round 2: /health counts the restore', m.get('restored') == 3, m)
        kill()

    # ── round 3: disk wins ───────────────────────────────────────────────
    state3 = Path(work) / 'state3'
    state3.mkdir(parents=True)
    local = json.dumps([{'id': 't9', 'title': 'the live container edited this'}])
    (state3 / 'tasks.json').write_text(local, encoding='utf-8')
    base, kill = boot(sdk, bucket_file, state3)
    check('round 3: server booted', base is not None)
    if base:
        st, body = request(base + '/hq/state/tasks')
        check('round 3: a populated state dir is NOT rolled back by the mirror',
              st == 200 and body == json.loads(local), (st, body))
        st, body = request(base + '/hq/state/notes')
        check('round 3: ...and siblings are not pulled in behind it either',
              st == 200 and body is None, (st, body))
        kill()

    # ── round 4: a refusing bucket never fails a save ─────────────────────
    state4 = Path(work) / 'state4'
    base, kill = boot(sdk, bucket_file, state4, put_failure='ServiceError: status=503')
    check('round 4: server booted', base is not None)
    if base:
        st, body = request(base + '/hq/state/pins', 'PUT', json.dumps(['p1']))
        check('round 4: PUT still 200 when the bucket refuses', st == 200, (st, body))
        st, body = request(base + '/hq/state/pins')
        check('round 4: the write is on disk regardless', body == ['p1'], body)
        ok = wait_for(lambda: ((request(base + '/health')[1] or {})
                               .get('hq_state_mirror') or {}).get('failed', 0) >= 1)
        st, h = request(base + '/health')
        m = (h or {}).get('hq_state_mirror') or {}
        check('round 4: /health counts the failed mirror with its reason',
              ok and '503' in (m.get('last_error') or ''), m)
        check('round 4: nothing new in the bucket',
              'user-abc/.hq-state/state/pins.json' not in bucket(bucket_file))
        kill()

    print()
    if FAILS:
        print('FAILED: ' + ', '.join(FAILS))
        sys.exit(1)
    print('all green')


if __name__ == '__main__':
    main()
