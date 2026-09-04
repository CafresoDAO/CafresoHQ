#!/usr/bin/env python3
"""■ Stop took the CEO's bubble back and then delegated the question anyway.

The chat meeting loop already documents this exact hazard, one branch up in
the same file:

    "aborting attendee two's stream does nothing to stop the loop from
     DISPATCHING attendee three — a brand-new run, launched after the boss
     said stop."

The CEO path had the identical leak and no guard at all. CafresoHQ writes
its routing markers WHILE it streams — `onTool` pushes every
`[DM_TO: name]…[/DM_TO]` into `ceoDms` and records `[HANDOFF_TO: name]`
into `ceoHandoff` as the tokens arrive — so a boss who presses ■ Stop
mid-reply has, by then, already caused those markers to be collected. The
catch rewrote the bubble to "…(stopped)" and execution then walked
straight on into the fan-out below it:

  · `ceoDms.length && onDispatchToAgent` → two specialists dispatched, each
    on a FRESH per-agent controller in app.jsx that the panel's aborted
    signal has never seen. The boss watches two coworkers start typing an
    answer to a question they just took back, burning tokens on both.
  · `ceoHandoff` → worse than tokens: `setHandoffFor` re-points the whole
    composer at a specialist ("Talk to them directly"), so the NEXT thing
    the boss types goes somewhere they never chose, because of a turn they
    cancelled.

Neither surface stopped it. The panel's own `controller.abort()` only
reaches `HQ.ceoStream`, and `turnEpochRef` — which ■ Stop and STOP ALL both
bump, and which the meeting loop reads at the top of every turn — was never
read on this path at all.

Fix: `turnStopped()` is checked once, after the stream settles and before
either dispatch branch, against BOTH stop surfaces (the panel's controller
and the turn epoch). A stopped turn says who never got the message instead
of sending it.

This lifts the REAL post-stream region of `send()` out of ui/chat.jsx into
a node harness (same anchored-region technique as the other chat.jsx
behaviour tests) and drives it with stubbed dispatch/state so the counts
below are what the office would actually do.

Run: python3 scripts/test_a_stopped_turn_stops_delegating.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAT = ROOT / 'ui' / 'chat.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


HARNESS = r'''
const CafresoHQClient = {};
const snagCause = (s) => String(s);
const withHandoff = (t) => t;
const attachVisit = () => {};

async function postStream(env) {
  const {
    controller, turnEpochRef, ceoTurnEpoch, ceoHandoff, ceoDms,
    onDispatchToAgent, agents, setHandoffFor, setChat, HQ, activeThread,
    setStreaming, text, askId, chatRef, onCeoUsage,
  } = env;
__REGION__
}

function makeEnv(over) {
  const state = { chat: [], dispatched: [], handoffs: [], streaming: [] };
  let n = 0;
  const HQ = {
    uid: (p) => p + (++n),
    cleanHarmony: (s) => s,
    visibleReply: (s) => s,
    honestyNotes: () => [],
    throttleTokens: () => {
      const o = () => {};
      o.note = () => {};
      o.flushNow = () => {};
      o.cancel = () => {};
      o.raw = () => '';
      return o;
    },
    ceoStream: async () => {},
  };
  const env = {
    controller: new AbortController(),
    turnEpochRef: { current: 7 },
    ceoTurnEpoch: 7,
    ceoHandoff: null,
    ceoDms: [],
    onDispatchToAgent: async (a, body) => { state.dispatched.push(a.name); return 'ok'; },
    agents: [
      { id: 'a1', name: 'Vera', role: 'analyst' },
      { id: 'a2', name: 'Kip', role: 'ops' },
    ],
    setHandoffFor: (thread, name) => state.handoffs.push(name),
    setChat: (u) => { state.chat = typeof u === 'function' ? u(state.chat) : u; },
    HQ,
    activeThread: 'direct',
    setStreaming: (v) => state.streaming.push(v),
    text: 'what margin are we running?',
    askId: 'ask1',
    chatRef: { current: [] },
    onCeoUsage: () => {},
    _state: state,
  };
  Object.assign(env, over || {});
  return env;
}

const out = {};

// ── 1. baseline: a turn nobody stopped still fans out ──────────────────
{
  const env = makeEnv({ ceoDms: [{ to: 'Vera', body: 'x' }, { to: 'Kip', body: 'y' }] });
  await postStream(env);
  out.live_fanout = env._state.dispatched.slice();
}
// ── 2. baseline: a live handoff still hands off ────────────────────────
{
  const env = makeEnv({ ceoHandoff: { to: 'Vera', body: 'brief' } });
  await postStream(env);
  out.live_handoff_dispatched = env._state.dispatched.slice();
  out.live_handoff_set = env._state.handoffs.slice();
}
// ── 3. the boss pressed the panel's own ■ Stop mid-stream ──────────────
{
  const env = makeEnv({ ceoDms: [{ to: 'Vera', body: 'x' }, { to: 'Kip', body: 'y' }] });
  env.controller.abort();
  await postStream(env);
  out.aborted_fanout = env._state.dispatched.slice();
  out.aborted_says = env._state.chat.map(m => m.text).join(' | ');
}
// ── 4. the turn epoch moved (■ Stop's sweep / STOP ALL) + a handoff ────
{
  const env = makeEnv({ ceoHandoff: { to: 'Vera', body: 'brief' } });
  env.turnEpochRef.current = 8;
  await postStream(env);
  out.swept_handoff_dispatched = env._state.dispatched.slice();
  out.swept_handoff_set = env._state.handoffs.slice();
  out.swept_says = env._state.chat.map(m => m.text).join(' | ');
}
console.log(JSON.stringify(out));
'''


def main():
    print('chat — a stopped turn stops delegating')
    if not CHAT.is_file():
        print(f'  FAIL  missing {CHAT}')
        return 1
    src = CHAT.read_text(encoding='utf-8')

    # Anchors that exist both before and after the fix: the end of the CEO
    # honesty-guard block, and the settle-the-record comment that closes the
    # turn. Everything between is the post-stream dispatch region.
    start_anchor = 'visits: ceoVisits,\n      })) flush.note(n);\n    }\n'
    end_anchor = '\n    /* Settled at the END of the turn'
    check('the CEO honesty-guard block is still the region opener',
          src.count(start_anchor) == 1,
          'ui/chat.jsx: start anchor not found exactly once')
    check('the settle-the-record comment still closes the turn',
          src.count(end_anchor) == 1,
          'ui/chat.jsx: end anchor not found exactly once')
    if FAILS:
        print('\nFAILED: %s' % FAILS)
        return 1
    region = src[src.index(start_anchor) + len(start_anchor):src.index(end_anchor)]

    # The region must be the real thing, not an empty slice.
    check('the region really is the dispatch region',
          'ceoHandoff' in region and 'ceoDms.length' in region
          and 'onDispatchToAgent' in region,
          'anchors drifted — extracted region does not contain the fan-out')
    if FAILS:
        print('\nFAILED: %s' % FAILS)
        return 1

    harness = HARNESS.replace('__REGION__', region)
    harness = '(async () => {\n' + harness + '\n})();'

    try:
        res = subprocess.run(['node', '--input-type=module', '-e', harness],
                             capture_output=True, text=True, timeout=30)
    except Exception as e:  # noqa: BLE001
        check('node harness ran', False, str(e))
        print('\nFAILED: %s' % FAILS)
        return 1
    check('node harness ran clean', res.returncode == 0, res.stderr.strip()[:400])
    if res.returncode != 0:
        print('\nFAILED: %s' % FAILS)
        return 1
    out = json.loads(res.stdout.strip().splitlines()[-1])

    # ── baselines: the fix must not cost the office its actual behaviour ──
    check('a live turn still fans out to both named coworkers',
          sorted(out['live_fanout']) == ['Kip', 'Vera'], str(out))
    check('a live handoff still dispatches the specialist',
          out['live_handoff_dispatched'] == ['Vera'], str(out))
    check('a live handoff still re-points the composer at them',
          out['live_handoff_set'] == ['Vera'], str(out))

    # ── the bug ───────────────────────────────────────────────────────────
    check('■ Stop mid-reply dispatches nobody',
          out['aborted_fanout'] == [],
          'ui/chat.jsx: markers collected before the abort were still fanned '
          'out on fresh per-agent controllers — dispatched ' + str(out['aborted_fanout']))
    check('...and the thread says who never got the message',
          'stopped this turn' in out['aborted_says']
          and '2 coworkers' in out['aborted_says'],
          'ui/chat.jsx: a silently dropped fan-out is its own trust bug — '
          'said: ' + repr(out['aborted_says']))
    check('a swept turn does not dispatch the handoff target',
          out['swept_handoff_dispatched'] == [],
          'ui/chat.jsx: the turn epoch is the surface ■ Stop and STOP ALL '
          'both bump — dispatched ' + str(out['swept_handoff_dispatched']))
    check('...and does not re-point the composer at a specialist',
          out['swept_handoff_set'] == [],
          'ui/chat.jsx: setHandoffFor after a stop sends the boss\'s NEXT '
          'message somewhere they never chose')
    check('...and says so instead',
          'stopped this turn' in out['swept_says']
          and '1 coworker' in out['swept_says'],
          'said: ' + repr(out['swept_says']))

    print()
    print(('FAILED: %s' % FAILS) if FAILS
          else 'a stopped turn stops delegating: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
