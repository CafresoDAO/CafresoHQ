#!/usr/bin/env python3
"""A dismissed coworker could still receive and answer a DM that was
already in flight when they were let go — the recipient-resolution line
in all three DM-continuation loops read a stale `agents` closure instead
of the live `agentsRef.current`.

`dispatchToAgent`, `onDelegate`, and `onTaskDropOnAgent` (app.jsx) each
run their own copy of the same post-stream loop: once an agent's reply
finishes, any `[DM_TO: <name>]` markers it emitted are resolved to a
target coworker by name and re-dispatched:

    for (const dm of dmQueue) {
      const target = agents.find(x => x.name.toLowerCase() === ...);
      ...
      await dispatchToAgent(target, dm.body, { dmFrom: agent, ... });
    }

`agents` is the plain state variable captured by closure at the render
that started the ORIGINAL dispatch (the one now emitting DM_TO markers)
— not `agentsRef.current`, the ref this same file already keeps live via
`agentsRef.current = agents` specifically so long-running async code can
read current state (`dispatchToAgent`'s own `peers`/`myAssistants`
context lists, and — per an earlier fix, `scripts/
test_honesty_notes_roster_reads_live_agents_in_remaining_dispatch_paths.py`
— its `honestyFor`'s `roster` field, in these same three functions).
That earlier fix only touched the honesty-label roster; the actual
recipient-resolution `target` line beside it, in all three functions,
was never converted.

`dispatchToAgent` DOES guard against dispatching to a just-dismissed
recipient — but only inside the branch that waits for a currently BUSY
desk (`if (agentAbortersRef.current.has(agent.id))`), which re-checks
the roster after the wait. `onDismiss` (the LET GO handler) calls
`abortAgentRun(id)`, which deletes the aborter entry SYNCHRONOUSLY —
so a coworker's desk reads as free the instant they're dismissed, in
the overwhelmingly common case where they weren't already mid-reply.
The busy-desk branch is never entered, its recipient-gone check never
runs, and dispatchToAgent falls straight through to post a chat bubble
under the dismissed coworker's name and stream them a real reply.

Concrete sequence: the boss asks Vera something that leads her to emit
`[DM_TO: Kenji]...[/DM_TO]`. While Vera is still streaming her reply
(this can run for many seconds), the boss presses LET GO on Kenji —
his desk is idle, so the dismissal is instant: `onDismiss` removes him
from `agents`, reassigns his tasks, drops his roster entries elsewhere.
Vera's stream finishes; her DM_TO is parsed and the `dmQueue` loop
resolves `agents.find(... 'kenji' ...)` against the STALE `agents`
array `dispatchToAgent` captured back when Vera's own dispatch began —
which still contains Kenji, because his dismissal happened after that
render. `target` resolves to him anyway, and he is re-dispatched: a chat
bubble reading "Kenji · <role>" appears and streams a real, billed LLM
reply from a coworker the boss just fired.

Found by the same background hunt that landed the honesty-notes roster
fix: sweeping `app.jsx` for every remaining `agents.find(`/`agents.map(`
read inside the three dispatch functions turned up this sibling
`target = agents.find(...)` line, unconverted in all three, sitting
right beside the roster line that already had been.

Fix: all three `target = agents.find(...)` reads now use
`agentsRef.current.find(...)`, matching the roster fix beside them.

Run: python3 scripts/test_dm_continuation_target_reads_live_agents_not_stale_closure.py
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


FUNCS = [
    ('dispatchToAgent',
     r"const dispatchToAgent = async \(agent, prompt, opts = \{\}\) => \{"),
    ('onDelegate',
     r"const onDelegate = async \(a, typed, thread\) => \{"),
    ('onTaskDropOnAgent',
     r"const onTaskDropOnAgent = async \(taskId, agent, taskFresh, opts = \{\}\) => \{"),
]


def main():
    print("the DM-continuation target resolver reads the live agentsRef "
          "in all three dispatch paths, not a stale `agents` closure")

    src = APP.read_text(encoding='utf-8')

    check('agentsRef is still defined and kept live via an effect '
          '(this fix depends on it existing)',
          'const agentsRef = useRefA(agents);  agentsRef.current = agents;' in src)

    target_matches = {}
    for name, start_pat in FUNCS:
        fn_m = re.search(start_pat + r"(.*?)\n  \};", src, re.S)
        check(f'found {name}', fn_m is not None)
        body = fn_m.group(1) if fn_m else ''
        tm = re.search(r"const target = (agentsRef\.current|agents)\.find\(",
                        body)
        check(f'found the DM-continuation target line inside {name}',
              tm is not None)
        target_matches[name] = tm
        check(f"{name}'s DM-continuation target reads agentsRef.current "
              f"(live), not the plain `agents` closure — the actual "
              f"regression: a coworker dismissed while {name}'s own "
              f"stream was in flight could still be resolved as a valid "
              f"DM target and re-dispatched",
              tm and tm.group(1) == 'agentsRef.current',
              tm and f'reads `{tm.group(1)}` instead')

    # Aggregate count, so a 4th dispatch path added later trips this test
    # rather than silently going unchecked (mirrors the sibling roster test).
    all_target_reads = re.findall(
        r"const target = (agentsRef\.current|agents)\.find\(x?a? => a?x?\.name\.toLowerCase\(\)",
        src)
    check('there are exactly 3 DM-continuation target-resolution reads '
          'in the file (dispatchToAgent, onDelegate, onTaskDropOnAgent) '
          '— if this count changes, a 4th dispatch path was added and '
          'needs the same check',
          len(all_target_reads) == 3, all_target_reads)
    check('every DM-continuation target read in the file uses the live '
          'agentsRef.current, none still read the plain stale `agents` '
          'closure',
          all(r == 'agentsRef.current' for r in all_target_reads),
          all_target_reads)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted '
          'lines below)', has_node, 'skipping the live-execution check')

    if has_node and all(target_matches.values()):
        # Lift the ACTUAL matched expression text out of the source for
        # each function rather than retyping the logic, and run it under
        # Node against a scenario shaped exactly like the bug: `agents`
        # (the stale closure) still contains a coworker who has since
        # been dismissed from the LIVE roster, `agentsRef.current`.
        exprs = {}
        for name, tm in target_matches.items():
            # tm matched only the opening "...find(" — recover the full
            # statement (up to the closing ");") from the same body text.
            fn_m = re.search(dict(FUNCS)[name] + r"(.*?)\n  \};", src, re.S)
            body = fn_m.group(1)
            full = re.search(r"const target = (?:agentsRef\.current|agents)\.find\(.*?\);", body)
            check(f'recovered the full target-resolution statement for {name}',
                  full is not None)
            stmt = full.group(0) if full else None
            # dispatchToAgent resolves through an intermediate `targetName`
            # (computed from `dm.to` one line above the target line) rather
            # than reading `dm.to` inline like the other two — lift that
            # supporting line too instead of reimplementing it by hand.
            if stmt and 'targetName' in stmt:
                pre = re.search(r"const targetName = [^\n]*;", body)
                check(f"recovered {name}'s supporting `targetName` line",
                      pre is not None)
                stmt = (pre.group(0) + '\n          ' + stmt) if pre else stmt
            exprs[name] = stmt

        js = f"""
        const dm = {{ to: 'Kenji' }};
        // Stale closure snapshot: what `agents` looked like at the render
        // that started the sender's own dispatch, BEFORE Kenji was let go.
        const agents = [
          {{ id: 'a_vera', name: 'Vera' }},
          {{ id: 'a_kenji', name: 'Kenji' }},
        ];
        // Live roster by the time the DM-continuation loop actually runs:
        // Kenji was dismissed while the sender's stream was in flight.
        const agentsRef = {{ current: [
          {{ id: 'a_vera', name: 'Vera' }},
        ] }};

        const results = {{}};

        {{
          {exprs['dispatchToAgent']}
          results.dispatchToAgent = target ? target.name : null;
        }}
        {{
          {exprs['onDelegate']}
          results.onDelegate = target ? target.name : null;
        }}
        {{
          {exprs['onTaskDropOnAgent']}
          results.onTaskDropOnAgent = target ? target.name : null;
        }}

        console.log(JSON.stringify(results));
        """
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the extracted target-resolution statements ran without a '
              'Node error', r.returncode == 0, r.stderr.strip()[-500:])
        if r.returncode == 0:
            import json
            out = json.loads(r.stdout.strip().splitlines()[-1])
            for name in ('dispatchToAgent', 'onDelegate', 'onTaskDropOnAgent'):
                check(f"{name} resolves the DM target to null now that "
                      f"Kenji is gone from the live roster (would "
                      f"wrongly resolve to 'Kenji' — resurrecting a "
                      f"dismissed coworker's reply — before the fix)",
                      out.get(name) is None, out.get(name))

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
