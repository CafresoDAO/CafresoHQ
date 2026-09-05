#!/usr/bin/env python3
"""Forty files were shared with the office; thirteen of them exist.

#137 made a colliding upload step aside instead of replacing, and it did
it the way the office asks most of its questions — ask, then act:

    fname, collided = free_name(fname, lambda c: (target_dir / c).exists())
    ...
    dest.write_bytes(data)

serve.py is a ThreadingMixIn server, so every handler runs at the same
time as every other one, and two coworkers dropping files into the same
folder at the same moment is an ordinary Tuesday. Both of them ask
whether `report.txt` is free. Both are told yes. Both write it.

Measured live against a real server on this branch, forty concurrent
POSTs of `report.txt` to /fs/upload, each with its own body:

    receipts saying filed        40
    files on disk                13
    'report (2).txt' handed to   12 different uploads

Twenty-seven people were told, in writing, that their file was shared
with the project. It was not there. The receipt was at its most
confident — `renamedFrom`, a byte count, a full path — exactly where the
bytes had been overwritten by whoever's write_bytes ran last. Same
family as the vault append (## 329.) and the OCI append (## 335.): a
look, a decision made from the look, and a write that assumes nothing
moved in between.

fs_routes.claim_name closes the gap by making "is this name free?" and
"this name is mine" the same syscall — O_CREAT|O_EXCL. The loser of a
race gets EEXIST and steps to the next variant, which is what stepping
aside was supposed to mean. free_name still does the skipping-ahead so
a folder with fifty `report (n).txt` costs fifty stats, not fifty
creates.

Guards:
  · the claim is exclusive — two claimers of one name never get the
    same name, and the second one's file still exists afterwards
  · both upload doors claim rather than look
  · every receipt that says "filed" has bytes behind it, under real
    concurrency, at BOTH doors
  · a sidestep still reports itself through renamedFrom

Run: python3 scripts/test_two_uploads_at_once_do_not_get_the_same_name.py
"""
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
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
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


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode()


def multipart(parts):
    bound = '----cafresoupload337'
    body = b''
    for name, ctype, data in parts:
        body += ('--%s\r\nContent-Disposition: form-data; name="files"; '
                 'filename="%s"\r\nContent-Type: %s\r\n\r\n'
                 % (bound, name, ctype)).encode()
        body += data + b'\r\n'
    body += ('--%s--\r\n' % bound).encode()
    return body, 'multipart/form-data; boundary=%s' % bound


def post_files(url, parts):
    body, ctype = multipart(parts)
    req = urllib.request.Request(url, data=body,
                                 headers={'Content-Type': ctype}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {'error': str(e)}


def boot(vault_root, state_dir, work_dir):
    port = free_port()
    env = dict(os.environ, PORT=str(port), CAFRESOHQ_VAULT=str(vault_root),
               CAFRESOHQ_HQ_STATE_DIR=str(state_dir),
               CAFRESOHQ_ALLOWED_DIRS=str(work_dir))
    for k in ('OCI_VAULT_NAMESPACE', 'OCI_VAULT_BUCKET', 'OCI_VAULT_PREFIX',
              'CAFRESOHQ_VAULT_BACKEND', 'CAFRESOHQ_OBSIDIAN_URL',
              'CAFRESOHQ_OBSIDIAN_KEY'):
        env.pop(k, None)
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=str(ROOT), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = 'http://127.0.0.1:%d' % port

    def kill():
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    for _ in range(80):
        if get(base + '/missions/scheduled')[0] == 200:
            return base, kill
        time.sleep(0.25)
    kill()
    return None, (lambda: None)


N = 40           # coworkers dropping the same filename at the same moment
STAMP = 'coworker-%02d'


# ── the claim, on its own ────────────────────────────────────────────────
def claim_checks():
    import fs_routes
    print('=== the claim itself ===')
    check('the door has a way to claim a name, not just look at one',
          hasattr(fs_routes, 'claim_name'))
    if not hasattr(fs_routes, 'claim_name'):
        return
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        path_for = lambda c: d / c
        fd, name, path, collided = fs_routes.claim_name('deck.pptx', path_for)
        os.write(fd, b'first')
        os.close(fd)
        check('a free name is claimed as typed',
              (name, collided) == ('deck.pptx', False), (name, collided))
        check('...and claiming it created it, so nobody else can have it',
              path.exists() and path.read_bytes() == b'first')

        fd2, name2, path2, collided2 = fs_routes.claim_name('deck.pptx', path_for)
        os.write(fd2, b'second')
        os.close(fd2)
        check('a second claimer of the same name gets a different one',
              name2 != name and collided2, (name2, collided2))
        check('...and the first claimer\'s bytes are still there',
              path.read_bytes() == b'first', path.read_bytes())
        check('...and the second claimer\'s bytes are there too',
              path2.read_bytes() == b'second', path2.read_bytes())

        # The exclusive open is the point: a name that already exists on disk
        # can never be handed back, no matter what a stale look said.
        (d / 'notes').write_text('older')
        fd3, name3, path3, _ = fs_routes.claim_name('notes', path_for)
        os.close(fd3)
        check('an extensionless name that exists is never re-handed out',
              name3 != 'notes' and (d / 'notes').read_text() == 'older', name3)


# ── both doors ask for a claim ───────────────────────────────────────────
def structure_checks():
    print()
    print('=== both doors claim, neither merely looks ===')
    fs_src = (ROOT / 'fs_routes.py').read_text(encoding='utf-8')
    serve = (ROOT / 'serve.py').read_text(encoding='utf-8')
    check('the claim is exclusive, not a create-if-you-feel-like-it',
          re.search(r'O_CREAT\s*\|\s*os\.O_EXCL', fs_src))
    check('the Projects door claims the name it writes to',
          re.search(r'claim_name\(fname,', fs_src))
    check('the Library door claims the name it writes to',
          'fs_routes.claim_name(' in serve)
    proj = fs_src[fs_src.find('def _fs_upload'):]
    proj = proj[:proj.find('\ndef ', 10)]
    check('the Projects door no longer writes to a name it only looked at',
          'dest.write_bytes(data)' not in proj)


# ── the whole door, under real concurrency ───────────────────────────────
def race_checks(base, work, vault):
    for label, url, folder in (
            ('Projects (/fs/upload)', base + '/fs/upload?path=' + urllib.parse.quote(str(work)), work),
            ('Library (/vault/upload)', base + '/vault/upload?dir=drops', vault / 'drops')):
        print()
        print('=== %s — %d coworkers, one filename ===' % (label, N))
        results = [None] * N
        barrier = threading.Barrier(N)

        def worker(i):
            payload = (STAMP % i).encode() + b'\n' + b'x' * 400
            barrier.wait()
            results[i] = post_files(url, [('report.txt', 'text/plain', payload)])

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        filed, names = [], {}
        for r in results:
            if r and r[0] == 200:
                for u in (r[1].get('uploaded') or []):
                    filed.append(u)
                    key = u.get('name') or u.get('path')
                    names[key] = names.get(key, 0) + 1
        dupes = {k: v for k, v in names.items() if v > 1}
        check('every upload got a receipt saying it was filed',
              len(filed) == N, '%d of %d' % (len(filed), N))
        check('no two uploads were handed the same name', not dupes, dupes)

        on_disk = sorted(p for p in folder.iterdir() if p.is_file())
        stamps = set()
        for p in on_disk:
            stamps.add(p.read_bytes().split(b'\n', 1)[0].decode('utf-8', 'replace'))
        missing = sorted(STAMP % i for i in range(N))
        missing = [s for s in missing if s not in stamps]
        check('every receipt that said "filed" has bytes behind it',
              not missing, '%d lost: %s' % (len(missing), missing[:6]))
        check('...and the folder holds one file per coworker',
              len(on_disk) == N, '%d of %d on disk' % (len(on_disk), N))
        sidesteps = [u for u in filed if u.get('renamedFrom')]
        check('the sidesteps still say so on the receipt',
              len(sidesteps) == N - 1, '%d of %d' % (len(sidesteps), N - 1))


def main():
    print('two uploads at once do not get the same name')
    claim_checks()
    structure_checks()
    with tempfile.TemporaryDirectory() as td:
        vault, state, work = Path(td) / 'vault', Path(td) / 'state', Path(td) / 'work'
        for p in (vault, state, work):
            p.mkdir(parents=True)
        (vault / 'drops').mkdir()
        base, kill = boot(vault, state, work)
        if not base:
            check('the office came up', False, 'server did not boot')
        else:
            try:
                race_checks(base, work, vault)
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
