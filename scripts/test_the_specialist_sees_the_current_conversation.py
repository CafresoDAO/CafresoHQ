#!/usr/bin/env python3
"""A fanned-out specialist was handed the conversation as it stood two turns ago.

`dispatchToAgent` built the coworker's model context with a per-render read:

    const recentChat = chat.slice(-6);

Typing "@Vera …" reaches that line in the same tick, so the snapshot is
right and the line looks correct forever. The chief of staff's fan-out does
not reach it in the same tick. It streams a reply, dispatches, awaits, and
only then calls in — through the `onDispatchToAgent` prop the chat panel was
handed renders ago, whose closure holds the chat from before any of it.

Measured on office 9261, 2026-08-15. The boss asked "MARKERALPHA what is the
vendor margin, both angles?" and the office fanned out to two specialists:

    CEO            MARKERALPHA present: True   (45 msgs)
    Vera, a spec   MARKERALPHA present: False   (8 msgs)
    Kip, a speci   MARKERALPHA present: False   (8 msgs)
    CEO            MARKERALPHA present: True   (2 msgs)

It is not the six-line window being too small. Vera's window ended two turns
back, on a reply to a question that was no longer the one being asked.

The @mention path was measured too, on the same office and the same run, and
was NOT stale — its window ended on the previous turn's CEO reply, with the
boss's new words arriving in the direct request. That is the whole difficulty
with this defect: one caller of the line is fine, and which one you happen to
test decides whether you see anything.

The fix is a ref. The ref object is stable across renders, so a closure built
at any render reads the current value; the prop it travels on no longer
decides what the specialist knows. Both dispatchers read it — the delegate
one is reached from a button in the same tick and is not stale today, but
"not stale today" is a fact about the caller, and the caller is a prop.

The task path is deliberately left with no history at all (app.jsx: "A card
dropped on a desk is the whole job"), and this suite pins that too, so a
future pass at this hazard does not helpfully hand it six lines of pears.

Run: python3 scripts/test_the_specialist_sees_the_current_conversation.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_RAW = (ROOT / 'app.jsx').read_text(encoding='utf-8')
RUNTIME_RAW = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Scan code, never prose — the comments written with this fix quote the
    broken read in full, twice."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
    """Body by brace matching. Bounded by structure, not by proximity — both
    dispatchers are several hundred lines long and a character budget would
    quietly stop scanning before the end of the thing it claims to check."""
    i = src.index(opener)
    parens = 0
    j = None
    for k in range(i, len(src)):
        c = src[k]
        if c == '(':
            parens += 1
        elif c == ')':
            parens -= 1
        elif c == '{' and parens == 0:
            j = k
            break
    if j is None:
        raise AssertionError('no body brace found lifting ' + opener)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


def calls(src, opener):
    """Every call spelled `opener`, whole, by paren matching.

    Scanning starts at the opener's own `(` — a first draft started past it,
    so the first inner paren in the argument list closed the count and every
    call came back truncated to a few characters. The check downstream then
    passed because the truncated text did not contain `chat:`, which is the
    precise failure mode this suite exists to complain about."""
    out = []
    start = 0
    while True:
        i = src.find(opener, start)
        if i < 0:
            return out
        start = i + 1
        depth = 0
        for k in range(i, len(src)):
            if src[k] == '(':
                depth += 1
            elif src[k] == ')':
                depth -= 1
                if depth == 0:
                    out.append(src[i:k + 1])
                    break
        else:
            raise AssertionError('unbalanced parens lifting ' + opener)


# A bare `chat` being indexed or having a member read — the per-render
# snapshot. `chatRef.current`, `recentChat` and `persistableChat` are not it,
# hence the lookbehind on word characters and the dot.
BARE_CHAT = re.compile(r'(?<![\w.$])chat\s*[.\[]')


def main():
    print('the specialist sees the current conversation')
    app = strip_comments(APP_RAW)
    code = strip_comments(RUNTIME_RAW)

    # ── 1. the ref, written on every render ─────────────────────────────
    check('the app keeps a ref to the live chat',
          re.search(r'const chatRef = useRefA\(chat\);\s*\n\s*chatRef\.current = chat;', app),
          '— created once and refreshed every render; a ref that is only '
          'initialised is a snapshot with extra steps')

    # ── 2. both dispatchers read it, and read nothing else ──────────────
    # The ban is per-dispatcher rather than file-wide: `chat.length` in an
    # effect dependency and `chat.some(...)` in JSX are per-render reads too,
    # and both are correct — they run during the render they belong to. What
    # cannot read the snapshot is a function the panel calls back into later.
    for label, opener in (
        ('the @mention dispatcher', 'const dispatchToAgent = async (agent, prompt, opts = {}) => {'),
        ('the delegate dispatcher', 'const onDelegate = async (a, typed) => {'),
    ):
        body = brace_lift(app, opener)
        check(label + ' reads the ref',
              'const recentChat = chatRef.current.slice(-6);' in body,
              [opener, '— the window handed to the coworker'])
        stale = BARE_CHAT.findall(body)
        check(label + ' holds no per-render read of the chat at all',
              not stale,
              [stale, '— this function is reached through a prop, so the '
               'render it closed over is whichever one the caller last saw'])

    # ── 3. the window is still actually sent ────────────────────────────
    # A ref read that never leaves the function is a fix to nothing.
    check('both dispatchers still send the window they built',
          len(re.findall(r'\n\s*chat: recentChat,', app)) == 2,
          len(re.findall(r'\n\s*chat: recentChat,', app)))
    check('...and no model context is built from the prop anywhere',
          'chat.slice(' not in app,
          [m for m in re.findall(r'.{40}chat\.slice\(.{20}', app)])
    check('...and that ban is not vacuous — the reads exist, on the ref',
          len(re.findall(r'chatRef\.current\.slice\(-6\)', app)) == 2,
          len(re.findall(r'chatRef\.current\.slice\(-6\)', app)))

    # ── 4. the path that is supposed to have no history, still hasn't ───
    # Measured before this suite existed: back-to-back tasks about pears and
    # then plums, and the plums deliverable came back describing pears.
    # Picked out by its own prompt, not by position: two of the three
    # agentStream calls in this file open `(agent,`, and taking the first is
    # how a check ends up reading the @mention path and reporting on the
    # task path.
    task_calls = [c for c in calls(app, 'await HQ.agentStream(')
                  if 'New task on your desk:' in c]
    check('there is exactly one task-run stream call to check',
          len(task_calls) == 1, len(task_calls))
    check('a task run is still handed no conversation',
          task_calls and not re.search(r'\bchat:', task_calls[0]),
          [task_calls[0][-300:] if task_calls else None,
           '— six lines of an unrelated thread are not context on this path, '
           'they are a wrong subject'])
    check('...and the reason is still written down next to it',
          'A task run gets NO chat history' in APP_RAW,
          '— the next person to sweep for this hazard will read that comment '
          'before deciding the task path is an oversight')

    # ── 5. what the two windows actually become ─────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the conversation check needs it')
    else:
        # chatToMessages is the choke point where stored chat becomes prompt,
        # and it calls stripOfficeVoice on every bubble. Both lifted from
        # source rather than stubbed: whether a stale window still looks like
        # a healthy conversation is the question, and a stub would answer it
        # by construction.
        floor = strip_comments((ROOT / 'app' / 'floor.jsx').read_text(encoding='utf-8'))
        js = floor[floor.index('const VISIT_WORDS = ['):
                   floor.index('function stripOfficeVoice(')] + '\n'
        js += brace_lift(floor, 'function stripOfficeVoice(') + '\n'
        js += brace_lift(code, 'function chatToMessages(') + '\n'
        js += r'''
// The measured fan-out, in order. The boss's question is four turns from
// the end, which is well inside a six-line window — and outside the one
// the specialist was handed.
const HISTORY = [
  { from: 'user',  name: 'You',       text: 'plain question with no mention at all' },
  { from: 'ceo',   name: 'CafresoHQ', text: "Understood — I'll pick that up." },
  { from: 'user',  name: 'You',       text: 'MARKERALPHA what is the vendor margin, both angles?' },
  { from: 'ceo',   name: 'CafresoHQ', text: 'On it — putting this to both of them now.' },
  { from: 'agent', name: 'Vera · Virtual Assistant', text: "Done — I've put my side of it together." },
  { from: 'agent', name: 'Kip · Deep Research',      text: "Done — I've put my side of it together." },
];
const ASK = { role: 'user', content: '[Direct request from the boss]:\nCan you pull the vendor list?' };
const opt = { selfName: 'Vera' };
// Two renders behind is exactly what the closure held: the array as it was
// before the boss's turn and everything the office did about it.
const stale = HISTORY.slice(0, 2);
const live  = HISTORY;
const asked = m => /MARKERALPHA/.test(m.content);
const S = chatToMessages(stale, opt).concat([ASK]);
const L = chatToMessages(live,  opt).concat([ASK]);
console.log(JSON.stringify({
  staleAsked: S.some(asked),
  liveAsked:  L.some(asked),
  staleRoles: S.map(m => m.role),
  liveRoles:  L.map(m => m.role),
  staleLast:  S[S.length - 2].content.slice(0, 60),
}));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        if p.returncode != 0:
            check('the conversation harness runs', False, p.stderr.strip()[:400])
        else:
            R = json.loads(p.stdout)
            check("the stale window has lost the question the boss asked",
                  R['staleAsked'] is False,
                  [R['staleLast'], '— the specialist was answering the turn '
                   'before the one they were dispatched for'])
            check('...and the live window carries it',
                  R['liveAsked'] is True, R['liveRoles'])
            check('nothing downstream could have told the two apart',
                  all(r in ('user', 'assistant') for r in R['staleRoles'])
                  and R['staleRoles'][-1] == R['liveRoles'][-1] == 'user',
                  [R['staleRoles'], '— a stale window is a perfectly '
                   'well-formed conversation. There is no error to catch '
                   'downstream, which is why this had to be caught here'])
            check('...and the coworker\'s own turns still come back as theirs',
                  'assistant' in R['liveRoles'],
                  [R['liveRoles'], '— selfName is what makes Vera\'s line '
                   'hers; without it she reads her own words as the room\'s'])

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
