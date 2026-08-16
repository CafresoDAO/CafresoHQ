#!/usr/bin/env python3
"""The tour's ring waited on a timer instead of on the thing it points at.

Measured 2026-08-16 on office 9280, mobile viewport (375x812), driving the
nine-step mobile first-run to its last step. A MutationObserver recorded
every relevant DOM event; the timestamps are relative to the card turning
over to step 9:

       0ms  CARD step 9 — "Hire your first coworker"
      55ms  TARGET .mas-plus in DOM, 36x36
      55ms  ring CLEARED
     987ms  RING 152,220

The control the card names was on screen at 55ms. The ring did not arrive
until the next tick of the retry loop. In between, the boss reads "Tap the
+ at the end of your coworker strip" with nothing highlighted anywhere —
the last step of the first run, pointing at nothing, while the thing it
points at sits there.

(The 987ms is inflated: the measuring tab was backgrounded, and Chrome
clamps background setTimeout to ~1s, so what would be one 100ms retry read
as one ~1000ms retry. The clamp does not touch the ORDERING, which is the
finding: target first, ring second, with a timer in between. On the
recorded first-run — foreground, cold floor, many retries — the same shape
was ~2s.)

The cause is structural, not a tuning problem. The first attempt runs in
the same effect tick as `step.action()`, before React has rendered the view
that action just opened, so on any navigating step it cannot succeed. That
makes the ring's arrival a property of the poll interval rather than of the
target. A mutation is the event actually being waited for.

Reading the effect to write this turned up a second one with no live repro
needed: it had no cleanup. `useEffect(..., [open, idx])` started a
setTimeout chain and never cancelled it, so pressing Next twice leaves step
8's search for `.palette-fab` running underneath step 9's card, free to
call setSpotlight with the PREVIOUS step's rect after the new one has
landed. Whichever target mounts last wins. That is the same defect the
file's own comments describe twice already ("a second of pointing at the
wrong control is still pointing at the wrong control"), arriving by a third
door.

WHAT THIS PINS
  · the ring lands on the MUTATION that brings the target in, not on the
    poll tick after it
  · the poll survives as a backstop, because a target that grows from 0x0
    through layout alone mutates nothing
  · the 2.5s budget, and onRect(null) — not a stale rect — when it expires
  · exactly one call to onRect, ever, by any of the three exits
  · cancel() means silence: a superseded step cannot paint over its
    successor
  · the effect returns that cancel
  · resolveSpotlight stays a liftable plain function with an injectable
    environment — this whole behaviour half exists only because it is one
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / 'ui' / 'onboarding.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """The comments quote the measurement and name the selectors, so a
    source check would otherwise match its own documentation."""
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
    print('the ring lands when the thing lands')
    code = strip_comments(SRC)

    # ── 1. the seams ─────────────────────────────────────────────────────
    check('resolveSpotlight is a liftable plain function',
          re.search(r'^function resolveSpotlight\(', code, re.M),
          '— the behaviour checks below lift it by name')

    eff = code[code.index('function OnboardingTour('):]
    eff = eff[:eff.index('}, [open, idx]);')]
    check('the effect hands back resolveSpotlight as its cleanup',
          re.search(r'return resolveSpotlight\(step\.target, setSpotlight\)',
                    eff),
          '— without a cleanup the old step keeps searching under the new '
          'card')
    check('...and no retry loop is left inline in the effect',
          'setTimeout' not in eff,
          '— a second timer in here is a second thing with no cleanup')
    check('the previous ring is still dropped before the search starts',
          re.search(r'setSpotlight\(null\);\s*\n\s*return resolveSpotlight',
                    eff),
          '— the old ring must not sit under the new words')

    rs = brace_lift(code, 'function resolveSpotlight(')
    check('the search watches for a mutation',
          'new Obs(' in rs and '.observe(' in rs and 'subtree: true' in rs,
          '— polling alone makes the ring a property of the interval')
    check('...and keeps the poll as a backstop, not as the mechanism',
          'setT(tick, every)' in rs and 'waited >= budget' in rs,
          '— a target that grows through layout alone mutates nothing')
    check('the budget is still 2.5s',
          're.budget' not in rs and 'e.budget || 2500' in rs,
          '— a navigating step can need well over a second')
    check('the environment is injectable',
          all(re.search(r'e\.' + n + r'\s*\|\|', rs)
              for n in ('doc', 'MutationObserver', 'setTimeout',
                        'clearTimeout')),
          '— otherwise none of the checks below can exist')

    # ── 2. what it actually does ─────────────────────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the behaviour half needs it')
        return 1 if FAILS else 0

    driver = rs + r'''
/* A document that mounts nothing until told to, and a MutationObserver
   that fires only when it does — the two halves of the real environment
   this function is timing against, with the clock in the test's hands. */
function rig(opts) {
  const o = opts || {};
  const log = [];
  let el = o.present ? { w: 36, h: 36 } : null;
  const cbs = [];
  const timers = [];
  let now = 0;
  const doc = {
    body: {},
    querySelector: () => el && ({
      getBoundingClientRect: () => ({ left: 100, top: 200, width: el.w, height: el.h }),
    }),
  };
  const env = {
    doc,
    MutationObserver: function (cb) {
      cbs.push(cb);
      return { observe: () => log.push('observe'), disconnect: () => log.push('disconnect') };
    },
    setTimeout: (fn, ms) => { const t = { fn, at: now + ms, dead: false }; timers.push(t); return t; },
    clearTimeout: (t) => { if (t) t.dead = true; },
  };
  return {
    log, env,
    /* Bring the target in, the way React does: DOM change, then observers. */
    mount: (w, h) => { el = { w: w === undefined ? 36 : w, h: h === undefined ? 36 : h };
                       cbs.forEach(f => f()); },
    /* Grow it with no mutation at all — a transition settling. */
    grow: () => { el.w = 36; el.h = 36; },
    /* A discrete-event clock, not a stopwatch that jumps. Each timer runs
       with `now` set to its OWN due time, so a callback that reschedules
       lands 100ms after when it fired rather than 100ms after wherever the
       clock had already been dragged. A self-rescheduling retry loop is the
       whole subject here; the first draft advanced `now` first and turned
       25 retries into two, which measures the harness, not the code. */
    tick: (ms) => {
      const target = now + ms;
      for (let guard = 0; guard < 10000; guard++) {
        const due = timers.filter(x => !x.dead && x.at <= target)
                          .sort((a, b) => a.at - b.at)[0];
        if (!due) break;
        now = due.at; due.dead = true; due.fn();
      }
      now = target;
    },
    pending: () => timers.filter(t => !t.dead).length,
  };
}

const out = {};

// Already on screen: resolved before any clock moves at all.
{
  const r = rig({ present: true });
  const seen = [];
  resolveSpotlight('.mas-plus', (x) => seen.push(x), r.env);
  out.immediate = seen;
  out.immediateWatchers = r.log.length;
}

// The measured case. The target arrives 55ms in; the poll would not run
// for another 45ms. The ring must land on the mutation.
{
  const r = rig({});
  const seen = [];
  resolveSpotlight('.mas-plus', () => seen.push('RING'), r.env);
  r.tick(55);              // clock moves, nothing mounted yet
  out.beforeMount = seen.length;
  r.mount();               // React puts .mas-plus in the DOM
  out.onMutation = seen.length;   // <- the whole ticket
  r.tick(1000);            // the poll would have fired here
  out.afterPoll = seen.length;    // still one, not two
  out.disconnected = r.log.filter(x => x === 'disconnect').length;
  out.noPending = r.pending();
}

// No mutation, only layout: the element was always there at 0x0 and grew.
// The observer cannot see this; the backstop must.
{
  const r = rig({});
  const seen = [];
  resolveSpotlight('.mas-plus', (x) => seen.push(x), r.env);
  r.mount(0, 0);           // present but unmeasurable
  out.zeroSizeIgnored = seen.length;
  r.grow();                // no mutation fired
  r.tick(100);
  out.backstopFound = seen.length === 1 && seen[0] && seen[0].width === 48;
}

// A target that never appears: one null, at the budget, and not before.
{
  const r = rig({});
  const seen = [];
  resolveSpotlight('.nope', (x) => seen.push(x), r.env);
  r.tick(2400);
  out.earlyGiveUp = seen.length;
  r.tick(200);
  out.gaveUp = seen;
  r.tick(5000);
  out.gaveUpOnce = seen.length;
}

// The racing chains. A superseded step must go silent — even if the thing
// it was looking for turns up afterwards.
{
  const r = rig({});
  const seen = [];
  const cancel = resolveSpotlight('.palette-fab', () => seen.push('RING'), r.env);
  r.tick(50);
  cancel();
  r.mount();
  r.tick(5000);
  out.afterCancel = seen.length;
  out.cancelDisconnects = r.log.filter(x => x === 'disconnect').length;
  out.cancelClearsTimer = r.pending();
}

console.log(JSON.stringify(out));
'''

    p = subprocess.run(['node', '--input-type=module', '-e', driver],
                       capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        check('the lifted function runs under node', False,
              (p.stderr or p.stdout)[-700:])
        return 1
    o = json.loads(p.stdout.strip().splitlines()[-1])

    check('a target already on screen rings with no clock at all',
          len(o['immediate']) == 1
          and o['immediate'][0] == {'left': 94, 'top': 194,
                                    'width': 48, 'height': 48},
          o['immediate'])
    check('...and sets nothing watching or waiting',
          o['immediateWatchers'] == 0, o['immediateWatchers'])

    check('nothing rings while the target is not there',
          o['beforeMount'] == 0, o['beforeMount'])
    check('the ring lands on the mutation that brings the target in',
          o['onMutation'] == 1,
          '— this is the ticket: 55ms, not the next poll tick')
    check('...and the poll behind it does not ring a second time',
          o['afterPoll'] == 1, o['afterPoll'])
    check('...and both the watcher and the timer are dropped once found',
          o['disconnected'] == 1 and o['noPending'] == 0,
          [o['disconnected'], o['noPending']])

    check('a target present at 0x0 is not rung',
          o['zeroSizeIgnored'] == 0, o['zeroSizeIgnored'])
    check('...and the poll backstop still catches it when it grows',
          o['backstopFound'],
          '— layout alone fires no mutation for the observer to see')

    check('an unfindable target is not given up on early',
          o['earlyGiveUp'] == 0, o['earlyGiveUp'])
    check('...and expires to no ring rather than a stale one',
          o['gaveUp'] == [None], o['gaveUp'])
    check('...exactly once',
          o['gaveUpOnce'] == 1, o['gaveUpOnce'])

    check('a cancelled step never rings, even if its target arrives',
          o['afterCancel'] == 0,
          '— step 8 painting over step 9 is the bug the cleanup exists for')
    check('...and leaves nothing watching or waiting behind it',
          o['cancelDisconnects'] == 1 and o['cancelClearsTimer'] == 0,
          [o['cancelDisconnects'], o['cancelClearsTimer']])

    print('\n' + ('all checks passed' if not FAILS
                  else '%d FAILED: %s' % (len(FAILS), FAILS)))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
