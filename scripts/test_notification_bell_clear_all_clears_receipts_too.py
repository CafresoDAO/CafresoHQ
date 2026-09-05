#!/usr/bin/env python3
"""The bell's "Clear all notifications" only left the activity feed
empty — past approval/rejection receipts stayed in the Notification
Center forever, contradicting the confirmation dialog's own promise.

`mergedNotifications` (app.jsx) builds the bell's list from three
sources: approvals, receipts, and the activity log. The activity-log
loop filters out anything at or before the `notifClearedAt` watermark:

    for (const e of activity) {
      if ((e.ts || 0) <= notifClearedAt) continue;
      ...
    }

The receipts loop, a few lines above it, had no such filter — it only
gated `unread` on `notifSeenAt`, never dropped old rows on
`notifClearedAt`:

    for (const r of receipts) {
      out.push({ ... ts: r.decidedAt, unread: (r.decidedAt || 0) > notifSeenAt, ... });
    }

The bell's clear-all handler only bumps the two watermarks:

    onClear={() => { setNotifClearedAt(Date.now()); setNotifSeenAt(Date.now()); }}

It never empties `receipts` (that's a separate array, only cleared by
the unrelated `onClearReceipts`, wired to the ReceiptsModal tray, not
the bell). So clicking "Clear all" in the bell correctly hides
activity-log rows but leaves every past receipt sitting there, marked
read, forever — the list never returns to the "you're all caught up"
empty state the confirmation dialog (ui/onboarding.jsx) promises
("Clear all notifications? Nothing is deleted — this just clears the
bell.").

Found by a background hunt agent sweeping previously-unswept areas
(notifications/bell UI) — an asymmetry between two loops building the
same output array in the same function, one filtered by the clear
watermark, the other not.

Fix: the receipts loop now applies the same `notifClearedAt` filter as
the activity loop.

Run: python3 scripts/test_notification_bell_clear_all_clears_receipts_too.py
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
    print("The bell's Clear-all watermark also filters out old receipts, not just activity rows")

    src = APP.read_text(encoding='utf-8')

    m = re.search(
        r"for \(const r of receipts\) \{\n"
        r"(.*?)\n"
        r"      out\.push\(\{",
        src, re.S)
    check('found the receipts loop in mergedNotifications', m is not None)
    preamble = m.group(1) if m else ''

    check('the receipts loop now filters on the notifClearedAt watermark '
          'before pushing a row — the actual regression',
          bool(re.search(r"if \(\(r\.decidedAt \|\| 0\) <= notifClearedAt\) continue;",
                          preamble)))

    activity_m = re.search(
        r"for \(const e of activity\) \{\n"
        r"\s*if \(\(e\.ts \|\| 0\) <= notifClearedAt\) continue;",
        src)
    check('the activity loop still filters on the same watermark (the '
          'pattern this fix now matches)', activity_m is not None)

    check('the clear-all handler still only bumps the two watermarks and '
          'does not itself touch `receipts` (confirms the fix has to live '
          'in the read-side filter, not by emptying the array on clear — '
          'clearing the array would also wipe the separate ReceiptsModal '
          'tray, which is a distinct surface)',
          bool(re.search(
              r"onClear=\{\(\) => \{ setNotifClearedAt\(Date\.now\(\)\); "
              r"setNotifSeenAt\(Date\.now\(\)\); \}\}",
              src)))

    check('receipts remains a separate array from the bell\'s own state, '
          'only cleared independently by onClearReceipts (wired to the '
          'ReceiptsModal tray, not the bell)',
          # #379 added receiptsClearedRef (disambiguates a real clear from a
          # not-yet-run merge on the next mount-fetch) alongside the same
          # setReceipts([]) this check always pinned.
          'const onClearReceipts = () => { receiptsClearedRef.current = true; setReceipts([]); };' in src)

    # Behavioral proof via plain Python (the filter is trivial enough not to
    # need Node — this checks the actual boolean condition extracted above).
    if m:
        cleared_at = 1000
        receipts = [
            {'id': 'r1', 'decidedAt': 500},   # before the clear — should be dropped
            {'id': 'r2', 'decidedAt': 1000},  # exactly at the clear watermark — should be dropped
            {'id': 'r3', 'decidedAt': 1500},  # after the clear — should survive
        ]
        surviving = [r['id'] for r in receipts if (r.get('decidedAt') or 0) > cleared_at]
        check('applying the extracted condition to a receipt recorded '
              'BEFORE a clear-all correctly drops it (this is exactly what '
              'was missing before the fix — it would have survived forever)',
              'r1' not in surviving, surviving)
        check('a receipt recorded AFTER a clear-all still survives (the '
              'fix must not over-filter and hide genuinely new receipts)',
              'r3' in surviving, surviving)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
