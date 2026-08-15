#!/usr/bin/env python3
"""A coworker was shown the chief of staff's words as her own.

Reproduced 2026-08-15 against a canned brain (port 9236) that appends
every request body it receives to `asked.jsonl`. Hire Vera, send one
`@Vera hello`, then read what actually went on the wire. The system
prompt says "You are Vera, a specialist coworker at CafresoHQ" — and the
transcript under it opened with three `assistant` turns Vera never spoke:

    system     You are Vera, a specialist coworker at CafresoHQ…
    assistant  Welcome to your HQ — I'm CafresoHQ, your chief of staff…
    assistant  We don't have a shared brain here… I'm opening the
               candidate book now…
    assistant  Welcome aboard, Vera! I've set up a desk.
    user       [Direct request from the boss]: hello

Vera was shown greeting herself, and shown claiming to be the chief of
staff. `assistant` is not a display label — it is the one role every chat
API defines as "you said this", and a small local brain reads it as an
instruction about who it is.

The mirror image was in the same two lines. Vera's OWN prior replies were
labelled `[Vera · Virtual Assistant]: …` under `user` — so the only turns
marked as hers were ones she had not said, and none of the ones she had.

`chatToMessages` is the single place stored chat becomes prompt, and it
had no idea who it was building for. It now takes `selfName`: omit it and
the reader is the chief of staff (unchanged — ceoStream), pass a name and
the reader is that coworker.

Measured on the same canned brain after the fix, with a CEO message in
the chat:

    user       [CafresoHQ]: Welcome aboard, Kip! I've set up a desk.
    user       [Direct request from the boss]: status please

and, in a chat containing Vera's own prior reply:

    user       @Vera hello
    assistant  Understood, on it.

This is the most runtime-agnostic surface in the product — every brain,
local or hosted, is handed this same envelope — so authorship is worth
more here than in any per-provider fix.

Run: python3 scripts/test_whose_words_are_whose.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Scan code, never prose. The comment written with this fix quotes
    the mislabelled transcript verbatim, `assistant` lines and all."""
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
    print('whose words are whose')
    code = strip_comments(RUNTIME)
    fn = brace_lift(code, 'function chatToMessages(')

    # ── 1. the transcript knows who it is for ───────────────────────────
    check('chatToMessages is told who it is building for',
          re.search(r'function chatToMessages\(chat, \{[^}]*selfName', fn),
          [fn[:120], '— without it there is no way to answer "is this turn '
           'mine", and every reader got the same wrong answer'])
    check('...and the coworker path tells it',
          re.search(r'chatToMessages\(chat, \{ selfName: agent\.name \}\)', code),
          'agentStream — the call that was building an anonymous transcript')
    # The CEO branch is the one that was always right; it must stay right.
    check('...and the chief of staff path deliberately does not',
          re.search(r"chatToMessages\(chat, \{ omitLastCeo: true \}\)", code)
          and 'selfName' not in re.search(
              r'chatToMessages\(chat, \{ omitLastCeo: true \}\)', code).group(0),
          'ceoStream — when the reader IS the CEO, ceo turns are its own')

    # ── 2. the two branches that were wrong ─────────────────────────────
    check("a CEO turn is a third party's when someone else is reading",
          re.search(r"if \(selfName\) out\.push\(\{ role: 'user', "
                    r"content: `\[\$\{m\.name\}\]: \$\{text\}` \}\)", fn),
          [fn, '— the peer form on the last line was always the right '
           'shape for a third party; the CEO simply is one'])
    check('...and stays the assistant only when the CEO is reading',
          re.search(r"else out\.push\(\{ role: 'assistant', content: text \}\);", fn),
          fn)
    check("a coworker's own turn is finally marked as theirs",
          re.search(r"selfName && speaker\(m\) === selfName", fn),
          [fn, '— these arrived as `[Vera · Role]: …` under `user`'])
    check('...matched on the name, not the captioned name-and-role',
          re.search(r"split\(' · '\)", fn),
          '— bubbles are captioned `${name} · ${role}`; a role edit must '
          'not orphan a coworker from their own history')
    # A coworker named CafresoHQ must not inherit the CEO's turns.
    # `.find`, not `.index` — the same lesson as the last ticket, relearned
    # by fire-testing this one: `.index` raises when the needle is gone, so
    # an arm that DELETES the self branch reports "the suite crashed"
    # instead of "this invariant broke". -1 fails the check it should fail.
    ceo_at, self_at = fn.find("m.from === 'ceo'"), fn.find('speaker(m) === selfName')
    check('the self branch cannot capture the chief of staff',
          ceo_at >= 0 and self_at >= 0 and ceo_at < self_at,
          [ceo_at, self_at, '— the ceo branch is checked first, so a name '
           "collision cannot hand one speaker another speaker's turns"])

    # ── 3. run it ───────────────────────────────────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the transcript checks need it')
    else:
        js = 'const stripOfficeVoice = (s) => String(s || "");\n' + fn + '\n'
        js += r'''
// The reproduced chat, in order: the office greets the boss, the boss
// @mentions Vera, Vera answers, a peer answers.
const CHAT = [
  { from: 'ceo',   name: 'CafresoHQ', text: "Welcome aboard, Vera! I've set up a desk." },
  { from: 'user',  name: 'You',       text: '@Vera hello' },
  { from: 'agent', name: 'Vera · Virtual Assistant', text: 'Understood, on it.' },
  { from: 'agent', name: 'Kip · Engineer',           text: 'Build is green.' },
];
const forVera = chatToMessages(CHAT, { selfName: 'Vera' });
const forCeo  = chatToMessages(CHAT);
const asst = (ms) => ms.filter(m => m.role === 'assistant').map(m => m.content);

const R = {
  // What Vera is told she said. Pre-fix this was the CEO's welcome.
  veraAssistant: asst(forVera),
  veraCeoTurn: forVera[0],
  veraOwnTurn: forVera[2],
  veraPeerTurn: forVera[3],
  // No assistant turn in Vera's transcript may contain the CEO's words.
  veraToldSheGreetedHerself: asst(forVera).some(c => /Welcome aboard, Vera/.test(c)),
  // The chief of staff's own transcript is unchanged.
  ceoAssistant: asst(forCeo),
  ceoPeerTurn: forCeo[3],
  // A coworker named after the office does not inherit its turns.
  collision: asst(chatToMessages(CHAT, { selfName: 'CafresoHQ' }))
               .some(c => /Welcome aboard/.test(c)),
  // A role edit must not orphan someone from their own history.
  roleRenamed: asst(chatToMessages(
      [{ from: 'agent', name: 'Vera · Chief of Research', text: 'mine' }],
      { selfName: 'Vera' })),
  // omitLastCeo still drops a trailing CEO turn.
  omitted: chatToMessages(
      [{ from: 'user', name: 'You', text: 'hi' },
       { from: 'ceo', name: 'CafresoHQ', text: 'thinking…' }],
      { omitLastCeo: true }).length,
};
console.log(JSON.stringify(R));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        if p.returncode != 0:
            check('the transcript harness runs', False, p.stderr.strip()[:400])
        else:
            R = json.loads(p.stdout)
            check('a coworker is never shown greeting herself',
                  R['veraToldSheGreetedHerself'] is False,
                  [R['veraAssistant'], '— this is the reproduced defect'])
            check("the chief of staff arrives as a named third party",
                  R['veraCeoTurn'] == {
                      'role': 'user',
                      'content': "[CafresoHQ]: Welcome aboard, Vera! I've set up a desk."},
                  R['veraCeoTurn'])
            check("...and the coworker's own reply as her own",
                  R['veraOwnTurn'] == {'role': 'assistant', 'content': 'Understood, on it.'},
                  [R['veraOwnTurn'], '— unlabelled: an assistant turn is '
                   'hers by role, and a name inside it is what small models '
                   'copy to the top of their next reply'])
            check('...with exactly one voice marked as hers',
                  R['veraAssistant'] == ['Understood, on it.'], R['veraAssistant'])
            check('a peer is still a labelled third party',
                  R['veraPeerTurn'] == {'role': 'user', 'content': '[Kip · Engineer]: Build is green.'},
                  R['veraPeerTurn'])
            check('the chief of staff still owns its own turns',
                  R['ceoAssistant'] == ["Welcome aboard, Vera! I've set up a desk."],
                  [R['ceoAssistant'], '— ceoStream passes no selfName; this '
                   'branch was correct and must not move'])
            check("...and still sees coworkers as labelled peers",
                  R['ceoPeerTurn'] == {'role': 'user', 'content': '[Kip · Engineer]: Build is green.'},
                  R['ceoPeerTurn'])
            check('a name collision with the office grants nothing',
                  R['collision'] is False,
                  [R, '— a coworker named CafresoHQ must not inherit the '
                   'chief of staff\'s turns as their own'])
            check('renaming a role does not orphan the history behind it',
                  R['roleRenamed'] == ['mine'], R['roleRenamed'])
            check('omitLastCeo still drops the trailing CEO turn',
                  R['omitted'] == 1, R['omitted'])

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
