#!/usr/bin/env python3
"""A command-line brain that cannot run says why, in one sentence.

Measured on a real machine with five brains hired: Codex answered a message
with a Node stack trace and terminal colour codes, and Gemini with start-up
chatter in front of the one line that mattered (Google refusing the account).
drivers.base.explain_failure names the failures we can identify and says what
to do; anything else keeps the old "exited N: …" shape with the noise removed.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from drivers.base import explain_failure, tidy_stderr  # noqa: E402
from drivers.gemini_cli import GeminiCliDriver  # noqa: E402

failures = []


def check(name, ok, detail=''):
    print(('    ok    ' if ok else '    FAIL  ') + name + (f' — {detail}' if detail and not ok else ''))
    if not ok:
        failures.append(name)


codex = ("Error: spawn /x/node_modules/@openai/codex/vendor/aarch64-apple-darwin/codex/codex ENOENT\n"
         "\x1b[90m    at ChildProcess._handle.onexit (node:internal/child_process:285:19)\x1b[39m")
s = explain_failure('Codex', codex, 1)
check('a missing program file is named as a broken install', 'cannot start' in s and 'Reinstall Codex' in s, s)
check('no stack frame, colour code or path reaches the sentence',
      '\x1b' not in s and 'ChildProcess' not in s and '/x/' not in s, s)

gemini = ("YOLO mode is enabled. All tool calls will be automatically approved.\n"
          "Error authenticating: IneligibleTierError: This client is no longer supported for "
          "Gemini Code Assist for individuals.")
s = explain_failure('Gemini', gemini, 55)
check('a refused Google account says so and names the other door',
      'no longer lets this kind of account' in s and 'Settings → Connections' in s, s)

s = explain_failure('Claude', 'OAuth session expired and could not be refreshed', 1)
check('an expired sign-in asks for a sign-in', 'not signed in' in s, s)

s = explain_failure('Codex', 'something odd\n\x1b[90m    at foo\x1b[39m', 3)
check('an unknown failure keeps its exit code and first real line', s == 'exited 3: something odd', s)
check('start-up chatter is dropped', tidy_stderr('YOLO mode is enabled.\nreal problem') == 'real problem')

check('every sentence ends as a sentence, so the chat prints it without a lead-in',
      all(explain_failure('X', t, 1).endswith('.') for t in (codex, gemini, 'not logged in')))

GeminiCliDriver.refused = 'Google no longer lets this kind of account use the Gemini command line.'
try:
    det = GeminiCliDriver().detect()
    check('the front desk is told when Google refused the account', bool(det.get('refused')), str(det))
finally:
    GeminiCliDriver.refused = ''
hire = (ROOT / 'modals' / 'hire.jsx').read_text(encoding='utf-8')
check("the card says CAN'T BE USED instead of FOUND", "c.refused ? \"CAN'T BE USED\"" in hire)

if failures:
    print(f'\n{len(failures)} check(s) failed')
    sys.exit(1)
print('\nall checks passed')
