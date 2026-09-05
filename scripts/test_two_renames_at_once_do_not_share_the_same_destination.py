#!/usr/bin/env python3
"""Twenty coworkers renamed twenty different files onto one name; two of
them were told it worked.

#137/#337 made the upload doors CLAIM a name instead of merely looking at
it first (`fs_routes.claim_name`, O_CREAT|O_EXCL). `/fs/rename` carried the
identical shape and was never touched:

    if dp.exists() or dp.is_symlink():
        return self._send_json(409, {'error': 'target already exists'})
    ...
    os.replace(str(move_src), str(dp))

serve.py is a ThreadingMixIn server, so two coworkers renaming two
different files onto the same `to` at the same moment is the same
ordinary Tuesday claim_name's own note describes. Both ask "is `to`
free?". Both are told yes. Both os.replace() onto it — and os.replace
(rename(2)) never refuses an existing destination, it just silently
replaces it.

Measured against a real running server: twenty concurrent POSTs to
/fs/rename, twenty different sources, one shared destination:

    200 OK responses          2
    source files left on disk 18   (of 20 — so 18 renames correctly lost)
    final.txt on disk         whichever replace ran last

One of the two callers told "ok, moved to final.txt" had its file
silently thrown away with no error anywhere — the exact failure #337
closed on /fs/upload and /vault/upload, reopened here by a door that
looks the same but was never given the fix.

Fix: `_fs_rename` now claims `dp` before moving anything onto it —
O_CREAT|O_EXCL for a file destination, os.mkdir (equally exclusive) for a
directory one — so "is `to` free?" and "`to` is mine now" are the same
syscall, exactly like claim_name. The loser gets FileExistsError and a
clean 409 with nothing touched; the winner then replaces its own
just-claimed placeholder with the real move. A failed move afterwards
unclaims the placeholder (`_fs_rename_unclaim`) rather than leaving a
phantom empty file/folder sitting at `to`.

Guards:
  · exactly one of N concurrent renames onto one destination wins
  · every source file that lost the race is still on disk, untouched
  · the destination holds the WINNER's bytes, not a coin flip
  · a normal rename, a directory rename, and rename-onto-an-existing-
    destination (still a clean 409, nothing moved) all still work

Run: python3 scripts/test_two_renames_at_once_do_not_share_the_same_destination.py
"""
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


def post_json(url, obj):
    body = json.dumps(obj).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {'error': str(e)}


def boot(work_dir, state_dir):
    port = free_port()
    env = dict(os.environ, PORT=str(port), CAFRESOHQ_HQ_STATE_DIR=str(state_dir),
               CAFRESOHQ_ALLOWED_DIRS=str(work_dir),
               GAP_CRON='0', NEWS_CRON='0', TOPICS_CRON='0')
    env.pop('SEARCH_WORKER', None)
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


N = 30      # coworkers renaming different files onto one destination
ROUNDS = 5  # the race is real-clock timing, not deterministic — several
            # rounds against a real running server make it very unlikely
            # to slip past unnoticed the way one round did in early runs


# ── the claim exists on this door too ────────────────────────────────────
def structure_checks():
    print('=== the rename door claims the destination, not just looks ===')
    fs_src = (ROOT / 'fs_routes.py').read_text(encoding='utf-8')
    rename_body = fs_src[fs_src.find('def _fs_rename('):]
    rename_body = rename_body[:rename_body.find('\ndef _fs_delete')]
    check('the destination is claimed with an exclusive syscall',
          'O_CREAT' in rename_body and 'O_EXCL' in rename_body)
    check('a directory destination is claimed the same exclusive way',
          'dp.mkdir()' in rename_body)
    check('the door no longer os.replace()s straight onto a merely-looked-at path',
          'dp.exists() or dp.is_symlink():\n        return self._send_json(409' not in rename_body)


# ── the whole door, under real concurrency ───────────────────────────────
def race_checks(base, work):
    print()
    print('=== /fs/rename — %d rounds of %d coworkers, one destination ===' % (ROUNDS, N))
    bad_rounds = []
    for rnd in range(ROUNDS):
        srcs = []
        for i in range(N):
            p = work / ('r%d-src%02d.txt' % (rnd, i))
            p.write_text('coworker-%d-%02d\n' % (rnd, i))
            srcs.append(p)
        dst = work / ('r%d-final.txt' % rnd)

        results = [None] * N
        barrier = threading.Barrier(N)

        def worker(i, _srcs=srcs, _dst=dst, _results=results):
            barrier.wait()
            _results[i] = post_json(base + '/fs/rename', {'from': str(_srcs[i]), 'to': str(_dst)})

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        winners = [i for i, r in enumerate(results) if r and r[0] == 200]
        surviving = [i for i in range(N) if srcs[i].exists()]
        losers_expected = sorted(i for i in range(N) if i not in winners)
        ok = (len(winners) == 1 and sorted(surviving) == losers_expected and dst.exists()
              and (not winners or dst.read_text() == 'coworker-%d-%02d\n' % (rnd, winners[0])))
        if not ok:
            bad_rounds.append({'round': rnd, 'winners': winners,
                               'surviving': surviving, 'dst_text':
                               dst.read_text() if dst.exists() else None})
    check('every round: exactly one rename wins, every loser survives untouched, '
          'and the destination holds the winner\'s bytes (never a coin flip)',
          not bad_rounds, bad_rounds)


def sanity_checks(base, work):
    print()
    print('=== plain rename still behaves ===')
    f = work / 'plain-one.txt'
    f.write_text('hello')
    code, resp = post_json(base + '/fs/rename', {'from': str(f), 'to': str(work / 'plain-two.txt')})
    check('a normal file rename still succeeds', code == 200, resp)
    check('...and the bytes travel with it',
          (work / 'plain-two.txt').exists() and (work / 'plain-two.txt').read_text() == 'hello')

    d = work / 'plain-dir-a'
    d.mkdir()
    (d / 'x.txt').write_text('inside')
    code, resp = post_json(base + '/fs/rename', {'from': str(d), 'to': str(work / 'plain-dir-b')})
    check('a directory rename still succeeds', code == 200, resp)
    check('...and its contents travel with it',
          (work / 'plain-dir-b' / 'x.txt').read_text() == 'inside')

    other = work / 'plain-three.txt'
    other.write_text('do-not-lose-me')
    code, resp = post_json(base + '/fs/rename',
                           {'from': str(other), 'to': str(work / 'plain-two.txt')})
    check('renaming onto an existing destination is still a clean 409',
          code == 409, (code, resp))
    check('...and neither file was touched',
          other.exists() and (work / 'plain-two.txt').read_text() == 'hello')


def main():
    print('two renames at once do not share the same destination')
    structure_checks()
    with tempfile.TemporaryDirectory() as td:
        work, state = Path(td) / 'work', Path(td) / 'state'
        work.mkdir(parents=True)
        base, kill = boot(work, state)
        if not base:
            check('the office came up', False, 'server did not boot')
        else:
            try:
                race_checks(base, work)
                sanity_checks(base, work)
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
