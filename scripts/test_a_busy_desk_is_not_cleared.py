#!/usr/bin/env python3
"""The desk timer cut a conversation the boss was still having.

Measured 2026-08-15 on office 9261, canned brain. The boss @mentioned a
transient helper (Sub-fact-4wf) inside its 30-second grace window and
asked a follow-up. The dismissal timer fired mid-reply and cut the
conversation with three lies in one motion:

  - the helper's answer ended " …(stopped)" — a conversation binned
    with no warning, the very thing #90 outlawed at the task-start door;
  - the registry filed the boss's own question as state 'cancelled',
    note 'aborted by user' — a stop the boss never made (the timer's
    belt-and-braces abortAgentRun made it);
  - the next chat line was "🍂 Sub-fact-4wf (transient) dismissed —
    task complete." — completion announced over the boss's open
    question, and the helper gone from the floor mid-conversation.

When the boss is driving, the office does not bin the conversation to
keep a tidy floor. The fix makes the timer a named dismissWhenQuiet():
after #95's floor guard, it checks agentAbortersRef for a live stream
on the helper's desk — if one is running it re-arms itself for another
30 seconds and touches nothing. Only a QUIET desk is cleared. The
abortAgentRun call is gone: at dismissal time the quiet check has just
established there is nothing to abort. Deferral terminates because
endAgentRun deletes the aborter whenever a run settles.

Run: python3 scripts/test_a_busy_desk_is_not_cleared.py
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
QUIET = "if (agentAbortersRef.current.has(transientAgent.id)) {"
REARM = "setTimeout(dismissWhenQuiet, 30_000);"


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('a busy desk is not cleared')
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    bare = strip_comments(app)
    tpl = '(transient) dismissed — ${'

    # ── source shape: guard, then quiet check, then (and only then) words ─
    check('the timer is the named dismissWhenQuiet',
          bare.count('const dismissWhenQuiet = () => {') == 1)
    n = bare.count(REARM)
    check('the re-arm line appears twice (defer + initial arm)', n == 2,
          f'{n} sites — one arms the timer, one defers a busy desk')
    if bare.count(tpl) == 1:
        tpl_at = bare.index(tpl)
        open_at = bare.rfind('const dismissWhenQuiet = () => {', 0, tpl_at)
        guard_at = bare.find(GUARD, open_at)
        quiet_at = bare.find(QUIET, open_at)
        check('floor guard first, quiet check second, goodbye last',
              open_at != -1 and -1 < guard_at < quiet_at < tpl_at,
              'the empty desk exits before the busy desk defers; only a '
              'quiet desk reaches the goodbye')
        check('the timer aborts nothing',
              'abortAgentRun(' not in bare[open_at:tpl_at],
              'the quiet check just established there is no stream to '
              'abort — an abort here is the measured cut')
    else:
        check('single goodbye writer (prerequisite)', False,
              f'{bare.count(tpl)} sites')

    # ── deferral terminates: settle deletes the aborter ─────────────────
    check('endAgentRun deletes the aborter on settle',
          re.search(r'const endAgentRun = \(agentId, controller\) => \{\s*'
                    r'if \(agentAbortersRef\.current\.get\(agentId\) === '
                    r'controller\) \{\s*'
                    r'agentAbortersRef\.current\.delete\(agentId\);', bare)
          is not None,
          'without this the deferral never ends and the goodbye never comes')

    # ── the honest note is untouched for genuinely boss-made stops ──────
    check("the 'aborted by user' note still exists for real aborts",
          "note: aborted ? 'aborted by user'" in bare,
          'the fix removes the misattribution by not aborting, not by '
          'renaming the note')

    # ── behavior: the lifted timer over busy, quiet, and empty desks ────
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
            print(f'busy-desk: {len(FAILS)} FAILED')
            return 1
        print('busy-desk: source checks passed')
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
        'const setTimeout = (fn, ms) => { calls.rearms.push({ same: fn === dismissWhenQuiet, ms }); };\n'
        'const setAgents = (fn) => { calls.agentsWrites++; floor = fn(floor); agentsRef.current = floor; };\n'
        'const setChat = (fn) => { calls.chat = fn(calls.chat); };\n'
        'const dismissWhenQuiet = () => {' + body + '};\n'
        + '''
const run = (startFloor, busy) => {
  calls = { rearms: [], agentsWrites: 0, chat: [] };
  floor = startFloor;
  agentsRef.current = floor;
  agentAbortersRef.current = new Map(busy ? [['sub_1', { abort: () => {} }]] : []);
  dismissWhenQuiet();
  return { rearms: calls.rearms, agentsWrites: calls.agentsWrites,
           chat: calls.chat.map(m => m.text), floorIds: floor.map(a => a.id) };
};
const R = {
  busy: run([{ id: 'sub_1' }, { id: 'a_kip' }], true),
  quiet: run([{ id: 'sub_1' }, { id: 'a_kip' }], false),
  gone: run([{ id: 'a_kip' }], true),
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

    check('a busy desk is deferred, not cleared',
          r['busy']['chat'] == [] and r['busy']['agentsWrites'] == 0
          and r['busy']['floorIds'] == ['sub_1', 'a_kip'],
          [r['busy'], '— the measured cut: " …(stopped)", "aborted by '
           'user", "task complete." over the boss\'s open question'])
    check('the deferral re-arms this same timer for another 30s',
          r['busy']['rearms'] == [{'same': True, 'ms': 30000}],
          r['busy']['rearms'])
    check('a quiet desk is cleared with the one goodbye',
          len(r['quiet']['chat']) == 1
          and 'dismissed — task complete.' in r['quiet']['chat'][0]
          and r['quiet']['floorIds'] == ['a_kip']
          and r['quiet']['rearms'] == [],
          r['quiet'])
    check('an empty desk still exits before the busy check',
          r['gone']['chat'] == [] and r['gone']['rearms'] == []
          and r['gone']['agentsWrites'] == 0,
          [r['gone'], '— #95\'s guard outranks the deferral: nobody home '
           'beats desk busy'])

    print()
    if FAILS:
        print(f'busy-desk: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('busy-desk: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
