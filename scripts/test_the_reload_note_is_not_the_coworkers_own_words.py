#!/usr/bin/env python3
"""The office's "this reply stopped when the page reloaded" note was being
sent to the brain as the coworker's own words.

#348 fixed a real defect on the screen: a reply the page outlived came back
from a reload as a blank bubble under the coworker's name, with nothing
anywhere saying the answer had been cut off. Its fix stamps a durable
`interrupted` marker on the write and spends it on the read (`chatOnLoad`),
appending one of two sentences INTO the message's `text`:

    _(nothing came back — this reply stopped when the page reloaded.
      Ask again when you want it.)_
    …partial tokens…

    _(cut off here — this reply stopped when the page reloaded.
      Ask again if you need the rest.)_

Right for the bubble. Wrong one file over. `chatToMessages` (hq-runtime.jsx)
is, in its own words, "the single place stored chat becomes prompt", and a
message's `text` is exactly what it sends as that speaker's `assistant`
turn. Measured under node on the real `persistableChat -> chatOnLoad ->
chatToMessages` chain, with an interrupted reply from a coworker named Kip:

    BEFORE #348   [ {user: 'summarise the deck'} ]
                  -- the empty placeholder had no text, so `if (text)`
                     dropped it and the envelope was clean

    AFTER #348    [ {user: 'summarise the deck'},
                    {assistant: '_(nothing came back — this reply stopped
                      when the page reloaded. Ask again when you want it.)_'} ]

A turn Kip never spoke, in the one grammatical slot every chat API defines
as "you said this", instructing the model that it had already declined and
told the boss to ask again. That is precisely the forgery `stripOfficeVoice`
was written to stop -- its own comment: "the office's report of its OWN
actions must not re-enter the model's context as prior conversation" -- and
the strip regex knew only the visit templates, so the office's own newest
sentence walked straight past it. The partial case is worse in kind: the
brain reads "Three risks: \n\n_(cut off here — …)_" as Kip having narrated
his own interruption mid-sentence.

Fix: both sentences are office voice, so they live in app/floor.jsx beside
the visit templates and leave through the same door. `stripOfficeVoice`
removes them; app/storage.jsx imports the constants instead of spelling
them itself, so the bubble and the strip can never drift apart. The empty
case then strips to '' and the turn is dropped whole -- the pre-#348
envelope exactly -- and the partial case keeps the tokens that really
arrived and drops only the narration, which is this function's standing
rule: "Result bodies survive; only the template goes."

The screen is unchanged. This test asserts both halves: the bubble still
says it, and the brain still never hears it.

Run: python3 scripts/test_the_reload_note_is_not_the_coworkers_own_words.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOOR = ROOT / 'app' / 'floor.jsx'
STORAGE = ROOT / 'app' / 'storage.jsx'
RUNTIME = ROOT / 'hq-runtime.jsx'
FAILS = []

GONE = ('_(nothing came back — this reply stopped when the page reloaded. '
        'Ask again when you want it.)_')
CUT = ('_(cut off here — this reply stopped when the page reloaded. '
       'Ask again if you need the rest.)_')


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Scan code, never prose — the comments written with this fix quote the
    forged assistant turn verbatim, sentence and all."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
    """Body by brace matching, so the REAL implementation runs in the harness
    rather than being pattern-matched from a distance."""
    i = src.index(opener)
    parens, j = 0, None
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
        raise SystemExit('no body brace lifting ' + opener)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise SystemExit('unbalanced braces lifting ' + opener)


def stmt_lift(src, opener):
    """A `const x = …;` declaration, by paren/brace balance."""
    i = src.index(opener)
    depth = 0
    for k in range(i, len(src)):
        c = src[k]
        if c in '({[':
            depth += 1
        elif c in ')}]':
            depth -= 1
        elif c == ';' and depth == 0:
            return src[i:k + 1]
    raise SystemExit('no statement end lifting ' + opener)


print("the reload note is not the coworker's own words")

FLOOR_SRC = strip_comments(FLOOR.read_text(encoding='utf-8'))
STORE_SRC = strip_comments(STORAGE.read_text(encoding='utf-8'))
RT_SRC = strip_comments(RUNTIME.read_text(encoding='utf-8'))

# ── The premise: text IS what becomes the prompt. ────────────────────────
check('chatToMessages is still the one place stored chat becomes prompt, and '
      'it still builds the turn out of the message text',
      re.search(r'const text = stripOfficeVoice\(m\.text\);', RT_SRC) is not None
      and re.search(r"\{ role: 'assistant', content: text \}", RT_SRC) is not None)
check('an empty body is still what keeps a placeholder out of the envelope '
      '— the behaviour #348 spent by writing into text',
      re.search(r'if \(text\)', RT_SRC) is not None)

# ── One home for the sentences. ─────────────────────────────────────────
check('both reload sentences are declared in app/floor.jsx, beside the other '
      'office-voice templates',
      re.search(r'const CHAT_CUT_NOTE\b', FLOOR_SRC) is not None
      and re.search(r'const CHAT_GONE_NOTE\b', FLOOR_SRC) is not None)
check('...and app/storage.jsx imports them rather than spelling them again, '
      'so the bubble and the strip cannot drift apart',
      re.search(r'import \{[^}]*CHAT_CUT_NOTE[^}]*CHAT_GONE_NOTE[^}]*\} '
                r"from '\./floor\.jsx'", STORE_SRC) is not None)
check('chatOnLoad no longer carries its own copy of either sentence',
      'this reply stopped when the page reloaded' not in STORE_SRC,
      '— a second copy is a second thing to forget to strip')
check('the office-voice matcher really knows about them (they are alternatives '
      'in the regex, not a separate best-effort pass)',
      re.search(r'CHAT_CUT_NOTE, CHAT_GONE_NOTE\]', FLOOR_SRC) is not None
      and re.search(r'notes', FLOOR_SRC) is not None)

# ── Run the real chain. ─────────────────────────────────────────────────
if not shutil.which('node'):
    print('  SKIP  node not on PATH — the envelope checks need it')
else:
    js = FLOOR_SRC.replace('export {', 'const _exports_unused = {') + '\n'
    js += brace_lift(RT_SRC, 'function chatToMessages(') + '\n'
    js += stmt_lift(STORE_SRC, 'const capChatFair =') + '\n'
    js += stmt_lift(STORE_SRC, 'const persistableChat =') + '\n'
    js += stmt_lift(STORE_SRC, 'const chatOnLoad =') + '\n'
    js += r'''
/* A reply that was mid-stream when the page died. The dispatcher seeds a
   placeholder and useStored's 300ms debounce is re-armed by every token
   frame, so `text: ''` really is what usually reaches disk. */
const LIVE  = [{ id: 'u1', from: 'user',  name: 'You', text: 'summarise the deck' },
               { id: 'a1', from: 'agent', name: 'Kip · Deep Research', text: '', streaming: true }];
/* …and the rarer one, where some tokens had landed first. */
const LIVE_P = [{ id: 'u2', from: 'user',  name: 'You', text: 'and the risks?' },
                { id: 'a2', from: 'agent', name: 'Kip · Deep Research', text: 'Three risks: ', streaming: true }];
/* A reply that FINISHED. Nothing about it may change. */
const DONE  = [{ id: 'u3', from: 'user',  name: 'You', text: 'ship it?' },
               { id: 'a3', from: 'agent', name: 'Kip · Deep Research', text: 'Yes — merged.', streaming: false }];

const loaded  = chatOnLoad(persistableChat(LIVE));
const loadedP = chatOnLoad(persistableChat(LIVE_P));
const loadedD = chatOnLoad(persistableChat(DONE));
/* Interrupted, reloaded, written, reloaded again. */
const twice   = chatOnLoad(persistableChat(chatOnLoad(persistableChat(LIVE))));

console.log(JSON.stringify({
  screenEmpty:   loaded[1].text,
  screenPartial: loadedP[1].text,
  screenTwice:   twice[1].text,
  promptEmpty:   chatToMessages(loaded,  { selfName: 'Kip' }),
  promptPartial: chatToMessages(loadedP, { selfName: 'Kip' }),
  promptTwice:   chatToMessages(twice,   { selfName: 'Kip' }),
  promptDone:    chatToMessages(loadedD, { selfName: 'Kip' }),
  /* The reader is not always the coworker: the chief of staff builds the
     same envelope with no selfName, and the note must not survive there
     as a labelled peer line either. */
  promptForCeo:  chatToMessages(loaded),
  /* The strip must not be a blanket "drop anything parenthesised": a
     coworker who really writes an italic aside keeps it. */
  keepsRealAside: stripOfficeVoice('Done.\n\n_(the deck is in the Library)_'),
  /* And the visit templates it already knew still go. */
  stillStripsVisit: stripOfficeVoice('📡 Read("a.md") →\nthe body'),
}, null, 2));
'''
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=90)
    if p.returncode != 0:
        check('the envelope harness runs on source lifted from the app',
              False, p.stderr.strip()[:600])
    else:
        R = json.loads(p.stdout)
        asst = lambda ms: [m['content'] for m in ms if m['role'] == 'assistant']
        allc = lambda ms: '\n'.join(m['content'] for m in ms)

        # ── The screen: #348's whole point, unchanged. ──────────────────
        check('the bubble still says the reply was cut off when nothing had '
              'streamed — #348 is not undone', R['screenEmpty'] == GONE,
              R['screenEmpty'])
        check('...and still says it under the tokens that did arrive',
              R['screenPartial'] == 'Three risks: \n\n' + CUT,
              R['screenPartial'])
        check('...and says it exactly once after a second reload',
              R['screenTwice'] == GONE, R['screenTwice'])

        # ── The prompt: the defect. ────────────────────────────────────
        check('the brain is NOT told the coworker said "nothing came back — '
              'ask again"', GONE not in allc(R['promptEmpty']),
              R['promptEmpty'])
        check('...and an interrupted reply with nothing in it contributes no '
              'turn at all, exactly as it did before #348',
              R['promptEmpty'] == [{'role': 'user', 'content': 'summarise the deck'}],
              R['promptEmpty'])
        check('the brain is NOT told the coworker narrated his own '
              'interruption mid-answer', CUT not in allc(R['promptPartial']),
              R['promptPartial'])
        check('...and the tokens that really arrived survive — a body is not '
              'a template', asst(R['promptPartial']) == ['Three risks:'],
              R['promptPartial'])
        check('a second reload does not smuggle it in either',
              GONE not in allc(R['promptTwice']), R['promptTwice'])
        check('the chief of staff\'s envelope is clean too — the note must '
              'not survive as a labelled peer line',
              GONE not in allc(R['promptForCeo']), R['promptForCeo'])

        # ── Nothing else moved. ────────────────────────────────────────
        check('a reply that FINISHED still reaches the brain whole',
              asst(R['promptDone']) == ['Yes — merged.'], R['promptDone'])
        check('a coworker\'s own italic aside is not collateral — this is a '
              'named sentence, not a blanket rule',
              R['keepsRealAside'] == 'Done.\n\n_(the deck is in the Library)_',
              R['keepsRealAside'])
        check('the visit templates stripOfficeVoice already knew still go',
              R['stillStripsVisit'] == 'the body', R['stillStripsVisit'])

print()
if FAILS:
    print('FAILED (%d): %s' % (len(FAILS), '; '.join(FAILS)))
    sys.exit(1)
print('all ok')
