"""A coworker pinned to a key-based brain, in an office with no key, runs on the shared brain.

Found 2026-11-20 on ai.cafreso.com: Kip (Deep Research) was pinned to Claude through the
Anthropic API. The browser had no Anthropic key, so the boss's request failed with
"No Anthropic API key", even though the front desk was answering on the shared Cafreso GPU
in the same office.

`effectiveModel` now picks the brain that will really answer:
  - pinned to anthropic or google, no key, shared brain up -> shared brain, plus a note that says so
  - a key is connected -> unchanged
  - no shared brain -> unchanged (the old, explanatory error still fires)
and agentStream and ceoStream apply it BEFORE choosing the tool format, because the shared
brain isn't the pinned one.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENT = (ROOT / 'claude-client.jsx').read_text(encoding='utf-8')
RUNTIME = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
failures = 0


def check(label, ok, why=''):
    global failures
    print(('  ok    ' if ok else '  FAIL  ') + label + ('' if ok else f'  ({why})'))
    if not ok:
        failures += 1


def lift(src, name):
    m = re.search(r'^function ' + name + r'\(.*?^\}', src, re.S | re.M)
    assert m, f'{name} not found'
    return m.group(0)


harness = '\n'.join([
    lift(CLIENT, 'parseModelId'),
    lift(CLIENT, 'effectiveModel'),
    """
let _settings = {}; let _managedBrain = null;
const cases = JSON.parse(process.argv[1]);
const out = cases.map(([settings, brain, id]) => { _settings = settings; _managedBrain = brain; return effectiveModel(id); });
console.log(JSON.stringify(out));
""",
])
GPU = {'model': 'gemma-4-31b', 'provider': 'cafreso'}
cases = [
    [{'provider': 'hermes'}, GPU, 'anthropic:claude-sonnet-5-5'],                       # 0 no key, shared up
    [{'provider': 'hermes', 'anthropicKey': 'k'}, GPU, 'anthropic:claude-sonnet-5-5'],  # 1 key connected
    [{'provider': 'hermes'}, False, 'anthropic:claude-sonnet-5-5'],                     # 2 no shared brain
    [{'provider': 'anthropic'}, GPU, None],                                             # 3 default provider w/o key
    [{'provider': 'hermes'}, GPU, 'google:gemini-2.5-pro'],                             # 4 google, no key
    [{'provider': 'hermes'}, GPU, 'cafresohq:sonnet'],                                  # 5 not key-based
    [{'provider': 'hermes', 'hermesModel': 'my-agent'}, GPU, 'anthropic:x'],            # 6 custom hermes model
]
res = json.loads(subprocess.run(['node', '-e', harness, json.dumps(cases)], capture_output=True, text=True, check=True).stdout)

print('effectiveModel')
check('no key + shared brain -> runs on the shared brain', res[0]['model'] == 'hermes:hermes-agent', res[0])
check('...and says which brain it wanted and which ran', 'Claude (Anthropic API)' in res[0]['note'] and 'gemma-4-31b' in res[0]['note'], res[0])
check('...and how to get the wanted one back', 'Settings → Connections' in res[0]['note'], res[0])
check('a connected key changes nothing', res[1] == {'model': 'anthropic:claude-sonnet-5-5', 'note': ''}, res[1])
check('no shared brain changes nothing (the old error still explains)', res[2]['note'] == '' and res[2]['model'] == 'anthropic:claude-sonnet-5-5', res[2])
check('an office defaulting to Anthropic with no key falls back too', res[3]['model'] == 'hermes:hermes-agent', res[3])
check('Gemini via a Google key falls back the same way', 'Gemini (Google API)' in res[4]['note'], res[4])
check('brains that need no browser key are left alone', res[5] == {'model': 'cafresohq:sonnet', 'note': ''}, res[5])
check("the office's own Hermes model is used for the fallback", res[6]['model'] == 'hermes:my-agent', res[6])

print('the streams use it before choosing a tool format')
agent_body = RUNTIME[RUNTIME.index('async function agentStream('):]
ceo_body = RUNTIME[RUNTIME.index('async function ceoStream('):]
check('agentStream applies effectiveModel before useJson',
      0 <= agent_body.find('effectiveModel(agent.model)') < agent_body.find('const useJson'))
check('ceoStream applies effectiveModel before useJsonCeo',
      0 <= ceo_body.find('effectiveModel(model)') < ceo_body.find('const useJsonCeo'))
check('both show the note out of band (onHint), not in the reply text',
      agent_body.count('onHint(eff.note)') == 1 and ceo_body.count('onHint(eff.note)') >= 1)
check('the client exports it', 'parseModelId, effectiveModel,' in CLIENT)

print('\nall checks passed' if not failures else f'\n{failures} check(s) failed')
sys.exit(1 if failures else 0)
