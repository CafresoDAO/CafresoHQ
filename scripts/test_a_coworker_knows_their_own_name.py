#!/usr/bin/env python3
"""A coworker hired through the form was never told who they were.

Measured in the meeting room, two coworkers, one question: "Each of you:
name ONE risk ... and say who you are."

    Llama:  "I'm Llama, Generalist."
    Nova:   "I'm Nova, Web Specialist."

Nova's role is Head of Inbox Wrangling. The meeting prompt had asked it to
answer "from your role's perspective". It was not being evasive and it was
not a weak model — Llama, on the identical brain, got it right. Nothing in
Nova's prompt had ever named it, so it invented a job title, and the boss
reads that invention in a room they are moderating.

The difference between the two is the door they came in by.
`agentStream` built its system prompt as:

    const base = agent.systemPrompt || `You are ${name}... Role: ${role}...`

Llama was hired at the front desk and carries no systemPrompt, so it fell
through to the default — the one and only sentence in the whole prompt
that says who they are. Nova was hired through NEW HIRE, and that form
PRE-FILLS the JOB DESCRIPTION box ("You are a helpful coworker. Be concise
and warm."). So every hire made through the only path to a custom coworker
arrives carrying a systemPrompt, and that systemPrompt replaced the
identity instead of joining it.

The office was not missing the facts. The form asks for NAME and ROLE /
TITLE in two dedicated fields, stores both on the agent, and prints them
on the desk plate, the seat card and the meeting-room chair. It then wrote
a prompt that mentioned neither.

The fix states identity ALWAYS and treats systemPrompt as what the form
calls it: the job description. Two things this pins that are easy to break
later:

- The boss's brief must SURVIVE. A "fix" that swapped `||` for the default
  alone would name the coworker correctly and silently delete everything
  the boss typed into the job description.
- The default branch keeps FILE-DELIVERY. A front-desk hire has no
  systemPrompt, and that branch is where the vault-delivery rule lives;
  losing it turns every long deliverable back into a wall of chat text.
  It has two forms now — the MUST when VAULT_NEW was granted, and a plain
  "keep it in your reply" when it was not, because ordering a coworker to
  file into a vault it does not have is what
  test_the_brief_and_the_grant_agree_before_sending.py exists for.

Run: python3 scripts/test_a_coworker_knows_their_own_name.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'hq-runtime.jsx'
HIRE = ROOT / 'modals' / 'hire.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'(?m)//.*$', '', src)


def main():
    print('a coworker knows their own name')
    runtime = RUNTIME.read_text(encoding='utf-8')
    hire = HIRE.read_text(encoding='utf-8')

    # ── 1. the thing that makes this reachable at all ────────────────────
    # If the form ever stops pre-filling the job description, the defect
    # goes quiet on its own and this file would be pinning nothing. It is
    # the pre-fill that turns "a boss who wrote a persona" into "every
    # single custom hire".
    check('the hire form still pre-fills a job description',
          re.search(r"setPrompt\('You are a helpful coworker", hire),
          'NEW HIRE left JOB DESCRIPTION blank — the identity loss would '
          'now only hit bosses who typed one, which is a different bug')
    check('...and stores it as the agent systemPrompt',
          re.search(r'systemPrompt:\s*prompt', hire), hire[:0] or 'hire.jsx')

    # ── 2. identity is stated unconditionally ────────────────────────────
    # Bound the window to agentStream's own head; `You are ${agent.name}`
    # appears in several unrelated prompts across the file.
    i = runtime.index('async function agentStream(')
    head = strip_comments(runtime[i:i + 4000])
    check('identity is built from the agent, not from the job description',
          re.search(r'const identity = `You are \$\{agent\.name\}.*?'
                    r'Role: \$\{agent\.role\}', head),
          'the name and the role are collected in two dedicated fields; '
          'the prompt has to actually say them')
    check('the job description no longer replaces it',
          not re.search(r'const base = agent\.systemPrompt \|\|', head),
          '`||` is the whole defect: a systemPrompt substituted for the '
          'only sentence naming the coworker')
    check('both branches of base start from identity',
          len(re.findall(r'\$\{identity\}', head)) >= 2,
          re.findall(r'\$\{identity\}', head))

    # ── 3. run the real thing over both doors ────────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH for the behavioural arm')
        return 1 if FAILS else 0

    # Runs to the end of `const base`, not to `const toolsNote` — the
    # reconciliation between the brief and the grant now sits between them
    # and belongs to its own suite.
    body = re.search(
        r'const identity = `You are \$\{agent\.name\}[\s\S]*?'
        r'const base = agent\.systemPrompt\s*\n?\s*\?[\s\S]*?;\n',
        head)
    # A missing pair is the defect this file exists for, so it has to be a
    # named failure -- a test that dies with a traceback prints no FAILED
    # line and the fire arm reads as "not pinned".
    check('the identity/base pair is still there to be run', bool(body),
          'no `const identity = ...` + `const base = agent.systemPrompt ? '
          '...` pair in agentStream')
    if not body:
        print()
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1

    # Both real doors, verbatim from the live office where this was found.
    agents = {
        # NEW HIRE form: name + role in their own fields, job description
        # left at the box's pre-filled default.
        'form_hire': {'name': 'Nova', 'role': 'Head of Inbox Wrangling',
                      'systemPrompt': 'You are a helpful coworker. Be concise and warm.'},
        # Front desk: detected on the machine, no systemPrompt at all.
        'front_desk': {'name': 'Llama', 'role': 'Generalist'},
        # A roster persona, which already opens by naming itself. The
        # restatement must not be allowed to drop its brief.
        'roster': {'name': 'Kip', 'role': 'Deep Research',
                   'systemPrompt': 'You are Kip, the Deep Research specialist. '
                                   'Always cite at least 3 distinct sources.'},
    }
    # The same front-desk hire on an office with no vault. Measured live as
    # Otto: hired through NEW HIRE with the job description cleared, no
    # vault box, and handed a MUST for two tools he did not have.
    granted = {k: ['VAULT_NEW', 'VAULT_APPEND'] for k in agents}
    agents['front_desk_no_vault'] = dict(agents['front_desk'])
    granted['front_desk_no_vault'] = []
    js = ('const AGENTS = %s;\nconst GRANTED = %s;\nconst R = {};\n'
          % (json.dumps(agents), json.dumps(granted))) + \
         'for (const [k, agent] of Object.entries(AGENTS)) {\n' + \
         '  const enabledTools = GRANTED[k].map(name => ({ name }));\n' + \
         body.group(0) + '\n  R[k] = base;\n}\n' + \
         'console.log(JSON.stringify(R));'
    p = subprocess.run(['node', '--input-type=module', '-e', js], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-1200:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    r = json.loads(p.stdout.strip().split('\n')[-1])

    for key, a in agents.items():
        check('%s is told their name' % key, a['name'] in r[key], r[key][:160])
        check('%s is told their role' % key, a['role'] in r[key], r[key][:160])

    check("the form hire's job description survives",
          agents['form_hire']['systemPrompt'] in r['form_hire'],
          'naming the coworker by deleting what the boss typed is not a fix')
    check("a roster persona's brief survives intact",
          'cite at least 3 distinct sources' in r['roster'], r['roster'][:200])
    check('a front-desk hire still gets the file-delivery rule',
          'FILE-DELIVERY RULE' in r['front_desk'],
          'no systemPrompt means this branch is the only place the vault '
          'rule is taught; without it long deliverables go back to chat')
    check('...and it orders the marker only when the marker exists',
          'VAULT_NEW' in r['front_desk']
          and 'VAULT_NEW' not in r['front_desk_no_vault'],
          r['front_desk_no_vault'][-260:])
    check('...and still asks for the restraint the rule was written for',
          'FILE-DELIVERY RULE' in r['front_desk_no_vault']
          and 'keep it tight' in r['front_desk_no_vault'],
          'dropping the whole rule with the vault puts the wall of text '
          'back; only the order to file has to go')
    check('...and a job description does not silently inherit it',
          'FILE-DELIVERY RULE' not in r['form_hire'],
          'the boss owns the job description; quietly appending office '
          'rules to it is the same conflation pointed the other way')

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
