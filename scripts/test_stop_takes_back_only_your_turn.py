#!/usr/bin/env python3
"""The little Stop was the big red brake with a quieter tooltip.

Measured 2026-08-16, office 9272. Kip was four minutes into a job the
boss had delegated from the composer's own hand-off menu. The boss then
asked the chief of staff an unrelated question and pressed the
composer's ■ Stop — tooltip "Stop streaming" — to take the question
back. BOTH records went to `cancelled`. Kip's delegated job, which the
turn had nothing to do with, died with it. No dialog was shown and no
"■ STOP ALL — aborted 2 streams" line was written. The topbar's brake,
performing the identical sweep, first asks "This will stop 2 coworkers
mid-reply and pause 0 running missions".

The reach was right for the wrong scope. Room / @-mention / brainstorm /
handoff sends run through dispatchToAgent's per-agent controllers, which
the panel's own abortRef never saw, so ■ Stop was once a no-op for
exactly the multi-agent phases most likely to run long. The fix for THAT
pointed the little button at `abortAllAgentRuns` — the office-wide
sweep — and `agentAbortersRef` is keyed by agent across every dispatch
path, a card dropped on a desk as much as a specialist the turn pulled
in.

So the sweep is scoped to what the turn started:

  - `bossTurnRef` holds the open ask; `recordBossAsk` opens the turn and
    `settleBossAsk` closes it, on every ending.
  - `beginAgentRun` files a run under the turn only if the turn is open
    when it STARTS. A job already running when the boss began typing is
    somebody else's.
  - `abortTurnAgentRuns` aborts that set and nothing else, and bumps a
    TURN epoch. `abortAllAgentRuns` bumps both epochs, because stopping
    the office stops the turn with it.
  - the outbox wait cancels a held note on an office sweep always, and on
    a turn sweep only when the held dispatch belongs to the turn.

Run: python3 scripts/test_stop_takes_back_only_your_turn.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []

STOP_FN = '''  const stop = () => {
    if (abortRef.current) abortRef.current.abort();
    if (onStopTurn) onStopTurn();
  };'''
BEGIN = 'const beginAgentRun = (agentId) => {'
END = 'const endAgentRun = (agentId, controller) => {'
TURN_SWEEP = 'const abortTurnAgentRuns = () => {'
ALL_SWEEP = 'const abortAllAgentRuns = () => {'
WIRE = 'onStopTurn={abortTurnAgentRuns} turnEpochRef={turnEpochRef}'
BRAKE = 'onClick={onStopAll}'


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'\{/\*.*?\*/\}', '', src, flags=re.S)
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_from(src, i):
    if i < 0 or i >= len(src):
        return ''
    close = {'{': '}', '(': ')'}.get(src[i])
    if not close:
        return ''
    depth = 0
    for j in range(i, len(src)):
        if src[j] == src[i]:
            depth += 1
        elif src[j] == close:
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    return ''


def lift(src, decl):
    """`const foo = (…) => { … }` by its declaration line. The head ends ON
    the opening brace, so the block is taken from that same character and
    the head re-joined without it — otherwise one brace stays open and node
    reports it at the end of the whole script."""
    i = src.find(decl)
    if i < 0:
        return ''
    body = brace_from(src, i + len(decl) - 1)
    return (decl[:-1] + body) if body else ''


def main():
    print('stop takes back only your turn')
    if not shutil.which('node'):
        print('SKIP — node not on PATH')
        return 0

    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    chat = (ROOT / 'ui' / 'chat.jsx').read_text(encoding='utf-8')
    bare = strip_comments(app)
    cbare = strip_comments(chat)

    # ── the button no longer holds the brake ────────────────────────────
    check('the composer Stop calls the turn sweep, not the office one',
          STOP_FN in cbare and 'onStopAll' not in cbare,
          'onStopAll still reachable from the chat panel'
          if 'onStopAll' in cbare else cbare[cbare.find('const stop = ('):][:120])
    check('the panel is handed the turn sweep and the turn epoch',
          bare.count(WIRE) == 1, f'{bare.count(WIRE)} wire sites')
    check('the office sweep is still what the big red button calls',
          bare.count(BRAKE) == 1 and 'abortAllAgentRuns();' in bare,
          'the emergency brake must keep its office-wide reach')
    check('…and the brake still asks first, with a count',
          'window.hqConfirm(`STOP ALL?' in bare
          and 'coworker${inflight===1' in bare)
    # The tooltip is the sentence the boss reads before pressing. It said
    # "Stop streaming" over a button that stopped the office.
    title = re.search(r'onClick=\{stop\} title="([^"]*)"', chat)
    check('the tooltip says what it will and will not reach',
          bool(title) and 'turn' in title.group(1).lower()
          and 'STOP ALL' in title.group(1),
          title.group(1) if title else 'no titled stop button')

    # ── the turn has a beginning and an end ─────────────────────────────
    rec = lift(bare, 'const recordBossAsk = (text) => {')
    settle = lift(bare, 'const settleBossAsk = (id, err) => {')
    check('recordBossAsk opens the turn', 'bossTurnRef.current = id;' in rec)
    check('settleBossAsk closes it before any of its endings',
          'bossTurnRef.current = null;' in settle
          and settle.find('bossTurnRef.current = null;') < settle.find("'completed'"),
          'a turn left open outlives its ask and captures the next job')
    check('…and only its own turn', 'bossTurnRef.current === id' in settle)
    # Both ends of the turn are lifted and driven below, rather than pinned
    # by eye. The two statements that clear the books read as belt-and-
    # braces — the open clears what the close should already have cleared —
    # and a mutation dropping either one passes every source check while
    # leaving a previous turn's runs reachable by the next ■ Stop.
    m_open = re.search(r'^\s*bossTurnRef\.current = id;\n'
                       r'(?:^\s*turnRunsRef\.current\.clear\(\);\n)?', rec, re.M)
    m_close = re.search(r'^\s*if \(bossTurnRef\.current[^\n]*\n(?:^(?!\s*\}).*\n)*^\s*\}\n',
                        settle, re.M)
    check('the turn-open statements lift', bool(m_open), rec[:80])
    check('the turn-close block lifts',
          bool(m_close) and 'bossTurnRef.current = null;' in m_close.group(0),
          m_close.group(0) if m_close else settle[:120])
    open_src = m_open.group(0) if m_open else ''
    close_src = m_close.group(0) if m_close else ''

    # ── drive the real sweeps ───────────────────────────────────────────
    begin_src = lift(bare, BEGIN)
    end_src = lift(bare, END)
    turn_src = lift(bare, TURN_SWEEP)
    all_src = lift(bare, ALL_SWEEP)
    for nm, s in (('beginAgentRun', begin_src), ('endAgentRun', end_src),
                  ('abortTurnAgentRuns', turn_src), ('abortAllAgentRuns', all_src)):
        check(f'{nm} lifts', s.endswith('}'), s[-40:] or 'not found')

    js = ('const SRC = ' + json.dumps(
              begin_src + ';\n' + end_src + ';\n' + turn_src + ';\n' + all_src + ';') + ';\n'
          + 'const OPEN = ' + json.dumps(open_src) + ';\n'
          + 'const CLOSE = ' + json.dumps(close_src) + ';\n'
          + r'''
/* A fake office: the refs the sweeps read, and nothing else. The runs are
   started through the REAL beginAgentRun and the controllers it hands back
   are the real thing — a planted stand-in would be aborted on the spot,
   because starting a run at a busy desk cancels what is there (#99). Who
   was stopped is therefore read off `signal.aborted`, not a spy list. */
const mk = () => {
  const env = {
    agentAbortersRef: { current: new Map() },
    turnRunsRef: { current: new Set() },
    bossTurnRef: { current: null },
    turnEpochRef: { current: 0 },
    stopEpochRef: { current: 0 },
    /* #394 added the desk ledger, which endAgentRun now drops entries from
       by controller identity. Nothing in this test signs it, so it stays
       empty — it just has to exist in the namespace the lift runs in. */
    deskWorkRef: { current: new Map() },
  };
  const fns = new Function(
    'agentAbortersRef', 'turnRunsRef', 'bossTurnRef', 'turnEpochRef', 'stopEpochRef',
    'deskWorkRef',
    SRC + ' return { beginAgentRun, endAgentRun, abortTurnAgentRuns, abortAllAgentRuns };'
  )(env.agentAbortersRef, env.turnRunsRef, env.bossTurnRef, env.turnEpochRef, env.stopEpochRef,
    env.deskWorkRef);
  /* The real open/close statements, lifted out of recordBossAsk and
     settleBossAsk and given the same two refs they read there. */
  const openTurn = new Function('bossTurnRef', 'turnRunsRef', 'id', OPEN)
    .bind(null, env.bossTurnRef, env.turnRunsRef);
  const closeTurn = new Function('bossTurnRef', 'turnRunsRef', 'id', CLOSE)
    .bind(null, env.bossTurnRef, env.turnRunsRef);
  return { env, fns, openTurn, closeTurn,
           books: () => [...env.turnRunsRef.current].sort() };
};
const who = (runs) => Object.entries(runs)
  .filter(([, c]) => c.signal.aborted).map(([n]) => n).sort();

/* The measured run: Kip is already working when the boss starts typing. */
const scenario = () => {
  const o = mk();
  const kip = o.fns.beginAgentRun('kip');   // delegated, before — no turn open
  o.env.bossTurnRef.current = 'msg_ask';    // boss starts a turn
  const otto = o.fns.beginAgentRun('otto'); // fan-out, inside the turn
  return { ...o, runs: { kip, otto } };
};

const turnStop = scenario();
const turnStopped = turnStop.fns.abortTurnAgentRuns();

const brake = scenario();
brake.fns.abortAllAgentRuns();

/* A run that STARTS after the turn closed must not be filed under it. */
const after = mk();
after.env.bossTurnRef.current = 'msg_ask';
const aKip = after.fns.beginAgentRun('kip');
after.env.bossTurnRef.current = null;
const aVera = after.fns.beginAgentRun('vera');
after.fns.abortTurnAgentRuns();

/* A settled run leaves the turn's books, so a later sweep cannot reach a
   controller some other path has since registered on the same desk. */
const reuse = mk();
reuse.env.bossTurnRef.current = 'msg_ask';
const rFirst = reuse.fns.beginAgentRun('kip');
reuse.fns.endAgentRun('kip', rFirst);
reuse.env.bossTurnRef.current = null;
const rSecond = reuse.fns.beginAgentRun('kip');
reuse.fns.abortTurnAgentRuns();

/* Scoping the sweep must not have cost the busy-desk cancel (#99): a second
   run at the same desk still takes the first one's controller with it. */
const busy = mk();
const bFirst = busy.fns.beginAgentRun('kip');
const bSecond = busy.fns.beginAgentRun('kip');

/* An ask that never settles must not hand its runs to the next one. The
   close is guarded on identity, so a turn the boss abandoned mid-flight
   (a second ask, a reload of the panel) leaves its ids on the books unless
   the OPEN clears them too. Driven with the real statements from both
   ends, so belt and braces are each tested with the other removed. */
const stale = mk();
stale.openTurn('ask_A');
const sKip = stale.fns.beginAgentRun('kip');   // filed under the abandoned turn
stale.closeTurn('ask_OTHER');                  // a late settle for somebody else
const staleAfterLateSettle = stale.books();
stale.openTurn('ask_B');                       // the boss asks again
const booksAtOpen = stale.books();
const sVera = stale.fns.beginAgentRun('vera');
stale.fns.abortTurnAgentRuns();

/* And the sweep leaves its own books clean, so it does not depend on a
   settle it has no way to make happen. */
const tidy = mk();
tidy.openTurn('ask_A');
tidy.fns.beginAgentRun('kip');
tidy.fns.abortTurnAgentRuns();
const booksAfterTurnSweep = tidy.books();
const office = mk();
office.openTurn('ask_A');
office.fns.beginAgentRun('kip');
office.fns.abortAllAgentRuns();
const booksAfterOfficeSweep = office.books();

console.log(JSON.stringify({
  turnStop: {
    aborted: who(turnStop.runs), returned: turnStopped,
    left: [...turnStop.env.agentAbortersRef.current.keys()],
    turnEpoch: turnStop.env.turnEpochRef.current,
    officeEpoch: turnStop.env.stopEpochRef.current,
  },
  brake: {
    aborted: who(brake.runs),
    left: [...brake.env.agentAbortersRef.current.keys()],
    turnEpoch: brake.env.turnEpochRef.current,
    officeEpoch: brake.env.stopEpochRef.current,
  },
  after: { aborted: who({ kip: aKip, vera: aVera }),
           left: [...after.env.agentAbortersRef.current.keys()] },
  reuse: { aborted: who({ first: rFirst, second: rSecond }),
           left: [...reuse.env.agentAbortersRef.current.keys()] },
  busy: { aborted: who({ first: bFirst, second: bSecond }) },
  stale: { aborted: who({ kip: sKip, vera: sVera }),
           staleAfterLateSettle, booksAtOpen,
           stillOpen: stale.env.bossTurnRef.current },
  books: { afterTurnSweep: booksAfterTurnSweep,
           afterOfficeSweep: booksAfterOfficeSweep },
}));
''')
    p = subprocess.run(['node', '--input-type=module', '-e',
                        '(async () => {' + js
                        + '})().catch(e => { console.error(e); process.exit(1); });'],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('the lifted sweeps run', False, p.stderr.strip()[:400])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    t = r['turnStop']
    check("the turn's own fan-out is stopped", t['aborted'] == ['otto'], t)
    check('a job that was already running is LEFT ALONE',
          'kip' in t['left'],
          'this is the measured bug: a delegated job died with an unrelated turn')
    check('…and the sweep reports what it actually stopped',
          t['returned'] == 1, t['returned'])
    check('the turn sweep bumps the turn epoch only',
          t['turnEpoch'] == 1 and t['officeEpoch'] == 0, t)

    b = r['brake']
    check('STOP ALL still takes everything', b['aborted'] == ['kip', 'otto']
          and b['left'] == [], b)
    check('…and bumps both epochs — stopping the office stops the turn',
          b['turnEpoch'] == 1 and b['officeEpoch'] == 1, b)

    check('a run started after the turn closed is not filed under it',
          r['after']['aborted'] == ['kip'] and 'vera' in r['after']['left'],
          r['after'])
    check("a settled run leaves the turn's books, so its desk can be re-used",
          r['reuse']['aborted'] == [] and 'kip' in r['reuse']['left'],
          r['reuse'])
    check('a second run at a busy desk still cancels the first (#99 intact)',
          r['busy']['aborted'] == ['first'], r['busy'])

    s = r['stale']
    check('a late settle for another ask leaves this turn open and its books alone',
          s['staleAfterLateSettle'] == ['kip'] and s['stillOpen'] == 'ask_B', s)
    check('a new ask does not inherit an abandoned one\'s runs',
          s['booksAtOpen'] == [] and s['aborted'] == ['vera'],
          "the close is guarded on id, so the open has to clear too")
    check('the turn sweep leaves its own books empty',
          r['books']['afterTurnSweep'] == [],
          'a sweep that leans on settleBossAsk to tidy up is a sweep that '
          'breaks the first time an ask does not settle')
    check('…and so does the office sweep', r['books']['afterOfficeSweep'] == [],
          r['books'])

    # ── the held note in the outbox ─────────────────────────────────────
    disp = bare[bare.find('const dispatchToAgent = async'):]
    disp = disp[:disp.find('const abortAgentRun')] if 'const abortAgentRun' in disp else disp
    check('a dispatch records whether it belongs to the turn, at entry',
          'const inBossTurn = !!bossTurnRef.current;' in disp,
          'read at the wait instead, and a turn that closed mid-wait changes the answer')
    check('a held note is cancelled by an office sweep whatever it belongs to',
          'const sweptOffice = stopEpochRef.current !== stopEpochAtWait;' in disp)
    check('…and by a turn sweep only when the note is the turn\'s own',
          'const sweptTurn = inBossTurn && turnEpochRef.current !== turnEpochAtWait;' in disp)
    check('the note says WHICH stop dropped it, not always STOP ALL',
          "sweptOffice ? 'STOP ALL' : 'You stopped the turn'" in disp,
          'a turn-stop filed under STOP ALL is the office over-reporting itself')

    # ── the meeting loop adjourns on either ─────────────────────────────
    check('the meeting loop watches the turn epoch',
          'turnEpochRef.current !== turnEpochAtStart' in cbare
          and 'stopEpochRef' not in cbare,
          'a meeting IS the boss\'s turn; the office sweep bumps that epoch too')

    if FAILS:
        print(f'FAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS))
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
