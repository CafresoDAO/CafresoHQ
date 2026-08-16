#!/usr/bin/env python3
"""A coworker's DM cut a teammate's answer to the boss mid-sentence.

Measured 2026-08-15 on office 9261, canned brain. The boss asked Kip AND
Vera one question in the same breath. Kip finished first and DM'd Vera
a follow-up — and delivering that DM aborted Vera's in-flight reply to
the boss:

  - Vera's answer to the boss became " …(stopped)";
  - the registry filed the boss's question to Vera as state 'cancelled',
    note 'aborted by user' — a stop the boss never made (timestamped at
    the exact moment Kip's DM chain fired: +12.16s, the instant Kip's
    delayed reply settled);
  - Kip's note took the boss's place on Vera's desk — she answered the
    DM and never the boss.

dispatchToAgent had no busy-desk check: beginAgentRun evicts any prior
run on the same desk, and every office-initiated dispatch (DM chains,
approval walk-backs, workflow steps, retries) rode that eviction
straight through whatever conversation was open. The boss's own sends
never arrive at a busy desk — the composer serializes them — so the
eviction ONLY ever fired against conversations nobody chose to end.

The fix is #97's stance at the dispatch door: an office-initiated
dispatch WAITS for the desk to go quiet (one team-room line says so),
checking every 750ms. If the coworker is dismissed while the note
waits, the message is filed 'failed' with an honest recipient-gone
cause instead of resurrecting a dismissed coworker's bubble.

Run: python3 scripts/test_a_dm_waits_for_the_desk.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []

DEFER_OPEN = 'if (agentAbortersRef.current.has(agent.id)) {'
DEFER_WAIT = 'while (agentAbortersRef.current.has(agent.id)) {'
BUBBLE = "const agentMsgId = HQ.uid('m');"


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('a dm waits for the desk')
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    bare = strip_comments(app)

    # ── source shape: the wait sits between the DM echo and the bubble ──
    check('the deferral gate exists once', bare.count(DEFER_OPEN) == 1,
          f'{bare.count(DEFER_OPEN)} sites')
    check('the wait loop exists once', bare.count(DEFER_WAIT) == 1,
          f'{bare.count(DEFER_WAIT)} sites')
    gate_at = bare.find(DEFER_OPEN)
    if gate_at != -1:
        bubble_at = bare.find(BUBBLE)
        busy_paint = bare.find("onUpdateAgent(agent.id, { status: 'busy'")
        in_prog = bare.find("MessageRegistry.transition(messageId, 'in_progress'")
        begin_at = bare.find('const controller = beginAgentRun(agent.id);')
        check('the wait comes before the bubble, the busy paint, the '
              'in_progress stamp and the run itself',
              -1 < gate_at < bubble_at and gate_at < busy_paint
              and gate_at < in_prog and gate_at < begin_at,
              [gate_at, bubble_at, busy_paint, in_prog, begin_at,
               '— a deferred dispatch must not paint the coworker as '
               'already answering it'])
        block = bare[gate_at:bubble_at] if bubble_at > gate_at else ''
        check('the deferral aborts nothing',
              'abort' not in block.replace('agentAbortersRef', ''),
              'waiting means waiting — the measured cut was an abort here')
        check('a dismissed recipient is filed failed, not dispatched',
              "'recipient-gone'" in block
              and "MessageRegistry.transition(messageId, 'failed'" in block
              and "return ''" in block)
        check('the wait says so in the team room',
              'waits its turn' in block)
    check('endAgentRun still releases the desk on settle (termination)',
          re.search(r'const endAgentRun = \(agentId, controller\) => \{\s*'
                    r'if \(agentAbortersRef\.current\.get\(agentId\) === '
                    r'controller\) \{\s*'
                    r'agentAbortersRef\.current\.delete\(agentId\);', bare)
          is not None)

    # ── behavior: the lifted deferral over three desks ──────────────────
    body = None
    if gate_at != -1:
        bubble_at = bare.find(BUBBLE)
        if bubble_at > gate_at:
            body = bare[gate_at:bubble_at]
    check('the deferral block lifts', body is not None)
    if body is None or not shutil.which('node'):
        if not shutil.which('node'):
            print('  SKIP  node not on PATH — behavior checks need it')
        print()
        if FAILS:
            print(f'dm-waits: {len(FAILS)} FAILED')
            return 1
        print('dm-waits: source checks passed')
        return 0

    js = (
        'const agent = { id: "a_v", name: "Vera" };\n'
        'const messageId = "msg_1";\n'
        'const HQ = { uid: () => "m_x" };\n'
        'let calls;\n'
        'const agentAbortersRef = { current: new Map() };\n'
        # The #101 stop epoch is a free variable of the lifted block now.
        # Never bumped here: these drives are about WAITING, and the
        # swept-mid-wait ending has its own suite
        # (test_a_stop_stops_the_outbox_too).
        'const stopEpochRef = { current: 0 };\n'
        'const agentsRef = { current: [] };\n'
        'let dmFrom = null;\n'
        'let onTick = null;\n'
        'const setTimeout = (fn, ms) => { calls.ticks++; if (onTick) onTick(calls.ticks); fn(); };\n'
        'const setChat = (fn) => { calls.chat = fn(calls.chat); };\n'
        'const MessageRegistry = { transition: (id, state, meta) => { calls.transitions.push({ id, state, note: meta && meta.note, kind: meta && meta.failureCause && meta.failureCause.kind }); } };\n'
        'const defer = async () => {' + body + ' return "PROCEEDED"; };\n'
        + '''
const run = async (busy, quietAfter, dismissAfter, from) => {
  calls = { ticks: 0, chat: [], transitions: [] };
  dmFrom = from;
  agentAbortersRef.current = new Map(busy ? [['a_v', {}]] : []);
  agentsRef.current = [{ id: 'a_v' }, { id: 'a_k' }];
  onTick = (n) => {
    if (quietAfter !== null && n >= quietAfter) {
      agentAbortersRef.current.delete('a_v');
      if (dismissAfter) agentsRef.current = [{ id: 'a_k' }];
    }
  };
  const out = await defer();
  return { out, ticks: calls.ticks, chat: calls.chat.map(m => m.text),
           transitions: calls.transitions };
};
const R = {
  quiet: await run(false, null, false, null),
  busyThenQuiet: await run(true, 3, false, { name: 'Kip' }),
  busyThenGone: await run(true, 2, true, { name: 'Kip' }),
};
console.log(JSON.stringify(R));
''')
    p = subprocess.run(['node', '--input-type=module', '-e',
                        '(async () => {' + js.replace('const R = {', 'const R = {')
                        + '})().catch(e => { console.error(e); process.exit(1); });'],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('lifted deferral runs', False, p.stderr.strip()[:300])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('a quiet desk is not delayed and not narrated',
          r['quiet']['out'] == 'PROCEEDED' and r['quiet']['ticks'] == 0
          and r['quiet']['chat'] == [] and r['quiet']['transitions'] == [],
          r['quiet'])
    check('a busy desk waits its turn, then proceeds',
          r['busyThenQuiet']['out'] == 'PROCEEDED'
          and r['busyThenQuiet']['ticks'] >= 3
          and len(r['busyThenQuiet']['chat']) == 1
          and 'waits its turn' in r['busyThenQuiet']['chat'][0]
          and "Kip's note" in r['busyThenQuiet']['chat'][0]
          and r['busyThenQuiet']['transitions'] == [],
          [r['busyThenQuiet'], '— the measured cut: " …(stopped)" and '
           "'aborted by user' for a stop the boss never made"])
    check('a recipient dismissed mid-wait is filed failed, not dispatched',
          r['busyThenGone']['out'] == ''
          and any(t['state'] == 'failed' and t['kind'] == 'recipient-gone'
                  for t in r['busyThenGone']['transitions'])
          and any('left the office' in c for c in r['busyThenGone']['chat']),
          r['busyThenGone'])

    print()
    if FAILS:
        print(f'dm-waits: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('dm-waits: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
