#!/usr/bin/env python3
"""The cast (app/cast.jsx) — pure-function suite.

§2's card rules are product promises: the vendor is a chip, never the
identity (and NEVER a wrong brand — unknown vendors get no chip); the four
bars are coarse honest class judgements bounded 1..4; an earned XP affinity
always beats the class hunch. Same node-under-Python pattern as the other
jsx suites.
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
    print('the cast — coworker card helpers')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1

    out = run_js(r'''
const R = {};
const A = (model) => ({ model });
// ── poweredBy — chip, never identity, never a wrong brand ──────────────
R.vOllama     = poweredBy(A('ollama:llama3.1:latest'));
R.vLmStudio   = poweredBy(A('lmstudio:qwen2.5'));
R.vOpenRouter = poweredBy(A('openrouter:meta-llama/llama-3.1-8b'));
R.vGroq       = poweredBy(A('groq:llama-3.3-70b'));
R.vClaude     = poweredBy(A('sonnet'));
R.vClaudeCode = poweredBy(A('claude-code'));
R.vCodex      = poweredBy(A('codex'));
R.vGemini     = poweredBy(A('gemini-api:gemini-2.5-pro'));
R.vHermes     = poweredBy(A('hermes-4-405b'));
R.vUnknown    = poweredBy(A('mystery-model-9000'));
R.vEmpty      = poweredBy(A(''));
R.vNull       = poweredBy(null);
// ── statBars — 1..4, honest classes, prefix-stripped ────────────────────
const all = [];
for (const m of ['fable', 'claude-opus-5', 'sonnet', 'haiku', 'codex', 'claude-code',
                 'gemini-api:gemini-2.5-flash', 'ollama:llama3.1:latest',
                 'openrouter:qwen/qwen-2.5-72b', 'mystery-model-9000', '', null]) {
  const b = statBars(A(m));
  all.push([b.speed, b.depth, b.code, b.cost].every(v => v >= 1 && v <= 4) && typeof b.tag === 'string' && b.tag.length > 0);
}
R.allBounded   = all.every(Boolean);
R.localCheap   = statBars(A('ollama:llama3.1:latest')).cost;           // 4 — free-local
R.opusDeep     = statBars(A('claude-opus-5')).depth;                   // 4
R.haikuFast    = statBars(A('haiku')).speed;                           // 4
R.prefixStrip  = statBars(A('openrouter:meta-llama/llama-3.1-8b')).cost; // llama class through the prefix
R.flashIsFast  = statBars(A('gemini-api:gemini-2.5-flash')).speed;     // 'flash' → quick class
R.unknownTag   = statBars(A('mystery-model-9000')).tag;
// ── specialtyTag — earned beats hunch ───────────────────────────────────
R.earnedWins   = specialtyTag(A('ollama:llama3.1'), '12 research briefs');
R.hunchDefault = specialtyTag(A('ollama:llama3.1'), '');
// ── brainName — §6: no raw model ids on a card ─────────────────────────
R.bnPrefix   = brainName(A('openrouter:google/gemma-3-27b-it'));
R.bnLocal    = brainName(A('ollama:llama-3.3-70b-instruct'));
R.bnDated    = brainName(A('claude-haiku-4-5-20251001'));
R.bnGpt      = brainName(A('gpt-5'));
R.bnFree     = brainName(A('openrouter:qwen/qwen-2.5-7b-instruct:free'));
R.bnNone     = brainName(A(''));
R.bnMissing  = brainName({});
R.bnNoColon  = brainName(A('mystery-model-9000'));
// Formatting only — every word of the id's identity must survive.
R.bnKeepsAll = ['gemma','3','27']
  .every(t => brainName(A('openrouter:google/gemma-3-27b-it')).toLowerCase().includes(t));
R.bnNoPrefixLeak = ['openrouter','ollama','gemini-api','google/','meta-llama/']
  .every(p => !brainName(A('openrouter:google/gemma-3-27b-it')).toLowerCase().includes(p)
           && !brainName(A('ollama:llama-3.3-70b-instruct')).toLowerCase().includes(p));
console.log(JSON.stringify(R));
''')

    check('ollama chips as your hardware', out['vOllama'] == 'your hardware')
    check('lmstudio chips as your hardware', out['vLmStudio'] == 'your hardware')
    check('openrouter chips as OpenRouter', out['vOpenRouter'] == 'OpenRouter')
    check('groq chips as Groq', out['vGroq'] == 'Groq')
    check('sonnet chips as Claude', out['vClaude'] == 'Claude')
    check('claude-code chips as Claude', out['vClaudeCode'] == 'Claude')
    check('codex chips as OpenAI', out['vCodex'] == 'OpenAI')
    check('gemini chips as Google', out['vGemini'] == 'Google')
    check('hermes chips as Nous Research', out['vHermes'] == 'Nous Research')
    check('unknown model gets NO chip (never a wrong brand)', out['vUnknown'] is None)
    check('empty model gets no chip', out['vEmpty'] is None)
    check('null agent tolerated', out['vNull'] is None)

    check('every class is bounded 1..4 with a tagline', out['allBounded'])
    check('local models read as cheap (cost 4)', out['localCheap'] == 4)
    check('opus-class reads deep (depth 4)', out['opusDeep'] == 4)
    check('haiku-class reads fast (speed 4)', out['haikuFast'] == 4)
    check('class resolves through a driver prefix', out['prefixStrip'] == 4,
          str(out['prefixStrip']))
    check('flash resolves to the quick class', out['flashIsFast'] == 4)
    check('unknown model falls back to the generalist row',
          out['unknownTag'] == 'steady generalist', out['unknownTag'])

    check('an earned affinity beats the class hunch',
          out['earnedWins'] == '12 research briefs')
    check('no affinity yet → the class tagline',
          out['hunchDefault'] == 'cheap and tireless')

    # §6: the card shows a NAME, never the raw id. Formatting only — the
    # identity the id carries must survive, the plumbing around it must not.
    check('routing prefix + org path are dropped',
          out['bnPrefix'] == 'Gemma 3 27B', out['bnPrefix'])
    check('local model keeps its size marker',
          out['bnLocal'] == 'Llama 3.3 70B', out['bnLocal'])
    check('trailing date stamp is dropped',
          out['bnDated'] == 'Claude Haiku 4 5', out['bnDated'])
    check('gpt keeps its casing', out['bnGpt'] == 'GPT 5', out['bnGpt'])
    check(':free tier suffix is dropped',
          out['bnFree'] == 'Qwen 2.5 7B', out['bnFree'])
    check('no model set says so, never invents one',
          out['bnNone'] == 'not set yet' and out['bnMissing'] == 'not set yet',
          f"{out['bnNone']} / {out['bnMissing']}")
    check('an unrecognised id still yields a name',
          out['bnNoColon'] == 'Mystery Model 9000', out['bnNoColon'])
    check('every identity token of the id survives', out['bnKeepsAll'])
    check('no routing prefix or org path ever leaks to the card',
          out['bnNoPrefixLeak'])

    print()
    if FAILS:
        print(f'the cast: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('the cast: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
