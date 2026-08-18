#!/usr/bin/env python3
"""The Library filed a note at a path it can never show, and said "Saved".

Driven live: Library, New note, path `.drafts/q3-plan`, type a line, wait
2.5 seconds:

    editor   "Saved"
    disk     .drafts/q3-plan.md — real, readable, full of the boss's text
    list     15 files, none of them this one

Every backend's listing skips dotted parts — serve.py's fs and oci branches
filter `part.startswith('.')` outright, and the REST walk skips dot-entries
at every level — so the write doors could file a note that no list in the
product would ever show again. POST /vault/rename did the same in the other
direction: a VISIBLE note moved to `.archive/` got a 200 and vanished from
the count. #136 was this disappearance at the upload door and #137 made that
door refuse hidden files out loud; the editor's own doors kept filing them
in silence.

The invariant this suite pins: nothing the Library cannot show is accepted
through a door that says "Saved". The refusal happens at BOTH ends — the
server (one sentence for the boss, a coworker's VAULT_* tool and the night
shift alike) and the client (BEFORE a buffer opens, because the 2.5s
autosave files an open buffer without the boss pressing anything). And the
rescue direction stays open on purpose: a file ALREADY invisible can still
be read, renamed out, and deleted — refusing those would trap it in the
dark forever.

Run: python3 scripts/test_the_library_never_files_what_it_cannot_show.py
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
SERVE_RAW = (ROOT / 'serve.py').read_text(encoding='utf-8')
VAULT_RAW = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# ── the coupling the ticket rests on ──────────────────────────────────────
def premise_checks():
    print('=== the premise: every list skips dotted parts ===')
    # If a listing ever starts SHOWING dotted paths, the refusal below stops
    # protecting anything real and becomes policy that should be re-decided,
    # not silently inherited. This check is the tripwire for that re-decision.
    # Counted INSIDE the /vault/list handler, not file-wide: /vault/search
    # carries the same guard line, and a file-wide count let the fs listing
    # lose its skip while the tally stayed high enough to pass.
    a = SERVE_RAW.find("if path == '/vault/list'")
    b = SERVE_RAW.find("if path == '/vault/note'", a)
    list_section = SERVE_RAW[a:b] if 0 <= a < b else ''
    check('the fs and oci listings still skip dotted parts',
          list_section.count("if any(part.startswith('.') for part in") >= 2,
          'serve.py /vault/list stopped hiding dotted paths — if hidden files '
          'are shown now, the write-door refusal is guarding a rule that no '
          'longer exists and #140 should be re-decided, not patched')
    check('the client still autosaves an open buffer unprompted',
          'Autosave' in VAULT_RAW and '2500' in VAULT_RAW,
          "views/vault.jsx: if autosave is gone, the client-side refusal in "
          'newNote loses its stated reason (a buffer that only saves on '
          'command could ask at save time instead) — re-read the comment '
          'above _hiddenPart before relying on this suite')


# ── the client, before there is a buffer to lose ──────────────────────────
def brace_lift(src, header, start=0):
    """`header` plus its balanced `{ … }` body, verbatim. Anchored on the
    DECLARATION, never the fix: a lift anchored on the fix returns '' when
    the fix is removed, and a check that cannot find its subject is skipped
    rather than failed."""
    i = src.index(header, start)
    j = src.index('{', i + len(header) - 1)
    d, k = 0, j
    while k < len(src):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                return src[i:k + 1]
        k += 1
    raise SystemExit('unbalanced braces lifting ' + header)


def run_js(js):
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-1600:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(p.stdout.strip().split('\n')[-1])


STUBS = """
const says = [];
const opened = [];
const renames = [];
const say = (text, kind = 'info') => says.push({ text, kind });
const snag = (label, e) => says.push({ text: label, kind: 'snag' });
const setOpenNote = (v) => opened.push(v);
const setSaveState = () => {};
const refresh = async () => {};
const CafresoHQClient = { vaultRename: async (a, b) => renames.push([a, b]) };
const saveNoteRef = { current: async () => {} };
globalThis.window = globalThis;
"""


def client_checks():
    print('=== the client: refuse at the prompt, before the buffer ===')
    helpers = brace_lift(VAULT_RAW, 'const _hiddenPart = (path) => {')
    msg = re.search(r'const _hiddenMsg =[\s\S]*?;\n', VAULT_RAW)
    if not msg:
        check('_hiddenMsg exists in views/vault.jsx', False)
        return
    new_note = brace_lift(VAULT_RAW, 'const newNote = async () => {')
    ren_note = brace_lift(VAULT_RAW, 'const renameNote = async () => {')

    def drive(fn, call, answer, note=None):
        js = (STUBS
              + 'const openNoteRef = { current: %s };\n'
              % (json.dumps(note) if note else 'null')
              + f'window.hqPrompt = async () => {json.dumps(answer)};\n'
              + helpers + '\n' + msg.group(0)
              + fn + '\n' + f'await {call};\n'
              + 'console.log(JSON.stringify({ says, opened, renames }));')
        return run_js(js)

    r = drive(new_note, 'newNote()', '.drafts/q3-plan')
    errs = [s for s in r['says'] if s['kind'] == 'error']
    check('a dotted new-note path is refused out loud — THE TICKET',
          len(errs) == 1,
          f"{r['says']} — the office used to open the buffer, autosave it "
          '2.5s later, and say "Saved" about a note no list would ever show')
    check('...before any buffer exists', r['opened'] == [],
          f"{r['opened']} — a buffer at a dotted path is a note the autosave "
          'will file without the boss pressing anything')
    check('...naming the folder and the way forward',
          errs and 'never lists anything under ".drafts"' in errs[0]['text']
          and 'leading dot' in errs[0]['text'], errs)

    r = drive(new_note, 'newNote()', 'Inbox/.hidden/idea')
    check('a dotted part in the MIDDLE of the path is caught too',
          any(s['kind'] == 'error' for s in r['says']) and r['opened'] == [], r)

    r = drive(new_note, 'newNote()', 'Inbox/idea')
    check('a clean path still opens a buffer, .md appended, nothing scolded',
          r['opened'] == [{'path': 'Inbox/idea.md', 'id': None,
                           'content': '', 'dirty': True}]
          and not any(s['kind'] == 'error' for s in r['says']), r)

    r = drive(new_note, 'newNote()', '')
    check('a cancel stays a silent no-op',
          r['says'] == [] and r['opened'] == [], r)

    NOTE = {'path': 'notes/plan.md', 'id': 'n1', 'content': '', 'dirty': False}
    r = drive(ren_note, 'renameNote()', '.archive/plan.md', NOTE)
    check('a dotted rename DESTINATION is refused, nothing moved',
          any(s['kind'] == 'error' for s in r['says']) and r['renames'] == [],
          f'{r} — the server answers this with a 400 now, but by then the '
          'dialog has closed; the refusal belongs at the prompt')
    r = drive(ren_note, 'renameNote()', 'plans/q4.md', NOTE)
    check('a clean rename still goes through',
          r['renames'] == [['notes/plan.md', 'plans/q4.md']], r)
    r = drive(ren_note, 'renameNote()', 'plan.md',
              {'path': '.lost/plan.md', 'id': 'n2', 'content': '', 'dirty': False})
    check('a dotted SOURCE stays movable — the rescue path out of the dark',
          r['renames'] == [['.lost/plan.md', 'plan.md']],
          f'{r} — refusing this traps an already-invisible file forever; '
          'only destinations are checked, on purpose')


# ── the server, one sentence for every caller ─────────────────────────────
def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def http(url, method='GET', data=None, ctype=None):
    """(status, parsed-or-raw body). Never raises."""
    headers = {'Content-Type': ctype} if ctype else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            st = r.status
    except urllib.error.HTTPError as e:
        raw, st = e.read(), e.code
    except Exception as e:
        return 0, {'error': str(e)}
    try:
        return st, json.loads(raw.decode('utf-8'))
    except Exception:
        return st, raw.decode('utf-8', 'replace')


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


def q(rel):
    return urllib.parse.quote(rel)


def listed(base):
    st, r = http(base + '/vault/list')
    return {f['path'] for f in r.get('files', [])} if st == 200 else set()


def server_checks(base, vault):
    print('=== the write doors ===')
    st, r = http(base + '/vault/note?path=' + q('.drafts/q3-plan.md'),
                 'PUT', b'# Q3\n')
    err = r.get('error', '') if isinstance(r, dict) else str(r)
    check('PUT to a dotted path is a 400, not a "Saved" — THE TICKET',
          st == 400,
          f'{st} {r} — this door filed `.drafts/q3-plan.md`, said Saved, and '
          'the list never showed it again')
    check('...nothing landed on disk behind the refusal',
          not (vault / '.drafts' / 'q3-plan.md').exists(),
          'a refusal that still writes is worse than the silence was')
    check('...the refusal names the folder and the way forward',
          'never lists anything under ".drafts"' in err
          and 'leading dot' in err, err)

    st, r = http(base + '/vault/note?path=' + q('.drafts/log.md')
                 + '&mode=append', 'PUT', b'line\n')
    check('append is the same door and refuses the same way',
          st == 400 and not (vault / '.drafts' / 'log.md').exists(), (st, r))

    st, r = http(base + '/vault/note?path=' + q('.hidden-note.md'),
                 'PUT', b'x\n')
    check('a dotted FILENAME is refused, not only dotted folders',
          st == 400 and not (vault / '.hidden-note.md').exists(), (st, r))

    st, r = http(base + '/vault/note?path=' + q('.drafts\\win-plan.md'),
                 'PUT', b'x\n')
    check('a backslashed dotted path cannot sneak past',
          st == 400, (st, r))

    st, r = http(base + '/vault/note?path=' + q('plans/q3-plan.md'),
                 'PUT', b'# Q3\n')
    check('a visible path is still filed', st == 200, (st, r))
    check('...and is in the list the boss will look at',
          'plans/q3-plan.md' in listed(base),
          'filed but unlisted is the ticket all over again')

    print('=== the rename door ===')
    (vault / 'keep.md').write_text('# keep\n', encoding='utf-8')
    st, r = http(base + '/vault/rename', 'POST',
                 json.dumps({'from': 'keep.md', 'to': '.archive/keep.md'})
                 .encode(), 'application/json')
    err = r.get('error', '') if isinstance(r, dict) else str(r)
    check('a visible note cannot be moved into the dark',
          st == 400, f'{st} {r} — this used to be a 200, and the note left '
          'every list the room keeps')
    check('...the note stayed where it was',
          (vault / 'keep.md').exists()
          and not (vault / '.archive' / 'keep.md').exists()
          and 'keep.md' in listed(base), sorted(listed(base)))
    check('...with the folder named and the way forward in the sentence',
          '".archive"' in err and 'leading dot' in err, err)

    print('=== the rescue direction stays open ===')
    lost = vault / '.lost'
    lost.mkdir(exist_ok=True)
    (lost / 'plan.md').write_text('# found again\n', encoding='utf-8')
    st, body = http(base + '/vault/note?path=' + q('.lost/plan.md'))
    check('an already-invisible note is still READABLE',
          st == 200 and 'found again' in str(body),
          f'{st} — a file the list cannot show still needs a door out, not '
          'a second lock')
    st, r = http(base + '/vault/rename', 'POST',
                 json.dumps({'from': '.lost/plan.md', 'to': 'rescued-plan.md'})
                 .encode(), 'application/json')
    check('a dotted SOURCE renames out into the light',
          st == 200 and not (lost / 'plan.md').exists()
          and 'rescued-plan.md' in listed(base),
          f'{st} {r} — the one move that FIXES an invisible file; refusing '
          'it traps the file forever')
    junk = vault / '.junk'
    junk.mkdir(exist_ok=True)
    (junk / 'old.md').write_text('x\n', encoding='utf-8')
    st, r = http(base + '/vault/note?path=' + q('.junk/old.md'), 'DELETE')
    check('an already-invisible note can still be DELETED',
          st == 200 and not (junk / 'old.md').exists(), (st, r))

    print('=== a traversal is not a hidden file ===')
    st, r = http(base + '/vault/note?path=' + q('../escape.md'), 'PUT', b'x\n')
    err = (r.get('error', '') if isinstance(r, dict) else str(r)).lower()
    check('`..` is refused as the traversal it is, not called hidden',
          st == 400 and 'escapes' in err and 'hidden' not in err,
          f'{st} {r} — "drop the leading dot" over a traversal attempt sends '
          'the boss to rename a file that was never the problem')


def main():
    premise_checks()
    print()
    client_checks()
    print()

    tmp = Path(tempfile.mkdtemp(prefix='library140-'))
    vault, state, work = tmp / 'vault', tmp / 'hq', tmp / 'work'
    vault.mkdir()
    work.mkdir()
    (vault / 'existing-note.md').write_text('# already here\n', encoding='utf-8')
    base, kill = boot(vault, state, work)
    try:
        if not base:
            check('the office starts', False,
                  'serve.py never answered /missions/scheduled')
        else:
            server_checks(base, vault)
    finally:
        kill()

    print()
    if FAILS:
        print('%d FAILED: %s' % (len(FAILS), '; '.join(FAILS)))
        return 1
    print('the Library never files what it cannot show: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
