#!/usr/bin/env python3
"""Approving (or rejecting) a request left the office still saying it needed
the boss — forever.

`onApprovalRequest` (app.jsx) writes TWO things for one decision: the stamp
card in `approvals`, and a `priority:'attention'`, `unread:true` mirror row
in the activity log so "Selvin requests approval: …" appears in the queue
next to failures and blocks. That row is not history — app/attention.jsx's
`attentionCount` counts an attention row for exactly as long as its own
`unread` flag is true, and that one function drives the office "N need you"
pill, the Team-nav badge AND the inbox's "Needs attention · N" tab.

`onApprove` and `onReject` removed the CARD (`setApprovals(prev =>
prev.filter(...))`) and never touched the row. So the moment the boss
stamped, the thing they had just decided went on being counted as needing
them — and now with no control anywhere that could answer it, because
Approve/Reject live on the card and the card is gone. The only escape was
spotting the dead row in the Team inbox and clicking it to mark it read.
Every approval the office ever asked for left one of these behind, so the
pill drifts monotonically upward over a session: stamp ten things, read
"10 need you", open the queue, find ten decisions you already made.

Fix: the mirror row's id is derived from the approval id at log time
(`approvalNoticeId`), and both handlers call `clearApprovalNotice(id)` right
next to the setApprovals that drops the card — up front, not inside one of
the `ap.kind` branches, several of which return early.

This test runs the REAL logActivity, the REAL onApprovalRequest, the REAL
approvalNoticeId/clearApprovalNotice lifted out of app.jsx, and the REAL
app/attention.jsx `attentionCount` under Node, and checks the pill goes
quiet after the stamp. It also pins the placement of the clear call ahead of
the kind-fork in both handlers, since a `publish`/`hire-agent`/
`grant-elevation` approval returns before ever reaching the bottom.

Run: python3 scripts/test_a_stamped_approval_stops_asking_for_the_boss.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
ATTENTION = ROOT / 'app' / 'attention.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract(text, start_marker, end_marker):
    """Lift a real block out of app.jsx, or return None if it isn't there."""
    i = text.find(start_marker)
    if i < 0:
        return None
    j = text.find(end_marker, i + len(start_marker))
    if j < 0:
        return None
    return text[i:j + len(end_marker)]


def run_js(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the real files')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('A stamped approval stops asking for the boss')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    app = APP.read_text(encoding='utf-8')

    notice_id = extract(app, 'function approvalNoticeId(', '\n')
    request = extract(app, '  const onApprovalRequest = (req) => {', '\n  };\n')
    clear = extract(app, '  const clearApprovalNotice = (apId) =>', ';\n')
    log_activity = extract(app, '  const logActivity = useCallbackA(', '), [setActivity]);')

    check('app.jsx derives the mirror row\'s id from the approval id, so the '
          'decision can find its own notice again',
          notice_id is not None,
          'no approvalNoticeId in app.jsx — the row is logged with a random '
          'HQ.uid("act") and nothing can ever link the stamp back to it')
    check('app.jsx has a clearApprovalNotice that marks that row read',
          clear is not None, 'not found in app.jsx')
    check('lifted the real logActivity and onApprovalRequest',
          log_activity is not None and request is not None,
          'app.jsx shape changed')

    # Placement: both handlers fork on ap.kind and RETURN from several
    # branches (publish, hire-agent, hire-assistant, grant-elevation,
    # workflow-step). A clear call after the fork would only fire for the
    # kinds that fall through, which is most of the bug back again.
    for handler in ('onApprove', 'onReject'):
        body = extract(app, '  const %s = (id) => {' % handler, '\n  };\n')
        if body is None:
            check('%s is still shaped as expected' % handler, False, 'not found')
            continue
        clear_at = body.find('clearApprovalNotice(id)')
        fork_at = body.find('ap.kind')
        check('%s clears the notice before it forks on ap.kind — a publish or '
              'hire approval returns early and would otherwise never reach it'
              % handler,
              clear_at >= 0 and (fork_at < 0 or clear_at < fork_at),
              'clearApprovalNotice at %d, first ap.kind at %d' % (clear_at, fork_at))

    if notice_id is None or clear is None or request is None or log_activity is None:
        print()
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1

    attention_src = '\n'.join(
        ln for ln in ATTENTION.read_text(encoding='utf-8').split('\n')
        if not ln.startswith('import ') and not ln.startswith('export '))

    # The real logActivity/onApprovalRequest/clearApprovalNotice over a
    # plain array standing in for React state, then the real attentionCount
    # asked the only question the pill asks: how many things need the boss?
    harness = """
%(attention)s
%(noticeId)s
let activity = [];
const setActivity = (fn) => { activity = fn(activity); };
let approvals = [];
const setApprovals = (fn) => { approvals = fn(approvals); };
const useCallbackA = (fn) => fn;
let uidN = 0;
const HQ = { uid: (p) => p + '_' + (++uidN) };
const say = () => {};
%(logActivity)s
%(request)s
%(clear)s

const roster = [{ id: 'a1', name: 'Selvin' }];
onApprovalRequest({ title: 'Ship the pricing page', by: 'Selvin', agentId: 'a1' });
const whilePending = attentionCount(activity, approvals, roster);
// The boss stamps it. The card goes; the queue must go quiet with it.
const apId = approvals[0].id;
setApprovals(prev => prev.filter(p => p.id !== apId));
clearApprovalNotice(apId);
const afterStamp = attentionCount(activity, approvals, roster);
const rowStillThere = activity.length;
const rowUnread = activity[0].unread;

// A SECOND, unrelated request must not be silenced by the first one's stamp.
onApprovalRequest({ title: 'Wire the payout', by: 'Selvin', agentId: 'a1' });
onApprovalRequest({ title: 'Delete the archive', by: 'Selvin', agentId: 'a1' });
const twoPending = attentionCount(activity, approvals, roster);
const firstId = approvals[0].id;
setApprovals(prev => prev.filter(p => p.id !== firstId));
clearApprovalNotice(firstId);
const oneLeft = attentionCount(activity, approvals, roster);

console.log(JSON.stringify({ whilePending, afterStamp, rowStillThere, rowUnread,
                             twoPending, oneLeft }));
""" % {'attention': attention_src, 'noticeId': notice_id,
       'logActivity': log_activity, 'request': request, 'clear': clear}
    R = run_js(harness)

    check('while the stamp is still pending the office does say it needs the '
          'boss (the fix must not silence a LIVE request)',
          R['whilePending'] >= 1, R)
    check('once the boss stamps it, nothing is left asking for them — this is '
          'the regression: the mirror row used to stay unread forever and the '
          '"N need you" pill went on counting a decision already made',
          R['afterStamp'] == 0, R)
    check('the row itself is still in the activity log — this closes the '
          'queue item, it does not erase what happened',
          R['rowStillThere'] == 1, R)
    check('the row is marked read rather than deleted', R['rowUnread'] is False, R)
    check('stamping one request does not silence another still waiting — two '
          'pending, stamp one, one still needs the boss',
          R['twoPending'] > R['oneLeft'] and R['oneLeft'] >= 1, R)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
