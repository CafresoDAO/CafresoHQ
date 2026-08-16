#!/usr/bin/env python3
"""The question the boss actually asked has to be in the log of questions.

Reproduced 2026-08-16 on a scratch office (127.0.0.1:9271, canned brain,
roster of Kip and Otto). One sentence typed into the composer:

    registry probe one one six — who is covering vendor spend?

CafresoHQ split it between two specialists. The registry came out holding
five records, and none of them was the question:

    You  -> Kip    parent None   thr_f83ukxy   "Pull the Q3 vendor numbers…"
    You  -> Otto   parent None   thr_l6gpl48   "Cross-check those vendor…"
    Kip  -> Otto   parent msg_…  thr_f83ukxy
    Otto -> Kip    parent msg_…  thr_l6gpl48
    Kip  -> Otto   parent msg_…  thr_l6gpl48

Three separate wrongs, all from one missing wire:

1. The boss's ask is absent. Every OTHER dispatch path mints — @mentions,
   the meeting room, /brainstorm, drag-to-delegate, agent-to-agent DMs —
   so the one path that never did is the default one, the thing the
   composer does when the boss just types. The tour says "every real
   action streams into the ticker and the Team inbox" and Getting Started
   says "the Team inbox logs every action".

2. `You -> Kip` over a brief the boss never wrote. Those two bodies are
   CafresoHQ's words; the Inbox credited them to the person reading it.

3. `parent None` and two threadIds. One question became two unrelated
   threads with no link to each other or to what caused them — in the one
   place the product keeps to answer "what happened to that?".

The registry already knew how to do this. `createMessage` inherits a
parent's threadId, and the agent-to-agent DMs three rows down show it
working. The dispatch that never supplied a parent was the one the boss
started.

So this suite holds:

  1. the ask is filed, to a chief of staff the registry can NAME
  2. it reaches a terminal state that matches what happened — including
     `cancelled` for a boss-pressed Stop, which is not a failure
  3. what CafresoHQ dispatches on the boss's behalf hangs off the ask and
     is attributed to CafresoHQ
  4. one ask stays one thread, however many people it reaches

Checks 1-4 run the real functions — `recordBossAsk`, `settleBossAsk`,
`classifyStreamFailure` and the registry's own `createMessage` — lifted
out and executed in node, because thread inheritance across a fan-out is
arithmetic over three records and reading the source does not prove it.

§5 (a wrong door is worse than a locked one — an Inbox that answers "no
such record" about work the office did is a wrong door onto its own
memory) and §6 (a record attributed to the boss is the office putting
words in their mouth).
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
CHAT = (ROOT / 'ui' / 'chat.jsx').read_text(encoding='utf-8')
RUNTIME = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')

FAILS = []


def check(label, ok, detail=''):
    if ok:
        print(f'  ok    {label}')
    else:
        FAILS.append(label)
        print(f'  FAIL  {label}' + (f'  — {detail}' if detail else ''))


def brace_from(src, j):
    if j < 0:
        return ''
    depth, k = 0, j
    while k < len(src):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[j:k + 1]
        k += 1
    return ''


def lift(src, opener):
    """The braced body that follows `opener`, or ''."""
    i = src.find(opener)
    return brace_from(src, src.find('{', i + len(opener) - 1)) if i >= 0 else ''


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', src)


def run_node(src):
    p = subprocess.run(['node', '--input-type=module', '-e', src],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stdout)
        print(p.stderr[-1800:], file=sys.stderr)
        return None
    return json.loads(p.stdout.strip().split('\n')[-1])


def main():
    print('the boss ask is on the record')

    # ── who the ask is addressed TO ──────────────────────────────────────
    m = re.search(r"const CHIEF_OF_STAFF = \{([^}]*)\}", RUNTIME)
    chief = {}
    if m:
        chief = dict(re.findall(r"(\w+):\s*'([^']*)'", m.group(1)))
    check('the chief of staff has an identity the registry can name',
          bool(chief.get('id')) and bool(chief.get('name')),
          '— hq-runtime.jsx: without one there is nothing to put in '
          "`toAgentId`, which is why the ask had nowhere to be filed")
    check('...and every door reads the same one',
          'ELEVATION_TOOL_IDS, CHIEF_OF_STAFF' in RUNTIME,
          '— app.jsx and ui/chat.jsx both reach it as HQ.CHIEF_OF_STAFF')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH — behavioural checks not run')
    else:
        record = lift(APP, 'const recordBossAsk = (text) =>')
        settle = lift(APP, 'const settleBossAsk = (id, err) =>')
        classify = lift(APP, 'const classifyStreamFailure = (s) =>')
        create = lift(APP, 'const createMessage = (input) =>')
        check('the ask-filing functions are liftable out of app.jsx',
              all([record, settle, classify, create]),
              f'— record={bool(record)} settle={bool(settle)} '
              f'classify={bool(classify)} create={bool(create)}; every '
              'behavioural check below runs these')

        if all([record, settle, classify, create]):
            harness = '''
const HQ = { CHIEF_OF_STAFF: %s };
const classifyStreamFailure = (s) => %s;

/* The real registry, with its three closure dependencies stubbed. The
   threadId inheritance below is the shipped code, not a restatement. */
let STORE = [];
const messagesRef = { get current() { return STORE; } };
const setMessages = (fn) => { STORE = fn(STORE); };
let seq = 0;
const _genId = (p) => p + '_' + (++seq);
const _now = () => 1000 + seq;
const createMessage = (input) => %s;

const CALLS = [];
const transition = (id, state, opts) => CALLS.push({ id, state, opts: opts || {} });
const MessageRegistry = { createMessage, transition };

const recordBossAsk = (text) => %s;
const settleBossAsk = (id, err) => %s;

const R = {};

// ── the ask itself ───────────────────────────────────────────────────
const askId = recordBossAsk('who is covering vendor spend?');
const ask = STORE[0];
R.ask = { from: ask.fromAgentName, toId: ask.toAgentId, toName: ask.toAgentName,
          body: ask.body, state: ask.state };
R.askDelivered = CALLS.map(c => c.state);

// ── the fan-out CafresoHQ causes, filed the way chat.jsx files it ─────
const leg = (name, body) => createMessage({
  parentId: askId,
  fromAgentId: HQ.CHIEF_OF_STAFF.id, fromAgentName: HQ.CHIEF_OF_STAFF.name,
  toAgentId: 'a_' + name.toLowerCase(), toAgentName: name, body,
});
leg('Kip', 'Pull the Q3 vendor numbers.');
leg('Otto', 'Cross-check those against the contracts.');
R.threads = [...new Set(STORE.map(m => m.threadId))].length;
R.legFrom = [...new Set(STORE.slice(1).map(m => m.fromAgentName))];
R.legParents = [...new Set(STORE.slice(1).map(m => m.parentId))];
R.records = STORE.length;

// A leg is still traceable when the specialist DMs onward — the same
// inheritance, one level deeper. This is what made the reproduced
// transcript TWO threads instead of one.
createMessage({ parentId: STORE[1].id, fromAgentId: 'a_kip', fromAgentName: 'Kip',
                toAgentId: 'a_otto', toAgentName: 'Otto', body: 'over to you' });
R.threadsAfterDm = [...new Set(STORE.map(m => m.threadId))].length;

// ── how the ask ends ─────────────────────────────────────────────────
const outcome = (err) => {
  CALLS.length = 0;
  settleBossAsk('msg_x', err);
  return CALLS[0] || null;
};
R.done = outcome(null);
const abort = new Error('aborted'); abort.name = 'AbortError';
R.stopped = outcome(abort);
R.broke = outcome(new Error('LM Studio 500: server_error'));
R.authBroke = outcome(new Error('401 invalid bearer token'));
CALLS.length = 0; settleBossAsk(null, null); R.noIdIsNoOp = CALLS.length === 0;

console.log(JSON.stringify(R));
''' % (json.dumps(chief), classify, create, record, settle)
            R = run_node(harness)
            if R is None:
                check('the lifted functions run', False, '— see stderr')
            else:
                check('the boss\'s question is filed',
                      R['ask']['body'] == 'who is covering vendor spend?'
                      and R['ask']['from'] == 'You',
                      f"— {R['ask']}; the reproduced registry held five "
                      'records and this was not one of them')
                check('...addressed to the chief of staff by name',
                      R['ask']['toId'] == chief.get('id')
                      and R['ask']['toName'] == chief.get('name'),
                      f"— to {R['ask']['toId']!r}/{R['ask']['toName']!r}")
                check('...and marked delivered, not left sitting at queued',
                      R['askDelivered'] == ['delivered'],
                      f"— {R['askDelivered']}; the office is holding it the "
                      'moment the chief of staff starts reading')

                check('a fan-out is attributed to whoever wrote the brief',
                      R['legFrom'] == [chief.get('name')],
                      f"— {R['legFrom']}; the shipped pair read `You → Kip` "
                      'over words CafresoHQ composed')
                check('...and hangs off the question that caused it',
                      len(R['legParents']) == 1 and R['legParents'][0] is not None,
                      f"— parents {R['legParents']}; both were None")
                check('...so one ask stays one thread',
                      R['records'] == 3 and R['threads'] == 1,
                      f"— {R['records']} records across {R['threads']} "
                      'thread(s); the reproduced fan-out made two')
                check('...and stays one when a specialist DMs onward',
                      R['threadsAfterDm'] == 1,
                      f"— {R['threadsAfterDm']} threads; inheritance has to "
                      'survive the second hop or the trail forks again')

                check('a finished turn completes the record',
                      R['done'] and R['done']['state'] == 'completed',
                      f"— {R['done']}")
                check('a boss-pressed Stop is cancelled, not failed',
                      R['stopped'] and R['stopped']['state'] == 'cancelled',
                      f"— {R['stopped']}; the @mention and delegate paths "
                      'both make this distinction and Needs-attention reads it')
                check('a dead brain fails the record with a cause to act on',
                      R['broke'] and R['broke']['state'] == 'failed'
                      and (R['broke']['opts'].get('failureCause') or {}).get('actionNeeded'),
                      f"— {R['broke']}; without this the most common failure "
                      'in the product has no row in Needs attention')
                check('...classified by the shared table, not a second one',
                      (R['authBroke']['opts'].get('failureCause') or {}).get('kind') == 'auth',
                      f"— a 401 came back as "
                      f"{(R['authBroke']['opts'].get('failureCause') or {}).get('kind')!r}; "
                      'two spellings of what killed a run is how the reply '
                      'cleaners drifted apart')
                check('settling a turn that was never filed does nothing',
                      R['noIdIsNoOp'],
                      '— onBossAsk can be absent (the panel renders outside '
                      'the office in tests) and that must not throw')

    # ── where the ask is minted ──────────────────────────────────────────
    # Order matters more than presence: every path that returns above this
    # already files through onDispatchToAgent, so minting too early files
    # the same turn twice.
    code = strip_comments(CHAT)
    i_mint = code.find('onBossAsk(text)')
    i_hand = code.find('if (handoffAgent) {')
    i_ment = code.find('if (mentionAll && onDispatchToAgent) {')
    i_brain = code.find("text.toLowerCase().startsWith('/brainstorm')")
    check('the ask is filed on the chief-of-staff path', i_mint > 0,
          '— ui/chat.jsx: nothing calls onBossAsk')
    check('...below every path that files its own record',
          i_mint > max(i_hand, i_ment, i_brain) > 0,
          f'— mint at {i_mint}, handoff {i_hand}, mentions {i_ment}, '
          f'brainstorm {i_brain}; those dispatch through onDispatchToAgent, '
          'which mints — filing here too would double-count the turn')

    # ── what the chief of staff dispatches ───────────────────────────────
    for label, marker in (('hand-off', 'if (ceoHandoff && onDispatchToAgent) {'),
                          ('fan-out', 'if (targets.length) {')):
        blk = lift(code, marker)
        check(f'the {label} is findable', bool(blk),
              '— the two checks below read it')
        check(f'...the {label} chains onto the ask',
              'parentMessageId: askId' in blk,
              f'— without it the {label} is an orphan record in a thread of '
              'its own')
        check(f'...and says who wrote the brief',
              'dispatchAs: HQ.CHIEF_OF_STAFF' in blk,
              '— the body is CafresoHQ\'s words and the record said "You"')

    # ── how the turn is settled ──────────────────────────────────────────
    check('a failed CEO stream is remembered past its catch',
          'askErr = err;' in code,
          '— ui/chat.jsx: the catch does not rethrow, so the error has to be '
          'carried out to the settle below the fan-out')
    i_settle = code.find('onBossAskSettled(askId, askErr)')
    i_fan = code.find('if (ceoHandoff && onDispatchToAgent) {')
    check('the record is settled after the work it caused, not before',
          i_settle > i_fan > 0,
          f'— settle at {i_settle}, fan-out at {i_fan}; `completed` while two '
          'specialists are still typing is the Inbox answering early')

    # ── the attribution seam stays narrow ────────────────────────────────
    disp = lift(APP, 'const dispatchToAgent = async (agent, prompt, opts = {}) =>')
    check('dispatchToAgent is findable', bool(disp))
    check('...and dmFrom still wins over dispatchAs',
          'const sender = dmFrom || dispatchAs;' in disp,
          '— an agent-to-agent DM is from that agent, whatever the caller '
          'says it is acting as')
    check('...and dispatchAs touches nothing but the record',
          strip_comments(disp).count('dispatchAs') == 2,
          '— destructure + the sender line, and no more. dmFrom also routes '
          'the thread to team, renames the bubble and changes the activity '
          'kind; the CEO fan-out is none of those')

    check('the chat panel is handed both ends of the lifecycle',
          'onBossAsk={recordBossAsk}' in APP and 'onBossAskSettled={settleBossAsk}' in APP,
          '— app.jsx: a mint with no settle strands every ask at delivered')

    print()
    if FAILS:
        print(f'FAILED {len(FAILS)} check(s):')
        for f in FAILS:
            print('  · ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
