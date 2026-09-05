#!/usr/bin/env python3
"""An external (Claude Code PreToolUse hook) approval that times out
vanished from the tray with ZERO record anywhere — no receipt, no chat
line, nothing.

serve.py's `_gc_approvals()` auto-denies any pending entry that sits for
longer than `_APPROVAL_TTL_SEC` (30 minutes) with no human decision, and
evicts it from `_approvals_pending`. Confirmed live: shrank the TTL to
6s, POSTed a real request to /approvals/external, watched
/approvals/external/list return it, waited past the TTL, and watched
/approvals/external/list go back to `{"pending": []}` — the server log
shows `[approvals] queued ...` on submit but prints NOTHING when the GC
later denies/evicts it. No trace server-side, no trace in the log.

The UI's poll effect (app.jsx, the `/approvals/external/list` interval)
is the ONLY place a boss could ever learn what happened to that ask. Its
`setApprovals` updater computed:

    const kept = prev.filter(p => !p.externalId || liveIds.has(p.externalId));

— dropping any external row the server no longer lists — with a comment
("decided/expired elsewhere") but no actual handling: no `recordReceipt`,
no `settleReceipt`, no chat line. Lifted that exact updater out of
app.jsx and ran it for real (not reimplemented) with a `pending` list
that no longer contains a row the tray was tracking, mirroring the
curl-verified server state above: the tray row disappeared and every
side-effect mock (recordReceipt/settleReceipt/setChat) sat at zero
calls.

That's strictly worse than the already-fixed sibling bug (a failed POST
to /approvals/external/decide swallowed by `.catch(() => {})`,
scripts/test_decide_external_reports_failure_instead_of_silent_drop.py):
here the boss never even got to click, the office denied on their
behalf, and the Receipts modal — which calls itself "stamped approvals ·
audit trail" — has no entry for the decision it presided over.

Fix: the poll's updater now computes `timedOut` (the external rows that
were in `prev` but are no longer live) separately from `kept`, and for
each one calls `recordReceipt(ap, 'rejected')` +
`settleReceipt(rcId, 'expired', ...)` plus a single chat line (one row
if only one timed out, an aggregate line if several did) — reusing the
same receipt/outcome plumbing the `publish` and `decideExternal`-failure
branches already use elsewhere in this file. The steady-state no-op path
(nothing pending, nothing tracked) is untouched, and so is the ordinary
"a new ask arrived" path.

Run: python3 scripts/test_expired_external_approval_leaves_a_receipt.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FEATURES = ROOT / 'features.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract_paren_call(src, marker):
    """Lift `marker(...)` verbatim, brace/paren-matched — same technique
    scripts/test_a_busy_desk_is_not_cleared.py uses to lift a timer body,
    applied here to a call expression instead of a function body."""
    start = src.index(marker)
    i = start + len(marker)
    depth = 1
    while depth > 0:
        c = src[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        i += 1
    end = i
    if src[end:end + 1] == ';':
        end += 1
    return src[start:end]


def main():
    print('a timed-out external approval still leaves a receipt')

    app_src = APP.read_text(encoding='utf-8')
    feat_src = FEATURES.read_text(encoding='utf-8')

    # ── source shape ─────────────────────────────────────────────────────
    check("the poll still drops rows the server no longer lists "
          "(the mechanism being fixed, not removed)",
          "const kept = prev.filter(p => !p.externalId || liveIds.has(p.externalId));"
          in app_src)
    check('the fix names the dropped rows instead of silently discarding them',
          "const timedOut = prev.filter(p => p.externalId && !liveIds.has(p.externalId));"
          in app_src)
    check('every timed-out row gets a receipt',
          "recordReceipt(ap, 'rejected')" in app_src)
    check("...settled with an 'expired' outcome (distinct from approved/"
          "rejected/failed elsewhere in this file)",
          re.search(r"settleReceipt\(rcId, 'expired',", app_src) is not None)
    check('...and a chat line so the boss sees it without opening the '
          'Receipts modal',
          "timedOut.length === 1" in app_src and "were automatically denied"
          in app_src)
    check("ReceiptsModal gives the 'expired' outcome its own icon instead "
          "of falling into the generic ⚠ bucket used for a failed publish",
          "r.outcome === 'expired' ? '⏱ '" in feat_src)

    # ── behavior: lift the real setApprovals updater and run it ─────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — behavior checks need it')
        print()
        if FAILS:
            print(f'{len(FAILS)} FAILED')
            return 1
        print('source checks passed')
        return 0

    block = extract_paren_call(app_src, 'setApprovals(prev => {')
    check('the setApprovals updater lifts cleanly', block.startswith('setApprovals(prev => {'))

    # Run each scenario in its own process so the mock call-logs never leak
    # across scenarios (cleaner than threading extra reset plumbing through
    # a single run) -- mirrors the isolation test_a_busy_desk_is_not_cleared
    # gets via separate keys in one JSON blob; here separate runs are
    # simpler because each scenario needs a different closure-captured
    # `pending`.
    def run_scenario(pending_json, prev_json, extra_setup=''):
        script = '''
const calls = { recordReceipt: [], settleReceipt: [], chatMsgs: [] };
let capturedUpdater = null;
function setApprovals(fn) { capturedUpdater = fn; }
const agentsRef = { current: [] };
function formatToolInput(input) { return JSON.stringify(input || {}); }
/* Stub sibling of formatToolInput: the row's headline is built by
   app/approvals.jsx too (#282), so the lifted updater needs it in scope.
   This test is about the timeout/receipt path, not about the headline's
   own bidi guard — that has its own test. */
function approvalTitle(tool, summary, input) {
  return summary ? tool + ': ' + summary
                 : tool + ' (' + (Object.keys(input || {}).join(', ') || 'no args') + ')';
}
const HQ = { uid: (p) => p + '_test' };
function say() {}
function recordReceipt(ap, decision) {
  calls.recordReceipt.push({ ap, decision });
  return 'rc_' + calls.recordReceipt.length;
}
function settleReceipt(rcId, outcome, text) { calls.settleReceipt.push({ rcId, outcome, text }); }
function setChat(fn) { calls.chatMsgs.push(...fn([]).map(m => m.text)); }

let pending = ''' + pending_json + ''';
''' + extra_setup + '''
''' + block + '''

const prev = ''' + prev_json + ''';
const next = capturedUpdater(prev);
console.log(JSON.stringify({
  sameRef: next === prev,
  rowCount: next.length,
  recordReceipt: calls.recordReceipt,
  settleReceipt: calls.settleReceipt,
  chatMsgs: calls.chatMsgs,
}));
'''
        p = subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT,
                            capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            return None, p.stderr.strip()[:500]
        return json.loads(p.stdout.strip().split('\n')[-1]), None

    row_js = ("(externalId, title) => ({ id: 'apx_' + externalId, externalId, title, "
              "by: 'test-agent', kind: 'claude-code · tool use', elevated: true, "
              "external: true, cwd: '/tmp/demo', detail: 'd' })")

    # Scenario 1: one tracked row, server no longer lists it.
    r1, err1 = run_scenario(
        '[]',
        f"[({row_js})('ce_1', 'Bash: Clean up demo files')]")
    check('lifted updater runs (scenario: one row times out)', r1 is not None, err1)
    if r1:
        check('the timed-out row is removed from the tray', r1['rowCount'] == 0)
        check('...but a receipt is recorded for it',
              len(r1['recordReceipt']) == 1 and r1['recordReceipt'][0]['decision'] == 'rejected',
              r1['recordReceipt'])
        check("...settled with outcome 'expired', not silently approved",
              len(r1['settleReceipt']) == 1 and r1['settleReceipt'][0]['outcome'] == 'expired',
              r1['settleReceipt'])
        check('...and the boss gets a chat line naming the request',
              len(r1['chatMsgs']) == 1 and 'Clean up demo files' in r1['chatMsgs'][0],
              r1['chatMsgs'])

    # Scenario 2: two rows time out together -> one aggregate chat line.
    r2, err2 = run_scenario(
        '[]',
        f"[({row_js})('ce_a', 'Bash: task A'), ({row_js})('ce_b', 'Bash: task B')]")
    check('lifted updater runs (scenario: two rows time out together)', r2 is not None, err2)
    if r2:
        check('both rows get their own receipt',
              len(r2['recordReceipt']) == 2, r2['recordReceipt'])
        check('...but only ONE chat line (aggregated, not spammed)',
              len(r2['chatMsgs']) == 1 and '2' in r2['chatMsgs'][0], r2['chatMsgs'])

    # Scenario 3: ordinary new-ask path — must stay untouched by this fix.
    r3, err3 = run_scenario(
        "[{ id: 'ce_new', tool: 'Bash', input: { command: 'ls' }, cwd: '/tmp', "
        "agent: 'test-agent', summary: 'List files' }]",
        '[]')
    check('lifted updater runs (scenario: a brand-new ask arrives)', r3 is not None, err3)
    if r3:
        check('the new ask is added to the tray',
              r3['rowCount'] == 1, r3)
        check('...with no receipt/settle/chat noise (nothing was decided)',
              r3['recordReceipt'] == [] and r3['settleReceipt'] == [] and r3['chatMsgs'] == [],
              r3)

    # Scenario 4: steady state — the one row tracked is still live.
    r4, err4 = run_scenario(
        "[{ id: 'ce_1', tool: 'Bash', input: {}, cwd: '/tmp/demo', "
        "agent: 'test-agent', summary: 'Clean up demo files' }]",
        f"[({row_js})('ce_1', 'Bash: Clean up demo files')]")
    check('lifted updater runs (scenario: nothing changed)', r4 is not None, err4)
    if r4:
        check('React gets the SAME array reference back (no needless re-render)',
              r4['sameRef'] is True, r4)
        check('...and no side effects fire for a row that is still pending',
              r4['recordReceipt'] == [] and r4['settleReceipt'] == [] and r4['chatMsgs'] == [],
              r4)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
