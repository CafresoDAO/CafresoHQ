#!/usr/bin/env python3
"""A hand-off leaves no record the registry can see.

Measured 2026-08-15 on office 9261, canned brain. A brief delegated to
Vera ran to completion on the floor — the chat shows the delegation
bubble and her finished answer — while the registry held NOTHING for it
(77 records, none this run's). The Delegate path was the one dispatch
surface that never touched MessageRegistry:

  - the Inbox could not answer "what happened to that hand-off?";
  - a delegation that DIED filed no 'failed' row and no cause — the
    chat error bubble was the only witness, and it scrolls away;
  - a dismissal's outcome read never saw delegated work;
  - every DM the delegated coworker sent started a fresh, unlinked
    thread — the trail went cold one hop in.

The fix files the same lifecycle the @mention path files: minted after
the busy-desk door (a declined gesture was cancelled before anything
was dispatched — no record for work that never started), 'delivered' at
dispatch, 'in_progress' before the stream, the reply itself as the
'completed' note, and the catch splits 'cancelled'/'aborted by user'
from 'failed' with the SHARED cause table — classifyStreamFailure is
hoisted to module scope so both catches read one table instead of two
hand-written spellings. Vault writes attach as artifacts under the same
only-if-it-happened rule, and the DM continuation loop passes
parentMessageId so child records chain the thread.

Run: python3 scripts/test_a_handoff_leaves_a_record.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []

HOIST = 'const classifyStreamFailure = (s) =>'
DOOR = 'if (agentAbortersRef.current.has(a.id)) {'
MINT = 'toAgentId: a.id, toAgentName: a.name,'
DELIVERED = "MessageRegistry.transition(messageId, 'delivered', { by: 'host' });"
USERMSG = "const userMsg = { id: HQ.uid('m'), from: 'user', name: 'You', delegated: true"
INPROG = "MessageRegistry.transition(messageId, 'in_progress', { by: a.name });"
STREAM = 'await HQ.agentStream(a, brief'
COMPLETED = ("MessageRegistry.transition(messageId, 'completed', "
             "{ by: a.name, note: cleanBuf.slice(0, 120) || 'no body' });")
CATCHFILE = "MessageRegistry.transition(messageId, aborted ? 'cancelled' : 'failed', {"
RAW_ANCHOR = 'const raw = err && err.message || String(err);'


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('a hand-off leaves a record')
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    bare = strip_comments(app)

    # ── one cause table, both catches ───────────────────────────────────
    check('the cause table is hoisted once', bare.count(HOIST) == 1,
          f'{bare.count(HOIST)} sites')
    check('no catch keeps a private spelling of it',
          'const classify = (s)' not in bare,
          'two hand-written failure tables is how the reply-clean recipes drifted')
    # Shape, not census. This read `== 2` — the two dispatch catches that
    # existed when it was written — so the first correct third caller
    # failed it (2026-08-16: settleBossAsk, filing the chief of staff's own
    # stream through the same table, exactly what this check wants). A
    # count says "these two"; what the check means is "nobody builds a
    # cause any other way", and that survives a new caller doing it right.
    uses = bare.count('classifyStreamFailure(')
    shaped = bare.count('{ ...classifyStreamFailure(raw), message: raw.slice(0, 240) }')
    check('every catch that classifies a dead stream reads the shared table',
          uses >= 2 and shaped == uses,
          f'{uses} call(s), {shaped} of them built the same way — a caller '
          'assembling its own cause object is the drift this guards')

    # ── the delegate region files the lifecycle ─────────────────────────
    d_at = bare.find('const onDelegate = async (a, typed, thread)')
    d_end = bare.find('const onCoffee = (a)')
    check('the delegate region lifts', -1 < d_at < d_end)
    region = bare[d_at:d_end] if -1 < d_at < d_end else ''

    check('the hand-off is minted exactly once', region.count(MINT) == 1,
          f'{region.count(MINT)} mints')
    check("it is minted from the boss, body = the brief",
          "fromAgentId: 'boss', fromAgentName: 'You'," in region
          and 'body: brief' in region)
    door_at = region.find(DOOR)
    mint_at = region.find(MINT)
    deliv_at = region.find(DELIVERED)
    user_at = region.find(USERMSG)
    prog_at = region.find(INPROG)
    stream_at = region.find(STREAM)
    check('door → mint → delivered → bubble → in_progress → stream',
          -1 < door_at < mint_at < deliv_at < user_at < prog_at < stream_at,
          [door_at, mint_at, deliv_at, user_at, prog_at, stream_at,
           '— a declined gesture must file nothing, and the record must '
           'exist before the floor paints the work'])
    check('the reply itself is the completed note',
          region.count(COMPLETED) == 1)
    check("the catch splits a boss stop from a dead run",
          region.count(CATCHFILE) == 1
          and "'aborted by user'" in region
          and 'failureCause: cause,' in region)
    check('a vault write that happened attaches as the deliverable',
          region.count('MessageRegistry.attachArtifact(messageId, {') == 1
          and "if (!ev.failed && (ev.name === 'VAULT_NEW' || ev.name === 'VAULT_APPEND'))"
          in region)
    check("the coworker's own DMs chain to the hand-off record",
          region.count('parentMessageId: messageId') == 1)

    # ── behavior: the lifted pieces under node ──────────────────────────
    hoist_at = bare.find(HOIST)
    hoist_end = bare.find('\n};', hoist_at)
    table = bare[hoist_at:hoist_end + 3] if -1 < hoist_at < hoist_end else None
    gate = None
    if -1 < door_at < deliv_at:
        gate = region[door_at:deliv_at + len(DELIVERED)]
    filing = None
    raw_at = region.find(RAW_ANCHOR)
    file_at = region.find(CATCHFILE)
    if -1 < raw_at < file_at:
        file_end = region.find('});', file_at)
        filing = region[raw_at:file_end + 3]
    check('the table, the gate and the filing lift',
          bool(table and gate and filing))
    if not (table and gate and filing) or not shutil.which('node'):
        if not shutil.which('node'):
            print('  SKIP  node not on PATH — behavior checks need it')
        print()
        if FAILS:
            print(f'handoff-record: {len(FAILS)} FAILED')
            return 1
        print('handoff-record: source checks passed')
        return 0

    js = (
        table + '\n'
        + 'const a = { id: "a_v", name: "Vera" };\n'
        + 'const brief = "reconcile the vendor table";\n'
        + 'let calls, confirmAnswer;\n'
        + 'const agentAbortersRef = { current: new Map() };\n'
        + 'const MessageRegistry = {\n'
        + '  createMessage: (input) => { calls.mints.push(input); return "msg_1"; },\n'
        + '  transition: (id, state, meta) => { calls.transitions.push({ id, state,\n'
        + '    note: meta && meta.note, kind: meta && meta.failureCause && meta.failureCause.kind }); },\n'
        + '};\n'
        + 'const window = { hqConfirm: async (msg, opts) => { calls.confirms.push({ msg, danger: opts && opts.danger }); return confirmAnswer; } };\n'
        + 'const onUpdateAgent = () => {};\n'
        + 'const snagSentence = (s) => s;\n'
        + 'const gate = async () => {' + gate + ' return { proceeded: true }; };\n'
        + 'const file = (err, sigAborted) => { const aborted = sigAborted;\n'
        + '  const messageId = "msg_1";\n' + filing + '\n};\n'
        + '''
const runGate = async (busy, answer) => {
  calls = { mints: [], transitions: [], confirms: [] };
  confirmAnswer = answer;
  agentAbortersRef.current = new Map(busy ? [['a_v', {}]] : []);
  const out = await gate();
  return { out, mints: calls.mints.length, confirms: calls.confirms,
           transitions: calls.transitions };
};
const runFile = (err, aborted) => {
  calls = { mints: [], transitions: [], confirms: [] };
  file(err, aborted);
  return calls.transitions;
};
const R = {
  kinds: ['401 invalid bearer', 'quota hit 429', 'request timed out',
          'model x not found', 'ECONNREFUSED'].map(s => classifyStreamFailure(s).kind),
  quiet: await runGate(false, true),
  busyYes: await runGate(true, true),
  busyNo: await runGate(true, false),
  stopped: runFile(new Error('whatever'), true),
  dead: runFile(new Error('quota hit 429'), false),
};
console.log(JSON.stringify(R));
''')
    p = subprocess.run(['node', '--input-type=module', '-e',
                        '(async () => {' + js
                        + '})().catch(e => { console.error(e); process.exit(1); });'],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('lifted pieces run', False, p.stderr.strip()[:300])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('the table names auth, rate-limit, timeout, config, unknown',
          r['kinds'] == ['auth', 'rate-limit', 'timeout', 'config', 'unknown'],
          r['kinds'])
    check('a quiet desk mints without asking',
          r['quiet']['out'] == { 'proceeded': True } and r['quiet']['mints'] == 1
          and r['quiet']['confirms'] == []
          and [t['state'] for t in r['quiet']['transitions']] == ['delivered'],
          r['quiet'])
    check('a busy desk asks, then mints on yes',
          r['busyYes']['out'] == { 'proceeded': True } and r['busyYes']['mints'] == 1
          and len(r['busyYes']['confirms']) == 1
          and r['busyYes']['confirms'][0]['danger'] is True,
          r['busyYes'])
    check('a declined gesture files NOTHING',
          r['busyNo']['out'] is False and r['busyNo']['mints'] == 0
          and r['busyNo']['transitions'] == [],
          [r['busyNo'], '— a record for a hand-off that never started '
           'would file work nobody dispatched'])
    check("a boss stop files 'cancelled' / 'aborted by user', no cause",
          r['stopped'] == [{ 'id': 'msg_1', 'state': 'cancelled',
                             'note': 'aborted by user', 'kind': None }],
          r['stopped'])
    check("a dead run files 'failed' with the shared cause",
          r['dead'] == [{ 'id': 'msg_1', 'state': 'failed',
                          'note': 'rate-limit: Wait or upgrade plan',
                          'kind': 'rate-limit' }],
          r['dead'])

    print()
    if FAILS:
        print(f'handoff-record: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('handoff-record: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
