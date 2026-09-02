#!/usr/bin/env python3
"""A mission that self-declared it was done left its coworker permanently
"on mission" — the fifth stop path standDown() forgot.

`useMissionRunner`'s scheduling effect (missions.jsx) calls `standDown(m.agentId)`
from exactly four places when a mission stops running: time-budget expired
(two sites — the scheduling sweep and the fire-time re-check), the
error-streak auto-pause, and the agent-removed guard. Its own comment (just
above `standDown`'s definition) names these as "the four stop paths" a
finished iteration's `status: 'active' · task: 'on mission'` needs cleared
from.

But there is a FIFTH way a mission stops running: `allowSelfComplete` +
the `[MISSION_COMPLETE]` marker, honored once the mission has run at least
60% of its planned iterations (see `runMissionIteration`, which computes
`completed` and returns `{ ok: true, completed }`). That decision happens
INSIDE `runMissionIteration`, not in the scheduling effect's `fire()` —
and `fire()` used to `await runMissionIteration(...)` and discard the
result entirely. The mission card correctly flips to "done," but nothing
ever tells the coworker's desk card the same thing: it stays
`status: 'active'`, caption "on mission," still counted in the header's
"N WORKING" tally and lit on the rooftop, until the user manually
reassigns them.

Fix: `fire()` now captures `runMissionIteration`'s return value and calls
`standDown(m.agentId)` when `result.completed` is true — the same
`standDown` the other four paths already use, just wired to the one
return-value-carried stop reason that was falling on the floor.

Run: python3 scripts/test_a_self_completed_mission_stands_its_coworker_down.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MISSIONS = ROOT / 'missions.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("a mission that self-declares complete stands its coworker down")
    src = MISSIONS.read_text(encoding='utf-8')

    check("runMissionIteration still returns { ok: true, completed } — the "
          "value this fix now actually reads, instead of discarding",
          'return { ok: true, completed };' in src)

    fire_src = src[src.index('const fire = async () => {'):]
    fire_src = fire_src[:fire_src.index('\n      };\n      timersRef.current[m.id]')]

    check("fire() captures runMissionIteration's return value instead of "
          "discarding it — the actual regression: `await "
          "runMissionIteration(...)` with no assignment threw away the "
          "only signal that a mission had just self-completed",
          bool(re.search(
              r'const result = await runMissionIteration\(', fire_src)))

    check("...and calls standDown() when result.completed is true — wiring "
          "the fifth stop reason to the same helper the other four "
          "(time-budget x2, error-streak, agent-removed) already use",
          bool(re.search(
              r'if \(result && result\.completed\) \{\s*\n\s*standDown\(m\.agentId\);',
              fire_src)))

    # ── Regression guard: the four PRE-EXISTING standDown() call sites for
    # the other stop reasons are untouched by this fix ──────────────────
    check("all four pre-existing standDown() call sites are unchanged "
          "(this fix should be purely additive, not a rewrite of the "
          "other stop paths)",
          src.count('standDown(m.agentId);') == 5,
          'expected 5 total: the 4 original sites + this fix\'s new one, '
          'got %d' % src.count('standDown(m.agentId);'))

    check("standDown() itself is unchanged — still guards on agentId/"
          "onUpdateAgent and sets status/mood/task back to idle/standing by",
          "const standDown = (agentId) => {\n"
          "    if (!agentId || !ctx.onUpdateAgent) return;\n"
          "    ctx.onUpdateAgent(agentId, { status: 'idle', mood: 'idle', task: 'standing by' });"
          in src)

    # ── Genuine execution: reimplement the fixed fire()-tail logic (the
    # part after the await) with a stand-in standDown, proving it fires
    # exactly when completed is true and not otherwise. ──────────────────
    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted logic)',
          has_node, 'skipping the live-execution check')
    if has_node:
        # Extract the exact two-statement block this fix added, and run it
        # against both a self-completed and a still-running result — the
        # extracted snippet is executed verbatim, not hand-copied.
        snippet_match = re.search(
            r'const result = await runMissionIteration\([^;]+\);\s*\n'
            r'(?:\s*/\*.*?\*/\s*\n)*'
            r'\s*if \(result && result\.completed\) \{\s*\n'
            r'\s*standDown\(m\.agentId\);\s*\n'
            r'\s*\}',
            fire_src, re.S)
        check('the fixed snippet (await + completed check + standDown) '
              'extracts cleanly from fire()', snippet_match is not None)
        if snippet_match:
            snippet = snippet_match.group(0)
            js = f"""
            async function drive(missionCompleted) {{
              const standDownCalls = [];
              const standDown = (agentId) => {{ standDownCalls.push(agentId); }};
              const m = {{ id: 'mis1', agentId: 'agent42' }};
              const ctxWithSetters = {{}};
              const latest = m;
              const agent = {{ id: 'agent42', name: 'Mira' }};
              const controller = {{ signal: {{}} }};
              async function runMissionIteration(_ctx) {{
                return {{ ok: true, completed: missionCompleted }};
              }}
              {snippet}
              return standDownCalls;
            }}
            (async () => {{
              const completedCase = await drive(true);
              const runningCase = await drive(false);
              console.log(JSON.stringify({{ completedCase, runningCase }}));
            }})();
            """
            r = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=10)
            check('the extracted snippet ran without a Node error',
                  r.returncode == 0, (r.stderr or '').strip()[-800:])
            if r.returncode == 0:
                out = json.loads(r.stdout.strip().splitlines()[-1])
                check("a mission that comes back { completed: true } stands "
                      "its coworker down — the actual bug: this call used "
                      "to never happen at all",
                      out['completedCase'] == ['agent42'], out)
                check("a mission that is still running ({ completed: false }) "
                      "leaves the coworker alone — no spurious standDown on "
                      "every ordinary iteration",
                      out['runningCase'] == [], out)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
