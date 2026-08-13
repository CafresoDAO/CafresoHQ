#!/usr/bin/env python3
"""Auto night-mode-at-load silently overwrote an explicit "stay in day
mode" choice, every evening, forever.

`useStored(k('night'), false)` reads localStorage synchronously in its
initializer, so by the time any effect runs, `night` already correctly
reflects a boss's stored preference (`false` if they'd explicitly turned
night mode off). A separate mount-only effect then ran unconditionally:
`if (h < 7 || h >= 19) setNight(true)` — no check for whether a
preference was already stored, just the clock. A boss who explicitly
chose day mode via the toggle (or the ROOMS menu's "Switch to day") had
that exact choice silently overwritten back to night on their very next
reload after 7pm — with no way to make day mode stick in the evening,
since every fresh load re-ran the same unconditional override.

The auto-detect ITSELF is legitimate — a first-time visitor loading HQ
after dark reasonably gets night mode instead of a glaring day theme —
the bug was applying it to EVERY mount instead of only the one case
`useStored` itself treats as "unset": no key in localStorage at all.

Fix: gate the effect on `localStorage.getItem(k('night')) == null` before
checking the clock — the exact same signal `useStored`'s own initializer
already uses to distinguish "never set" from "explicitly set". Verified
the guard's logic precisely (not just "the code compiles") with a small
node harness replicating the exact effect body against four scenarios:
new visitor + evening (still auto-sets true), new visitor + day (no-op,
unchanged), returning visitor with explicit false + evening (must NOT
override — this is the bug, now fixed), returning visitor with explicit
true + day (no-op, unaffected). All four passed. Also smoke-tested live:
a fresh throwaway office loaded at the real current daytime hour stayed
in day mode, confirming no regression to the ordinary case.

Run: python3 scripts/test_night_mode_respects_explicit_choice.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


src = APP.read_text()

m = re.search(
    r"useEffectA\(\(\) => \{\s*"
    r"if \(localStorage\.getItem\(k\('night'\)\) != null\) return;\s*"
    r"const h = new Date\(\)\.getHours\(\);\s*"
    r"if \(h < 7 \|\| h >= 19\) setNight\(true\);\s*"
    r"\}, \[\]\);",
    src,
)
check(
    m,
    "app.jsx: the night-mode auto-detect effect must check "
    "`localStorage.getItem(k('night')) != null` and return early BEFORE "
    "checking the clock — without this guard, every mount during evening/"
    "night hours re-applies night mode regardless of an explicit stored "
    "preference, so a boss can never make 'stay in day mode' stick past "
    "7pm.",
)

if failures:
    print("FAIL:")
    for f in failures:
        print(f" - {f}")
    raise SystemExit(1)

print("ALL PASS")
