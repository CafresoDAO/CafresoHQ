#!/usr/bin/env python3
"""The access log must not record anything that opens a door.

`## 315.` found the office's own API key going to stderr on every PTY
handshake, because `_api_key_ok` accepts it as `?k=…` on a WebSocket URL (the
browser API cannot set a header there) and `log_message` writes the query
string verbatim. It added `_LOG_SECRET_RE` and redacted `k|key|token|api_key`.

It missed `nonce`, which does not read like a credential and is one. `## 323.`
measured a rebound page trading that value for `101 Switching Protocols` on
/terminal/pty — a shell. Any handshake that fails BEFORE the upgrade (a CLI
that is not installed, a `cwd` that does not exist) is logged by this same
method, so the operator's redirected log file held the key to the terminal.

The list is the point, not any one entry: this test drives the real compiled
pattern over every parameter the app actually puts a credential in, so a new
one has to be added here to be forgotten there.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
fails = []


def ok(label, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + label
          + (('  — ' + str(detail)) if detail and not cond else ''))
    if not cond:
        fails.append(label)


# Lift the real pattern out of serve.py rather than restating it here — a copy
# would pass while the shipped one rotted.
src = (ROOT / 'serve.py').read_text()
m = re.search(r'_LOG_SECRET_RE = _re\.compile\(\s*(r\'[^\']+\')', src)
ok('the access log compiles a redaction pattern', m is not None,
   'no _LOG_SECRET_RE found in serve.py')
if not m:
    print('\nFAILED: cannot continue without the pattern')
    sys.exit(1)

PATTERN = re.compile(eval(m.group(1)), re.IGNORECASE)
SECRET = 'aaaaaaaabbbbbbbbccccccccdddddddd'

# Every query parameter this app is known to carry a credential in.
for param in ('k', 'key', 'token', 'api_key', 'nonce'):
    line = f'GET /terminal/pty?cli=hermes&{param}={SECRET} HTTP/1.1'
    out = PATTERN.sub(r'\1<redacted>', line)
    ok(f'?{param}= is redacted', SECRET not in out, out)
    ok(f'…and the request stays recognisable with {param} named',
       f'{param}=<redacted>' in out.lower(), out)

# The real shape that leaked: a handshake that fails before the 101, so the
# whole URL reaches log_message. Order and casing must not rescue it.
real = ('GET /terminal/pty?cli=hermes&cwd=/nonexistent-dir-xyz'
        f'&cols=80&rows=24&NONCE={SECRET} HTTP/1.1')
ok('a failed PTY handshake logs no nonce, whatever the case',
   SECRET not in PATTERN.sub(r'\1<redacted>', real),
   PATTERN.sub(r'\1<redacted>', real))

# ...and the parts that are not secret survive, or the log stops being useful.
scrubbed = PATTERN.sub(r'\1<redacted>', real)
ok('the useful parts of the line survive redaction',
   '/terminal/pty' in scrubbed and 'cli=hermes' in scrubbed
   and 'cwd=/nonexistent-dir-xyz' in scrubbed, scrubbed)

# A value that is not a credential must not be swallowed — over-redaction
# would hide the very fields that make a log worth keeping.
plain = 'GET /fs/file?path=/Users/x/Documents/notes.md HTTP/1.1'
ok('a non-secret parameter is left alone',
   PATTERN.sub(r'\1<redacted>', plain) == plain,
   PATTERN.sub(r'\1<redacted>', plain))

print()
if fails:
    print('FAILED %d check(s): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('the access log keeps no key to the terminal: all checks passed')
