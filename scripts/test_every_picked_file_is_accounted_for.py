#!/usr/bin/env python3
"""Two of three files vanished, and the receipt was a green tick.

Driven on the live office (127.0.0.1:9280) through the Library's own 📤
button, three files picked at once — `quarterly-plan.txt`,
`.env.production`, and one named `   `:

    toast   ✓  "Filed 1 file in the Library."
    tree    quarterly-plan.txt
    disk    quarterly-plan.txt

Two files went into the office and were never mentioned again, under a
green tick. Both upload doors decided a name and then `continue`d past the
ones they didn't like:

    fname = _re.sub(r'[^\\w .()\\[\\]\\-]+', '_', fname).strip()
    if not fname or fname.startswith('.'):
        continue

A part that hits that `continue` reaches neither `saved` nor `errors`, so
the partial-upload warning the client already had could never fire — it is
reached from `res.failed`, and `res.failed` was empty. The sanitizer above
it renames silently too: `Ana's notes.md` is filed as `Ana_s notes.md`, and
a boss who goes looking for the name they typed does not find it.

The Projects door made it worse. POSTing the same three dotfiles to
/fs/upload returned `HTTP 200 {"uploaded": [], "count": 0}` with nothing on
disk, and views/projects.jsx reported it as:

    toast   ✓  "Shared 3 files with acme-site"

because it printed `res.count || files.length` — the boss's own pick count
wearing the server's clothes. Zero is falsy, so the receipt was at its most
confident exactly when the server had done nothing at all.

§7: every honest sentence needs a way forward, and "hidden files are not
accepted" is one. Silence is not. Same shape as #136 — one question asked
in three places, answered three ways — so the decision lives in one
function (fs_routes.upload_name) and the receipt is composed in one
function (app/floor.jsx uploadReceipt) from what the server actually said.

Guards:
  · every part the boss picks comes back either filed or refused, never
    neither — count + failed == picked, at both doors
  · a refusal carries a sentence a boss can read, and something printable
    to call the file by
  · a file filed under a changed name says so
  · an all-refused upload is a 200 with a body, not a thrown 500 — the
    status line used to depend on how many OTHER files were in the pick
  · no receipt is composed from the caller's own file count
  · nothing refused is on disk, and everything reported filed is

Run: python3 scripts/test_every_picked_file_is_accounted_for.py
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
sys.path.insert(0, str(ROOT))
SERVE_RAW = (ROOT / 'serve.py').read_text(encoding='utf-8')
FS_RAW = (ROOT / 'fs_routes.py').read_text(encoding='utf-8')
FLOOR_JSX = (ROOT / 'app' / 'floor.jsx').read_text(encoding='utf-8')
VAULT_JSX = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')
PROJ_JSX = (ROOT / 'views' / 'projects.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_js_comments(src):
    return re.sub(r'/\*[\s\S]*?\*/', '', re.sub(r'^\s*//.*$', '', src, flags=re.M))


def section(src, start, end):
    """A slice between two markers, or '' if either is missing — empty rather
    than 'the rest of the file', so a check can't pass on a string that lives
    in some other handler."""
    a = src.find(start)
    if a < 0:
        return ''
    b = src.find(end, a)
    return src[a:b] if b > a else ''


# ── the pick that started it ──────────────────────────────────────────────
# One of each outcome: filed as typed, refused for being hidden, refused for
# having no usable name, and filed under a name the boss did not type.
PLAIN = ('quarterly-plan.txt', 'text/plain', b'Freight is 41% of spend.\n')
HIDDEN = ('.env.production', 'text/plain', b'SECRET=1\n')
BLANK = ('   ', 'application/octet-stream', b'x')
RENAMED = ('my report@2x.png', 'image/png', b'\x89PNG\r\n\x1a\n' + bytes(range(64)))
PICK = [PLAIN, HIDDEN, BLANK, RENAMED]


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
    bound = '----cafresoupload137'
    body = b''
    for name, ctype, data in parts:
        body += ('--%s\r\nContent-Disposition: form-data; name="files"; '
                 'filename="%s"\r\nContent-Type: %s\r\n\r\n'
                 % (bound, name, ctype)).encode()
        body += data + b'\r\n'
    body += ('--%s--\r\n' % bound).encode()
    return body, 'multipart/form-data; boundary=%s' % bound


def post_files(url, parts):
    """(status, json). Never raises — a 500 here is the defect, not a crash."""
    body, ctype = multipart(parts)
    req = urllib.request.Request(url, data=body,
                                 headers={'Content-Type': ctype}, method='POST')
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


# ── the naming decision, on its own ───────────────────────────────────────
def decision_checks():
    import fs_routes
    print('=== the decision both doors ask ===')
    d = fs_routes.upload_name('quarterly-plan.txt')
    check('an ordinary name is filed as typed',
          d['name'] == 'quarterly-plan.txt' and not d['renamedFrom'] and not d['refusal'], d)

    d = fs_routes.upload_name('.env.production')
    check('a hidden file is refused, not dropped',
          d['name'] is None and bool(d['refusal']), d)
    check('...and the refusal names the file it is about',
          d['shown'] == '.env.production', d)

    d = fs_routes.upload_name('   ')
    check('a name with nothing in it is refused', d['name'] is None and bool(d['refusal']), d)
    check('...with something printable to call it by — a toast cannot say ""',
          bool(d['shown'].strip()), d)

    d = fs_routes.upload_name("Ana's notes.md")
    check('a rename is reported, not performed in silence',
          d['name'] == 'Ana_s notes.md' and d['renamedFrom'] == "Ana's notes.md", d)

    d = fs_routes.upload_name('../../etc/passwd')
    check('a path is still flattened to its last segment', d['name'] == 'passwd', d)
    d = fs_routes.upload_name('..')
    check('.. is refused rather than filed', d['name'] is None, d)

    for raw in ('.env.production', '   ', 'x' * 4):
        d = fs_routes.upload_name(raw)
        bad = [w for w in ('regex', 'sanit', 'Traceback', 'None', 'strip()')
               if d['refusal'] and w in d['refusal']]
        check('the refusal for %r is a sentence, not a diagnosis' % raw, not bad,
              d.get('refusal'))


# ── both doors, live ──────────────────────────────────────────────────────
def library_checks(base, vault):
    print('=== the Library door ===')
    st, up = post_files(base + '/vault/upload', PICK)
    check('the mixed pick is answered at all', st == 200, (st, up))
    if st != 200:
        return
    saved = up.get('uploaded', [])
    failed = up.get('failed', [])
    check('every file the boss picked is accounted for — THE TICKET',
          len(saved) + len(failed) == len(PICK),
          '%d filed + %d refused, out of %d picked — the rest vanished'
          % (len(saved), len(failed), len(PICK)))
    check('the two the office can file are filed', up.get('count') == 2, up)
    check('the two it will not file are named as refused', len(failed) == 2, failed)

    names = {f.get('path', '') for f in failed}
    check('the hidden file is one of them',
          any(n.endswith('.env.production') for n in names), names)
    check('the nameless one is reported under something printable',
          all(n.strip() for n in names) and any('(unnamed)' in n for n in names), names)
    check('every refusal carries a reason', all(f.get('error') for f in failed), failed)

    ren = [f for f in saved if f.get('renamedFrom')]
    check('the renamed file says what it was called',
          len(ren) == 1 and ren[0]['renamedFrom'] == 'my report@2x.png', saved)
    check('...and what it is called now',
          bool(ren) and ren[0]['path'].endswith('my report_2x.png'), saved)

    check('everything reported filed is really on disk',
          all((vault / f['path']).is_file() for f in saved), saved)
    check('nothing refused was written anyway',
          not (vault / '.env.production').exists()
          and not any(p.name.strip() == '' for p in vault.iterdir()),
          sorted(p.name for p in vault.iterdir()))

    # The status line used to depend on how many OTHER files were in the pick:
    # the same refusal was a 200 field beside a good file and a thrown 500 on
    # its own, so the client reported it two different ways.
    st, up = post_files(base + '/vault/upload', [HIDDEN, ('.gitignore', 'text/plain', b'x')])
    check('an all-refused pick is still an answer, not an error', st == 200, (st, up))
    check('...that filed nothing and says so',
          up.get('count') == 0 and len(up.get('failed', [])) == 2, up)


def projects_checks(base, work):
    print('=== the Projects door ===')
    proj = work / 'acme-site'
    proj.mkdir(parents=True, exist_ok=True)
    (proj / 'README.md').write_text('# acme\n', encoding='utf-8')
    url = base + '/fs/upload?path=' + urllib.parse.quote(str(proj))
    st, up = post_files(url, PICK)
    check('the mixed pick is answered at all', st == 200, (st, up))
    if st != 200:
        return
    saved, failed = up.get('uploaded', []), up.get('failed', [])
    check('every file the boss picked is accounted for here too',
          len(saved) + len(failed) == len(PICK),
          '%d shared + %d refused, out of %d picked' % (len(saved), len(failed), len(PICK)))
    check('the two it can share are shared', up.get('count') == 2, up)
    check('every refusal carries a reason', failed and all(f.get('error') for f in failed),
          failed)
    check('the rename is reported', any(f.get('renamedFrom') for f in saved), saved)
    on_disk = sorted(p.name for p in proj.iterdir())
    check('the working tree holds exactly what was reported shared',
          on_disk == sorted(['README.md', 'quarterly-plan.txt', 'my report_2x.png']),
          on_disk)

    st, up = post_files(url, [HIDDEN])
    check('an all-refused share is a 200 with a body', st == 200, (st, up))
    check('...saying nothing was shared', up.get('count') == 0 and up.get('failed'), up)


# ── the receipt itself ────────────────────────────────────────────────────
RECEIPT_CASES = '''
const out = {};
const LIB = {verb: 'Filed', tried: 'file', where: 'in the Library'};
const PROJ = {verb: 'Shared', tried: 'share', where: 'with acme-site'};
out.allGood = uploadReceipt({uploaded: [{path: 'a.md'}, {path: 'b.md'}, {path: 'c.md'}],
                             count: 3}, LIB);
out.mixed = uploadReceipt({uploaded: [{path: 'q.txt'}], count: 1,
                           failed: [{path: '.env.production', error: 'hidden files are not accepted'},
                                    {path: '(unnamed)', error: 'hidden files are not accepted'}]},
                          LIB);
out.noneFiled = uploadReceipt({uploaded: [], count: 0,
                               failed: [{path: '.env.production', error: 'hidden files are not accepted'},
                                        {path: '.gitignore', error: 'hidden files are not accepted'},
                                        {path: '.npmrc', error: 'hidden files are not accepted'}]},
                              PROJ);
out.oneFailed = uploadReceipt({uploaded: [], count: 0,
                               failed: [{path: '.env', error: 'hidden files are not accepted'}]},
                              PROJ);
out.mixedReasons = uploadReceipt({uploaded: [], count: 0,
                                  failed: [{path: 'a', error: 'hidden files are not accepted'},
                                           {path: 'b', error: 'that name has no usable characters'},
                                           {path: 'c', error: 'hidden files are not accepted'},
                                           {path: 'd', error: 'no space left on device'},
                                           {path: 'e', error: 'hidden files are not accepted'}]},
                                 LIB);
out.manySameReason = uploadReceipt({uploaded: [], count: 0,
                                    failed: ['a','b','c','d','e'].map(n => ({path: n, error: 'hidden files are not accepted'}))},
                                   LIB);
out.renamed = uploadReceipt({uploaded: [{path: 'Ana_s notes.md', renamedFrom: "Ana's notes.md"}],
                             count: 1}, LIB);
out.renamedMany = uploadReceipt({uploaded: [{path: 'a_1.md', renamedFrom: 'a@1.md'},
                                            {path: 'b_1.md', renamedFrom: 'b@1.md'}],
                                 count: 2}, LIB);
out.nothing = uploadReceipt({uploaded: [], count: 0}, LIB);
out.noBody = uploadReceipt(null, LIB);
// A caller with no verb still gets a grammatical sentence.
out.verbless = uploadReceipt({uploaded: [], count: 0,
                              failed: [{path: '.env', error: 'hidden files are not accepted'}]}, {});
console.log(JSON.stringify(out));
'''


def receipt_results():
    """Run the shipped uploadReceipt, sliced out of app/floor.jsx.

    Sliced rather than bundled because the point of the check is partly that
    this function stays self-contained: a receipt that needs the view's state
    to be composed is a receipt each view will end up composing itself again.
    """
    m = re.search(r'\nfunction uploadReceipt\(res, opts\) \{[\s\S]*?\n\}\n', FLOOR_JSX)
    if not m:
        return None
    tmp = ROOT / '._receipt137.cjs'
    try:
        tmp.write_text(m.group(0) + RECEIPT_CASES, encoding='utf-8')
        p = subprocess.run(['node', tmp.name], cwd=str(ROOT), capture_output=True,
                           text=True, timeout=120)
        if p.returncode != 0:
            print('  node failed:', (p.stderr or '')[-700:])
            return None
        return json.loads(p.stdout.strip().split('\n')[-1])
    except Exception as e:
        print('  node failed:', e)
        return None
    finally:
        tmp.unlink(missing_ok=True)


def receipt_checks():
    print('=== the sentence the boss reads ===')
    r = receipt_results()
    check('uploadReceipt is in app/floor.jsx and runs standalone', r is not None)
    if not r:
        return

    good = r.get('allGood') or {}
    check('a clean upload is still a green tick',
          good.get('tone') == 'success' and good.get('text') == 'Filed 3 files in the Library.',
          good)

    mixed = r.get('mixed') or {}
    check('a partial upload is not a green tick', mixed.get('tone') == 'warn', mixed)
    check('...and says both halves',
          'Filed 1 file in the Library.' in (mixed.get('text') or '')
          and "Couldn't file 2 — " in (mixed.get('text') or ''), mixed)
    check('...and names the ones that did not make it',
          '.env.production' in (mixed.get('text') or ''), mixed)

    none_filed = r.get('noneFiled') or {}
    txt = none_filed.get('text') or ''
    check('nothing shared is never reported as something shared — THE TICKET',
          not re.search(r'Shared \d', txt), txt)
    check('...it says what actually happened, with the reason',
          txt.startswith("Couldn't share 3 — ")
          and 'hidden files are not accepted' in txt, txt)
    check('...in a warning, not a success', none_filed.get('tone') == 'warn', none_filed)

    one = r.get('oneFailed') or {}
    check('a single refusal is named and explained',
          '.env' in (one.get('text') or '')
          and 'hidden files are not accepted' in (one.get('text') or ''), one)

    txt = (r.get('manySameReason') or {}).get('text') or ''
    check('many refusals under one reason name a few and count the rest',
          txt == "Couldn't file 5 — hidden files are not accepted: a, b, c and 2 more.", txt)

    # Five refusals, three different reasons. Stamping one of them across all
    # five is the bigger lie of the two available: "hidden files are not
    # accepted" over a file that failed because the disk is full sends the
    # boss to rename a file that was never the problem.
    many = r.get('mixedReasons') or {}
    txt = many.get('text') or ''
    check('each reason keeps only the files it is about',
          'hidden files are not accepted: a, c, e' in txt
          and 'that name has no usable characters: b' in txt, txt)
    check('...and a third reason is counted rather than crowding the toast',
          txt.endswith('; and 1 more.') and 'no space left on device' not in txt, txt)

    ren = r.get('renamed') or {}
    check('a file filed under a changed name says both names',
          "Ana's notes.md" in (ren.get('text') or '')
          and 'Ana_s notes.md' in (ren.get('text') or ''), ren)
    check('...and is still a success — it was filed', ren.get('tone') == 'success', ren)
    check('several renames are counted rather than listed',
          '2 were filed under changed names' in ((r.get('renamedMany') or {}).get('text') or ''),
          r.get('renamedMany'))

    vl = (r.get('verbless') or {}).get('text') or ''
    check('a caller that names no verb still reads as English',
          "Couldn't" not in vl and vl.startswith('".env" didn\'t make it'), vl)

    check('an empty pick says nothing at all',
          r.get('nothing') is None and r.get('noBody') is None,
          [r.get('nothing'), r.get('noBody')])


# ── the wiring, so a truthful server can't be re-narrated by a view ───────
def source_checks():
    print('=== one decision, one receipt ===')
    vault_up = section(SERVE_RAW, "if path == '/vault/upload'", "# ---------- Search")
    fs_up = section(FS_RAW, 'def _fs_upload(self):', '# ---- Working-tree file manager')
    check('the Library door asks the shared naming decision',
          'fs_routes.upload_name(' in vault_up, 'serve.py: /vault/upload names files itself again')
    check('the Projects door asks the same one',
          'upload_name(' in fs_up, 'fs_routes.py: _fs_upload names files itself again')
    for label, block in (('Library', vault_up), ('Projects', fs_up)):
        check('the %s door keeps its own sanitizer nowhere' % label,
              "sub(r'[^\\w" not in block,
              'a second copy of the rule is how the two doors drifted apart')
        check('the %s door reports a refusal instead of skipping it' % label,
              "'error': decided['refusal']" in block,
              'a part that reaches neither list is a file that vanished')
        check('the %s door does not turn a refusal into a 500' % label,
              'if not saved and errors' not in block,
              'the same refusal was a field at one count and an exception at another')

    proj = strip_js_comments(PROJ_JSX)
    vault = strip_js_comments(VAULT_JSX)
    check('no receipt is composed from the pick the boss made — THE TICKET',
          'count || files.length' not in proj and '|| files.length' not in proj,
          "views/projects.jsx: `res.count || files.length` reports the boss's "
          'own count back at them when the server filed none of it')
    do_upload = section(proj, 'const doUpload = ', 'const uploadTo =')
    upload_files = section(proj, 'const res = await CafresoHQClient.fsUpload(', 'setBusy(false)')
    on_upload = section(vault, 'const onUpload = ', 'const renameNote =')
    check('the Projects drop zone reads the shared receipt',
          'uploadReceipt(' in do_upload, do_upload[:200])
    check('the Projects tree upload reads it too',
          'uploadReceipt(' in upload_files, upload_files[:200])
    check('the Library 📤 reads it as well', 'uploadReceipt(' in on_upload, on_upload[:200])
    for label, block in (('Projects drop zone', do_upload), ('Projects tree', upload_files),
                         ('Library', on_upload)):
        check('the %s receipt carries the tone the server earned' % label,
              re.search(r'receipt\.tone', block) is not None,
              'a hardcoded success is the tick this ticket is about')

    body = re.search(r'\nfunction uploadReceipt\(res, opts\) \{[\s\S]*?\n\}\n', FLOOR_JSX)
    check('the receipt has no way to see the caller\'s file list',
          body is not None and 'files' not in body.group(0).replace('file${', 'X')
          .replace(' file', 'X').replace('files ', 'X'),
          'uploadReceipt can only report what the server returned')


def main():
    decision_checks()
    receipt_checks()
    source_checks()

    tmp = Path(tempfile.mkdtemp(prefix='upload137-'))
    vault, state, work = tmp / 'vault', tmp / 'hq', tmp / 'work'
    vault.mkdir()
    work.mkdir()
    (vault / 'existing-note.md').write_text('# already here\n', encoding='utf-8')
    base, kill = boot(vault, state, work)
    try:
        if not base:
            check('the office starts', False, 'serve.py never answered /missions/scheduled')
        else:
            library_checks(base, vault)
            projects_checks(base, work)
    finally:
        kill()

    print()
    if FAILS:
        print('%d FAILED: %s' % (len(FAILS), '; '.join(FAILS)))
        return 1
    print('every picked file is accounted for: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
