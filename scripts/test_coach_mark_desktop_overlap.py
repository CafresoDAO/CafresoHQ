#!/usr/bin/env python3
"""The coach-mark pill clipped the Getting Started checklist's corner on
real desktop widths, not just on mobile.

The checklist (`.gs-coach`) is left-anchored near the rail (246px desktop,
214px at <=1100px, 70px rail-collapsed) at a fixed 274px width. The coach
mark pill was always `left: 50%, transform: translateX(-50%)` -- screen-
centered regardless of viewport width. Measured live (both via
getBoundingClientRect and the render condition below) at three common
desktop widths:

  1100px: checklist right edge 488, pill left edge  315 -> overlap ~173px
  1366px: checklist right edge 520, pill left edge  448 -> overlap  ~72px
  1600px: checklist right edge 520, pill left edge  565 -> clear    ~45px

1366px is one of the single most common screen resolutions there is. The
existing code comment claimed "on desktop both show as before, where they
don't touch" -- true only above roughly 1510px, which is not "desktop" in
general, just "wide desktop."

The mobile fix for the analogous phone-width collision (2026-08-1x,
`isNarrowViewport`-gated) already articulated the real reason these two
surfaces shouldn't show together: the expanded checklist lists the exact
same next step with the exact same CTA the coach mark would nudge toward,
so showing both is redundant, not just crowded. That reasoning was never
mobile-specific -- it was just only APPLIED on narrow viewports. The fix
here is the same suppression, with the `isNarrowViewport &&` qualifier
dropped so it applies at every width: the pill only renders once the
checklist is collapsed or dismissed.

Verified live: rebuilt the bundle, drove a throwaway office with one
hired agent at 1366px, confirmed the pill is entirely absent while the
checklist is expanded, and reappears (clear of the collapsed pill, ~46px
gap) once the checklist is collapsed.

Run: python3 scripts/test_coach_mark_desktop_overlap.py
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
    r"\{!tourOpen && coachMark && ([^\n]*?) && \(\s*\n\s*<div className=\"coach-mark\"",
    src,
)
check(m, 'app.jsx: could not find the coach-mark render condition '
         '(`{!tourOpen && coachMark && ... && (<div className="coach-mark"`).')
if m:
    cond = m.group(1)
    check(
        'isNarrowViewport' not in cond,
        "the coach-mark's render condition still references isNarrowViewport "
        "— the whole point of this fix is that the checklist-overlap suppression "
        "must NOT be gated to narrow viewports only. Found: " + repr(cond),
    )
    check(
        'gsDismissed' in cond and 'gsCollapsed' in cond,
        "the coach-mark's render condition must still check both gsDismissed "
        "and gsCollapsed — it should render only when the checklist is NOT "
        "currently expanded (dismissed OR collapsed). Found: " + repr(cond),
    )

if failures:
    print("FAIL:")
    for f in failures:
        print(f" - {f}")
    raise SystemExit(1)

print("ALL PASS")
