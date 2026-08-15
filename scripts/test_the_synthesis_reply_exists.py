#!/usr/bin/env python3
"""The combined answer after a two-way fan-out had never once been produced.

When the chief of staff DMs two specialists in parallel, a synthesis pass
is supposed to fold their replies into one tight answer for the boss. It
was dead twice over, and each half alone was enough:

1. It read the chat through `setChat(prev => { synthChat = prev; return
   prev; })`. React runs that updater on a later tick than the line that
   reads the captured variable. Measured live on 2026-08-15 with both
   specialists back and `targets=2`: `immediate=0, afterTick=20`. So
   `replies` was empty every time, `replies.length >= 2` was false every
   time, and the block returned without doing anything.

2. Even fed a full chat, it called `ceoStream(synthPrompt, …, { chat })`
   — and ceoStream reads `prompt` ONLY when `chat` is absent. The
   instruction the whole block is built around was discarded by the
   callee. Confirmed on the brain's request log: with (1) fixed and (2)
   not, a synthesis turn was sent and the string "Now synthesize" did not
   appear in it. The office replayed the conversation instead.

The same idiom 250 lines up DOES read back, because React evaluates the
first updater of a fresh event eagerly — which is exactly why nobody
looked at it twice.

Turning the feature on brought its own risk, so the guards came with it:
the synthesis prompt is the ONLY prompt in the office that asks for a
file path ("cite vault paths if any were saved"), and `unfiledPath` is
the guard for a named path nothing wrote. Shipping the feature without it
would have shipped, on the first working run, precisely the defect the
guard exists to catch.

Verified live, both sides, on the run this suite was written from:

    Both are back. Vera has the vendor list, Kip has the arithmetic, and
    they agree on the shape. I've saved the combined write-up to
    Reports/vendor-margin.md for you.

    _(`Reports/vendor-margin.md` is named above, but nothing was written
    to the cabinet on this run, so that file is not there.)_

...and a synthesis reply claiming no file at all produced no note.

Run: python3 scripts/test_the_synthesis_reply_exists.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_artifacts import pure_source  # noqa: E402
CHAT = (ROOT / 'ui' / 'chat.jsx').read_text(encoding='utf-8')
RUNTIME = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Scan code, never prose — the comments written with this fix quote
    both broken call shapes in full."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
    """Body by brace matching — bounded by structure, not by proximity."""
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
    print('the synthesis reply exists')
    chat = strip_comments(CHAT)
    code = strip_comments(RUNTIME)

    # ── 1. the read that made the feature dead ──────────────────────────
    # A ref is written on every render, so there is no tick in which it is
    # behind. The capture idiom is the defect itself and must not come
    # back on this path — matched as a whole statement so that the send
    # path's own (working, differently-shaped) capture is not caught.
    check('the panel keeps a ref to the live chat',
          re.search(r'const chatRef = useRef\(chat\);\s*\n\s*chatRef\.current = chat;', chat),
          '— the `chat` prop is captured per render, and this handler has '
          'awaited two dispatches by the time it reads it')
    synth = chat[chat.index('if (targets.length >= 2) {'):]
    synth = synth[:synth.index('\n          }\n')]
    check('...and the synthesis pass reads it',
          'const synthChat = chatRef.current;' in synth,
          [synth[:200]])
    check('...not a setChat capture, which is read a tick before it is written',
          not re.search(r'setChat\(prev => \{\s*synthChat = prev;', synth),
          '— measured: immediate=0, afterTick=20')

    # ── 2. the call that made the prompt undeliverable ──────────────────
    # ceoStream's own contract: `prompt` is read only when `chat` is
    # absent. Passing both is silent — no error, no log, no reply.
    ceo_head = code[code.index('async function ceoStream('):]
    ceo_head = ceo_head[:ceo_head.index('const reg = await registrySnippet();')]
    check('ceoStream still ignores prompt when chat is given',
          re.search(r'const messages = chat\s*\n\s*\? chatToMessages\(chat', ceo_head),
          [ceo_head, '— this is the CONTRACT, not the bug; the bug was a '
           'caller that passed both. If this ever changes, the send path '
           'starts sending the boss\'s turn twice'])
    synth_call = re.search(r'await HQ\.ceoStream\(synthPrompt, synthFlush, \{([^}]*)\}', synth)
    check('the synthesis passes its prompt where ceoStream reads it',
          synth_call and 'chat:' not in synth_call.group(1),
          [synth_call.group(1) if synth_call else None,
           '— with `chat:` here the instruction is discarded and the office '
           'replays the conversation instead of summarising it'])
    check('...and the prompt is self-contained, since it travels alone now',
          'The boss asked:' in synth and 'Here are their replies' in synth,
          '— it restates the question and quotes both replies in full')

    # ── 3. what the feature must not do once it is finally running ──────
    # This prompt is the only one in the office that asks for a file path.
    check('the synthesis prompt still asks for vault paths',
          'cite vault paths if any were saved' in synth,
          '— which is exactly why the guard below is not optional')
    check('...so the synthesis reply runs the honesty guards',
          re.search(r'if \(HQ\.honestyNotes && synthFlush\.note\) \{', synth)
          and 'HQ.honestyNotes(rawSynth, {' in synth,
          '— unfiledPath is the guard for a named path nothing wrote')
    check('...with every note actually emitted',
          re.search(r'\)\) synthFlush\.note\(n\);', synth), synth[-300:])
    check('...reading the raw stream, not the cleaned bubble',
          'const rawSynth = synthFlush.raw ? synthFlush.raw() : ' in synth,
          '— the strip above has already removed the markers')
    check('...and telling the guards the fan-out really happened',
          'delivered: targets.length' in synth,
          '— the DMs on this run DID go out; a hardcoded 0 would accuse the '
          'office of faking the very dispatch the boss just watched')
    check('the synthesis collects its visits, like the other four sites',
          re.search(r'if \(ev\.echo\) synthVisits\.push\(\{[^}]*failed: !!ev\.failed', synth),
          '— "if you add a fourth site, carry it" (app.jsx); this is the fifth')

    # ── 4. the count. Both CEO reply paths, not just the one that broke ──
    # #69 wired the guards to the send path and this ticket found a second
    # ceoStream caller in the same file with none. The census is the check.
    # `guarded` counts the GUARD, not the call. Fire-testing caught the
    # weaker form: an arm that changed the condition to `false && …` left
    # `HQ.honestyNotes(` sitting in the file and the census green, which is
    # the same blind spot one level up — a call nothing reaches is a call
    # that does not run.
    callers = len(re.findall(r'HQ\.ceoStream\(', chat))
    guarded = len(re.findall(r'if \(HQ\.honestyNotes && \w+\.note\) \{', chat))
    check('every ceoStream caller in the panel is guarded',
          callers == guarded == 2,
          [callers, guarded, '— a third caller added without a guard is the '
           'shape of #69 and #70 both; this is the line that notices'])

    # ── 5. the guard the prompt makes load-bearing, actually run ────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the guard check needs it')
    else:
        # `unfiledPath` reaches into app/artifacts.jsx for its decision —
        # what the reply NAMED, minus what the run actually touched.
        # Lifting the guard without that ran, and threw, which is the
        # honest failure; a stub would have made the harness agree with
        # itself instead of with the shipped code.
        #
        # The whole pure half of artifacts.jsx comes in, rather than the two
        # constants and two functions this used to name. #82 replaced those
        # two functions with one shared `unwrittenPaths`, and a lift that
        # knew only the old names died on a ReferenceError instead of
        # reporting — the same enumerated-list rot as #79 and #81. The
        # dependency is "whatever the guard needs from that file", so lift
        # that instead of guessing at it.
        js = pure_source() + '\n'
        js += brace_lift(code, 'function unfiledPath(') + '\n'
        js += r'''
// The reproduced synthesis reply, byte for byte off the live run.
const NAMED = "Both are back. Vera has the vendor list, Kip has the arithmetic, "
  + "and they agree on the shape. I've saved the combined write-up to "
  + "Reports/vendor-margin.md for you.";
// The same reply with nothing claimed — the false-alarm side, also live.
const CLEAN = "Both are back. Vera has the vendor list and Kip has the arithmetic; "
  + "they agree on the shape and neither has written anything up yet. Want me to "
  + "have one of them file it?";
const WROTE = [{ name: 'vault_new', arg: 'Reports/vendor-margin.md', echo: 'x' }];
const R = {
  // visits: [] — the synthesis ran no tools, so nothing was filed.
  caught:   unfiledPath(NAMED, []),
  // ...and a reply that claims no file is left alone.
  quiet:    unfiledPath(CLEAN, []),
  // ...as is one whose claimed file really was written this run.
  filed:    unfiledPath(NAMED, WROTE),
  // No visits array at all means "unknowable", which stays silent — the
  // shape the synthesis had before it collected any.
  blind:    unfiledPath(NAMED, undefined),
};
console.log(JSON.stringify(R));
'''
        p = subprocess.run(['node', '--input-type=module', '-e', js],
                           cwd=ROOT, capture_output=True, text=True)
        if p.returncode != 0:
            check('the guard harness runs', False, p.stderr.strip()[:400])
        else:
            R = json.loads(p.stdout)
            check('a synthesised file claim with no write is caught',
                  R['caught'] and 'vendor-margin.md' in R['caught'],
                  [R['caught'], '— the reply the boss saw on the first run '
                   'this feature ever completed'])
            check('...and a synthesis claiming nothing is left alone',
                  R['quiet'] is None,
                  [R['quiet'], '— a false alarm calls an honest office a liar'])
            check('...as is one whose file really was filed',
                  R['filed'] is None, R['filed'])
            check('...and no visits at all stays silent rather than guessing',
                  R['blind'] is None,
                  [R['blind'], '— unknowable is not the same as false'])

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
