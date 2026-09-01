#!/usr/bin/env python3
"""A CEO-desk sticky note could get silently deleted by ambient agent
activity.

`pins` holds both corkboard/receipt pins AND the boss's manually typed
sticky notes (onAddSticky) in one array. `onPin`'s truncation used to be
`.slice(0, 18)` on the WHOLE merged array, regardless of `kind` — and
every agent deliverable (VAULT_NEW, EXPORT_PPTX, GENERATE_IMAGE, etc.)
quietly calls `onPin(..., { quiet: true })` during ordinary, frequent
agent work. Once 18 receipts had landed after a sticky note, the next
quiet receipt pin would bump the sticky clean out of the array — no
toast, no warning, no undo, indistinguishable from background noise.

Found by a background hunt agent sweeping previously-uncovered areas.

Fix: `onPin` now caps only the non-sticky ("receipt"/corkboard) entries
at 18; sticky notes are exempt from the cap entirely and can only be
removed by the boss's own ✕ (onRemoveSticky).

Run: python3 scripts/test_sticky_note_survives_receipt_pin_cap.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("A sticky note is exempt from onPin's receipt-count cap")

    src = APP.read_text(encoding='utf-8')

    m = re.search(r"const onPin = \(pin, \{ quiet = false \} = \{\}\) => \{(.*?)\n  \};",
                   src, re.S)
    check('onPin is still present', m is not None)
    body = m.group(1) if m else ''

    check("the old kind-agnostic cap on the WHOLE merged array is gone "
          "(it used to silently evict stickies once 18 newer pins of any "
          "kind had landed)",
          re.search(r"\[\{ id: HQ\.uid\('pin'\).*?\}, \.\.\.prev\]\.slice\(0, 18\)",
                     body, re.S) is None)

    check("stickies are pulled out of the merged list before the cap is "
          "applied, so the cap never sees them",
          "next.filter(p => p.kind === 'sticky')" in body)
    check("only the non-sticky (receipt/corkboard) entries are capped at 18",
          "next.filter(p => p.kind !== 'sticky').slice(0, 18)" in body)
    check("the capped result recombines both groups, so a sticky note "
          "survives no matter how many receipts land after it",
          "return [...others, ...stickies]" in body)

    m2 = re.search(r"const onAddSticky = async \(\) => \{(.*?)\n  \};", src, re.S)
    check("onAddSticky (the boss's own sticky-note action) is untouched "
          "and still uncapped on its own add",
          m2 is not None and 'setPins(prev =>' in (m2.group(1) if m2 else ''))

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
