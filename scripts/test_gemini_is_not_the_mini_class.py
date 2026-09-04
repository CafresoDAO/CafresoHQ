#!/usr/bin/env python3
"""'gemini' contains 'mini' (app/cast.jsx CAST_CLASSES).

The small-and-quick row keyed on the bare substring `mini`, and it sits
ABOVE the /gemini/ row. Since every Google model id containing "gemini"
also contains "mini", the quick row won every time and the /gemini/ row —
'strong all-rounder', 3/3/3/2 — was unreachable dead code.

What the boss saw: a `gemini:gemini-2.5-pro` coworker (the brain
CANDIDATE_BRAINS hands the whole candidate shelf on a Gemini-CLI office)
introducing itself as "quick with the small stuff" with DEPTH 2 and CODE 2
bars — Google's deep-work model sold as the small one, on every card of
that office's first screen.

§2 binds these bars: "honest and RELATIVE, not benchmark cosplay". A class
judgement produced by an accidental substring match is neither.

Runs app/cast.jsx verbatim under node, same harness as scripts/test_cast.py.
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
    print('gemini is not the mini class')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1

    out = run_js(r'''
const R = {};
const A = (model) => ({ model });
const bars = (m) => { const b = statBars(A(m)); return [b.speed, b.depth, b.code, b.cost, b.tag]; };

// The exact id CANDIDATE_BRAINS hands a Gemini-CLI office's whole shelf.
R.shelfBrain = (CANDIDATE_BRAINS.find(b => b.id === 'gemini') || {}).model || '';
R.proCli     = bars('gemini:gemini-2.5-pro');
R.proApi     = bars('gemini-api:gemini-2.5-pro');
R.proBare    = bars('gemini-1.5-pro');

// The /gemini/ row must be REACHABLE — i.e. some model actually lands on it.
R.geminiRowUsed = CAST_CLASSES.some(c => c.re.test('gemini-2.5-pro'));
R.geminiRowIdx  = CAST_CLASSES.findIndex(c => c.re.test('gemini-2.5-pro'));
R.geminiRowSrc  = String((CAST_CLASSES[CAST_CLASSES.findIndex(c => c.re.test('gemini-2.5-pro'))] || {}).re);

// Real members of the small-and-quick class must NOT be lost to the fix.
R.gpt4oMini  = bars('codex:gpt-4o-mini');
R.o4MiniHigh = bars('o4-mini-high');
R.phiMini    = bars('ollama:phi-4-mini-instruct');
R.haiku      = bars('claude-haiku-4-5');
R.nano       = bars('lmstudio:nvidia/nemotron-3-nano-4b');
// flash is its own word and stays quick — the right answer for it.
R.flash      = bars('gemini-api:gemini-2.5-flash');

console.log(JSON.stringify(R));
''')

    QUICK = 'quick with the small stuff'
    ROUND = 'strong all-rounder'

    check("the Gemini-CLI shelf brain is a 'gemini:' pro id",
          out['shelfBrain'].startswith('gemini:'), out['shelfBrain'])

    # The bug, stated three ways it reaches a card.
    check('gemini-2.5-pro is NOT filed as the small-and-quick class',
          out['proCli'][4] != QUICK, str(out['proCli']))
    check('gemini-2.5-pro reads as the all-rounder',
          out['proCli'][4] == ROUND, str(out['proCli']))
    check('a Gemini pro card does not show DEPTH 2',
          out['proCli'][1] == 3, str(out['proCli'][1]))
    check('a Gemini pro card does not show CODE 2',
          out['proCli'][2] == 3, str(out['proCli'][2]))
    check('the gemini-api: prefix lands on the same class',
          out['proApi'][4] == ROUND, str(out['proApi']))
    check('a bare gemini id lands on the same class',
          out['proBare'][4] == ROUND, str(out['proBare']))

    # The row itself must not be dead code.
    check('the /gemini/ row in CAST_CLASSES is reachable',
          out['geminiRowUsed'] and 'gemini' in out['geminiRowSrc'],
          f"gemini-2.5-pro matched row {out['geminiRowIdx']}: {out['geminiRowSrc']}")

    # And the fix must not evict the row's real members.
    check('gpt-4o-mini stays quick', out['gpt4oMini'][4] == QUICK, str(out['gpt4oMini']))
    check('o4-mini-high stays quick', out['o4MiniHigh'][4] == QUICK, str(out['o4MiniHigh']))
    check('phi-4-mini-instruct stays quick', out['phiMini'][4] == QUICK, str(out['phiMini']))
    check('haiku stays quick', out['haiku'][4] == QUICK, str(out['haiku']))
    check('nano stays quick', out['nano'][4] == QUICK, str(out['nano']))
    check('gemini-2.5-flash stays quick (on "flash", not on "mini")',
          out['flash'][4] == QUICK and out['flash'][0] == 4, str(out['flash']))

    print(f'\n{"FAIL" if FAILS else "PASS"} — {len(FAILS)} failing')
    return 1 if FAILS else 0


if __name__ == '__main__':
    raise SystemExit(main())
