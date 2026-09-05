#!/usr/bin/env python3
"""The Library has three write doors and only two of them asked.

#140 ("the Library never files what it cannot show") built the general
helper `_vault_hidden_part(rel)` and wired it into two doors: PUT
/vault/note and the destination half of POST /vault/rename. Its own
docstring states the family rule out loud — "The write doors ask this
before touching any backend" — and there is a third write door:
POST /vault/upload.

That door asked only half the question. `fs_routes.upload_name()` refuses
a dotted BASENAME, which is why a picked file called `.env` comes back as
a loud refusal. But the destination is `dir + '/' + name`, and the `dir`
query parameter never met the helper. Drop three files into
`/vault/upload?dir=.archive` and every backend wrote them, the receipt
counted them in `uploaded`, the toast said the files were filed — and
/vault/list, /vault/search and the fs/oci/REST walks all skip any path
with a dotted part, so the boss never saw them again. Exactly the
disappearance #140 was written to end, through the one door #140 did not
touch.

Drives the real server: boots serve.py on a scratch vault and posts real
multipart bodies at the real route.

Run: python3 scripts/test_the_upload_door_asks_the_hidden_question_the_other_write_doors_ask.py
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
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Python source without # comments or docstrings — so this file's own
    prose about the bug can never satisfy a check about the fix."""
    out = re.sub(r'"""[\s\S]*?"""', '""', src)
    out = re.sub(r"'''[\s\S]*?'''", "''", out)
    return re.sub(r'(?m)^\s*#.*$', '', out)


# ── harness (same shape as the #140 suite) ───────────────────────────────
def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def http(url, method='GET', data=None, ctype=None):
    headers = {'Content-Type': ctype} if ctype else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw, st = r.read(), r.status
    except urllib.error.HTTPError as e:
        raw, st = e.read(), e.code
    except Exception as e:
        return 0, {'error': str(e)}
    try:
        return st, json.loads(raw.decode('utf-8'))
    except Exception:
        return st, raw.decode('utf-8', 'replace')


def multipart(files):
    """(body, content-type) for [(filename, bytes), …]."""
    b = 'x-cafresohq-329-boundary'
    out = b''
    for name, data in files:
        out += ('--%s\r\nContent-Disposition: form-data; name="files"; '
                'filename="%s"\r\nContent-Type: application/octet-stream'
                '\r\n\r\n' % (b, name)).encode('utf-8')
        out += data + b'\r\n'
    out += ('--%s--\r\n' % b).encode('utf-8')
    return out, 'multipart/form-data; boundary=' + b


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
        if http(base + '/missions/scheduled')[0] == 200:
            return base, kill
        time.sleep(0.25)
    kill()
    return None, (lambda: None)


def listed(base):
    st, r = http(base + '/vault/list')
    return {f['path'] for f in r.get('files', [])} if st == 200 else set()


def upload(base, folder, files):
    body, ctype = multipart(files)
    url = base + '/vault/upload'
    if folder is not None:
        url += '?dir=' + urllib.parse.quote(folder)
    return http(url, 'POST', body, ctype)


# ── the premise, before the fix means anything ───────────────────────────
def premise_checks():
    print('=== the premise ===')
    serve = strip_comments((ROOT / 'serve.py').read_text(encoding='utf-8'))
    a = serve.find("if path == '/vault/list'")
    b = serve.find("if path == '/vault/note'", a)
    section = serve[a:b] if 0 <= a < b else ''
    check('/vault/list still skips every dotted path part',
          section.count("if any(part.startswith('.') for part in") >= 2,
          'if hidden paths are listed now, this refusal guards nothing and '
          '#140 wants re-deciding, not extending')
    check('the general helper is still the one the other doors ask',
          serve.count('_vault_hidden_part(') >= 4,
          'serve.py lost the helper the write doors share')
    fs = strip_comments((ROOT / 'fs_routes.py').read_text(encoding='utf-8'))
    check("upload_name() still only ever sees the file's own name",
          "split('/')[-1]" in fs,
          'fs_routes.upload_name takes the last path segment — it structurally '
          'cannot see the folder half of the destination')


def server_checks(base, vault):
    print('=== the third write door ===')
    st, r = upload(base, '.archive', [('q3-plan.md', b'# Q3\n'),
                                      ('deck.txt', b'slides\n')])
    err = r.get('error', '') if isinstance(r, dict) else str(r)
    check('an upload into a dotted folder is a 400 — THE TICKET',
          st == 400,
          f'{st} {r} — this door wrote both files, counted them in '
          '`uploaded`, and /vault/list never showed either again')
    check('...and nothing landed on disk behind the refusal',
          not (vault / '.archive').exists(),
          'a refusal that still writes is worse than the silence was')
    check('...the sentence names the folder and the way forward',
          'never lists anything under ".archive"' in err
          and 'leading dot' in err, err)

    st, r = upload(base, 'notes/.drafts', [('q3-plan.md', b'# Q3\n')])
    check('a dotted part deeper in the folder is caught too',
          st == 400 and not (vault / 'notes' / '.drafts').exists(), (st, r))

    st, r = upload(base, '.archive\\win', [('q3-plan.md', b'# Q3\n')])
    check('a backslashed dotted folder cannot sneak past',
          st == 400, (st, r))

    print('=== the doors that already worked still work ===')
    st, r = upload(base, 'plans', [('q3-plan.md', b'# Q3\n')])
    check('a visible folder still files the file',
          st == 200 and isinstance(r, dict) and r.get('count') == 1, (st, r))
    check('...and it is in the list the boss will look at',
          'plans/q3-plan.md' in listed(base), sorted(listed(base)))

    st, r = upload(base, None, [('root-note.md', b'x\n')])
    check('no dir at all is still the vault root, not a refusal',
          st == 200 and (vault / 'root-note.md').exists(), (st, r))

    st, r = upload(base, 'plans', [('.env', b'SECRET=1\n')])
    failed = r.get('failed', []) if isinstance(r, dict) else []
    check('a dotted FILENAME is still refused out loud, per part',
          st == 200 and r.get('count') == 0 and len(failed) == 1
          and 'hidden' in failed[0].get('error', ''), (st, r))

    print('=== the rescue direction stays open ===')
    lost = vault / '.lost'
    lost.mkdir(exist_ok=True)
    (lost / 'plan.md').write_text('# rescued\n', encoding='utf-8')
    st, r = http(base + '/vault/rename', 'POST',
                 json.dumps({'from': '.lost/plan.md', 'to': 'plan.md'}).encode(),
                 'application/json')
    check('an already-hidden note can still be moved back into the light',
          st == 200 and (vault / 'plan.md').exists(),
          f'{st} {r} — refusing this would trap the file in the dark forever')


def main():
    print('the upload door asks the hidden question the other write doors ask')
    premise_checks()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        vault, state, work = td / 'vault', td / 'state', td / 'work'
        for d in (vault, state, work):
            d.mkdir()
        base, kill = boot(vault, state, work)
        if not base:
            check('the server booted', False, 'serve.py never answered')
        else:
            try:
                server_checks(base, vault)
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
