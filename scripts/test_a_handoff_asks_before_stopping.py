#!/usr/bin/env python3
"""Delegate at a busy desk kills the answer being written, unasked.

Measured 2026-08-15 on office 9261, canned brain. The boss @mentioned
Vera and, while she was mid-reply, typed a follow-up and used the
composer's Delegate picker to hand it to her. No dialog appeared. Her
in-flight answer to the boss's previous question was cut to
" …(stopped)" and the registry filed it 'cancelled' / 'aborted by
user' — the click said "hand this off", not "stop her".

Every other surface already had its answer: task starts, task deletes
and retries ask first (#90, #92); office-initiated dispatches wait for
the desk (#98). Delegate was the last boss-facing dispatch door with
neither. The fix is #90's rule at this door: if the target's desk has
a live stream, hqConfirm asks — "Stop & hand off" or "Let them
finish" — and declining returns false so the picker restores the
boss's typed text instead of losing it. A quiet desk delegates exactly
as before, no dialog.

Run: python3 scripts/test_a_handoff_asks_before_stopping.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []

DOOR = 'if (agentAbortersRef.current.has(a.id)) {'
DECLINE = "if (!ok) return false;"


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('a handoff asks before stopping')
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    chat = (ROOT / 'ui' / 'chat.jsx').read_text(encoding='utf-8')
    bare = strip_comments(app)
    cbare = strip_comments(chat)

    # ── the door sits in onDelegate, between the brief guard and dispatch ─
    check('the busy-desk door exists once', bare.count(DOOR) == 1,
          f'{bare.count(DOOR)} sites')
    door_at = bare.find(DOOR)
    deleg_at = bare.find('const onDelegate = async (a, typed) => {')
    check('onDelegate is async (the door awaits a dialog)', deleg_at != -1)
    if door_at != -1 and deleg_at != -1:
        brief_guard = bare.find('(nothing to hand ${a.name} yet', deleg_at)
        user_msg = bare.find('const userMsg = { id: HQ.uid(', deleg_at)
        begin = bare.find('const controller = beginAgentRun(a.id);', deleg_at)
        check('the door asks after the empty-hand guard, before anything '
              'is painted or run',
              deleg_at < brief_guard < door_at < user_msg < begin,
              [deleg_at, brief_guard, door_at, user_msg, begin,
               '— an empty hand needs no warning, and a declined one must '
               'leave no trace on the floor'])
        block = bare[door_at:user_msg] if user_msg > door_at else ''
        check('the ask is a danger confirm with honest labels',
              'window.hqConfirm(' in block and 'danger: true' in block
              and "okLabel: 'Stop & hand off'" in block
              and "cancelLabel: 'Let them finish'" in block)
        check('declining refuses the hand-off', DECLINE in block,
              'false is the signal the picker needs to restore the text')
        check('the door names what will happen',
              'Their current answer will be stopped.' in block,
              'the measured cut happened with no warning at all')

    # ── the picker keeps the boss's words on decline ────────────────────
    check('the picker restores typed text when the boss declines',
          'const ok = await onDelegate(a, typed);' in cbare
          and 'if (ok === false) setInput(typed);' in cbare,
          "the old onClick discarded input before onDelegate could answer")
    check('the picker closes before the dialog, not after the stream',
          re.search(r"const typed = input; setShowDelegate\(false\); "
                    r"setInput\(''\);", cbare) is not None)

    # ── behavior: the lifted door over three desks ──────────────────────
    body = None
    if door_at != -1:
        user_msg = bare.find('const userMsg = { id: HQ.uid(', door_at)
        if user_msg > door_at:
            body = bare[door_at:user_msg]
    check('the door block lifts', body is not None)
    if body is None or not shutil.which('node'):
        if not shutil.which('node'):
            print('  SKIP  node not on PATH — behavior checks need it')
        print()
        if FAILS:
            print(f'handoff-asks: {len(FAILS)} FAILED')
            return 1
        print('handoff-asks: source checks passed')
        return 0

    js = (
        'const a = { id: "a_v", name: "Vera" };\n'
        'let calls;\n'
        'const agentAbortersRef = { current: new Map() };\n'
        'let confirmAnswer = true;\n'
        'const window = { hqConfirm: (msg, opts) => { calls.confirms.push({ msg, danger: !!(opts && opts.danger) }); return Promise.resolve(confirmAnswer); } };\n'
        'const door = async () => {' + body + ' return "PROCEEDED"; };\n'
        + '''
const run = async (busy, answer) => {
  calls = { confirms: [] };
  confirmAnswer = answer;
  agentAbortersRef.current = new Map(busy ? [['a_v', {}]] : []);
  const out = await door();
  return { out, confirms: calls.confirms };
};
const R = {
  quiet: await run(false, true),
  busyYes: await run(true, true),
  busyNo: await run(true, false),
};
console.log(JSON.stringify(R));
''')
    p = subprocess.run(['node', '--input-type=module', '-e',
                        '(async () => {' + js
                        + '})().catch(e => { console.error(e); process.exit(1); });'],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('lifted door runs', False, p.stderr.strip()[:300])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('a quiet desk delegates with no dialog',
          r['quiet']['out'] == 'PROCEEDED' and r['quiet']['confirms'] == [],
          r['quiet'])
    check('a busy desk asks, and yes proceeds',
          r['busyYes']['out'] == 'PROCEEDED'
          and len(r['busyYes']['confirms']) == 1
          and r['busyYes']['confirms'][0]['danger']
          and 'mid-reply' in r['busyYes']['confirms'][0]['msg'],
          r['busyYes'])
    check('a busy desk asks, and no refuses the hand-off',
          r['busyNo']['out'] is False and len(r['busyNo']['confirms']) == 1,
          [r['busyNo'], '— the measured defect: no dialog, the answer cut, '
           "'aborted by user' for a stop the boss never chose"])

    print()
    if FAILS:
        print(f'handoff-asks: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('handoff-asks: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
