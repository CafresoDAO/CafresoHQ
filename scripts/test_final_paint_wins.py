#!/usr/bin/env python3
"""A queued frame repainted the raw stream over the cleaned reply.

Every streaming path in this office ends the same two ways:

    flush.flushNow();                       // paint what has arrived
    ...
    setChat(... text: cleanBuf ...)         // then paint the FINISHED text

`cleanBuf` is the reply with markers stripped — `visibleReply` +
`cleanHarmony`. But `throttleTokens.flush()` renders from `raw`, which
still contains every marker the model emitted. So any frame that fires
after that second write undoes it.

And one usually IS queued. The last tokens call `schedule()`, `flushNow()`
runs synchronously in the same task, and the queued callback fires
afterwards. React batches all three writes into a single commit, so the
cleaned text never even paints — the bubble goes straight from streaming
to raw-markers-and-all, with no visible flicker to give it away.

Watched live 2026-08-13 on the CEO, the bubble the boss reads most:

    CafresoHQ — Nova is the right person for this.
                [HANDOFF_TO: Nova]
                The boss wants a read on the gold rails.
                [/HANDOFF_TO]

directly underneath a strip whose own comment says it was made
unconditional so that this could not happen. The strip ran every time. Its
result was overwritten every time. A plain `[ACK: completed: …]` reproduced
it identically, so this was never about hand-offs.

Whether the bug shows depends only on whether the last token happened to
land in an earlier frame — which is why a slow remote model hides it and a
fast local one shows it on every run, and why it survived this long.

The abort path already knew the shape of this: it calls `cancel()`, and its
comment says a queued frame "would fire AFTER this rewrite and overwrite"
it. Only the success path was left holding the same open door.

Fix: `flushNow()` is the throttle's LAST paint. It flushes and then ends
the throttle, exactly as `cancel()` does — and `note()` already handles the
ended case by APPENDING to whatever the caller wrote instead of re-rendering
from `raw`, which its own comment asks for.

This drives the real `throttleTokens` under node with a fake frame queue,
rather than grepping for the fix — the bug is entirely about WHEN callbacks
run, and a source check cannot see that.

Run: python3 scripts/test_final_paint_wins.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'hq-runtime.jsx'
FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def run_js(cases_js):
    text = SRC.read_text(encoding='utf-8')
    wanted = []
    for fn in ('cleanHarmony', 'throttleTokens'):
        m = re.search(r'^function ' + fn + r'\(.*?^\}', text, re.M | re.S)
        if not m:
            raise SystemExit(f'could not find {fn} in {SRC}')
        wanted.append(m.group(0))
    src = '\n'.join(wanted)
    proc = subprocess.run(['node', '--input-type=module', '-e', src + '\n' + cases_js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


# The harness models the three things that matter and nothing else: a frame
# queue we drain by hand, a message whose text the throttle rewrites, and a
# caller that writes the finished text the way every real call site does.
CASES = r'''
const R = {};

function makeWorld() {
  const frames = [];
  globalThis.requestAnimationFrame = (cb) => { frames.push(cb); return frames.length; };
  let msg = { id: 'm1', text: '' };
  const setChat = (fn) => { msg = fn([msg])[0]; };
  return {
    frames,
    setChat,
    drain: () => { const q = frames.splice(0); q.forEach(cb => cb(0)); },
    text: () => msg.text,
  };
}

// The exact CEO reply from the live run.
const RAW = 'Nova is the right person for this.\n[HANDOFF_TO: Nova]\n' +
            'The boss wants a read on the gold rails.\n[/HANDOFF_TO]';
const CLEAN = 'Nova is the right person for this.';

// ── the shape every call site has ──────────────────────────────────────
// tokens arrive (scheduling a frame), the stream ends, flushNow paints,
// the caller writes the finished text, and only THEN does the queued frame
// get its turn — which is exactly the real ordering.
{
  const w = makeWorld();
  const flush = throttleTokens(w.setChat, 'm1');
  flush(RAW);                       // one token burst -> one frame queued
  R.framesQueued = w.frames.length; // must be 1, or this test proves nothing
  flush.flushNow();
  w.setChat(prev => prev.map(m => m.id === 'm1' ? { ...m, text: CLEAN } : m));
  R.beforeFrame = w.text();
  w.drain();                        // the frame that was already in flight
  R.afterFrame = w.text();
}

// ── a note arriving after the finish must not re-dirty it either ───────
// `note` is the office speaking out of band about a request that never
// parsed. It has to survive, and it has to append rather than re-render
// from `raw` — its own comment says so, and that only holds if the
// throttle is finished by then.
{
  const w = makeWorld();
  const flush = throttleTokens(w.setChat, 'm1');
  flush(RAW);
  flush.flushNow();
  w.setChat(prev => prev.map(m => m.id === 'm1' ? { ...m, text: CLEAN } : m));
  flush.note('(that hand-off never went out)');
  w.drain();
  R.noteKept   = w.text().includes('never went out');
  R.noteClean  = !/\[HANDOFF_TO/.test(w.text());
  R.noteOnTop  = w.text().startsWith(CLEAN);
}

// ── streaming itself still works ───────────────────────────────────────
// The fix must not turn the throttle off early: tokens before the finish
// still paint, or the boss watches a frozen bubble for the whole reply.
{
  const w = makeWorld();
  const flush = throttleTokens(w.setChat, 'm1');
  flush('Hello ');
  w.drain();
  R.midStream1 = w.text();
  flush('world.');
  w.drain();
  R.midStream2 = w.text();
  // The last tokens of a real reply arrive with a frame still pending —
  // flushNow has to PAINT them, not just close the throttle down. Ending
  // the throttle before the flush instead of after loses this word.
  flush(' Bye.');
  R.atFinish = (flush.flushNow(), w.text());
}

// ── cancel still means cancel ──────────────────────────────────────────
{
  const w = makeWorld();
  const flush = throttleTokens(w.setChat, 'm1');
  flush(RAW);
  flush.cancel();
  w.setChat(prev => prev.map(m => m.id === 'm1' ? { ...m, text: '(stopped)' } : m));
  w.drain();
  R.abortKept = w.text();
}

// ── raw() is a scanner's view and must stay unstripped ─────────────────
// The approval tray reads this. It went blind once already when a scan was
// pointed at cleaned text instead.
{
  const w = makeWorld();
  const flush = throttleTokens(w.setChat, 'm1');
  flush(RAW);
  flush.flushNow();
  R.rawIntact = flush.raw() === RAW;
}

console.log(JSON.stringify(R));
'''

out = run_js(CASES)
print('final paint — the cleaned reply is the one that survives')

check('the harness really does leave a frame in flight',
      out['framesQueued'] == 1,
      f"expected exactly 1 queued frame, got {out['framesQueued']} — without "
      'one in flight this test cannot detect the bug at all')
check('the caller\'s finished text is what stands after flushNow',
      out['beforeFrame'] == 'Nova is the right person for this.',
      repr(out['beforeFrame']))
check('a frame queued before the finish cannot repaint the raw stream',
      out['afterFrame'] == 'Nova is the right person for this.',
      'the in-flight frame overwrote the cleaned reply with markers: '
      + repr(out['afterFrame']))

check('an out-of-band note still reaches the boss', out['noteKept'] is True)
check('...without dragging the raw markers back with it', out['noteClean'] is True)
check('...and lands under the finished reply, not instead of it',
      out['noteOnTop'] is True)

check('tokens still paint while the reply streams',
      out['midStream1'] == 'Hello ' and out['midStream2'] == 'Hello world.',
      f"{out['midStream1']!r} then {out['midStream2']!r} — the fix must not "
      'freeze the bubble mid-reply')
check('the final flush still paints what arrived',
      out['atFinish'] == 'Hello world. Bye.', repr(out['atFinish'])
      + ' — flushNow must flush and THEN end the throttle; ending it first '
      'makes the flush a no-op and drops the last tokens of every reply')

check('a stopped run keeps its own marker', out['abortKept'] == '(stopped)',
      repr(out['abortKept']))
check('raw() stays unstripped for the scanners', out['rawIntact'] is True,
      'the approval tray reads raw() — stripping it there is how the tray '
      'went blind before')

print()
if FAILS:
    print(f'final paint: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
    raise SystemExit(1)
print('final paint: all checks passed')
