#!/usr/bin/env python3
"""A note waited its turn for a busy desk, then died for somebody else's yes.

#391's guard sweep left one finding for its own hunt: dispatchToAgent's
busy-desk `while` poll, "two office-initiated notes can both wake on the
same clear tick and both proceed … two DISTINCT messages where one gets
evicted (lost work)". Driven here against the real source, that claim does
NOT hold — the `while` re-tests `has(agent.id)` at the top of every
iteration, each 750ms sleep is its own macrotask, the microtask checkpoint
between two timer tasks lets the first waiter's continuation finish, and
the stretch from the loop's exit to `beginAgentRun` is straight-line
synchronous with no await in it. The second waiter re-tests a desk the
first has already claimed and goes back to sleep. Two, three, ten notes
all arrive. That negative is pinned below, because it is only true while
that stretch stays await-free.

What the finding was pointing at is one door over, and it does reproduce.
The two BOSS-initiated claim paths — onDelegate's hand-off and
onTaskDropOnAgent's ▶ START / drop — read the desk, `await
window.hqConfirm(...)`, and only then call `beginAgentRun`. A modal is
open for as long as the boss leaves it open; the wait re-polls every
750ms. So a note that queued behind the SAME busy desk can wake inside
that gap, find the desk clear, claim it and start streaming — and the
boss's "Stop & hand off" then evicts the note instead of the run the
dialog described.

Measured 2026-09-05 via scripts/harness_busydesk_race.mjs against the real
extracted handlers: Kip's reply held Vera's desk, Sam's note waited its
turn (the team room says so), Kip finished while the boss read the dialog,
Sam's note claimed the desk and began — and "Start it" killed Sam's note
mid-token with `displacementReported: false`: not one team-room line, not
one registry transition. The boss was asked about Kip and answered about
Kip; Sam's work was the thing that stopped, and nothing anywhere said so.
Worse than a duplicate, which at least leaves two of something.

The fix is a desk ledger — `deskWorkRef`, one entry per desk, signed by
dispatchToAgent after its own claim — plus `displaceDeskNote`, called at
both claim sites with the occupant AS OBSERVED before the dialog. The
boss's gesture still wins; the note it actually displaced is now filed the
way the wait's own STOP ALL branch files an undelivered one: `cancelled`,
retryable, with a team-room line naming it and the re-send left to the
boss.

Run: python3 scripts/test_a_note_that_waited_its_turn_is_not_stopped_in_silence.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / 'scripts' / 'harness_busydesk_race.mjs'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def run_harness(scenario=None):
    cmd = ['node', str(HARNESS), str(ROOT / 'app.jsx'), str(ROOT / 'hq-runtime.jsx')]
    if scenario:
        cmd.append(scenario)
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if out.returncode != 0:
        print('  FAIL  harness did not run  — ' + (out.stderr or '')[-900:])
        FAILS.append('harness did not run')
        return {}
    rows = {}
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line.startswith('{'):
            continue
        row = json.loads(line)
        rows[row['scenario']] = row
    return rows


def main():
    print('a note that waited its turn is not stopped in silence')
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    bare = strip_comments(app)

    # ── round 1: the ledger and the report exist, and sit where they must ──
    check('the desk ledger exists', 'const deskWorkRef = useRefA(new Map());' in bare)
    check('the honest displacement report exists once',
          bare.count('const displaceDeskNote = (agentId, agentName, since, byWhat) => {') == 1)

    check("beginAgentRun's signature is untouched",
          'const beginAgentRun = (agentId) => {' in bare,
          'a dozen tests lift it by this exact marker — sign the desk at the '
          'call site instead of widening the registry')

    sign = re.search(
        r"const controller = beginAgentRun\(agent\.id\);\s*"
        r"deskWorkRef\.current\.set\(agent\.id, \{\s*"
        r"controller, messageId, from:", bare)
    check("dispatchToAgent signs the desk the instant it claims it", sign is not None,
          'the signature must be the statement after the claim — anything in '
          'between is a window where the desk is held by a nameless run')

    check('endAgentRun drops the ledger entry by controller identity',
          re.search(r'const held = deskWorkRef\.current\.get\(agentId\);\s*'
                    r'if \(held && held\.controller === controller\) '
                    r'deskWorkRef\.current\.delete\(agentId\);', bare) is not None,
          'a stale name on a free desk would be reported as displaced work')

    body = ''
    m = re.search(r'const displaceDeskNote = \(agentId, agentName, since, byWhat\) => \{(.*?)\n  \};',
                  bare, flags=re.S)
    if m:
        body = m.group(1)
    check('the report refuses to fire when the desk never changed hands',
          'if (!now || now === since) return null;' in body)
    check('the report refuses to name a run the ledger does not hold',
          'if (!held || held.controller !== now) return null;' in body,
          'identity, not presence — the same check endAgentRun makes')
    check('the displaced note is filed cancelled and retryable',
          "MessageRegistry.transition(held.messageId, 'cancelled'" in body
          and "kind: 'displaced', retryable: true" in body
          and 'actionNeeded' in body)
    check('the team room is told, in the room the office already uses for this',
          "thread: 'team'" in body and 'not the one you were asked about' in body)

    # Both boss-initiated claim sites: observe the desk, then report BEFORE
    # beginAgentRun evicts. The order is the whole fix.
    for label, prior_marker, call_marker, claim_marker in (
        ('the hand-off door',
         'const priorRun = agentAbortersRef.current.get(a.id);',
         "displaceDeskNote(a.id, a.name, priorRun, 'your hand-off');",
         'const controller = beginAgentRun(a.id);'),
        ('the ▶ START / drop door',
         'const priorRun = agentAbortersRef.current.get(agent.id);',
         'displaceDeskNote(agent.id, agent.name, priorRun, `starting "${task.title}"`);',
         'const controller = beginAgentRun(agent.id);'),
    ):
        p_at = bare.find(prior_marker)
        c_at = bare.find(call_marker)
        b_at = bare.find(claim_marker, c_at) if c_at != -1 else -1
        check(f'{label} observes the desk before its dialog and reports '
              f'before it claims',
              -1 < p_at < c_at < b_at, [p_at, c_at, b_at])
        if -1 < c_at < b_at:
            check(f'{label} reports with nothing awaitable in between',
                  re.search(r'\bawait\b', bare[c_at:b_at]) is None,
                  'the report reads the desk; anything async here re-opens '
                  'the very window it closes')

    # ── the pinned negative: what makes two waiting notes serialize ──────
    gate_at = bare.find('while (agentAbortersRef.current.has(agent.id)) {')
    claim_at = bare.find('const controller = beginAgentRun(agent.id);', gate_at)
    loop_end = bare.find('}', bare.find('await new Promise(res => setTimeout(res, 750));', gate_at))
    check('the busy-desk poll re-tests the desk at the top of every iteration',
          gate_at != -1 and 'await new Promise(res => setTimeout(res, 750));'
          in bare[gate_at:gate_at + 400],
          'a wait that tests once and sleeps is a wait that wakes into an '
          'occupied desk')
    check('nothing awaitable stands between the poll and the claim',
          -1 < loop_end < claim_at
          and re.search(r'\bawait\b', bare[loop_end:claim_at]) is None,
          'this is the ONLY reason two notes waking on the same clear tick '
          'serialize instead of both proceeding — #391 flagged that race, '
          'and it is safe by this property and nothing else')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH — behavior checks need it')
    else:
        # ── rounds 2-4: two distinct notes, one busy desk. The negative,
        #    driven rather than argued.
        rows = run_harness()
        for name, n in (('two-notes-one-busy-desk', 2),
                        ('three-notes-one-busy-desk', 3)):
            r = rows.get(name, {})
            check(f'{name}: every note is delivered, none evicted',
                  r.get('delivered') and len(r['delivered']) == n
                  and r.get('lost') == 0,
                  [r.get('started'), r.get('delivered'), r.get('evicted')])
            check(f'{name}: each note said it was waiting its turn',
                  r.get('waitNotes') == n, r.get('waitNotes'))
            check(f'{name}: the desk is free when the last one ends',
                  r.get('deskEmptyAtEnd') is True)

        # sanity: one note, one busy desk, nothing clever.
        r = rows.get('one-note-one-busy-desk', {})
        check('one-note-one-busy-desk: it waits, then it runs',
              r.get('delivered') == ['note1'] and r.get('lost') == 0
              and r.get('waitNotes') == 1, r)

        # ── round 5: the bug. The dialog outlives the occupant it named. ──
        r = rows.get('dialog-outlives-the-occupant', {})
        check('the boss was asked about the run that was there at the time',
              r.get('dialogsShown') == 1, r.get('dialogNamed'))
        check("the waiting note did claim the desk inside the dialog's gap",
              r.get('samsNoteStarted') is True,
              'the race did not set up — the scenario proves nothing')
        check('the note it actually stopped is REPORTED, not silent',
              r.get('displacementReported') is True,
              [r.get('samsNoteEvicted'), r.get('chatLines'), r.get('transitions')])
        trs = r.get('transitions') or []
        check('the displaced note is filed cancelled against its own record',
              any(t.get('state') == 'cancelled' and t.get('id') == 'msg_sam' for t in trs),
              trs)
        check('the team room names whose note it was',
              any("Sam's note" in (t or '') and 'took the desk' in (t or '')
                  for t in (r.get('chatLines') or [])),
              r.get('chatLines'))

    print()
    if FAILS:
        print(f'waited-its-turn: {len(FAILS)} FAILED')
        for f in FAILS:
            print('   - ' + f)
        return 1
    print('waited-its-turn: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
