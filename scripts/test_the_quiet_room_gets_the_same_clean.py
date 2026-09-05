#!/usr/bin/env python3
"""Focus Mode's own `send()` never got either half of the "clean the CEO's
bubble" fix its sibling — the ordinary Direct-chat CEO path in ui/chat.jsx —
already carries.

`ceoStream` grants the CEO tools unconditionally in every caller: "CEO has
implicit web + vault — those are top-of-house concerns" (hq-runtime.jsx).
So the exact same brain FocusMode puts the boss alone with in "1:1 WITH
CAFRESOHQ ... quiet room · no distractions" can emit a [VAULT_NEW: ...] or
a dangling harmony commentary block exactly as it can in ordinary chat.
ui/chat.jsx already learned this the hard way and fixed it twice, and both
comments are still there to read:

  1. "Strip raw routing markers from the rendered CEO bubble ... Now the
     same visibleReply + cleanHarmony recipe as the other six paths, run
     unconditionally." — added a final
         HQ.cleanHarmony(HQ.visibleReply(String(m.text || ''), 'CafresoHQ'))
     pass after the stream finishes, because `HQ.throttleTokens`'s own live
     flush only ever runs `cleanHarmony` while streaming, never
     `visibleReply` — so a bracket marker like [VAULT_NEW: ...]...
     [/VAULT_NEW] survives every live repaint and is still sitting in the
     bubble when the stream ends.

  2. "Kill any rAF flush scheduled just before the abort — it would fire
     AFTER this rewrite and overwrite the '(stopped)' marker with the raw
     truncated text." — added `flush.cancel();` as the first line of the
     catch block, because `throttleTokens`'s pending frame renders straight
     from the unstripped `raw` buffer (see test_final_paint_wins.py), and
     nothing but `cancel()`/`flushNow()` stops a frame already queued from
     firing after a later write and clobbering it.

FocusMode (features.jsx) calls the exact same `HQ.ceoStream` /
`HQ.throttleTokens` pair from its own, separately-written `send()` and had
neither fix: no final visibleReply/cleanHarmony pass on success, and no
`flush.cancel()` in its catch. A vault write or search the CEO made in the
quiet room left raw bracket syntax in the one bubble the boss came here
"for no distractions" to read, and a stopped or failed 1:1 reply could be
silently overwritten by a stray queued frame back to the raw, truncated
stream, dropping the "…(stopped)"/error text the boss actually saw for a
moment.

Run: python3 scripts/test_the_quiet_room_gets_the_same_clean.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURES = ROOT / 'features.jsx'
CHAT = ROOT / 'ui' / 'chat.jsx'
RUNTIME = ROOT / 'hq-runtime.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, opener):
    """Body by brace matching, parens-aware so it also lifts arrow
    functions (`const send = async () => { ... }`), not just
    `function name(...) { ... }`."""
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


RECIPE = "HQ.cleanHarmony(HQ.visibleReply(String(m.text || ''), 'CafresoHQ'))"


def main():
    print("does Focus Mode's own CEO bubble get the same clean as the front door?")
    features = FEATURES.read_text(encoding='utf-8')
    chat = CHAT.read_text(encoding='utf-8')
    src = RUNTIME.read_text(encoding='utf-8')
    have_node = bool(shutil.which('node'))

    # `_send`, not `send`: `## 393` put a one-live-turn claim in front of
    # FocusMode's handler (a doubled Enter used to run a second real
    # ceoStream), so `send` is now a three-line wrapper and the turn itself
    # — including the clean recipe this test is about — lives in `_send`.
    send_body = brace_lift(features, 'const _send = async () => {')

    # ── 1. the sibling recipe actually exists in ui/chat.jsx (sentinel —
    #        if this ever moves or is rewritten, the whole comparison this
    #        test makes is moot, and it should say so rather than pass by
    #        accident) ─────────────────────────────────────────────────────
    check("ui/chat.jsx still runs the visibleReply+cleanHarmony recipe on "
          "the CEO's own bubble (the fix this ticket ports into Focus Mode)",
          RECIPE in chat,
          'ui/chat.jsx — if this string changed, re-check the recipe below '
          'still matches it')
    check("ui/chat.jsx's catch still cancels the throttle before rewriting "
          "the bubble (the second half of the same family)",
          re.search(r'catch \(err\) \{\s*/\*[\s\S]*?\*/\s*flush\.cancel\(\);',
                     chat) is not None,
          'ui/chat.jsx — the sibling fix for the race this ticket also ports')

    # ── 2. Focus Mode's send() now carries both ─────────────────────────
    check("Focus Mode's send() runs the exact same recipe on its own CEO "
          "bubble before it stops streaming",
          RECIPE in send_body,
          'features.jsx: FocusMode.send() — this is the measured defect: '
          'a coworker (well, the CEO) using [VAULT_NEW:...] or leaving a '
          'dangling harmony block left raw syntax in the quiet room')
    check("...gated to the CEO's own message only (never touches the "
          "boss's own bubble)",
          re.search(r"if \(m\.id !== ceoId\) return m;\s*\n\s*const cleaned = "
                     + re.escape(RECIPE), send_body) is not None,
          'features.jsx — the guard that keeps this from rewriting every '
          'message in the array')
    check("...and never blanks an otherwise-clean reply",
          "cleaned && cleaned !== m.text" in send_body,
          'features.jsx — same guard ui/chat.jsx uses so a reply with '
          'nothing to strip is left exactly as it was')
    check("Focus Mode's catch now cancels the throttle first, like the "
          "front door already does",
          re.search(r'catch \(err\) \{\s*/\*[\s\S]*?\*/\s*flush\.cancel\(\);',
                     send_body) is not None,
          'features.jsx: FocusMode.send() — without this, a frame queued '
          'just before a stop/error can fire after the rewrite and undo it')

    # ── 3. mechanism, run for real: the same visibleReply/cleanHarmony this
    #        repo already ships, fed the shape of reply a real vault write
    #        produces ───────────────────────────────────────────────────────
    if not have_node:
        print('  SKIP  node not on PATH — the mechanism checks need it')
    else:
        js = re.search(r'^const PLACEHOLDER_ARG\s*=.*?;$', src, re.M).group(0) + '\n'
        orphan = [c.group(0) for c in
                  re.finditer(r'^const ORPHAN_TAG_\w+\s*=[\s\S]*?;$', src, re.M)]
        if not orphan:
            raise SystemExit('could not find any ORPHAN_TAG_* const')
        js += '\n'.join(orphan) + '\n'
        for fn in ('reasoningPatterns', 'stripReasoning', 'maskReasoning',
                   'extractAcks', 'stripAcks', 'stripOrphanTags', 'stripBlocks',
                   'stripSelfLabel', 'extractAllDMs', 'isHandoffPlaceholder',
                   'placeholderRefusal', 'unsentBlocks', 'extractApproval',
                   'shownBody', 'visibleReply', 'cleanHarmony'):
            js += brace_lift(src, 'function ' + fn + '(') + '\n'

        # The measured shape: prose, a genuine closed VAULT_NEW block (the
        # CEO's vault_new tool really is offered unconditionally by
        # ceoStream), and prose again. VAULT_NEW is one of stripBlocks'
        # paired NAMES, so a well-formed block like this is exactly what a
        # real successful write looks like on the wire.
        js += r'''
const MEASURED = "Found it — saving the note now.\n\n" +
  "[VAULT_NEW: Notes/quarterly.md]\nQ3 revenue was $42,000, up 8% from Q2.\n[/VAULT_NEW]\n\n" +
  "Saved the numbers to your Library.";
console.log(JSON.stringify({
  harmonyOnly: cleanHarmony(MEASURED),
  fixedRecipe: cleanHarmony(visibleReply(MEASURED, 'CafresoHQ')),
  plainReplyUnchanged: cleanHarmony(visibleReply('Q3 was up 8%.', 'CafresoHQ')),
}));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=15)
        if p.returncode != 0:
            check('the marker-stripping mechanism harness runs', False,
                  p.stderr.strip()[:400])
        else:
            R = json.loads(p.stdout)
            check("cleanHarmony alone — Focus Mode's OLD live-stream recipe "
                  "— leaves the vault-write marker and its payload sitting "
                  "in the bubble",
                  '[VAULT_NEW' in R['harmonyOnly']
                  and '$42,000' in R['harmonyOnly'],
                  [R['harmonyOnly'], '— this is the raw text a boss in the '
                   'quiet room actually saw before the fix'])
            check("...but the fixed recipe (cleanHarmony(visibleReply(...))) "
                  "strips the whole marker and its payload",
                  '[VAULT_NEW' not in R['fixedRecipe']
                  and '$42,000' not in R['fixedRecipe'],
                  [R['fixedRecipe'], '— this is what Focus Mode\'s bubble '
                   'reads after the fix'])
            check("...and still keeps the sentences the CEO actually wrote "
                  "around it",
                  R['fixedRecipe'].startswith('Found it')
                  and R['fixedRecipe'].strip().endswith('Saved the numbers to your Library.'),
                  repr(R['fixedRecipe']))
            check("an ordinary reply with nothing to strip passes through "
                  "untouched",
                  R['plainReplyUnchanged'] == 'Q3 was up 8%.',
                  repr(R['plainReplyUnchanged']))

    # ── 4. mechanism, run for real: the actual throttleTokens under a fake
    #        frame queue, proving the catch-block race the second half of
    #        this fix closes — same harness shape as
    #        test_final_paint_wins.py, aimed at THIS call site's shape ─────
    if not have_node:
        print('  SKIP  node not on PATH — the race-mechanism check needs it')
    else:
        js2 = ''
        for fn in ('reasoningPatterns', 'stripReasoning', 'maskReasoning',
                   'cleanHarmony', 'throttleTokens'):
            m = re.search(r'^function ' + fn + r'\(.*?^\}', src, re.M | re.S)
            if not m:
                raise SystemExit(f'could not find {fn} in hq-runtime.jsx')
            js2 += m.group(0) + '\n'
        js2 += r'''
function makeWorld() {
  const frames = [];
  globalThis.requestAnimationFrame = (cb) => { frames.push(cb); return frames.length; };
  let msg = { id: 'ceo1', text: '' };
  const setChat = (fn) => { msg = fn([msg])[0]; };
  return { frames, setChat, drain: () => { const q = frames.splice(0); q.forEach(cb => cb(0)); }, text: () => msg.text };
}
// A partial buffer mid-stream when the boss hits STOP — the shape the
// catch block actually rewrites from.
const PARTIAL = 'Checking the vault now';
const R = {};

// ── Focus Mode's OLD catch: writes "(stopped)" with no flush.cancel() ──
{
  const w = makeWorld();
  const flush = throttleTokens(w.setChat, 'ceo1');
  flush(PARTIAL);                 // queues a frame, same as any mid-stream token
  R.framesQueuedOld = w.frames.length;
  // the catch block's own rewrite, exactly as it read before this fix
  w.setChat(prev => prev.map(m => m.id === 'ceo1' ? { ...m, text: m.text + ' …(stopped)' } : m));
  R.beforeDrainOld = w.text();
  w.drain();                      // the frame queued above finally gets its turn
  R.afterDrainOld = w.text();
}

// ── Focus Mode's NEW catch: flush.cancel() first, then the same rewrite ─
{
  const w = makeWorld();
  const flush = throttleTokens(w.setChat, 'ceo1');
  flush(PARTIAL);
  R.framesQueuedNew = w.frames.length;
  flush.cancel();
  w.setChat(prev => prev.map(m => m.id === 'ceo1' ? { ...m, text: m.text + ' …(stopped)' } : m));
  R.beforeDrainNew = w.text();
  w.drain();
  R.afterDrainNew = w.text();
}
console.log(JSON.stringify(R));
'''
        p2 = subprocess.run(['node', '-e', js2], capture_output=True, text=True, timeout=15)
        if p2.returncode != 0:
            check('the race-mechanism harness runs', False, p2.stderr.strip()[:400])
        else:
            R2 = json.loads(p2.stdout)
            check('the harness really does leave a frame in flight for both '
                  'variants (or neither proves anything)',
                  R2['framesQueuedOld'] == 1 and R2['framesQueuedNew'] == 1,
                  R2)
            check('the "…(stopped)" rewrite is what stands right after '
                  'the catch runs, in both variants',
                  R2['beforeDrainOld'].endswith('…(stopped)')
                  and R2['beforeDrainNew'].endswith('…(stopped)'),
                  R2)
            check("WITHOUT flush.cancel() (Focus Mode's old catch), the "
                  "queued frame fires after the rewrite and wipes the "
                  '"…(stopped)" marker back to the raw buffer — the '
                  'measured bug',
                  not R2['afterDrainOld'].endswith('…(stopped)'),
                  [R2['afterDrainOld'], '— if this now ends in "(stopped)" '
                   'the reproduction stopped reproducing anything'])
            check('WITH flush.cancel() (the fix), the same queued frame is '
                  'a no-op and "…(stopped)" survives',
                  R2['afterDrainNew'].endswith('…(stopped)'), R2)

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
