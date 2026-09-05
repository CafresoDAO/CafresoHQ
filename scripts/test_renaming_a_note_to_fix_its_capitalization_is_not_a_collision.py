#!/usr/bin/env python3
"""Fixing a note's capitalization was refused as a collision with itself.

The Library's ✎ button opens a prompt pre-filled with the note's own
path, so the most ordinary edit anyone makes there is a capital letter:
"meeting notes.md" → "Meeting Notes.md". POST /vault/rename (fs backend,
the shipping default) answered that with

    409 {"error": "target already exists"}

and the UI said "Couldn't move that note — target already exists."  The
file it was pointing at was the note itself: on macOS/APFS and on
Windows the filesystem opens names case-insensitively, so
`d_path.exists()` is true for every case-variant of the source. The note
kept its old title forever, and the message blamed a second note that
never existed.

Measured live against the real server on this Mac, before the fix:

    POST /vault/rename {"from":"meeting.md","to":"Meeting.md"}
      → {"error": "target already exists"}      # meeting.md still there

`os.replace` performs a case-only rename correctly on this volume — it
was only the guard in front of it that refused.

Now the collision check asks whether the destination is a DIFFERENT file
(os.path.samefile), not merely whether the name resolves to something. A
real collision — two distinct notes — is still refused with 409.

Run: python3 scripts/test_renaming_a_note_to_fix_its_capitalization_is_not_a_collision.py
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


def get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=10) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:                                    # noqa: BLE001
        return 0, str(e)


def rename(base, src, dst):
    req = urllib.request.Request(
        base + '/vault/rename',
        data=json.dumps({'from': src, 'to': dst}).encode('utf-8'),
        headers={'content-type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8', 'replace'))
        except Exception:                                     # noqa: BLE001
            return e.code, {}
    except Exception as e:                                    # noqa: BLE001
        return 0, {'error': str(e)}


def case_insensitive(d):
    """Does this volume open names case-insensitively? (macOS/APFS and
    Windows: yes. A case-sensitive volume never had this bug.)"""
    probe = Path(d) / 'CaseProbe.tmp'
    probe.write_text('x', encoding='utf-8')
    try:
        return (Path(d) / 'caseprobe.tmp').exists()
    finally:
        probe.unlink()


def main():
    print('renaming a note to fix its capitalization is not a collision')
    serve = (ROOT / 'serve.py').read_text(encoding='utf-8')

    # ── structure: the guard asks "is it a DIFFERENT file", not "is there
    #    anything at that name" ────────────────────────────────────────
    check('the fs rename collision check consults samefile',
          'samefile' in serve and 'target already exists' in serve)

    with tempfile.TemporaryDirectory() as td:
        vault = Path(td)
        (vault / 'meeting.md').write_text(
            'Notes from the Q3 sync.\n', encoding='utf-8')
        (vault / 'linker.md').write_text(
            'See [[meeting]] for the details.\n', encoding='utf-8')
        (vault / 'other.md').write_text('unrelated\n', encoding='utf-8')

        insensitive = case_insensitive(td)
        if not insensitive:
            print('  note  this volume is case-SENSITIVE — the collision '
                  'never fired here; running the real-collision half only')

        port = free_port()
        base = 'http://127.0.0.1:%d' % port
        env = dict(os.environ, PORT=str(port), CAFRESOHQ_VAULT=str(vault))
        proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=ROOT, env=env,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        try:
            for _ in range(80):
                if get(base, '/health')[0] == 200:
                    break
                time.sleep(0.25)
            else:
                check('server came up', False, 'no /health after 20s')
                return 1

            s, body = rename(base, 'meeting.md', 'Meeting.md')
            check('a capital letter is accepted', s == 200, body)
            check('...the file on disk carries the new title',
                  'Meeting.md' in os.listdir(str(vault))
                  if insensitive else True,
                  os.listdir(str(vault)))
            check('...the contents survived the rename',
                  (vault / 'Meeting.md').read_text(encoding='utf-8')
                  == 'Notes from the Q3 sync.\n')
            check('...the note the boss sees is titled the new way',
                  '"title": "Meeting"' in get(base, '/vault/list')[1],
                  get(base, '/vault/list')[1][:200])
            check('...and the inbound wikilink followed it',
                  '[[Meeting]]' in (vault / 'linker.md').read_text(
                      encoding='utf-8'),
                  (vault / 'linker.md').read_text(encoding='utf-8'))

            # A genuine collision — two different notes — is still refused,
            # or this "fix" would silently eat one of them.
            s2, body2 = rename(base, 'other.md', 'Meeting.md')
            check('a real collision is still refused', s2 == 409, body2)
            check('...and neither note was harmed',
                  (vault / 'other.md').exists()
                  and (vault / 'Meeting.md').read_text(encoding='utf-8')
                  == 'Notes from the Q3 sync.\n')
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
