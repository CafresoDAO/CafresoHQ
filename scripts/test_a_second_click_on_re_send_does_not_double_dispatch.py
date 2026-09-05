#!/usr/bin/env python3
"""A second click on the Inbox row's own ↻ RE-SEND, landing before React
re-renders, used to dispatch to the recipient coworker TWICE.

`#388` fixed this exact bug shape one door over (app.jsx's five
client-local approval kinds) and named a fix pattern: a ref-backed Set,
checked and claimed as the very first thing the handler does, closes the
race regardless of what the stale render's state still says. This hunt
went looking for OTHER one-shot handlers with the same shape and found one
`#388` didn't touch: `resendMessage`.

**The bug.** `resendMessage(m, { confirm })` looked self-guarding — it reads
`messagesRef.current` and looks for a message whose `parentId` is `m.id`
(an "already retried" check) before dispatching — but `messagesRef.current`
is only kept in sync with React state by the render-time assignment
`messagesRef.current = messages;`, and the dispatch that would eventually
produce that child message goes through `MessageRegistry.createMessage`,
which only calls `setMessages` (an async, batched React state update). A
second call landing before that update commits and a render runs sees the
EXACT SAME stale `messagesRef.current` the first call saw — "already" is
still undefined — and dispatches again.

The Inbox row's own ↻ RE-SEND button calls `resendMessage(named, { confirm:
false })` (via `onRetryActivity`) — `confirm: false` and a zero `bodyDropped`
skip the `window.hqConfirm` await entirely, so nothing serializes a fast
double-click the way the approval tray's async confirm dialogs incidentally
would for some callers. Reproduced by lifting the REAL `resendMessage` body
out of app.jsx — brace-balanced text extraction, not a re-implementation —
via `scripts/harness_resend_race.mjs`, and calling it twice against one
unchanged snapshot: pre-fix, `dispatchToAgent` — a real dispatch to a real
coworker — fired twice for one failed message.

Fix: a new `resendingIdsRef` (a `Set`, same shape as `#388`'s
`approvedIdsRef`) is checked-and-claimed as the very FIRST thing
`resendMessage` does, synchronously, before `messagesRef.current` is even
read. Unlike `approvedIdsRef` (a card is decided once, full stop),
`resendMessage`'s claim is released again on the two paths that do NOT end
in a real dispatch — recipient no longer hired, or the boss declined the
confirm door — because those are exactly the cases where a LATER retry of
the same message id should still be possible (the agent could be re-hired;
the boss could reconsider). Left claimed after a real dispatch, matching
what `messagesRef` would show anyway once it catches up.

Round 1: structural — the guard exists, sits before `messagesRef.current`
is read, and both non-dispatch return paths release it. Round 2: the real
extracted body, called twice back-to-back, `dispatchToAgent` firing exactly
once. Round 3: a plain single call still dispatches once, AND a declined
confirm still allows a later retry of the same id to go through.

Run: python3 scripts/test_a_second_click_on_re_send_does_not_double_dispatch.py
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
HARNESS = os.path.join(ROOT, "scripts", "harness_resend_race.mjs")

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok    " if cond else "  FAIL  ") + name
          + ((f"  — {detail}") if not cond and detail else ""))
    if not cond:
        FAILS.append(name)


def _extract_balanced(src: str, marker: str) -> str:
    # marker is written to END with the function's own opening brace, so
    # that brace is `marker`'s own last character — searching for the next
    # '{' from `marker`'s START (rather than its end) can instead match one
    # of the braces INSIDE the marker text itself (resendMessage's own
    # destructuring default, `{ confirm = true } = {}`), truncating the
    # extraction to just that literal. See harness_resend_race.mjs for the
    # same fix applied to the .mjs side of this same extraction.
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

    check("resendingIdsRef is declared (a Set, same shape as #388's "
          "approvedIdsRef)",
          re.search(r"const resendingIdsRef = useRefA\(new Set\(\)\)", src) is not None)

    body = _extract_balanced(src, "const resendMessage = async (m, { confirm = true } = {}) => {")

    claim_re = re.compile(
        r"if \(resendingIdsRef\.current\.has\(m\.id\)\) return;\s*"
        r"resendingIdsRef\.current\.add\(m\.id\);", re.DOTALL)
    m = claim_re.search(body)
    check("resendMessage claims m.id before doing anything else", bool(m))
    if m:
        check("...and the claim sits BEFORE messagesRef.current is read "
              "(not after — a guard placed after the read wouldn't close "
              "the window)",
              body.index(m.group(0)) < body.index("messagesRef.current"))

    check("a release() helper is defined right after the claim",
          "const release = () => resendingIdsRef.current.delete(m.id);" in body)

    # The two non-dispatch return paths (recipient gone, confirm declined)
    # must release the claim so a later retry of the SAME message id can
    # still succeed; the "already retried" early-return does NOT need to
    # (it's already permanently blocked by the real messagesRef state, not
    # just by this ref) but releasing there too would be harmless — this
    # only asserts the two paths where NOT releasing would be a real
    # regression (a boss who cancels the confirm door being unable to ever
    # retry that message again).
    recipient_gone = re.search(
        r"if \(!agent\) \{\s*release\(\);", body)
    check("the 'recipient no longer hired' path releases the claim",
          bool(recipient_gone))

    confirm_declined = re.search(
        r"undefined\)\)\) \{ release\(\); return; \}", body)
    check("the declined-confirm path releases the claim",
          bool(confirm_declined))


# ── Round 2: the real extracted resendMessage, called twice ────────────────
def race_checks() -> None:
    print("round 2 — the real resendMessage body, called twice")
    if shutil.which("node") is None:
        check("node is available to run the extracted-source harness", False,
              "no node on PATH — cannot drive the real resendMessage body")
        return
    out = subprocess.run(["node", HARNESS, APP_JSX], cwd=ROOT,
                          capture_output=True, text=True, timeout=60)
    check("harness ran without a node-level error", out.returncode == 0,
          out.stderr.strip()[-800:] if out.returncode != 0 else "")
    lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    check("harness produced the expected 3 scenario results", len(lines) == 3,
          f"got {len(lines)} lines")

    by_scenario = {}
    for line in lines:
        d = json.loads(line)
        by_scenario[d["scenario"]] = d

    d = by_scenario.get("retry-row-confirm-false")
    check("retry-row-confirm-false scenario ran", d is not None)
    if d is not None:
        check("retry-row-confirm-false: extracted resendMessage ran without throwing",
              d["threw"] is None, str(d["threw"])[-400:] if d["threw"] else "")
        n = len(d["calls"].get("dispatchToAgent", []))
        check("retry-row-confirm-false: dispatchToAgent fired exactly once "
              "for two re-entrant resendMessage(m, {confirm:false}) calls "
              "(a second click on ↻ RE-SEND must not dispatch twice)",
              n == 1, f"fired {n} times")

    d = by_scenario.get("single-call-sanity")
    check("single-call-sanity scenario ran", d is not None)
    if d is not None:
        n = len(d["calls"].get("dispatchToAgent", []))
        check("single-call-sanity: one ordinary retry still dispatches exactly once",
              n == 1, f"fired {n} times")

    d = by_scenario.get("declined-confirm-then-retry-succeeds")
    check("declined-confirm-then-retry-succeeds scenario ran", d is not None)
    if d is not None:
        check("declined-confirm-then-retry-succeeds: extracted resendMessage "
              "ran without throwing", d["threw"] is None,
              str(d["threw"])[-400:] if d["threw"] else "")
        n = len(d["calls"].get("dispatchToAgent", []))
        check("declined-confirm-then-retry-succeeds: a boss who declines the "
              "confirm door can still retry the same message afterward "
              "(the claim must be released, not permanent)",
              n == 1, f"fired {n} times")


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
