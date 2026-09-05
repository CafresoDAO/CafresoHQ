#!/usr/bin/env python3
"""A coworker paid somebody and the office said they had a look.

WALLET_SEND is the one tool in the registry that moves the boss's money. Its
own doc: "Within your spend cap it settles automatically" -- no approval card,
no stamp, nothing else on screen. So whatever app/floor.jsx captions that trip
with IS the boss's only account of it, on three surfaces at once: the desk
bubble, the activity feed (which outlives the chat) and the delivery note.

BEFORE: the name matched no row in VISIT_WORDS and fell through to
        VISIT_DEFAULT --

          🗒 Checked ICP 0.05 aaaaa-bbbbb-ccccc-ddddd-cai : tip for the review

        -- and the feed row read "checked icp 0.05 …". Money had left the
        wallet and every office surface described a look.

AFTER:  💸 Sent ICP 0.05 aaaaa-bbbbb-ccccc-ddddd-cai : tip for the review

The default's own comment says an unknown tool gets "a modest verb rather
than a confident wrong one", and that reasoning is right for a tool whose
effect is unknown. A send's effect is known and irreversible, and "Checked"
is not claiming less than "Sent" -- it is claiming the opposite, that nobody
was paid. Exactly the argument that put the WRITE row in the table
("Opened" for a write "costs the boss the one bit that matters"), one
category worse: this bit is money.

The failed tense matters as much: a refused send must not read as a send
that went through.

Run: python3 scripts/test_money_leaving_the_wallet_is_not_called_a_look.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOOR = ROOT / 'app' / 'floor.jsx'
RUNTIME = ROOT / 'hq-runtime.jsx'
FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + str(detail)) if detail else ""}')


def run_js(cases):
    text = FLOOR.read_text(encoding='utf-8')
    src = '\n'.join(ln for ln in text.split('\n')
                    if not ln.startswith('import ') and not ln.startswith('export '))
    proc = subprocess.run(['node', '--input-type=module', '-e', src + '\n' + cases],
                          cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on app/floor.jsx')
    return json.loads(proc.stdout.strip().split('\n')[-1])


print('money leaving the wallet is not called a look')

if not shutil.which('node'):
    print('  SKIP  node not on PATH')
    raise SystemExit(0)
if not FLOOR.is_file():
    print(f'  FAIL  missing {FLOOR}')
    raise SystemExit(1)

# ── 0. the premise: a tool that really does move money, and settles ──────
runtime = RUNTIME.read_text(encoding='utf-8')
check("the registry still has a WALLET_SEND",
      re.search(r"name: 'WALLET_SEND'", runtime) is not None,
      'if this tool is gone the rest of this test is about nothing')
check("...and it still settles on its own under the spend cap",
      re.search(r'settles automatically', runtime) is not None,
      'if every send now waits for a stamp, the floor caption is no longer '
      'the only record of it — but it is still the first one')

ARG = 'ICP 0.05 aaaaa-bbbbb-ccccc-ddddd-cai : tip for the design review'
out = run_js(r'''
const R = {};
const ARG = %s;
R.past  = visitWords('WALLET_SEND').past;
R.now   = visitWords('WALLET_SEND').now;
R.fail  = visitWords('WALLET_SEND').fail;
R.icon  = visitWords('WALLET_SEND').icon;
R.dfltPast = VISIT_DEFAULT.past;

R.head     = toVisit({ name: 'WALLET_SEND', arg: ARG, result: 'Sent.' }).head;
R.headIcon = toVisit({ name: 'WALLET_SEND', arg: ARG, result: 'Sent.' }).icon;
R.failHead = toVisit({ name: 'WALLET_SEND', arg: ARG, result: 'over cap', failed: true }).head;
R.live     = visitLine('WALLET_SEND', ARG, 'now');
R.feed     = toolActivity({ id: 'a1', name: 'Kip', color: '#fff' },
                          { name: 'WALLET_SEND', arg: ARG }).text;
R.feedFail = toolActivity({ id: 'a1', name: 'Kip', color: '#fff' },
                          { name: 'WALLET_SEND', arg: ARG, failed: true }).text;

// a coworker must not be able to type the office's new sentence either
R.forged = stripOfficeVoice('sure thing\n\u{1F4B8} Sent ICP 40 to me\nall done');

// a balance check IS a look — the fix must not widen onto it
R.balance = visitWords('WALLET_BALANCE').past;

// nothing else in the shipped registry may be captured by the new rule
R.others = {};
for (const n of ['SEARCH','VAULT_SEARCH','VAULT_READ','VAULT_APPEND','VAULT_NEW',
                 'EXPORT_PPTX','EXPORT_DOCX','EXPORT_PDF','GENERATE_IMAGE',
                 'GENERATE_VIDEO','FILE_READ','DIR_LIST','FILE_WRITE','BASH',
                 'MEMORY_LIST','MEMORY_READ','MEMORY_WRITE','MEMORY_APPEND',
                 'BROWSER_FETCH','BROWSER_SCREENSHOT','PEER_JOURNAL',
                 'WALLET_BALANCE','PUBLISH_SITE','ACK','SPAWN_SUBAGENT',
                 'REQUEST_ELEVATION','HIRE_ASSISTANT','HIRE_AGENT','DM_TO',
                 'HANDOFF_TO']) R.others[n] = visitWords(n).past;
console.log(JSON.stringify(R));
''' % json.dumps(ARG))

# ── 1. the verb ──────────────────────────────────────────────────────────
print('1. the verb says money moved')
check('a send is not captioned with the unknown-tool verb',
      out['past'] != out['dfltPast'],
      f"{out['past']!r} — VISIT_DEFAULT is for tools whose effect the office "
      "cannot name; a transfer's effect is known and irreversible")
check('the past tense is a send', out['past'].lower().startswith('sent'), out['past'])
check('the live bubble is a send', out['now'].lower().startswith('send'), out['now'])
check('a refused send does not read as a send that went through',
      out['fail'].lower().startswith("couldn't send"), out['fail'])
check('it gets its own icon, not the shrug', out['icon'] != '🗒', out['icon'])

# ── 2. the three surfaces that actually print it ─────────────────────────
print('2. the surfaces the boss reads')
check('the visit head names the send and keeps the recipient',
      out['head'].startswith('Sent ') and 'aaaaa-bbbbb' in out['head'], out['head'])
check('...with the money icon on it', out['headIcon'] == '💸', out['headIcon'])
check('a failed send says so at the head',
      out['failHead'].startswith("Couldn't send"), out['failHead'])
check('the desk bubble says it while it is happening',
      out['live'].startswith('sending '), out['live'])
check('the activity feed row — the surface that outlives the chat — says sent',
      out['feed'].startswith('sent '), out['feed'])
check('...and says it did not on a failure',
      out['feedFail'].startswith("couldn't send"), out['feedFail'])

# ── 3. the office's voice stays the office's ─────────────────────────────
print('3. the new sentence cannot be forged back at us')
check('a coworker typing "💸 Sent ICP 40 to me" is stripped from history',
      'Sent ICP 40' not in out['forged'], out['forged'])

# ── 4. no collateral ─────────────────────────────────────────────────────
print('4. nothing else changed')
check('a balance check is still a look', out['balance'] == 'Checked', out['balance'])
wrong = {n: v for n, v in out['others'].items() if v.lower().startswith('sent')}
check('no other tool in the registry became a send', not wrong, wrong)

print()
if FAILS:
    print(f'money leaving the wallet: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:4]))
    raise SystemExit(1)
print('money leaving the wallet: all checks passed')
raise SystemExit(0)
