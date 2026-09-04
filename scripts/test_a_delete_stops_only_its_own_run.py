#!/usr/bin/env python3
"""Deleting a parked card stopped somebody else's live run.

Measured 2026-08-15 on office 9261, canned brain. "Empty hands three" had
been parked on Vera's desk for five hours (doing + blockedReason — the
run-end path's stamp for a run that came back empty). Vera was mid-reply
to "@Vera hold that thought eleven". Clicking ✕ on the PARKED card drew:

    Vera is working on "Empty hands three" right now.
    Delete it and stop them?

— false; that run ended when the card parked. Confirming then ran
abortAgentRun(assignee), which cancelled the conversation — an unrelated
live run — and filed it as "aborted by user". Two lies for one click: a
dialog claiming live work on a dead card, and a registry note blaming the
boss for a stop they never chose.

onDeleteTask detected "running" with the status-only witness #86 outlawed
at the START door — t.status === 'doing' && !!t.assignedTo — surviving
here in a different spelling, which is exactly how #86's own absence pin
missed it. The premise in the abort comment ("their in-flight stream IS
this task's") only holds for an unparked doing card with the registry bit
set: a conversation aborts any such card's run on its way in, so
registry + doing + no-blockedReason pins the stream to this card.

The fix uses that full witness. Parked cards carry `result` (written with
the park), so deleting one falls through to the "work will be lost"
confirm — it still asks, it just stops claiming live work and stops
reaching for the abort.

Run: python3 scripts/test_a_delete_stops_only_its_own_run.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, header):
    i = src.index(header)
    j = src.index('{', i + len(header) - 1)
    d = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces after ' + header)


def main():
    print('a delete stops only its own run')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    app = APP.read_text(encoding='utf-8')
    bare = strip_comments(app)

    # ── the witness, pinned at the source ───────────────────────────────
    check('the delete door reads the full in-flight witness',
          re.search(r"const running = t\.status === 'doing' && !t\.blockedReason"
                    r' && !!t\.assignedTo\s*&& agentAbortersRef\.current\.has\('
                    r't\.assignedTo\);', bare) is not None,
          'app.jsx onDeleteTask: doing + no park stamp + registry — the same '
          'three facts displacedTask reads at the START door (#86)')
    check('the status-only spelling is gone',
          "t.status === 'doing' && !!t.assignedTo;" not in bare,
          'the #86 witness, surviving at another door in another spelling, '
          'is this whole ticket')
    check('the abort still sits behind that same answer',
          re.search(r'if \(running\) abortAgentRun\(t\.assignedTo\);', bare)
          is not None,
          'scoping the witness must not detach the abort from it')

    # ── behavior through the real lifted function ───────────────────────
    fn = brace_lift(app, 'const onDeleteTask = async (id) =>')
    js = (
        'async function drive(s) {\n'
        '  const log = { dialogs: [], aborted: [], deleted: [], said: [] };\n'
        '  const tasks = s.tasks;\n'
        '  const agents = [{ id: "a1", name: "Vera" }];\n'
        '  const agentAbortersRef = { current: new Map(s.running ? [["a1", 1]] : []) };\n'
        '  const window = { hqConfirm: async (msg) => { log.dialogs.push(msg); return s.ok !== false; } };\n'
        '  const abortAgentRun = (aid) => { log.aborted.push(aid); return true; };\n'
        '  const setTasks = (fn) => { const kept = fn(tasks); log.deleted = tasks.filter(t => !kept.includes(t)).map(t => t.id); };\n'
        '  const say = (msg) => log.said.push(msg);\n'
        # onDeleteTask also purges the tray of approval cards bound to the
        # deleted task (see test_deleting_a_task_takes_its_approval_cards_with_it).
        '  const setApprovals = (fn) => { log.approvals = fn(s.approvals || []); };\n'
        '  ' + fn + ';\n'
        '  await onDeleteTask(s.id);\n'
        '  return log;\n'
        '}\n'
    )
    PARKED = ('{ id: "tk_p", title: "Empty hands three", status: "doing", '
              'assignedTo: "a1", blockedReason: "empty run", result: "lead-in" }')
    LIVE = ('{ id: "tk_l", title: "briefing", status: "doing", '
            'assignedTo: "a1" }')
    DONE = ('{ id: "tk_d", title: "old", status: "done", '
            'assignedTo: "a1", result: "the report" }')
    js += (
        'const S = {\n'
        f'  parked_chat:    {{ tasks: [{PARKED}], id: "tk_p", running: true }},\n'
        f'  parked_idle:    {{ tasks: [{PARKED}], id: "tk_p", running: false }},\n'
        f'  live_own:       {{ tasks: [{LIVE}], id: "tk_l", running: true }},\n'
        f'  live_declined:  {{ tasks: [{LIVE}], id: "tk_l", running: true, ok: false }},\n'
        f'  stray_doing:    {{ tasks: [{LIVE}], id: "tk_l", running: false }},\n'
        f'  archived:       {{ tasks: [{DONE}], id: "tk_d", running: false }},\n'
        '};\n'
        'const R = {};\n'
        'Promise.all(Object.keys(S).map(async k => { R[k] = await drive(S[k]); }))\n'
        '  .then(() => console.log(JSON.stringify(R)));\n'
    )
    p = subprocess.run(['node', '--input-type=module', '-e', js], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('lifted onDeleteTask runs', False, p.stderr.strip()[:300])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('a parked card never draws "right now", even mid-conversation',
          not any('right now' in d for d in r['parked_chat']['dialogs']),
          r['parked_chat']['dialogs'])
    check('...and deleting it never reaches for the abort',
          r['parked_chat']['aborted'] == [] and r['parked_chat']['deleted'] == ['tk_p'],
          r['parked_chat'])
    check('...but the boss is still asked, because the card carries output',
          any('will be lost' in d for d in r['parked_chat']['dialogs']),
          [r['parked_chat']['dialogs'], '— the park writes `result`; losing '
           'the live-work claim must not make the delete silent'])
    check('a parked card on an idle desk reads the same',
          r['parked_idle']['aborted'] == []
          and not any('right now' in d for d in r['parked_idle']['dialogs']),
          r['parked_idle'])
    check('a genuinely live card still says so and still stops its own run',
          any('right now' in d for d in r['live_own']['dialogs'])
          and r['live_own']['aborted'] == ['a1']
          and r['live_own']['deleted'] == ['tk_l'],
          r['live_own'])
    check('...and declining keeps both the card and the run',
          r['live_declined']['aborted'] == [] and r['live_declined']['deleted'] == [],
          r['live_declined'])
    check('a doing card with no run behind it claims no live work',
          not any('right now' in d for d in r['stray_doing']['dialogs'])
          and r['stray_doing']['aborted'] == [],
          [r['stray_doing'], '— a stream that died unsettled leaves doing '
           'set; the registry, not the column, says whether anyone is there'])
    check('an archived result still gets its own guard',
          any('will be lost' in d for d in r['archived']['dialogs']),
          r['archived'])

    print()
    if FAILS:
        print(f'delete-scope: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('delete-scope: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
