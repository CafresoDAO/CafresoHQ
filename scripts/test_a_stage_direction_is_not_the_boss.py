#!/usr/bin/env python3
"""A stage direction became the boss's ask.

Measured 2026-08-15 on office 9261, canned brain. Starting a task wrote

    { from: 'user', name: 'You', text: '(dropped "briefing status check"
      on Vera\'s desk)' }

into the chat — a message the boss never typed, filed in the boss's
voice, with no marker of any kind. Every reader believed the record:

1. chatToMessages handed it to brains as a bare role:'user' turn. In the
   same payload the REAL typed ask arrived framed "[Direct request from
   the boss]" and every coworker's words arrived labeled "[Vera · …]:" —
   only the office's fabrications rode unlabeled, wearing the boss's
   voice. Attribution exactly inverted.
2. onDelegate's last-ask finder skips only its OWN wrapper (delegated:
   true — the "four deep" fix). An empty hand-off right after a task
   drop picked the stage direction as "what the boss asked" and
   dispatched Kip on `(dropped "briefing status check two" on Vera's
   desk)` — marching orders about somebody else's desk. The transcript
   then read: (delegated "(dropped "…" on Vera's desk)" to Kip).
3. The Getting Started "chatted" gate — the same two-reader shape whose
   `assigned` half was fixed by #65 — ticked "say hi in chat" off a
   click, over a boss who had never typed a word.

The fix files the three pure-click stage directions (task drop/start,
✓ APPROVED, ✕ REJECTED) in the voice the office already has for
narrating gestures: from:'system', name:'HQ' — the helper-cap and
empty-hand-off lines were already written that way. With the record
true, every reader self-corrects: the renderer shows a quiet stage
direction instead of a "You" bubble, chatToMessages labels it "[HQ]:",
the finder and the chatted gate stop seeing it at all. No reader was
taught to distrust the record; the record stopped lying.

The delegate wrapper stays from:'user' + delegated:true on purpose: its
quoted interior is boss-authored (the typed brief), so the boss's voice
is the honest filing — the flag already keeps it out of the finder.

Residue, recorded not hidden: entries persisted BEFORE the fix carry the
old attribution and are not rewritten (#88's stance on stories), so an
old stage direction still reads as boss speech to every consumer.

Run: python3 scripts/test_a_stage_direction_is_not_the_boss.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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
    """Lift a whole function. Walks the parameter parens first so a
    destructured-default param (`{ omitLastCeo = false } = {}`) doesn't
    get mistaken for the body."""
    i = src.index(header)
    p = src.index('(', i)
    d = 0
    for k in range(p, len(src)):
        if src[k] == '(':
            d += 1
        elif src[k] == ')':
            d -= 1
            if d == 0:
                p = k
                break
    j = src.index('{', p)
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
    print('a stage direction is not the boss')
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    hq = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
    chatui = (ROOT / 'ui' / 'chat.jsx').read_text(encoding='utf-8')
    bare = strip_comments(app)

    # ── the three writes, pinned at the source ──────────────────────────
    # Pin the FACT (this text is office voice), not the variable names —
    # #92's lesson: outlaw a spelling and the defect survives in
    # paraphrase. Each fabricated template must sit in an object literal
    # that says from:'system', and none may say from:'user' nearby.
    TEMPLATES = [
        ("the drop/start line", "'s desk)`"),
        ("the APPROVED line", '✓ APPROVED — ${'),
        ("the REJECTED line", '✕ REJECTED — ${'),
    ]
    for label, tpl in TEMPLATES:
        n = bare.count(tpl)
        check(f'{label} appears once', n == 1, f'{n} occurrences of {tpl!r}')
        if n != 1:
            continue
        window = bare[max(0, bare.index(tpl) - 300):bare.index(tpl)]
        check(f'{label} is office voice',
              "from: 'system', name: 'HQ'" in window
              and "from: 'user'" not in window,
              'the object literal around it must say from:system/HQ — a '
              'stage direction narrates a gesture; the boss typed nothing')

    check('the drop line is still filed next to the streaming bubble',
          re.search(r"setChat\(prev => \[\.\.\.prev, dropMsg, \{ id: agentMsgId, "
                    r"from: 'agent'", bare) is not None,
          'losing the entry entirely would also pass the voice checks — '
          'the boss should still SEE that the card landed')

    check('the delegate wrapper keeps the boss\'s words in the boss\'s voice',
          re.search(r"from: 'user', name: 'You', delegated: true, "
                    r"text: `\(delegated ", bare) is not None,
          'its quoted interior is boss-authored (the typed brief); the '
          'delegated flag is what keeps it out of the finder')
    check('the last-ask finder still skips wrappers',
          re.search(r"\.reverse\(\)\.find\(m => m\.from === 'user' && "
                    r"!m\.delegated\)", bare) is not None)
    check('an empty hand-off still draws the honest notice, not an invention',
          re.search(r"if \(!brief\.trim\(\)\) \{\s*setChat\(prev => "
                    r"\[\.\.\.prev, \{ id: HQ\.uid\('m'\), from: 'system',"
                    r" name: 'HQ',", bare) is not None,
          'with stage directions out of the finder, a drop-then-hand-off '
          'must land here — nothing to hand over IS the honest answer')

    # ── the two chatted-gate sites still ask the one question ───────────
    n_gate = len(re.findall(r"\.some\(m => m\.from === 'user'\)", bare))
    check('both "has the boss chatted" surfaces read the same question',
          n_gate == 2,
          f'{n_gate} sites — the coach mark and Getting Started must '
          'agree (refactoring to a shared const should update this pin)')

    # ── renderer: system entries never wear the You label ───────────────
    map_body = chatui[chatui.index('visibleChat.map'):]
    sys_at = map_body.find("if (m.from === 'system')")
    who_at = map_body.find("const _whoLabel")
    check('the renderer files system entries as stage directions',
          0 <= sys_at < who_at and 'msg-system' in map_body[sys_at:sys_at + 200],
          'the msg-system branch must run before any You captioning')

    # ── behavior, through the real lifted code ──────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — behavior checks need it')
        print()
        if FAILS:
            print(f'stage-direction: {len(FAILS)} FAILED')
            return 1
        print('stage-direction: source checks passed')
        return 0

    ctm = brace_lift(hq, 'function chatToMessages(chat')
    finder_m = re.search(r"\[\.\.\.chat\]\.reverse\(\)\.find\((m => m\.from"
                         r" === 'user' && !m\.delegated)\)", app)
    gate_m = re.search(r"\.some\((m => m\.from === 'user')\)", app)
    js = (
        # stripOfficeVoice scrubs tool-visit echo lines; attribution is
        # untouched by it, so a trim stub keeps this suite about voices.
        'const stripOfficeVoice = (t) => String(t || "").trim();\n'
        + ctm + ';\n'
        + f'const finder = {finder_m.group(1)};\n'
        + f'const gate = {gate_m.group(1)};\n'
        + 'const lastAsk = (chat) => [...chat].reverse().find(finder);\n'
        + 'const chatted = (chat) => (chat || []).some(gate);\n'
        + '''
const TYPED = { from: 'user', name: 'You', text: '@Vera anything new on your desk?' };
const DROP_NEW = { from: 'system', name: 'HQ', text: '(dropped "briefing status check two" on Vera\\'s desk)' };
const DROP_OLD = { from: 'user', name: 'You', text: '(dropped "briefing status check two" on Vera\\'s desk)' };
const WRAP = { from: 'user', name: 'You', delegated: true, text: '(delegated "sweep the vendors" to Kip)' };
const APPROVE = { from: 'system', name: 'HQ', text: '\\u2713 APPROVED \\u2014 Publish site' };
const SELF = { from: 'agent', name: 'Vera · Virtual Assistant', text: 'Here is the plan' };
const R = {
  typed: chatToMessages([TYPED], { selfName: 'Vera' }),
  drop: chatToMessages([DROP_NEW], { selfName: 'Vera' }),
  approve: chatToMessages([APPROVE], { selfName: 'Vera' }),
  self: chatToMessages([SELF], { selfName: 'Vera' }),
  askAfterDrop: (lastAsk([TYPED, DROP_NEW]) || {}).text || null,
  askAfterWrap: (lastAsk([TYPED, WRAP]) || {}).text || null,
  askDropOnly: lastAsk([DROP_NEW]) === undefined,
  askOldHistory: (lastAsk([TYPED, DROP_OLD]) || {}).text || null,
  chattedDrop: chatted([DROP_NEW]),
  chattedTyped: chatted([TYPED]),
  chattedWrap: chatted([WRAP]),
};
console.log(JSON.stringify(R));
''')
    p = subprocess.run(['node', '--input-type=module', '-e', js], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('lifted harness runs', False, p.stderr.strip()[:300])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('boss speech reaches brains bare',
          r['typed'] == [{'role': 'user', 'content': TYPED_TEXT}],
          r['typed'])
    check('the stage direction reaches brains labeled, never as the boss',
          len(r['drop']) == 1 and r['drop'][0]['role'] == 'user'
          and r['drop'][0]['content'].startswith('[HQ]: (dropped')
          and '[HQ]' in r['drop'][0]['content'],
          [r['drop'], '— unlabeled was the inversion: real asks got a '
           'frame while fabrications rode bare'])
    check('an approval receipt is office narration too',
          len(r['approve']) == 1
          and r['approve'][0]['content'].startswith('[HQ]: '),
          r['approve'])
    check('a coworker\'s own words still come back as theirs',
          r['self'] == [{'role': 'assistant', 'content': 'Here is the plan'}],
          r['self'])
    check('after a drop, the boss\'s real last ask is still the ask',
          r['askAfterDrop'] == '@Vera anything new on your desk?',
          [r['askAfterDrop'], '— the measured defect: Kip was dispatched '
           'on the stage direction'])
    check('the delegate wrapper is still not an ask',
          r['askAfterWrap'] == '@Vera anything new on your desk?',
          r['askAfterWrap'])
    check('a drop with no real ask behind it hands over nothing',
          r['askDropOnly'] is True,
          '— the empty hand-off then says so instead of inventing')
    check('residue, recorded: pre-fix history still reads as boss speech',
          r['askOldHistory'] == DROP_TEXT,
          [r['askOldHistory'], '— stories are not rewritten; a migration '
           'that stamps old entries should flip this check on purpose'])
    check('a click does not tick "the boss chatted"',
          r['chattedDrop'] is False, r['chattedDrop'])
    check('a typed message does',
          r['chattedTyped'] is True and r['chattedWrap'] is True,
          [r['chattedTyped'], r['chattedWrap'], '— the wrapper carries '
           'the boss\'s typed brief, so it counts'])

    print()
    if FAILS:
        print(f'stage-direction: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('stage-direction: all checks passed')
    return 0


TYPED_TEXT = '@Vera anything new on your desk?'
DROP_TEXT = '(dropped "briefing status check two" on Vera\'s desk)'

if __name__ == '__main__':
    raise SystemExit(main())
