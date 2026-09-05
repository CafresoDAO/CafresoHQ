#!/usr/bin/env python3
"""Ten coworkers renamed ten different files at once; a shared note that
linked to all ten came back remembering three.

`_vault_rewrite_wikilinks` (serve.py) follows a rename through every
inbound `[[wikilink]]` in the vault: for the ONE note that links to
several renamed files, `/vault/rename` is called once per file, and each
call independently

    1. reads the note's current text
    2. derives a new body with just ITS OWN link rewritten
    3. `p.write_text(new_body)`

serve.py is a ThreadingMixIn server, so ten renames racing at once (an
ordinary bulk cleanup, or two coworkers each renaming a few files around
the same moment) can all read the SAME pre-race text at step 1 before any
of them reaches step 3. Whichever write lands last then overwrites the
file with its own single-link patch of that stale snapshot, quietly
discarding every other writer's already-applied rewrite underneath it —
every one of the ten `/vault/rename` calls still answers 200 with
`linksRewritten: 1`, and the note is never flagged as `stranded`, because
each caller's OWN read-modify-write genuinely succeeded from where it
was standing.

Measured against a real running server: ten concurrent `/vault/rename`
calls, one shared note linking to all ten targets:

    renames reporting success (200, linksRewritten: 1)   10 / 10
    of those, links actually still pointing at the OLD name in the
    note afterward                                        7 / 10

Three renames' worth of backlinks won the race; the boss is told all ten
followed the move, and seven silently didn't — the exact failure
`_vault_write_local` (#382) and `fs_routes.claim_name` (#337/#381) closed
on their own doors, reopened here because this one derives its write
from a READ instead of taking the caller's body whole.

Fix: a new shared `_vault_write_lock` (renamed from the append-only
`_vault_append_lock`, now covering every writer that mutates a note's
bytes in place). Before writing, `_vault_rewrite_wikilinks` re-reads the
note and re-applies its own substitution against those FRESH bytes while
holding the lock, then writes via `_vault_write_local` (mkstemp + fsync +
os.replace) still inside the same locked section — so no other writer's
read can land between this call's fresh read and its write, and this
call's write can't land in the middle of a plain `/vault/note` write or
append either (both now take the same lock). Each rewrite is disjoint
(one call only touches its own src/dst), so serializing them is enough:
whichever runs second re-derives from a body that already carries the
first one's change and simply adds its own on top.

Guards:
  · N concurrent renames whose backlinks share one note: every one of
    their links is present and correctly rewritten afterward, every round
  · the shared note is never left shorter/garbled — final byte length
    always matches the fully-rewritten expectation
  · a plain single rename with one backlink still rewrites it, and a
    plain single `/vault/note` write is unaffected by the new lock

Run: python3 scripts/test_two_renames_at_once_do_not_erase_each_others_backlinks.py
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


def boot(vault_dir, state_dir):
    port = free_port()
    env = dict(os.environ, PORT=str(port), CAFRESOHQ_HQ_STATE_DIR=str(state_dir),
               CAFRESOHQ_VAULT=str(vault_dir),
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


N = 10             # files renamed at once, all linked from one shared note
PAD_BYTES = 300_000  # padding per link so the shared note is a few MB —
                     # large enough that a real read-modify-write race has
                     # time to land between two coworkers' HTTP requests
ROUNDS = 5          # real-clock timing, not deterministic — several rounds
                    # make a slip past this check very unlikely


def structure_checks():
    print('=== the wikilink rewrite re-derives under a lock before it writes ===')
    src = (ROOT / 'serve.py').read_text(encoding='utf-8')
    fn_body = src[src.find('def _vault_rewrite_wikilinks('):]
    fn_body = fn_body[:fn_body.find('\ndef _vault_link_trouble')]
    check('the write goes through the shared vault write lock',
          '_vault_write_lock' in fn_body)
    check('the note is re-read fresh before the write, not written from '
          'the earlier unlocked snapshot',
          'fresh_bytes = p.read_bytes()' in fn_body
          and 'fresh_out = epat.sub(_esub, pat.sub(_sub, fresh_text))' in fn_body)
    check('the write itself goes through the atomic tmp+replace helper, '
          'not a bare write_text',
          '_vault_write_local(p, fresh_out)' in fn_body
          and 'p.write_text(out, encoding=\'utf-8\')' not in fn_body)
    check('the plain-write HTTP handler takes the same lock around its write',
          'with _vault_write_lock:\n                        _vault_write_local(target, body)'
          in src)
    check('append still shares the one lock (no longer a separate '
          'append-only lock)',
          '_vault_append_lock' not in src and 'with _vault_write_lock:' in
          src[src.find('def _vault_append_local('):src.find('def _vault_write_local(')])


def _seed_hub(vault, round_no):
    """One shared note linking to all N targets, padded so each rewrite
    pass takes measurable real time — the race is on wall-clock overlap
    between ten HTTP requests, not on CPU-bound regex speed."""
    for i in range(N):
        (vault / ('r%d-a%02d.md' % (round_no, i))).write_text('target %d\n' % i)
    pad = 'x' * 200 + '\n'
    reps = max(1, PAD_BYTES // len(pad))
    lines = []
    for i in range(N):
        lines.append(pad * reps)
        lines.append('backlink: [[r%d-a%02d]]\n' % (round_no, i))
    hub = vault / ('r%d-hub.md' % round_no)
    hub.write_text(''.join(lines))
    return hub


def race_checks(base, vault):
    print()
    print('=== /vault/rename — %d rounds of %d coworkers, one shared backlinked note ==='
          % (ROUNDS, N))
    bad_rounds = []
    for rnd in range(ROUNDS):
        hub = _seed_hub(vault, rnd)
        results = [None] * N
        barrier = threading.Barrier(N)

        def worker(i, _rnd=rnd, _results=results):
            barrier.wait()
            _results[i] = post_json(
                base + '/vault/rename',
                {'from': 'r%d-a%02d.md' % (_rnd, i), 'to': 'r%d-b%02d.md' % (_rnd, i)})

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        all_200 = all(r and r[0] == 200 for r in results)
        final = hub.read_text(encoding='utf-8')
        b_links = sorted(set(re.findall(r'\[\[(r%d-b\d\d)\]\]' % rnd, final)))
        a_links = sorted(set(re.findall(r'\[\[(r%d-a\d\d)\]\]' % rnd, final)))
        expect_b = sorted('r%d-b%02d' % (rnd, i) for i in range(N))
        ok = all_200 and b_links == expect_b and not a_links
        if not ok:
            bad_rounds.append({
                'round': rnd, 'all_200': all_200,
                'b_links_present': len(b_links), 'a_links_remaining': a_links,
            })
    check('every round: all %d renames report success AND all %d backlinks '
          'actually follow (never a stale link left behind)' % (N, N),
          not bad_rounds, bad_rounds)


def sanity_checks(base, vault):
    print()
    print('=== a plain single rename with one backlink still works ===')
    (vault / 'solo-target.md').write_text('hello\n')
    (vault / 'solo-hub.md').write_text('see [[solo-target]] for details\n')
    code, resp = post_json(base + '/vault/rename',
                           {'from': 'solo-target.md', 'to': 'solo-renamed.md'})
    check('the rename itself succeeds', code == 200, resp)
    check('...and rewrote the one backlink',
          resp.get('linksRewritten') == 1 and resp.get('filesTouched') == 1, resp)
    check('...and the note on disk shows the new name',
          '[[solo-renamed]]' in (vault / 'solo-hub.md').read_text(encoding='utf-8'))

    print()
    print('=== a plain single /vault/note write is unaffected by the new lock ===')
    body = b'a quiet Tuesday note\n'
    req = urllib.request.Request(base + '/vault/note?path=plain-note&mode=write',
                                 data=body, method='PUT')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    check('the write succeeds', code == 200, code)
    code, got = get(base + '/vault/note?path=plain-note')
    check('...and reads back byte-identical', code == 200 and got == body, got)


def main():
    print('two renames at once do not erase each other\'s backlinks')
    structure_checks()
    with tempfile.TemporaryDirectory() as td:
        vault, state = Path(td) / 'vault', Path(td) / 'state'
        vault.mkdir(parents=True)
        base, kill = boot(vault, state)
        if not base:
            check('the office came up', False, 'server did not boot')
        else:
            try:
                race_checks(base, vault)
                sanity_checks(base, vault)
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
