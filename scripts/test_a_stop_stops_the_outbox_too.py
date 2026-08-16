#!/usr/bin/env python3
"""STOP ALL pulled the plug and the office kept dispatching.

Measured 2026-08-15 on office 9261, canned brain (registry stamps are
UTC, so they read 2026-08-16). Kip's DM for Vera was waiting out her
busy desk in the #98 outbox. The boss pressed ■ STOP ALL and confirmed
'Stop all' at 00:36:42.543Z; the chat announced "aborted 1 stream"; and
at 00:36:48.357Z — six seconds later — Vera DELIVERED the waited note's
answer, lifecycle queued → delivered → in_progress → completed. The
office said everything stopped, then started new work.

Three leaks, one class — work HELD for later survives a sweep that only
kills work in FLIGHT:

  - the #98 wait loop polls `agentAbortersRef.current.has(agent.id)` —
    the exact map every sweep clears, so the sweep IS the go signal;
  - a stopped run's dmQueue still fans out: the DMs a killed reply
    queued are new dispatches, launched after "stop" (all THREE dispatch
    paths — @mention, Delegate, task drop — shared this);
  - the meeting loop takes turns sequentially, so aborting attendee
    two's stream never stops attendee three from being DISPATCHED.

The fix is one epoch: `stopEpochRef` bumps ONLY inside the office-wide
sweep (abortAllAgentRuns — which onStopAll and the unmount cleanup ride;
a per-desk stop does NOT bump, freeing one desk is not "stop
everything"). The wait loop captures the epoch before waiting and, on a
bump, files 'cancelled' (kind 'stopped-all') and says what was NOT
delivered; the fanout gates drop queued DMs on an aborted run and say
what the stop ate; the meeting adjourns with the truth about who never
spoke.

Amended 2026-08-16 by #120. The composer's ■ Stop used to ride that same
office-wide sweep, and this suite asserted it did — which made this file
a witness FOR a bug: the little button was stopping coworkers on jobs
the boss's turn had never touched. It now rides `abortTurnAgentRuns`,
which reaches only the runs the open turn started and bumps a separate
TURN epoch. The office sweep bumps BOTH, so everything below still holds
for STOP ALL, which is all this suite ever claimed. Two consequences are
pinned here rather than left to be rediscovered: a note held in the
outbox is dropped by an office sweep whether or not it belongs to a
turn, and the meeting loop — which IS a boss turn — now watches the turn
epoch, so it still adjourns on STOP ALL by way of that double bump.

Run: python3 scripts/test_a_stop_stops_the_outbox_too.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []

EPOCH_DECL = 'const stopEpochRef = useRefA(0);'
SWEEP_OPEN = 'const abortAllAgentRuns = () => {'
SWEEP_BUMP = 'stopEpochRef.current++;'
UNMOUNT = 'useEffectA(() => () => { abortAllAgentRuns(); }, []);'
WAIT_OPEN = 'if (agentAbortersRef.current.has(agent.id)) {'
WAIT_NOTE = 'waits its turn'
CAPTURE = 'const stopEpochAtWait = stopEpochRef.current;'
WAIT_LOOP = 'while (agentAbortersRef.current.has(agent.id)) {'
OFFICE_SWEPT = 'const sweptOffice = stopEpochRef.current !== stopEpochAtWait;'
EPOCH_CHECK = 'if (sweptOffice || sweptTurn) {'
STOPPED_ALL = "kind: 'stopped-all'"
GONE_CHECK = 'if (!(agentsRef.current || []).some(x => x.id === agent.id)) {'
DISPATCH_MARK = "const agentMsgId = HQ.uid('m');"
GATE = 'if (aborted && dmQueue.length) {'
GATE_DROP = 'dmQueue.length = 0;'
HOIST = 'let aborted = false;'
FANOUT = 'for (const dm of dmQueue) {'
# Since #120 the panel is handed the TURN epoch, not the office one. The
# office sweep bumps both, so STOP ALL still adjourns a meeting -- and a
# meeting the boss stops from the composer now adjourns too, which the
# office epoch alone could not have done.
PROP_PASS = 'turnEpochRef={turnEpochRef}'
PROP_SIG = 'turnEpochRef = null'
MEET_CAPTURE = 'const turnEpochAtStart = turnEpochRef ? turnEpochRef.current : null;'
MEET_LOOP = 'for (const [turnIdx, a] of recipients.entries()) {'
MEET_CHECK = 'if (turnEpochRef && turnEpochRef.current !== turnEpochAtStart) {'
ADJOURN = 'meeting adjourned — you stopped it.'


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('a stop stops the outbox too')
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    chatsrc = (ROOT / 'ui' / 'chat.jsx').read_text(encoding='utf-8')
    bare = strip_comments(app)
    cbare = strip_comments(chatsrc)

    # ── one epoch, bumped only by the shared sweep ──────────────────────
    check('the stop epoch exists, once', bare.count(EPOCH_DECL) == 1,
          f'{bare.count(EPOCH_DECL)} sites')
    sweep_at = bare.find(SWEEP_OPEN)
    sweep_end = bare.find('};', sweep_at)
    sweep = bare[sweep_at:sweep_end] if sweep_at != -1 and sweep_end > sweep_at else ''
    check('the sweep clears the map AND bumps the epoch',
          'agentAbortersRef.current.clear();' in sweep and SWEEP_BUMP in sweep,
          'clearing without bumping is exactly the six-second leak')
    check('nothing else bumps it', bare.count(SWEEP_BUMP) == 1,
          f'{bare.count(SWEEP_BUMP)} bumps — a per-desk stop must not adjourn the office')
    check('no private copy of the abort loop survives',
          bare.count('agentAbortersRef.current.clear()') == 1
          and bare.count('of agentAbortersRef.current.values()') == 1,
          'onStopAll kept its own sweep once; that copy is the one that forgot the epoch')
    stopall_at = bare.find('const onStopAll = async () => {')
    stopall = bare[stopall_at:bare.find('setMissions', stopall_at)] if stopall_at != -1 else ''
    check('STOP ALL rides the shared sweep', 'abortAllAgentRuns();' in stopall)
    check('the unmount cleanup rides the same sweep', UNMOUNT in bare,
          'a note waiting in the outbox must not fire a fetch after teardown')
    # This check used to read: the composer's ■ Stop rides it too. It did,
    # and that was #120 — the small button holding the office-wide brake.
    # What this suite actually needs is that the brake's OWN reach is
    # undiminished, and that the little button can no longer borrow it.
    check("the composer's ■ Stop no longer borrows the office sweep",
          'onStopAll' not in cbare and 'if (onStopTurn) onStopTurn();' in cbare,
          'see test_stop_takes_back_only_your_turn.py')
    check('…and the office sweep still bumps the turn epoch as well',
          'stopEpochRef.current++;' in sweep and 'turnEpochRef.current++;' in sweep,
          'without the second bump STOP ALL stops streams but not the meeting loop')

    # ── the wait loop reads the epoch, in the right order ───────────────
    check('the deferral block is where it was', bare.count(WAIT_OPEN) == 1,
          f'{bare.count(WAIT_OPEN)} sites')
    wait_at = bare.find(WAIT_OPEN)
    wait_end = bare.find(DISPATCH_MARK, wait_at)
    region = bare[wait_at:wait_end] if wait_at != -1 and wait_end > wait_at else ''
    order = [region.find(WAIT_NOTE), region.find(CAPTURE), region.find(WAIT_LOOP),
             region.find(OFFICE_SWEPT), region.find(EPOCH_CHECK),
             region.find(GONE_CHECK)]
    check('note → capture → wait → epoch check → recipient-gone, in that order',
          all(i != -1 for i in order) and order == sorted(order),
          order)
    epoch_block = region[region.find(EPOCH_CHECK):region.find(GONE_CHECK)] \
        if all(i != -1 for i in order) else ''
    check("a swept wait files 'cancelled' by the host, kind stopped-all",
          "'cancelled'" in epoch_block and "by: 'host'" in epoch_block
          and STOPPED_ALL in epoch_block and 'retryable: true' in epoch_block)
    check('…says what was NOT delivered, and dispatches nothing',
          'was not delivered' in epoch_block and "return '';" in epoch_block)

    # ── a stopped run delivers nothing — all three fanout paths ─────────
    check('aborted is hoisted out of all three catches',
          bare.count(HOIST) == 3, f'{bare.count(HOIST)} hoists')
    check('no catch re-shadows it',
          'const aborted =' not in bare,
          'a const in the catch is invisible to the fanout below it')
    check('three fanout gates', bare.count(GATE) == 3, f'{bare.count(GATE)} gates')
    check('each gate empties the queue', bare.count(GATE_DROP) == 3,
          f'{bare.count(GATE_DROP)} drops')
    loops = [m.start() for m in re.finditer(re.escape(FANOUT), bare)]
    guarded = [any(0 <= at - g <= 900 for g in
                   (m.start() for m in re.finditer(re.escape(GATE), bare)))
               for at in loops]
    check('every dmQueue loop sits behind a gate',
          len(loops) == 3 and all(guarded), f'{len(loops)} loops, guarded={guarded}')

    # ── the meeting takes the epoch and adjourns on it ──────────────────
    check('ChatPanel is handed the epoch', PROP_PASS in bare)
    check('…and declares the prop', PROP_SIG in cbare)
    mstart = cbare.find(MEET_CAPTURE)
    mloop = cbare.find(MEET_LOOP)
    mcheck = cbare.find(MEET_CHECK)
    mdispatch = cbare.find('await onDispatchToAgent(a, body, {', mloop)
    check('epoch captured before the turns start',
          -1 < mstart < mloop, (mstart, mloop))
    check('every turn checks the epoch BEFORE dispatching',
          mloop < mcheck < mdispatch, (mloop, mcheck, mdispatch))
    madj = cbare[mcheck:mdispatch] if -1 < mcheck < mdispatch else ''
    check('a bumped epoch adjourns with the truth about who never spoke',
          ADJOURN in madj and 'never got their turn' in madj and 'break;' in madj)
    check('the @all fan-out stays parallel',
          'Promise.all(recipients.map' in cbare,
          'only the MEETING serializes; the fan-out has no turn order to leak through')

    # ── drive the lifted pieces ─────────────────────────────────────────
    wait_lift = bare[wait_at:wait_end]
    g0 = bare.find(GATE)
    gate_lift = bare[g0:bare.find('}', bare.find(GATE_DROP, g0)) + 1]
    hs = cbare.find('const heardSoFar = [];')
    meet_lift = cbare[hs:cbare.find('} else {', hs)]
    check('the wait block lifts', wait_at != -1 and wait_end > wait_at)
    check('the gate lifts', g0 != -1 and GATE_DROP in gate_lift)
    check('the meeting loop lifts', -1 < hs < cbare.find('} else {', hs))

    js = ('const WAIT = ' + json.dumps(wait_lift) + ';\n'
          'const GATE = ' + json.dumps(gate_lift) + ';\n'
          'const MEET = ' + json.dumps(meet_lift) + ';\n'
          + r'''
let uidN = 0;
const mkSetChat = (chat) => (fn) => {
  const next = fn(chat.slice()); chat.length = 0; chat.push(...next);
};

/* `inBossTurn` defaults false: a coworker's DM waiting out a busy desk is
   nobody's turn, which is the whole point of the leak this suite is about
   — the note the boss never sees is the one the sweep must still reach. */
async function runWait(scenario, inBossTurn = false) {
  const chat = [], transitions = [];
  const agent = { id: 'a_1', name: 'Vera', role: 'Docs' };
  const dmFrom = { name: 'Kip' };
  const agentAbortersRef = { current: new Map([['a_1', { abort() {} }]]) };
  const stopEpochRef = { current: 3 };
  const turnEpochRef = { current: 5 };
  const agentsRef = { current: [agent] };
  const HQ = { uid: (p) => p + (++uidN) };
  const setChat = mkSetChat(chat);
  const MessageRegistry = {
    transition: (id, state, meta) => transitions.push({ id, state, meta }) };
  const messageId = 'msg_1';
  setTimeout(() => {          // the sweep (or the desk simply finishing)
    if (scenario === 'stopall') { stopEpochRef.current++; turnEpochRef.current++; }
    if (scenario === 'turnstop') turnEpochRef.current++;
    if (scenario === 'dismissed') agentsRef.current = [];
    agentAbortersRef.current.delete('a_1');
  }, 100);
  const fn = new Function('agentAbortersRef', 'agent', 'setChat', 'HQ',
    'dmFrom', 'stopEpochRef', 'turnEpochRef', 'inBossTurn',
    'MessageRegistry', 'messageId', 'agentsRef',
    'return (async () => {' + WAIT + "return 'DISPATCHED'; })();");
  const out = await fn(agentAbortersRef, agent, setChat, HQ, dmFrom,
    stopEpochRef, turnEpochRef, inBossTurn, MessageRegistry, messageId, agentsRef);
  return { out, notes: chat.map(c => c.text),
           trans: transitions.map(t => [t.state, t.meta.by,
             t.meta.failureCause && t.meta.failureCause.kind || null]) };
}

function runGateDrive(aborted, n) {
  const chat = [];
  const agent = { name: 'Kip' };
  const dmQueue = Array.from({ length: n }, (_, i) => ({ to: 'Vera', body: 'b' + i }));
  const HQ = { uid: (p) => p + (++uidN) };
  const setChat = mkSetChat(chat);
  const fn = new Function('aborted', 'dmQueue', 'agent', 'setChat', 'HQ', GATE);
  fn(aborted, dmQueue, agent, setChat, HQ);
  return { left: dmQueue.length, notes: chat.map(c => c.text) };
}

async function runMeeting(bumpAfterTurn, withRef) {
  const chat = [], dispatched = [];
  const turnEpochRef = withRef ? { current: 7 } : null;
  const recipients = [
    { id: 'a1', name: 'Kip', role: 'R' },
    { id: 'a2', name: 'Vera', role: 'D' },
    { id: 'a3', name: 'Miko', role: 'M' },
  ];
  const activeThread = 'meeting:m1';
  const body = 'agenda';
  const HQ = { uid: (p) => p + (++uidN) };
  const setChat = mkSetChat(chat);
  const bowOut = () => {};
  const onDispatchToAgent = async (a) => {
    dispatched.push(a.name);
    if (turnEpochRef && dispatched.length === bumpAfterTurn) turnEpochRef.current++;
    return a.name + ' spoke';
  };
  const fn = new Function('recipients', 'turnEpochRef', 'setChat', 'HQ',
    'activeThread', 'onDispatchToAgent', 'body', 'bowOut',
    'return (async () => {' + MEET + 'return heardSoFar.length; })();');
  const heard = await fn(recipients, turnEpochRef, setChat, HQ,
    activeThread, onDispatchToAgent, body, bowOut);
  return { dispatched, heard, notes: chat.map(c => c.text) };
}

const R = {
  clean: await runWait('clean'),
  stopall: await runWait('stopall'),
  stopallInTurn: await runWait('stopall', true),
  turnstopNotMine: await runWait('turnstop'),
  dismissed: await runWait('dismissed'),
  gateHit: runGateDrive(true, 2),
  gateOne: runGateDrive(true, 1),
  gateClean: runGateDrive(false, 2),
  adjourned: await runMeeting(1, true),
  lastTurn: await runMeeting(2, true),
  fullMeeting: await runMeeting(0, true),
  noRef: await runMeeting(1, false),
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

    check('a desk that simply finishes still dispatches',
          r['clean']['out'] == 'DISPATCHED' and r['clean']['trans'] == []
          and len(r['clean']['notes']) == 1, r['clean'])
    check("a sweep mid-wait cancels: by host, kind stopped-all, nothing dispatched",
          r['stopall']['out'] == ''
          and r['stopall']['trans'] == [['cancelled', 'host', 'stopped-all']]
          and any('was not delivered' in n for n in r['stopall']['notes'])
          and any('STOP ALL' in n for n in r['stopall']['notes']),
          r['stopall'])
    check('…and reaches a note that IS the boss\'s turn just the same',
          r['stopallInTurn']['out'] == ''
          and r['stopallInTurn']['trans'] == [['cancelled', 'host', 'stopped-all']],
          r['stopallInTurn'])
    # The other half of the same seam, kept here so the office sweep's reach
    # is stated next to its limit: a TURN stop is not a sweep of the office.
    check("a turn stop leaves somebody else's waiting note alone",
          r['turnstopNotMine']['out'] == 'DISPATCHED'
          and r['turnstopNotMine']['trans'] == [],
          r['turnstopNotMine'])
    check('…and the recipient-gone ending still works after it',
          r['dismissed']['out'] == ''
          and r['dismissed']['trans'] == [['failed', 'host', 'recipient-gone']],
          r['dismissed'])
    check('an aborted run drops its queued DMs and says so',
          r['gateHit']['left'] == 0
          and any('2 notes' in n and 'not sent' in n for n in r['gateHit']['notes']),
          r['gateHit'])
    check('…grammatically, when it was one note',
          r['gateOne']['left'] == 0
          and any('1 note queued' in n for n in r['gateOne']['notes']),
          r['gateOne'])
    check('a clean run keeps its queue', r['gateClean']['left'] == 2
          and r['gateClean']['notes'] == [], r['gateClean'])
    check('a sweep after turn one adjourns the meeting',
          r['adjourned']['dispatched'] == ['Kip'] and r['adjourned']['heard'] == 1
          and any('2 attendees never got their turn' in n
                  for n in r['adjourned']['notes']),
          r['adjourned'])
    check('…counting one attendee in the singular',
          r['lastTurn']['dispatched'] == ['Kip', 'Vera']
          and any('1 attendee never got their turn' in n
                  for n in r['lastTurn']['notes']),
          r['lastTurn'])
    check('an unswept meeting hears every attendee',
          r['fullMeeting']['dispatched'] == ['Kip', 'Vera', 'Miko']
          and r['fullMeeting']['heard'] == 3 and r['fullMeeting']['notes'] == [],
          r['fullMeeting'])
    check('a panel with no epoch prop still holds its meeting',
          r['noRef']['dispatched'] == ['Kip', 'Vera', 'Miko'],
          r['noRef'])

    if FAILS:
        print(f'FAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS))
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
