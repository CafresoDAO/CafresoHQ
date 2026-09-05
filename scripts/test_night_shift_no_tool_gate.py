#!/usr/bin/env python3
"""The Night Shift is open to every hire; in-tab Research is not. Both on purpose.

OFFICE_AS_INTERFACE.md's "Known open" list carried a bullet titled "A
front-desk hire cannot run a Night Shift", claiming the §3 zero-config path
"cannot use the headline overnight feature until someone visits Settings →
Roster". Driven live 2026-08-12: scheduled a real Night Shift on Llama —
`tools: ['web']`, no Vault Notes, exactly the front-desk-hire shape the
bullet said was blocked — and it ran, wrote a run record with a real
summary, and showed up on the office floor board. The bullet was written
from the in-tab Research gate and generalised to a feature that has never
shared its toolset.

The two really are different, and this file pins BOTH halves so neither
drifts into the other:

  · In-tab Research runs on the BROWSER's per-agent tool registry, so its
    picker must stay gated — `canDoMode()` disables options and labels them
    "(needs Web + Vault tools)". Ungating it would resurrect the measured
    failure the gate exists for: a 15-minute mission on a web-only brain
    that reached round 4, reported "Wrote 1", and left no Research/ folder.

  · The Night Shift runs server-side in night_runner.py, whose `run_tool()`
    grants VAULT_NEW/VAULT_APPEND unconditionally — it never reads
    `agent.tools`. Its picker matches: every hire selectable, and no TOOL
    gate on 🌙 SCHEDULE or ▶ RUN NOW. Adding one here would block a path
    that demonstrably works.

NARROWED BY #301, deliberately, and stated here so nobody has to guess.
The three assertions below used to read `'disabled' not in <slice>` — a
blanket ban on the attribute, standing in for the rule this file actually
holds, which is "no PER-AGENT TOOL gate". #301 found the other thing that
slice was silently promising: with an EMPTY roster the picker painted an
option-less `<select>` and both buttons stayed live, taking a click and
answering `topic + agent required`. Gating on "is anybody hired at all" is
not a tool gate — it is not per-agent, it cannot block a coworker the
server would have accepted, and it refuses only the case where there is no
coworker to accept. So the checks now name the tool-gating machinery
(`canDoMode`, `missingTools`, `agent.tools`) and pin the one `disabled`
that is allowed to appear, instead of banning the word. The original rule
is intact and, if anything, harder to get past: `disabled={!canDoMode(...)}`
in either place still fails, where before only the substring mattered.

Run: python3 scripts/test_night_shift_no_tool_gate.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MISSIONS = ROOT / 'missions.jsx'
RUNNER = ROOT / 'night_runner.py'
DOC = ROOT / 'docs' / 'OFFICE_AS_INTERFACE.md'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('night shift tool gate — open to every hire, unlike in-tab Research')
    for p in (MISSIONS, RUNNER, DOC):
        if not p.is_file():
            print(f'  FAIL  missing {p}')
            return 1
    missions = MISSIONS.read_text(encoding='utf-8')
    runner = RUNNER.read_text(encoding='utf-8')
    doc = DOC.read_text(encoding='utf-8')

    # ── the server-side runner never consults per-agent tools ──────────────
    run_tool = missions_slice = runner[runner.find('def run_tool('):]
    run_tool = run_tool[:run_tool.find('\ndef ', 1)]
    check("night_runner.run_tool() grants VAULT_NEW/VAULT_APPEND with no tool check",
          bool(re.search(r"if name in \('VAULT_APPEND', 'VAULT_NEW'\):", run_tool))
          and 'agent.tools' not in run_tool and "sched.get('tools'" not in run_tool,
          'night_runner.py: the night toolset is fixed and server-side — if '
          'this ever starts reading the agent\'s configured tools, the '
          'Night Shift picker needs a gate to match')

    # ── the Night Shift picker stays ungated, matching the runner ──────────
    ns = missions[missions.find('function NightShiftSection('):]
    ns = ns[:ns.find('\nfunction MissionsModal(')]
    # `[\s\S]*?` rather than an immediate `<select>`: since #301 the picker
    # sits behind a no-crew note, so the <select> is no longer the first
    # thing after the label. What matters is that it is still in there.
    picker = re.search(r'<label>COWORKER</label>[\s\S]*?</select>', ns)
    check('the Night Shift COWORKER picker exists', bool(picker))
    picker_body = picker.group(0) if picker else ''
    check('...and lists every hire with no tool-gated option',
          not re.search(r'<option[^>]*\bdisabled', picker_body)
          and 'canDoMode' not in picker_body
          and 'missingTools' not in picker_body,
          'missions.jsx: night_runner grants vault access to whoever runs, so '
          'gating this picker would block a path that demonstrably works')
    # The two action buttons live in one flex row; scope to it exactly rather
    # than eyeballing a character window around the labels.
    action_row = ns[ns.find("<div style={{ display: 'flex', gap: 8, marginTop: 8, alignItems: 'center' }}>"):]
    action_row = action_row[:action_row.find('</div>')]
    check('the action row really contains both Night Shift buttons',
          '🌙 SCHEDULE' in action_row and '▶ RUN NOW' in action_row,
          'test scoping is wrong — the slice below would be meaningless')
    check('neither 🌙 SCHEDULE nor ▶ RUN NOW is tool-gated',
          'canDoMode' not in action_row
          and 'missingTools' not in action_row
          and '.tools' not in action_row,
          'missions.jsx: same reason as the picker — the server side has no '
          'per-agent gate to enforce, so blocking here would be a lie')
    # The one gate these buttons ARE allowed: an office with nobody hired.
    # Pinned by exact text so a tool gate cannot arrive wearing its clothes.
    stray = [d for d in re.findall(r'disabled=\{[^}]*\}\}?', action_row)
             if d != 'disabled={!!noCrewNote(agents)}']
    check('...and the only gate on them is "nobody is hired yet"',
          not stray, stray)

    # ── in-tab Research keeps its gate (the failure it was built for) ──────
    modal = missions[missions.find('function MissionsModal('):]
    check("in-tab Research still gates its picker on canDoMode()",
          bool(re.search(r'<option key=\{a\.id\} value=\{a\.id\} disabled=\{!canDoMode\(a\)\}', modal)),
          'missions.jsx: this gate exists for a MEASURED failure (a web-only '
          'brain ran a full mission and wrote nothing) — do not remove it '
          'just because the Night Shift has no equivalent')
    check("...and still names the missing tools in the option label",
          "needs Web + Vault tools" in modal,
          'missions.jsx: §7 — a blocked choice must say why')

    # ── the ledger no longer claims the Night Shift is blocked ─────────────
    check("the doc's Known-open bullet is scoped to Research, not the Night Shift",
          '**A front-desk hire cannot run a Night Shift.**' not in doc
          and '**A front-desk hire cannot run a browser Research mission.**' in doc,
          'docs/OFFICE_AS_INTERFACE.md: the old title claimed a working '
          'feature was broken — an honesty ledger that overstates breakage '
          'is still wrong')

    print()
    if FAILS:
        print(f'night shift tool gate: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('night shift tool gate: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
