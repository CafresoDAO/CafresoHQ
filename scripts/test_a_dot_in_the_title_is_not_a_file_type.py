#!/usr/bin/env python3
"""A note titled "Meeting 2026.08.30" was filed as a file the office could
neither open nor search.

`_vault_resolve` appends '.md' only when `PurePosixPath(rel).suffix` is
empty. But `.suffix` is not "the file's type" — it is "everything after the
last dot in the final segment", and note TITLES carry dots that were never an
extension:

    "Research/Meeting 2026.08.30"  → suffix '.30'      → filed as-is
    "Q3 v1.2 plan"                 → suffix '.2 plan'  → filed as-is
    "Roadmap v2.1"                 → suffix '.1'       → filed as-is

So the note lands on disk with NO extension the Library understands, and
_VAULT_TEXT_EXT — the ONE set /vault/list, /vault/search and /vault/file all
read — does not contain '.30', '.1' or '.2 plan'. Two things follow, both
visible to the boss:

  · /vault/list flags the row `isBinary: true`, so views/vault.jsx sends the
    note to the DOWNLOAD door instead of the editor that just wrote it.
  · /vault/search never reads its BODY — it takes the name-only arm meant for
    decks and PDFs, so the note's own text is unfindable.

The write door itself answers 200 "Saved" the whole time. This is the write
path a coworker's VAULT_NEW and the night shift take, and dated/versioned
titles are most of what they write.

The fix: a suffix counts as a file type only when it is SHAPED like one —
1-8 alphanumerics with at least one letter (_VAULT_EXT_RE). Every real
extension still keeps itself ('.md', '.html', '.pptx', '.7z'); a version
number or a date fragment gets the '.md' default like any other bare slug.
Notes ALREADY filed the old way stay reachable at the exact path
/vault/list shows for them — `is_file()` holds that door open.

Run: python3 scripts/test_a_dot_in_the_title_is_not_a_file_type.py
"""
import json
import os
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


def boot(vault_root, state_dir):
    port = free_port()
    env = dict(os.environ, PORT=str(port), CAFRESOHQ_VAULT=str(vault_root),
               CAFRESOHQ_HQ_STATE_DIR=str(state_dir))
    for k in ('OCI_VAULT_NAMESPACE', 'OCI_VAULT_BUCKET', 'OCI_VAULT_PREFIX',
              'CAFRESOHQ_VAULT_BACKEND', 'CAFRESOHQ_OBSIDIAN_URL',
              'CAFRESOHQ_OBSIDIAN_KEY', 'CAFRESOHQ_API_KEY'):
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
        if http(base + '/vault/status')[0] == 200:
            return base, kill
        time.sleep(0.25)
    kill()
    return None, (lambda: None)


def q(rel):
    return urllib.parse.quote(rel)


def rows(base):
    st, r = http(base + '/vault/list')
    return {f['path']: f for f in r.get('files', [])} if st == 200 else {}


DATED = 'Research/Meeting 2026.08.30'
VERSIONED = 'Plans/Q3 v1.2 plan'
BODY = b'# Standup\n\nrenegotiate the warehouse lease before October.\n'


def server_checks(base, vault):
    print('=== a dated title is a note, not a file type ===')
    st, r = http(base + '/vault/note?path=' + q(DATED), 'PUT', BODY)
    check('the write door still says 200', st == 200, (st, r))
    check('...and it landed as a MARKDOWN note — THE TICKET',
          (vault / 'Research' / 'Meeting 2026.08.30.md').is_file(),
          'on disk: %s — "%s" read `.30` as the file type, so the note was '
          'filed with no extension the Library knows'
          % (sorted(p.name for p in (vault / 'Research').glob('*'))
             if (vault / 'Research').is_dir() else [], DATED))

    row = rows(base).get(DATED + '.md')
    check('...the Library lists it as text, not as a download',
          bool(row) and row.get('isBinary') is False,
          f'{row} — isBinary sends views/vault.jsx to the download door '
          'instead of the editor that just wrote the note')

    st, body = http(base + '/vault/note?path=' + q(DATED))
    check('...and the editor door reads it back',
          st == 200 and 'warehouse lease' in str(body), (st, str(body)[:200]))

    st, r = http(base + '/vault/search?q=' + q('warehouse lease'))
    hits = [h['path'] for h in r.get('hits', [])] if st == 200 else []
    check('...search finds it BY ITS BODY',
          DATED + '.md' in hits,
          f'{hits} — an unknown extension takes search\'s name-only arm, so '
          'the note\'s own text is unfindable')

    print('=== a version number in the title, same story ===')
    st, r = http(base + '/vault/note?path=' + q(VERSIONED), 'PUT', BODY)
    check('a spaced dot fragment ("v1.2 plan") is not an extension either',
          st == 200 and (vault / 'Plans' / 'Q3 v1.2 plan.md').is_file(),
          (st, sorted(p.name for p in (vault / 'Plans').glob('*'))
           if (vault / 'Plans').is_dir() else []))

    print('=== every REAL extension still keeps itself ===')
    st, _ = http(base + '/vault/note?path=' + q('Sites/launch.html'),
                 'PUT', b'<h1>hi</h1>\n')
    check('.html is untouched — the artifact the front door produces',
          st == 200 and (vault / 'Sites' / 'launch.html').is_file()
          and not (vault / 'Sites' / 'launch.html.md').exists(),
          (st, sorted(p.name for p in (vault / 'Sites').glob('*'))
           if (vault / 'Sites').is_dir() else []))
    st, _ = http(base + '/vault/note?path=' + q('Sites/notes.md'),
                 'PUT', b'x\n')
    check('.md is untouched',
          st == 200 and (vault / 'Sites' / 'notes.md').is_file(), st)
    st, _ = http(base + '/vault/note?path=' + q('Inbox/idea'), 'PUT', b'x\n')
    check('a bare slug still gets the .md default',
          st == 200 and (vault / 'Inbox' / 'idea.md').is_file(), st)

    print('=== notes already filed the old way stay reachable ===')
    old = vault / 'Legacy'
    old.mkdir(parents=True, exist_ok=True)
    (old / 'Report v3.1').write_text('# old\n\nthe hangar survey.\n',
                                     encoding='utf-8')
    listed = rows(base)
    check('...the list still shows the path it is really filed at',
          'Legacy/Report v3.1' in listed, sorted(listed))
    st, body = http(base + '/vault/note?path=' + q('Legacy/Report v3.1'))
    check('...and that exact path still opens — no 404 on a listed file',
          st == 200 and 'hangar survey' in str(body),
          f'{st} {str(body)[:160]} — appending .md to a path the list shows '
          'would 404 a file sitting in plain sight')


def main():
    with tempfile.TemporaryDirectory() as td:
        vault = Path(td) / 'vault'
        vault.mkdir(parents=True)
        state = Path(td) / 'state'
        base, kill = boot(vault, state)
        if not base:
            print('  FAIL  serve.py did not come up')
            return 1
        try:
            server_checks(base, vault)
        finally:
            kill()
    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), '; '.join(FAILS)))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
