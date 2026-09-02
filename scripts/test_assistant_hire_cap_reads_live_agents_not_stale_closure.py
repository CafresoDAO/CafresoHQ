#!/usr/bin/env python3
"""The per-senior assistant-hire cap could be silently exceeded by a
long-running dispatch that started before a concurrent hire bumped the
senior's live assistant count.

`dispatchToAgent` (app.jsx) is a plain, non-memoized async arrow
function recreated every render — it closes over whatever `agents`
was at the render that STARTED this particular dispatch, and it can
still be running minutes later (the whole reason `agentsRef`/
`tasksRef` exist and are already used twice elsewhere in this same
function for exactly this staleness hazard — see the "was I dismissed
mid-dispatch" checks). The assistant-hire cap check was left reading
the plain `agents` closure instead of `agentsRef.current`:

    const currentAssistants = agents.filter(a => a.reportsTo === agent.id).length;
    if (currentAssistants >= ASSISTANT_CAP_PER_SENIOR) { ...continue... }

Concrete sequence: senior A has 1 assistant when a long dispatch for A
starts (closing over that `agents` snapshot). While A's stream is still
running, a separate, quicker dispatch/approval hires a second assistant
for A — A's LIVE assistant count is now 2, the documented cap. When A's
original long-running dispatch reaches this check, it still sees the
stale snapshot (1 assistant), so `currentAssistants >= cap` is false and
it raises another hire proposal. `onApprove`'s `hire-assistant` branch
performs no independent cap re-check — it just builds the agent and
calls `onHire` — so approving it gives A a 3rd assistant, silently over
the cap the rest of the app (dismiss-cascade, the roster UI) assumes
holds.

Found by a background hunt agent sweeping previously-unswept areas,
specifically for stale-closure-over-state bugs in async dispatch code
(a category this file already has two other fixes for, `agentsRef`
checks at other points in the same function).

Fix: the cap check now reads `agentsRef.current` instead of the plain
`agents` closure, matching the pattern already used elsewhere in this
same function.

This test extracts the actual cap-check line from source (not a
hand-copied duplicate) and genuinely executes it via Node with a stale
`agents` value vs. a live `agentsRef.current` that has since grown past
the cap, confirming the check now catches the cap using live data.

Run: python3 scripts/test_assistant_hire_cap_reads_live_agents_not_stale_closure.py
(skips the live-execution check if `node` isn't on PATH — the
source-shape checks still run everywhere)
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("The assistant-hire cap check reads the live agentsRef, not a stale `agents` closure")

    src = APP.read_text(encoding='utf-8')

    m = re.search(
        r"const currentAssistants = (agentsRef\.current|agents)\.filter\("
        r"a => a\.reportsTo === agent\.id\)\.length;",
        src)
    check('found the assistant-hire cap check', m is not None)
    variable_read = m.group(1) if m else ''

    check("the cap check reads agentsRef.current (live), not the plain "
          "`agents` closure (which can be stale for a long-running "
          "dispatch) — this is the actual regression",
          variable_read == 'agentsRef.current',
          f'reads `{variable_read}` instead')

    check('ASSISTANT_CAP_PER_SENIOR is still defined as 2 (this test\'s '
          'scenario below assumes that exact cap)',
          'const ASSISTANT_CAP_PER_SENIOR = 2;' in src)

    check("onApprove's hire-assistant branch still performs no "
          "independent cap re-check of its own (confirms the fix has "
          "to live at the raise-time check tested above, not at "
          "approval time)",
          not re.search(
              r"if \(ap\.kind === 'hire-assistant'.*?ASSISTANT_CAP_PER_SENIOR",
              src, re.S))

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted '
          'check below)', has_node, 'skipping the live-execution check')

    if has_node and m:
        line = m.group(0)
        js = f"""
        const ASSISTANT_CAP_PER_SENIOR = 2;
        const agent = {{ id: 'a_senior' }};
        // Stale closure snapshot: only 1 assistant existed when this
        // (hypothetically long-running) dispatch started.
        const agents = [
          {{ id: 'a_senior' }},
          {{ id: 'a_asst1', reportsTo: 'a_senior' }},
        ];
        // Live state by the time the check actually runs: a second
        // assistant was hired for this senior in the meantime, reaching
        // the cap.
        const agentsRef = {{ current: [
          {{ id: 'a_senior' }},
          {{ id: 'a_asst1', reportsTo: 'a_senior' }},
          {{ id: 'a_asst2', reportsTo: 'a_senior' }},
        ] }};
        {line}
        console.log(JSON.stringify({{
          currentAssistants,
          capHit: currentAssistants >= ASSISTANT_CAP_PER_SENIOR,
        }}));
        """
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the extracted check ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-500:])
        if r.returncode == 0:
            import json
            out = json.loads(r.stdout.strip().splitlines()[-1])
            check('with a stale `agents` snapshot (1 assistant) but a live '
                  'count that has since reached the cap (2 assistants), '
                  'the check correctly reports capHit=true — it must read '
                  'the LIVE count, not the stale one (which would '
                  'incorrectly report capHit=false and let a 3rd '
                  'assistant through)',
                  out.get('capHit') is True, out)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
