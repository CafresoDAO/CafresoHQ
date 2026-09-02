#!/usr/bin/env python3
"""GET /fs/collect skipped the sandbox in local mode — unauthenticated
arbitrary-directory read.

`fs_routes._fs_collect` (walked by Publish-to-Canister, called from
claude-client.jsx's fsCollect helper) validated its `path` query param via
`self._validate_path(req_path)`. That function (serve.py) has a deliberate
skip: in local/native mode with no explicit CAFRESOHQ_ALLOWED_DIRS env var
set — the default outside a container — it returns the resolved path with
NO whitelist check at all, on the theory that "the user is developing
locally and can access their own files".

/fs/collect is not behind an API key (see serve.py's
_KEY_PROTECTED_PREFIXES: only the /fs *mutation* routes are key-gated; the
read routes are deliberately keyless and rely on the allowed-dirs boundary
instead). So in the default local configuration, any HTTP client that can
reach the dev server — no auth, no key — could ask
`GET /fs/collect?path=/etc` (or `~`, or any other directory on the host)
and get back a walk of every file under it, base64-encoded, in the JSON
response. `_fs_browse`, `_fs_file`, and `_fs_stat` — the other three
keyless /fs read routes — already went through this exact fix (their own
comments say so: "enforced in EVERY mode — was container-only, which left
local/BYO reads unbounded"). `_fs_collect` was the one route that still
used the skippable check, alone among its siblings.

Fix: `_fs_collect` now resolves the path via `_workspace_path(...).resolve()`
(no validation) and then checks it against `_within_allowed_dirs(p)` —
serve.py's OTHER path guard, which has no local-mode skip and is
"enforced in EVERY runtime mode" per its own docstring — exactly matching
the pattern `_fs_browse`/`_fs_file`/`_fs_stat` already use.

This test genuinely invokes the real `_fs_collect` function (not a
reimplementation) against a temp directory tree, with `fs_routes`'s module
globals wired up the same way serve.py wires them at import time, proving:
  - a path inside the configured allowed dirs still walks and returns files
    (the legitimate Publish-to-Canister case is not broken by this fix)
  - a path outside the allowed dirs is refused with 403, even though no
    CAFRESOHQ_ALLOWED_DIRS env var is set and _RUNTIME_ENV is 'local' —
    the exact configuration that let the bug through before.

Run: python3 scripts/test_fs_collect_enforces_allowed_dirs.py
"""
import json
import re
import sys
import tempfile
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FS_ROUTES = ROOT / 'fs_routes.py'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("/fs/collect enforces the allowed-dirs sandbox in local mode")
    src = FS_ROUTES.read_text(encoding='utf-8')

    fn = src[src.index('def _fs_collect('):]
    fn = fn[:fn.index('\ndef _fs_file(')]

    code_lines = '\n'.join(
        line for line in fn.splitlines() if not line.strip().startswith('#'))
    check("_fs_collect no longer CALLS the skippable self._validate_path() — "
          "the actual regression: that function returns the path completely "
          "unchecked in local mode with no explicit CAFRESOHQ_ALLOWED_DIRS "
          "(a mention of it in the explanatory comment is fine — only an "
          "actual call site in real code would mean the fix didn't take)",
          not re.search(r'self\._validate_path\(', code_lines), code_lines)

    check("_fs_collect now resolves the path via the plain _workspace_path "
          "helper (anchoring only, no validation of its own)",
          bool(re.search(r'root\s*=\s*_workspace_path\(req_path\)\.resolve\(\)', fn)))

    check("...and gates it with _within_allowed_dirs — the OTHER guard in "
          "serve.py, which has no local-mode skip and is unconditional in "
          "every runtime mode, matching _fs_browse/_fs_file/_fs_stat",
          bool(re.search(r'if not _within_allowed_dirs\(root\):', fn)))

    check("the refusal is still a 403 with the same message as the sibling "
          "routes, so existing callers/UI see a familiar error shape",
          "'path is outside CAFRESOHQ_ALLOWED_DIRS'" in fn)

    # ── Genuine execution: import fs_routes for real, wire its module
    # globals the way serve.py does at import time, and call the actual
    # _fs_collect function against real temp directories. ───────────────
    sys.path.insert(0, str(ROOT))
    import fs_routes  # noqa: E402
    import pathlib

    with tempfile.TemporaryDirectory() as tmp:
        allowed_root = Path(tmp) / 'allowed'
        outside_root = Path(tmp) / 'outside'
        (allowed_root / 'site').mkdir(parents=True)
        (outside_root).mkdir(parents=True)
        (allowed_root / 'site' / 'index.html').write_text('<h1>hi</h1>', encoding='utf-8')
        (outside_root / 'secret.txt').write_text('should never be readable', encoding='utf-8')

        def _client_path(p):
            return p

        def _workspace_path(path, strict=False):
            return pathlib.Path(path)

        def _within_allowed_dirs(p):
            try:
                rp = pathlib.Path(p).resolve()
            except Exception:
                return False
            try:
                rp.relative_to(allowed_root.resolve())
                return True
            except ValueError:
                return False

        fs_routes._client_path = _client_path
        fs_routes._workspace_path = _workspace_path
        fs_routes._within_allowed_dirs = _within_allowed_dirs
        fs_routes._RUNTIME_ENV = 'local'
        fs_routes._ALLOWED_DIRS_EXPLICIT = False
        fs_routes._cafresohq_allowed_dirs = (str(allowed_root),)

        class FakeSelf:
            def __init__(self, path):
                self.path = path
                self.sent = None

            def _send_json(self, code, payload):
                self.sent = (code, payload)

        # In-sandbox path: must still work (the legitimate Publish flow).
        inside = FakeSelf('/fs/collect?path=' + urllib.parse.quote(str(allowed_root)))
        fs_routes._fs_collect(inside)
        code, payload = inside.sent
        check('a path INSIDE the allowed dirs still returns 200 with the '
              'walked file collected — the fix does not break the '
              'legitimate Publish-to-Canister caller',
              code == 200 and any(f['path'] == 'site/index.html' for f in payload.get('files', [])),
              (code, payload))

        # Out-of-sandbox path: the actual reported vulnerability. No
        # CAFRESOHQ_ALLOWED_DIRS env var is set (_ALLOWED_DIRS_EXPLICIT is
        # False) and _RUNTIME_ENV is 'local' — precisely the configuration
        # that let self._validate_path() skip its check before this fix.
        outside = FakeSelf('/fs/collect?path=' + urllib.parse.quote(str(outside_root)))
        fs_routes._fs_collect(outside)
        code, payload = outside.sent
        check('a path OUTSIDE the allowed dirs is refused with 403 even in '
              'local mode with no explicit CAFRESOHQ_ALLOWED_DIRS — before '
              'the fix this walked and base64-returned secret.txt instead',
              code == 403 and 'files' not in payload,
              (code, payload))

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
