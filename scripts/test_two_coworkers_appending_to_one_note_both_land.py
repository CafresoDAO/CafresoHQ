#!/usr/bin/env python3
"""Two coworkers appending to the same note, and only one of them was there.

The Library's append door (PUT /vault/note?mode=append) is what every writer
in the product ends up calling: memory_append in hq-runtime.jsx (one per
STREAMING COWORKER, and several coworkers stream at once), VAULT_APPEND from
the night shift, the boss's own editor. On the fs backend it did:

    existing = target.read_text()
    sep = '' if existing.endswith('\\n') else '\\n'
    target.write_text(existing + sep + body)

A read, then a write, and nothing holding the two together. serve.py is a
ThreadingMixIn server, so two of those land in the branch at once on the same
note. Both read the same `existing`. Both write `existing + their own line`.
The write_text that runs second IS the file, and the other coworker's
paragraph is gone from disk — while its tool cheerfully returned "Appended N
chars -> <path> (now <size> bytes)", the byte count being perfectly right for
the note that happened to survive. write_text truncates before it writes, too,
so a VAULT_READ landing in the window sees the note empty or half-finished.

Same family as ## 304. (a check and an act in two lock holds) and ## 319. (an
unattended writer holding a stale copy of everything else), except what is
lost here is the boss's actual prose.

The fix moves "seek to end" inside the write itself: O_APPEND, so a second
writer cannot land on a stale offset however the threads interleave.

The interleaving below is FORCED, not hoped for. The real server runs in this
process, and pathlib's read_text is wrapped so that a reader of the note in
question parks on a two-thread barrier after it has read and before it can
write. Pre-fix that is a guaranteed lost update. Post-fix the append branch
never reads the file at all, so the barrier is never reached, and both
paragraphs land.

Run: python3 scripts/test_two_coworkers_appending_to_one_note_both_land.py
"""
from __future__ import annotations

import os
import pathlib
import re
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    print(('  ok    ' if cond else '  FAIL  ') + label
          + (('  - ' + str(detail)) if detail and not cond else ''))
    if not cond:
        FAILS.append(label)


def strip_py_comments(src: str) -> str:
    """Source minus comments and triple-quoted strings - serve.py's own
    explanation of the bad pattern (and this file's) must not be what the
    grep below finds. Tokenized rather than regexed: a naive line.split('#')
    eats the '#' inside string literals and unbalances the docstring pairs
    after it, which silently deleted the code being checked."""
    import io
    import token as _tok
    import tokenize as _tk
    out = []
    for t in _tk.generate_tokens(io.StringIO(src).readline):
        if t.type == _tok.COMMENT:
            continue
        if t.type == _tok.STRING and t.string.lstrip('rbufRBUF')[:3] in ('"""', "'''"):
            out.append((t.type, '""'))
            continue
        out.append((t.type, t.string))
    return _tk.untokenize(out)


# ── the real door, in this process so the interleaving can be forced ───────
def free_port() -> int:
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def http(url, method='GET', data=None, ctype=None):
    headers = {'Content-Type': ctype} if ctype else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:                                  # pragma: no cover
        return 0, str(e).encode()


def boot():
    """serve.py's own ThreadedServer + Handler, in-process."""
    os.environ['GAP_CRON'] = '0'
    os.environ['NEWS_CRON'] = '0'
    os.environ['TOPICS_CRON'] = '0'
    for k in ('SEARCH_WORKER', 'CAFRESOHQ_VAULT_BACKEND', 'OCI_VAULT_NAMESPACE',
              'OCI_VAULT_BUCKET', 'OCI_VAULT_PREFIX', 'CAFRESOHQ_OBSIDIAN_URL',
              'CAFRESOHQ_OBSIDIAN_KEY', 'CAFRESOHQ_API_KEY'):
        os.environ.pop(k, None)
    vault = pathlib.Path(tempfile.mkdtemp(prefix='append-race-vault-'))
    os.environ['CAFRESOHQ_VAULT'] = str(vault)
    os.environ['CAFRESOHQ_HQ_STATE_DIR'] = tempfile.mkdtemp(prefix='append-race-state-')
    os.environ['CAFRESOHQ_ALLOWED_DIRS'] = str(vault)
    os.chdir(ROOT)
    import serve

    port = free_port()
    httpd = serve.ThreadedServer(('127.0.0.1', port), serve.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True,
                     name='append-race-server').start()
    base = 'http://127.0.0.1:%d' % port
    for _ in range(80):
        if http(base + '/missions/scheduled')[0] == 200:
            break
        time.sleep(0.1)
    return base, vault, httpd


def append(base, rel, body):
    return http(base + '/vault/note?path=' + urllib.parse.quote(rel)
                + '&mode=append', 'PUT', body.encode('utf-8'), 'text/markdown')


# ── 1. the forced interleaving ────────────────────────────────────────────
def forced_interleave_check(base, vault) -> None:
    print('=== two appends to one note, forced to overlap ===')
    st, _ = append(base, 'Daily/standup.md', '# Standup\n')
    check('the note exists to be appended to', st == 200, st)

    gate = threading.Barrier(2)
    real_read_text = pathlib.Path.read_text

    def parked_read_text(self, *a, **k):
        data = real_read_text(self, *a, **k)
        if self.name == 'standup.md':
            # Both readers are now holding the same `existing`; whichever
            # writes second is the whole file.
            try:
                gate.wait(timeout=8)
            except (threading.BrokenBarrierError, Exception):
                pass
        return data

    pathlib.Path.read_text = parked_read_text
    codes: dict[str, int] = {}
    try:
        def coworker(who):
            codes[who] = append(
                base, 'Daily/standup.md',
                '\n## %s\n%s reported.\n' % (who, who))[0]

        threads = [threading.Thread(target=coworker, args=(w,), daemon=True,
                                    name='cw-' + w)
                   for w in ('Ada', 'Bran')]
        for t in threads:
            t.start()
        # A serialised append never gets two threads to the barrier at all;
        # break it so a lone parked thread is not held for its full timeout.
        time.sleep(0.5)
        gate.abort()
        for t in threads:
            t.join(timeout=30)
        alive = [t.name for t in threads if t.is_alive()]
    finally:
        pathlib.Path.read_text = real_read_text

    check('both appends were accepted',
          codes.get('Ada') == 200 and codes.get('Bran') == 200, codes)
    check('neither append hung', not alive, alive)
    body = (vault / 'Daily' / 'standup.md').read_text(encoding='utf-8')
    check('the note kept its heading', body.startswith('# Standup'), repr(body[:80]))
    check("Ada's paragraph is on disk - THE TICKET", 'Ada reported.' in body,
          'lost: ' + repr(body))
    check("Bran's paragraph is on disk - THE TICKET", 'Bran reported.' in body,
          'lost: ' + repr(body))
    check('neither paragraph was written twice',
          body.count('Ada reported.') == 1 and body.count('Bran reported.') == 1,
          repr(body))
    check('no torn half-write left behind',
          body.count('# Standup') == 1 and '\x00' not in body, repr(body))


# ── 2. many appends, two clients, the same door ───────────────────────────
def volume_check(base, vault) -> None:
    print('=== forty appends each, two clients at once ===')
    rel = 'Daily/log.md'
    # A fat first line so any read-modify-write has a wide window to lose in.
    append(base, rel, 'padding ' * 4000 + '\n')

    N = 40
    codes: list[int] = []
    clock = threading.Lock()
    start = threading.Barrier(2)

    def client(tag):
        try:
            start.wait(timeout=30)
        except Exception:                                   # pragma: no cover
            pass
        for i in range(N):
            st = append(base, rel, '%s-%02d\n' % (tag, i))[0]
            with clock:
                codes.append(st)

    ts = [threading.Thread(target=client, args=(t,), daemon=True)
          for t in ('ada', 'bran')]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=180)

    check('every append was accepted', codes and all(c == 200 for c in codes),
          sorted(set(codes)))
    body = (vault / 'Daily' / 'log.md').read_text(encoding='utf-8')
    missing = [tag + '-%02d' % i for tag in ('ada', 'bran')
               for i in range(N) if (tag + '-%02d' % i) not in body]
    check('all %d concurrent appends survived on disk' % (2 * N), not missing,
          '%d lost, e.g. %s' % (len(missing), missing[:6]))
    check('the padding line was not clobbered', 'padding ' in body)


# ── 3. the source, comments stripped ──────────────────────────────────────
def source_check() -> None:
    print('=== the append branch does not read-then-write ===')
    # untokenize normalises spacing, so compare with whitespace removed.
    def ns(s):
        return re.sub(r'\s+', '', s)

    src = ns(strip_py_comments((ROOT / 'serve.py').read_text(encoding='utf-8')))
    door = src.split(ns("if path == '/vault/note' and method == 'PUT'"), 1)
    check('the append door is still where the test thinks it is', len(door) == 2)
    if len(door) != 2:
        return
    branch = door[1].split(ns("if path == '/vault/note' and method == 'DELETE'"), 1)[0]
    fs_tail = branch.split(ns('_vault_resolve(rel)'), 1)[-1]
    check('the fs append branch no longer read_texts the note first',
          'read_text' not in fs_tail, fs_tail[:400])
    check('...and no longer write_texts a concatenation of a stale read',
          ns('existing + sep') not in fs_tail, fs_tail[:400])
    check('...it goes through the O_APPEND helper instead',
          ns('_vault_append_local(') in fs_tail, fs_tail[:400])
    helper = (src.split(ns('def _vault_append_local'), 1)[-1]
                 .split(ns('def _vault_rewrite_wikilinks'), 1)[0])
    check('the helper opens for append rather than truncating',
          "'a+b'" in helper or '"a+b"' in helper, helper[:300])
    check('the helper serialises its newline probe against other appenders',
          # #385 generalized the append-only _vault_append_lock into
          # _vault_write_lock, shared with the whole-body write and the
          # wikilink-rewrite paths — same lock, wider name.
          '_vault_write_lock' in helper, helper[:300])


def main() -> int:
    base, vault, httpd = boot()
    try:
        forced_interleave_check(base, vault)
        volume_check(base, vault)
    finally:
        httpd.shutdown()
    source_check()
    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), '; '.join(FAILS)))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
