#!/usr/bin/env python3
"""Every Terminal tab 400'd on a self-hosted install: cwd was container-only.

views/misc.jsx's TerminalView (the standalone Terminal sidebar tab — distinct
from the per-Project terminal, which passes its own real path) falls back to
'/root/Documents' whenever `window._TERMINAL_CWD` is unset. That path is the
container image's code-agent sandbox dir (docker/Dockerfile creates it under
root's home), but nothing in serve.py ever SET `window._TERMINAL_CWD` on any
run outside that container. Confirmed live: driving Terminal -> Hermes in a
throwaway self-hosted office produced a WebSocket that connected then
immediately failed, because pty_server.py's `/terminal/pty` handler 400s with
"directory not found: <cwd>" whenever `cwd_path.is_dir()` is false — and on a
real Mac/Linux self-host, /root doesn't exist at all (not even readable by a
non-root user).

Fix: serve.py now computes `_cafresohq_terminal_cwd` the same way it already
computes `_cafresohq_allowed_dirs`'s local-mode default (CAFRESOHQ_ALLOWED_DIRS
docstring, ~line 148) — `~/Documents`, overridable via the *_CWD env var the
misc.jsx comment always claimed existed but was never implemented — and
injects it as `window._TERMINAL_CWD=...` in `_hq_manifest_tags()`, right next
to the existing `window.__CAFRESO_BUNDLE__` injection. Because the container
runs as root, `~/Documents` there resolves to the exact same `/root/Documents`
as before — zero behavior change for the managed/OCI path, real behavior for
every self-hosted one.

Verified live: rebuilt the bundle, restarted a throwaway office, confirmed
`window._TERMINAL_CWD` was the real home Documents dir, and opening a Hermes
terminal tab produced a real PTY session ("Welcome to Hermes Agent!") instead
of a connect/fail loop — server log showed `WS detached: ... @
/Users/<user>/Documents`.

Run: python3 scripts/test_terminal_cwd_wired.py
"""
import importlib
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def load_serve_with_home(home):
    """Import serve.py fresh with HOME/USERPROFILE pointed at `home`, so its
    module-level `os.path.expanduser('~')` calls pick it up. serve.py must
    already be imported by an earlier test in the same process (common in
    this suite's run-all loop) — del it from sys.modules first so the
    module body actually re-executes instead of returning the cached one."""
    old_home = os.environ.get('HOME')
    os.environ['HOME'] = home
    sys.modules.pop('serve', None)
    try:
        return importlib.import_module('serve')
    finally:
        if old_home is None:
            os.environ.pop('HOME', None)
        else:
            os.environ['HOME'] = old_home


# 1. Default: no CAFRESOHQ_TERMINAL_CWD set -> ~/Documents of that HOME.
with tempfile.TemporaryDirectory() as tmp_home:
    os.environ.pop('CAFRESOHQ_TERMINAL_CWD', None)
    serve = load_serve_with_home(tmp_home)
    expected = os.path.join(tmp_home, 'Documents')
    check(
        serve._cafresohq_terminal_cwd == expected,
        f"serve._cafresohq_terminal_cwd should default to '{expected}' "
        f"(mirrors CAFRESOHQ_ALLOWED_DIRS's own local-mode default), got "
        f"'{serve._cafresohq_terminal_cwd}'.",
    )

# 2. Explicit CAFRESOHQ_TERMINAL_CWD overrides the default.
with tempfile.TemporaryDirectory() as tmp_home:
    os.environ['CAFRESOHQ_TERMINAL_CWD'] = '/some/explicit/path'
    try:
        serve = load_serve_with_home(tmp_home)
        check(
            serve._cafresohq_terminal_cwd == '/some/explicit/path',
            "CAFRESOHQ_TERMINAL_CWD env var should override the ~/Documents "
            f"default, got '{serve._cafresohq_terminal_cwd}'.",
        )
    finally:
        os.environ.pop('CAFRESOHQ_TERMINAL_CWD', None)

# 3. _hq_manifest_tags() actually emits the window._TERMINAL_CWD script tag.
#    Method body never touches `self`, so it's safe to call unbound.
serve = load_serve_with_home(os.path.expanduser('~'))
tags = serve.Handler._hq_manifest_tags(None)
check(
    'window._TERMINAL_CWD=' in tags,
    "_hq_manifest_tags() must inject a `window._TERMINAL_CWD=...` script "
    "tag — without it, views/misc.jsx's TerminalView silently falls back "
    "to the container-only '/root/Documents'.",
)

# 4. views/misc.jsx must still read window._TERMINAL_CWD (the client half
#    of this fix was already correct — only the server-side injection and
#    the misc.jsx fallback comment's promised env var were missing).
misc_src = (ROOT / 'views' / 'misc.jsx').read_text()
check(
    "window._TERMINAL_CWD" in misc_src,
    "views/misc.jsx must read window._TERMINAL_CWD for TerminalView's cwd.",
)

if failures:
    print("FAIL:")
    for f in failures:
        print(f" - {f}")
    raise SystemExit(1)

print("ALL PASS")
