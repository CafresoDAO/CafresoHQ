#!/usr/bin/env python3
"""app/approvals.jsx's `formatToolInput` renders the ONE consent surface the
boss reads before authorising a tool call — its own header comment says the
raw payload IS the point, because the row's title is only the requesting
agent's CLAIM about what it wants to do, and the gate exists to catch a
claim that doesn't match the action.

That guarantee assumed painting a value verbatim is the same as showing the
boss the truth. It isn't, for one class of byte: Unicode bidi-control
characters (U+202A-U+202E, U+2066-U+2069). These don't change what a string
IS, only the order a renderer PAINTS it in. A command carrying a
RIGHT-TO-LEFT OVERRIDE (U+202E) can display with its tail reordered in
front of its head -- the well-documented "trojan source" trick used in the
wild to disguise `evil.exe` as something reading like `evil txt.exe`
(actually `evil` + RLO + `exe.txt`, painted in reverse after the override).

Before this fix, formatToolInput passed such bytes straight through into
the approval box: the string the boss's browser PAINTS and the string the
CLI actually EXECUTES could diverge, exactly the gap the file's own
docstring says this gate exists to close ("the action has to be visible
next to it"). A single-key `command` value containing an embedded RLO is
the sharpest case -- it renders bare (no `command:` label ahead of it to
anchor the eye), so the reordering has nothing else on the line to give it
away.

The fix escapes bidi-control code points to a literal `\\uXXXX` sequence
rather than stripping them -- nothing about the payload disappears (same
"never silently hide the tail" rule the cap/truncation code already
follows), only their power to reorder how the line reads.

Run: python3 scripts/test_approval_box_neutralizes_bidi_override_spoofing.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app' / 'approvals.jsx'

FAILS = []


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


# A command whose real bytes are entirely innocuous ("cat notes.txt") but
# which embeds a RIGHT-TO-LEFT OVERRIDE so a renderer paints the tail
# ahead of the override point -- the classic filename/command spoof.
CASES = r'''
const R = {};

const rlo = '‮';
const pdf = '‬';
const spoofed = 'cat notes' + rlo + 'txt.exe' + pdf;   // reads "cat notesexe.txt" painted
R.spoofedOut = formatToolInput({ command: spoofed });

// A plain command with none of these code points must render byte-for-byte
// unchanged -- this fix must not touch ordinary payloads.
R.plainOut = formatToolInput({ command: 'ls -la' });

// Multi-key case: the value still keeps its label and its non-bidi content,
// just with the control code point neutralised.
R.labelledOut = formatToolInput({ file_path: '/etc/hosts', note: 'safe' + rlo + 'x' });

console.log(JSON.stringify(R));
'''


def main():
    print('approval box — bidi-override spoofing is neutralised, not painted verbatim')
    if not shutil.which('node'):
        print('  SKIP  node not available')
        return 0
    out = run_js(CASES)

    check('a RIGHT-TO-LEFT OVERRIDE is never handed to the renderer raw',
          '‮' not in out['spoofedOut'],
          f'the approval box still contains U+202E — {out["spoofedOut"]!r} would '
          'be painted in a different order than its actual bytes, which is the '
          'exact gap the consent gate exists to close')
    check('...nor its POP DIRECTIONAL FORMATTING partner',
          '‬' not in out['spoofedOut'], repr(out['spoofedOut']))
    check('...the control point is escaped visibly (\\u202E), not silently dropped '
          '— nothing about the payload disappears, same rule the truncation code '
          'already follows',
          '\\u202E' in out['spoofedOut'], repr(out['spoofedOut']))
    check('...and every real character around it survives untouched',
          out['spoofedOut'].startswith('cat notes') and 'txt.exe' in out['spoofedOut'],
          repr(out['spoofedOut']))

    check('an ordinary command with no bidi controls is untouched, byte for byte',
          out['plainOut'] == 'ls -la', repr(out['plainOut']))

    check('a labelled multi-arg value is neutralised the same way',
          '‮' not in out['labelledOut'] and '\\u202E' in out['labelledOut'],
          repr(out['labelledOut']))
    check('...and keeps its label and surrounding text',
          out['labelledOut'].startswith('file_path: /etc/hosts\nnote: safe'),
          repr(out['labelledOut']))

    print()
    if FAILS:
        print(f'approval box bidi guard: {len(FAILS)} failure(s)')
        return 1
    print('approval box bidi guard: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
