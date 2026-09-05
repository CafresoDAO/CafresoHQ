#!/usr/bin/env python3
"""claude_approval_hook.py is the PreToolUse gate between Claude Code and the
HQ ApprovalTray, and #237 pinned the rule this file lives by: per Claude
Code's hook contract (code.claude.com/docs/hooks.md, "Exit Codes & Output")
only exit code 2 hard-blocks a tool call — every other nonzero exit is
"non-blocking error by default — action proceeds". So an uncaught exception
in this hook does not deny a tool call, it silently ALLOWS it.

#237 applied that rule to the two `json.loads` calls inside `main()`. It did
not apply it one line up, to the module body, where a crash is the same
bypass with none of the evidence: no tray row, no decision on stdout, and
every tool call in the session waved through unapproved.

    TIMEOUT_S = int(os.environ.get('CAFRESOHQ_HQ_TIMEOUT', '1800'))

`CAFRESOHQ_HQ_TIMEOUT` is a documented env knob (this file's own docstring
lists it). Exported empty — `export CAFRESOHQ_HQ_TIMEOUT=`, or a settings
entry set to "" — `os.environ.get` returns '' rather than the default and
`int('')` raises ValueError at import. So does any human spelling of a
duration: `30m`, `1800s`, `1800.0`.

It is the odd one out among fifteen numeric env reads in this repo. The
other fourteen all guard the empty string with `or <default>`:
serve.py's PORT and _TRIAL_DAILY_CAP, drivers/hermes.py's HERMES_PORT, and
eleven budgets/caps/intervals in search_worker_service/worker.py. The one
that didn't is the one whose failure is a security boundary.

Fix: `_int_env()` falls back to the documented default for anything that
isn't an integer, so a mistyped knob costs you your custom timeout and
nothing else — the gate still asks, and still denies when HQ is unreachable.

Run: python3 scripts/test_a_mistyped_timeout_knob_never_waves_a_tool_call_through.py
"""
import importlib.util
import io
import json
import os
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


def load_hook_module(env):
    """Import the REAL file with `env` overlaid on os.environ.

    Returns (module_or_None, exception_or_None) — the import itself is the
    thing under test, so a raise here is a result, not a test error.
    """
    with mock.patch.dict(os.environ, env, clear=False):
        spec = importlib.util.spec_from_file_location('claude_approval_hook_t', SRC)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except BaseException as e:
            return None, e
    return mod, None


def run_main_denies(mod, payload):
    """Drive the real main() with an HQ that never answers. Returns the
    permissionDecision string, or None if it crashed / printed nothing."""
    out = io.StringIO()
    fake_stdin = io.StringIO(json.dumps(payload))
    boom = urllib.error.URLError('connection refused')
    with mock.patch.object(sys, 'stdin', fake_stdin), \
         mock.patch('urllib.request.urlopen', side_effect=boom):
        try:
            with redirect_stdout(out):
                mod.main()
        except SystemExit:
            pass
        except BaseException:
            return None
    try:
        return json.loads(out.getvalue())['hookSpecificOutput']['permissionDecision']
    except Exception:
        return None


PAYLOAD = {
    'tool_name': 'Bash',
    'tool_input': {'command': 'rm -rf /tmp/whatever'},
    'cwd': '/tmp',
    'session_id': 'sess1',
}

# Every one of these is a value a person can actually put in a shell profile
# or a settings.json env block. None of them is a reason to stop asking.
BAD_KNOBS = [
    ('an exported-but-empty knob', ''),
    ('a duration with a unit', '30m'),
    ('seconds spelled with an s', '1800s'),
    ('a word', 'default'),
    ('a float', '1800.0'),
]


def main():
    print('a mistyped CAFRESOHQ_HQ_TIMEOUT never waves a tool call through')

    # Baseline: with the knob unset the documented default must still be 1800.
    mod, err = load_hook_module({'CAFRESOHQ_HQ_TIMEOUT': '1800'})
    check('the documented default (1800s) still imports', err is None, err)
    if mod is not None:
        check('...and TIMEOUT_S is 1800', mod.TIMEOUT_S == 1800, getattr(mod, 'TIMEOUT_S', None))

    # A real, valid override must still be honoured — this fix must not turn
    # the knob into a decoration.
    mod, err = load_hook_module({'CAFRESOHQ_HQ_TIMEOUT': '900'})
    check('a real override (900) is still honoured',
          err is None and mod is not None and mod.TIMEOUT_S == 900,
          err or getattr(mod, 'TIMEOUT_S', None))
    mod, err = load_hook_module({'CAFRESOHQ_HQ_TIMEOUT': '  900  '})
    check('...and surviving stray whitespace around it',
          err is None and mod is not None and mod.TIMEOUT_S == 900,
          err or getattr(mod, 'TIMEOUT_S', None))

    for label, value in BAD_KNOBS:
        mod, err = load_hook_module({'CAFRESOHQ_HQ_TIMEOUT': value})
        check(f'{label} ({value!r}) does not crash the hook at import '
              '(an import crash never reaches _emit, and per the Claude Code '
              'hook contract a nonzero exit lets the tool call proceed '
              'unapproved)',
              err is None, f'{type(err).__name__}: {err}' if err else '')
        if mod is None:
            continue
        check(f'...{label}: TIMEOUT_S falls back to the documented 1800',
              mod.TIMEOUT_S == 1800, mod.TIMEOUT_S)
        # End to end: the gate still runs, and an unreachable HQ still denies.
        mod.FAIL_OPEN = False
        decision = run_main_denies(mod, PAYLOAD)
        check(f'...{label}: the gate still emits a decision, and it is deny',
              decision == 'deny', decision)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
