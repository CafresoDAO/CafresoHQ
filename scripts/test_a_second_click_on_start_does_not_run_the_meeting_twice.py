#!/usr/bin/env python3
"""A second click on ▶ START (stand-up) or SEND (meeting room), landing
before React re-renders, used to run the WHOLE round twice.

`## 388`, `## 389` and `## 390` each fixed one handler whose "has this
already happened" guard read a value that does not update synchronously —
and each of the three discovered that the PREVIOUS fix's cited
"already-safe" example was itself broken. `## 390` closed the last door that
series named. This hunt swept the rest of the client for the same shape and
found the two biggest remaining ones, both in `features.jsx`, both guarding
a whole ROUND of model calls rather than a single dispatch.

**The bug.** `StandupModal.start` opens with
`if (phase === 'running' || phase === 'summarizing') return;` and
`MeetingRoom.moderate` with `if (!input.trim() || streaming) return;`.
`phase` and `streaming` are React state (`useSF`). The `setPhase('running')`
/ `setStreaming(true)` that would flip them runs further down the same
handler and only tells the truth on the NEXT render — the handler itself
closes over THIS render's copy, exactly the way `onApprove` closed over a
stale `approvals` in `## 388` and `resendMessage` over a stale
`messagesRef.current` in `## 389`. Neither button carries a `disabled` for
the run or any debounce: the stand-up's ▶ START is rendered as
`{phase === 'idle' && <button onClick={start}>▶ START ({participating.length})}`
and its RE-RUN as `{phase === 'done' && <button onClick={start}>RE-RUN}`;
the meeting's is `{streaming ? ■ STOP : <button onClick={moderate}>SEND}`.
A second call landing before React commits — a fast double-click, or a
duplicate synthetic click off a double-tap, the same physical shape as
`## 388`'s stamp and `## 390`'s ▶ START on a task card — sees the same
stale guard value and runs the entire round again.

What a round costs makes this the largest duplicate in the family so far.
The stand-up fans out one `HQ.agentStream` per participating coworker and
then a closing `HQ.ceoStream`: on a five-person office, one extra click is
twelve real model calls instead of six. The meeting room does the same, one
turn per seated attendee plus the CEO's synthesis. Both also assign
`abortRef.current = controller` for their own run, so the second round
clobbers the first's controller and ■ STOP can only reach one of them — the
other keeps burning up to `STANDUP_TIMEOUT_MS` per agent with no UI left
that can stop it, the very leak the modal's `open`-edge abort effect exists
to prevent.

Reproduced by lifting the REAL `start`/`_start` and `moderate`/`_moderate`
function bodies out of features.jsx — brace-balanced text extraction of the
actual committed source, not a re-implementation — via
`scripts/harness_standup_meeting_race.mjs`, and calling each twice (then
three times) against one unchanged snapshot. Pre-fix, with three
participants: `HQ.agentStream` fired 6 times and `HQ.ceoStream` twice for
one click's worth of intent; 9 and 3 for a triple.

**The fix.** A `standupRunningRef` / `roundRunningRef` (a live ref, the only
thing in either component that is true the instant the round begins) is
checked-and-claimed as the very FIRST thing the button's own handler does,
synchronously, before `phase`/`streaming`/`input` are read at all. Unlike
`## 388`/`## 389`/`## 390`'s `Set` refs there is no id to key on — a modal
has exactly one live round, and the id those Sets hold was the id of the
one thing being acted on — so the claim is the ref itself. Released in a
`finally` on every ending (finished, stopped, threw), so RE-RUN and the next
SEND still work; the existing state guards stay exactly where they are, now
as the second line of defence rather than the only one.

Round 1: structural — both refs exist, both claims sit before the handler
reads any state, both release in a `finally`, and the original state guards
are still present. Round 2: the real extracted bodies, called twice and
three times against one snapshot, with `agentStream`/`ceoStream` firing
exactly once per round. Round 3: a plain single click is unaffected. Round
4: a second round started AFTER the first one finished still runs — proving
the claim releases rather than permanently deadening the button, the
stand-up/meeting analogue of `## 390`'s "a different taskId still starts".

Run: python3 scripts/test_a_second_click_on_start_does_not_run_the_meeting_twice.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEATURES_JSX = os.path.join(ROOT, "features.jsx")
HARNESS = os.path.join(ROOT, "scripts", "harness_standup_meeting_race.mjs")

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok    " if cond else "  FAIL  ") + name
          + ((f"  — {detail}") if not cond and detail else ""))
    if not cond:
        FAILS.append(name)


def _extract_balanced(src: str, marker: str) -> str:
    # Same rule as ## 388/## 389/## 390's harnesses: the marker must END with
    # the function's own opening brace, so a brace inside the signature (a
    # destructured default, an object literal) can never be mistaken for it.
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


def _try_extract(src: str, marker: str):
    """Same, but a MISSING marker is a reported failure rather than a crash.

    The fix splits each handler into a claim-wrapper (`start`/`moderate`,
    what the button is wired to) and the round itself (`_start`/`_moderate`).
    With the fix reverted the `_`-prefixed halves do not exist at all, and a
    hard `.index()` there would abort the run before the race rounds — which
    is precisely the evidence a fire-test needs to print.
    """
    try:
        return _extract_balanced(src, marker)
    except ValueError:
        return None


# ── Round 1: structural ────────────────────────────────────────────────────
def structural_checks() -> None:
    print("round 1 — the fix is really in the source")
    src = open(FEATURES_JSX, encoding="utf-8").read()

    for ref_name, entry, inner, state_guard in (
        ("standupRunningRef", "const start = async () => {",
         "const _start = async () => {",
         "if (phase === 'running' || phase === 'summarizing') return;"),
        ("roundRunningRef", "const moderate = async () => {",
         "const _moderate = async () => {",
         "if (!input.trim() || streaming) return;"),
    ):
        check(f"{ref_name} is declared (a live ref, not a state value)",
              re.search(rf"const {ref_name} = useRF\(false\)", src) is not None)

        body = _try_extract(src, entry)
        check(f"the {entry.split(' ')[1]} handler is still findable in the source",
              body is not None, f"marker not found: {entry}")
        if body is None:
            continue

        claim_re = re.compile(
            rf"if \({ref_name}\.current\) return;\s*{ref_name}\.current = true;",
            re.DOTALL)
        m = claim_re.search(body)
        check(f"{entry.split(' ')[1]} claims {ref_name} before doing anything else",
              bool(m))
        if m:
            # The whole point of ## 388/## 389/## 390: a guard placed after
            # the stale read is not a guard. Nothing may precede the claim.
            before = body[:body.index(m.group(0))].strip()
            before = re.sub(r"/\*.*?\*/", "", before, flags=re.DOTALL).strip()
            before = "\n".join(ln for ln in before.splitlines()
                               if not ln.strip().startswith("//")).strip()
            check(f"...and NOTHING executable runs before the {ref_name} claim",
                  before == "", f"found: {before[:200]!r}")

        check(f"{ref_name} is released in a finally (every ending — done, "
              f"stopped, threw — so the button lives to be clicked again)",
              re.search(rf"finally \{{ {ref_name}\.current = false; \}}", body) is not None)

        # The fix ADDS a lock; it must not remove the original guard, which
        # still correctly refuses a second round on a LATER render.
        inner_body = _try_extract(src, inner)
        check(f"the round itself lives in {inner.split(' ')[1]}, behind the claim",
              inner_body is not None, f"marker not found: {inner}")
        check(f"the original state guard is still there ({state_guard[:44]}...)",
              inner_body is not None and state_guard in inner_body)


# ── Round 2/3/4: the real extracted bodies, driven by the node harness ─────
def race_checks() -> None:
    print("rounds 2-4 — the real start/moderate bodies, clicked twice and three times")
    if shutil.which("node") is None:
        check("node is available to run the extracted-source harness", False,
              "no node on PATH — cannot drive the real start/moderate bodies")
        return
    out = subprocess.run(["node", HARNESS, FEATURES_JSX], cwd=ROOT,
                         capture_output=True, text=True, timeout=120)
    check("harness ran without a node-level error", out.returncode == 0,
          out.stderr.strip()[-800:] if out.returncode != 0 else "")
    lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    check("harness produced one result per scenario", len(lines) == 8,
          f"got {len(lines)} lines")

    by_scenario = {}
    for line in lines:
        d = json.loads(line)
        by_scenario[d["scenario"]] = d
        check(f"{d['scenario']}: the extracted body ran without throwing",
              d["threw"] is None, str(d["threw"])[-400:] if d["threw"] else "")

    # Round 2 (the race) + round 3 (the single-click sanity check). Three
    # participants/seats each, so one round is 3 agentStream + 1 ceoStream.
    for name in ("standup-double-click", "standup-triple-click", "standup-single",
                 "meeting-double-send", "meeting-triple-send", "meeting-single"):
        d = by_scenario.get(name)
        check(f"{name}: scenario present", d is not None)
        if not d:
            continue
        check(f"{name}: HQ.agentStream (one real model call per coworker) "
              f"fired exactly once per participant — one round, not two",
              d["agentStream"] == 3, f"fired {d['agentStream']} times, expected 3")
        check(f"{name}: HQ.ceoStream (the closing synthesis, real spend) "
              f"fired exactly once",
              d["ceoStream"] == 1, f"fired {d['ceoStream']} times, expected 1")

    # Round 4 — not over-blocked. The claim is scoped to a LIVE round, not to
    # the component forever: once a round has ended, RE-RUN / the next SEND
    # must still work. This is this fix's analogue of ## 390's "a genuinely
    # different taskId still starts" check.
    for name in ("standup-rerun-after-finish", "meeting-second-round-after-finish"):
        d = by_scenario.get(name)
        check(f"{name}: scenario present", d is not None)
        if not d:
            continue
        check(f"{name}: a SECOND round started after the first one ended "
              f"still runs in full — the claim releases, it does not "
              f"permanently deaden the button",
              d["agentStream"] == 6 and d["ceoStream"] == 2,
              f"agentStream={d['agentStream']} (expected 6), "
              f"ceoStream={d['ceoStream']} (expected 2)")


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
