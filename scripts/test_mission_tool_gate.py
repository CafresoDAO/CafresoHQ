#!/usr/bin/env python3
"""The Research modal told a fully-equipped coworker to go turn tools on.

Two faults on one row of `missions.jsx`, and the first is the worse one.

**The hint rendered unconditionally.** Measured live on the real office with
Vera selected — who holds web, email, cal AND vault, whose row is not
disabled, and who can start a mission immediately — the modal still read:

    NEEDS WEB SEARCH AND VAULT NOTES — TURN THEM ON IN SETTINGS → ROSTER

The office instructing a boss to fix something that is not broken is the same
fault as a structural verdict about a graph with no shape: a true-sounding
sentence bolted to a case it does not describe.

**And the dropdown disagreed with itself.** The row said "(needs Web + Vault
tools)" — the MODE's requirement — while the sentence under it said only
Vault Notes, which is what that coworker actually lacked. Measured on a
zero-config office where Llama arrives with `['web']`.

**And the way forward was a treasure map.** "Turn them on in Settings →
Roster" is not a route out for the §3 zero-config boss, who has never opened
Settings. The tools are now handed over on the spot, by name, with the
consequence stated — the same `onUpdateAgent` the Roster uses, so nothing is
granted that the boss could not already grant; it just no longer requires
knowing the app's furniture.

Note what this deliberately does NOT do: it does not make a detected brain
ARRIVE with Vault Notes on. That is a real permissions question about write
access to the boss's cabinet, and it stays the boss's to answer.

The gate itself is correct and must stay. In-tab Research runs on the
BROWSER's per-agent tool registry, so an ungated run silently delivers
nothing — `missions.jsx` records the measurement: a 15-minute mission on
Llama reached round 4, claimed "Wrote 1" in its own transcript, and left
`writes: null` and no Research/ directory. (The Night Shift runs server-side
in night_runner.py and used to grant the vault write without consulting
`agent.tools` at all, on the theory that unifying the two gates would take
the overnight feature away from every front-desk hire. #360 reversed that:
an unrestricted server-side write is the bigger hole, and the two paths now
enforce the SAME roster grant through two different, non-unified mechanisms
— see the section below.)

Runs the REAL helpers by extracting them from missions.jsx and evaluating
them under node, rather than restating their logic here.

Run: python3 scripts/test_mission_tool_gate.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'missions.jsx'
APP = ROOT / 'app.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract_helpers(text):
    """Pull the real TOOL_LABEL/neededTools/missingTools/canDoMode block."""
    start = text.find('  const TOOL_LABEL =')
    end = text.find('\n', text.find('  const canDoMode ='))
    if start < 0 or end < 0:
        return None
    return text[start:end]


def run_js(helpers, cases):
    proc = subprocess.run(
        ['node', '--input-type=module', '-e', 'let mode;\n' + helpers + '\n' + cases],
        cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('mission tool gate — say it only when true, and then open the door')
    if not SRC.is_file() or not APP.is_file():
        print('  FAIL  missing source file(s)')
        return 1
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    text = SRC.read_text(encoding='utf-8')
    helpers = extract_helpers(text)
    if not helpers:
        print('  FAIL  could not find the TOOL_LABEL…canDoMode block in missions.jsx')
        return 1

    out = run_js(helpers, r'''
const R = {};
const A = (tools) => ({ id: 'a', name: 'Llama', tools });
mode = 'research';
R.rVera      = missingTools(A(['web','email','cal','vault']));
R.rLlama     = missingTools(A(['web']));
R.rCli       = missingTools(A(['files','shell','web']));
R.rBare      = missingTools(A([]));
R.rNoTools   = missingTools({ id: 'x', name: 'X' });
R.rNull      = missingTools(null);
R.canVera    = canDoMode(A(['web','email','cal','vault']));
R.canLlama   = canDoMode(A(['web']));
mode = 'project-study';
R.sVera      = missingTools(A(['web','email','cal','vault']));
R.sLlama     = missingTools(A(['web']));
R.sVaultOnly = missingTools(A(['vault']));
R.canStudyVaultOnly = canDoMode(A(['vault']));
R.labels     = TOOL_LABEL;
console.log(JSON.stringify(R));
''')

    # ── The false alarm: a capable coworker must have nothing to say ────
    check('a fully-equipped coworker is missing nothing (research)',
          out['rVera'] == [],
          f"got {out['rVera']!r} — Vera holds web+vault and can start right now; "
          'anything non-empty here is the modal telling her boss to go fix '
          'something that is not broken')
    check('...and the same coworker passes a project study',
          out['sVera'] == [] and out['canStudyVaultOnly'] is True,
          f"got {out['sVera']!r}")

    # ── Naming WHAT is missing, per coworker, not per mode ──────────────
    check('a web-only hire is missing exactly Vault Notes, not "Web + Vault"',
          out['rLlama'] == ['vault'],
          f"got {out['rLlama']!r} — this is the front-desk hire shape; naming the "
          "MODE's requirement made the dropdown row disagree with the sentence "
          'directly under it')
    check('a CLI hire (files/shell/web) is also missing exactly Vault Notes',
          out['rCli'] == ['vault'],
          f"got {out['rCli']!r}")
    check('a coworker with nothing is missing both, in a stable order',
          out['rBare'] == ['web', 'vault'],
          f"got {out['rBare']!r} — order matters, the copy joins these into a "
          'sentence')
    check('a project study asks only for Vault Notes',
          out['sLlama'] == ['vault'] and out['sVaultOnly'] == [],
          f"research/study must not share one requirement list: got "
          f"{out['sLlama']!r} / {out['sVaultOnly']!r}")

    # ── Degenerate agents must not crash the render ─────────────────────
    check('an agent with no tools key, and a null agent, are handled',
          out['rNoTools'] == ['web', 'vault'] and out['rNull'] == ['web', 'vault'],
          f"got {out['rNoTools']!r} / {out['rNull']!r} — this runs during render, "
          'before a selection exists')

    # ── canDoMode must still gate. The gate is CORRECT: in-tab research ──
    # ── on a vault-less agent runs its full duration and writes nothing. ─
    check('canDoMode still blocks a web-only hire from in-tab research',
          out['canLlama'] is False and out['canVera'] is True,
          'the gate is not the bug — an ungated run reached round 4, reported '
          '"Wrote 1" and left writes: null')

    # ── Copy: office words, not tool ids ────────────────────────────────
    check('the tools are named in the boss\'s words',
          out['labels'].get('web') == 'Web Search' and out['labels'].get('vault') == 'Library',
          f"got {out['labels']!r} — §6: no raw tool ids in UI copy")

    # ── Render-level: the hint is conditional and hands the tool over ───
    check('the hint returns null when nothing is missing',
          re.search(r'if\s*\(!selectedAgent\s*\|\|\s*miss\.length\s*===\s*0\)\s*return null', text) is not None,
          'missions.jsx: without this guard the sentence renders over a coworker '
          'who can already start')
    check('the row names the coworker\'s own gap, not the mode\'s',
          re.search(r'needs \$\{missingTools\(a\)', text) is not None,
          'missions.jsx: a static "(needs Web + Vault tools)" disagrees with the '
          'sentence under it')
    check('the missing tools can be granted from the modal',
          re.search(r'onUpdateAgent\(selectedAgent\.id,\s*\n?\s*\{\s*tools:', text) is not None,
          'missions.jsx: "turn them on in Settings → Roster" is a treasure map, '
          'not a way forward')
    check('...and the grant is wired from app.jsx',
          re.search(r'<MissionsModal[\s\S]{0,600}?onUpdateAgent=\{onUpdateAgent\}', APP.read_text(encoding='utf-8')) is not None,
          'app.jsx: the button renders only when the prop is passed, so an '
          'unwired prop silently removes the way forward')
    check('granting says what it costs the boss',
          'file their work into your cabinet' in text,
          'missions.jsx: this is write access to the vault — a permission asked '
          'for without stating it is not consent')
    check('coworkers are people, not "it"',
          "they need {names}" in text and "it needs {names}" not in text,
          'missions.jsx: §2 casts these as coworkers')

    # ── The Night Shift's grant is REVERSED as of #360 ──────────────────
    #
    # Everything above this line still holds: the two mission paths run in
    # different places (browser vs. server) and must not share ONE gating
    # mechanism. What changed is whether the server-side runner may ignore
    # the Roster at all. It used to, on purpose — this file said so, twice,
    # and a prior attempt to add a gate here was reverted for exactly the
    # reason quoted below. #360 reversed that call: a scheduled mission
    # writing into the boss's Library on behalf of a coworker the boss never
    # ticked "read your Library" for is a bigger hole than the convenience
    # it was buying front-desk hires, and it is now closed. See #360 in
    # docs/OFFICE_AS_INTERFACE.md for the full account, including why the
    # gate is fail-closed on an agent the roster can no longer find.
    night = (ROOT / 'night_runner.py').read_text(encoding='utf-8')
    check('the Night Shift now DOES consult what the boss granted',
          re.search(r"may_write_to_vault\(ctx\.agent_tools\)", night) is not None,
          'night_runner.py: #360 gates VAULT_APPEND/VAULT_NEW on the '
          'dispatched coworker\'s real grants — a web-only front-desk hire '
          'now gets the same overnight-vault refusal a boss would see from '
          'them by day, instead of a silent bypass')
    check('...and a missing grant reads as a refusal the ledger cannot mistake for a note',
          re.search(r"_VAULT_FAIL_PREFIX,\s*\n?\s*NIGHT_VAULT_FORBIDDEN", night) is not None,
          'night_runner.py: the refusal must be shaped as a vault_write_status '
          'failure, or run_iteration counts a None as a landed note and the '
          'morning report names a write the Library never saw')

    print()
    if FAILS:
        print(f'mission tool gate: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('mission tool gate: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
