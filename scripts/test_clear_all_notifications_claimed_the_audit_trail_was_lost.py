#!/usr/bin/env python3
""""Clear all" on the notification bell claimed the audit trail was lost.

Reproduced by reading the source, then live in the browser. The
NotificationCenter's confirm dialog in `ui/onboarding.jsx` read:

    'Clear all notifications? Audit trail is lost.'

`onClear` — passed in from `app.jsx` — is:

    onClear={() => { setNotifClearedAt(Date.now()); setNotifSeenAt(Date.now()); }}

Both calls just bump watermark timestamps. `notifClearedAt` has exactly
one other use in the whole file: filtering the bell's own derived
`notifications` list going forward (`if ((e.ts || 0) <= notifClearedAt)
continue;`). The underlying `approvals`, `receipts`, and `activity`
state arrays — the actual record the dialog is warning about — are
never touched. Nothing is deleted; the bell just stops showing old
entries.

Notably, `features.jsx`'s ReceiptsModal has the identical sentence,
"Clear all receipts? Audit trail is lost," and there it's true — its
`onClear` is `onClearReceipts = () => setReceipts([])`, a real delete.
The bell's confirm text was very likely copied from that honest
sibling without checking whether its own `onClear` did the same thing.

Run: python3 scripts/test_clear_all_notifications_claimed_the_audit_trail_was_lost.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ONBOARDING = (ROOT / 'ui/onboarding.jsx').read_text(encoding='utf-8')
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
FEATURES = (ROOT / 'features.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('"Clear all" claimed the audit trail was lost')

    check('the notification bell confirm dialog no longer claims the audit trail is lost',
          "Clear all notifications? Audit trail is lost." not in ONBOARDING)
    check('...it now says nothing is deleted, matching what onClear actually does',
          "Clear all notifications? Nothing is deleted — this just clears the bell." in ONBOARDING)

    # Verify the claim against the real onClear wiring in app.jsx: it must
    # still only bump the two watermarks, never touch approvals/receipts/activity.
    wiring = re.search(r"onClear=\{\(\) => \{ setNotifClearedAt\(Date\.now\(\)\); setNotifSeenAt\(Date\.now\(\)\); \}\}", APP)
    check('app.jsx onClear still only bumps notifClearedAt/notifSeenAt (the fix must describe reality, not change it)',
          wiring is not None)
    # notifClearedAt now filters BOTH the activity loop and the receipts loop
    # of mergedNotifications (a later fix closed the gap where receipts
    # ignored the watermark entirely) — but every functional use is still a
    # `<= notifClearedAt) continue` filter on a derived list, never a delete
    # of the underlying approvals/receipts/activity state arrays.
    filter_uses = re.findall(r"if \(\(.*?\) <= notifClearedAt\) continue;", APP)
    check('every functional use of notifClearedAt is a filter-continue on '
          'a derived list (not a delete of the underlying state) — this is '
          'still true even though a later fix added a second such filter '
          '(receipts, alongside the original activity-log one)',
          len(filter_uses) == 2, filter_uses)

    # The sibling ReceiptsModal dialog, where the identical old sentence is
    # actually true (setReceipts([]) really deletes), must stay untouched.
    check("ReceiptsModal's own (honest, for its own onClear) audit-trail warning is untouched",
          "Clear all receipts? Audit trail is lost." in FEATURES)

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
