#!/usr/bin/env python3
"""The office told the boss the same correction twice.

Reproduced 2026-08-15 on a fresh office (port 9260, one hire — Vera — on a
local brain, canned reply naming `Research/vendor-comparison.md` and filing
nothing). The bubble ended:

    Recommendation: B for now, revisit at scale.

    _(`Research/vendor-comparison.md` is named above, but nothing was
      written to the cabinet on this run, so that file is not there.)_

    _(`Research/vendor-comparison.md` is named above, but nothing was
      written to the cabinet on this run, so that file is not there.)_

One `unfiledPath` note. One `honestyNotes` entry — confirmed by the activity
row, which prints `honesty.join(' ')` and showed the sentence ONCE. One
`note()` call — confirmed by instrumenting the emit loop. Two copies in the
message.

The order, instrumented live, is the whole finding:

    [P] flushNow
    [P] emit#1  (honesty.length = 1)
    [P] note()      cancelled=true
    [P] withNotes   suffix="\\n\\n_(`Research/…` is named above, …"

`withNotes` is called at app.jsx:2186, LEXICALLY BEFORE the note is emitted
at 2614 — but it is called from inside a `setChat(prev => …)` updater, and
React runs updaters when it processes the queue, not when the caller
enqueues them. The write requested first is evaluated last, over a `suffix`
that grew in between. Both mechanisms that exist so the note is never LOST
then applied it.

Only one of the two writes could be reordered safely. `withNotes` is
ABSOLUTE — it computes the whole text — so running it twice, or last, still
yields one copy. `note()`'s direct branch is RELATIVE: it reads the current
text and appends, so it duplicates whatever an absolute write already
included. Asking "is it already there" makes it idempotent in either order.

All three dispatch paths call `withNotes` from inside an updater, so all
three said it twice. Measured on two of them before and after:

    @mention  2 -> 1
    Delegate  2 -> 1

A doubled sentence is not cosmetic here. This note exists to tell the boss
the office did not do what it was asked to do; a correction that stutters
reads like the office is unsure of its own correction.

Run: python3 scripts/test_the_office_says_it_once.py
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Scan code, never prose — the comment written with this fix quotes
    every phrase below, including the duplicated sentence itself."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
    """Body by brace matching; the opener is the first `{` at paren depth 0.

    Fifth suite here to need this. A `{0,N}?` window does not report "not
    found" when the code outgrows it — it reports a confident false
    statement about whatever it did reach.
    """
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
    print('the office says a correction once')
    code = strip_comments(RUNTIME)
    app = strip_comments(APP)

    # ── 1. the relative write is guarded ────────────────────────────────
    note = brace_lift(code, 'ontok.note = (text) =>')
    check('note() still has a direct-write branch for a cancelled throttle',
          'cancelled' in note and 'setChat' in note,
          'without it a note emitted after flushNow is dropped entirely — '
          'the failure this branch was added to fix')
    check('...and it asks whether the note already landed',
          re.search(r'indexOf\(text\)\s*>=\s*0|\.includes\(text\)', note),
          [note, '— the append is relative, so an absolute write that ran '
           'first (a deferred withNotes) makes it a duplicate'])
    # `.index` raises when the needle is gone, and a check that raises is a
    # check that reports "the suite crashed" instead of "this is broken" —
    # fire-tested, two arms came back as HARNESS CRASH and told me nothing
    # about which invariant they had violated. `.find` answers -1 instead.
    g, a = note.find('indexOf(text)'), note.find("+ '\\n\\n' + text")
    check('...before appending, not after',
          g >= 0 and a >= 0 and g < a,
          [g, a, '— a guard after the append is not a guard'])

    # The no-op ternary that hid the asymmetry: both branches were '\n\n'.
    check('the suffix join is not a ternary with two identical arms',
          not re.search(r"suffix \? '\\n\\n' : '\\n\\n'", code),
          'it read as if the first note were special-cased; it was not')

    # ── 2. withNotes stays absolute ─────────────────────────────────────
    wn = brace_lift(code, 'ontok.withNotes = (text) =>')
    check('withNotes still computes the whole text',
          'return text' in wn and 'suffix' in wn, wn)
    check('...and never reads the message it is writing into',
          'setChat' not in wn and 'm.text' not in wn,
          'the moment it appends to what is there, BOTH writes are '
          'relative and the guard above cannot save either of them')

    # ── 3. the ordering hazard itself is pinned ─────────────────────────
    # This is the shape that made a lexically-earlier call execute later.
    # It is legitimate — but if it ever stops being true on all three
    # paths, the reasoning in note()'s comment stops describing the app.
    deferred = re.findall(r'setChat\(prev =>[\s\S]{0,400}?flush\.withNotes\(', app)
    check('withNotes is still called from inside a state updater',
          len(deferred) == 3,
          [len(deferred), '— all three, not "at least two": with >=2 this '
           'check survived one path dropping withNotes entirely, which is '
           'how the note goes back to being lost on that path'])
    emits = re.findall(r'for \(const n of honesty\) if \(flush && flush\.note\) flush\.note\(n\);', app)
    check('every dispatch path emits its notes through the one loop',
          len(emits) == 3, [len(emits), '@mention, Delegate, task'])
    check('...and each computes honesty exactly once per run',
          app.count('if (!honesty) honesty = honestyFor(') == 3
          and app.count('honesty = honestyFor(') == 6,
          [app.count('honesty = honestyFor('),
           '— three eager (the activity row needs the answer) plus three '
           'error-path fallbacks; a fourth would double the notes at the '
           'source instead of at the write'])

    # ── 4. one note in, one note out, run for real ──────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the ordering checks need it')
    else:
        js = re.search(r'^function throttleTokens\(setChat, msgId\) \{[\s\S]*?^\}$',
                       RUNTIME, re.M).group(0) + '\n'
        js += r'''
function cleanHarmony(s) { return s; }              // not what this tests
const NOTE = '_(a file is named above, but nothing was written.)_';

// A message store that behaves like React: updaters are QUEUED and run in
// enqueue order when the queue is processed, not when setChat is called.
function makeStore() {
  const st = { msgs: [{ id: 'm1', text: '' }], queue: [] };
  st.setChat = (fn) => st.queue.push(fn);
  st.process = () => { for (const fn of st.queue) st.msgs = fn(st.msgs); st.queue = []; };
  st.text = () => st.msgs[0].text;
  return st;
}
const count = (s) => (s.split(NOTE).length - 1);

// The reproduced order: stream, flushNow, caller enqueues its withNotes
// write, THEN the note is emitted. The enqueued updater runs last.
function reproduced() {
  const st = makeStore();
  const flush = throttleTokens(st.setChat, 'm1');
  flush('the reply body');
  flush.flushNow();
  st.process();
  st.setChat(prev => prev.map(m => m.id === 'm1' ? { ...m, text: flush.withNotes('the reply body') } : m));
  flush.note(NOTE);
  st.process();
  return st.text();
}
// The same two writes, opposite order. Neither may duplicate.
function reversed() {
  const st = makeStore();
  const flush = throttleTokens(st.setChat, 'm1');
  flush('the reply body');
  flush.flushNow();
  st.process();
  flush.note(NOTE);
  st.process();
  st.setChat(prev => prev.map(m => m.id === 'm1' ? { ...m, text: flush.withNotes('the reply body') } : m));
  st.process();
  return st.text();
}
// A path that never calls withNotes at all — the abort route. The note is
// the ONLY thing that can carry it, so it must still land.
function noWithNotes() {
  const st = makeStore();
  const flush = throttleTokens(st.setChat, 'm1');
  flush('the reply body');
  flush.flushNow();
  st.process();
  flush.note(NOTE);
  st.process();
  return st.text();
}
// Two DIFFERENT notes, the shape a run with two failed claims produces.
function twoNotes() {
  const st = makeStore();
  const flush = throttleTokens(st.setChat, 'm1');
  flush('body');
  flush.flushNow();
  st.process();
  st.setChat(prev => prev.map(m => m.id === 'm1' ? { ...m, text: flush.withNotes('body') } : m));
  flush.note(NOTE);
  flush.note('_(second note.)_');
  st.process();
  return st.text();
}
const R = {
  repro: count(reproduced()),
  reproHas: reproduced().indexOf(NOTE) >= 0,
  reversed: count(reversed()),
  none: count(noWithNotes()),
  twoA: count(twoNotes()),
  twoB: twoNotes().split('_(second note.)_').length - 1,
  bodyKept: reproduced().indexOf('the reply body') >= 0,
};
console.log(JSON.stringify(R));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        if p.returncode != 0:
            check('the ordering harness runs', False, p.stderr.strip()[:400])
        else:
            import json
            R = json.loads(p.stdout)
            check('the reproduced order yields the note exactly once',
                  R['repro'] == 1,
                  [R['repro'], '— this is the measured sequence: flushNow, '
                   'an enqueued withNotes write, then note(). It printed '
                   'the correction twice.'])
            check('...and the note is actually there, not merely un-doubled',
                  R['reproHas'],
                  'suppressing both copies would pass a count check and '
                  'lose the only sentence that tells the boss the truth')
            check('...and the coworker keeps their own words', R['bodyKept'], R)
            check('the opposite order also yields exactly one',
                  R['reversed'] == 1,
                  [R['reversed'], '— React decides the order, not us'])
            check('a path with no withNotes still gets its note',
                  R['none'] == 1,
                  [R['none'], '— the abort route writes its own text and '
                   'never calls withNotes; the direct branch is the only '
                   'thing carrying the note there'])
            check('two different notes both land, once each',
                  R['twoA'] == 1 and R['twoB'] == 1, R)

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
