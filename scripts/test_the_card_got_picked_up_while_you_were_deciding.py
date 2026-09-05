#!/usr/bin/env python3
"""#400 — the three doors #398 diagnosed and left open.

#398 swept all 85 suspend points in app.jsx and hq-runtime.jsx for the class
#394 opened — an observation made BEFORE an `await`, acted upon AFTER it —
fixed two, and named three precisely for the next hunt. These are those three.

1. onDeleteTask, the OTHER direction. #398 closed the case where `running` was
   TRUE and the desk changed hands during the "stop them?" dialog. When
   `running` is FALSE the boss is answering the RESULT-GUARD confirm instead
   ("Your coworker's work on it will be lost"), and a chain step can auto-start
   that very card inside the gap — triggerChainStep → onTaskDropOnAgent with
   `opts.auto`, which never asks and never checks whether a modal is open.
   `if (running)` is still false afterwards, so the card is deleted and the run
   is left alive. That is verbatim the failure the abort's own comment claims
   was closed ("a minute later the run finished and FILED A DELIVERY into the
   cabinet for work the boss had explicitly removed" — the office survives
   ordinary accidents, 2026-08-07). The claim held only for the desk as it was
   BEFORE the ask.

   Measured pre-fix via scripts/harness_await_tail.mjs with the REAL
   onDeleteTask, the REAL card-assign block out of onTaskDropOnAgent and the
   REAL desk registry: `cardDeleted: true, runStillAlive: true, deskStillLit:
   true, abortFired: false`, and not one line anywhere saying so.

2. isVaultReady (hq-runtime.jsx). The probe reads the cache, awaits
   CafresoHQClient.vaultStatus(), then writes with a PRE-await stamp and no
   check that the cache is still the one it was asked about. A
   clearVaultReadyCache() landing mid-probe — Settings → Connections after a
   backend swap, which is exactly when a probe is in flight — is silently
   undone: the OLD vault's answer is written back over the deliberate
   invalidation, the watchers fire, and every coworker card goes from honestly
   saying nothing to advertising a vault the boss just disconnected, while
   `toolsForAgent` (which awaits this same function) hands out VAULT_* for it.
   Measured pre-fix: `syncAfterProbeLanded: "true"` one tick after a clear.

   And the stamp: a 4s probe filed under the time it was ASKED is born 4s old,
   so the 5s window expires 1s after the answer arrives and the next caller
   re-probes. Measured pre-fix on a stubbed clock: `probes: 2`.

3. onStopAll. #398 filed this visible-only, "the sweep it performs is
   unconditional and correct". True of every arm but one. `setMissions` /
   `setAgents` are functional updaters that read at commit time and
   `abortAllAgentRuns` reads a ref — but the night-shift arm acts by ITERATING
   the array its render closed over, so a schedule that reaches its start time
   during the dialog, is picked up by the 15s poll, and lands in
   nightShiftBoard is missed by every DELETE. The big red button says the
   office stopped; the night shift runs on server-side. Measured pre-fix:
   `nightShiftDeleted: false`, with the chat line reading "aborted 1 stream"
   for a sweep that took two.

Run: python3 scripts/test_the_card_got_picked_up_while_you_were_deciding.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
RT = ROOT / 'hq-runtime.jsx'
HARNESS = ROOT / 'scripts' / 'harness_await_tail.mjs'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, header):
    i = src.index(header)
    j = src.index('{', i + len(header) - 1)
    d = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                return src[j + 1:k]
    raise AssertionError('unbalanced: ' + header)


app_raw = APP.read_text()
rt_raw = RT.read_text()
app = strip_comments(app_raw)
rt = strip_comments(rt_raw)

print('\n#400 · the card got picked up while you were deciding')

# ── 1. onDeleteTask's far side ────────────────────────────────────────────
print('\nstructural — the ✕, re-derived on the far side of the ask')
handler = brace_lift(app, 'const onDeleteTask = async (id) =>')

check('the door re-derives the board from tasksRef.current after the ask',
      re.search(r'const afterAsk = tasksRef\.current\.find\(x => x\.id === id\)', handler),
      'the render closure cannot have moved — only the ref can')

check('it re-derives with the SAME witness the observation used',
      re.search(r"afterAsk\.status === 'doing'\s*&& !afterAsk\.blockedReason", handler)
      and 'agentAbortersRef.current.has(afterAsk.assignedTo)' in handler,
      'a weaker witness here would re-open #86/#394 at this door')

check('it never names a desk the abort below is already stopping',
      re.search(r"const stopping = running \? t\.assignedTo : null", handler)
      and 'afterAsk.assignedTo !== stopping' in handler)

check('the late run is aborted',
      re.search(r'if \(lateDesk\) \{', handler) and 'abortAgentRun(lateDesk)' in handler)

check('and it is reported exactly once, through the ticker the office has',
      len(re.findall(r'while you were deciding', handler)) == 1
      and re.search(r'logActivity\(\{.*?while you were deciding', handler, re.S))

check('the report names who picked it up, off the LIVE roster',
      'agentsRef.current' in handler and 'lateWho' in handler,
      'a chain step can land on a coworker this render never saw')

check("the toast stops saying a plain delete when a run was stopped",
      re.search(r'say\(\(running \|\| lateDesk\) \?', handler))

# The pinned negatives. These are properties of the door, not of this fix:
# a later refactor that loses them re-opens exactly what #398 and #400 closed.
print('\nnegatives — pinned so a later refactor cannot quietly re-open this')
check('#398: the abort marker is still verbatim what its own test pins',
      'if (running) abortAgentRun(t.assignedTo);' in handler)
check('#398: the in-flight report above it is untouched',
      'if (running) displaceDeskNote(t.assignedTo, who, priorRun,' in handler)
check('#86: the full running witness is still the full one',
      re.search(r"const running = t\.status === 'doing' && !t\.blockedReason && !!t\.assignedTo",
                handler))

# The load-bearing one. An `await` between the re-derivation and the abort
# re-opens the very window this closes: the desk could change hands again.
between = None
if 'const afterAsk =' in handler and 'abortAgentRun(lateDesk)' in handler:
    tail = handler[handler.index('const afterAsk ='):]
    between = tail[:tail.index('abortAgentRun(lateDesk)')]
check('no await stands between the re-derivation and the two acts on it',
      between is not None and 'await' not in between,
      'the re-derivation is missing' if between is None
      else 'found: ' + repr(between[max(0, between.find('await') - 40):][:80]))

# ── 2. the vault probe ────────────────────────────────────────────────────
print('\nstructural — the vault probe and the clear that outran it')
probe = brace_lift(rt, 'async function isVaultReady()')
clear = brace_lift(rt, 'function clearVaultReadyCache()')

check('an epoch exists beside the cache it guards',
      re.search(r'^let _vaultCacheEpoch = 0;', rt, re.M))
check('every deliberate invalidation bumps it', '_vaultCacheEpoch++' in clear)
check('the probe reads the epoch BEFORE it suspends',
      'const epoch = _vaultCacheEpoch;' in probe
      and probe.index('const epoch = _vaultCacheEpoch;') < probe.index('await CafresoHQClient.vaultStatus()'))
check('and re-checks it before every write, both the answer and the failure',
      len(re.findall(r'if \(epoch === _vaultCacheEpoch\) _noteVaultReady', probe)) == 2)
check('the stamp is taken when the answer LANDS, not when it was asked',
      len(re.findall(r'_noteVaultReady\(.*?, Date\.now\(\)\)', probe)) == 2
      and not re.search(r'_noteVaultReady\([^)]*, now\)', probe))
check('the freshness TEST still uses the pre-await `now` (it is a read, not a write)',
      re.search(r'if \(_vaultConfiguredCache\.at && now - _vaultConfiguredCache\.at < 5000\)', probe))
check('a discarded probe returns the cache, not its own stale answer',
      re.search(r'return _vaultConfiguredCache\.ok;\s*$', probe.strip()))

# ── 3. STOP ALL ───────────────────────────────────────────────────────────
print('\nstructural — the big red button, counted and swept at sweep time')
stopall = brace_lift(app, 'const onStopAll = async () =>')

check('nightShiftBoard is mirrored into a ref, the way agentsRef/tasksRef are',
      re.search(r'const nightShiftBoardRef = useRefA\(nightShiftBoard\);\s*'
                r'nightShiftBoardRef\.current = nightShiftBoard;', app))
check('the night-shift sweep iterates the LIVE board',
      re.search(r'const nightNow = nightShiftBoardRef\.current \|\| \[\];', stopall)
      and re.search(r'nightNow\.forEach\(n => \{', stopall)
      and 'nightShiftBoard.forEach' not in stopall)
check('the stream count is read on the statement before the sweep empties it',
      re.search(r'const swept = agentAbortersRef\.current\.size;\s*\n\s*abortAllAgentRuns\(\);', stopall))
check('the sentence reports what was swept, not what was counted',
      'aborted ${swept} stream' in stopall and 'aborted ${inflight} stream' not in stopall
      and 'const nightSwept = nightNow.length;' in stopall)
# Negative: the DIALOG is a question about now, so it keeps the pre-ask read.
check('negative — the confirm still describes the office as it asked',
      'This will stop ${inflight} coworker' in stopall
      and 'pause ${running} running mission' in stopall)
check('negative — the early bail still uses the pre-ask counts',
      re.search(r'if \(inflight === 0 && running === 0\)', stopall))

# ── behavioural, through the real handlers ────────────────────────────────
print('\nbehavioural — driven through scripts/harness_await_tail.mjs')
p = subprocess.run(['node', str(HARNESS), str(ROOT)],
                   cwd=ROOT, capture_output=True, text=True)
if p.returncode != 0:
    check('the harness runs', False, (p.stderr or p.stdout)[-600:])
    print('\nFAILED: ' + ', '.join(FAILS))
    sys.exit(1)
S = {}
for line in p.stdout.strip().splitlines():
    if line.startswith('{'):
        r = json.loads(line)
        S[r['scenario']] = r

r = S['chain-step-starts-during-the-result-confirm']
check('the dialog the boss answered was the result guard', r['dialogWasTheResultGuard'])
check('the chain step really did claim the desk inside the gap', r['chainStarted'])
check('the boss still gets their deletion', r['cardDeleted'])
check('the run that started during the dialog is stopped', not r['runStillAlive'], r)
check('and the desk goes dark with the card', not r['deskStillLit'], r)
check('the office says which run it stopped', r['lateStopReported'], r['activity'])
check('the toast no longer calls it a plain delete',
      any('stopped the run' in s for s in r['said']), r['said'])

r = S['no-chain-step-nothing-said']
check('an untouched card is deleted in silence, as before',
      r['cardDeleted'] and not r['abortFired'] and not r['lateStopReported'], r)

r = S['declined-delete-keeps-the-card-and-the-run']
check('a DECLINED delete keeps the card AND the run that started',
      (not r['cardDeleted']) and r['runStillAlive'] and not r['abortFired'], r)

r = S['vault-cleared-mid-probe']
check('a clear that lands mid-probe is not undone by the probe',
      r['clearSurvivedTheProbe'], r)
check('the cards keep saying nothing rather than naming the old vault',
      r['syncAfterProbeLanded'] == 'undefined', r)
check('no watcher is told the disconnected vault is ready',
      r['watched'] == ['undefined'], r['watched'])

r = S['vault-untouched-probe-still-answers']
check('negative — with nobody clearing, the probe still lands',
      r['syncAfterProbeLanded'] == 'true' and r['watched'] == ['true'], r)

r = S['vault-slow-probe-freshness']
check('a slow probe is fresh for 5s from when it ANSWERED',
      r['probes'] == 1 and not r['reProbedImmediately'], r)

r = S['stop-all-night-shift-arrives-mid-dialog']
check('a night shift that came up during the dialog is actually cancelled',
      r['nightShiftDeleted'], r['deletes'])
check('the board is cleared with it', r['boardCleared'], r)
check('the sentence counts the streams the sweep actually took',
      'aborted 2 streams' in r['chatLine'], r['chatLine'])
check('and names the night shift it stopped',
      '1 night shift' in r['chatLine'], r['chatLine'])

r = S['stop-all-quiet-office']
check('negative — no night shift means no DELETE and no night-shift clause',
      (not r['nightShiftDeleted']) and 'night shift' not in r['chatLine'], r)

print()
if FAILS:
    print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
    sys.exit(1)
print('all good — the ✕, the vault probe and the big red button all act on the '
      'office as it is when they act, not as it was when they asked.')
