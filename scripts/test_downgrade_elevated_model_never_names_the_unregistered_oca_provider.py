#!/usr/bin/env python3
"""downgradeElevatedModel() named a provider that does not exist.

`app/agents.jsx`'s `downgradeElevatedModel` exists to keep a non-elevated
helper (a spawned sub-agent, or an assistant hired off a senior) off an
elevation-only brain. Sub-agents and assistants inherit their spawner's
model, and when that model lives under `cafresohq:` or `codex:` — both
elevation-only providers — the upstream `stream()` call refuses the
request ("CafresoHQ provider requires the agent to be elevated"). Rather
than fail, `downgradeElevatedModel` is supposed to swap in the closest
non-elevated equivalent and report the swap so the boss sees a system
chat note (app.jsx: "That helper is on <brain> rather than <brain>...").

For `codex:<tail>` it built `oca:oca/<tail>` and reported that as a clean
swap (`swapped: true`), no settings fallback attempted. But `oca` is not
a provider `claude-client.jsx` knows about anywhere:

  - `parseModelId()`'s prefix table lists hermes, anthropic, lmstudio,
    ollama, claudecode, cafresohq, codex, google, openrouter, groq,
    gemini-api, gemini — no 'oca'. A model id starting "oca:" fails every
    `startsWith` check, so `parseModelId` hands back `{provider: null,
    model: "oca:oca/<tail>"}` — the WHOLE string, unparsed, as the model.
  - `stream()` then falls back to `_settings.provider` (whatever the boss
    has picked globally, e.g. 'anthropic') and sends it the literal string
    "oca:oca/<tail>" as the model id.

So a helper "downgraded" off a codex-elevated model was silently rerouted
to the boss's own default provider carrying a garbage model id, while the
toast confidently reported a clean swap. `brainName()` only strips prefixes
and title-cases what is left — it does not validate the provider exists —
so the chat note read as plausible ("That helper is on Oca Gpt 5.5...")
while the actual request underneath it was headed nowhere real.

Fix: the codex branch no longer invents an unregistered 'oca:' provider.
It leaves `swap` unset, which routes through the settings-based fallback
that already existed a few lines below — the one that only ever names
'anthropic:', 'claudecode:', or bare 'haiku', all of which `stream()`
actually dispatches.

Run: python3 scripts/test_downgrade_elevated_model_never_names_the_unregistered_oca_provider.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('downgradeElevatedModel never names the unregistered oca provider')
    if not shutil.which('node'):
        print('SKIP — node not on PATH')
        return 0

    agents_src = (ROOT / 'app' / 'agents.jsx').read_text(encoding='utf-8')
    client_src = (ROOT / 'claude-client.jsx').read_text(encoding='utf-8')

    fn = agents_src[agents_src.index('function downgradeElevatedModel'):
                     agents_src.index('\n}\n', agents_src.index('function downgradeElevatedModel')) + 2]
    check('downgradeElevatedModel lifts', 'function downgradeElevatedModel' in fn)

    # ── the routing table this function's output has to survive ─────────
    prefix_table = re.search(r"for \(const p of \[(.*?)\]\)", client_src, re.S)
    check('parseModelId prefix table found', bool(prefix_table))
    prefixes = re.findall(r"'([a-z0-9-]+):'", prefix_table.group(1)) if prefix_table else []
    check('claude-client.jsx really has no oca provider (sanity)',
          'oca' not in prefixes, prefixes)

    js = ('const DOWNGRADE = ' + json.dumps(fn) + ';\n'
          + 'const PREFIXES = ' + json.dumps(prefixes) + ';\n'
          + r'''
const mod = new Function(DOWNGRADE
  + ' return { downgradeElevatedModel };')();
const { downgradeElevatedModel } = mod;

function parseModelId(id) {
  if (!id) return { provider: null, model: null };
  for (const p of PREFIXES) {
    if (id.startsWith(p + ':')) return { provider: p, model: id.slice(p.length + 1) };
  }
  return { provider: null, model: id };
}

const settingsWithKey = { anthropicKey: 'sk-test', anthropicModel: 'claude-opus-4-5' };
const settingsNoKey = { claudecodeModel: 'sonnet' };
const settingsBare = {};

const cafresohq = downgradeElevatedModel('cafresohq:sonnet', settingsWithKey);
const codexWithKey = downgradeElevatedModel('codex:gpt-4.1', settingsWithKey);
const codexNoKey = downgradeElevatedModel('codex:gpt-4.1', settingsNoKey);
const codexBare = downgradeElevatedModel('codex:gpt-4.1', settingsBare);
const unelevated = downgradeElevatedModel('anthropic:claude-opus-4-5', settingsWithKey);

console.log(JSON.stringify({
  cafresohq, codexWithKey, codexNoKey, codexBare, unelevated,
  cafresohqRoutes: parseModelId(cafresohq.model).provider,
  codexWithKeyRoutes: parseModelId(codexWithKey.model).provider,
  codexNoKeyRoutes: parseModelId(codexNoKey.model).provider,
  codexBareRoutes: parseModelId(codexBare.model).provider,
}));
''')
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('the lifted function runs', False, p.stderr.strip()[:400])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('cafresohq: still swaps to the real claudecode: provider (unchanged)',
          r['cafresohq']['model'] == 'claudecode:sonnet' and r['cafresohq']['swapped'],
          r['cafresohq'])
    check('cafresohq: swap is routable',
          r['cafresohqRoutes'] == 'claudecode', r['cafresohqRoutes'])

    check('codex: never names the unregistered oca provider',
          not r['codexWithKey']['model'].startswith('oca'), r['codexWithKey'])
    check('codex: swaps to the boss\'s anthropic default when a key is set',
          r['codexWithKey']['model'] == 'anthropic:claude-opus-4-5', r['codexWithKey'])
    check('codex: with-key swap is routable',
          r['codexWithKeyRoutes'] == 'anthropic', r['codexWithKeyRoutes'])

    check('codex: falls back to the configured claudecode model with no anthropic key',
          r['codexNoKey']['model'] == 'claudecode:sonnet', r['codexNoKey'])
    check('codex: no-key swap is routable',
          r['codexNoKeyRoutes'] == 'claudecode', r['codexNoKeyRoutes'])

    check('codex: falls all the way back to bare haiku with no settings at all',
          r['codexBare']['model'] == 'haiku', r['codexBare'])
    check('codex: bare-haiku swap needs no provider prefix to route',
          r['codexBareRoutes'] is None, r['codexBareRoutes'])

    check('codex swaps still report swapped:true and a reason',
          r['codexWithKey']['swapped'] and 'Codex' in r['codexWithKey']['why'],
          r['codexWithKey'])

    check('an already non-elevated model is left alone',
          r['unelevated'] == {'model': 'anthropic:claude-opus-4-5', 'swapped': False, 'why': ''},
          r['unelevated'])

    if FAILS:
        print(f'FAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS))
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
