#!/usr/bin/env python3
"""A second click on APPROVE (or REJECT), landing before React re-renders,
used to run the real side effect twice.

A prior hunt into approval double-fire found the SERVER-backed external-tool
flow (`/approvals/external/decide`, Claude Code's PreToolUse hook bridge)
already safe — it atomically claims a pending item under a lock before
executing, confirmed against real concurrent HTTP requests — and explicitly
left one door unchecked: app.jsx's five CLIENT-LOCAL approval kinds
(`publish`, `hire-agent`, `hire-assistant`, `grant-elevation`,
`workflow-step`). These never touch a shared server-side pending list; they
live purely in one browser tab's own React state, seeded by
`onApprovalRequest` and decided by `onApprove`/`onReject`.

**The bug.** `onApprove(id)` looked self-guarding —
`setApprovals(prev => prev.filter(p => p.id !== id))` runs before the
side-effecting branch — but that filter only protects the NEXT render.
`onApprove` closes over THIS render's `approvals` (and `agents`, and
`tasks`), and the ApprovalTray/AgentInbox buttons that call it
(`features.jsx`'s `<button onClick={()=>onApprove(p.id)}>`,
`views/core.jsx`'s mirror) carry no disabled state and no debounce. A second
call for the same id — a fast double-click, or a duplicate synthetic click
event off a fast double-tap — landing before React has committed the
`setApprovals` update and rebound the button to a fresh closure sees the
SAME stale `approvals` array, with the card still "pending," and re-runs
every side effect: a second agent hired off one proposal, a second
elevation-granted dispatch nudging an agent to redo a real file/shell turn,
a second workflow chain-step trigger re-running already-started work, a
second publishSite upload for one stamp. Exactly the ## 387 bug shape one
door over: not double-billed tokens, a duplicated deliverable.

Reproduced below by lifting the REAL `onApprove` (and `onReject`) function
bodies out of app.jsx — brace-balanced text extraction, not a
re-implementation — via `scripts/harness_onapprove_race.mjs`, then calling
each twice against one unchanged snapshot (the exact shape of a second
click landing before any state update from the first would have taken
effect), once per approval kind, checking the real side-effecting mock
(onHire / onUpdateAgent+dispatchToAgent / triggerChainStep / publishSite)
fires exactly once.

Fix: a new `approvedIdsRef` (a `Set`, same shape as the file's own
`pendingHiresRef`/`pendingElevationRef`) is checked-and-claimed as the very
FIRST thing both `onApprove` and `onReject` do, synchronously, before
`approvals.find` even runs — so a second re-entrant call for an id already
claimed no-ops regardless of what the stale `approvals` closure still says.

Round 1: structural — the guard exists, sits before `approvals.find` in
both handlers, and both handlers claim into the SAME ref (a card is decided
once, whichever way). Round 2: the real extracted bodies, called twice per
approval kind, each side effect firing exactly once. Round 3: a plain
single approve/reject is unaffected (one call still does its one thing).

Run: python3 scripts/test_a_second_click_on_a_stamp_does_not_double_the_action.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_JSX = os.path.join(ROOT, "app.jsx")
HARNESS = os.path.join(ROOT, "scripts", "harness_onapprove_race.mjs")

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok    " if cond else "  FAIL  ") + name
          + ((f"  — {detail}") if not cond and detail else ""))
    if not cond:
        FAILS.append(name)


def _extract_balanced(src: str, marker: str) -> str:
    start = src.index(marker)
    brace_start = src.index("{", start)
    depth = 0
    for k in range(brace_start, len(src)):
        c = src[k]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[brace_start + 1:k]
    raise AssertionError("unbalanced braces for marker: " + marker)


# ── Round 1: structural ────────────────────────────────────────────────────
def structural_checks() -> None:
    print("round 1 — the fix is really in the source")
    src = open(APP_JSX, encoding="utf-8").read()

    check("approvedIdsRef is declared (a Set, same shape as the other "
          "one-outstanding-thing refs in this file)",
          re.search(r"const approvedIdsRef = useRefA\(new Set\(\)\)", src) is not None)

    on_approve = _extract_balanced(src, "const onApprove = (id) => {")
    on_reject = _extract_balanced(src, "const onReject = (id) => {")

    claim_re = re.compile(
        r"if \(approvedIdsRef\.current\.has\(id\)\) return;\s*"
        r"approvedIdsRef\.current\.add\(id\);", re.DOTALL)

    m1 = claim_re.search(on_approve)
    check("onApprove claims the id before doing anything else", bool(m1))
    if m1:
        check("...and the claim sits BEFORE approvals.find (not after — a "
              "guard placed after the read wouldn't close the window)",
              on_approve.index(m1.group(0)) < on_approve.index("approvals.find"))

    m2 = claim_re.search(on_reject)
    check("onReject claims the id the same way (a card is decided once, "
          "whichever way — the second handler needs the same lock)", bool(m2))
    if m2:
        check("...also before its own approvals.find",
              on_reject.index(m2.group(0)) < on_reject.index("approvals.find"))


# ── Round 2: the real extracted onApprove, called twice per kind ──────────
def race_checks() -> None:
    print("round 2 — the real onApprove body, called twice, per approval kind")
    if shutil.which("node") is None:
        check("node is available to run the extracted-source harness", False,
              "no node on PATH — cannot drive the real onApprove body")
        return
    out = subprocess.run(["node", HARNESS, APP_JSX], cwd=ROOT,
                          capture_output=True, text=True, timeout=60)
    check("harness ran without a node-level error", out.returncode == 0,
          out.stderr.strip()[-800:] if out.returncode != 0 else "")
    lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    check("harness produced one result per approval kind", len(lines) == 5,
          f"got {len(lines)} lines")

    expect = {
        "hire-agent": ("onHire", "a second HIRE_AGENT approval must not hire twice"),
        "hire-assistant": ("onHire", "a second HIRE_ASSISTANT approval must not hire twice"),
        "grant-elevation": ("onUpdateAgent", "a second GRANT_ELEVATION approval must not "
                             "re-grant / re-dispatch the resume nudge twice"),
        "workflow-step": ("triggerChainStep", "a second workflow-step approval must not "
                           "re-trigger the same chain step"),
        "publish": ("publishSite", "a second PUBLISH approval must not upload twice"),
    }

    seen = set()
    for line in lines:
        d = json.loads(line)
        scenario = d["scenario"]
        seen.add(scenario)
        check(f"{scenario}: extracted onApprove ran without throwing",
              d["threw"] is None, str(d["threw"])[-400:] if d["threw"] else "")
        if d["threw"] is not None:
            continue
        key, why = expect[scenario]
        n = len(d["calls"].get(key, []))
        check(f"{scenario}: {key} fired exactly once for two re-entrant "
              f"onApprove(id) calls ({why})", n == 1, f"fired {n} times")
        # dispatchToAgent is grant-elevation's SECOND real side effect (the
        # onUpdateAgent flag-flip is idempotent by itself; the dispatch that
        # nudges the agent to redo real elevated work is the consequential
        # half) — check it too.
        if scenario == "grant-elevation":
            nd = len(d["calls"].get("dispatchToAgent", []))
            check("grant-elevation: dispatchToAgent (the real 'resume with "
                  "your new tools' nudge) fired exactly once", nd == 1,
                  f"fired {nd} times")

    check("every expected approval kind was exercised",
          seen == set(expect), f"missing {set(expect) - seen}")


# ── Round 3: a plain single call is unaffected ─────────────────────────────
def sanity_single_call_checks() -> None:
    print("round 3 — a plain single approve is unaffected")
    if shutil.which("node") is None:
        check("node is available", False, "no node on PATH")
        return
    script = r"""
    const fs = require('fs');
    const path = process.argv[1];
    const src = fs.readFileSync(path, 'utf8');
    function extract(marker) {
      const start = src.indexOf(marker);
      const bs = src.indexOf('{', start);
      let depth = 0;
      for (let k = bs; k < src.length; k++) {
        if (src[k] === '{') depth++;
        else if (src[k] === '}') { depth--; if (depth === 0) return src.slice(bs+1, k); }
      }
      throw new Error('unbalanced');
    }
    const body = extract('const onApprove = (id) => {');
    const PARAM_NAMES = ['approvals','setApprovals','clearApprovalNotice','recordReceipt',
      'setChat','HQ','CafresoHQClient','settleReceipt','logActivity','officeCause','say',
      'pendingHiresRef','agents','onHire','downgradeElevatedModel','brainName',
      'pendingAssistantHiresRef','pendingElevationRef','onUpdateAgent','dispatchToAgent',
      'tasks','triggerChainStep','decideExternal','approvedIdsRef'];
    const fn = new Function(...PARAM_NAMES, 'id', body);
    let hireCount = 0;
    const world = {
      approvals: [{ id: 'ap1', kind: 'hire-agent',
        hireProposal: { proposedBy: 'x', name: 'N', role: 'r', proposedByName: 'X', rationale: 'r' } }],
      setApprovals: () => {}, clearApprovalNotice: () => {}, recordReceipt: () => 'rc',
      setChat: () => {}, HQ: { uid: (p) => p + '-1', AGENT_COLORS: ['red'] },
      CafresoHQClient: { publishSite: async () => ({}), getSettings: () => ({}) },
      settleReceipt: () => {}, logActivity: () => {}, officeCause: (m) => m, say: () => {},
      pendingHiresRef: { current: new Set() }, agents: [{ id: 'x', name: 'X' }],
      onHire: () => { hireCount++; }, downgradeElevatedModel: (m) => ({ model: m, swapped: false }),
      brainName: () => 'b', pendingAssistantHiresRef: { current: new Set() },
      pendingElevationRef: { current: new Set() }, onUpdateAgent: () => {},
      dispatchToAgent: () => {}, tasks: [], triggerChainStep: () => {},
      decideExternal: async () => {}, approvedIdsRef: { current: new Set() },
    };
    fn(...PARAM_NAMES.map(n => world[n]), 'ap1');
    console.log(JSON.stringify({ hireCount }));
    """
    out = subprocess.run(["node", "-e", script, APP_JSX], cwd=ROOT,
                          capture_output=True, text=True, timeout=30)
    check("single-call harness ran cleanly", out.returncode == 0,
          out.stderr.strip()[-600:] if out.returncode != 0 else "")
    if out.returncode == 0:
        d = json.loads(out.stdout.strip().splitlines()[-1])
        check("one ordinary approve still hires exactly one agent",
              d["hireCount"] == 1, f"got {d['hireCount']}")


if __name__ == "__main__":
    structural_checks()
    race_checks()
    sanity_single_call_checks()
    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED:")
        for f in FAILS:
            print(f"  - {f}")
        sys.exit(1)
    print("all checks passed")
