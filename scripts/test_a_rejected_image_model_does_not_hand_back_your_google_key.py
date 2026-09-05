#!/usr/bin/env python3
"""The image generator must never answer with the tester's own provider key.

#322. A beta tester pastes a real Google AI Studio key into Settings ->
Connections and a model name into Settings -> Media. `_generate_image`
forwarded that key to Google in the query string of the request URL:

    .../v1beta/models/{model_id}:predict?key={api_key}

`model_id` is free text. Give it a space -- "imagen 4", "gemini 2.5 flash
image", anything a person would type -- and urllib refuses to build the
request at all, raising

    ValueError: URL can't contain control characters. '<the entire URL>'

The handler's `except Exception as e` arm returned `str(e)` to the browser,
so the app's answer to "make me a picture" was a 500 whose body quoted the
tester's plaintext Google key. That string is what lands in a screenshot, a
console, and the bug report they paste into a chat window.

This drives the real handler with a fake request handler and a sentinel key,
and asserts the sentinel appears in NO response body, on NO error path.
"""
import io
import json
import os
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SENTINEL = 'AIzaSyCAFRESO-322-SENTINEL-NOT-A-REAL-KEY-0000'

fails = []


def ok(msg):
    print(f'ok - {msg}')


def fail(msg):
    print(f'FAIL - {msg}')
    fails.append(msg)


# ── harness ────────────────────────────────────────────────────────────────
import exporters  # noqa: E402

_VAULT = tempfile.mkdtemp(prefix='hq322-vault-')
exporters._vault_root = lambda: _VAULT
exporters._vault_hidden_part = lambda rel: next(
    (p for p in str(rel).replace('\\', '/').split('/')
     if p.startswith('.') and p not in ('.', '..')), '')


class FakeHandler:
    """Just enough of serve.py's Handler for the generate endpoints."""

    def __init__(self, body):
        raw = json.dumps(body).encode('utf-8')
        self.rfile = io.BytesIO(raw)
        self.headers = {'content-length': str(len(raw))}
        self.sent = None

    _read_json_body = exporters._read_json_body
    _vault_binary_path = exporters._vault_binary_path

    def _send_json(self, code, obj):
        self.sent = (code, obj)
        return obj


def run_image(body):
    h = FakeHandler(body)
    try:
        exporters._generate_image(h)
    except Exception as e:                     # a raise is also a leak channel
        return ('raised', {'error': f'{type(e).__name__}: {e}'})
    return h.sent if h.sent else ('none', {})


def body_text(sent):
    return json.dumps(sent[1] if isinstance(sent, tuple) else sent)


# ── 1. the observed leak: a model name urllib refuses ──────────────────────
# No socket is opened on this path -- urllib rejects the URL locally -- so
# this test never talks to Google and never spends anyone's quota.
for bad_model in ('imagen 4', 'gemini 2.5 flash image'):
    sent = run_image({'path': 'shot.png', 'prompt': 'a cat',
                      'provider': 'google', 'model': bad_model,
                      'apiKey': SENTINEL})
    text = body_text(sent)
    if SENTINEL in text:
        fail(f'model {bad_model!r}: the response handed the key back -> {text[:220]}')
    else:
        ok(f'model {bad_model!r}: rejected without quoting the key')

# ── 2. no google branch may put the key in a URL at all ────────────────────
src = (ROOT / 'exporters.py').read_text(encoding='utf-8')
# Strip comments and docstrings first: this file's own prose explains the bug
# and necessarily contains the very pattern being searched for.
try:
    import ast
    import tokenize

    def strip_comments(text):
        out = []
        readline = io.StringIO(text).readline
        for tok in tokenize.generate_tokens(readline):
            if tok.type in (tokenize.COMMENT,):
                continue
            out.append(tok)
        return tokenize.untokenize(out)

    code = strip_comments(src)
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            node.value.value = ''
    code = ast.unparse(tree)
except Exception as e:                                  # pragma: no cover
    fail(f'could not strip comments from exporters.py: {e}')
    code = ''

hits = [ln for ln in code.splitlines()
        if 'googleapis.com' in ln and re.search(r'[?&]key=', ln)]
if hits:
    fail('a google URL still carries the key in its query string: '
         + ' | '.join(h.strip()[:120] for h in hits))
else:
    ok('no googleapis.com URL is built with ?key=')

hdr = [ln for ln in code.splitlines() if 'x-goog-api-key' in ln]
if len(hdr) >= 2:
    ok('both google image endpoints send the key as an x-goog-api-key header')
else:
    fail(f'expected 2 x-goog-api-key headers in exporters.py, found {len(hdr)}')

# ── 3. the scrub is actually wired to the error paths ──────────────────────
scrubbed = exporters._scrub(
    f"URL can't contain control characters. '/v1beta/x:predict?key={SENTINEL}'",
    SENTINEL)
if SENTINEL in scrubbed:
    fail('_scrub did not remove the secret')
else:
    ok('_scrub removes the secret from an error string')

if exporters._scrub('nothing to see', '') == 'nothing to see':
    ok('_scrub leaves an empty secret alone')
else:
    fail('_scrub mangled a string when no secret was supplied')

unscrubbed = [ln.strip() for ln in code.splitlines()
              if '_send_json(500' in ln and 'str(e)' in ln]
if unscrubbed:
    fail('a generate error path still returns a raw str(e): '
         + ' | '.join(u[:120] for u in unscrubbed))
else:
    ok('every generate 500 path runs its error text through _scrub')

# ── 4. a provider that echoes the key in its own 4xx body ──────────────────
# HTTPError bodies come from the provider and are relayed verbatim; the scrub
# has to catch a credential quoted there too.
relayed = exporters._scrub(
    json.dumps({'error': {'message': f'API key not valid: {SENTINEL}'}}),
    SENTINEL)
if SENTINEL in relayed:
    fail('a provider 4xx body could still relay the key to the browser')
else:
    ok('a provider 4xx body quoting the key is scrubbed before relay')

print()
if fails:
    print(f'{len(fails)} check(s) failed')
    sys.exit(1)
print('all checks passed')
