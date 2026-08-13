#!/usr/bin/env python3
"""The stamp's walk-back told a coworker to undo work already on disk.

Drove the whole §3 step 4 gesture on a live office: starter card → task
→ dragged onto Nova's desk → run on a local brain → 1,217-character brief
→ filed to the cabinet. The office said so, in its own delivery modal:

    Nova finished Research brief: How gold-backed tokens settle on chain
    and filed it in your cabinet.
    📁 Research/research-brief-how-gold-backed-tokens-settle-on-chain.md

In the same beat the header raised a stamp — `[NEEDS_APPROVAL: Research
brief on gold-backed token settlement, no cost]`, the model restating the
finished work rather than asking to do anything. That shape was already in
the ledger, recorded as harmless:

    "this generic marker doesn't match publish/hire-agent/hire-assistant/
     grant-elevation/workflow-step, so Approve or Reject is pure local
     bookkeeping — no real action either way."

True when written. `onApprove`/`onReject` then widened their last branch
from `ap.elevated && ap.agentId` to `ap.agentId` — correct on its own
terms, because a coworker who asked deserves the answer — and that turned
the generic marker into a real dispatch. Nobody re-checked the earlier
conclusion against the newer branch.

So rejecting the already-filed brief sent Nova "Stand down — do NOT carry
out that action", and Nova rewrote the brief and closed by asking the boss
to review it: a loop, off an order to do nothing. Approve was the same
defect facing the other way — "Carry it out" for a file already in the
vault.

The office knows two things here: the boss stamped, and what the
description said. It does NOT know whether the action is still pending —
all four raise sites are run finalizers, so a genuine "may I publish this?"
and a restatement of finished work arrive through the identical path and
are not distinguishable from the text. So the walk-back must stop
asserting which one it is. That is the property this pins: the decision
still travels (the protocol promises "you'll be told once it's decided"),
the imperative is conditioned, and the already-done case is named.

Measured live, same coworker and rejected title, one run per arm: the old
wording drew 735 characters that restated the brief and re-asked for
review; the new wording drew a 138-character acknowledgement with no
second copy.

Run: python3 scripts/test_stamp_walkback_knows_what_it_knows.py
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
print('stamp walk-back — the office states the decision, not a world-state')

fns = {}
for name in ('onApprove', 'onReject'):
    m = re.search(r'const ' + name + r' = \(id\) => \{[\s\S]*?\n  \};', src)
    check(f'{name} is still where it was', bool(m), f'app.jsx: could not find {name}')
    fns[name] = m.group(0) if m else ''

# The dispatch that walks the decision back to the coworker who asked. It is
# the LAST dispatchToAgent in each function — the earlier ones belong to the
# typed kinds (hire, elevation) which are genuine pre-action gates and are
# deliberately left alone.
walk = {}
for name, body in fns.items():
    tail = body.split("else if (ap.agentId)")[-1] if 'else if (ap.agentId)' in body else ''
    m = re.search(r'dispatchToAgent\(target,\s*\n?\s*`([^`]*)`', tail)
    check(f'{name} still walks the decision back to the asker', bool(m),
          f'app.jsx: no dispatch in {name}\'s `ap.agentId` branch — the stamp is '
          'only half the loop, and both approval notes promise the coworker '
          'will be told')
    walk[name] = m.group(1) if m else ''

# ── 1. the decision itself still travels ────────────────────────────────
# Everything below removes certainty from these strings; this makes sure it
# does not remove the message.
check('approve says it was approved, and names what', 'APPROVED' in walk['onApprove']
      and '${ap.title}' in walk['onApprove'], repr(walk['onApprove']))
check('reject says it was rejected, and names what', 'REJECTED' in walk['onReject']
      and '${ap.title}' in walk['onReject'], repr(walk['onReject']))

# ── 2. neither one asserts the action is still pending ──────────────────
check('approve does not order work that may already be done',
      not re.search(r'You may now proceed with that action\. Carry it out', walk['onApprove']),
      repr(walk['onApprove']) + ' — a bare "carry it out" is a claim about the '
      'world, and the raise sites are run finalizers, so the office cannot '
      'know whether anything is left to carry out')
check('reject does not order a stand-down from a finished act',
      'Stand down' not in walk['onReject'],
      repr(walk['onReject']) + ' — watched live against a brief already written '
      'to the vault: the coworker rewrote it and asked for review again')

# ── 3. …and both name the case the office cannot rule out ───────────────
# The absence checks above are satisfied by deleting the sentence entirely,
# which would lose the walk-back. This is the half that has to be present.
check('approve conditions the go-ahead on it not being done yet',
      re.search(r'If you have not done it yet', walk['onApprove'])
      and re.search(r'already done', walk['onApprove']),
      repr(walk['onApprove']))
check('reject tells the coworker to say so rather than redo it',
      re.search(r'already did it', walk['onReject'])
      and re.search(r'do not repeat it or redo the work', walk['onReject']),
      repr(walk['onReject']) + ' — "do not do it" alone left the model to guess '
      'what to do about the copy it had already produced, and it guessed '
      '"produce it again"')

# ── 4. the real gate is untouched ───────────────────────────────────────
# External approvals come from the Claude Code PreToolUse hook, which
# long-polls /approvals/external/wait and is genuinely BLOCKED on the answer.
# Nothing above may soften that path: there the action really has not
# happened, and the hedge would be the lie.
for name, decision in (('onApprove', 'allow'), ('onReject', 'deny')):
    body = fns[name]
    check(f'{name} still answers a blocked external hook with "{decision}"',
          re.search(r"decideExternal\(ap\.externalId, '" + decision + r"'", body),
          f'app.jsx: {name} must keep releasing the hook — that caller is '
          'waiting on a socket, and it is the one approval the office KNOWS '
          'is pending')
    ext = body.find('ap.external && ap.externalId')
    agid = body.find('else if (ap.agentId)')
    check(f'{name} checks the external gate before the generic walk-back',
          ext != -1 and agid != -1 and ext < agid,
          f'app.jsx: external at {ext}, generic at {agid} — an external '
          'approval also carries agentId, so reversing these would send the '
          'hedged note and leave the hook blocked forever')

print()
if FAILS:
    print(f'stamp walk-back: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
    sys.exit(1)
print('stamp walk-back: all checks passed')
