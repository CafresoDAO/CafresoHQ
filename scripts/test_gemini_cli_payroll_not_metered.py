#!/usr/bin/env python3
"""payrollLabel (app/cast.jsx) must classify the Gemini CLI as a subscription
hire, not a metered one.

modals/hire.jsx's FRONT_DESK entry for 'gemini' is the Gemini CLI — a
coding-agent driver hired off a Google sign-in ("We found your Google sign-in
on this machine."), pinned to model 'gemini:gemini-2.5-pro'. That is the same
category as Claude Code, Codex and Hermes: a flat-plan subscription with no
per-word component, which payrollLabel's own doc comment calls "subscription
— a CLI hire billed by a flat plan; per-job payroll is not a thing that
exists, so we say so."

PAYROLL_PLAN, the regex payrollLabel keys the "on your plan" branch on, only
listed claudecode|codex|cafresohq|hermes — 'gemini' was missing. So a Gemini
CLI hire's Payroll stat read "—" with the tooltip "Billed per word by the
provider. No rate is configured here" — the exact invented-uncertainty lie
this function exists to stop (§6: "Payroll shows real numbers"), on the one
CLI driver whose billing is a subscription like its three siblings.

Must not regress the metered 'gemini-api:' prefix (the real per-token Gemini
API key), which has to keep reading as unrated/metered.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app' / 'cast.jsx'

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


def main():
    print('Gemini CLI payroll — a subscription hire, not a metered one')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1

    out = run_js(r'''
const R = {};
// The exact model id FRONT_DESK.gemini in modals/hire.jsx pins the Gemini
// CLI candidate to.
R.geminiCli      = payrollLabel({ model: 'gemini:gemini-2.5-pro' });
// Its three subscription siblings — must stay "on your plan" too.
R.claudeCode     = payrollLabel({ model: 'claudecode:sonnet' }).text;
R.codex          = payrollLabel({ model: 'codex:gpt-5' }).text;
R.hermes         = payrollLabel({ model: 'hermes:hermes-agent' }).text;
// The real metered Gemini API key must NOT be swept up by the fix.
R.geminiApi      = payrollLabel({ model: 'gemini-api:gemini-2.5-flash' }).text;
console.log(JSON.stringify(R));
''')

    check('the Gemini CLI reads as on-your-plan, not a dollar mystery',
          out['geminiCli']['text'] == 'on your plan', repr(out['geminiCli']))
    check('...and its tooltip never claims per-word billing',
          'Billed per word' not in out['geminiCli']['title'], out['geminiCli']['title'])
    check('its subscription siblings are unaffected',
          out['claudeCode'] == 'on your plan' and out['codex'] == 'on your plan'
          and out['hermes'] == 'on your plan',
          f"{out['claudeCode']} / {out['codex']} / {out['hermes']}")
    check('the metered Gemini API key still shows no invented rate',
          out['geminiApi'] == '—', out['geminiApi'])

    print()
    if FAILS:
        print(f'Gemini CLI payroll: {len(FAILS)} failure(s)')
        return 1
    print('Gemini CLI payroll: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
