#!/usr/bin/env python3
"""onDelegate (the "HAND OFF TO…" button flow) had the same stale-closure
bug already fixed in dispatchToAgent — but in a sibling dispatch path
that was never given the same fix.

`onDelegate` (app.jsx) is a plain, non-memoized async arrow function
recreated every render. It captures `agents` from the render that
mounted the click handler, then can sit through: (1) a confirm dialog
if the target coworker's desk is mid-reply
(`await window.hqConfirm(...)`), and (2) a potentially long-running
`await HQ.agentStream(...)` call. Two reads inside it used the plain
`agents` closure instead of `agentsRef.current` (the live ref already
established elsewhere in this same file, e.g. dispatchToAgent, for
exactly this staleness hazard):

    const honestyFor = (raw) => (HQ.honestyNotes
      ? HQ.honestyNotes(raw, { delivered: dmQueue.length, roster: agents.map(x => x.name), ... })
      : []);
    ...
    peers: agents.filter(x => x.id !== a.id),

`honestyFor` is actually CALLED after the `agentStream` await resolves
(see the `honesty = honestyFor(buf)` call sites further down in the
same function), so a roster change during the stream (a hire or a
dismissal) made its "roster" argument stale by the time it ran. `peers`
is passed into `agentStream` at call time, but that call time is itself
already downstream of the confirm-dialog await and the full render-to-
click gap — using the live ref removes that staleness window too,
matching the pattern dispatchToAgent already uses for its own peers
list.

Concrete sequence: boss delegates a brief to Vera while she happens to
also be mid-reply elsewhere — the confirm dialog appears, boss takes a
moment to answer it, and in that window a new coworker (Nano) is hired
or an existing one (Kenji) is dismissed. Vera's dispatch proceeds with
a peer list frozen at the stale snapshot: Nano is invisible to her for
the whole run (she can't [DM_TO: Nano] even if the boss's brief asked
her to loop him in), and Kenji still appears as a live peer to address
even though he's gone.

Found by a background hunt agent sweeping previously-unswept areas,
steered toward other instances of the stale-closure-over-state pattern
in async dispatch code outside dispatchToAgent — this is a direct
parallel in the sibling "Hand off to…" dispatch path.

Fix: both reads now use `agentsRef.current` instead of the plain
`agents` closure.

Run: python3 scripts/test_delegate_reads_live_agents_not_stale_closure.py
(skips the live-execution check if `node` isn't on PATH — the
source-shape checks still run everywhere)
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("onDelegate's honesty-roster and peers reads use the live agentsRef, not a stale closure")

    src = APP.read_text(encoding='utf-8')

    delegate_m = re.search(r"const onDelegate = async \(a, typed, thread\) => \{(.*?)\n  \};", src, re.S)
    check('found onDelegate', delegate_m is not None)
    body = delegate_m.group(1) if delegate_m else ''

    roster_m = re.search(
        r"roster: (agentsRef\.current|agents)\.map\(x => x\.name\)", body)
    check('found the honestyFor roster line inside onDelegate', roster_m is not None)
    check("honestyFor's roster reads agentsRef.current (live), not the "
          "plain `agents` closure — the actual regression, since "
          "honestyFor is called AFTER the agentStream await resolves",
          roster_m and roster_m.group(1) == 'agentsRef.current',
          roster_m and f'reads `{roster_m.group(1)}` instead')

    peers_m = re.search(
        r"peers: (agentsRef\.current|agents)\.filter\(x => x\.id !== a\.id\)", body)
    check('found the peers line inside onDelegate', peers_m is not None)
    check('the agentStream call\'s peers option reads agentsRef.current '
          '(live), not the plain `agents` closure',
          peers_m and peers_m.group(1) == 'agentsRef.current',
          peers_m and f'reads `{peers_m.group(1)}` instead')

    check("honestyFor is genuinely called after the agentStream await "
          "(confirms this isn't a same-tick read where staleness "
          "couldn't matter)",
          bool(re.search(r"honesty = honestyFor\(buf\)", body)))

    check('agentsRef is still defined and kept live via an effect '
          '(this fix depends on it existing)',
          'const agentsRef = useRefA(agents);  agentsRef.current = agents;' in src)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted '
          'lines below)', has_node, 'skipping the live-execution check')

    if has_node and roster_m and peers_m:
        js = f"""
        const a = {{ id: 'a_vera', name: 'Vera' }};
        // Stale closure snapshot: this is what `agents` looked like when
        // onDelegate's render mounted the click handler / when the confirm
        // dialog appeared.
        const agents = [
          {{ id: 'a_vera', name: 'Vera' }},
          {{ id: 'a_kenji', name: 'Kenji' }},
        ];
        // Live state by the time the dispatch actually reads it: Kenji was
        // dismissed, Nano was hired, in the gap while the boss answered the
        // confirm dialog / while the stream was in flight.
        const agentsRef = {{ current: [
          {{ id: 'a_vera', name: 'Vera' }},
          {{ id: 'a_nano', name: 'Nano' }},
        ] }};

        const roster = {roster_m.group(0).split(':', 1)[1].strip()};
        const peers = {peers_m.group(0).split(':', 1)[1].strip()};

        console.log(JSON.stringify({{
          roster,
          peerNames: peers.map(p => p.name),
        }}));
        """
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the extracted lines ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-500:])
        if r.returncode == 0:
            import json
            out = json.loads(r.stdout.strip().splitlines()[-1])
            check('the honesty-notes roster reflects the live roster '
                  '(Nano present, Kenji absent) rather than the stale '
                  'closure snapshot (would show Kenji, no Nano, before '
                  'the fix)',
                  out.get('roster') == ['Vera', 'Nano'], out.get('roster'))
            check('the agentStream peers list picks up the newly hired '
                  'Nano and no longer lists the dismissed Kenji (would '
                  'be the reverse before the fix)',
                  out.get('peerNames') == ['Nano'], out.get('peerNames'))

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
