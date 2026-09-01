#!/usr/bin/env python3
"""Every Memory-shelf entry used to be permanently labelled "Today," no
matter when it was actually added.

`MemoryPage.submit()` built each record with a hardcoded literal string
`date: 'Today'` — not a timestamp — and `onAddMemory` (app.jsx) persisted
it exactly as given. There is no other writer of `.date` anywhere in the
memory pipeline. A note added a month ago and one added five seconds ago
rendered an identical `memdate` of "Today," forever — a boss scanning the
shelf for what changed recently had no way to tell old rules from fresh
ones.

Found by a background hunt agent sweeping previously-uncovered areas
(Calendar, Library/Graph, Meetings, Memory, Night Shift, search).

Fix: `submit()` now stores `date: Date.now()` — a real timestamp — and a
new `fmtMemDate` helper (mirroring the fmtAgo pattern AgentInbox already
uses a few hundred lines below in the same file) formats it at render
time: "Just now", "Xm/Xh/Xd ago", or a real date past a week. A
non-numeric `date` (an already-saved entry from before this fix) falls
back to a plain "Unknown" label instead of crashing into `Invalid Date`.

Run: python3 scripts/test_memory_entry_date_is_a_real_timestamp.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / 'views' / 'core.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("Memory-shelf entries carry a real timestamp, not a frozen 'Today' string")

    src = CORE.read_text(encoding='utf-8')

    m = re.search(r"const submit = \(\) => \{(.*?)\n  \};", src, re.S)
    check('MemoryPage.submit is still present', m is not None)
    submit_body = m.group(1) if m else ''

    check("submit() stores a real timestamp (date: Date.now()), not the "
          "old frozen literal string date: 'Today'",
          "date: Date.now()" in submit_body)
    check("...and the old literal is gone",
          "date: 'Today'" not in submit_body)

    m2 = re.search(r"const fmtMemDate = \(d\) => \{(.*?)\n  \};", src, re.S)
    check('fmtMemDate helper exists', m2 is not None)
    fmt_body = m2.group(1) if m2 else ''

    check("it falls back to a plain label for a non-numeric date (an "
          "already-saved pre-fix entry), instead of crashing into Invalid Date",
          "typeof d !== 'number'" in fmt_body)
    check("it distinguishes 'just added' from older entries",
          "'Just now'" in fmt_body and "'m ago'" in fmt_body
          and "'h ago'" in fmt_body and "'d ago'" in fmt_body)

    check('the memrow renders the entry through fmtMemDate rather than '
          'printing the raw stored value directly',
          re.search(r'<div className="memdate">\{fmtMemDate\(m\.date\)\}</div>',
                     src) is not None)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
