#!/usr/bin/env python3
"""A task start silently kills a conversation in flight.

Measured 2026-08-15 on office 9261, canned brain: chatted "@Vera hold
that thought nine", then clicked ▶ START on "Empty hands" while her
reply streamed. No dialog appeared. The chat bubble ended " …(stopped)",
the task started as if the desk were free, and the message registry
filed the run as cancelled with the note "aborted by user" — a stop the
boss never made.

The #86 guard asks leave before binning a displaced CARD, but a cardless
run — an @mention conversation or a delegate hand-off — registers an
aborter without ever putting a folder on the desk. displacedTask only
speaks for cards, so both confirm branches were skipped and beginAgentRun
cut the conversation off with nothing anywhere saying the task start did
it.

The fix reads the same registry the abort rides: a run in flight with no
displaced card is a conversation (the @mention and delegate paths are
beginAgentRun's only cardless call sites). Boss-driven starts get the
same danger dialog a displaced card gets; chain steps park in the inbox
with a note, because automation must not bin a running conversation to
make room.

Run: python3 scripts/test_a_conversation_is_work_in_flight.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
RUNTIME = ROOT / 'hq-runtime.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


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


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('a conversation is work in flight')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    app = APP.read_text(encoding='utf-8')
    runtime = RUNTIME.read_text(encoding='utf-8')

    # ── the guard, pinned at the source ─────────────────────────────────
    bare = strip_comments(app)
    check('the cardless run is read off the same registry the abort rides',
          re.search(r'const priorRun = agentAbortersRef\.current\.get\(agent\.id\);',
                    bare) is not None,
          'app.jsx onTaskDropOnAgent: the run this guard speaks for must be '
          'the aborter registry entry, the one the abort itself rides')
    check('...minus the card the #86 guard already speaks for',
          re.search(r'const chatCut = !displaced && running;', bare) is not None,
          'app.jsx onTaskDropOnAgent: chatCut is the run in flight minus the '
          'card #86 already speaks for')
    check('...and minus the pipeline handing this very card over (#129)',
          re.search(r'const running = !!priorRun && !handingOver;', bare)
          is not None,
          'app.jsx onTaskDropOnAgent: a chain step dispatched from the tail of '
          'the step before it is not a conversation — see #129')
    check('automation parks instead of asking or binning',
          'if (chatCut && opts.auto)' in bare)
    check('the boss-driven start asks first',
          re.search(r'if \(chatCut\) \{\s*const ok = await window\.hqConfirm\(',
                    bare) is not None)
    check('the dialog names the conversation, not a guessed card',
          'is mid-conversation in chat' in app)
    check('the parked step says why it is waiting',
          'was mid-conversation when this step came up' in app)

    # ── behavior through the real lifted segment ────────────────────────
    # From the registry read, not from `displaced`: since #129 the answer both
    # guards run on is derived up here, and lifting below it would leave the
    # harness scoring a `running` this suite made up.
    seg_start = app.index('const priorRun = agentAbortersRef.current.get(agent.id);')
    seg_end = app.index('/* Starting clears the note:')
    segment = app[seg_start:seg_end]
    displaced_fn = brace_lift(runtime, 'function displacedTask(')

    js = displaced_fn + '\n'
    js += (
        'const HQ = { displacedTask };\n'
        'async function drive(s) {\n'
        '  const log = { dialogs: [], notes: [], activity: [] };\n'
        '  const agent = { id: "a1", name: "Vera", color: "c" };\n'
        '  const taskId = "tk_new";\n'
        '  const tasks = s.tasks;\n'
        '  const task = tasks.find(t => t.id === taskId);\n'
        '  const opts = s.opts || {};\n'
        '  const agentAbortersRef = { current: new Map(s.running ? [["a1", 1]] : []) };\n'
        # #390 added startingTaskIdsRef (a Set claimed synchronously at the top
        # of onTaskDropOnAgent) and its releaseStartClaim() helper, called on
        # every path that doesn't end in a real dispatch. The lifted segment
        # below starts after the claim, so the harness only needs the release
        # to exist; a no-op keeps this a test of the two desk guards.
        '  const releaseStartClaim = () => {};\n'
        '  const window = { hqConfirm: async (msg) => { log.dialogs.push(msg); return s.ok !== false; } };\n'
        '  const setTasks = (fn) => { fn(tasks).forEach(t => { if (t.stalledNote) log.notes.push([t.id, t.stalledNote]); }); };\n'
        '  const logActivity = (row) => log.activity.push(row.text || "");\n'
        '  const out = await (async () => {\n'
        + segment +
        '\n    return "started";\n'
        '  })();\n'
        '  return { out: out || "not-started", ...log };\n'
        '}\n'
    )
    NEW = '{ id: "tk_new", title: "lime", status: "inbox", assignedTo: "a1" }'
    BUSY = '{ id: "tk_busy", title: "cherry", status: "doing", assignedTo: "a1" }'
    PARKED = ('{ id: "tk_park", title: "stale", status: "doing", '
              'assignedTo: "a1", blockedReason: "empty run" }')
    js += (
        'const S = {\n'
        f'  idle:          {{ tasks: [{NEW}], running: false }},\n'
        f'  card_manual:   {{ tasks: [{NEW}, {BUSY}], running: true }},\n'
        f'  card_auto:     {{ tasks: [{NEW}, {BUSY}], running: true, opts: {{ auto: true }} }},\n'
        f'  chat_declined: {{ tasks: [{NEW}], running: true, ok: false }},\n'
        f'  chat_ok:       {{ tasks: [{NEW}], running: true }},\n'
        f'  chat_auto:     {{ tasks: [{NEW}], running: true, opts: {{ auto: true }} }},\n'
        f'  parked_chat:   {{ tasks: [{NEW}, {PARKED}], running: true }},\n'
        f'  parked_idle:   {{ tasks: [{NEW}, {PARKED}], running: false }},\n'
        '};\n'
        'const R = {};\n'
        'Promise.all(Object.keys(S).map(async k => { R[k] = await drive(S[k]); }))\n'
        '  .then(() => console.log(JSON.stringify(R)));\n'
    )
    p = subprocess.run(['node', '--input-type=module', '-e', js], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('lifted segment runs', False, p.stderr.strip()[:300])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('an idle desk starts with no questions',
          r['idle']['out'] == 'started' and not r['idle']['dialogs'],
          r['idle'])
    check('a displaced card still gets its own dialog (#86 kept)',
          r['card_manual']['out'] == 'started'
          and any('cherry' in d for d in r['card_manual']['dialogs'])
          and not any('mid-conversation' in d for d in r['card_manual']['dialogs']),
          r['card_manual'])
    check('a chain step still parks behind a real card (#86 kept)',
          r['card_auto']['out'] == 'not-started'
          and any('still on "cherry"' in n for _, n in r['card_auto']['notes']),
          r['card_auto'])
    check('a conversation in flight draws the danger dialog',
          any('mid-conversation in chat' in d for d in r['chat_ok']['dialogs']),
          r['chat_ok'])
    check('...and saying no keeps the conversation',
          r['chat_declined']['out'] == 'not-started'
          and not r['chat_declined']['notes'],
          r['chat_declined'])
    check('...and saying yes starts the task',
          r['chat_ok']['out'] == 'started', r['chat_ok'])
    check('a chain step never bins a conversation — it parks and says why',
          r['chat_auto']['out'] == 'not-started'
          and not r['chat_auto']['dialogs']
          and any('mid-conversation when this step came up' in n
                  for tid, n in r['chat_auto']['notes'] if tid == 'tk_new'),
          r['chat_auto'])
    check('a parked card does not hide the conversation behind it',
          any('mid-conversation in chat' in d for d in r['parked_chat']['dialogs'])
          and not any('stale' in d for d in r['parked_chat']['dialogs']),
          r['parked_chat'])
    check('a parked card alone still asks nothing (#86 kept)',
          r['parked_idle']['out'] == 'started'
          and not r['parked_idle']['dialogs'],
          r['parked_idle'])

    # ── the registry premise the wording leans on ───────────────────────
    # "a cardless run is a conversation" holds only while chat surfaces are
    # beginAgentRun's only cardless callers. Count the call sites: the task
    # path plus exactly two others (the @mention and delegate paths).
    sites = re.findall(r'beginAgentRun\(', bare)
    check('beginAgentRun has exactly three call sites (task, @mention, delegate)',
          len(sites) == 3,
          f'{len(sites)} call sites — a new one must decide whether a '
          'cardless run is still a conversation before riding this dialog')

    print()
    if FAILS:
        print(f'chat-in-flight: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('chat-in-flight: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
