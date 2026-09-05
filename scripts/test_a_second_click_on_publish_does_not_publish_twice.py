#!/usr/bin/env python3
"""A second click on 🚀 Publish, or a second submit of Clone & add, used to
do the whole job twice.

`## 391`'s exhaustive sweep of the "has this already happened / is this
already in flight" guards named six remaining EXPOSED doors and diagnosed
each precisely. Two of them are in views/projects.jsx and are closed here.
They are the same bug in two sibling surfaces of one file, which is why one
entry covers both — but they are not equally exposed, and the difference is
worth writing down rather than smoothing over.

**`publishOpen` — no guard at all.** Every door `## 388`–`## 391` fixed at
least *had* a check that read a stale React value. This one has nothing.
`setPubMsg({ kind: 'busy', … })` sits at the top of the handler and looks
like the flag; it is never read as one, it only paints a line of text.
Neither 🚀 Publish nor its 🔗 Preview link twin carries a `disabled`, and
there is no debounce. Two clicks were two `CafresoHQClient.publishSite`
calls, unconditionally — not a race that depends on React's commit timing,
just an open door. In `canister` mode a publish is a real upload of the
whole site to public hosting plus a `.url` file written into the project, so
a duplicate is a duplicate deploy; both rounds then race the one `pubMsg`
slot and the clipboard, so the link the boss pastes can be the loser's.

**`submitGithub` — a real gate, one render late.** This button IS
`disabled={busy}`, and that gate is not merely cosmetic: an ordinary second
mouse click lands in a later task, React 18 has already flushed the discrete
`setBusy(true)` by then, and HTML refuses implicit form submission through a
disabled default button, so Enter is covered too. What `disabled` cannot
cover is a second submit landing in the SAME tick as the first, before React
commits anything — a duplicate synthetic click off a touch double-tap (this
view is explicitly mobile, see `_isMobile`), or a programmatic
`requestSubmit`. So it is a genuine race window rather than an open door.
When it lands it is two `cloneRepo` calls — two `git clone`s of one repo
racing the same destination directory — and two `onCommit`s, i.e. two
project rows in the office for one repo the boss added once.

Reproduced by lifting the REAL `publishOpen`/`_publishOpen` and
`submitGithub`/`_submitGithub` bodies out of views/projects.jsx —
brace-balanced text extraction of the actual committed source, not a
re-implementation — via `scripts/harness_projects_publish_clone_race.mjs`,
and calling each twice (then three times) against one unchanged snapshot.
Pre-fix: `publishSite` fired 2 times for a double click and 3 for a triple
(and 2 in the preview-link fallback), `cloneRepo` 2 and 3, with `onCommit`
matching it row for row.

**The fix.** A `publishingPathsRef` / `cloningUrlsRef` — a live ref holding
a `Set`, the only thing in either component true the instant the work
begins — is checked-and-claimed as the FIRST thing each handler does. The
work moves behind the claim into `_publishOpen` / `_submitGithub` so the
release is a single `finally` covering every ending, including an
unexpected throw, rather than a release at each of several terminal points
(a missed one there deadens the button forever). Keyed by a `Set` on the
natural id — the file path being published, the repo URL being cloned —
matching `## 388`'s `approvedIdsRef`, `## 389`'s `resendingIdsRef` and
`## 390`'s `startingTaskIdsRef`, rather than `## 391`'s bare boolean, so the
claim scopes to the thing being acted on and a genuinely different file or
repo is never swallowed by a lock scoped to the wrong thing. `submitGithub`
keeps `e.preventDefault()` ahead of the claim on purpose: it is the one
statement that must also run on the REFUSED submit, or the blocked second
event navigates the page away.

Round 1: structural — both refs exist, both claims sit at the top of their
handler with nothing but the key derivation (and `preventDefault`) ahead of
them, both release in a `finally`, and the work really did move behind the
claim. Round 2: the real extracted bodies, called twice and three times
against one snapshot, with the real call firing exactly once. Round 3: a
plain single click is unaffected. Round 4: a second attempt started AFTER
the first finished still runs — and, separately, a retry after a FAILED
publish/clone still runs, which is the case that matters most, since a
failure is exactly when the boss clicks again.

Run: python3 scripts/test_a_second_click_on_publish_does_not_publish_twice.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS_JSX = os.path.join(ROOT, "views", "projects.jsx")
HARNESS = os.path.join(ROOT, "scripts", "harness_projects_publish_clone_race.mjs")

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok    " if cond else "  FAIL  ") + name
          + ((f"  — {detail}") if not cond and detail else ""))
    if not cond:
        FAILS.append(name)


def _extract_balanced(src: str, marker: str) -> str:
    # Same rule as ## 388–## 391's harnesses: the marker must END with the
    # function's own opening brace, so a brace inside the signature can
    # never be mistaken for it.
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

    The fix splits each handler into a claim-wrapper (`publishOpen` /
    `submitGithub`, what the button and the form are wired to) and the work
    itself (`_publishOpen` / `_submitGithub`). With the fix reverted the
    `_`-prefixed halves do not exist at all, and a hard `.index()` there
    would abort the run before the race rounds — which is precisely the
    evidence a fire-test needs to print.
    """
    try:
        return _extract_balanced(src, marker)
    except ValueError:
        return None


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return "\n".join(ln for ln in text.splitlines()
                     if not ln.strip().startswith("//")).strip()


# ── Round 1: structural ────────────────────────────────────────────────────
def structural_checks() -> None:
    print("round 1 — the fix is really in the source")
    src = open(PROJECTS_JSX, encoding="utf-8").read()

    surfaces = (
        # ref name, entry marker, inner marker, what may precede the claim,
        # a line that must have moved behind the claim
        ("publishingPathsRef",
         "const publishOpen = async () => {",
         "const _publishOpen = async () => {",
         ["const claim = (openFile && openFile.path) || '';"],
         "await CafresoHQClient.publishSite(openFile.path)"),
        ("cloningUrlsRef",
         "const submitGithub = async (e) => {",
         "const _submitGithub = async () => {",
         ["e && e.preventDefault();", "const claim = repoUrl.trim();"],
         "await CafresoHQClient.cloneRepo("),
    )

    for ref_name, entry, inner, allowed_before, moved_line in surfaces:
        short = entry.split(" ")[1]

        check(f"{ref_name} is declared (a live ref holding a Set, not a state value)",
              re.search(rf"const {ref_name} = useRV\(new Set\(\)\)", src) is not None)

        body = _try_extract(src, entry)
        check(f"the {short} handler is still findable in the source",
              body is not None, f"marker not found: {entry}")
        if body is None:
            continue

        claim_re = re.compile(
            rf"if \({ref_name}\.current\.has\(claim\)\) return;\s*"
            rf"{ref_name}\.current\.add\(claim\);", re.DOTALL)
        m = claim_re.search(body)
        check(f"{short} checks-and-claims {ref_name} for this id, synchronously",
              bool(m))
        if m:
            # The whole point of ## 388–## 391: a guard placed after the work
            # is not a guard. Only deriving the key — and, for the form,
            # preventDefault, which MUST also run on the refused submit —
            # may precede it.
            before = _strip_comments(body[:body.index(m.group(0))])
            before_lines = [ln.strip() for ln in before.splitlines() if ln.strip()]
            check(f"...and nothing but the key derivation runs before the "
                  f"{ref_name} claim",
                  before_lines == allowed_before,
                  f"found: {before_lines!r}, expected {allowed_before!r}")

        check(f"{ref_name} releases this id in a finally (every ending — done, "
              f"failed, threw — so a legitimate retry still works)",
              re.search(rf"finally \{{ {ref_name}\.current\.delete\(claim\); \}}",
                        body) is not None)

        # The real work must be BEHIND the claim, not still sitting in front
        # of it in the entry point.
        check(f"the real work moved out of {short} and behind the claim",
              moved_line not in body, "the side effect is still in the wrapper")
        inner_body = _try_extract(src, inner)
        check(f"the work itself lives in {inner.split(' ')[1]}, behind the claim",
              inner_body is not None, f"marker not found: {inner}")
        check(f"...and it is the real call ({moved_line[:42]}...)",
              inner_body is not None and moved_line in inner_body)

    # The fix must not have quietly removed the gate the clone form already
    # had. `disabled={busy}` is a real second line of defence for the
    # ordinary, post-commit second click; the ref covers the same-tick one.
    check("the Clone & add button still carries disabled={busy} "
          "(the ref is an addition, not a replacement)",
          'type="submit" className="px-btn primary" disabled={busy}' in src)


# ── Rounds 2/3/4: the real extracted bodies, driven by the node harness ────
def race_checks() -> None:
    print("rounds 2-4 — the real publish/clone bodies, clicked twice and three times")
    if shutil.which("node") is None:
        check("node is available to run the extracted-source harness", False,
              "no node on PATH — cannot drive the real publishOpen/submitGithub bodies")
        return
    out = subprocess.run(["node", HARNESS, PROJECTS_JSX], cwd=ROOT,
                         capture_output=True, text=True, timeout=120)
    check("harness ran without a node-level error", out.returncode == 0,
          out.stderr.strip()[-800:] if out.returncode != 0 else "")
    lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    check("harness produced one result per scenario", len(lines) == 12,
          f"got {len(lines)} lines")

    by_scenario = {}
    for line in lines:
        d = json.loads(line)
        by_scenario[d["scenario"]] = d
        check(f"{d['scenario']}: the extracted body ran without throwing",
              d["threw"] is None, str(d["threw"])[-400:] if d["threw"] else "")

    def get(name):
        d = by_scenario.get(name)
        check(f"{name}: scenario present", d is not None)
        return d

    # Round 2 (the race) + round 3 (the single-click sanity check).
    for name in ("publish-double-click", "publish-triple-click", "publish-single",
                 "publish-preview-double-click"):
        d = get(name)
        if not d:
            continue
        check(f"{name}: CafresoHQClient.publishSite (a real deploy of the whole "
              f"site) fired exactly once — one publish, not two",
              d["publishSite"] == 1, f"fired {d['publishSite']} times, expected 1")

    d = get("publish-double-click")
    if d:
        # Two rounds racing one clipboard is the other half of the damage:
        # the link the boss pastes can be the loser's.
        check("publish-double-click: the clipboard was written exactly once",
              d["clipboard"] == 1, f"written {d['clipboard']} times, expected 1")

    for name in ("clone-double-submit", "clone-triple-submit", "clone-single"):
        d = get(name)
        if not d:
            continue
        check(f"{name}: CafresoHQClient.cloneRepo (a real git clone into a real "
              f"directory) fired exactly once",
              d["cloneRepo"] == 1, f"fired {d['cloneRepo']} times, expected 1")
        check(f"{name}: onCommit filed exactly one project row for one repo",
              d["onCommit"] == 1, f"filed {d['onCommit']} rows, expected 1")

    # A submit the claim REFUSES must still have been preventDefault'd, or
    # the blocked second event navigates the page away — worse than the bug.
    d = get("clone-refused-submit-still-prevented")
    if d:
        check("clone-refused-submit-still-prevented: BOTH submit events were "
              "preventDefault'd, including the one the claim refused",
              d.get("prevented") == 2, f"prevented {d.get('prevented')} of 2")
        check("clone-refused-submit-still-prevented: ...and still only one clone",
              d["cloneRepo"] == 1, f"fired {d['cloneRepo']} times, expected 1")

    # Round 4 — not over-blocked. The claim is scoped to a LIVE operation,
    # not to the surface forever.
    d = get("publish-again-after-finish")
    if d:
        check("publish-again-after-finish: publishing again AFTER the first one "
              "finished still works — the claim releases, it does not "
              "permanently deaden the button",
              d["publishSite"] == 2, f"fired {d['publishSite']} times, expected 2")
    d = get("clone-again-after-finish")
    if d:
        check("clone-again-after-finish: a second clone after the first finished "
              "still works",
              d["cloneRepo"] == 2 and d["onCommit"] == 2,
              f"cloneRepo={d['cloneRepo']} (expected 2), onCommit={d['onCommit']} (expected 2)")

    # ...and the case that matters most: a FAILED attempt must release too,
    # because a failure is exactly when the boss clicks again.
    d = get("publish-retry-after-failure")
    if d:
        check("publish-retry-after-failure: after a publish that FAILED, the "
              "retry really re-publishes — a failed publish is precisely when "
              "the boss clicks again",
              d["publishSite"] == 2, f"fired {d['publishSite']} times, expected 2")
    d = get("clone-retry-after-failure")
    if d:
        check("clone-retry-after-failure: after a clone that FAILED, the retry "
              "the error box invites really re-clones",
              d["cloneRepo"] == 2, f"fired {d['cloneRepo']} times, expected 2")
        check("clone-retry-after-failure: ...and neither failed attempt filed a "
              "project row",
              d["onCommit"] == 0, f"filed {d['onCommit']} rows, expected 0")


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
