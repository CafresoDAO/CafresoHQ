#!/usr/bin/env python3
"""Stamping a stale workflow-step approval must not re-run the step (app.jsx).

Bug: the chain-advance that RAISES the "Workflow: run <step>?" card gates on
`nextTask.status === 'inbox'` before dispatching or asking — but the approve
handler for `ap.kind === 'workflow-step'` did not. It ran
`if (nextTask) triggerChainStep(...)` on whatever state the task was in by
stamp time. The card sits in the tray indefinitely, and the board offers
▶ START on the very step the card asks about, so the stale-card path is one
ordinary click away: step 1 completes → the approval card lands → the boss
starts step 2 by hand → it runs to DONE → the boss later clears the tray by
stamping the card → triggerChainStep → onTaskDropOnAgent (which has no
status guard of its own — verified: it reads the task and dispatches
regardless) → the finished step flips back to `doing` and runs a second
time, overwriting its result; a step that was merely `doing` gets a second,
competing run. `workflowStatusBits`/the board then report a done step as in
progress again with nothing anywhere saying why.

Fix: the approve branch now dispatches only when `nextTask.status ===
'inbox'` — the exact gate the chain-advance uses when it raises the card —
and otherwise posts a system chat line saying the step already ran, so the
stamp still visibly does something ("every stamp does something", ledger
2026-08-07) without re-running work.

This lifts the REAL `if (ap.kind === 'workflow-step') {` block out of
app.jsx by brace-balanced extraction (model: test_workspace_terminal_key.py)
and checks the structural invariants directly:
  - triggerChainStep in that block is unreachable unless status === 'inbox'
  - the non-inbox branch still says something to the boss (setChat)
It also lifts the chain-advance site to pin the two gates to the same
sentence, so they cannot quietly diverge again.
Run: python3 scripts/test_a_stamped_workflow_step_only_runs_from_the_inbox.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def extract_block(src, anchor):
    """Brace-balanced extraction of the block opened by `anchor ... {`."""
    m = re.search(re.escape(anchor), src)
    if not m:
        return None
    i = src.find('{', m.end() - 1)
    if i == -1:
        return None
    depth = 0
    j = i
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
        j += 1
    return None


def main():
    print('workflow-step stamp — dispatch gated on the step still being in the inbox')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    text = SRC.read_text(encoding='utf-8')

    # ── The approve branch ────────────────────────────────────────────────
    block = extract_block(text, "if (ap.kind === 'workflow-step')")
    check('workflow-step approve branch extracted from app.jsx', block is not None)
    if block is None:
        print('\n1 failure(s)')
        return 1

    check('branch still dispatches via triggerChainStep',
          'triggerChainStep(' in block)

    # The dispatch must be unreachable without the inbox gate: the
    # triggerChainStep call has to sit inside an if whose condition names
    # nextTask.status === 'inbox'. Structural, not cosmetic — a gate that
    # exists but doesn't guard the call would pass a plain substring test.
    gated = re.search(
        r"if\s*\(\s*nextTask\s*&&\s*nextTask\.status\s*===\s*'inbox'\s*\)\s*\{"
        r"[^{}]*triggerChainStep\(",
        block)
    check("triggerChainStep only runs when nextTask.status === 'inbox'",
          bool(gated), 'dispatch is not inside the inbox-status guard')

    # The regression's exact shape: an UNgated `if (nextTask) triggerChainStep`
    # must never come back.
    ungated = re.search(
        r"if\s*\(\s*nextTask\s*\)\s*(?:\{[^{}]*)?triggerChainStep\(", block)
    check('no ungated `if (nextTask) triggerChainStep(...)` remains',
          not ungated, (ungated.group(0)[:60] if ungated else ''))

    # Every stamp does something: when the step already ran, the boss is told
    # instead of silently no-opping (the ledger's "worst dead end" rule).
    said = re.search(r"else\s+if\s*\(\s*nextTask\s*\)\s*\{[\s\S]*?setChat\(", block)
    check('a stamp on an already-run step still says so in chat (setChat)',
          bool(said))
    check('the note distinguishes done from underway',
          "'done'" in block and 'underway' in block)

    # ── The gate it must mirror ───────────────────────────────────────────
    # The chain-advance that raises the card checks the same sentence; pin it
    # so the two ends of the hand-off cannot diverge again.
    advance = re.search(
        r"nextTask\s*&&\s*nextTask\.status\s*===\s*'inbox'", text)
    check("chain-advance still gates on nextTask.status === 'inbox' too",
          bool(advance))

    print()
    print(('FAILED: %s' % FAILS) if FAILS
          else 'stamped workflow step inbox gate: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
