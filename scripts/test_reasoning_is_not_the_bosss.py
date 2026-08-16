#!/usr/bin/env python3
"""A coworker's private reasoning, shown to the boss and acted on.

Measured 2026-08-16, office 9280, canned brain on the LM Studio door. The
brain replied the way deepseek-r1 and qwen3 reply through Ollama — chain of
thought inline in `content`, wrapped in `<think>`:

    <think>
    … I could run [VAULT_READ: Reports/q3-summary.md] to look — but that
    file almost certainly does not exist yet, and a failed read would just
    burn a hop for nothing. Better to simply ask the boss where the numbers
    live.
    </think>

    I don't have last quarter's numbers to hand — where should I look?

Three things landed in the boss's thread. The tags and the whole
deliberation, verbatim. The VAULT_READ the model had just talked ITSELF out
of, executed for real, with its snag card underneath. And — because the tool
parser had already eaten the marker out of the middle of the thought — the
mutilated sentence "I could run  to look". The office deleted the evidence
of what it was about to do, and then did it.

None of this is new ground; it is the same rule, missed on a third wire
format. `claude-client.jsx` routes `delta.reasoning_content` away from the
answer and drops it, and its note ends "One concept, two wire formats, and
only one of them was handled." `cleanHarmony` removes harmony's analysis
channel whole, stating the rule outright: "chain of thought and tool calls
are not for the boss". `<think>` was matched by nothing anywhere in the
tree — `grep -rn '<think' --include=*.jsx` returned nothing at all.

What makes it a product defect rather than a missing feature is that the
format is not a property of the model. The SAME deepseek-r1 splits its
thinking into `reasoning_content` through one local runtime and inlines
`<think>` through another, so the identical thought was silently dropped or
pasted into the bubble depending on which daemon the boss happened to have
running. Same brain, same thought, opposite treatment — on a product whose
whole premise is that the brain is swappable.

WHAT THIS PINS

  · display — reasoning never reaches the boss, on the live streaming path
    as well as the final one, closed / unclosed / opener-less alike
  · execution — a marker inside reasoning is not a call, at detectToolCall
    and at the four extractors that answer "did they actually do this"
  · the equal-length invariant — maskReasoning blanks in place, because
    detectToolCall hands back `raw` and upToToolCall finds it by index in
    the ORIGINAL buffer. Deleting bytes there cuts the reply in the wrong
    place, and the failure is silent
  · parity — night_runner.py carries the same tag list and masks at its own
    three seams, the way test_night_grammar.py pins _TOOL_RE_SRC. A comment
    claiming parity is not parity

Run: python3 scripts/test_reasoning_is_not_the_bosss.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import night_runner as nr  # noqa: E402

RUNTIME_RAW = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
NIGHT_RAW = (ROOT / 'night_runner.py').read_text(encoding='utf-8')
CLIENT_RAW = (ROOT / 'claude-client.jsx').read_text(encoding='utf-8')
FAILS = []

# The reply that was actually measured. Kept whole rather than trimmed to
# the interesting line: the defect needed a marker sitting mid-sentence
# inside prose inside a block, and a shortened fixture stops reproducing it.
MEASURED = (
    "<think>\n"
    "The boss is asking me to summarise last quarter's numbers. Before I "
    "answer I\nshould check whether we already have something on file. I "
    "could run\n[VAULT_READ: Reports/q3-summary.md] to look — but that file "
    "almost certainly\ndoes not exist yet, and a failed read would just burn "
    "a hop for nothing.\nBetter to simply ask the boss where the numbers "
    "live.\n</think>\n\n"
    "I don't have last quarter's numbers to hand — where should I look for "
    "them?"
)


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """The comments here quote the measured reply and the tag list, so a
    check reading source text would match its own documentation."""
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


def line_lift(src, needle):
    """The const declaration `needle` starts, to its terminating newline."""
    i = src.index(needle)
    return src[i:src.index('\n', i)]


def main():
    print("a coworker's private reasoning is not the boss's")
    code = strip_comments(RUNTIME_RAW)

    # ── 1. the seams: where the rule is applied, and where it is not ─────
    #
    # Source-text checks, and they are the weaker half — §5's point is that
    # a call site can be present and wrong. They earn their place by
    # pinning the CHOKEPOINT choice: the fix works at all ten final-text
    # recipes and on the live stream only because it sits inside
    # cleanHarmony, which throttleTokens.flush() runs per animation frame.
    # Move it to a sibling function and every one of those inherits
    # nothing, silently.
    ch = brace_lift(code, 'function cleanHarmony(')
    check('cleanHarmony strips reasoning before anything else',
          re.search(r'^\s*const t = stripReasoning\(text\);', ch, re.M),
          '— the chokepoint every reply passes, live and final')
    check('...and its early return can no longer skip the strip',
          'indexOf(\'<|\') < 0) return t' in ch
          and 'if (!text || text.indexOf(\'<|\') < 0) return text' not in ch,
          '— the old guard returned before reasoning was ever looked at')
    check('throttleTokens still paints through cleanHarmony',
          'cleanHarmony(raw) + suffix' in code,
          '— this is what makes the live bubble inherit the fix')
    # Eight suites lift cleanHarmony out of this file and run it under node.
    # Its whole dependency chain has to be liftable BY NAME, or those
    # harnesses die with a ReferenceError instead of a readable failure —
    # which is exactly what happened when the patterns were five bare
    # module-level consts. Nothing but functions below cleanHarmony's call
    # graph, and one tuple entry per name.
    for dep in ('reasoningPatterns', 'stripReasoning', 'maskReasoning'):
        check('%s is liftable as a plain function' % dep,
              re.search(r'^function %s\(' % dep, code, re.M),
              '— a bare const dependency breaks every suite that lifts '
              'cleanHarmony')

    dt = brace_lift(code, 'function detectToolCall(')
    check('detectToolCall scans masked text, not raw',
          re.search(r'const scan = maskReasoning\(text\);', dt))
    check('...and every detector inside it reads the same scan',
          not re.search(r'\b(detectJsonToolCall|extractAllDMs|'
                        r'extractHarmonyToolCalls)\(text\b', dt),
          re.findall(r'\w+\(text\b', dt))

    for fn, opener in (('extractApproval', 'function extractApproval('),
                       ('extractAcks', 'function extractAcks('),
                       ('extractAllDMs', 'function extractAllDMs('),
                       ('extractHandoff', 'function extractHandoff('),
                       ('honestyNotes', 'function honestyNotes(')):
        body = brace_lift(code, opener)
        check('%s asks the masked buffer whether it happened' % fn,
              'maskReasoning(' in body,
              '— a marker written while thinking was never sent')

    # A helper the runtime defines but never puts on the HQ surface is
    # invisible to every other module, and the failure is a runtime
    # TypeError deep in a reply path, not a build error. `export { HQ }` is
    # the module's ONLY export statement — the surface is the object
    # literal, which is what a reader has to check. The first draft of this
    # check read `^export \{`, matched `export { HQ };`, and reported both
    # helpers missing when both were correctly placed.
    surface = brace_lift(code, 'const HQ = {')
    names = set(re.findall(r'[\w$]+', surface))
    check('both helpers are on the HQ surface',
          {'stripReasoning', 'maskReasoning'} <= names,
          sorted({'stripReasoning', 'maskReasoning'} - names))

    # ── 2. the premise that made this a defect, still true ───────────────
    #
    # If claude-client ever starts SHOWING reasoning instead of dropping it,
    # deleting it here becomes the inconsistency rather than the fix. The
    # rule is "all three wire formats get the same treatment", not "strip".
    check('the office still drops reasoning it is handed out-of-band',
          'onReasoning' in CLIENT_RAW
          and not re.search(r'onReasoning\s*[:=]\s*(?!null)\w', code),
          '— if the office starts SHOWING thinking, this suite should fail '
          'and <think> should be routed there instead of removed')

    # ── 3. what actually happens to the measured reply ───────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the behaviour half needs it')
        return 1 if FAILS else 0

    lifted = '\n'.join([
        line_lift(code, 'const REASONING_TAGS'),
        brace_lift(code, 'function reasoningPatterns('),
        brace_lift(code, 'function stripReasoning('),
        brace_lift(code, 'function maskReasoning('),
        brace_lift(code, 'function cleanHarmony('),
    ])

    # A stand-in for the one tool the measured reply reaches for. The real
    # TOOL_REGISTRY entry drags in the whole runtime; the REGEX is the part
    # detectToolCall uses, and it is copied from the registry by the check
    # below rather than retyped here.
    vault_read_re = re.search(
        r'vault_read: \{[\s\S]*?re: (/[^\n]+?/i),', code).group(1)

    driver = lifted + """
const TOOLS = [{ name: 'VAULT_READ', re: %s }];
function detectBracket(text) {
  const scan = maskReasoning(text);
  for (const t of TOOLS) {
    const m = String(scan).match(t.re);
    if (m) return { name: t.name, arg: m[1], raw: m[0] };
  }
  return null;
}
const MEASURED = %s;
const out = {};

out.shown        = cleanHarmony(MEASURED);
out.fired        = detectBracket(MEASURED);
out.plainUntouched = cleanHarmony('Just a normal reply. 2 < 3 and 5 > 4.');
out.plainIdentity  = cleanHarmony('no angle brackets here') === 'no angle brackets here';

// Every frame throttleTokens can paint: the accumulated buffer, one
// character longer each time. Any frame that shows a fragment of the
// thought is a frame the boss saw it in.
//
// DANGLE is the second half of "a fragment": a frame ending `…<thin` is a
// tag arriving, and it is just as much a leak as `…<think` is — but the
// prose needles above cannot see it, and the first draft of this sweep
// missed it. Derived here from the pinned tag string rather than read off
// the runtime's own `partial`, so the runtime dropping its derivation is
// something this sweep notices instead of agreeing with. At least one
// letter, matching the runtime's own choice: a lone trailing `<` is prose.
const DANGLE = new RegExp('<(?:' + REASONING_TAGS.split('|')
  .flatMap(t => Array.from({ length: t.length }, (_, i) => t.slice(0, i + 1)))
  .sort((a, b) => b.length - a.length).join('|') + ')$', 'i');
const leaked = [];
for (let i = 1; i <= MEASURED.length; i++) {
  const frame = cleanHarmony(MEASURED.slice(0, i));
  if (/summarise last quarter|burn a hop|<\\/?think/i.test(frame)
      || DANGLE.test(frame)) leaked.push(i);
}
out.leakFrames = leaked.length;
out.firstLeak  = leaked.length ? MEASURED.slice(0, leaked[0]).slice(-60) : '';

// A closer with no opener — some deepseek-r1 builds send the thought first
// and mark only where it ends.
out.orphan = cleanHarmony('Weighing the options here.</think>\\nThe answer is 4.');

// The orphan pattern above is greedy from the start of the buffer, so it is
// only safe while the closed-block pattern has already eaten every block
// that HAS a closer. Drop the closed pattern and this sandwich loses its
// first line — the boss's answer, silently shortened, with the thought
// removed correctly. Content loss, not a leak, which is why none of the
// checks above see it.
out.sandwich = cleanHarmony(
  'Sure — one moment.\\n<think>internal only</think>\\nThe answer is 4.');

// Reasoning that contains harmony scaffolding: removed as a block, not
// half-cleaned by the harmony pass.
out.nested = cleanHarmony('<think><|channel|>analysis<|message|>hm<|end|></think>Done.');

// The equal-length invariant. upToToolCall finds `raw` by index in the
// ORIGINAL buffer, so a mask that shifts offsets truncates the reply
// somewhere else entirely — silently.
const OUTSIDE = 'Let me look.\\n[VAULT_READ: notes/a.md]\\nand then some more.';
out.maskLen    = maskReasoning(MEASURED).length === MEASURED.length;
out.outsideHit = detectBracket(OUTSIDE);
out.rawIndex   = OUTSIDE.indexOf(detectBracket(OUTSIDE).raw);

// Equal length is not enough on its own. maskReasoning's docstring promises
// newlines survive, "so line-anchored patterns outside the block still see
// the same line structure" — and five readers in this file are built with
// the `m` flag. A blank that pads with spaces keeps the byte count and
// still collapses a multi-line thought into one very long line, which is a
// promise in a comment that nothing was checking. Per-line lengths pin it.
out.maskLines = maskReasoning(MEASURED).split('\\n').map(l => l.length);
out.origLines = MEASURED.split('\\n').map(l => l.length);

// A marker outside the block still fires when a block is also present.
const BOTH = '<think>maybe [VAULT_READ: no.md]</think>\\n[VAULT_READ: yes.md]';
out.bothHit = detectBracket(BOTH);

// A reply that was ONLY thinking cleans to empty — which is what it is,
// and the empty reply already has an honest line of its own.
out.thoughtOnly = cleanHarmony('<think>still working it out</think>');

console.log(JSON.stringify(out));
""" % (vault_read_re, json.dumps(MEASURED))

    p = subprocess.run(['node', '--input-type=module', '-e', driver],
                       capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        check('the runtime source runs under node', False,
              (p.stderr or p.stdout)[-700:])
        return 1
    out = json.loads(p.stdout.strip().splitlines()[-1])

    check('the deliberation never reaches the boss',
          'burn a hop' not in out['shown']
          and 'summarise last quarter' not in out['shown'],
          out['shown'][:160])
    check('...nor do the tags around it',
          '<think' not in out['shown'] and '</think' not in out['shown'],
          out['shown'][:160])
    check('...and the answer underneath survives whole',
          out['shown'] == "I don't have last quarter's numbers to hand — "
                          "where should I look for them?",
          repr(out['shown']))

    check('the tool it talked itself out of does not run',
          out['fired'] is None,
          out['fired'])

    # The live path, not just the filed one. This is the check that fails if
    # someone strips only closed blocks: mid-stream there is no closer yet,
    # so every frame from `<think>` onward would paint the monologue.
    check('no streaming frame shows the thought either',
          out['leakFrames'] == 0,
          '%d of %d frames leaked, first at …%s'
          % (out['leakFrames'], len(MEASURED), out['firstLeak']))

    check('a closer with no opener takes the thought with it',
          out['orphan'] == 'The answer is 4.', repr(out['orphan']))
    check('...and takes nothing that was written before the block',
          'Sure — one moment.' in out['sandwich']
          and 'The answer is 4.' in out['sandwich']
          and 'internal only' not in out['sandwich'],
          repr(out['sandwich']))
    check('reasoning wrapped around harmony goes whole',
          out['nested'] == 'Done.', repr(out['nested']))
    check('a reply that was only thinking cleans to empty',
          out['thoughtOnly'] == '', repr(out['thoughtOnly']))

    check('ordinary prose with angle brackets is untouched',
          out['plainUntouched'] == 'Just a normal reply. 2 < 3 and 5 > 4.'
          and out['plainIdentity'],
          repr(out['plainUntouched']))

    check('masking preserves length, so `raw` still indexes the original',
          out['maskLen'] and out['rawIndex'] == 13,
          [out['maskLen'], out['rawIndex']])
    check('...and preserves the line structure the docstring promises',
          out['maskLines'] == out['origLines'],
          [out['maskLines'], out['origLines']])
    check('a real call outside a block still fires',
          out['outsideHit'] and out['outsideHit']['arg'] == 'notes/a.md',
          out['outsideHit'])
    check('...including when a contemplated one sits above it',
          out['bothHit'] and out['bothHit']['arg'] == 'yes.md',
          out['bothHit'])

    # ── 4. the night shift carries the same rule ─────────────────────────
    #
    # Driven, not read: night_runner is importable, so there is no excuse
    # for checking it by grep. The browser tag list is compared to the
    # Python one as STRINGS, which is the drift this catches.
    js_tags = re.search(r"const REASONING_TAGS = '([^']+)'", code).group(1)
    check('both sides pin the same reasoning tags',
          js_tags == nr.REASONING_TAGS,
          [js_tags, nr.REASONING_TAGS])

    check('the night shift does not run what a brain only weighed',
          nr.find_first_tool(MEASURED) is None,
          nr.find_first_tool(MEASURED))
    check('...and still runs a real one',
          (nr.find_first_tool('[VAULT_READ: notes/a.md]') or [None])[0]
          == 'VAULT_READ')
    check('...with its span still indexing the original reply',
          nr.mask_reasoning(MEASURED) is not None
          and len(nr.mask_reasoning(MEASURED)) == len(MEASURED))

    # The morning report accuses a coworker of reaching for something it
    # cannot do. Weighing a tool and rejecting it is not reaching for it,
    # and an accusation is a bad thing to be wrong about at 8am.
    weighed = ('<think>I could [PUBLISH_SITE: site/] but it is not ready. '
               'I will not.</think>\nDrafted the page; it needs review.')
    check('a tool weighed and rejected is not reported as a reach',
          nr.find_unsupported_tool(weighed) is None,
          nr.find_unsupported_tool(weighed))
    check('...while a real reach still is',
          nr.find_unsupported_tool('Publishing now. [PUBLISH_SITE: site/]')
          == 'PUBLISH_SITE')
    check('the morning summary carries no monologue',
          'not ready' not in nr.strip_unsupported_markers(weighed)
          and 'review' in nr.strip_unsupported_markers(weighed),
          nr.strip_unsupported_markers(weighed))

    check('the night file names the suite that pins its parity',
          'test_reasoning_is_not_the_bosss.py' in NIGHT_RAW,
          '— the pointer test_night_grammar.py sets the precedent for')

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), '; '.join(FAILS)))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
