#!/usr/bin/env python3
"""A failed POST to /approvals/external/decide was silently swallowed,
leaving the boss's chat and receipt claiming a decision the external
tool call never actually received.

`decideExternal` (app.jsx) is the ONLY thing that tells
`claude_approval_hook.py`'s long-poll (`/approvals/external/wait`) what
the boss decided for an external (Claude Code PreToolUse hook) approval.
It used to be:

    const decideExternal = (externalId, decision, reason) => {
      fetch(...).catch(() => {});
    };

Called fire-and-forget from `onApprove`/`onReject`'s `ap.external`
branches, with no await, no retry, and no error surfaced anywhere. If
the POST failed (a transient localhost hiccup, the server mid-restart —
realistic for a locally-run dev server), the failure vanished into the
`.catch(() => {})`. Meanwhile: the receipt was already recorded as
'approved'/'rejected' as final (`recordReceipt`, called BEFORE this
branch runs), and chat already showed "✓ APPROVED — …" / "✕ REJECTED —
…". On the backend, the hook's long-poll never received the decision
(the server-side approval state was never updated), so it keeps
waiting until its own 30-minute timeout and then auto-DENIES the tool
call regardless of what the boss actually clicked — silently
contradicting the audit trail the boss is looking at, with no warning
for up to half an hour.

This is a direct asymmetry with the `publish` branch in the same
function (`onApprove`), which awaits its own async call, reports
success/failure explicitly via chat + `settleReceipt`, and uses
`officeCause` for a one-honest-sentence failure message — the standard
this codebase applies everywhere except here.

Found by a background hunt agent looking for "assumes a network/IPC
call always succeeds" bugs — a direct textual match for the
`.catch(() => {})` no-report pattern.

Fix: `decideExternal` now rejects on both a network failure and a
non-2xx response (it used to only guard the network case, and even
then only to discard it). Both `onApprove`'s and `onReject`'s
`ap.external` branches now await it inside an async IIFE (matching the
`publish` branch's own shape) and, on failure, post a one-sentence
chat warning and call `settleReceipt(rcId, 'failed', ...)` so the
receipt record no longer silently claims a decision that never arrived.

Run: python3 scripts/test_decide_external_reports_failure_instead_of_silent_drop.py
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
    print("decideExternal's failures are reported, not silently swallowed")

    src = APP.read_text(encoding='utf-8')

    fn_m = re.search(
        r"const decideExternal = \(externalId, decision, reason\) =>\n"
        r"(.*?)\n  ;",
        src, re.S)
    # Fallback: the arrow body may not end with a bare semicolon on its own
    # line — match up to the next top-level const instead.
    if not fn_m:
        fn_m = re.search(
            r"const decideExternal = \(externalId, decision, reason\) =>(.*?)\n  const recordReceipt",
            src, re.S)
    check('found decideExternal', fn_m is not None)
    fn_body = fn_m.group(1) if fn_m else ''

    check('decideExternal no longer swallows every failure with '
          '`.catch(() => {})` — the actual regression',
          '.catch(() => {})' not in fn_body)
    check('decideExternal now rejects on a non-2xx HTTP response too, '
          'not just a network-level failure',
          bool(re.search(r"if \(!r\.ok\) throw new Error", fn_body)))

    approve_m = re.search(
        r"if \(ap\.external && ap\.externalId\) \{(.*?)\n      \} else if \(ap\.agentId\) \{",
        src, re.S)
    check('found at least one ap.external branch (onApprove or onReject)',
          approve_m is not None)

    external_branches = re.findall(
        r"if \(ap\.external && ap\.externalId\) \{(.*?)\n      \} else if \(ap\.agentId\)",
        src, re.S)
    check('found both ap.external branches (onApprove and onReject)',
          len(external_branches) == 2, len(external_branches))

    for label, body in zip(['first (onApprove)', 'second (onReject)'], external_branches):
        check(f'{label} ap.external branch awaits decideExternal inside a '
              f'try/catch (no longer fire-and-forget)',
              'await decideExternal(' in body and 'catch (err)' in body)
        check(f'{label} ap.external branch reports a failure via chat '
              f'using officeCause (one honest sentence, matching the '
              f'publish branch\'s own standard)',
              'officeCause(err' in body)
        check(f'{label} ap.external branch calls settleReceipt on failure '
              f'so the receipt no longer silently claims a decision that '
              f'never arrived',
              "settleReceipt(rcId, 'failed'," in body)

    check("onReject now captures recordReceipt's return value as `rcId` "
          "(it used to discard it — settleReceipt needs it to correct "
          "the receipt on failure)",
          bool(re.search(r"const rcId = recordReceipt\(ap, 'rejected'\);", src)))

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
