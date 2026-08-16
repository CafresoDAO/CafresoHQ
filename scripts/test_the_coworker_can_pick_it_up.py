#!/usr/bin/env python3
"""A run that stops at the hop budget has to be resumable, because the
office promises the boss it is.

Reproduced 2026-08-16 on office 9280 against the canned brain (9236). A
coworker with a vault was asked a question whose every hop answered with
the same tool call, so all four hops fired and the loop ran out of budget.
The office then said, in its own voice, in the chat:

    Let me check the vendor notes on file before I answer.
    Let me check the vendor notes on file before I answer.
    Let me check the vendor notes on file before I answer.
    Let me check the vendor notes on file before I answer.
    _(they did as much as they can in one go and stopped there. If this is
      part of a running project it will carry on by itself; otherwise ask
      again and they will pick it up.)_

The boss asked again — the one door the sentence names — and this is the
request that went on the wire, read off the brain's own log:

    system     You are Local Brain, a specialist coworker at CafresoHQ…
    user       @Local Brain hop budget probe one two six — what do the …
    assistant  Let me check the vendor notes on file before I answer.…
    user       [Direct request from the boss]: carry on one two six

Four VAULT_READs of a file containing the string ZEPHYR-QUOTA-8841, and
the resumed turn carried no TOOL_RESULT turn, no file content, and no
sentinel. The coworker was handed its own four "let me go and look" lines
with everything looking had found removed, and asked to carry on.

Nothing had been lost. `toVisit` puts every tool result on the message as
`body`, and it was sitting there on the very bubble the hint was attached
to. `chatToMessages` — the single place stored chat becomes prompt — reads
`m.text` and nothing else, and a visit is not in the text.

So this suite holds two things that have to stay true together:

  1. if the office tells the boss that asking again picks the job up,
     then the results of the stopped run go back to the brain
  2. and only the reader's OWN results do, framed the way a live hop
     frames them, with the office's report of the trip left behind

That second half is the rule this function already enforced for `m.text`
(§4, and the forged `📡 …→` visit that made it necessary): result bodies
survive, the office's voice does not. `head` and `icon` are the voice.
`[TOOL_RESULT: <name>]` is not — it is the protocol frame the brain is
shown on every hop of a live run, which is exactly what makes a resumed
turn read like the turn it resumes.

§5 (a wrong door is worse than a locked one) and §7 (an honest sentence
still needs a way forward).

Run: python3 scripts/test_the_coworker_can_pick_it_up.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
FLOOR = (ROOT / 'app' / 'floor.jsx').read_text(encoding='utf-8')
FAILS = []

SENTINEL = 'ZEPHYR-QUOTA-8841'
# The office's words for the trip. Never allowed into a transcript.
HEAD = 'Opened Research/vendor-notes.md in the cabinet'


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Scan code, never prose. The comments written with this fix quote the
    reproduced transcript, sentinel and all, and one of them contains the
    literal `[TOOL_RESULT: <name>]` that half these checks search for."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
    """Body by brace matching; the opener is the first `{` at paren depth 0."""
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
    print('the coworker can pick it up')
    code = strip_comments(RUNTIME)
    floor = strip_comments(FLOOR)
    fn = brace_lift(code, 'function chatToMessages(')

    # ── 1. the promise and the mechanism are one ticket ──────────────────
    # Read as "promised ⇒ mechanised", not as a ban on changing the words.
    # If a future round decides the office should stop offering a resume,
    # the first half of each pair goes false and this stops objecting —
    # but nobody gets to keep the sentence and drop the machinery.
    # Matched on the sentence rather than the call: #127 split agentStream's
    # into two, one for a caller that passes history and one for a caller
    # that does not, so the hint is no longer a bare string argument. Which
    # caller gets which is that ticket's business (see
    # scripts/test_a_run_that_stopped_is_not_a_finished_run.py). What is
    # this suite's business is the pairing below, and it reads every
    # sentence the office might say, however it is selected.
    hints = re.findall(r"'_\(they did as much as they can[^']*'", code)
    check('the hop-budget hints are still findable',
          len(hints) >= 2,
          [hints, '— at least ceoStream and agentStream; a caller with its '
           'own wording somewhere else would be unowned by this suite'])
    promises = [h for h in hints if 'ask again' in h.lower()]
    replays = bool(re.search(r"\[TOOL_RESULT: \$\{v\.name\}\]", fn))
    check('a hint that says "ask again" is backed by a real resume',
          not promises or replays,
          [promises, '— this is the reproduced defect: the sentence named '
           'the door and the door did nothing'])
    check('...and the resume reads the results off the message',
          're.visits' not in fn and 'm.visits' in fn,
          [fn, '— the bodies were already stored on the bubble; the fix is '
           'that the transcript finally looks at them'])

    # ── 2. the office's voice stays behind ───────────────────────────────
    check('the transcript never reaches for the visit head',
          '.head' not in fn,
          [fn, '— `head` is "Opened X in the cabinet", the office narrating '
           'its own trip, and a model that reads it in history learns to '
           'write it (see the forged 📡 visit in app/floor.jsx)'])
    check('...nor for its icon',
          '.icon' not in fn, fn)
    check('...and replays only the reader\'s own trips',
          re.search(r'if \(!mine\) continue;', fn),
          [fn, "— another coworker's results are hearsay, and hearsay "
           'already has a shape here: `[Name]: …` under `user`'])

    # ── 3. the record keeps what a frame needs ───────────────────────────
    tv = brace_lift(floor, 'function toVisit(')
    check('a visit records which tool ran',
          re.search(r'name: ev\.name', tv),
          [tv, '— without it a replayed result is a page of text with '
           'nothing saying which question it answers'])
    check('...and what it was asked for',
          re.search(r'arg: ev\.arg', tv), tv)
    check('...with the arg stored whole',
          not re.search(r'arg:[^,\n]*slice\(', tv),
          [tv, '— `body` is capped at VISIT_RESULT_CAP because a page fetch '
           'is long; an arg is a path or a query, and a path cut short is a '
           'different path'])

    # ── 4. run it ────────────────────────────────────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the transcript checks need it')
    else:
        js = 'const stripOfficeVoice = (s) => String(s || "");\n' + fn + '\n'
        js += r'''
const VISIT = { icon: '📁', head: 'Opened Research/vendor-notes.md in the cabinet',
                body: 'Negotiated ceiling reference: ZEPHYR-QUOTA-8841',
                failed: false, at: null,
                name: 'VAULT_READ', arg: 'Research/vendor-notes.md' };

// The reproduced chat: the boss asks, the coworker reads a file and runs
// out of hops, a peer says something unrelated.
const CHAT = [
  { from: 'user',  name: 'You', text: 'what do the vendor notes say?' },
  { from: 'agent', name: 'Vera · Generalist',
    text: 'Let me check the vendor notes on file before I answer.',
    visits: [VISIT] },
  { from: 'agent', name: 'Kip · Engineer', text: 'Build is green.', visits: [VISIT] },
];

const dump = (ms) => JSON.stringify(ms);
const forVera = chatToMessages(CHAT, { selfName: 'Vera' });
const forKip  = chatToMessages(CHAT, { selfName: 'Kip' });

// A chief-of-staff bubble carrying its own trip, read both ways.
const CEO = [{ from: 'ceo', name: 'CafresoHQ', text: 'Checked it.', visits: [VISIT] }];

// A stopped run whose every hop was a tool call leaves no prose at all.
const SILENT = [{ from: 'agent', name: 'Vera · Generalist', text: '', visits: [VISIT] }];

// Written before this change: a body, and no idea which tool produced it.
const LEGACY = [{ from: 'agent', name: 'Vera · Generalist', text: 'done',
                  visits: [{ icon: '📁', head: 'Opened a file', failed: false,
                             body: 'ZEPHYR-QUOTA-8841' }] }];

// A trip that came back with nothing to say.
const EMPTY = [{ from: 'agent', name: 'Vera · Generalist', text: 'done',
                 visits: [{ name: 'VAULT_READ', arg: 'x.md', body: '   ' }] }];

const R = {
  vera: forVera,
  veraHasSentinel: /ZEPHYR-QUOTA-8841/.test(dump(forVera)),
  // The peer's identical trip must not become Vera's own work.
  kipsTripLeakedToVera: forVera.filter(
      m => /ZEPHYR-QUOTA-8841/.test(m.content)).length,
  // …and reads correctly from the other side.
  kipHasSentinel: /ZEPHYR-QUOTA-8841/.test(dump(forKip)),
  // The office's narration of the trip, in any transcript, is the defect
  // this function has been guarding against since the forged visit.
  headLeaked: /Opened Research/.test(dump(forVera) + dump(forKip)
                                     + dump(chatToMessages(CEO))),
  ceoOwnTrip: chatToMessages(CEO),
  ceoTripSeenBySpecialist: /ZEPHYR-QUOTA-8841/.test(
      dump(chatToMessages(CEO, { selfName: 'Vera' }))),
  silent: chatToMessages(SILENT, { selfName: 'Vera' }),
  legacy: chatToMessages(LEGACY, { selfName: 'Vera' }),
  empty: chatToMessages(EMPTY, { selfName: 'Vera' }),
  // The four role mappings this fix restructured the branch of.
  roles: chatToMessages(CHAT, { selfName: 'Vera' }).map(m => m.role),
  ceoAsThirdParty: chatToMessages(CEO, { selfName: 'Vera' })[0],
};
console.log(JSON.stringify(R));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        if p.returncode != 0:
            check('the transcript harness runs', False, p.stderr.strip()[:400])
        else:
            R = json.loads(p.stdout)
            vera = R['vera']

            check('the stopped run\'s result reaches the resumed turn',
                  R['veraHasSentinel'] is True,
                  [vera, '— this is the reproduced defect: the boss asked '
                   'again and the brain was handed nothing it had found'])
            check('...framed the way a live hop frames it',
                  any(m['role'] == 'user'
                      and m['content'].startswith('[TOOL_RESULT: VAULT_READ]')
                      and SENTINEL in m['content'] for m in vera),
                  [vera, '— the brain sees this exact envelope on every hop '
                   'of a run that does not stop; a resumed turn should be '
                   'indistinguishable from the one it resumes'])
            check('...under the call it answers',
                  any(m['role'] == 'assistant'
                      and m['content'] == '[VAULT_READ: Research/vendor-notes.md]'
                      for m in vera),
                  [vera, '— visibleReply strips the marker out of the stored '
                   'text, so without this the result names no file'])
            check('...after what the coworker said, not before it',
                  ([m['role'] for m in vera].index('assistant')
                   < max(i for i, m in enumerate(vera)
                         if m['content'].startswith('[TOOL_RESULT'))),
                  [vera, '— the last thing before the boss\'s new ask should '
                   'be the result, which is where the stopped run stopped'])

            check("a peer's identical trip is not replayed as the reader's",
                  R['kipsTripLeakedToVera'] == 1,
                  [vera, '— Kip made the same trip in this chat; exactly one '
                   'copy of the sentinel may appear in Vera\'s transcript, '
                   'and it has to be hers'])
            check('...and is replayed for the peer when the peer reads',
                  R['kipHasSentinel'] is True,
                  '— the rule is ownership, not suppression')

            check('the office\'s report of the trip reaches no transcript',
                  R['headLeaked'] is False,
                  '— `head` is the template a local model once learned to '
                  'forge, complete with an invented result and vault path')

            check("the chief of staff's own trip comes back to the chief of staff",
                  any(m['content'].startswith('[TOOL_RESULT: VAULT_READ]')
                      for m in R['ceoOwnTrip']),
                  [R['ceoOwnTrip'], '— ceoStream passes no selfName, so a ceo '
                   'bubble IS the reader\'s own turn there'])
            check('...and is hearsay to everybody else',
                  R['ceoTripSeenBySpecialist'] is False,
                  '— for a specialist the same bubble is a third party, and '
                  'a third party\'s results are not theirs to have run')
            check('...whose words still arrive labelled',
                  R['ceoAsThirdParty'] == {'role': 'user',
                                           'content': '[CafresoHQ]: Checked it.'},
                  R['ceoAsThirdParty'])

            check('a run that produced only tool calls still resumes',
                  [m['content'] for m in R['silent']]
                  == ['[VAULT_READ: Research/vendor-notes.md]',
                      '[TOOL_RESULT: VAULT_READ]\n'
                      'Negotiated ceiling reference: ' + SENTINEL],
                  [R['silent'], '— `if (!text) continue` used to drop the '
                   'whole bubble, and a hop budget spent entirely on tools '
                   'is exactly the run this ticket is about'])
            check('...without inventing a turn nobody spoke',
                  all(m['content'].strip() for m in R['silent']),
                  R['silent'])

            check('a visit stored before this change still gives up its body',
                  any(m['content'] == '[TOOL_RESULT]\nZEPHYR-QUOTA-8841'
                      for m in R['legacy']),
                  [R['legacy'], '— an unnamed frame is honest; dropping the '
                   'body loses work the coworker did, and guessing the name '
                   'attributes it to a tool that may not have run'])
            check('...and claims no call it cannot name',
                  not any(m['role'] == 'assistant' and m['content'].startswith('[')
                          for m in R['legacy']),
                  R['legacy'])

            check('a trip that came back empty adds no turn',
                  [m['content'] for m in R['empty']] == ['done'],
                  [R['empty'], '— an empty TOOL_RESULT tells the brain a '
                   'tool answered when it had nothing to answer with'])

            check('the four role mappings survived the restructure',
                  R['roles'] == ['user', 'assistant', 'assistant', 'user', 'user'],
                  [R['roles'], vera, '— boss, Vera\'s prose, her replayed '
                   'call, her replayed result, then Kip as a labelled peer'])

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
