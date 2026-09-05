#!/usr/bin/env python3
"""The one page a brand-new tester sees first was an empty reply.

`#295`/`#296` and `test_a_fresh_clone_is_told_to_run_npm_install.py` built the
sentence a fresh clone needs — "run `npm install` then `npm run build` in
<cwd>" — and pinned its wording. Nobody checked that the sentence ever reaches
a browser. It did not.

`_serve_hq_html` passes that whole sentence as `send_error`'s SECOND argument,
which is the HTTP **reason phrase** — the tail of the status line. Python's
`BaseHTTPRequestHandler.send_response_only` builds that line with

    ("%s %d %s\r\n" % (self.protocol_version, code, message)).encode('latin-1')

and the sentence contains an em dash (U+2014). `send_error` therefore raises
`UnicodeEncodeError` from inside itself, after the handler has committed to
replying and before one byte is written. The socket closes with no response.

Measured on a real `git archive HEAD | tar -x` clone with no `dist-ui/`:

    $ curl -sv http://127.0.0.1:8931/hq.html
    * Empty reply from server

    UnicodeEncodeError: 'latin-1' codec can't encode character '—'
      in position 185: ordinal not in range(256)

The browser shows `ERR_EMPTY_RESPONSE`, `README.md`'s own promise that
"hq.html is 500 until dist-ui/ exists" is false, and the tester learns
nothing — on the single most likely first-run mistake there is.

The em dash is only the trigger that fires every time. The same call
interpolates the exception text and `os.getcwd()`, both of which carry the
user's own home directory name, so the crash outlives any de-punctuation:
a tester whose account is named in Cyrillic, Greek, Hebrew or any CJK script
gets the same dropped connection from the same line.

Fix (`## 396.`): the reason phrase is the bare ASCII 'HQ UI not built' and the
advice moves to `explain`, which `send_error` HTML-escapes into the body and
encodes UTF-8 — so it carries any text there is. The two siblings in
`pty_server.py` (the WS origin refusal, which interpolates a caller-supplied
`Origin`, and the nonce refusal) are the same shape and move the same way.

Round 1 is structural: every `send_error` reason phrase in the server files is
a plain latin-1-encodable constant, and the hq.html door really does carry its
advice in the third argument.

Round 2 is the real thing: a serve.py booted from a directory with no
`dist-ui/` — and deliberately named with a non-latin-1 character, so the
dynamic half of the bug is exercised alongside the em dash — answered over
raw `http.client`, so a dropped connection is distinguishable from a 500
rather than being smoothed into one by urllib.

Run: python3 scripts/test_the_page_that_teaches_a_new_tester_the_two_commands_can_be_read.py
"""
import ast
import http.client
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER_FILES = ['serve.py', 'pty_server.py', 'fs_routes.py', 'exporters.py']
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def send_error_calls(path):
    """(lineno, call) for every `self.send_error(...)` in a server file."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    return [(n.lineno, n) for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == 'send_error']


def structural():
    print('=== the reason phrase is the status line, and the status line is latin-1 ===')
    for fn in SERVER_FILES:
        p = ROOT / fn
        if not p.exists():
            continue
        for lineno, call in send_error_calls(p):
            if len(call.args) < 2:
                continue                       # bare send_error(404) — nothing to encode
            arg = call.args[1]
            ok_kind = isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            check(f'{fn}:{lineno} reason phrase is a plain string constant',
                  ok_kind,
                  'an f-string or a % here can smuggle a runtime character '
                  'into the status line, where it kills the response')
            if not ok_kind:
                continue
            try:
                arg.value.encode('latin-1')
                enc = True
            except UnicodeEncodeError:
                enc = False
            check(f'{fn}:{lineno} reason phrase survives latin-1',
                  enc,
                  f'{arg.value!r} raises UnicodeEncodeError inside send_error, '
                  'so the caller gets no response at all')

    # The hq.html door specifically: the advice has to be in `explain`.
    hq = [(ln, c) for ln, c in send_error_calls(ROOT / 'serve.py')
          if any(isinstance(a, ast.Constant) and isinstance(a.value, str)
                 and 'HQ UI not built' in a.value for a in c.args)]
    check('serve.py still has an "HQ UI not built" door', len(hq) == 1,
          f'found {len(hq)}')
    if len(hq) == 1:
        _, call = hq[0]
        check('the fresh-clone 500 passes an `explain` argument',
              len(call.args) >= 3,
              'with only a reason phrase the advice rides in the status line')
        if len(call.args) >= 3:
            src = ast.dump(call.args[2])
            check('the advice — both commands — lives in `explain`',
                  'npm install' in src and 'npm run build' in src,
                  'explain is the argument the browser renders')


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def unbuilt_tree(tmp):
    """A checkout with everything serve.py imports and NO dist-ui/.

    Symlinked rather than copied so this stays cheap; `os.getcwd()` is the
    temp directory, which is what serve.py joins 'dist-ui' onto.
    """
    skip = {'dist-ui', 'node_modules', 'hq-state', '.git'}
    for entry in os.listdir(ROOT):
        if entry in skip:
            continue
        os.symlink(ROOT / entry, os.path.join(tmp, entry))


def raw_get(port, path):
    """Return (status, body) — or ('DROPPED', why) when the server answered
    with nothing, which is exactly what the bug looked like. http.client,
    not urllib, because urllib turns a RemoteDisconnected into a generic
    URLError and loses the distinction this test exists to make."""
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    try:
        conn.request('GET', path)
        r = conn.getresponse()
        return r.status, r.read().decode('utf-8', 'replace')
    except Exception as e:
        return 'DROPPED', f'{type(e).__name__}: {e}'
    finally:
        conn.close()


def live():
    print()
    print('=== a fresh clone with no dist-ui/, answered for real ===')
    # A non-latin-1 name on the working directory: it lands in os.getcwd()
    # AND in the FileNotFoundError text, so this one boot covers both the
    # em dash and the user-named-directory half of the same bug.
    tmp = tempfile.mkdtemp(prefix='hq-firstrun-事務所-')
    state = tempfile.mkdtemp(prefix='hq-firstrun-state-')
    proc = None
    try:
        unbuilt_tree(tmp)
        check('the test tree really has no built bundle',
              not os.path.exists(os.path.join(tmp, 'dist-ui')))
        port = free_port()
        env = dict(os.environ, PORT=str(port),
                   CAFRESOHQ_HQ_STATE_DIR=state,
                   CAFRESOHQ_ALLOWED_DIRS=state)
        proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=tmp, env=env,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.STDOUT)
        up = False
        for _ in range(80):
            if raw_get(port, '/health')[0] == 200:
                up = True
                break
            time.sleep(0.25)
        check('the office boots from a directory with no bundle', up,
              'the server never answered /health')
        if not up:
            return

        status, body = raw_get(port, '/hq.html')
        check('/hq.html answers at all', status != 'DROPPED',
              f'{body} — this is the bug: the response died inside '
              'send_error and the browser shows ERR_EMPTY_RESPONSE')
        check('/hq.html answers 500', status == 500, status)
        if status == 'DROPPED':
            return
        check('the reply names `npm install`', 'npm install' in body,
              repr(body[-500:]))
        check('the reply names `npm run build`', 'npm run build' in body,
              repr(body[-500:]))
        check('it names install BEFORE build',
              body.find('npm install') < body.find('npm run build'))
        check('the reply names the directory to run them in',
              '事務所' in body,
              'the cwd is how a tester knows WHERE the two commands go — '
              'and it is the half that carries the user\'s own name')
        check('the status line is intact', status == 500)

        # And the ordinary route still works from the same unbuilt tree, so
        # this is a page-shaped failure and not a dead office.
        st, _ = raw_get(port, '/health')
        check('/health is unaffected', st == 200, st)
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(state, ignore_errors=True)


def main():
    print('first run: the page that teaches the two commands can be read')
    structural()
    live()
    print()
    if FAILS:
        print(f'first run: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('first run: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
