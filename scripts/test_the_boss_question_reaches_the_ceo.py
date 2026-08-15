#!/usr/bin/env python3
"""A mistyped @name sent the chief of staff a conversation with nothing in it.

The send path built the CEO's message list by capturing it out of a state
updater:

    let pendingChat = [];
    setChat(prev => { pendingChat = [...prev, userMsg]; return pendingChat; });

That reads back only while this hook's queue is untouched, because React
evaluates the first updater of an untouched queue eagerly. `setInput('')`
a few lines above is a DIFFERENT hook, so it never disturbed it — which is
why the line held for so long.

The stray-name branch is not a different hook. "@Dana …" against a roster
of Vera and Kip pushes "(nobody here is called @Dana — the team is @Vera,
@Kip. Sending this to CafresoHQ instead.)" into chat, and from then on the
queue is dirty: the capture stays `[]`, `chatToMessages([])` is `[]`, and
the request that leaves the office carries exactly ONE message — the
system prompt. No history. Not even the question.

Measured on office 9261, 2026-08-15, before the fix:

    roles: ['system']

On screen it looked completely ordinary: the note, the boss's message, and
a confident CEO reply to neither of them. The office had just said in its
own voice "Sending this to CafresoHQ instead", and had sent nothing.

Two things changed. The state write is now a plain append, which cannot
clobber whatever landed since the last render — the hazard the original
comment was written about. And what the CEO is SENT is built from a ref,
plus the stray note, which the branch's own comment had already asked for:
"The CEO cannot clarify what it was never told."

After the fix, same input, same office: 41 messages, ending with the note
and then the question. A plain message with no mention: 43, unbroken.

Run: python3 scripts/test_the_boss_question_reaches_the_ceo.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAT = (ROOT / 'ui' / 'chat.jsx').read_text(encoding='utf-8')
RUNTIME = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Scan code, never prose — the comment written with this fix quotes the
    broken capture in full, including the variable it assigned to."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
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


def main():
    print('the boss question reaches the CEO')
    chat = strip_comments(CHAT)
    code = strip_comments(RUNTIME)

    # ── 1. no capture-from-updater anywhere in the panel ────────────────
    # Not "not on this line" — anywhere. The same idiom was dead on the
    # synthesis pass and conditionally alive here, and the difference
    # between those two is invisible at the call site. So the check is a
    # ban, not a spot fix.
    captures = re.findall(r'set[A-Z]\w*\(\s*\w+\s*=>', chat)
    bad = [m.group(0) for m in re.finditer(
        r'set[A-Z]\w*\(\s*(\w+)\s*=>\s*\{[^\n]{0,160}', chat)
        if re.search(r'\b\w+\s*=\s*(\[\s*\.\.\.)?' + re.escape(m.group(1)) + r'\b',
                     m.group(0))]
    check('nothing in the panel reads state back out of an updater',
          not bad,
          [bad, '— it reads back only while that hook queue is untouched, '
           'and nothing at the call site says whether it is'])
    check('...and the panel has updaters, so that check is not vacuous',
          len(captures) > 5, len(captures))

    # ── 2. what the CEO is sent, and what the state write does ──────────
    check('the CEO payload is built from the live ref',
          re.search(r'const pendingChat = \[\.\.\.chatRef\.current,', chat),
          '— the `chat` prop is a per-render snapshot; this is not')
    check('...and carries the boss\'s own message',
          re.search(r'const pendingChat = \[[^\n]*userMsg\];', chat),
          '— the reproduced request had no user turn in it at all')
    check('the state write is an append, so it cannot clobber',
          re.search(r'setChat\(prev => \[\.\.\.prev, userMsg\]\);', chat),
          '— returning a captured snapshot is what erased agent DMs that '
           'landed since the last render, which is why the capture existed')
    check('...and the payload still goes to ceoStream',
          re.search(r'HQ\.ceoStream\(text, flush, \{ chat: pendingChat,', chat),
          chat[:0])

    # ── 3. the stray note reaches the CEO, not just the screen ──────────
    # This is the half the branch's own comment asked for and did not get.
    stray_at = chat.index('Sending this to CafresoHQ instead')
    stray = chat[chat.rindex('if (unknown.length) {', 0, stray_at):]
    stray = stray[:stray.index('\n      }\n')]
    check('the stray-name note is built once, as a value',
          re.search(r'strayNote = \{', stray),
          [stray[:200], '— it was constructed inline inside setChat, so it '
           'existed only in state and could not be shown to the CEO'])
    check('...and is still shown to the boss',
          re.search(r'setChat\(prev => \[\.\.\.prev, strayNote\]\);', stray),
          stray[-200:])
    check('...and is included in what the CEO is sent',
          re.search(r'\.\.\.\(strayNote \? \[strayNote\] : \[\]\)', chat),
          '— "The CEO cannot clarify what it was never told"')
    # `.find`, not `.index`. Fire-testing crashed the whole suite here on
    # an arm that removed the assignment: a check that raises reports
    # nothing at all, which is worse than a check that fails.
    decl_at, use_at = chat.find('let strayNote = null;'), chat.find('strayNote = {')
    check('...declared where both halves can see it',
          decl_at >= 0 and use_at >= 0 and decl_at < use_at,
          [decl_at, use_at, '— written in the @mention block, read on the '
           'CEO path'])

    # ── 4. the shape that makes an empty list catastrophic ──────────────
    # chatToMessages has no floor: given [] it returns [], and ceoStream
    # sends that as the entire conversation. Nothing downstream notices.
    body = brace_lift(code, 'function chatToMessages(')
    check('chatToMessages has no floor of its own',
          'return out;' in body and 'if (!out.length)' not in body,
          '— this is not a bug in chatToMessages; it is why the CALLER has '
          'to be right. An empty list is a legal answer to an empty chat')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the emptiness check needs it')
    else:
        # stripOfficeVoice lives in app/floor.jsx and chatToMessages calls
        # it on every bubble. Lifted rather than stubbed: a stub would let
        # the harness agree with itself about whether the stray note
        # survives the conversion, which is the thing being asked.
        floor = strip_comments((ROOT / 'app' / 'floor.jsx').read_text(encoding='utf-8'))
        # stripOfficeVoice sits on a chain — _officeVoiceRe, _VISIT_VERBS,
        # _VISIT_ICONS, VISIT_WORDS. Sliced whole rather than lifted piece
        # by piece, and deliberately not stubbed: whether the stray note
        # survives this strip is the question, and a stub would answer it
        # by construction.
        js = floor[floor.index('const VISIT_WORDS = ['):
                   floor.index('function stripOfficeVoice(')] + '\n'
        js += brace_lift(floor, 'function stripOfficeVoice(') + '\n'
        js += body + '\n'
        js += r'''
const NOTE = { from: 'system', name: 'HQ',
  text: '(nobody here is called @Dana — the team is @Vera, @Kip. Sending this to CafresoHQ instead.)' };
const ASK  = { from: 'user', name: 'You', text: '@Dana can you follow up on that margin thread?' };
const PRIOR = { from: 'ceo', name: 'CafresoHQ', text: 'Understood.' };
const R = {
  // What the office actually sent before the fix.
  wasSent:  chatToMessages([]),
  // What it sends now: history, the note, the question.
  nowSent:  chatToMessages([PRIOR, NOTE, ASK]),
  // The note must arrive as something the model reads, not be dropped.
  noteSeen: chatToMessages([NOTE]).length,
};
console.log(JSON.stringify(R));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        if p.returncode != 0:
            check('the conversation harness runs', False, p.stderr.strip()[:400])
        else:
            R = json.loads(p.stdout)
            check('an empty chat really does produce an empty conversation',
                  R['wasSent'] == [],
                  [R['wasSent'], '— so the capture returning [] was not '
                   'degraded context, it was no context'])
            check('...and the boss\'s question survives the conversion',
                  any(m['role'] == 'user' and 'margin thread' in m['content']
                      for m in R['nowSent']),
                  R['nowSent'])
            check('...as does the stray-name note',
                  R['noteSeen'] == 1
                  and 'nobody here is called @Dana' in
                      chatToMessagesFirst(R['nowSent']),
                  [R['nowSent'], '— stripOfficeVoice drops the office\'s own '
                   'action reports; this note is not one of those'])

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


def chatToMessagesFirst(msgs):
    return ' '.join(m['content'] for m in msgs)


if __name__ == '__main__':
    sys.exit(main())
