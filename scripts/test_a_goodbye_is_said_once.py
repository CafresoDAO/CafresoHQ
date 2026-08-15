#!/usr/bin/env python3
"""A helper already let go got a second goodbye.

Measured 2026-08-15 on office 9261, canned brain. A transient helper
(Sub-fact-7q6) finished its task; the boss clicked LET GO on its card
inside the 30-second grace window. The door did its job: the helper left
the floor and the chat said "Sub-fact-7q6 has been let go." Nine seconds
later the dismissal timer fired anyway and posted

    🍂 Sub-fact-7q6 (transient) dismissed — task complete.

— the same departure announced twice, in two voices, with two framings
(#64 family: the office telling the boss the same thing twice). The
second line also reads as the OFFICE dismissing the helper, when the
boss had already done it at the door.

The fix guards the timer on the floor itself: at fire time it looks up
agentsRef for the helper; if the desk is already empty there is nothing
left to do and nothing true left to say — no abort, no removal, no
goodbye. The door's own farewell was the record, and it stands alone.
When the helper IS still on the floor, the timer behaves exactly as
before (#94's outcome-reading goodbye included).

Run: python3 scripts/test_a_goodbye_is_said_once.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []

GUARD = "if (!(agentsRef.current || []).some(a => a.id === transientAgent.id)) return;"


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('a goodbye is said once')
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    bare = strip_comments(app)

    # ── the timer looks at the floor before it speaks ───────────────────
    tpl = '(transient) dismissed — ${'
    check('the transient goodbye still has one writer',
          bare.count(tpl) == 1, f'{bare.count(tpl)} sites')
    n_guard = bare.count(GUARD)
    check('the floor guard exists once', n_guard == 1, f'{n_guard} sites')

    if bare.count(tpl) == 1 and n_guard == 1:
        tpl_at = bare.index(tpl)
        guard_at = bare.index(GUARD)
        # The timer body is a named function now (#97's deferral needs to
        # re-arm itself); the guard must still be its first act.
        timer_at = bare.rfind('const dismissWhenQuiet = () => {', 0, tpl_at)
        check('the guard sits inside the timer, before anything else',
              timer_at != -1 and timer_at < guard_at < tpl_at
              and guard_at < bare.index('agentAbortersRef.current.has(',
                                        timer_at),
          'an empty desk means the whole firing is moot — deferral and '
          'removal included, not just the words')

    # ── the door still says its own goodbye ─────────────────────────────
    check('the front door farewell is still filed',
          'text: `${a.name} has been let go.`' in bare,
          'the guard works BECAUSE the door already spoke — if the door '
          'goes silent, a boss-dismissed helper leaves without a word')

    # ── behavior: the lifted timer, fired over both floors ──────────────
    # The timer body is the named dismissWhenQuiet function; its span runs
    # from the declaration to the arming line right after it.
    body = None
    if bare.count(tpl) == 1:
        tpl_at = bare.index(tpl)
        open_marker = 'const dismissWhenQuiet = () => {'
        open_at = bare.rfind(open_marker, 0, tpl_at)
        arm_at = bare.find('setTimeout(dismissWhenQuiet, 30_000);', tpl_at)
        close_at = bare.rfind('};', 0, arm_at) if arm_at != -1 else -1
        if open_at != -1 and close_at != -1 and open_at < close_at:
            body = bare[open_at + len(open_marker):close_at]
    check('the timer body lifts', body is not None)
    if body is None or not shutil.which('node'):
        if not shutil.which('node'):
            print('  SKIP  node not on PATH — behavior checks need it')
        print()
        if FAILS:
            print(f'goodbye-once: {len(FAILS)} FAILED')
            return 1
        print('goodbye-once: source checks passed')
        return 0

    js = (
        'const transientAgent = { id: "sub_1", name: "Sub-test-abc" };\n'
        'const spawnMsgId = "msg_spawn1";\n'
        'const HQ = { uid: () => "m_x" };\n'
        'const MessageRegistry = { getMessage: () => ({ state: "completed" }) };\n'
        'let calls;\n'
        'let floor;\n'
        'const agentsRef = { current: [] };\n'
        'const agentAbortersRef = { current: new Map() };\n'
        'const setTimeout = (fn, ms) => { calls.rearms++; };\n'
        'const setAgents = (fn) => { calls.agentsWrites++; floor = fn(floor); agentsRef.current = floor; };\n'
        'const setChat = (fn) => { calls.chat = fn(calls.chat); };\n'
        'const dismissWhenQuiet = () => {' + body + '};\n'
        'const fire = dismissWhenQuiet;\n'
        + '''
const run = (startFloor) => {
  calls = { rearms: 0, agentsWrites: 0, chat: [] };
  floor = startFloor;
  agentsRef.current = floor;
  fire();
  return { rearms: calls.rearms, agentsWrites: calls.agentsWrites,
           chat: calls.chat.map(m => m.text), floorIds: floor.map(a => a.id) };
};
const R = {
  present: run([{ id: 'sub_1' }, { id: 'a_kip' }]),
  gone: run([{ id: 'a_kip' }]),
};
console.log(JSON.stringify(R));
''')
    p = subprocess.run(['node', '--input-type=module', '-e', js], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('lifted timer runs', False, p.stderr.strip()[:300])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('a helper still at their desk gets the one goodbye',
          len(r['present']['chat']) == 1
          and 'dismissed — task complete.' in r['present']['chat'][0]
          and r['present']['floorIds'] == ['a_kip']
          and r['present']['rearms'] == 0,
          r['present'])
    check('a helper already let go gets no second goodbye',
          r['gone']['chat'] == [],
          [r['gone']['chat'], '— the measured double: "has been let go" '
           'at the door, then "dismissed — task complete." from the timer'])
    check('an empty desk means the timer touches nothing',
          r['gone']['rearms'] == 0 and r['gone']['agentsWrites'] == 0
          and r['gone']['floorIds'] == ['a_kip'],
          r['gone'])

    print()
    if FAILS:
        print(f'goodbye-once: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('goodbye-once: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
