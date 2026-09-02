#!/usr/bin/env python3
"""Approval payloads (app/approvals.jsx) — pure-function suite.

An approval row is the one CONSENT surface in the app, so its honesty rules
run opposite to everything else: the raw payload is the point, not noise to
translate away. The row's title is the requesting agent's own summary of its
request — a claim — and this gate exists to catch a claim that doesn't match
the action.

The checks below are release-blocking rather than cosmetic. Each one pins a
property that, if it regressed, would let a boss approve something other
than what they were shown:

  - values go through VERBATIM (no paraphrase, no normalisation)
  - the END of long input survives (that is where something buried would be)
  - truncation, when it must happen, is always MARKED

Same node-under-Python pattern as the other jsx suites.
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


CASES = r'''
const R = {};

// The literal case that motivated this: a destructive command whose author
// summarised it as "Clean the build directory".
R.bashBare      = formatToolInput({ command: 'rm -rf build/' });

// Multiple args: every line keeps its label, or "/etc/hosts" and its
// contents become indistinguishable from each other.
R.writeLabelled = formatToolInput({ file_path: '/etc/hosts', content: '127.0.0.1 evil.example.com' });

// Decision-relevant keys lead regardless of object key order.
R.leadOrder     = formatToolInput({ verbose: true, command: 'ls -la' });
R.leadFirstLine = R.leadOrder.split('\n')[0];

// THE security property: a long value must keep its tail. A first cut capped
// at 400 chars and silently ate exactly this.
const buried = 'echo start; ' + 'x'.repeat(500) + '; rm -rf /important';
R.buriedOut     = formatToolInput({ command: buried });
R.buriedKeptTail = R.buriedOut.indexOf('rm -rf /important') !== -1;
R.buriedVerbatim = R.buriedOut === buried;

// Past the cap, output is truncated but SAYS so — never silently.
const huge = 'y'.repeat(APPROVAL_VALUE_CAP + 50);
R.hugeOut       = formatToolInput({ command: huge });
R.hugeMarked    = /…\(\d+ chars omitted\)…/.test(R.hugeOut);
R.hugeShorter   = R.hugeOut.length < huge.length + 30;

// THE property the cap itself must not break: a dangerous tail buried past
// the 8000-char cap (not just past the old 400-char one) must still
// survive — this is the exact bug the cap-raise comment above describes,
// just re-triggered at the new threshold if truncation ever slices the
// tail off instead of the middle.
const buriedPastCap = 'echo start; ' + 'x'.repeat(APPROVAL_VALUE_CAP + 500) + '; rm -rf /important';
R.buriedPastCapOut      = formatToolInput({ command: buriedPastCap });
R.buriedPastCapKeptTail = R.buriedPastCapOut.indexOf('rm -rf /important') !== -1;
R.buriedPastCapKeptHead = R.buriedPastCapOut.indexOf('echo start;') !== -1;
R.buriedPastCapMarked   = /…\(\d+ chars omitted\)…/.test(R.buriedPastCapOut);

// Nested objects survive as real JSON rather than "[object Object]".
R.nested        = formatToolInput({ tool: 'x', opts: { deep: [1, 2] } });
R.nestedNoJunk  = R.nested.indexOf('[object Object]') === -1 && R.nested.indexOf('"deep"') !== -1;

// Degenerate inputs return '' so the row simply omits the box — never the
// string "undefined" or "null" presented as if it were the command.
R.emptyObj      = formatToolInput({});
R.nullIn        = formatToolInput(null);
R.undefIn       = formatToolInput(undefined);
R.stringIn      = formatToolInput('rm -rf /');
R.arrayIn       = formatToolInput(['a']);

// Falsy and null values still render honestly rather than vanishing.
R.falsyVals     = formatToolInput({ force: false, target: null, count: 0 });

console.log(JSON.stringify(R));
'''


def main():
    print('approval payloads — the consent surface')
    if not shutil.which('node'):
        print('  SKIP  node not available')
        return 0
    out = run_js(CASES)

    check('a lone command renders bare and verbatim',
          out['bashBare'] == 'rm -rf build/', repr(out['bashBare']))
    check('multiple args each keep their label',
          out['writeLabelled'] == 'file_path: /etc/hosts\ncontent: 127.0.0.1 evil.example.com',
          repr(out['writeLabelled']))
    check('decision-relevant keys lead regardless of key order',
          out['leadFirstLine'] == 'command: ls -la', repr(out['leadFirstLine']))

    check('a long command KEEPS ITS TAIL (the 400-cap bug)',
          out['buriedKeptTail'])
    check('...and is passed through verbatim, unaltered',
          out['buriedVerbatim'])

    check('past the cap it truncates but says so',
          out['hugeMarked'], repr(out['hugeOut'][-40:]))
    check('...and actually shortens rather than only labelling',
          out['hugeShorter'])

    check('a dangerous tail buried PAST the 8000-char cap still survives '
          '— slicing off the tail here would silently recreate the exact '
          'bug the cap-raise comment describes, just at a bigger threshold',
          out['buriedPastCapKeptTail'], repr(out['buriedPastCapOut'][-60:]))
    check('...and the head survives too — the middle is what gets elided, '
          'not either end',
          out['buriedPastCapKeptHead'], repr(out['buriedPastCapOut'][:60]))
    check('...and the elision is marked, never silent',
          out['buriedPastCapMarked'])

    check('nested values render as JSON, never [object Object]',
          out['nestedNoJunk'], repr(out['nested']))

    check('empty object yields no detail box', out['emptyObj'] == '')
    check('null input yields no detail box', out['nullIn'] == '')
    check('undefined input yields no detail box', out['undefIn'] == '')
    check('a bare string is not mistaken for args', out['stringIn'] == '')
    check('an array is not mistaken for args', out['arrayIn'] == '')

    check('false / null / 0 values still render honestly',
          out['falsyVals'] == 'force: false\ntarget: null\ncount: 0',
          repr(out['falsyVals']))

    print()
    if FAILS:
        print(f'approval payloads: {len(FAILS)} failure(s)')
        return 1
    print('approval payloads: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
