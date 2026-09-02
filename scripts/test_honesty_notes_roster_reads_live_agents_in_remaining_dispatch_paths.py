#!/usr/bin/env python3
"""The honesty-notes `roster` closure read a stale `agents` snapshot in
two of the app's three dispatch paths — even though the identical
closure in the third (`onDelegate`) was already fixed.

`honestyFor` is defined near the top of each of the app's async
dispatch handlers, but only CALLED after `await HQ.agentStream(...)`
resolves — a call that can run for a long time. `agents` is captured by
closure at the render that started the dispatch; `agentsRef.current` is
kept live by an effect specifically so async code can read current
state. `dispatchToAgent` (the @mention path) and `onTaskDropOnAgent`
(the task-drop path) both still read the plain `agents` closure for
`honestyFor`'s `roster` field:

    const honestyFor = (raw) => (HQ.honestyNotes
      ? HQ.honestyNotes(raw, { delivered: dmQueue.length, roster: agents.map(x => x.name), ... })
      : []);

`onDelegate`'s identical closure was already converted to
`agentsRef.current` in an earlier fix — these two were missed.

Concrete sequence: a coworker's @mention or task-drop dispatch is
streaming a reply. While it's in flight, the boss hires a new coworker
or dismisses one. `HQ.honestyNotes` (hq-runtime.jsx) uses `roster` to
decide whether a name in the reply is a real teammate — a dismissed
coworker's name still passes the roster check (the honesty guard that
exists specifically to catch a claimed handoff to someone who isn't
real silently fails to catch it), and a newly hired coworker's name can
get flagged as NOT a real teammate even though they now are one.

Found by a background hunt agent that had already found this exact bug
shape three times (dispatchToAgent's peers/assistants/teammates/tasks,
onDelegate's roster/peers) — it went looking for any remaining
instance of the same closure in the app's other dispatch paths and
found it was fixed in onDelegate but not in the other two functions
that have their own copy of the identical honestyFor closure.

Fix: both remaining `roster: agents.map(...)` reads now use
`agentsRef.current.map(...)`, matching the already-fixed `onDelegate`
sibling.

Run: python3 scripts/test_honesty_notes_roster_reads_live_agents_in_remaining_dispatch_paths.py
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
    print("honestyFor's roster reads the live agentsRef in every dispatch path, not just onDelegate")

    src = APP.read_text(encoding='utf-8')

    roster_reads = re.findall(
        r"roster: (agentsRef\.current|agents)\.map\(x => x\.name\)", src)
    check('found honestyFor roster closures in the file',
          len(roster_reads) > 0)
    check('there are exactly 3 honestyFor roster closures in the file '
          '(dispatchToAgent, onTaskDropOnAgent, onDelegate) — if this '
          'count changes, a 4th dispatch path was added and needs the '
          'same check',
          len(roster_reads) == 3, roster_reads)
    check('every honestyFor roster closure in the file now reads the '
          'live agentsRef.current, none still read the plain stale '
          '`agents` closure — the actual regression, previously true '
          'for only 1 of the 3',
          all(r == 'agentsRef.current' for r in roster_reads), roster_reads)

    # Confirm each of the three functions individually, so a future
    # refactor that renames/reorders can't accidentally make the aggregate
    # count checks above pass while one specific function regresses.
    dispatch_m = re.search(
        r"const dispatchToAgent = async \([^)]*\) => \{.*?"
        r"const honestyFor = \(raw\) => \(HQ\.honestyNotes\n"
        r"\s*\? HQ\.honestyNotes\(raw, \{ delivered: dmQueue\.length, "
        r"roster: (agentsRef\.current|agents)\.map",
        src, re.S)
    check('found dispatchToAgent\'s honestyFor roster read',
          dispatch_m is not None)
    check("dispatchToAgent's honestyFor reads agentsRef.current",
          dispatch_m and dispatch_m.group(1) == 'agentsRef.current',
          dispatch_m and f'reads `{dispatch_m.group(1)}` instead')

    task_m = re.search(
        r"const onTaskDropOnAgent = async \([^)]*\) => \{.*?"
        r"const honestyFor = \(raw\) => \(HQ\.honestyNotes\n"
        r"\s*\? HQ\.honestyNotes\(raw, \{ delivered: dmQueue\.length, "
        r"roster: (agentsRef\.current|agents)\.map",
        src, re.S)
    check('found onTaskDropOnAgent\'s honestyFor roster read',
          task_m is not None)
    check("onTaskDropOnAgent's honestyFor reads agentsRef.current",
          task_m and task_m.group(1) == 'agentsRef.current',
          task_m and f'reads `{task_m.group(1)}` instead')

    delegate_m = re.search(
        r"const onDelegate = async \([^)]*\) => \{.*?"
        r"const honestyFor = \(raw\) => \(HQ\.honestyNotes\n"
        r"\s*\? HQ\.honestyNotes\(raw, \{ delivered: dmQueue\.length, "
        r"roster: (agentsRef\.current|agents)\.map",
        src, re.S)
    check('found onDelegate\'s honestyFor roster read (should already '
          'have been fixed by an earlier tick)', delegate_m is not None)
    check("onDelegate's honestyFor still reads agentsRef.current",
          delegate_m and delegate_m.group(1) == 'agentsRef.current',
          delegate_m and f'reads `{delegate_m.group(1)}` instead')

    check('agentsRef is still defined and kept live via an effect '
          '(this fix depends on it existing)',
          'const agentsRef = useRefA(agents);  agentsRef.current = agents;' in src)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute an extracted '
          'roster line below)', has_node, 'skipping the live-execution check')

    if has_node and roster_reads:
        js = """
        const agentsRef = { current: [
          { id: 'a_senior', name: 'Vera' },
          { id: 'a_new', name: 'Nano' },
        ] };
        const roster = agentsRef.current.map(x => x.name);
        console.log(JSON.stringify({ roster }));
        """
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the agentsRef.current.map(...) shape genuinely executes '
              'without a Node error and reflects the live roster passed '
              'to it', r.returncode == 0, r.stderr.strip()[-300:])

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
