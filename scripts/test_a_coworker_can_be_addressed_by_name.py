#!/usr/bin/env python3
"""The office hired a coworker it could not address, and did not say so.

Measured end to end on a fresh office with two local brains — Llama on
Ollama, and the front desk's LM Studio card, which hires a coworker named
**Local Brain**.

Asked Llama to hand a question to Local Brain. Llama wrote the DM_TO
inline instead of as a block, so nothing was delivered, and the office's
own guard said so — correctly, and with a way forward:

    (the handoff to Local Brain didn't go out … ask them yourself with @Local.)

I typed exactly that. The CEO answered. Three separate things had to be
wrong for that to happen, and all three were:

1. `unsentHandoff` suggested `@${who.split(/\\s+/)[0]}` — the first word of
   the name. For "Nova" that is "Nova". For "Local Brain" it is nobody.

2. `extractAllMentions` matched `@[A-Za-z][A-Za-z0-9_-]*`: one word, no
   spaces. A coworker with a space in their name could not be addressed at
   all — including by the office itself, since the task→chat bridge writes
   ``@${assignee.name} `` verbatim and would emit a mention it could not
   then parse.

3. The unknown-mention notice in ui/chat.jsx lived INSIDE `if
   (dedup.length)`, so it only ever ran when some OTHER mention had
   matched. The one case where the boss most needs telling — they
   addressed somebody by name and nobody by that name exists — was the one
   case that said nothing and quietly handed the message to the CEO. The
   comment there reads "fall through to CEO so they can clarify"; the CEO
   cannot clarify what it was never told, and it did not.

Any one of these alone is a bad afternoon. Together they are a boss who
follows the office's own written instruction, gets an answer from the
wrong person, and has nothing on screen to tell them the addressee
changed.

Two things this pins that are easy to lose later:

- The fallback stays. With no roster, or a name not on it, parsing is
  exactly what it was — one word — because an unknown name still has to
  parse in order to be REPORTED as unknown. Widening the token itself
  would have swallowed the rest of the sentence.
- Longest match wins. A team holding both "Local" and "Local Brain" must
  route "@Local Brain" to the second; a first-match parser silently gives
  every such message to the shorter name forever.

Run: python3 scripts/test_a_coworker_can_be_addressed_by_name.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'hq-runtime.jsx'
CHAT = ROOT / 'ui' / 'chat.jsx'
APP = ROOT / 'app.jsx'
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


def main():
    print('a coworker can be addressed by the name the office gave them')
    runtime = RUNTIME.read_text(encoding='utf-8')
    chat = CHAT.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')

    # ── 1. the office still creates a name with a space in it ────────────
    # This is the premise. If the front desk stops hiring "Local Brain" the
    # bug goes quiet on its own and this file would be pinning nothing.
    check('the front desk still hires a two-word name',
          re.search(r"name: 'Local Brain'", (ROOT / 'modals' / 'hire.jsx').read_text(encoding='utf-8')),
          'no multi-word coworker means no reachable defect here — but the '
          'NEW HIRE form lets the boss type one at any time')
    check('...and the office writes mentions from that name',
          re.search(r"const prefix = assignee \? `@\$\{assignee\.name\} ` : '';", app),
          'the task→chat bridge is where the office mentions its own '
          'coworkers; it emits the full name')

    # ── 2. the three fixes are wired ─────────────────────────────────────
    check('the mention parser is given the roster',
          re.search(r'function extractAllMentions\(text, roster\)', runtime),
          'without the roster there is no way to know where a name ends')
    sites = re.findall(r'HQ\.extractAllMentions\(([^)]*)\)', chat)
    check('every call site passes one', len(sites) == 2 and all(',' in s for s in sites),
          f'{sites} — a call site that forgets it silently reverts to '
          'one-word names on that path only')
    check('the handoff guard is given the roster too',
          re.search(r'function unsentHandoff\(text, deliveredCount, selfName, roster\)', runtime),
          'this is the sentence that told the boss to type @Local')
    check('...and honestyNotes hands it over',
          re.search(r'push\(unsentHandoff\(raw, delivered, o\.self, o\.roster\)\)', runtime),
          'a parameter nothing fills is the same as no parameter')

    # ── 3. the unknown notice escaped the dedup block ────────────────────
    # Structural, because this is a nesting bug: the notice existed and was
    # correct, it just could not run in the case it was written for.
    send = brace_lift(chat, 'const mentionAll = HQ.extractAllMentions(')
    tail = chat[chat.index('const mentionAll = HQ.extractAllMentions('):]
    tail = tail[:tail.index('\n    setInput(\'\');')]
    dedup_block = re.search(r'if \(dedup\.length\) \{', tail)
    check('the mention block is still shaped as expected', bool(dedup_block), tail[:200])
    if dedup_block:
        after = tail[dedup_block.end():]
        check('an all-unknown mention is reported outside the matched branch',
              re.search(r'\n      \}\n(?:.*?\n)*?      if \(unknown\.length\) \{', after),
              'the notice is still nested under `if (dedup.length)`, so it '
              'cannot fire when NOTHING matched — the case it exists for')
    check('...and the notice names who is actually on the team',
          re.search(r'const team = agents\.map\(a => \'@\' \+ a\.name\)', chat),
          'telling the boss the name is wrong without saying what is right '
          'is half a sentence')

    # ── 4. run the parser ────────────────────────────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH for the behavioural arm')
        return 1 if FAILS else 0

    fn = brace_lift(runtime, 'function extractAllMentions(text, roster) {')
    hf = brace_lift(runtime, 'function unsentHandoff(text, deliveredCount, selfName, roster) {')
    TEAM = ['Local Brain', 'Llama']
    cases = {
        # The measured failure, and the measured fix.
        'two_word': ('@Local Brain hi there', TEAM),
        # An unknown name must still PARSE, or it cannot be reported.
        'unknown': ('@Local hi there', TEAM),
        'fanout': ('@Llama @Local Brain hi there', TEAM),
        # Longest wins: a team holding both must not give this to "Local".
        'ambiguous': ('@Local Brain hi there', ['Local', 'Local Brain']),
        # Unchanged from the regex this replaced.
        'no_roster': ('@plato go', []),
        'punctuation': ('@plato, hello', TEAM),
        'no_body': ('@Llama', TEAM),
        'not_a_mention': ('email me at a@b.com', TEAM),
        'dupes': ('@Llama @llama hi', TEAM),
    }
    js = fn + '\nconst R = {};\n' + '\n'.join(
        'R[%s] = extractAllMentions(%s, %s);' % (json.dumps(k), json.dumps(v[0]), json.dumps(v[1]))
        for k, v in cases.items()
    ) + '\n' + hf + '\n' + (
        'const DM = "Sure. [DM_TO: Local Brain] please take this";\n'
        'R.handoff_known = unsentHandoff(DM, 0, "Llama", %s);\n'
        'R.handoff_unknown = unsentHandoff("x [DM_TO: Nova, the researcher] y", 0, "Llama", %s);\n'
        'R.handoff_short = unsentHandoff("x [DM_TO: Local] y", 0, "Llama", %s);\n'
        'R.handoff_nameless = unsentHandoff("x [DM_TO: ...] y", 0, "Llama", %s);\n'
        % (json.dumps(TEAM), json.dumps(TEAM), json.dumps(TEAM), json.dumps(TEAM))
    ) + 'console.log(JSON.stringify(R));'
    p = subprocess.run(['node', '--input-type=module', '-e', js], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    # A named check, not a raise: a deleted or renamed target should be
    # REPORTED as a failure, not crash the runner into silence.
    check('the lifted parser and guard run at all', p.returncode == 0,
          (p.stderr or '').strip().split('\n')[-1][:300])
    if p.returncode != 0:
        print()
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('a two-word coworker can be addressed',
          r['two_word'] and r['two_word']['targetNames'] == ['Local Brain']
          and r['two_word']['body'] == 'hi there', r['two_word'])
    check('a name that is not on the team still parses, so it can be reported',
          r['unknown'] and r['unknown']['targetNames'] == ['Local'], r['unknown'])
    check('a fan-out mixes one-word and two-word names',
          r['fanout'] and r['fanout']['targetNames'] == ['Llama', 'Local Brain'], r['fanout'])
    check('the longest matching name wins',
          r['ambiguous'] and r['ambiguous']['targetNames'] == ['Local Brain'],
          f"{r['ambiguous']} — first-match would hand every "
          '"@Local Brain …" to a coworker called "Local", forever')
    check('with no roster it behaves exactly as before',
          r['no_roster'] and r['no_roster']['targetNames'] == ['plato']
          and r['no_roster']['body'] == 'go', r['no_roster'])
    check('a name followed by punctuation is still not a mention',
          r['punctuation'] is None,
          'the regex this replaced required whitespace after the name; '
          'losing that turns "@plato, hello" into a dispatch')
    check('a mention with no message is still not a mention',
          r['no_body'] is None, r['no_body'])
    check('an email address is still not a mention',
          r['not_a_mention'] is None, r['not_a_mention'])
    check('case-folded dupes still collapse to one dispatch',
          r['dupes'] and r['dupes']['targetNames'] == ['Llama'], r['dupes'])

    check('the handoff guard suggests a name that can be typed',
          '@Local Brain.' in r['handoff_known'],
          f"{r['handoff_known']} — this is the sentence the boss follows")
    check('...even when the model wrote a name with prose stuck to it',
          '@Nova.' in r['handoff_unknown'],
          f"{r['handoff_unknown']} — the first WORD of "
          '"Nova, the researcher" is "Nova," and the comma makes it '
          'unmentionable; this is the defect the first draft of the fix '
          'shipped with')
    check('...and a short form is completed to the roster spelling',
          '@Local Brain.' in r['handoff_short'],
          f"{r['handoff_short']} — a model writing [DM_TO: Local] means "
          'the coworker called Local Brain; suggesting "@Local" sends the '
          'boss to nobody')
    check('when no name survives, it says so instead of inventing a handle',
          r['handoff_nameless'] and '@' not in r['handoff_nameless']
          and 'send it again yourself' in r['handoff_nameless'],
          f"{r['handoff_nameless']} — §7 wants a way forward, not a "
          'way forward shaped object')

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
