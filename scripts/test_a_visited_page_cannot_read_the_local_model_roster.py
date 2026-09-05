#!/usr/bin/env python3
"""A stranger's tab must not learn which models are on this machine.

`## 332.` closed the ROUTES fall-through against state changes: a page the
user merely visited could POST through to the local LM Studio / Ollama and
read the reply. It deliberately left the READ side alone, on the reasoning
that a proxied GET changes nothing.

It changes nothing and it still ANSWERS. `GET /lmstudio/models` hands back
the roster of models installed on the box, and both proxy prefixes were
absent from `_HOST_DATA_PREFIXES`, so `_cors` fell through to `ACAO: '*'` and
any origin could read the body. Measured against a real serve.py with a stub
model server: `Origin: https://evil.example` → 200, `Access-Control-Allow-
Origin: *`, full roster readable.

The list is the point, not either entry: this drives the real
`_HOST_DATA_PREFIXES` and pins that it is DERIVED from ROUTES rather than
naming its two keys, so a third passthrough is covered the day it is added.
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


# ── the real lists, lifted out of the shipped module ─────────────────────
#
# Imported rather than re-stated: a copy of the tuple would keep agreeing
# with itself long after serve.py had drifted.
proc = subprocess.run(
    [sys.executable, '-c',
     'import serve, json;'
     ' print(json.dumps({"host": list(serve._HOST_DATA_PREFIXES),'
     ' "routes": list(serve.ROUTES),'
     ' "key": list(serve._KEY_PROTECTED_PREFIXES)}))'],
    cwd=str(ROOT), capture_output=True, text=True)
ok('serve.py imports and exposes its prefix lists', proc.returncode == 0,
   proc.stderr[-400:])
if proc.returncode != 0:
    print('\nFAILED: cannot continue without the lists')
    sys.exit(1)

import json
lists = json.loads(proc.stdout.strip().splitlines()[-1])
HOST, ROUTES, KEY = lists['host'], lists['routes'], lists['key']

ok('the proxy table is not empty', len(ROUTES) >= 2, ROUTES)

# ── A. every passthrough prefix withholds ACAO from a stranger ───────────
for prefix in ROUTES:
    ok(f'{prefix} is host data',
       prefix in HOST,
       f'{prefix} missing from _HOST_DATA_PREFIXES -> ACAO:* to any origin')

# The paths the UI actually asks for must be covered by the prefix match
# that _cors performs (startswith on the path with the query stripped).
for path in ('/lmstudio/models', '/ollama/models',
             '/lmstudio/chat/completions'):
    ok(f'{path} is matched by the list',
       path.startswith(tuple(HOST)),
       'a real request path falls outside every host-data prefix')

# ── B. derived, not hand-typed ───────────────────────────────────────────
#
# The whole failure mode here was a hand-maintained list drifting behind the
# thing it was meant to shadow. Pin the derivation itself.
src = (ROOT / 'serve.py').read_text()
m = re.search(r'_HOST_DATA_PREFIXES = \((.*?)\n\n', src, re.S)
ok('_HOST_DATA_PREFIXES is defined in serve.py', m is not None)
if m:
    body = m.group(1)
    ok('it iterates ROUTES rather than re-typing its keys',
       'tuple(ROUTES)' in body, body[-300:])
    for prefix in ROUTES:
        ok(f'it does not hand-list {prefix}',
           f"'{prefix}'" not in body and f'"{prefix}"' not in body,
           'a literal here is the drift this fix removes')

# ── C. no collateral: public probes stay public ──────────────────────────
#
# Over-listing would be its own bug — /health is meant to answer anyone.
for path in ('/health', '/hq.html', '/dist-ui/app.js'):
    ok(f'{path} is still public to any origin',
       not path.startswith(tuple(HOST)),
       'a public probe was swept into the host-data list')

# ── D. the state-change gate is untouched by this ────────────────────────
#
# `## 332.` gates POST/PUT/DELETE on the same prefixes; that list and this
# one are separate on purpose, and both must still cover the proxy.
ok('the key list still does NOT hold the proxy prefixes',
   not any(p in KEY for p in ROUTES),
   'the proxy is keyless by design — the UI picker sends no X-API-Key')

print()
if fails:
    print('FAILED %d check(s): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('a visited page cannot read the local model roster: all checks passed')
