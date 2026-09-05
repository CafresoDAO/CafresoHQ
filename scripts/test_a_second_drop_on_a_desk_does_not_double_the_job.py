#!/usr/bin/env python3
"""A second drop on the same desk, for the same card, landing before React
re-renders, used to run the real dispatch twice.

## 389's own sweep flagged `onTaskDropOnAgent` for this hunt series' shape —
read from state to find "the thing to act on," then run a real side effect,
with no ref claimed first — but judged it "not independently guarded, but
bounded — a double-drop is caught by beginAgentRun's own eviction (second
dispatch aborts the first's controller before real work happens) rather than
any guard in the handler itself," and deferred a real harness-based check to
a future hunt. This is that hunt, and the claim did not hold up.

**The bug.** `displacedTask` (hq-runtime.jsx) deliberately excludes the
task's OWN id (`t.id !== taskId`) from "is this coworker already working on
something a new start would displace" — that exclusion exists so a chain's
own hand-off (the finishing step still in the registry while it dispatches
the next one) doesn't misread itself as an interruption. But it means a
SAME-task double-drop — the ▶ START button in `features.jsx` has no disabled
state and no debounce (`onClick={(e) => { e.stopPropagation();
onStartTask(t.id, a); }}`), the exact physical shape as ## 388's stamp
double-click — never lands on the `displaced` branch. It falls to `chatCut`
instead, whose own comment claims "every cardless registrant is a chat
surface" — false here, since the registrant IS this task's own just-started
run — and shows a dialog that lies about why ("... is mid-conversation in
chat ... Their reply stops where it is, and the rest of it is lost") with an
OK button reading "Start it" — exactly what a boss who meant to click
▶ START once, and got an unexpected dialog, would click through. Confirming
it runs `onTaskDropOnAgent` a second time: `beginAgentRun` DOES evict the
first run's controller, but only AFTER the first `HQ.agentStream` call has
already fired — the eviction happens too late to stop it.

Reproduced by lifting the REAL `onTaskDropOnAgent` (plus the REAL
`beginAgentRun`/`endAgentRun` and the REAL `displacedTask`) out of the
source — brace-balanced text extraction, not a re-implementation — via
`scripts/harness_taskdrop_race.mjs`, and calling it twice back-to-back
against one unchanged snapshot. Pre-fix, `HQ.agentStream` — a real call to a
real model — fired twice for one card.

Fix: a new `startingTaskIdsRef` (a `Set` keyed by taskId, same shape as
## 388's `approvedIdsRef` and ## 389's `resendingIdsRef`) is
checked-and-claimed as the very FIRST thing `onTaskDropOnAgent` does,
synchronously, before `task` is even looked up. A second call for a taskId
already mid-start is a silent no-op. Released on every path that does NOT
end in a real dispatch (task not found, displaced-and-declined,
chat-cut-and-declined, either auto no-op) and in the run's own `finally` —
so a task that finishes, or is genuinely restarted later, can still be
dropped again.

Round 1: structural — the guard exists, sits before `task` is looked up, and
every early-return path (including the `finally`) releases it. Round 2: the
real extracted bodies, called twice (and three times) for the same
(task, agent) pair, `HQ.agentStream` firing exactly once. Round 3: a plain
single drop is unaffected. Round 4: a genuinely DIFFERENT task dropped on
the same busy desk still reaches the legitimate interrupt-and-replace
confirm flow (a different taskId is never already claimed).

Run: python3 scripts/test_a_second_drop_on_a_desk_does_not_double_the_job.py
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
HQ_RUNTIME_JSX = os.path.join(ROOT, "hq-runtime.jsx")
HARNESS = os.path.join(ROOT, "scripts", "harness_taskdrop_race.mjs")

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok    " if cond else "  FAIL  ") + name
          + ((f"  — {detail}") if not cond and detail else ""))
    if not cond:
        FAILS.append(name)


def _extract_balanced(src: str, marker: str) -> str:
    # The marker must END with the function's own opening brace ("=> {") —
    # searching for the first '{' after `start` (as a naive scan would) can
    # instead match a brace INSIDE the marker text itself. onTaskDropOnAgent's
    # own signature has exactly this trap: `opts = {}) => {` — the `{}` of
    # the default parameter is the first brace after `start`, and a naive
    # scan would extract nothing (##388/##389 hit the same trap for
    # resendMessage's `{ confirm = true } = {}`).
    assert marker.endswith("{"), "marker must end with the function's opening brace"
    start = src.index(marker)
    brace_start = start + len(marker) - 1
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

    check("startingTaskIdsRef is declared (a Set, same shape as the other "
          "one-outstanding-thing refs in this file)",
          re.search(r"const startingTaskIdsRef = useRefA\(new Set\(\)\)", src) is not None)

    body = _extract_balanced(
        src, "const onTaskDropOnAgent = async (taskId, agent, taskFresh, opts = {}) => {")

    claim_re = re.compile(
        r"if \(startingTaskIdsRef\.current\.has\(taskId\)\) return;\s*"
        r"startingTaskIdsRef\.current\.add\(taskId\);", re.DOTALL)
    m = claim_re.search(body)
    check("onTaskDropOnAgent claims the taskId before doing anything else", bool(m))
    if m:
        check("...and the claim sits BEFORE `task` is even looked up (not "
              "after — a guard placed after the read wouldn't close the window)",
              body.index(m.group(0)) < body.index("const task ="))

    check("releaseStartClaim is defined right after the claim",
          "const releaseStartClaim = () => startingTaskIdsRef.current.delete(taskId);" in body)

    # Every early-return branch before the real dispatch must release the
    # claim — a guard that only claims and never releases would turn one
    # failed/declined/auto-parked drop into a permanently stuck card.
    early_return_release_sites = [
        "if (!task) { releaseStartClaim(); return; }",
        "releaseStartClaim();\n      return;\n    }\n    if (displaced) {",
        "if (!ok) { releaseStartClaim(); return; }\n      setTasks(prev => prev.map(t => t.id === displaced.id",
        "releaseStartClaim();\n      return;\n    }\n    if (chatCut) {",
    ]
    for site in early_return_release_sites:
        check(f"early-return path releases the claim: {site.splitlines()[0][:60]}...",
              site in body)
    check("the declined chat-cut confirm also releases the claim",
          re.search(r"okLabel: 'Start it' \}\);\s*\n\s*if \(!ok\) \{ releaseStartClaim\(\); return; \}\s*\n\s*\}\s*\n\s*\n\s*/\* Starting clears the note",
                    body) is not None)

    check("the run's own finally releases the claim (so a finished — or "
          "genuinely restarted — task can be dropped again)",
          re.search(r"endAgentRun\(agent\.id, controller\);\s*releaseStartClaim\(\);\s*\}",
                    body) is not None)


# ── Round 2: the real extracted onTaskDropOnAgent, called twice/three times ─
def race_checks() -> None:
    print("round 2 — the real onTaskDropOnAgent body, called twice/three times for one card")
    if shutil.which("node") is None:
        check("node is available to run the extracted-source harness", False,
              "no node on PATH — cannot drive the real onTaskDropOnAgent body")
        return
    out = subprocess.run(["node", HARNESS, APP_JSX, HQ_RUNTIME_JSX], cwd=ROOT,
                          capture_output=True, text=True, timeout=60)
    check("harness ran without a node-level error", out.returncode == 0,
          out.stderr.strip()[-800:] if out.returncode != 0 else "")
    lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    check("harness produced one result per scenario", len(lines) == 4,
          f"got {len(lines)} lines")

    by_scenario = {}
    for line in lines:
        d = json.loads(line)
        by_scenario[d["scenario"]] = d
        check(f"{d['scenario']}: extracted onTaskDropOnAgent ran without throwing",
              d["threw"] is None, str(d["threw"])[-400:] if d["threw"] else "")

    for name, n_expected in (
        ("same-task-same-agent-double-drop", 1),
        ("same-task-same-agent-triple-drop", 1),
        ("single-call-sanity", 1),
    ):
        d = by_scenario.get(name)
        check(f"{name}: scenario present", d is not None)
        if not d:
            continue
        n = len(d["calls"].get("agentStream", []))
        check(f"{name}: HQ.agentStream (a real call to a real model) fired "
              f"exactly once", n == n_expected, f"fired {n} times")

    d = by_scenario.get("two-different-tasks-same-agent-confirmed")
    check("two-different-tasks-same-agent-confirmed: scenario present", d is not None)
    if d:
        n = len(d["calls"].get("agentStream", []))
        check("two-different-tasks-same-agent-confirmed: a genuinely "
              "DIFFERENT card still dispatches once the boss confirms — "
              "the taskId-keyed claim must not block a different taskId",
              n == 2, f"fired {n} times")


if __name__ == "__main__":
    structural_checks()
    race_checks()
    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED:")
        for f in FAILS:
            print(f"  - {f}")
        sys.exit(1)
    print("all checks passed")
