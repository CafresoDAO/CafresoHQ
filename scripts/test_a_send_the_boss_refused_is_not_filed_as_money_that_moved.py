#!/usr/bin/env python3
"""The boss declined the payment and the office filed it as paid.

#276 gave WALLET_SEND its own row in VISIT_WORDS, so the tool that moves the
boss's money stopped being captioned "Checked". That row shipped a `fail`
tense alongside the `past` one for exactly the reason this test exists -- "a
send that was refused must not read as a send that went through" -- and
nothing in the app was ever able to select it.

`wallet_send`'s handler was declared `run: async (arg) => {`. Two parameters
short. The runtime calls every tool as `run(arg, { signal, meta }, body)` and
reads `meta.failed` afterwards, because a tool can fail WITHOUT raising: this
one answers all six of its bridge statuses with an ordinary string. Never
having taken `ctx`, it had no `meta` to write to, so the runtime read "it
returned" as "it worked" and stamped the past tense over all six.

BEFORE, on a send the boss had just declined -- the desk bubble, the activity
feed and the filed delivery note, in the office's own voice:

    💸 Sent 0.05 ICP -> aaaaa-bbbbb-ccccc-ddddd-cai : tip for the review
    The boss declined the 0.05 ICP send to aaaaa-bbbbb-ccccc-ddddd-cai

Two lines, one event, opposite claims, and the heading is the half a boss
skims. The same caption sat over a send still waiting for a stamp, a send
the ledger threw out, and a send blocked by a paused wallet.

AFTER, three different facts told apart, because "not sent" is three
different instructions to whoever decides what happens next:

    🚫 Refused, so did not send 0.05 ICP -> aaaaa-…   (finished business)
    ⏳ Asked the boss to send 0.05 ICP -> aaaaa-…     (LIVE -- do not re-issue)
    ⚠ Couldn't send 0.05 ICP -> aaaaa-…              (may be worth retrying)

The middle one is the dangerous one to get wrong in the other direction: a
pending send captioned "Couldn't send" invites the boss to send it again, and
when the stamp lands the payee is paid twice.

This test drives the REAL handler, lifted verbatim from hq-runtime.jsx and
run under node against a stubbed bridge, then feeds what it actually sets on
`meta` through the REAL floor vocabulary and the REAL filed-note composer.
Nothing is paraphrased.

Run: python3 scripts/test_a_send_the_boss_refused_is_not_filed_as_money_that_moved.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'hq-runtime.jsx'
FLOOR = ROOT / 'app' / 'floor.jsx'
ARTIFACTS = ROOT / 'app' / 'artifacts.jsx'
APP = ROOT / 'app.jsx'
CHAT = ROOT / 'ui' / 'chat.jsx'
FAILS = []

ARG = 'ICP 0.05 aaaaa-bbbbb-ccccc-ddddd-cai : tip for the design review'


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Source with /*…*/ and //… removed.

    A test that greps for a bad pattern must not be able to match the comment
    that explains why the pattern is gone. This file's own fix is documented
    in prose directly above the code it fixed, in the words of the bug.
    Strings are left alone -- no pattern below looks inside one."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2)
            i = n if j == -1 else j + 2
            out.append(' ')
        elif c == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i)
            i = n if j == -1 else j
            out.append(' ')
        elif c in '"\'`':
            q, j = c, i + 1
            while j < n and src[j] != q:
                j += 2 if src[j] == '\\' else 1
            out.append(src[i:min(j + 1, n)])
            i = j + 1
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def handler_lift(src, anchor):
    """The `async (…) => { … }` expression that follows `anchor`, verbatim.

    Anchored on the registry spread that names the tool, so it lifts the copy
    the app really binds, and cannot silently drift onto a sibling `run:`."""
    i = src.index(anchor)
    r = src.index('run:', i)
    a = src.index('=> {', r)
    k, d = a + 3, 0
    while k < len(src):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                break
        k += 1
    return src[r + len('run:'):k + 1]


def floor_scope():
    t = FLOOR.read_text(encoding='utf-8')
    return '\n'.join(ln for ln in t.split('\n')
                     if not ln.startswith('import ') and not ln.startswith('export '))


def artifacts_working_notes():
    """`workingNotes` lifted from app/artifacts.jsx -- the FILED note."""
    t = ARTIFACTS.read_text(encoding='utf-8')
    i = t.index('function workingNotes(visits) {')
    k, d = t.index('{', i + len('function workingNotes(visits) ') - 1), 0
    while k < len(t):
        if t[k] == '{':
            d += 1
        elif t[k] == '}':
            d -= 1
            if d == 0:
                break
        k += 1
    return t[i:k + 1]


def run_js(js):
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-2000:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(p.stdout.strip().split('\n')[-1])


def main():
    print('a send the boss refused is not filed as money that moved')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    for f in (RUNTIME, FLOOR, ARTIFACTS, APP, CHAT):
        if not f.is_file():
            print(f'  FAIL  missing {f}')
            return 1

    rt = RUNTIME.read_text(encoding='utf-8')
    rt_code = strip_comments(rt)

    # ── 0. the premise ───────────────────────────────────────────────────
    print('0. the premise: a tool that moves money and settles on its own')
    check('the registry still ships a WALLET_SEND',
          "name: 'WALLET_SEND'" in rt,
          'if this tool is gone the rest of this test is about nothing')
    check('...and it still settles under the cap without a second surface',
          'settles automatically' in rt,
          'if every send now waits for a stamp, the floor caption is no '
          'longer the only record of one — it is still the first')
    check('the runtime still reads meta.failed off a tool that did not raise',
          'failed: !!meta.failed' in rt_code,
          'the whole mechanism this fix hangs on')

    # ── 1. the handler takes ctx at all ──────────────────────────────────
    print('1. the handler can reach meta')
    send_src = handler_lift(rt, '...TOOL_REGISTRY.wallet_send,')
    send_code = strip_comments(send_src)
    sig = send_code[:send_code.index('=>')]
    check('wallet_send no longer takes only the argument',
          not re.match(r'\s*async\s*\(\s*arg\s*\)\s*$', sig),
          f'{sig.strip()!r} — a handler with one parameter never receives '
          'ctx, so it can never report anything but success')
    check('...it names a second parameter, which is where meta lives',
          re.search(r'async\s*\(\s*\w+\s*,', sig) is not None, sig.strip())
    check('...and actually writes the failure flag',
          'meta.failed' in send_code, 'nothing sets what the floor reads')
    check('...and the outcome beside it',
          'meta.outcome' in send_code,
          'without this all four not-sent statuses collapse to one sentence')

    # ── 2. drive the real handler against every status it can return ─────
    print('2. the real handler, run against every status the bridge returns')
    statuses = ['ok', 'needsApproval', 'declined', 'paused', 'noWallet',
                'error', 'somethingNobodyHasWrittenYet']
    out = run_js(floor_scope() + '\n' + artifacts_working_notes() + '\n' + r'''
const ARG = %s;
const STATUSES = %s;
let NEXT = null;
const CafresoHQChain = { wallet: { send: async () => NEXT } };
const walletAgentId = 'kip';
const walletSend = %s;

const R = { rows: {}, malformed: null };
for (const status of STATUSES) {
  NEXT = { status, block: 4211, reason: 'over cap', error: 'InsufficientFunds' };
  const meta = {};
  const result = await walletSend(ARG, { signal: null, meta });
  /* Composed exactly as the runtime's done-emission composes it. */
  const ev = { name: 'WALLET_SEND', arg: ARG, result,
               failed: !!meta.failed, outcome: meta.outcome || '' };
  const visit = toVisit(ev);
  R.rows[status] = {
    failed: !!meta.failed, outcome: meta.outcome || '', result,
    head: visit.head, icon: visit.icon,
    feed: toolActivity({ id: 'a1', name: 'Kip', color: '#fff' }, ev).text,
    /* The filed delivery note, through the visit record the app stores. */
    note: workingNotes([{ name: ev.name, arg: ev.arg, failed: ev.failed,
                          outcome: visit.outcome }])[0],
  };
}
/* A call the model got wrong: no destination, so nothing could be sent. */
{
  NEXT = { status: 'ok', block: 1 };
  const meta = {};
  const result = await walletSend('ICP 0.05', { signal: null, meta });
  R.malformed = { failed: !!meta.failed, result,
                  head: toVisit({ name: 'WALLET_SEND', arg: 'ICP 0.05',
                                  result, failed: !!meta.failed,
                                  outcome: meta.outcome || '' }).head };
}
/* The live bubble is about an attempt in flight and stays the present tense. */
R.live = visitLine('WALLET_SEND', ARG, 'now');
/* A read of a file that is not there is not a read (memory_read's twin). */
R.notFound = toVisit({ name: 'MEMORY_READ', arg: 'work/plans.md',
                       result: '(no memory saved…)', failed: true }).head;
/* Nothing that cannot fail may be dragged into the not-sent vocabulary. */
R.balance = toVisit({ name: 'WALLET_BALANCE', arg: 'all',
                      result: 'x' }).head;
console.log(JSON.stringify(R));
''' % (json.dumps(ARG), json.dumps(statuses), send_src))

    rows = out['rows']

    print('   2a. a send that went through')
    ok = rows['ok']
    check('ok is the one status that keeps the past tense',
          ok['failed'] is False and ok['head'].startswith('Sent '), ok['head'])
    check('...with the money icon', ok['icon'] == '💸', ok['icon'])
    check('...and the feed says sent', ok['feed'].startswith('sent '), ok['feed'])
    check('...and so does the filed note',
          ok['note'].startswith('- Sent '), ok['note'])

    print('   2b. the four that did not send are not captioned as sends')
    for s in ('needsApproval', 'declined', 'paused', 'error',
              'noWallet', 'somethingNobodyHasWrittenYet'):
        r = rows[s]
        check(f'{s}: the handler reports it did not work', r['failed'] is True,
              f"{r['result'][:70]!r}")
        for surface in ('head', 'feed', 'note'):
            check(f'{s}: the {surface} does not say the money was sent',
                  not re.search(r'\bsent\b', r[surface].split(' ')[0], re.I)
                  or 'not send' in r[surface].lower(),
                  r[surface])

    print('   2c. and the three answers are told apart')
    check('a declined send reads as a refusal, not a breakage',
          rows['declined']['outcome'] == 'refused'
          and 'did not send' in rows['declined']['head'].lower(),
          rows['declined']['head'])
    check('...and carries the refusal icon, not the warning triangle',
          rows['declined']['icon'] == '🚫', rows['declined']['icon'])
    check('a paused wallet is a standing decision, not a retryable error',
          rows['paused']['outcome'] == 'refused', rows['paused']['outcome'])
    check('a send awaiting the stamp reads as LIVE, so it is not re-issued',
          rows['needsApproval']['outcome'] == 'pending'
          and 'asked the boss' in rows['needsApproval']['head'].lower(),
          rows['needsApproval']['head'])
    check('...and is not captioned "Couldn\'t send", which invites a double pay',
          "couldn't send" not in rows['needsApproval']['head'].lower(),
          rows['needsApproval']['head'])
    check('...with the waiting icon, because nothing has gone wrong yet',
          rows['needsApproval']['icon'] == '⏳', rows['needsApproval']['icon'])
    check('a ledger error stays a plain failure, which may be worth retrying',
          rows['error']['outcome'] == ''
          and rows['error']['head'].lower().startswith("couldn't send"),
          rows['error']['head'])
    check('a status this office has never seen claims less, never more',
          rows['somethingNobodyHasWrittenYet']['failed'] is True
          and rows['somethingNobodyHasWrittenYet']['outcome'] == '',
          'an unknown status is not a receipt, and is not a diagnosis either')
    check('the three not-sent headings are three different sentences',
          len({rows['declined']['head'], rows['needsApproval']['head'],
               rows['error']['head']}) == 3,
          'collapsing them is honest about the money and useless about '
          'the next move')

    print('   2d. the filed note carries the distinction too')
    check('the note distinguishes a refusal from a breakage',
          rows['declined']['note'] != rows['error']['note'],
          rows['declined']['note'])
    check('...and a pending send from a refused one',
          rows['needsApproval']['note'] != rows['declined']['note'],
          rows['needsApproval']['note'])
    check('the note never files a not-sent send as "Sent"',
          all(not rows[s]['note'].startswith('- Sent ')
              for s in ('declined', 'needsApproval', 'paused', 'error')),
          {s: rows[s]['note'] for s in ('declined', 'needsApproval')})

    print('   2e. no collateral')
    check('a malformed send is not filed as a send either',
          out['malformed']['failed'] is True
          and not out['malformed']['head'].startswith('Sent '),
          out['malformed']['head'])
    check('the live bubble still describes an attempt in flight',
          out['live'].startswith('sending '), out['live'])
    check('a balance check is still a plain look',
          out['balance'].startswith('Checked '), out['balance'])
    check('a memory read of a file that is not there is not "Opened"',
          not out['notFound'].startswith('Opened'), out['notFound'])

    # ── 3. the plumbing, at every joint ──────────────────────────────────
    print('3. the outcome survives the trip to every surface')
    done = re.findall(r"phase: 'done'[\s\S]{0,320}?\}\);", rt_code)
    check('the runtime emits a done event from more than one place',
          len(done) >= 2, len(done))
    check('...and every one of them carries the outcome',
          all('outcome:' in d for d in done),
          'a fix on one emission and not its twin is worth nothing')
    check('toVisit stores the outcome on the visit record it keeps',
          re.search(r'outcome:\s*ev\.outcome', strip_comments(
              FLOOR.read_text(encoding='utf-8'))) is not None,
          'the filed note re-derives its tense from this long after the '
          'event is gone')
    for f in (APP, CHAT):
        src = strip_comments(f.read_text(encoding='utf-8'))
        pushes = re.findall(r'Visits\.push\(\{[^}]*\}', src)
        check(f'{f.name}: every stored visit carries the outcome forward',
              bool(pushes) and all('outcome' in p for p in pushes),
              [p for p in pushes if 'outcome' not in p] or 'no push sites found')

    # ── 4. the twins in the same registry ────────────────────────────────
    print('4. the twins — handlers that answer a failure with a plain string')
    for anchor, label in (('...TOOL_REGISTRY.publish_site,', 'publish_site (bound)'),
                          ('...TOOL_REGISTRY.memory_read,', 'memory_read (bound)')):
        h = strip_comments(handler_lift(rt, anchor))
        sig = h[:h.index('=>')]
        check(f'{label} takes a second parameter',
              re.search(r'async\s*\(\s*\w+\s*,', sig) is not None, sig.strip())
        check(f'{label} sets the failure flag on the path that did not work',
              'meta.failed' in h, 'it returns a failure as an ordinary string')
    pub = strip_comments(handler_lift(rt, "name: 'PUBLISH_SITE',"))
    check('the unbound publish_site twin was fixed alongside it',
          'meta.failed' in pub,
          'the dominant bug class in this codebase is a fix landing on one '
          'copy while its twin keeps the defect')

    print()
    if FAILS:
        print(f'a refused send: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:4]))
        return 1
    print('a refused send: all checks passed')
    return 0


raise SystemExit(main())
