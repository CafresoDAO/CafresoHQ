#!/usr/bin/env python3
"""Five export doors filed rendered deliverables where the Library can't show them.

#140 taught the write doors — PUT /vault/note and the rename destination —
to refuse a dotted path, because every backend's listing skips dotted parts
and "Saved" over an unlistable file is a lie. But the EXPORT_PPTX /
EXPORT_DOCX / EXPORT_PDF tools and the image/video generators do not go
through those doors: they resolve their target with
`exporters._vault_binary_path`, which mirrored `_vault_resolve`'s traversal
guard and never asked the hidden-part question. `[EXPORT_PPTX:
.decks/board.pptx]` rendered a real deck, filed it in the dark, and told
the coworker — and through it the boss — "Saved PowerPoint → .decks/…".
Reproduced live before the fix: the resolver accepted the dotted path and
created `.decks/` on disk even though the missing renderer stopped that
particular box one step later.

The invariant this suite pins: every door that writes a deliverable into
the vault asks the same hidden-part question, refuses with the same
sentence as the write doors, refuses BEFORE anything touches disk (no
`.decks/` left behind), and still refuses `..` as the traversal it is —
"drop the leading dot" over a traversal would send the boss to rename a
file that was never the problem.

The refusal must also come BEFORE the renderer/provider checks: a box
without python-pptx used to answer a dotted path with "install
python-pptx" — the office asking the boss to install software so it could
file a deliverable into the dark. That order makes this suite independent
of which renderers happen to be installed.

Run: python3 scripts/test_a_deliverable_is_never_filed_in_the_dark.py
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
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
EXPORTERS_RAW = (ROOT / 'exporters.py').read_text(encoding='utf-8')
CLIENT_RAW = (ROOT / 'claude-client.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# ── the resolver, on its own ──────────────────────────────────────────────
def unit_checks():
    print('=== the one resolver behind all five doors ===')
    import exporters
    tmp = Path(tempfile.mkdtemp(prefix='export141-unit-'))
    exporters._vault_root = lambda: str(tmp)
    # A replica of serve.py's _vault_hidden_part, because importing serve
    # imports a web server. The REAL function and the REAL injection are
    # exercised by the live-boot section below; this replica only lets the
    # resolver run standalone.
    def hidden_part(rel):
        for part in str(rel or '').replace('\\', '/').split('/'):
            part = part.strip()
            if part in ('', '.', '..'):
                continue
            if part.startswith('.'):
                return part
        return None
    exporters._vault_hidden_part = hidden_part

    try:
        exporters._vault_binary_path(None, '.decks/board.pptx', ('.pptx',))
        check('a dotted path is refused — THE TICKET', False,
              'the resolver handed back a path no listing will ever show')
    except ValueError as e:
        check('a dotted path is refused — THE TICKET', True)
        check('...with the folder named and the way forward',
              'never lists anything under ".decks"' in str(e)
              and 'leading dot' in str(e), e)
    check('...and nothing was created behind the refusal',
          not (tmp / '.decks').exists(),
          'the resolver used to mkdir the hidden folder before anyone '
          'checked whether the render could even happen')

    out = exporters._vault_binary_path(None, 'decks/board.pptx', ('.pptx',))
    # tmp.resolve(): the resolver resolves symlinks (macOS /var -> /private/var)
    # and mkdtemp hands back the unresolved spelling.
    check('a visible path still resolves under the vault',
          str(out).startswith(str(tmp.resolve())) and out.name == 'board.pptx', out)

    try:
        exporters._vault_binary_path(None, '../escape.pptx', ('.pptx',))
        check('`..` is still refused as a traversal', False, 'resolved!')
    except ValueError as e:
        check('`..` is still refused as a traversal',
              'escapes' in str(e) and 'hidden' not in str(e).lower(), e)

    try:
        exporters._vault_binary_path(None, '.decks/board.txt', ('.pptx',))
        check('a dotted path with a bad extension is refused', False, 'resolved!')
    except ValueError as e:
        check('a dotted path with a bad extension hears the HIDDEN refusal',
              'never lists' in str(e) and 'extension' not in str(e),
              f'{e} — "use .pptx" over a hidden path invites the boss to fix '
              'the extension and file into the dark on the second try')

    check('all five doors ride this one resolver',
          EXPORTERS_RAW.count('self._vault_binary_path(rel,') == 5,
          'a door that resolves its own path is a door that skipped the '
          'question — this count is how #141 happened to five doors at once')


# ── the client functions the tools call ───────────────────────────────────
def client_source_checks():
    print('=== the client raises what the server refuses ===')
    # The tool wrapper turns a throw into "That didn't work — <reason>" for
    # both the coworker and the boss; that only works if these five actually
    # throw on a non-2xx instead of returning the error body as a result.
    for fn in ('exportPptx', 'exportDocx', 'exportPdf',
               'generateImage', 'generateVideo'):
        m = re.search(r'async function %s\([^)]*\) \{[\s\S]*?\n\}' % fn,
                      CLIENT_RAW)
        check(f'{fn} throws the server sentence on a refusal',
              m is not None and 'throw new Error(j.error' in m.group(0),
              f'claude-client.jsx: {fn} — a swallowed refusal here becomes '
              'a success receipt one layer up')


# ── the five doors, live ──────────────────────────────────────────────────
def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def post(url, obj):
    req = urllib.request.Request(url, data=json.dumps(obj).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'},
                                 method='POST')
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


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode()


def boot(vault_root, state_dir, work_dir):
    port = free_port()
    env = dict(os.environ, PORT=str(port), CAFRESOHQ_VAULT=str(vault_root),
               CAFRESOHQ_HQ_STATE_DIR=str(state_dir),
               CAFRESOHQ_ALLOWED_DIRS=str(work_dir))
    for k in ('OCI_VAULT_NAMESPACE', 'OCI_VAULT_BUCKET', 'OCI_VAULT_PREFIX',
              'CAFRESOHQ_VAULT_BACKEND', 'CAFRESOHQ_OBSIDIAN_URL',
              'CAFRESOHQ_OBSIDIAN_KEY', 'OPENAI_API_KEY', 'FAL_KEY'):
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


DOTTED = [
    ('/export/pptx', {'path': '.decks/board.pptx', 'content': '# T'}, '.decks'),
    ('/export/docx', {'path': '.docs/brief.docx', 'content': '# T'}, '.docs'),
    ('/export/pdf', {'path': '.papers/plan.pdf', 'content': '# T'}, '.papers'),
    ('/generate/image', {'path': '.art/logo.png', 'prompt': 'a logo',
                         'provider': 'openai'}, '.art'),
    ('/generate/video', {'path': '.clips/intro.mp4', 'prompt': 'an intro',
                         'provider': 'fal'}, '.clips'),
]


def live_checks(base, vault):
    print('=== the five doors, live ===')
    for path, body, part in DOTTED:
        st, r = post(base + path, body)
        err = r.get('error', '')
        check(f'{path} refuses a dotted destination',
              st == 400 and f'never lists anything under "{part}"' in err
              and 'leading dot' in err,
              f'{st} {r} — before the fix this door accepted the path; on a '
              'box without the renderer it answered "install …" instead, '
              'asking the boss to install software to file into the dark')
        check(f'...and {part}/ was never created',
              not (vault / part).exists(),
              'the resolver used to mkdir the hidden folder before the '
              'renderer/provider was even checked')

    st, r = post(base + '/export/pptx',
                 {'path': 'decks/board.pptx', 'content': '# T'})
    err = r.get('error', '')
    check('a visible deck path is not caught in the net',
          'never lists' not in err,
          f'{st} {r} — the refusal is about dots, not about decks')
    if st == 200:
        # Renderer installed on this box: the success must be a listable file.
        stl, raw = get(base + '/vault/list')
        listed = {f['path'] for f in json.loads(raw)['files']} if stl == 200 else set()
        check('...and a rendered deck lands where the list can show it',
              r.get('path') in listed, (r, sorted(listed)))
    else:
        check('...without a renderer the answer is about the renderer',
              st == 503 and 'install' in err, (st, r))

    st, r = post(base + '/export/pptx',
                 {'path': '../escape.pptx', 'content': '# T'})
    err = r.get('error', '').lower()
    check('`..` at an export door is a traversal, not a hidden file',
          st == 400 and 'escapes' in err and 'hidden' not in err, (st, r))


def main():
    unit_checks()
    print()
    client_source_checks()
    print()

    tmp = Path(tempfile.mkdtemp(prefix='export141-'))
    vault, state, work = tmp / 'vault', tmp / 'hq', tmp / 'work'
    vault.mkdir()
    work.mkdir()
    base, kill = boot(vault, state, work)
    try:
        if not base:
            check('the office starts', False,
                  'serve.py never answered /missions/scheduled')
        else:
            live_checks(base, vault)
    finally:
        kill()

    print()
    if FAILS:
        print('%d FAILED: %s' % (len(FAILS), '; '.join(FAILS)))
        return 1
    print('a deliverable is never filed in the dark: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
