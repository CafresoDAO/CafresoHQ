#!/usr/bin/env python3
"""The bell's Notification Center had real per-row onClick handlers — a
receipt row opened the Receipts modal, an activity row opened the Team
inbox, an approval row jumped to Visual — but none of the receipt/
activity rows ever marked themselves read. Only two paths did that:
closing the whole panel (✕/backdrop) and "Mark all read". So a boss who
triaged one notification at a time by clicking it (the obvious, natural
interaction — "click to read") saw the bell's unread count sit frozen at
the same number, and that same row still rendered as unread if they
reopened the panel, even though they'd just acted on it.

Root cause: unread-ness for receipts/activity isn't tracked per item —
it's a single `notifSeenAt` watermark (an item is unread if it arrived
after that timestamp) plus a per-activity-entry `unread` flag that only
`onClose`/`onMarkAllRead` ever cleared. Every row's own onClick in
app.jsx's `mergedNotifications` builder called `setNotifOpen(false)` and
navigated, but never touched either of those. Found by a background hunt
agent scanning the Inbox/notifications and CEO 1:1 surfaces (this
session's next-least-scrutinized areas), confirmed by tracing exactly
which onClick closures update `notifSeenAt`/`activity` and which don't.

The fix factors the shared "mark seen" side effect (bump notifSeenAt,
clear unread on non-attention activity entries — attention-priority rows
stay flagged until actually resolved via the Team inbox, same as
before) into one `markNotifsSeen` callback, and calls it from the
receipt and activity row onClicks (approvals aren't touched — an
approval's unread status is "still pending a decision", not driven by
notifSeenAt, so it's correct that clicking one doesn't clear it).
`onClose`/`onMarkAllRead` now call the same shared callback instead of
duplicating its body.

Verified live in the browser: with the bell showing "2 unread" (2
pending receipts), clicked a single receipt row — the Receipts modal
opened (unchanged behavior) AND the bell's own aria-label read
"Notifications (0 unread)" the moment the panel was reopened, matching
the shared watermark going for every row rather than a single item.

Run: python3 scripts/test_notification_click_marks_read.py
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
    print("Notification Center rows mark themselves read on click")

    app = APP.read_text(encoding='utf-8')

    check('a shared markNotifsSeen callback exists that bumps notifSeenAt '
          'and clears unread on non-attention activity entries',
          re.search(r"const markNotifsSeen = useCallbackA\(\(\) => \{\s*"
                     r"setNotifSeenAt\(Date\.now\(\)\);\s*"
                     r"setActivity\(xs => xs\.map\(x => x\.priority === 'attention' "
                     r"\? x : \{ \.\.\.x, unread: false \}\)\);",
                     app) is not None,
          'app.jsx: markNotifsSeen callback missing or reshaped')

    m = re.search(r"for \(const r of receipts\) \{(.*?)\n    \}", app, re.S)
    check('the receipt row (in mergedNotifications) still opens the '
          'Receipts modal AND now calls markNotifsSeen on click',
          m is not None
          and 'setReceiptsOpen(true)' in m.group(1)
          and 'markNotifsSeen()' in m.group(1),
          'app.jsx: receipt row onClick missing setReceiptsOpen or markNotifsSeen')

    m = re.search(r"for \(const e of activity\) \{(.*?)\n    \}", app, re.S)
    check('the activity row still opens the Team attention inbox AND now '
          'calls markNotifsSeen on click',
          m is not None
          and 'openAttention()' in m.group(1)
          and 'markNotifsSeen()' in m.group(1),
          'app.jsx: activity row onClick missing openAttention or markNotifsSeen')

    m = re.search(r"for \(const ap of approvals\) \{(.*?)\n    \}", app, re.S)
    check("the approval row's onClick is untouched — approvals are "
          "unread until decided, not until seen, so clicking one "
          "shouldn't call markNotifsSeen",
          m is not None
          and 'goTo(\'visual\')' in m.group(1)
          and 'markNotifsSeen' not in m.group(1),
          'app.jsx: approval row onClick unexpectedly changed')

    check('NotificationCenter\'s onClose and onMarkAllRead now delegate '
          'to the same shared markNotifsSeen (no duplicated watermark logic)',
          re.search(r"onClose=\{\(\) => \{ setNotifOpen\(false\); markNotifsSeen\(\); \}\}",
                     app) is not None
          and re.search(r"onMarkAllRead=\{markNotifsSeen\}", app) is not None,
          'app.jsx: NotificationCenter wiring no longer matches')

    check("mergedNotifications' useMemo dependency array includes "
          'markNotifsSeen (the onClick closures it builds now capture it)',
          re.search(r"\[approvals, receipts, activity, notifSeenAt, notifClearedAt, "
                     r"markNotifsSeen\]", app) is not None,
          'app.jsx: mergedNotifications deps missing markNotifsSeen')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
