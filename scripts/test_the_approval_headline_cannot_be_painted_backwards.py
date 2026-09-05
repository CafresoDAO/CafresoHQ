#!/usr/bin/env python3
"""The approval row's HEADLINE was the one consent surface with no bidi guard.

An external approval row has two surfaces that carry the requesting agent's
own bytes:

  1. the detail box  — `formatToolInput(p.input)`, which since the
     trojan-source fix escapes Unicode bidi controls (U+202A-U+202E,
     U+2066-U+2069) to a visible `\\uXXXX`; and
  2. the headline    — `Bash: <summary>`, which app.jsx assembled inline
     out of `p.summary`. `claude_approval_hook.py` fills that field with
     the first 200 characters of the ACTUAL command.

Only (1) was guarded. So a command carrying a RIGHT-TO-LEFT OVERRIDE
painted a reordered headline while the box underneath it showed the truth:
the two halves of the same consent row disagreed, and the half the boss
reads FIRST was the lying one. The headline is also what `recordReceipt`
copies verbatim into the Receipts modal — "stamped approvals · audit
trail" — so the spoof outlived the decision it spoofed.

The hook's 200-char cut makes it worse: it can slice an override away from
its POP DIRECTIONAL FORMATTING, leaving an unterminated control that
reorders the rest of the row too ("by claude-code · in <cwd>").

The fix moves the headline into app/approvals.jsx as `approvalTitle` and
runs it through the same escape as the value box — escaped visibly, never
stripped, so nothing about the claim disappears.

Run: python3 scripts/test_the_approval_headline_cannot_be_painted_backwards.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app' / 'approvals.jsx'
APP = ROOT / 'app.jsx'

FAILS = []

RLO = '‮'
PDF = '‬'
LRI = '⁦'


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def run_js(cases_js):
    text = SRC.read_text(encoding='utf-8')
    src = '\n'.join(ln for ln in text.split('\n')
                    if not ln.startswith('import ') and not ln.startswith('export '))
    proc = subprocess.run(['node', '--input-type=module', '-e', src + '\n' + cases_js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


CASES = r'''
const R = {};
const rlo = '‮', pdf = '‬', lri = '⁦';

/* Exactly what claude_approval_hook.py would post for this Bash call:
   `summary` is the first 200 chars of the real command. */
const spoofed = 'rm -rf /tmp/cache ' + rlo + 'hsart/ fr- mr' + pdf;
R.spoofed = approvalTitle('Bash', spoofed, { command: spoofed, description: 'tidy up' });

/* The hook's 200-char cut can drop the terminator, leaving an override
   that runs past the end of the headline into the rest of the row. */
R.unterminated = approvalTitle('Bash', 'echo hi ' + rlo + 'oops', { command: 'x' });
R.isolate = approvalTitle('Bash', 'echo ' + lri + 'hi', { command: 'x' });

/* Ordinary requests must come out byte-for-byte as before this fix. */
R.plain = approvalTitle('Bash', 'ls -la', { command: 'ls -la' });
R.noSummary = approvalTitle('Bash', '', { command: 'x', description: 'y' });
R.noArgs = approvalTitle('Read', '', {});
R.nullish = approvalTitle('Bash', null, null);

console.log(JSON.stringify(R));
'''


def main():
    print('the approval headline cannot be painted backwards')

    src = SRC.read_text(encoding='utf-8')
    check('app/approvals.jsx owns the headline (approvalTitle) and exports it',
          'function approvalTitle' in src and re.search(r'export\s*{[^}]*approvalTitle', src),
          'the headline must be built by the file that owns consent honesty, '
          'not assembled inline next to the fetch')

    app = APP.read_text(encoding='utf-8')
    check('app.jsx imports it', bool(re.search(
        r'import\s*{[^}]*approvalTitle[^}]*}\s*from\s*[\'"]\./app/approvals\.jsx[\'"]', app)))
    check('app.jsx builds the external approval title through it',
          'title: approvalTitle(' in app)
    check('...and no longer interpolates the raw summary into the headline',
          '`${p.tool}: ${p.summary}`' not in app,
          'the unguarded inline template is still there')

    if not shutil.which('node'):
        print('  SKIP  node not available for the behaviour half')
        return 1 if FAILS else 0

    out = run_js(CASES)

    check('a RIGHT-TO-LEFT OVERRIDE never reaches the renderer in the headline',
          RLO not in out['spoofed'],
          f'{out["spoofed"]!r} would be PAINTED in a different order than the '
          'command it names — and the detail box beside it shows the honest '
          'text, so the row contradicts itself')
    check('...nor its POP DIRECTIONAL FORMATTING partner',
          PDF not in out['spoofed'], repr(out['spoofed']))
    check('...it is escaped visibly (\\u202E), not silently stripped',
          '\\u202E' in out['spoofed'], repr(out['spoofed']))
    check('...and every real character of the claim survives',
          out['spoofed'].startswith('Bash: rm -rf /tmp/cache ')
          and 'hsart/ fr- mr' in out['spoofed'], repr(out['spoofed']))

    check('an override the hook truncated away from its terminator is caught too',
          RLO not in out['unterminated'] and '\\u202E' in out['unterminated'],
          repr(out['unterminated']))
    check('the isolate successors (U+2066-U+2069) are caught as well',
          LRI not in out['isolate'] and '\\u2066' in out['isolate'],
          repr(out['isolate']))

    check('an ordinary headline is untouched, byte for byte',
          out['plain'] == 'Bash: ls -la', repr(out['plain']))
    check('the no-summary fallback still lists argument NAMES',
          out['noSummary'] == 'Bash (command, description)', repr(out['noSummary']))
    check('...and still says "no args" when there are none',
          out['noArgs'] == 'Read (no args)', repr(out['noArgs']))
    check('a missing summary and a missing input do not produce "undefined"',
          'undefined' not in out['nullish'] and out['nullish'] == 'Bash (no args)',
          repr(out['nullish']))

    return 1 if FAILS else 0


rc = main()
if FAILS:
    print(f'\n{len(FAILS)} check(s) failed:')
    for f in FAILS:
        print(f'  - {f}')
    sys.exit(1)
print('\nall checks passed')
sys.exit(rc)
