#!/usr/bin/env python3
"""A mistyped domain reached the boss as a C library errno.

Measured live (#145) on a fresh office. Asked a coworker to read a page and
mistyped the host by one letter. Under the reply:

    ⚠ Couldn't read cafreshq.com/team
    Couldn't read that page — fetch failed: URLError: <urlopen error [Errno 8]
    nodename nor servname provided, or not known>

Driven through the same route by hand, a refused port answered "[Errno 61]
Connection refused" and an expired certificate answered "certificate verify
failed: certificate has expired (_ssl.c:1082)". §6 bans that vocabulary
anywhere the boss can see it, and §7 asks each failure for one honest
sentence carrying a way forward. None of the three said what to do, and the
one that had an obvious answer -- look at what you typed -- said it least.

The reason nobody had looked is written into the tool that reads the value
aloud. BROWSER_FETCH's comment says "`j.error` is authored by our own
serve.py and already reads as English", which was true of every branch except
the catch-all, where the raw exception was formatted straight into the field.
A true-sounding comment over one false branch.

`_page_fetch_cause` now owns the clause. What is checked here is that the
boss's sentence is free of machine vocabulary AND still says something --
absence alone is satisfied by "something went wrong", which §7 calls a worse
answer than the shrapnel it replaces. The raw text must survive too: a
self-hosted install has a second reader, and dropping stderr entirely trades
one blind user for another.

Run: python3 scripts/test_a_page_that_would_not_load.py
"""
import http.server
import json
import re
import socket
import ssl
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# Every one of these is a real exception, raised by the real thing failing --
# not a string composed here to match the table. A table tested against its
# own fixtures proves only that it was copied correctly.
def real_exceptions():
    out = {}

    def grab(key, fn):
        try:
            fn()
        except Exception as e:                                # noqa: BLE001
            out[key] = e
        else:
            out[key] = None

    grab('dns', lambda: urllib.request.urlopen(
        'http://cafreshq-no-such-host-9d2f.invalid/team', timeout=5))
    # A port nothing is listening on, found by binding and releasing one.
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    dead = s.getsockname()[1]
    s.close()
    grab('refused', lambda: urllib.request.urlopen(
        'http://127.0.0.1:%d/x' % dead, timeout=5))
    # A real TLS handshake against a plain-HTTP listener: "wrong version
    # number", which is the certificate family without needing the network.
    class Quiet(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass                      # a TLS ClientHello is not a log line

    srv = http.server.HTTPServer(('127.0.0.1', 0), Quiet)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    grab('tls', lambda: urllib.request.urlopen(
        'https://127.0.0.1:%d/' % srv.server_address[1], timeout=5,
        context=ssl.create_default_context()))
    srv.server_close()
    # A socket that accepts and then says nothing, so the read times out.
    # The accepted connection is HELD: letting it fall out of scope closes
    # it, and the first draft of this fixture got a connection reset that
    # the table classified as a network fault. The suite failed and was
    # right to -- the fixture was wrong, not the row.
    q = socket.socket()
    q.bind(('127.0.0.1', 0))
    q.listen(1)
    held = []
    threading.Thread(target=lambda: held.append(q.accept()), daemon=True).start()
    grab('timeout', lambda: urllib.request.urlopen(
        'http://127.0.0.1:%d/' % q.getsockname()[1], timeout=1))
    for conn, _addr in held:
        conn.close()
    q.close()
    out['unknown'] = ValueError('something nobody has classified yet')
    return out


# §6's never-say list, narrowed to what a failed fetch actually leaks, plus
# the shapes that are machine vocabulary in any table: an errno, a C source
# location, an exception class name, angle-bracketed repr.
SHRAPNEL = re.compile(
    r'errno|urlerror|sslerror|oserror|timeouterror|valueerror|_ssl\.c|'
    r'urlopen|getaddrinfo|traceback|exception|\bstderr\b|\bENO[A-Z]+\b|'
    r'<[^>]+>|\bfetch failed\b', re.I)


def main():
    print('a page that would not load — the boss gets a sentence, not an errno')
    import serve                                              # noqa: PLC0415

    exc = real_exceptions()
    missing = [k for k, v in exc.items() if v is None]
    if missing:
        # Never silently: a network that refuses to fail is not a pass.
        print('  SKIP  these did not fail as expected here: ' + ', '.join(missing))

    print('1. nothing the boss cannot read')
    said = {}
    for key, e in exc.items():
        if e is None:
            continue
        said[key] = serve._page_fetch_cause(e)
        hit = SHRAPNEL.search(said[key])
        check(f'{key}: no machine vocabulary survives',
              hit is None, f'{said[key]!r} says {hit.group(0) if hit else ""!r}')
        check(f'{key}: one sentence, not a transcript',
              '\n' not in said[key] and len(said[key]) <= 120, repr(said[key]))
        # The caller writes "Couldn't read that page — " and joins. A clause
        # that spends a second em-dash reads as two thoughts, and it was the
        # first draft's mistake.
        check(f'{key}: reads on from the dash the caller already wrote',
              '—' not in said[key] and said[key][:1].islower(), repr(said[key]))

    print('2. …and each one still says something')
    # The absence checks above are all satisfied by "something went wrong".
    # SNAG_CAUSES' own comment calls a vague honest answer better than a
    # confident wrong one — but only the classified ones get to be vague.
    if 'dns' in said:
        check('a mistyped host points at the spelling, not at the network',
              'spelling' in said['dns'],
              f"{said['dns']!r} — the boss's own typo is the likely cause here "
              'and it is the only case where that is true')
    if 'refused' in said:
        check('a refused port says nothing answered',
              'nothing answered' in said['refused'], repr(said['refused']))
    if 'tls' in said:
        check('a bad certificate says the office chose not to trust it',
              'certificate' in said['tls'] and 'trust' in said['tls'],
              f"{said['tls']!r} — a refusal the office MADE, said as a choice")
    if 'timeout' in said:
        check('a hung page says the office stopped waiting',
              'too long' in said['timeout'], repr(said['timeout']))
    check('anything unclassified falls through to a vague honest one',
          said.get('unknown') == 'the office could not reach it',
          f"{said.get('unknown')!r} — the fallthrough must not guess")
    # Each classified family must be distinguishable, or the table is
    # decoration: four rows that all answer the same sentence would pass
    # every check above.
    distinct = {v for k, v in said.items() if k != 'unknown'}
    check('the classified causes do not collapse into one another',
          len(distinct) == len([k for k in said if k != 'unknown']),
          f'{sorted(distinct)} — a table that answers the same clause to '
          'every input is a fallthrough wearing a table')

    print('3. the route, and the reader who still needs the raw text')
    handler = ROOT / 'serve.py'
    src = handler.read_text(encoding='utf-8')
    i = src.index('def _browser_fetch(self):')
    body = src[i:src.index('\n    def ', i + 1)]
    catch = body[body.index('except Exception as e:'):]
    check('the catch-all hands the boss the sentence',
          '_page_fetch_cause(e)' in catch,
          'serve.py: BROWSER_FETCH reads `error` aloud verbatim')
    check('...and never the formatted exception',
          not re.search(r"'error':\s*f?['\"][^'\"]*\{?type\(e\)", catch),
          repr(catch[:200]))
    check('...while the raw text still reaches whoever is debugging',
          "'detail'" in catch and 'type(e).__name__' in catch,
          'serve.py: a self-hosted install has a second reader — dropping the '
          'stderr entirely trades one blind user for another')

    # The comment that kept this branch invisible for as long as it did.
    rt = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
    j = rt.index('browser_fetch: {')
    tool = rt[j:rt.index('browser_screenshot: {', j)]
    check('the tool still hands j.error straight to the boss',
          'return fail(j.error);' in tool,
          'hq-runtime.jsx: if this ever stops being true the sentence above '
          'stops being the one the boss reads, and this suite guards nothing')
    # Asserted positively. Banning the old claim would fail on the comment's
    # own record of having made it — the mistake #143 made twice.
    check('...and its comment records which branch that claim was false for',
          '_page_fetch_cause' in tool,
          'hq-runtime.jsx: "already reads as English" was true of every branch '
          'but the catch-all, and the comment saying so is why nobody looked')

    print()
    if FAILS:
        print(f'page fetch: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('page fetch: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
