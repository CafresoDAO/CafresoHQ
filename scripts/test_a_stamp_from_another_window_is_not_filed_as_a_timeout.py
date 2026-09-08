#!/usr/bin/env python3
"""An external approval the boss APPROVED was filed in the audit trail as
rejected, and announced to the boss as "automatically denied", while the
shell command it named had already run.

serve.py's /approvals/external/list answered with ONE fact — which ids are
still pending — so the UI could only ever see an id go missing. Three
different events drop an id out of that list:

  1. the boss stamped it   (POST /approvals/external/decide, allow)
  2. the boss declined it  (…, deny)
  3. nobody was there      (_gc_approvals auto-denies after 30 minutes)

`## 325.` taught app.jsx's poll to stop discarding the vanished rows in
silence, and — with nothing else to go on — to read all three as (3):

    const timedOut = prev.filter(p => p.externalId && !liveIds.has(p.externalId));
    timedOut.forEach(ap => {
      const rcId = recordReceipt(ap, 'rejected');
      settleReceipt(rcId, 'expired',
        'Timed out waiting for you (30 min) — automatically denied …');

Measured end to end against a real `python3 serve.py` and the real
`claude_approval_hook.py`, with no mocks between them: POST a Bash tool
call through the hook, watch it long-poll, POST the same decide body the
tray's `decideExternal` sends with decision 'allow' — the hook printed
`"permissionDecision": "allow"` and exited, i.e. Claude Code was told to
run `rm -rf /tmp/…` and ran it. Then GET /approvals/external/list, feed
that REAL response body to the REAL setApprovals updater lifted out of
app.jsx, and the office wrote:

    receipt   decision='rejected'  outcome='expired'
    chat      "⏱ Timed out waiting for you — Bash: rm -rf … was
               automatically denied."

for a command the boss had just approved and the machine had just
executed. The Receipts modal calls itself "stamped approvals · audit
trail"; here it recorded the opposite of the stamp it presided over.

Two ordinary ways in, neither exotic:
  * a second office window (both poll the same server; only the window
    that clicked removes its own row);
  * ONE window, with the click landing between `await r.json()` resolving
    and the updater running — a genuine await boundary.

Same family as `## 316.` (a declined payment reported as "💸 Sent 0.05
ICP"): the decision happened, the handler never received the outcome, and
the office narrated the reverse.

Fix: serve.py remembers WHY each entry left (`_approvals_resolved`, a
bounded outcome-only stub written under the same lock that flips the
decision, from both `_approval_decide` and `_gc_approvals`) and ships it
alongside `pending`. app.jsx splits the departed rows into the ones a
stamp accounts for (receipt carries the boss's real decision, settled
'ran' / 'blocked') and the ones it genuinely cannot (unchanged: 'rejected'
/ 'expired' — the arm that claims less, and still where an older server,
or an entry aged past the cap, lands).

Run: python3 scripts/test_a_stamp_from_another_window_is_not_filed_as_a_timeout.py
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
SERVE = ROOT / 'serve.py'
HOOK = ROOT / 'claude_approval_hook.py'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def get(url, timeout=10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode('utf-8') or '{}')
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, {'error': str(e)}


def post(url, body, timeout=10):
    req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'),
                                 method='POST',
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode('utf-8') or '{}')
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, {'error': str(e)}


def boot(work_dir):
    port = free_port()
    env = dict(os.environ, PORT=str(port), CAFRESOHQ_ALLOWED_DIRS=str(work_dir))
    for k in ('OCI_VAULT_NAMESPACE', 'OCI_VAULT_BUCKET', 'CAFRESOHQ_API_KEY'):
        env.pop(k, None)
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=str(ROOT), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = 'http://127.0.0.1:%d' % port

    def kill():
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    for _ in range(80):
        if get(base + '/health')[0] == 200:
            return base, kill
        time.sleep(0.25)
    kill()
    return None, (lambda: None)


def extract_paren_call(src, marker):
    """Lift `marker(...)` verbatim, paren-matched — the same technique
    scripts/test_expired_external_approval_leaves_a_receipt.py uses to run
    this exact updater, so both tests exercise the shipped code."""
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


def run_updater(block, list_body, prev_json):
    """Run the real updater over a REAL /approvals/external/list body."""
    script = '''
const calls = { recordReceipt: [], settleReceipt: [], chatMsgs: [] };
let capturedUpdater = null;
function setApprovals(fn) { capturedUpdater = fn; }
const agentsRef = { current: [] };
function formatToolInput(input) { return JSON.stringify(input || {}); }
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

/* Destructured exactly as app.jsx's poll destructures the response, off
   the body a real serve.py actually returned. */
const body = ''' + json.dumps(list_body) + ''';
const { pending = [], resolved = [] } = body;

''' + block + '''

const prev = ''' + prev_json + ''';
const next = capturedUpdater(prev);
console.log(JSON.stringify({
  rowCount: next.length,
  recordReceipt: calls.recordReceipt,
  settleReceipt: calls.settleReceipt,
  chatMsgs: calls.chatMsgs,
}));
'''
    p = subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        return None, p.stderr.strip()[:600]
    return json.loads(p.stdout.strip().split('\n')[-1]), None


ROW_JS = ("(externalId, title) => ({ id: 'apx_' + externalId, externalId, title, "
          "by: 'claude-code', kind: 'claude-code · tool use', elevated: true, "
          "external: true, cwd: '/tmp/demo', detail: 'd' })")


def drive(base, decision):
    """Run the REAL hook against the REAL server, stamp it, and hand back
    (hook decision, the /approvals/external/list body seen afterwards)."""
    payload = json.dumps({
        'tool_name': 'Bash',
        'tool_input': {'command': 'rm -rf /tmp/cafresohq-338-demo'},
        'cwd': '/tmp/demo',
        'session_id': 'sess-338',
    })
    env = dict(os.environ, CAFRESOHQ_HQ_URL=base, CAFRESOHQ_HQ_TIMEOUT='60')
    env.pop('CAFRESOHQ_HQ_FAILOPEN', None)
    hook = subprocess.Popen([sys.executable, str(HOOK)], cwd=str(ROOT), env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    hook.stdin.write(payload)
    hook.stdin.close()
    # communicate() below still tries to flush/close whatever `hook.stdin`
    # refers to, even though it is already closed — harmless on some Python
    # builds, a `ValueError: I/O operation on closed file` on others (measured
    # on 3.12; not on 3.14 here). None tells communicate() there's nothing
    # left to write, matching what the hook already received.
    hook.stdin = None

    aid = None
    for _ in range(60):
        st, body = get(base + '/approvals/external/list')
        if st == 200 and body.get('pending'):
            aid = body['pending'][0]['id']
            break
        time.sleep(0.1)
    if not aid:
        hook.kill()
        return None, None, None

    # Exactly the body app.jsx's decideExternal POSTs.
    post(base + '/approvals/external/decide',
         {'id': aid, 'decision': decision,
          'reason': ('approved' if decision == 'allow' else 'rejected')
                    + ' by boss in HQ'})
    try:
        out, _err = hook.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        hook.kill()
        return aid, None, None
    try:
        hooked = json.loads(out)['hookSpecificOutput']['permissionDecision']
    except Exception:
        hooked = None
    _st, after = get(base + '/approvals/external/list')
    return aid, hooked, after


def main():
    print('a stamp made in another window is not filed as a timeout')

    app_src = APP.read_text(encoding='utf-8')
    serve_src = SERVE.read_text(encoding='utf-8')

    # ── source shape ─────────────────────────────────────────────────────
    check('the server remembers WHY an approval left the pending list',
          '_approvals_resolved' in serve_src
          and 'def _remember_resolution' in serve_src)
    check('...written when the boss stamps AND when the GC auto-denies',
          serve_src.count('_remember_resolution(') >= 3)
    check('...and it is bounded, so a long day cannot grow it forever',
          '_APPROVALS_RESOLVED_CAP' in serve_src)
    check("...and it ships alongside 'pending' on the list endpoint",
          "'resolved': resolved" in serve_src)
    check('the poll reads it, defaulting to [] against an older server',
          'const { pending = [], resolved = [] } = await r.json();' in app_src)
    check('the departed rows are split by what the server says happened',
          'const stamped = timedOut.filter(' in app_src
          and 'const reallyTimedOut = timedOut.filter(' in app_src)

    if not shutil.which('node'):
        print('  SKIP  node not on PATH — behavior checks need it')
        print()
        return 1 if FAILS else 0

    block = extract_paren_call(app_src, 'setApprovals(prev => {')
    check('the setApprovals updater lifts cleanly',
          block.startswith('setApprovals(prev => {'))

    # ── behaviour: real server + real hook + real updater ────────────────
    tmp = tempfile.mkdtemp(prefix='cafresohq-338-')
    base, kill = boot(tmp)
    check('serve.py boots', base is not None)
    if not base:
        shutil.rmtree(tmp, ignore_errors=True)
        print()
        print(f'{len(FAILS)} FAILED')
        return 1
    try:
        # 1. APPROVE — the tool call reaches the world, so the record must
        #    not say it was denied.
        aid, hooked, after = drive(base, 'allow')
        check('the real hook long-polls a real queued approval', aid is not None)
        check('...and a stamped approval reaches Claude Code as "allow" '
              '(the command RAN)', hooked == 'allow', hooked)
        check('...while the list endpoint stops listing it',
              bool(after) and not after.get('pending'), after)
        check('...but now reports its fate instead of just dropping it',
              bool(after) and any(x.get('id') == aid and x.get('decision') == 'allow'
                                  and not x.get('expired')
                                  for x in (after or {}).get('resolved', [])),
              (after or {}).get('resolved'))

        r1, err1 = run_updater(block, after or {},
                               f"[({ROW_JS})({json.dumps(aid)}, 'Bash: rm -rf /tmp/cafresohq-338-demo')]")
        check('the updater runs on the real response body', r1 is not None, err1)
        if r1:
            check('the row leaves the tray (it is decided)', r1['rowCount'] == 0)
            check("the receipt records the boss's REAL decision, not 'rejected'",
                  len(r1['recordReceipt']) == 1
                  and r1['recordReceipt'][0]['decision'] == 'approved',
                  r1['recordReceipt'])
            check("...settled as the tool call having RUN, not as 'expired'",
                  len(r1['settleReceipt']) == 1
                  and r1['settleReceipt'][0]['outcome'] == 'ran',
                  r1['settleReceipt'])
            check('...and the boss is never told an approved call was '
                  'automatically denied',
                  all('automatically denied' not in m and 'Timed out' not in m
                      for m in r1['chatMsgs']), r1['chatMsgs'])
            check('...the chat line says it ran',
                  len(r1['chatMsgs']) == 1 and 'ran' in r1['chatMsgs'][0],
                  r1['chatMsgs'])

        # 2. DECLINE — a real "no" must not be filed as an unattended
        #    timeout either; the boss made that call and the trail says so.
        aid2, hooked2, after2 = drive(base, 'deny')
        check('a declined approval reaches Claude Code as "deny"',
              hooked2 == 'deny', hooked2)
        r2, err2 = run_updater(block, after2 or {},
                               f"[({ROW_JS})({json.dumps(aid2)}, 'Bash: rm -rf /tmp/cafresohq-338-demo')]")
        check('the updater runs on the real response body (declined)',
              r2 is not None, err2)
        if r2:
            check('the receipt still records a rejection',
                  len(r2['recordReceipt']) == 1
                  and r2['recordReceipt'][0]['decision'] == 'rejected',
                  r2['recordReceipt'])
            check("...but settled 'blocked' (a decision), not 'expired' "
                  '(nobody was there)',
                  len(r2['settleReceipt']) == 1
                  and r2['settleReceipt'][0]['outcome'] == 'blocked',
                  r2['settleReceipt'])
            check('...and the boss is not told it timed out',
                  all('Timed out' not in m for m in r2['chatMsgs']),
                  r2['chatMsgs'])

        # 3. The arm that claims less survives: a row the server cannot
        #    account for (restarted, aged past the cap) still reads as a
        #    timeout — the `## 325.` behaviour, unchanged.
        r3, err3 = run_updater(block, {'pending': [], 'resolved': []},
                               f"[({ROW_JS})('ce_unknown', 'Bash: something old')]")
        check('the updater runs (scenario: fate unknown)', r3 is not None, err3)
        if r3:
            check('an unaccounted-for row still leaves an expired receipt',
                  len(r3['recordReceipt']) == 1
                  and r3['recordReceipt'][0]['decision'] == 'rejected'
                  and r3['settleReceipt'][0]['outcome'] == 'expired',
                  (r3['recordReceipt'], r3['settleReceipt']))
            check('...and still says so in chat',
                  len(r3['chatMsgs']) == 1
                  and 'automatically denied' in r3['chatMsgs'][0],
                  r3['chatMsgs'])

        # 4. A genuine GC expiry is flagged as such, so it lands in (3)'s
        #    arm rather than being read as a stamp.
        r4, err4 = run_updater(
            block,
            {'pending': [],
             'resolved': [{'id': 'ce_gc', 'ts': 0, 'decision': 'deny',
                           'reason': 'expired (no human present)',
                           'expired': True}]},
            f"[({ROW_JS})('ce_gc', 'Bash: nobody was watching')]")
        check('the updater runs (scenario: GC expiry)', r4 is not None, err4)
        if r4:
            check("a GC auto-deny is NOT dressed up as the boss's decision",
                  len(r4['settleReceipt']) == 1
                  and r4['settleReceipt'][0]['outcome'] == 'expired',
                  r4['settleReceipt'])
    finally:
        kill()
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
