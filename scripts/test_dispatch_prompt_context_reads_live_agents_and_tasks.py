#!/usr/bin/env python3
"""`dispatchToAgent`'s prompt-context construction (peers, my assistants,
project teammates, my open tasks) read the plain `agents`/`tasks`
closures instead of the live `agentsRef.current`/`tasksRef.current`.

`dispatchToAgent` (app.jsx) is a plain, non-memoized async arrow
function recreated every render — it closes over whatever
`agents`/`tasks` were at the render that STARTED this particular
dispatch, and it can still be running minutes later (the busy-desk wait
loop a few lines above this code can block indefinitely until a desk
frees up). `agentsRef`/`tasksRef` exist and are kept live via effects
specifically so async code reads current state — and the
recipient-existence check ("did they leave while we waited?") a few
lines above this code already uses `agentsRef.current` for exactly this
reason — but the very next several reads, building the agent's prompt
context, were left reading the stale plain closures:

    const peers = agents.filter(a => a.id !== agent.id);
    const myAssistants = agents.filter(a => a.reportsTo === agent.id);
    const teammates = (proj.agentIds || []).map(aid => agents.find(...));
    const myTasks = (tasks || []).filter(t => t.assignedTo === agent.id && ...);

Concrete sequence: dispatch a note to an agent whose desk is busy. The
function enters the busy-desk wait loop, which can run for minutes.
While it waits, the boss hires a new coworker, dismisses one, adds/
removes a project teammate, or reassigns/completes a task. When the
wait ends and the prompt context is built, it reflects the roster/board
as it was when the wait STARTED, not when the message is actually
delivered: a dismissed coworker can still be listed as a live peer or
assistant to DM, a newly hired coworker is invisible, a newly added
project teammate is missing from "Other coworkers on this project", and
a task already completed (or reassigned elsewhere) is still listed
under "YOUR OPEN TASKS".

Found by a background hunt agent sweeping previously-unswept areas,
specifically for stale-closure-over-state bugs in async dispatch code —
the same category, and the same function, as the already-fixed
assistant-hire-cap bug (see
scripts/test_assistant_hire_cap_reads_live_agents_not_stale_closure.py),
but four distinct read sites the cap fix didn't touch.

Fix: all four reads now use `agentsRef.current`/`tasksRef.current`
instead of the plain `agents`/`tasks` closures, matching the pattern
already used earlier in this same function.

This test extracts the actual four lines from source (not hand-copied
duplicates) and genuinely executes them via Node with a stale `agents`/
`tasks` snapshot vs. a live ref that has since changed, confirming each
one now reflects the live state.

Run: python3 scripts/test_dispatch_prompt_context_reads_live_agents_and_tasks.py
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
    print("dispatchToAgent's prompt-context lists read the live agentsRef/tasksRef, not stale closures")

    src = APP.read_text(encoding='utf-8')

    peers_m = re.search(
        r"const peers = (agentsRef\.current|agents)\.filter\(a => a\.id !== agent\.id\);",
        src)
    check('found the peers line', peers_m is not None)
    check('peers reads agentsRef.current (live), not the plain `agents` closure',
          peers_m and peers_m.group(1) == 'agentsRef.current',
          peers_m and f'reads `{peers_m.group(1)}` instead')

    assist_m = re.search(
        r"const myAssistants = (agentsRef\.current|agents)\.filter\("
        r"a => a\.reportsTo === agent\.id\);",
        src)
    check('found the myAssistants line', assist_m is not None)
    check('myAssistants reads agentsRef.current (live), not the plain '
          '`agents` closure',
          assist_m and assist_m.group(1) == 'agentsRef.current',
          assist_m and f'reads `{assist_m.group(1)}` instead')

    teammates_m = re.search(
        r"\.map\(aid => (agentsRef\.current|agents)\.find\(a => a\.id === aid\)\)",
        src)
    check('found the project-teammates line', teammates_m is not None)
    check('teammates reads agentsRef.current (live), not the plain '
          '`agents` closure',
          teammates_m and teammates_m.group(1) == 'agentsRef.current',
          teammates_m and f'reads `{teammates_m.group(1)}` instead')

    tasks_m = re.search(
        r"const myTasks = \((tasksRef\.current|tasks) \|\| \[\]\)\.filter\(t =>\n"
        r"\s*t\.assignedTo === agent\.id && t\.status !== 'done'\);",
        src)
    check('found the myTasks line', tasks_m is not None)
    check('myTasks reads tasksRef.current (live), not the plain `tasks` '
          'closure',
          tasks_m and tasks_m.group(1) == 'tasksRef.current',
          tasks_m and f'reads `{tasks_m.group(1)}` instead')

    check('agentsRef is still defined and kept live via an effect '
          '(this fix depends on it existing)',
          'const agentsRef = useRefA(agents);  agentsRef.current = agents;' in src)
    check('tasksRef is still defined and kept live via an effect '
          '(this fix depends on it existing)',
          'const tasksRef = useRefA(tasks);  tasksRef.current = tasks;' in src)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted '
          'lines below)', has_node, 'skipping the live-execution check')

    if has_node and peers_m and assist_m and teammates_m and tasks_m:
        js = f"""
        const agent = {{ id: 'a_senior' }};
        // Stale closure snapshot: this is what `agents`/`tasks` looked like
        // when the (hypothetically long-running) dispatch started.
        const agents = [
          {{ id: 'a_senior' }},
          {{ id: 'a_dismissed', name: 'Gone', role: 'x' }},
        ];
        const tasks = [
          {{ id: 't1', assignedTo: 'a_senior', status: 'open', title: 'stale-open' }},
        ];
        // Live state by the time the prompt context is actually built: the
        // dismissed peer is gone, a new assistant was hired, a new
        // coworker joined the project, and the task was completed.
        const agentsRef = {{ current: [
          {{ id: 'a_senior' }},
          {{ id: 'a_new_asst', reportsTo: 'a_senior', name: 'NewAsst', role: 'y' }},
          {{ id: 'a_new_teammate', name: 'NewTeammate', role: 'z' }},
        ] }};
        const tasksRef = {{ current: [
          {{ id: 't1', assignedTo: 'a_senior', status: 'done', title: 'stale-open' }},
          {{ id: 't2', assignedTo: 'a_senior', status: 'open', title: 'fresh' }},
        ] }};
        const proj = {{ agentIds: ['a_senior', 'a_new_teammate'] }};

        {peers_m.group(0)}
        {assist_m.group(0)}
        const teammates = (proj.agentIds || [])
          {teammates_m.group(0)}
          .filter(a => a && a.id !== agent.id);
        {tasks_m.group(0)}

        console.log(JSON.stringify({{
          peerIds: peers.map(p => p.id),
          assistantIds: myAssistants.map(a => a.id),
          teammateIds: teammates.map(t => t.id),
          taskIds: myTasks.map(t => t.id),
        }}));
        """
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the extracted lines ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-500:])
        if r.returncode == 0:
            out = json.loads(r.stdout.strip().splitlines()[-1])
            check('peers no longer lists the dismissed coworker (would '
                  'incorrectly include a_dismissed if reading the stale '
                  '`agents` closure)',
                  'a_dismissed' not in out.get('peerIds', []), out.get('peerIds'))
            check('myAssistants picks up the newly hired assistant (would '
                  'be empty if reading the stale `agents` closure)',
                  out.get('assistantIds') == ['a_new_asst'], out.get('assistantIds'))
            check('teammates picks up the newly added project teammate '
                  '(would be missing if reading the stale `agents` closure)',
                  out.get('teammateIds') == ['a_new_teammate'], out.get('teammateIds'))
            check('myTasks no longer lists the now-completed task and '
                  'does list the newly assigned open one (would still show '
                  't1 as open if reading the stale `tasks` closure)',
                  out.get('taskIds') == ['t2'], out.get('taskIds'))

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
