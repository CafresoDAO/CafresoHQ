#!/usr/bin/env python3
"""HAND OFF TO… invented an order and signed the boss's name to it.

Drove the delegate path on a fresh office: two coworkers, nothing typed,
nothing said yet. Opened HAND OFF TO… and picked Nova. The transcript got

    You   (delegated "Standing order: review your backlog and report the
           top next step." to Nova)

The boss had issued no standing order. That sentence was a hardcoded
fallback, wrapped in the same `from: 'user', name: 'You'` envelope as a
real message, so nothing in the room distinguished it from something the
boss had typed — and it went to the coworker as the boss's brief.

The fabrication did not stop there, which is the part that makes this
worth a test rather than a tidy-up. A coworker handed a false premise
fills it in. Nova, asked to review a backlog that does not exist, replied:

    "I need to follow up on a pending request from Kenji regarding the
     current draft for our project. The last update was three days ago,
     and I'd like to confirm with him which version is current."

There is no Kenji, no project, no draft and no three days ago. Two bubbles
above it, the same office had said "nothing here is pre-staged, so
everything you see happen from here on is real". The office invented an
instruction, attributed it to the boss, and the floor invented work to
match it — §7's "no lies to the boss" broken twice from one default value.

An empty hand-off is not an error. It is a gesture with nothing in it, so
the office says so and names what would make it work. Nobody is
dispatched: no tokens, no busy desk, no bubble for work that does not
exist.

Run: python3 scripts/test_delegate_says_only_what_was_asked.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


src = APP.read_text(encoding='utf-8')
print('delegate — the office hands over what was asked, or says there is nothing')

fn = re.search(r'const onDelegate = async \(a, typed\) => \{[\s\S]*?\n  \};', src)
check('the delegate path is still where it was', bool(fn),
      'app.jsx: could not find onDelegate')
body = fn.group(0) if fn else ''

# ── 1. no invented brief, here or anywhere ──────────────────────────────
# Pinned on the whole file, not just this function: the value's problem is
# that it is fiction presented as the boss's words, and moving it to a
# constant at the top would not change that.
#
# Comments are stripped first, deliberately. The record of what the string
# WAS belongs next to the code that no longer uses it — that is how the
# next person understands why the empty case is guarded instead of given a
# sensible default. Searching the raw file would make keeping that note
# impossible, so this asks the question that actually matters: is it live?
code = re.sub(r'/\*[\s\S]*?\*/', '', src)
code = re.sub(r'(?m)^\s*//.*$', '', code)
check('no standing order the boss never gave',
      not re.search(r'Standing order', code),
      "app.jsx: the fallback brief was fiction wrapped as a message from "
      "'You' — a coworker cannot tell it from something the boss typed, and "
      'neither can the boss')

m = re.search(r'const brief = [^;]*;', body)
check('the brief comes from the boss or is empty', bool(m) and 'typed' in m.group(0),
      'app.jsx: could not read the brief assignment')
brief_line = m.group(0) if m else ''
check('...with no third source invented to fill the gap',
      brief_line.count('||') <= 2 and brief_line.rstrip().endswith("'';")
      or "? lastUser.text : ''" in brief_line,
      repr(brief_line) + " — what was typed, else what was last asked, else "
      'NOTHING. A third fallback is the office writing the boss\'s half of '
      'the conversation')

# ── 2. an empty hand-off dispatches nobody ──────────────────────────────
guard = re.search(r"if \(!brief\.trim\(\)\) \{[\s\S]{0,600}?\n    \}", body)
check('an empty hand-off is caught', bool(guard),
      'app.jsx: nothing guards the empty case — the coworker is dispatched '
      'against whatever the fallback happened to be')
g = guard.group(0) if guard else ''
check('...and stops there, before anyone is asked to work',
      'return;' in g,
      'app.jsx: the guard must return — a note plus a dispatch is the same '
      'fabrication with a disclaimer stapled on')

# Ordering is the real assertion: a guard that sits below the dispatch is
# decoration. Both indexes are inside onDelegate, so this reads the
# function's actual control flow rather than trusting the guard exists.
if g and body:
    gi = body.index(g)
    for after in ('agentStream(', 'onUpdateAgent(a.id, { status: \'busy\'', 'setChat(prev => [...prev, userMsg'):
        idx = body.find(after)
        check(f'the guard runs before `{after.split("(")[0].strip()}`',
              idx == -1 or gi < idx,
              f'app.jsx: the empty-brief guard is at {gi}, `{after}` at {idx} '
              '— a guard below the thing it guards changes nothing')

# ── 3. the office says it in its own voice ──────────────────────────────
# The whole defect was office text wearing the boss's name. The correction
# must not repeat the trick in the other direction.
check('the note is the office speaking, not the boss',
      "from: 'system'" in g and "from: 'user'" not in g,
      'app.jsx: this line is the office reporting, so it must be a system '
      'message — the defect being fixed IS office text filed under `You`')
check('...and it names both the coworker and the way forward',
      '${a.name}' in g and re.search(r"type what you'?d like them to do", g),
      'app.jsx: "nothing happened" without a next step is a dead end (§7)')

# ── 4. a real hand-off is untouched ─────────────────────────────────────
# Verified live alongside this: typing a question and picking Nova sent
# exactly that question, once, and cleared the composer.
check('a real brief still reaches the coworker',
      re.search(r'await HQ\.agentStream\(a, brief,', body),
      'app.jsx: the dispatch must still send the brief itself')
check('the hand-off is still disclosed in the transcript',
      re.search(r'text: `\(delegated "\$\{brief\}" to \$\{a\.name\}\)`', body),
      'app.jsx: the boss must be able to see what was sent and to whom')
check('...and still marked so it cannot be re-delegated as a fresh ask',
      'delegated: true' in body
      and re.search(r"m\.from === 'user' && !m\.delegated", body),
      'app.jsx: without the flag these wrappers nest — four clicks once '
      'produced a brief four `(delegated "…"` deep')

print()
if FAILS:
    print(f'delegate: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
    sys.exit(1)
print('delegate: all checks passed')
