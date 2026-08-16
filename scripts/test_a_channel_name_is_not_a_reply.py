#!/usr/bin/env python3
"""A coworker's entire reply was the word "final".

Measured on screen, office 9262, 2026-08-15, gpt-oss-20b through LM
Studio. Mika's bubble, in full:

    MIKA · BUILDER
    final

`cleanHarmony` removes the analysis and commentary blocks whole — content
and all — and keeps the `final` channel's content, which is the one the
boss is meant to read. To do that it matched the final header exactly:
the literal name, and a closing `<|message|>`. A stream that stopped
before `<|message|>` arrived matched nothing, fell through to the
belt-and-suspenders `<|…|>` catch-all, and that removes the TAG while
leaving the channel NAME behind as prose.

The reason this is not a rare edge is `throttleTokens`: it re-runs
cleanHarmony over the ACCUMULATED buffer on every animation frame, so
every prefix of the model's emission is a frame that goes on screen. The
header arrives in one frame and `<|message|>` in a later one, so the word
"final" is rendered as the coworker's reply on the way past — every single
time a harmony model answers. It is only *stuck* there when the stream
also ends around that point, which is what happened here.

So the sweep below is not arbitrary truncation: it is every frame the boss
can see. The fix strips the channel header generically — name optional and
unenumerated (#73's lesson: a list of names is a list that silently stops
being complete), `<|message|>` optional, since that is the token that was
missing. A truncated stream now cleans to empty, which is what it is, and
an empty reply already has an honest line of its own.

Run: python3 scripts/test_a_channel_name_is_not_a_reply.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_RAW = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """The comment written with this fix quotes the leaked word and the
    header it came from."""
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
    print('a channel name is not a reply')
    code = strip_comments(RUNTIME_RAW)
    body = brace_lift(code, 'function cleanHarmony(')

    # ── 1. the two things that made the leak possible ───────────────────
    #
    # There are two `<|channel|>` patterns in here and they do opposite
    # jobs: one DROPS a block whole, one strips a header and keeps what
    # follows. The first draft of this check took whichever came first in
    # the file and read the wrong one. They are told apart by what they
    # are for, not by where they sit.
    chan = re.findall(r'<\\\|channel\\\|>[^\n]*', body)
    check('there are exactly two channel patterns to tell apart',
          len(chan) == 2, chan)
    drop = [c for c in chan if '(?!final' in c]
    hdr = [c for c in chan if '(?!final' not in c]
    check('one drops every block that is not the final channel',
          len(drop) == 1,
          [chan, '— naming the channels it knew left an unknown one\'s '
           'content welded onto the front of the answer'])
    check('the other matches a header whatever the channel is called',
          len(hdr) == 1 and 'final' not in hdr[0],
          [hdr, '— the header strip named one channel, so a header naming '
           'any other fell through to the catch-all, which leaves the name'])
    check('...and whether or not <|message|> arrived yet',
          len(hdr) == 1 and '(?:<\\|message\\|>)?' in hdr[0],
          [hdr, '— requiring <|message|> is requiring the token that was '
           'missing'])

    # ── 2. the frames the boss actually sees ────────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the frame sweep needs it')
        return 1 if FAILS else 0

    # cleanHarmony's dependency chain, lifted by name — see the note on
    # reasoningPatterns in hq-runtime.jsx for why these are functions.
    js = (brace_lift(code, 'function reasoningPatterns(') + '\n'
          + brace_lift(code, 'function stripReasoning(') + '\n'
          + brace_lift(code, 'function maskReasoning(') + '\n'
          + body) + r'''
// Emissions in the shape gpt-oss actually produces. `throttleTokens` cleans
// the accumulated buffer once per frame, so EVERY prefix of each of these
// is rendered in the coworker's bubble on the way past.
const STREAMS = {
  plain:   '<|channel|>final<|message|>Here is your landing page.<|return|>',
  thought: '<|channel|>analysis<|message|>The boss wants a page. I should '
         + 'not say this part out loud.<|end|>'
         + '<|channel|>final<|message|>Here is your landing page.<|return|>',
  tool:    '<|channel|>commentary to=FILE_WRITE <|constrain|>json<|message|>'
         + '{"path":"site/index.html","content":"<h1>Lemonade</h1>"}<|call|>'
         + '<|channel|>final<|message|>Saved it.<|return|>',
  // A channel this office has never heard of. The two block regexes name
  // analysis and commentary; nothing names this one.
  unknown: '<|channel|>critic<|message|>Too terse.<|end|>'
         + '<|channel|>final<|message|>Rewritten.<|return|>',
  // A framing token this office has no name for. Only the catch-all at the
  // bottom of cleanHarmony stands between it and the boss — without this
  // stream nothing here exercised that line, and removing it altogether
  // left the suite green.
  oddTag:  '<|channel|>final<|message|>Done<|refusal|> and dusted.<|return|>',
};

// Anything that is framing rather than words. A frame whose whole visible
// text is one of these is the reported defect.
const NAMES = ['final', 'analysis', 'commentary', 'critic', 'assistant',
               'channel', 'message', 'constrain', 'end', 'call', 'return',
               'to', 'json'];

const leaks = [];        // a frame whose entire text is a piece of framing
const leadIns = [];      // a frame that OPENS with one, then real prose
const tags = [];         // a frame still showing a raw <|…|> tag
const secrets = [];      // a frame showing chain of thought

/* Frames arrive on token boundaries, not character ones. `<|channel|>` is
   a single token in this model's vocabulary and cannot be delivered in
   halves; ordinary text arrives a word or so at a time. Slicing per
   character instead reported `<|`, `<|c`, `<|cha` … as frames the boss
   sees, which is not a thing the transport can produce — a check has to
   model the real boundary or it is measuring its own fiction. The
   reported defect survives this stricter model intact: `<|channel|>` is
   one token, `final` is the next, and the frame between them is the word
   on its own. */
const atoms = s => s.match(/<\|[^|]*\|>|[^<\s]+\s*|\s+/g) || [];

for (const [name, stream] of Object.entries(STREAMS)) {
  const parts = atoms(stream);
  let acc = '';
  for (const part of parts) {
    acc += part;
    const n = acc.length;
    const shown = cleanHarmony(acc);
    if (!shown) continue;
    const t = String(shown).trim();
    if (NAMES.includes(t)) leaks.push([name, n, t]);
    const first = t.split(/[\s<{]/)[0];
    if (NAMES.includes(first) && t !== first) leadIns.push([name, n, t.slice(0, 48)]);
    if (t.includes('<|')) tags.push([name, n, t.slice(0, 48)]);
    if (t.includes('not say this part out loud')) secrets.push([name, n, t.slice(0, 48)]);
  }
}

const clean = s => cleanHarmony(s);
console.log(JSON.stringify({
  leaks: leaks.slice(0, 8),
  leakCount: leaks.length,
  leadIns: leadIns.slice(0, 8),
  tags: tags.slice(0, 8),
  secrets: secrets.slice(0, 4),
  // The measured string, on its own.
  measured: clean('<|channel|>final'),
  // The completed streams must still say what they say.
  finished: Object.fromEntries(
    Object.entries(STREAMS).map(([k, v]) => [k, clean(v)])),
  // A header whose content never got a message marker is still content.
  noMarker: clean('<|channel|>final The page is at site/index.html.'),
  // Prose is prose. Nothing here matches without a literal <|channel|>.
  prose: clean('This is my final answer.'),
  plainProse: clean('Hello, boss.'),
  // The word arriving as ordinary text, mid-sentence, must survive.
  midSentence: clean('<|channel|>final<|message|>My final answer is yes.<|return|>'),
}));
'''
    p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
    if p.returncode != 0:
        check('the frame sweep runs', False, p.stderr.strip()[:500])
    else:
        R = json.loads(p.stdout)

        check('no frame the boss sees is just a piece of framing',
              not R['leaks'],
              [R['leaks'], '%d frame(s)' % R['leakCount'],
               '— "final", alone, in a coworker\'s bubble'])
        check('...and none opens with one either',
              not R['leadIns'],
              [R['leadIns'], '— the same header, one frame later, with the '
               'reply growing out of it'])
        check('no frame shows a raw harmony tag',
              not R['tags'], R['tags'])
        check('no frame shows the model thinking',
              not R['secrets'],
              [R['secrets'], '— the analysis channel is not for the boss'])

        check('the measured reply is now empty, not a word',
              R['measured'] == '',
              [R['measured'], '— empty is what a truncated stream IS, and an '
               'empty reply already has an honest line of its own'])

        fin = R['finished']
        check('a finished stream still says what it said',
              fin['plain'] == 'Here is your landing page.'
              and fin['thought'] == 'Here is your landing page.'
              and fin['tool'] == 'Saved it.'
              and fin['unknown'] == 'Rewritten.'
              and fin['oddTag'] == 'Done and dusted.',
              fin)
        check('a header with no message marker keeps its content',
              R['noMarker'] == 'The page is at site/index.html.',
              R['noMarker'])
        check('the word "final" in ordinary prose is untouched',
              R['prose'] == 'This is my final answer.'
              and R['midSentence'] == 'My final answer is yes.',
              [R['prose'], R['midSentence'],
               '— nothing matches without a literal <|channel|> in front'])
        check('text with no harmony in it passes through',
              R['plainProse'] == 'Hello, boss.', R['plainProse'])

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
