#!/usr/bin/env python3
"""A task dropped on a busy desk could hand its coworker a DM roster from
before the boss even answered the dialog.

`onTaskDropOnAgent` (app.jsx) is a plain, non-memoized async arrow
function recreated every render — the same shape `dispatchToAgent` has,
and the reason `agentsRef`/`tasksRef` exist and are already read twice in
THIS function for exactly this staleness hazard (the chain-advance block's
`tasksRef.current.find(t => t.id === task.chainTo)`, and the DM-fanout
loop's `agentsRef.current.find(...)` a little further down). Dropping a
card on a coworker who is already mid-run raises `window.hqConfirm` — an
await that blocks on the BOSS, for as long as they take to click something
— and the function only proceeds to actually start the run once that
promise resolves:

    const ok = await window.hqConfirm(`${agent.name} is working on ...`);
    if (!ok) return;
    ...
    await HQ.agentStream(agent, ..., { ..., peers: agents.filter(x => x.id !== agent.id), ... });

`peers` is not decoration — `toolsForAgent` in hq-runtime.jsx gates the
whole DM_TO tool on `peers && peers.length` and writes the exact "Coworkers
you can DM: ..." line from it, and binds PEER_JOURNAL's lookups to it too.
Reading the plain `agents` closure here means that list reflects the
roster as it stood at the RENDER that started this drop — before the
dialog ever opened — not the one live when the coworker's turn actually
runs.

Concrete sequence: card dropped on Vera while she's still finishing an
earlier job (or her chat is mid-reply); the "is working on X, start this
instead?" dialog opens. While it sits open the boss hires a new coworker,
Zara — or dismisses an existing one, Milo. The boss clicks "Start it".
The stale `agents` snapshot from before the dialog has no Zara, so DM_TO's
roster line omits her entirely — she is invisible as a hand-off target for
the entire run — and it still lists Milo, who is gone, as somebody Vera
can safely message. Neither is what the office actually looks like at the
moment the coworker is briefed.

Found by a background hunt agent sweeping the task board / drag-drop /
chain-step area for the same stale-closure-over-state category already
fixed twice in this exact function (chain-advance, DM fanout) and twice
more in `dispatchToAgent` (the assistant-hire cap, and the four
prompt-context reads in
scripts/test_dispatch_prompt_context_reads_live_agents_and_tasks.py) —
this is the fifth site of the same bug, on the one dispatch path (task
drop) those two sweeps never reached.

Fix: `peers` now reads `agentsRef.current.filter(...)` instead of the
plain `agents` closure, matching every other live-state read already in
this function.

This test extracts the actual `peers:` line from source (not a
hand-copied duplicate) and genuinely executes it via Node with a stale
`agents` array vs. a live `agentsRef.current` that has since gained one
coworker and lost another, confirming the extracted line now reflects the
live roster.

Run: python3 scripts/test_a_busy_desk_wait_stales_the_dm_roster.py
(skips the live-execution check if `node` isn't on PATH — the
source-shape checks still run everywhere)
"""
import json
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
    print("onTaskDropOnAgent's DM peer roster reads the live agentsRef, not a stale `agents` closure")

    src = APP.read_text(encoding='utf-8')

    m = re.search(
        r"peers: (agentsRef\.current|agents)\.filter\(x => x\.id !== agent\.id\),",
        src)
    check('found the onTaskDropOnAgent peers line', m is not None)
    variable_read = m.group(1) if m else ''

    check("the peers line reads agentsRef.current (live), not the plain "
          "`agents` closure (which can be stale after a boss sits on the "
          "displaced-run confirm dialog) — this is the actual regression",
          variable_read == 'agentsRef.current',
          f'reads `{variable_read}` instead')

    check('agentsRef is still defined and kept live via an effect '
          '(this fix depends on it existing)',
          'const agentsRef = useRefA(agents);  agentsRef.current = agents;' in src)

    # onTaskDropOnAgent's own hqConfirm await is the wait this bug rides on —
    # confirm it's still there, unmemoized, ahead of the peers line.
    func_m = re.search(
        r"const onTaskDropOnAgent = async \(taskId, agent, taskFresh, opts = \{\}\) => \{",
        src)
    check('onTaskDropOnAgent is still a plain (non-memoized) async arrow '
          'function — the shape this bug depends on', func_m is not None)
    if func_m:
        window = src[func_m.end():func_m.end() + 6000]
        check("a boss-blocking hqConfirm await still sits ahead of the "
              "peers line inside this same function",
              'await window.hqConfirm(' in window)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted '
          'line below)', has_node, 'skipping the live-execution check')

    if has_node and m:
        # The matched text is an object-literal property (`peers: expr,`),
        # not a standalone statement — turn it into one the same shape the
        # source expresses, without hand-copying the expression itself.
        line = 'const ' + m.group(0).rstrip(',').replace(': ', ' = ', 1) + ';'
        js = f"""
        const agent = {{ id: 'a_vera' }};
        // Stale closure snapshot: this is what `agents` looked like at the
        // render that started this task drop, before the confirm dialog
        // ever opened.
        const agents = [
          {{ id: 'a_vera' }},
          {{ id: 'a_milo', name: 'Milo', role: 'Ops' }},
        ];
        // Live state by the time the coworker's turn actually runs: the
        // boss hired Zara and dismissed Milo while the dialog sat open.
        const agentsRef = {{ current: [
          {{ id: 'a_vera' }},
          {{ id: 'a_zara', name: 'Zara', role: 'Research' }},
        ] }};
        {line}
        console.log(JSON.stringify({{ names: peers.map(p => p.name) }}));
        """
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the extracted line ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-500:])
        if r.returncode == 0:
            out = json.loads(r.stdout.strip().splitlines()[-1])
            names = out.get('names', [])
            check('the peer roster includes Zara, hired while the dialog '
                  'was open (would be missing if reading the stale '
                  '`agents` closure)',
                  'Zara' in names, names)
            check('the peer roster no longer offers Milo, dismissed while '
                  'the dialog was open (would still be listed as a valid '
                  'DM target if reading the stale `agents` closure)',
                  'Milo' not in names, names)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
