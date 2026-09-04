#!/usr/bin/env python3
"""claude_approval_hook.py gates every Claude Code tool call on a human
decision from the HQ ApprovalTray — its own docstring says the default is
fail-closed: "CAFRESOHQ_HQ_FAILOPEN ... (default deny — fail closed)."

Confirmed against Claude Code's own hook contract (code.claude.com/docs/
hooks.md, "Exit Codes & Output"): only exit code 2 hard-blocks a
PreToolUse tool call. Every other nonzero exit is "non-blocking error by
default — action proceeds", i.e. an uncaught exception in this hook does
NOT deny the tool call, it silently ALLOWS it. That makes "never crash
without emitting a decision" a hard security requirement for this file,
not a style nicety.

Before this fix, `_post()`/`_get()` called `json.loads(r.read()...)` on
the HTTP response from the HQ server, but the `except` clauses around
both call sites only caught `(urllib.error.URLError, OSError)` —
`json.JSONDecodeError` (a `ValueError`, not an `OSError`) fell straight
through. Any non-JSON 200 response from whatever is actually listening
on CAFRESOHQ_HQ_URL — plausible in this exact environment, where
127.0.0.1:8787 is also the port the separate cafresohq search-worker
container binds (docs/OFFICE_AS_INTERFACE.md / operator notes) — crashed
the hook with an uncaught traceback instead of emitting `deny`. Per the
hook contract above, that crash does not block the tool: it lets it run
unapproved, a straight approval-gate bypass.

Fix: both except clauses now also catch `json.JSONDecodeError`, so a
malformed HQ response is treated the same as an unreachable HQ — deny by
default (or allow only if CAFRESOHQ_HQ_FAILOPEN=1), always via the
proper hookSpecificOutput JSON on stdout with exit 0.

Run: python3 scripts/test_approval_hook_denies_on_malformed_hq_response.py
"""
import importlib.util
import io
import json
import sys
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'claude_approval_hook.py'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def load_hook_module():
    spec = importlib.util.spec_from_file_location('claude_approval_hook', SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeResp:
    """Minimal stand-in for the context-manager urlopen() returns."""
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def run_main_against(mod, urlopen_side_effect, stdin_payload):
    """Feed `stdin_payload` to mod.main() with urllib.request.urlopen
    replaced by `urlopen_side_effect`. Returns (crashed: bool,
    exc_or_None, stdout_text)."""
    out = io.StringIO()
    fake_stdin = io.StringIO(json.dumps(stdin_payload))
    with mock.patch.object(sys, 'stdin', fake_stdin), \
         mock.patch('urllib.request.urlopen', side_effect=urlopen_side_effect):
        try:
            with redirect_stdout(out):
                mod.main()
        except SystemExit:
            return False, None, out.getvalue()
        except BaseException as e:  # the bug: an uncaught crash, no decision emitted
            return True, e, out.getvalue()
    return False, None, out.getvalue()


def main():
    print('claude_approval_hook.py fails closed on a malformed HQ response')

    mod = load_hook_module()
    mod.FAIL_OPEN = False  # exercise the default (fail-closed) policy

    payload = {
        'tool_name': 'Bash',
        'tool_input': {'command': 'rm -rf /tmp/whatever'},
        'cwd': '/tmp',
        'session_id': 'sess1',
    }

    # The HQ submission POST succeeds at the transport layer (200 OK) but
    # the body is not JSON at all -- e.g. some other process answering on
    # that port, or a proxy/error page. This is what `_post()` sees.
    crashed, exc, out = run_main_against(
        mod, lambda *a, **k: _FakeResp(b'Not Found'), payload)

    check('the hook does not crash on a non-JSON HQ response '
          '(a crash here fails OPEN per the Claude Code hook contract: '
          'only exit code 2 blocks, every other nonzero exit lets the '
          'tool call proceed unapproved)',
          not crashed, f'{type(exc).__name__}: {exc}' if crashed else '')

    if not crashed:
        try:
            decision = json.loads(out)['hookSpecificOutput']['permissionDecision']
        except Exception as e:
            decision = None
            check('stdout is the expected hookSpecificOutput JSON', False, f'{e}: {out!r}')
        else:
            check('stdout is the expected hookSpecificOutput JSON', True)
        check("...and the decision is 'deny' (fail-closed default, "
              "CAFRESOHQ_HQ_FAILOPEN unset)",
              decision == 'deny', decision)

    # Same shape of bug, but during the long-poll wait() call instead of
    # the initial submit -- the second, separately-patched except clause.
    calls = {'n': 0}

    def two_stage(*a, **k):
        calls['n'] += 1
        if calls['n'] == 1:
            return _FakeResp(json.dumps({'id': 'ce_test123'}).encode('utf-8'))
        return _FakeResp(b'<html>garbage</html>')

    crashed2, exc2, out2 = run_main_against(mod, two_stage, payload)
    check('the hook does not crash on a non-JSON response during the '
          'wait/long-poll leg either',
          not crashed2, f'{type(exc2).__name__}: {exc2}' if crashed2 else '')
    if not crashed2:
        decision2 = json.loads(out2)['hookSpecificOutput']['permissionDecision']
        check("...and again denies by default", decision2 == 'deny', decision2)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
