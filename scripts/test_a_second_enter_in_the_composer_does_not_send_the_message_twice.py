#!/usr/bin/env python3
"""A second Enter (or a click landing on top of it) in a composer, arriving
before React re-renders, used to send the whole message TWICE.

`## 388`, `## 389`, `## 390` and `## 391` each fixed one handler whose "has
this already happened" guard read a value that does not update
synchronously. `## 391` then swept the rest of the client and left an
inventory of the remaining EXPOSED ones, each diagnosed. This hunt fixes the
three composer `send`s on that list — the three surfaces the boss actually
types into — which are the same bug in three siblings.

**The bug.** `ui/chat.jsx`'s `send` opens with
`if (!text || streaming) return;`, `FocusMode.send` (features.jsx) with the
same line, and `TerminalChat.send` (views/terminal.jsx) with
`if (!text || busy || !project) return;`. `streaming` and `busy` are React
state. The `setStreaming(true)` / `setBusy(true)` that would flip them runs
further down the SAME handler and only tells the truth on the NEXT render —
the handler closes over THIS render's copy, exactly the way `onApprove`
closed over a stale `approvals` in `## 388` and `StandupModal.start` over a
stale `phase` in `## 391`. Nothing on screen makes up for it: every control
that looks like a guard renders off that same state
(`{streaming ? ■ Stop : <button onClick={send}>Send ↵}`, the terminal's
`disabled={busy}` textarea and `onClick={busy ? stop : send}` button), and
all three composers' Enter handlers are a bare
`if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }`
with no guard of their own. Enter and then the button, a fast double-click,
or a duplicate synthetic click off a double-tap all read the same stale
value and run the entire turn again.

What that costs, per surface:

* `ui/chat.jsx` — the single most-used surface in the product, and the
  largest duplicate this series has found. A doubled boss message is a
  doubled `HQ.ceoStream` PLUS a doubled `onDispatchToAgent` for every
  @mentioned coworker and every seat in a room: on a message naming three
  people that is eight real model calls for the four asked for. It also
  clobbers `abortRef.current` (■ Stop reaches only the second turn while the
  first keeps streaming AND keeps delegating) and files two `onBossAsk`
  records for one question.
* `FocusMode` — one extra `HQ.ceoStream`, a doubled boss bubble and a second
  empty CEO bubble in the quiet room, plus the same clobbered `abortRef`.
* `TerminalChat` — not the office's tokens: two real non-interactive
  `claude`/`codex`/`gemini` turns on the USER'S OWN subscription, against
  their own project directory, each free to write files. Plus a clobbered
  `ctrlRef.current` so ■ reaches only one, and two writers racing the same
  `asstIdx` slot — `appendChunk` closes over an index computed from each
  call's own `history`, so two streams interleave into one transcript row.

Reproduced by lifting the REAL `send`/`_send` bodies out of all three files
— brace-balanced text extraction of the actual committed source, not a
re-implementation — via `scripts/harness_composer_send_race.mjs`, and
calling each twice (then three times) against one unchanged snapshot.
Pre-fix, measured: on "@A0 @A1 @A2 …", `onDispatchToAgent` fired 6 times for
a double and 9 for a triple (expected 3); on a plain question,
`HQ.ceoStream` fired 2 and 3 times and `onBossAsk` filed 2 and 3 records
(expected 1); FocusMode's `ceoStream` fired 2 and 3 times with 2 and 3 boss
bubbles; and `CafresoHQClient.terminalStream` — a real CLI turn on the
user's own subscription — fired 2 and 3 times.

**The fix.** `## 391`'s shape, applied to all three: a `sendRunningRef` /
`runningRef` (a live ref, the only thing in each component true the instant
the turn begins) is checked-and-claimed as the very FIRST thing the
handler does, synchronously, before `input`/`streaming`/`busy`/`project` are
read at all. As in `## 391`'s modals — and unlike `## 388`/`## 389`/
`## 390`'s `Set` refs, which held the id of the one thing being acted on —
there is no id to key on: a composer has exactly one live turn, so the claim
IS the ref. The turn moves behind it into `_send` so the release is a single
`finally` covering every ending (delivered, refused, stopped, threw) rather
than the many terminal `return`s these handlers have — `ui/chat.jsx`'s alone
has seven — which keeps an unexpected throw from deadening the composer
forever. The original state guards stay exactly where they are, now as the
second line of defence rather than the only one.

Round 1: structural — all three refs exist, all three claims have nothing
executable before them, all three release in a `finally`, all three original
state guards survive. Rounds 2-4: the real extracted bodies, called twice
and three times against one snapshot, with each real side effect firing
exactly once; a plain single send unaffected; and a second turn started
AFTER the first one finished still running in full, proving the claim
releases rather than permanently deadening the composer.

Run: python3 scripts/test_a_second_enter_in_the_composer_does_not_send_the_message_twice.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS = os.path.join(ROOT, "scripts", "harness_composer_send_race.mjs")

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok    " if cond else "  FAIL  ") + name
          + ((f"  — {detail}") if not cond and detail else ""))
    if not cond:
        FAILS.append(name)


def _extract_balanced(src: str, marker: str) -> str:
    # Same rule as ## 388-## 391's harnesses: the marker must END with the
    # function's own opening brace, so a brace inside the signature can never
    # be mistaken for it.
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

    The fix splits each handler into a claim-wrapper (`send`, what the button
    and Enter are wired to) and the turn itself (`_send`). With the fix
    reverted the `_send` halves do not exist at all, and a hard `.index()`
    there would abort the run before the race rounds — which is precisely the
    evidence a fire-test needs to print.
    """
    try:
        return _extract_balanced(src, marker)
    except ValueError:
        return None


# ── Round 1: structural ────────────────────────────────────────────────────
SURFACES = (
    ("ui/chat.jsx", "sendRunningRef", "useRef",
     "const send = async () => {", "const _send = async () => {",
     "if (!text || streaming) return;"),
    ("features.jsx", "runningRef", "useRF",
     "const send = async () => {", "const _send = async () => {",
     "const text = input.trim(); if (!text || streaming) return;"),
    ("views/terminal.jsx", "sendRunningRef", "React.useRef",
     "const send = async () => {", "const _send = async () => {",
     "if (!text || busy || !project) return;"),
)


def structural_checks() -> None:
    print("round 1 — the fix is really in the source")
    for rel, ref_name, ref_hook, entry, inner, state_guard in SURFACES:
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()

        check(f"{rel}: {ref_name} is declared (a live ref, not a state value)",
              re.search(rf"const {ref_name} = {re.escape(ref_hook)}\(false\)", src)
              is not None)

        body = _try_extract(src, entry)
        check(f"{rel}: the send handler is still findable in the source",
              body is not None, f"marker not found: {entry}")
        if body is None:
            continue

        claim_re = re.compile(
            rf"if \({ref_name}\.current\) return;\s*{ref_name}\.current = true;",
            re.DOTALL)
        m = claim_re.search(body)
        check(f"{rel}: send claims {ref_name} before doing anything else", bool(m))
        if m:
            # The whole point of ## 388-## 391: a guard placed after the stale
            # read is not a guard. Nothing may precede the claim.
            before = body[:body.index(m.group(0))].strip()
            before = re.sub(r"/\*.*?\*/", "", before, flags=re.DOTALL).strip()
            before = "\n".join(ln for ln in before.splitlines()
                               if not ln.strip().startswith("//")).strip()
            check(f"{rel}: ...and NOTHING executable runs before the claim",
                  before == "", f"found: {before[:200]!r}")

        check(f"{rel}: {ref_name} is released in a finally (every ending — "
              f"delivered, refused, stopped, threw — so the composer lives to "
              f"be typed into again)",
              re.search(rf"finally \{{ {ref_name}\.current = false; \}}", body)
              is not None)

        # The fix ADDS a lock; it must not remove the original guard, which
        # still correctly refuses a second turn on a LATER render.
        inner_body = _try_extract(src, inner)
        check(f"{rel}: the turn itself lives in _send, behind the claim",
              inner_body is not None, f"marker not found: {inner}")
        check(f"{rel}: the original state guard is still there "
              f"({state_guard[:40]}...)",
              inner_body is not None and state_guard in inner_body)


# ── Rounds 2/3/4: the real extracted bodies, driven by the node harness ────
# scenario -> {counter: expected}. Three @mentioned coworkers, so one round of
# the fan-out is 3 dispatches; every other round is one real call.
EXPECTED = {
    # Round 2 — the race, and round 3 — the single-send sanity check.
    "chat-mention-double": {"dispatch": 3, "ceoStream": 0},
    "chat-mention-triple": {"dispatch": 3, "ceoStream": 0},
    "chat-mention-single": {"dispatch": 3, "ceoStream": 0},
    "chat-ceo-double": {"ceoStream": 1, "bossAsk": 1, "dispatch": 0},
    "chat-ceo-triple": {"ceoStream": 1, "bossAsk": 1, "dispatch": 0},
    "chat-ceo-single": {"ceoStream": 1, "bossAsk": 1, "dispatch": 0},
    "focus-double": {"ceoStream": 1, "userMsgs": 1},
    "focus-triple": {"ceoStream": 1, "userMsgs": 1},
    "focus-single": {"ceoStream": 1, "userMsgs": 1},
    "terminal-double": {"terminalStream": 1},
    "terminal-triple": {"terminalStream": 1},
    "terminal-single": {"terminalStream": 1},
    # Round 4 — not over-blocked. The claim is scoped to a LIVE turn, not to
    # the composer forever: once a turn has ended, the next message must go.
    # This is this fix's analogue of ## 390's "a genuinely different taskId
    # still starts" and ## 391's "RE-RUN still works".
    "chat-ceo-second-turn-after-finish": {"ceoStream": 2, "bossAsk": 2},
    "focus-second-turn-after-finish": {"ceoStream": 2, "userMsgs": 2},
    "terminal-second-turn-after-finish": {"terminalStream": 2},
}

# What each counter is, in the boss's terms — so a failure line says what was
# really spent twice rather than naming a stub.
MEANING = {
    "dispatch": "onDispatchToAgent (one real coworker run per @mention)",
    "ceoStream": "HQ.ceoStream (a real chief-of-staff turn)",
    "bossAsk": "onBossAsk (the filed record of the question)",
    "userMsgs": "the boss's own message in the transcript",
    "terminalStream": "CafresoHQClient.terminalStream (a real claude/codex/"
                      "gemini turn on the USER'S OWN subscription)",
}


def race_checks() -> None:
    print("rounds 2-4 — the real send bodies, sent twice and three times")
    if shutil.which("node") is None:
        check("node is available to run the extracted-source harness", False,
              "no node on PATH — cannot drive the real send bodies")
        return
    out = subprocess.run(["node", HARNESS, ROOT], cwd=ROOT,
                         capture_output=True, text=True, timeout=180)
    check("harness ran without a node-level error", out.returncode == 0,
          out.stderr.strip()[-800:] if out.returncode != 0 else "")
    lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    check("harness produced one result per scenario", len(lines) == len(EXPECTED),
          f"got {len(lines)} lines, expected {len(EXPECTED)}")

    by_scenario = {}
    for line in lines:
        d = json.loads(line)
        by_scenario[d["scenario"]] = d
        check(f"{d['scenario']}: the extracted body ran without throwing",
              d["threw"] is None, str(d["threw"])[-400:] if d["threw"] else "")

    for name, wants in EXPECTED.items():
        d = by_scenario.get(name)
        check(f"{name}: scenario present", d is not None)
        if not d:
            continue
        for counter, expected in wants.items():
            check(f"{name}: {MEANING[counter]} fired exactly {expected}x",
                  d[counter] == expected,
                  f"fired {d[counter]} times, expected {expected}")


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
