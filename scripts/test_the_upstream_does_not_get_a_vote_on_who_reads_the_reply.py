#!/usr/bin/env python3
"""Who may read this office's answers is the office's decision.

`## 333.` withheld `Access-Control-Allow-Origin` from the proxy prefixes so a
page the boss merely visited could not read the roster of models installed on
their machine. The proxy loop then handed that decision straight back to the
upstream: it relayed every response header that was not hop-by-hop, and LM
Studio and Ollama both answer a browser permissively.

Measured against a stub that echoes Origin the way they do, a real serve.py
returned, for `GET /lmstudio/models` from `Origin: https://evil.example`:

    Access-Control-Allow-Origin: https://evil.example
    Access-Control-Allow-Credentials: true

Not merely readable — readable with the office's own cookies attached, which
is the exact thing `_cors`'s '*' fallback was written to prevent.

Three loops in serve.py relay upstream headers (Brave search, the local model
proxy, the Hermes gateway). This drives the real predicate all three ask, and
pins that they ask it rather than re-typing the condition — a fourth proxy
added later inherits the answer.
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
fails = []


def ok(label, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + label
          + (('  — ' + str(detail)) if detail and not cond else ''))
    if not cond:
        fails.append(label)


# ── the real predicate, out of the shipped module ────────────────────────
probe = subprocess.run(
    [sys.executable, '-c',
     'import serve, json;'
     ' names = ["Access-Control-Allow-Origin",'
     '          "access-control-allow-credentials",'
     '          "Access-Control-Expose-Headers",'
     '          "ACCESS-CONTROL-MAX-AGE",'
     '          "Content-Type", "Content-Length", "Connection",'
     '          "Content-Encoding", "X-Request-Id", "Retry-After",'
     '          "WWW-Authenticate", "Cache-Control"];'
     ' print(json.dumps({n: serve._relayable(n) for n in names}))'],
    cwd=str(ROOT), capture_output=True, text=True)
ok('serve.py exposes a relay predicate', probe.returncode == 0,
   probe.stderr[-400:])
if probe.returncode != 0:
    print('\nFAILED: cannot continue without the predicate')
    sys.exit(1)

import json
verdict = json.loads(probe.stdout.strip().splitlines()[-1])

# ── A. the upstream gets no vote on CORS, in any casing ──────────────────
#
# Casing matters: http.client hands headers back as the server wrote them,
# and the loops lower-case before asking. A case-sensitive test would pass
# while the shipped code let 'ACCESS-CONTROL-ALLOW-ORIGIN' through.
for name in ('Access-Control-Allow-Origin',
             'access-control-allow-credentials',
             'Access-Control-Expose-Headers',
             'ACCESS-CONTROL-MAX-AGE'):
    ok(f'{name} from the upstream is dropped', verdict[name] is False,
       'relayed — the upstream decides who reads the office\'s reply')

# ── B. the headers that make a proxy useful still get through ────────────
#
# Over-dropping would be its own bug: the office would relay a body nobody
# could interpret, or swallow the reason for a 429.
for name in ('Content-Type', 'X-Request-Id', 'Retry-After',
             'WWW-Authenticate', 'Cache-Control'):
    ok(f'{name} is still relayed', verdict[name] is True,
       'a useful upstream header was swallowed')

# ── C. the framing headers stay dropped, as before ───────────────────────
for name in ('Content-Length', 'Connection', 'Content-Encoding'):
    ok(f'{name} is still dropped', verdict[name] is False,
       'the loops re-frame the body; relaying this corrupts it')

# ── D. every relay loop ASKS, rather than re-typing the condition ────────
#
# This is the half that survives the next proxy being added. Comments are
# stripped first: a `#` inside a string literal makes a naive splitter eat
# the code under test.
import io
import tokenize

src = (ROOT / 'serve.py').read_text()
out, last = [], (1, 0)
for tok in tokenize.generate_tokens(io.StringIO(src).readline):
    if tok.type == tokenize.COMMENT:
        continue
    out.append(tok)
stripped = tokenize.untokenize(out)

loops = re.findall(r'for k, v in resp\.getheaders\(\):\s*\n\s*if ([^\n]+)',
                   stripped)
ok('serve.py still has its header-relay loops', len(loops) >= 3,
   f'found {len(loops)} — expected the Brave, model-proxy and gateway loops')
for i, cond in enumerate(loops):
    ok(f'relay loop {i + 1} asks _relayable', '_relayable(' in cond,
       cond.strip() + ' — a re-typed condition is the drift this removes')
    ok(f'relay loop {i + 1} does not re-type the hop list',
       'HOP_HEADERS' not in cond, cond.strip())

print()
if fails:
    print('FAILED %d check(s): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('the upstream does not get a vote on who reads the reply: all passed')
