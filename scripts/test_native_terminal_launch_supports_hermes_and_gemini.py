#!/usr/bin/env python3
"""The Terminal's "pop out" button and its native-terminal fallback screen
promised to launch whichever CLI tab the boss was on — Hermes is even the
DEFAULT tab (views/terminal.jsx's add-session menu) — but the server-side
handler behind both, pty_server.py's `_terminal_spawn` (GET /terminal/spawn),
only ever accepted `cli=claude` or `cli=codex`. Its sibling handler five
lines of logic away, `_terminal_pty_ws` (the embedded in-app PTY, GET
/terminal/pty), already accepted all four CLIs — proving the product intends
Hermes/Gemini to be full terminal citizens; only the native-window spawn
path was never extended to match.

Repro (pre-fix): open a Project's Terminal tab (default tab: Hermes), switch
to PTY mode, click "⬡ pop out" (or, on a host without an in-app PTY, the
fallback screen's "▶ LAUNCH HERMES IN TERMINAL" button). GET
/terminal/spawn?cli=hermes&cwd=... returned 400 {"error": "cli must be
claude or codex"}, surfaced verbatim to the boss as
"⚠ cli must be claude or codex" — no terminal window opened. Same for the
Gemini tab. Claude/Codex worked; so did Hermes/Gemini's own embedded PTY —
proving the gap was specifically this one whitelist, not a missing CLI
integration.

Run: python3 scripts/test_native_terminal_launch_supports_hermes_and_gemini.py
"""
import importlib
import json
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


sys.modules.pop('serve', None)
sys.modules.pop('pty_server', None)
serve = importlib.import_module('serve')
pty_server = sys.modules['pty_server']


class FakeSelf:
    def __init__(self, resolvers):
        self._resolvers = resolvers
        self.responses = []

    def _send_json(self, code, payload):
        self.responses.append((code, payload))

    def _claudecode_resolve(self): return self._resolvers.get('claude')
    def _codex_resolve(self):      return self._resolvers.get('codex')
    def _gemini_resolve(self):     return self._resolvers.get('gemini')
    def _hermes_resolve(self):     return self._resolvers.get('hermes')


def spawn(cli, cwd, resolvers, platform='darwin', which_map=None):
    """Drive the real, production-bound serve.Handler._terminal_spawn."""
    fs = FakeSelf(resolvers)
    fs.path = f'/terminal/spawn?cli={cli}&cwd={cwd}'
    popen_calls = []
    orig_platform = pty_server.sys.platform
    orig_which = pty_server.shutil.which
    orig_popen = pty_server.subprocess.Popen
    pty_server.sys.platform = platform
    pty_server.shutil.which = (lambda name: (which_map or {}).get(name, f'/usr/bin/{name}'))
    pty_server.subprocess.Popen = lambda *a, **k: popen_calls.append((a, k))
    try:
        serve.Handler._terminal_spawn(fs)
    finally:
        pty_server.sys.platform = orig_platform
        pty_server.shutil.which = orig_which
        pty_server.subprocess.Popen = orig_popen
    return fs.responses, popen_calls


with tempfile.TemporaryDirectory() as tmp:
    all_resolved = {'claude': '/bin/claude', 'codex': '/bin/codex',
                     'gemini': '/bin/gemini', 'hermes': '/bin/hermes'}

    # 1. Hermes is no longer rejected by the whitelist (the core bug).
    resp, calls = spawn('hermes', tmp, all_resolved)
    check(len(resp) == 1 and resp[0][0] == 200,
          f"cli=hermes should succeed (200), got {resp} — this is the exact "
          f"'⚠ cli must be claude or codex' regression the boss hit clicking "
          f"pop-out on the DEFAULT terminal tab")
    check(len(calls) == 1, "hermes should spawn exactly one terminal process")

    # 2. Gemini is no longer rejected either.
    resp, calls = spawn('gemini', tmp, all_resolved)
    check(len(resp) == 1 and resp[0][0] == 200,
          f"cli=gemini should succeed (200), got {resp}")
    check(len(calls) == 1, "gemini should spawn exactly one terminal process")

    # 3. Claude/Codex are unchanged (still 200, still one spawn each) —
    #    the fix is additive, not a rewrite of the working paths.
    for cli in ('claude', 'codex'):
        resp, calls = spawn(cli, tmp, all_resolved)
        check(len(resp) == 1 and resp[0][0] == 200,
              f"cli={cli} should still succeed (200), got {resp}")

    # 4. A still-genuinely-unsupported cli value is still rejected, and the
    #    error message now names all four supported CLIs (not the stale pair).
    resp, _ = spawn('bogus', tmp, all_resolved)
    check(len(resp) == 1 and resp[0][0] == 400
          and resp[0][1].get('error') == 'cli must be claude, codex, hermes, or gemini',
          f"an unsupported cli should still 400 with an up-to-date error "
          f"message, got {resp}")

    # 5. Hermes resolves through _hermes_resolve specifically (not silently
    #    falling through to _codex_resolve, which the old ternary would have
    #    done had the whitelist merely been widened without fixing dispatch).
    resp, _ = spawn('hermes', tmp, {'claude': '/bin/claude', 'codex': '/bin/codex',
                                     'gemini': '/bin/gemini', 'hermes': None})
    check(len(resp) == 1 and resp[0] == (503, {'error': 'hermes CLI not found'}),
          f"hermes CLI missing should 503 as 'hermes CLI not found' via "
          f"_hermes_resolve, not silently succeed via _codex_resolve, got {resp}")

    # 6. Gemini resolves through _gemini_resolve specifically.
    resp, _ = spawn('gemini', tmp, {'claude': '/bin/claude', 'codex': '/bin/codex',
                                     'gemini': None, 'hermes': '/bin/hermes'})
    check(len(resp) == 1 and resp[0] == (503, {'error': 'gemini CLI not found'}),
          f"gemini CLI missing should 503 as 'gemini CLI not found', got {resp}")

    # 7. Hermes' spawned command includes the 'chat' subcommand — mirroring
    #    _terminal_pty_ws's own `cli_extra_args = ['chat'] if cli == 'hermes'`
    #    — because the bare `hermes` binary doesn't open the interactive
    #    agent (see that handler's comment). Checked on macOS (AppleScript
    #    `do script`) and Linux (argv list) branches, the two this dev
    #    machine can meaningfully assert on.
    _, calls = spawn('hermes', tmp, all_resolved, platform='darwin')
    if calls:
        applescript = calls[0][0][0][2]  # Popen(['osascript', '-e', applescript])
        check('hermes chat' in applescript,
              f"macOS spawn should run 'hermes chat', not bare 'hermes' "
              f"(bare hermes doesn't open the interactive agent) — "
              f"applescript was: {applescript!r}")
        check('claude chat' not in applescript.replace('hermes chat', ''),
              "sanity: no cross-CLI contamination in the applescript string")

    _, calls = spawn('claude', tmp, all_resolved, platform='darwin')
    if calls:
        applescript = calls[0][0][0][2]
        check('claude chat' not in applescript and 'do script "cd ' in applescript,
              f"claude should NOT get a 'chat' subcommand appended (only "
              f"hermes needs it) — applescript was: {applescript!r}")

    _, calls = spawn('hermes', tmp, all_resolved, platform='linux',
                      which_map={'x-terminal-emulator': '/usr/bin/x-terminal-emulator'})
    if calls:
        args = calls[0][0][0]  # Popen([term, '-e', 'hermes', 'chat'], cwd=...)
        check(args[-2:] == ['hermes', 'chat'],
              f"Linux spawn argv should end with ['hermes', 'chat'], got {args}")

if failures:
    print("FAIL:")
    for f in failures:
        print(f" - {f}")
    raise SystemExit(1)

print("ALL PASS")
