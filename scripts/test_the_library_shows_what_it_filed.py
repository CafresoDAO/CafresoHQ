#!/usr/bin/env python3
"""The Library files a deck, says so, and then won't show it.

Driven on the live office (127.0.0.1:9280) through the 📤 button's own
hidden <input type="file">, four files at once:

    toast   "Filed 1 file in the Library."
    disk     board-pack.pdf  chart.png  q3-board-deck.pptx  vendor-summary.html
    tree     ▸ 📁 Deliveries
             ▸ 📁 Research
    list     6 files, every one of them a .md, none of them the four

The office accepted the files, wrote them where it said it would, told the
boss it had, and then the room they were filed into showed two folders and
nothing else. §3.6 calls this surface the cabinet — the story of the whole
product. A cabinet that hides what you put in it is not one.

Three doors answered the question "what is in the Library" and all three
answered differently:

    /vault/list      root.rglob('*.md')
    /vault/search    root.rglob('*.md') + root.rglob('*.html')
    /vault/note      read_text('utf-8')  → 500 "'utf-8' codec can't decode
                                            byte 0x89 in position 0"

so a search for "vendor" returned `vendor-summary.html` and the file tree
in the same pane said no such file existed; and a boss who clicked a filed
deck got a Python codec error, because the client raises `j.error` verbatim.

There was also nowhere for a deck to go. The view has had an `isBinary`
branch since the encrypted bridge vault started sending that flag, and its
whole content is a notice telling the boss to go and look at another
website — which is the entire truth in bridge mode and false on every
server backend, where the file is on the boss's own disk. No server backend
ever set `isBinary`, so the branch had never once run; the moment the
listing widened, it would have started lying. §5: a wrong door is worse
than a locked one, and §7: an honest sentence needs a way forward.

The fix is one set of extensions the editor can open, read by every door
that answers the question, plus GET /vault/file — the raw door — so that
"the editor can't open this" is a sentence with a button next to it.

Guards:
  · everything filed is listed, on every backend that lists
  · list and search agree — no hit for a file the tree denies
  · isBinary is set, and set correctly, so the view can route
  · /vault/file returns the exact bytes, and refuses to escape the folder
  · markup the office did not author is served as an attachment, nosniff
  · the editor's door refuses a deck without spelling a codec at the boss
  · the view sends server-backend binaries to a panel with a download, and
    keeps the bridge notice for the bridge
  · no Save button over a file the editor never opened

Run: python3 scripts/test_the_library_shows_what_it_filed.py
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
VAULT_JSX = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')
CORE_JSX = (ROOT / 'views' / 'core.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_py_comments(src):
    return re.sub(r'^\s*#.*$', '', src, flags=re.M)


def strip_js_comments(src):
    return re.sub(r'/\*[\s\S]*?\*/', '', re.sub(r'^\s*//.*$', '', src, flags=re.M))


def section(src, start, end):
    """A slice between two markers, or '' if either is missing — empty rather
    than 'the rest of the file', so a check can't pass by finding its string
    in some other handler."""
    a = src.find(start)
    if a < 0:
        return ''
    b = src.find(end, a)
    return src[a:b] if b > a else ''


def py_section(start, end):
    """A slice of serve.py taken BEFORE comments are stripped.

    Handlers here are separated by `# ---------- Name ----------` banners,
    which is to say by comments — slicing the stripped source looks for
    markers that stripping has already deleted, and every check below the
    cut then reports FAIL against a fix that is in the file. Cut first,
    strip second.
    """
    return strip_py_comments(section(SERVE_RAW, start, end))


# ── the fixture: one of everything a Library is supposed to hold ──────────
PNG = b'\x89PNG\r\n\x1a\n' + bytes(range(256)) * 2
PPTX = b'PK\x03\x04\x14\x00' + bytes(range(256)) * 3
PDF = b'%PDF-1.4\n' + bytes(range(256))
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>1</script></svg>'
HTML = b'<h1>Vendor summary</h1>\n<p>Freight dominates.</p>'
UPLOADS = [
    ('q3-board-deck.pptx',
     'application/vnd.openxmlformats-officedocument.presentationml.presentation',
     PPTX, True, 'attachment'),
    ('chart.png', 'image/png', PNG, True, 'inline'),
    ('board-pack.pdf', 'application/pdf', PDF, True, 'inline'),
    ('logo.svg', 'image/svg+xml', SVG, True, 'attachment'),
    ('vendor-summary.html', 'text/html', HTML, False, 'attachment'),
]


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def get(url):
    """(status, headers, body-bytes). Never raises — a dead server is a FAIL
    with a readable detail, not a traceback halfway down the run."""
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()
    except Exception as e:
        return 0, {}, str(e).encode()


def get_json(url):
    s, _h, raw = get(url)
    try:
        return s, json.loads(raw.decode('utf-8'))
    except Exception:
        return s, {}


def multipart(parts):
    bound = '----cafresolibrary136'
    body = b''
    for name, ctype, data in parts:
        body += ('--%s\r\nContent-Disposition: form-data; name="files"; '
                 'filename="%s"\r\nContent-Type: %s\r\n\r\n'
                 % (bound, name, ctype)).encode()
        body += data + b'\r\n'
    body += ('--%s--\r\n' % bound).encode()
    return body, 'multipart/form-data; boundary=%s' % bound


def boot(vault_root, state_dir):
    port = free_port()
    env = dict(os.environ, PORT=str(port), CAFRESOHQ_VAULT=str(vault_root),
               CAFRESOHQ_HQ_STATE_DIR=str(state_dir))
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


def live_checks(base, vault):
    # ── the ticket: file it, then find it ────────────────────────────────
    body, ctype = multipart([(n, c, d) for n, c, d, _b, _disp in UPLOADS])
    req = urllib.request.Request(base + '/vault/upload', data=body,
                                 headers={'Content-Type': ctype}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            up = json.loads(r.read().decode('utf-8'))
    except Exception as e:
        check('the upload door takes the files', False, e)
        return
    filed = [f['path'] for f in up.get('uploaded', [])]
    check('the upload door takes every file the boss picked',
          len(filed) == len(UPLOADS), [filed, '— the fixture is the point'])
    check('...and they really are on disk',
          all((vault / p).is_file() for p in filed),
          '— nothing below means anything if the upload was a no-op')

    s, j = get_json(base + '/vault/list')
    listed = {f['path']: f for f in j.get('files', [])}
    check('everything the office said it filed is in the Library listing',
          s == 200 and not [p for p in filed if p not in listed],
          [s, '— missing: %s' % [p for p in filed if p not in listed]])
    check('...and the note that was there before still is',
          'Research/vendor-notes.md' in listed,
          '— widening the glob must not drop the notes')
    check('...and dotfiles stay out of it',
          not [p for p in listed if p.startswith('.') or '/.' in p],
          sorted(listed))

    # ── the flag the view routes on ──────────────────────────────────────
    for name, _c, _d, want_bin, _disp in UPLOADS:
        row = listed.get(name) or {}
        check('%s is marked %s' % (name, 'unopenable' if want_bin else 'openable'),
              row.get('isBinary') is want_bin,
              [row.get('isBinary'), '— the view routes on this'])
    md = listed.get('Research/vendor-notes.md') or {}
    check('a note is not marked unopenable', md.get('isBinary') is False, md)
    check('a note keeps its bare title', md.get('title') == 'vendor-notes', md)
    check('a deck keeps its extension in the title',
          (listed.get('q3-board-deck.pptx') or {}).get('title') == 'q3-board-deck.pptx',
          '— "q3-board-deck" and "q3-board-deck.pptx" are different promises')

    # ── the two rooms agree ──────────────────────────────────────────────
    s, j = get_json(base + '/vault/search?q=vendor')
    hits = [h['path'] for h in j.get('hits', [])]
    check('search finds the page the starter task files',
          'vendor-summary.html' in hits, [s, hits, '— non-vacuity for the next check'])
    check('search never returns a file the listing denies exists',
          not [h for h in hits if h not in listed],
          [h for h in hits if h not in listed])

    # ── the raw door ─────────────────────────────────────────────────────
    for name, _c, data, want_bin, want_disp in UPLOADS:
        s, h, raw = get(base + '/vault/file?path=' + urllib.parse.quote(name))
        check('/vault/file hands back %s byte for byte' % name,
              s == 200 and raw == data, [s, len(raw), len(data)])
        check('...and serves it %s' % want_disp,
              h.get('content-disposition', '').startswith(want_disp),
              h.get('content-disposition'))
        check('...with sniffing off', h.get('x-content-type-options') == 'nosniff',
              h.get('x-content-type-options'))
    s, h, _raw = get(base + '/vault/file?path=' + urllib.parse.quote('logo.svg'))
    check('markup the office did not author is never rendered at its own origin',
          'attachment' in h.get('content-disposition', ''),
          [h.get('content-disposition'),
           '— an .svg is scriptable and this route is same-origin'])
    s, _h, _raw = get(base + '/vault/file?path=../../../etc/passwd')
    check('the raw door refuses to leave the Library', s in (400, 404), s)
    s, _h, _raw = get(base + '/vault/file?path=nothing-here.pptx')
    check('...and 404s a file that was never filed', s == 404, s)

    # ── the editor's door, asked for a deck ──────────────────────────────
    s, j = get_json(base + '/vault/note?path=' + urllib.parse.quote('chart.png'))
    check('the editor door refuses a deck instead of failing on it',
          s == 415, [s, j])
    err = (j.get('error') or '').lower()
    check('...without spelling a codec at the boss',
          not any(w in err for w in ('utf-8', 'codec', '0x', 'byte ')),
          j.get('error'))
    check('...and names where the file can actually be got',
          '/vault/file' in (j.get('download') or ''), j)
    s, _h, raw = get(base + '/vault/note?path=' + urllib.parse.quote('vendor-summary.html'))
    check('a page still opens in the editor', s == 200 and raw == HTML, [s, raw[:40]])


def source_checks():
    src = strip_py_comments(SERVE_RAW)
    ui = strip_js_comments(VAULT_JSX)
    core = strip_js_comments(CORE_JSX)

    # ── one set, not three globs ─────────────────────────────────────────
    check('the office has one list of what its editor can open',
          re.search(r'_VAULT_TEXT_EXT\s*=\s*frozenset', src) is not None,
          '— three globs is how three doors came to disagree')
    exts = re.search(r'_VAULT_TEXT_EXT\s*=\s*frozenset\(\{([^}]*)\}', src)
    names = set(re.findall(r"'(\.[a-z0-9]+)'", exts.group(1))) if exts else set()
    check('...and markdown and pages are both on it',
          {'.md', '.html'} <= names, sorted(names))
    check('...and .svg is not — it is markup that can carry script',
          '.svg' not in names, sorted(names))
    check('the row builder decides isBinary from that one list',
          '_VAULT_TEXT_EXT' in section(src, 'def _vault_entry', '\ndef '),
          '— a second copy of the set is a second thing to go stale')

    listing = py_section("if path == '/vault/list'", "if path == '/vault/note'")
    check('the listing is built by the shared row builder',
          listing.count('_vault_entry(') >= 2,
          '— fs and oci both list, and both have to agree')
    check('no door lists the Library by globbing markdown',
          "rglob('*.md')" not in listing, '— this glob IS the ticket')
    search = py_section("if path == '/vault/search'", '# ---------- Graph')
    check('search reads the same list of openable types',
          '_VAULT_TEXT_EXT' in search, '— or it drifts wider than the listing again')

    raw_door = py_section("if path == '/vault/file'", '# ---------- Write/Append')
    check('there is a raw door at all', bool(raw_door),
          "— \"we can't show this\" needs a button beside it")
    check('...guarded by the same traversal check as every other path',
          '_vault_resolve(' in raw_door, raw_door[:200])
    check('...that never lets a filed page run at the office origin',
          '_vault_inline_ok(' in raw_door and 'nosniff' in raw_door, raw_door[:200])
    note = py_section("if path == '/vault/note' and method == 'GET'",
                      '# ---------- Raw file')
    check('the editor door catches the decode instead of dumping it',
          'except UnicodeDecodeError' in note, '— the boss got the codec error')

    # ── the view routes, and keeps the bridge's own truth ────────────────
    branch = section(ui, 'if (fileMeta?.isBinary)', 'setBusy(true)')
    check('the ai.cafreso.com notice is gated on being in the bridge',
          re.search(r'if\s*\(_bridge\)\s*\{[\s\S]{0,400}?ai\.cafreso\.com', branch) is not None,
          '— on a server backend that file is on the boss\'s own disk')
    check('a server-backend file opens a panel instead',
          'binary: true' in branch, branch[:300])
    check('the panel exists and offers the raw door',
          "'/vault/file?path='" in ui and 'download={name}' in ui,
          '— §7: a way forward, not just a nicer refusal')
    check('the panel is rendered on both the phone and the desktop',
          ui.count('<FiledFilePanel') == 2, ui.count('<FiledFilePanel'))
    check('...and both panes actually reach it',
          ui.count('openNote.binary ? (') == 2,
          [ui.count('openNote.binary ? ('),
           '— a component nothing branches to is a component nobody sees'])
    check('no Save button over a file the editor never opened',
          ui.count('!openNote.binary') == 4,
          [ui.count('!openNote.binary'), '— Preview + Save, twice each'])

    check('the tree says which rows are not notes',
          'binExt' in core and 'tree-tag' in core,
          '— slides.pptx and a note called slides were one glyph apart')
    check('...and carries the flag from the listing to get there',
          'isBinary: !!f.isBinary' in core, '— buildTree dropped it')


def main():
    print('the library shows what it filed')
    tmp = tempfile.mkdtemp(prefix='library136-')
    vault = Path(tmp) / 'Library'
    (vault / 'Research').mkdir(parents=True)
    (vault / 'Research' / 'vendor-notes.md').write_text(
        '# Vendor notes\n\nFreight is the largest single line item.\n', encoding='utf-8')
    (vault / '.obsidian').mkdir()
    (vault / '.obsidian' / 'workspace.json').write_text('{}', encoding='utf-8')

    base, kill = boot(vault, Path(tmp) / 'state')
    if not base:
        check('the office starts', False, '— serve.py never answered')
    else:
        try:
            live_checks(base, vault)
        finally:
            kill()
    source_checks()

    print()
    if FAILS:
        print('%d FAILED: %s' % (len(FAILS), FAILS))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
