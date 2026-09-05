#!/usr/bin/env python3
"""A tester who redirects the log is never told which URL to open.

The beta-readiness audit found the failure end to end. In local mode
serve.py auto-provisions a localhost TLS cert, and Start-CafresoHQ.sh
actively tells the tester to install mkcert — so on a machine that took
that advice the server comes up on **https**, while the README hands out
an http:// address. The one line that would settle it is the startup
banner, which prints the live scheme and port:

    CafresoHQ -> https://localhost:8787/hq.html

That line was a bare print(). Python block-buffers stdout in 8 KiB
chunks whenever it is not a tty, and every launch a tester actually
performs is exactly that: `sh Start-CafresoHQ.sh > hq.log`, nohup,
Electron capturing the pipe. The banner therefore sat in a buffer that
an idle server never fills, and the audit confirmed it absent from a
cold-start log. The request log is written by BaseHTTPRequestHandler to
*stderr*, so the log read back that way showed the traffic and not the
address — which reads as "the server is running and I still can't find
it".

The fix is one line at the top of __main__ rather than flush=True on
each print: stdout is reconfigured to line-buffering for the whole run,
so the banner, the TLS line, the bind warning, the route table and every
print written later are all covered by construction. A per-print
flush is a rule someone has to remember; a stream setting is not.

The same "the human is told nothing" shape has a second face here.
mkcert -install can raise an admin-password prompt (a macOS keychain
dialog, sudo on Linux) with the server producing no output of its own
and a 60s timeout — so it looks like a hang. So the step is announced
before it is taken.

This test starts a REAL server, on a free ephemeral port, with stdout
redirected to a FILE, and reads the file back while the process is still
running. Grepping the source for flush=True would pass on code that
still never reaches the reader.

Run: python3 scripts/test_the_startup_banner_reaches_a_redirected_log.py
"""
import ast
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
SERVE = ROOT / 'serve.py'
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


def health(base):
    try:
        with urllib.request.urlopen(base + '/health', timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:                                    # noqa: BLE001
        return str(e)


def cold_start_log():
    """Start serve.py with stdout redirected to a file; return (text, port).

    stdout goes to a real file rather than a pipe because that is the
    launch under test, and because a pipe read back with .communicate()
    would only be readable after the process exits — at which point the
    buffer has been flushed and the bug is invisible. The file is read
    while the server is still serving.
    """
    port = free_port()
    base = 'http://127.0.0.1:%d' % port
    with tempfile.TemporaryDirectory() as state:
        out = Path(state) / 'stdout.log'
        # TLS_AUTO=0 keeps this deterministic on machines that do and do
        # not have mkcert; the banner's job is to name whichever scheme
        # the server actually chose, and here that is http.
        env = dict(os.environ, PORT=str(port), CAFRESOHQ_HQ_STATE_DIR=state,
                   CAFRESOHQ_TLS_AUTO='0')
        with open(out, 'wb') as fh:
            proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=ROOT,
                                    env=env, stdout=fh,
                                    stderr=subprocess.DEVNULL)
        try:
            up = False
            for _ in range(80):                                # ≤20s
                if proc.poll() is not None:
                    return '', port, 'server exited early (rc=%s)' % proc.returncode
                if health(base) == 200:
                    up = True
                    break
                time.sleep(0.25)
            if not up:
                return '', port, 'no /health after 20s'
            # The server is serving; the banner was printed strictly
            # before serve_forever(). Give the write a moment, then read
            # the log back with the process still alive — the whole
            # point is that a running server's log is legible.
            for _ in range(20):                                # ≤5s
                text = out.read_text(encoding='utf-8', errors='replace')
                if text.strip():
                    return text, port, None
                time.sleep(0.25)
            return out.read_text(encoding='utf-8', errors='replace'), port, None
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:                                  # noqa: BLE001
                proc.kill()


def main():
    print('the startup banner reaches a redirected log')

    text, port, err = cold_start_log()
    if err:
        check('a cold start comes up at all', False, err)
        return 1

    url = 'http://localhost:%d/hq.html' % port
    check('a redirected cold-start log is not empty', bool(text.strip()),
          'stdout was block-buffered and an idle server never fills 8 KiB')
    check('...and it names the address to open', url in text,
          'log was: %r' % text[:400])
    check('...naming the scheme the server actually serves',
          ('CafresoHQ -> http://localhost:%d' % port) in text,
          'a banner that hardcoded a scheme would send a tester with '
          'mkcert installed to an http:// address on an HTTPS server')
    # The banner is the first thing a human needs, so it must not be
    # gated behind the rest of the startup chatter arriving.
    check('...on one of the first lines', any(
        url in ln for ln in text.splitlines()[:6]), text.splitlines()[:6])
    # Everything else printed on the startup path shares the fix, which
    # is the point of doing it at the stream instead of per print().
    check('...along with the rest of the startup report',
          '/approvals/external' in text and '/cafresohq/stream' in text,
          'the last startup print is the proof the whole path is '
          'line-buffered, not just the one line someone remembered')

    # ── the fix is a stream setting, not a per-print habit ──────────────
    # Parsed, not grepped: this file's own prose contains every phrase a
    # grep would look for, and serve.py embeds JS/CSS in string literals
    # that a text search would happily match inside.
    tree = ast.parse(SERVE.read_text(encoding='utf-8'))
    main_block = None
    for node in tree.body:
        if (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name)
                and node.test.left.id == '__name__'):
            main_block = node
    check('the startup block is there to check', main_block is not None)

    reconf = [n for n in ast.walk(main_block) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Attribute)
              and n.func.attr == 'reconfigure'
              and any(k.arg == 'line_buffering' and k.value.value is True
                      for k in n.keywords)] if main_block else []
    check('stdout is line-buffered for the whole run', reconf,
          'without it every startup print is one someone has to remember '
          'to flush, and the next one added will not be')

    if main_block and reconf:
        first_print = min(
            (n.lineno for n in ast.walk(main_block) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == 'print'),
            default=10 ** 9)
        check('...before anything is printed',
              reconf[0].lineno < first_print,
              'a line-buffering switch after the first print leaves that '
              'print in the old buffer')

    # ── the mkcert step announces itself before it can block ───────────
    tls = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                and n.name == '_ensure_local_tls'), None)
    check('the TLS helper is there to check', tls is not None)
    if tls:
        install = [n for n in ast.walk(tls) if isinstance(n, ast.Call)
                   and any(isinstance(a, ast.Constant) and a.value == '-install'
                           for a in ast.walk(n))]
        check('mkcert -install still runs', install,
              'this ticket does not change WHETHER the CA is installed')
        said = [n for n in ast.walk(tls) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == 'write'
                and any(isinstance(a, ast.Constant)
                        and isinstance(a.value, str)
                        and 'password' in a.value.lower()
                        for a in ast.walk(n))]
        check('...and says so before it can raise a password prompt',
              said and install and said[0].lineno < install[0].lineno,
              'an unannounced -install with captured output looks like a '
              'hang for up to its 60s timeout')
        flushed = [n for n in ast.walk(tls) if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute)
                   and n.func.attr == 'flush']
        check('...where the reader can actually see it',
              flushed and install and
              any(f.lineno < install[0].lineno for f in flushed),
              'a warning that arrives after the thing it warns about is '
              'not a warning')

    print()
    if FAILS:
        print('FAILED: %d — %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
