#!/usr/bin/env python3
"""The ✕ on a task card stopped somebody's note, and named the card.

#394 opened a class and closed two of its doors: an observation made BEFORE
an `await`, acted upon AFTER it, when the observed thing can change during
the wait. Both doors it fixed were claim sites (onDelegate's hand-off,
onTaskDropOnAgent's ▶ START). This is the sweep of the rest, and it found
the same bug at a third door nobody had looked at — plus one place where
#391's own SAFE verdict was wrong.

ONE — onDeleteTask (app.jsx). The handler computes

    const running = t.status === 'doing' && !t.blockedReason && !!t.assignedTo
      && agentAbortersRef.current.has(t.assignedTo);

then raises `${who} is working on "…" right now.\\n\\nDelete it and stop
them?` and, on yes, runs `abortAgentRun(t.assignedTo)`. The abort takes
whatever is on that desk WHEN THE DIALOG CLOSES. A modal is open for as
long as the boss leaves it open, and dispatchToAgent's busy-desk poll
re-tests the desk every 750ms — so a note that queued behind this same
desk can wake inside the gap (the CARD's own run having finished on its
own), claim the cleared desk, start streaming, and be the thing the ✕
kills. Measured 2026-09-05 via scripts/harness_delete_desk_race.mjs with
the REAL handler, the REAL deferral block and the REAL registry:
`samsNoteStarted: true, samsNoteEvicted: true, displacementReported:
false` — no team-room line, no registry transition, and the record stays
`in_progress` forever. The boss was asked about a card and answered about
a card; a coworker's note was the thing that stopped.

Fixed with #394's own precedent, not a new mechanism: `displaceDeskNote`,
called with the desk's occupant AS OBSERVED before the ask, with nothing
awaitable between the report and the abort. Unchanged desk, it says
nothing. Changed desk, the boss's gesture still wins and the note it
actually displaced is filed `cancelled` / `kind: 'displaced'` / retryable
with one team-room line. Written as its own statement rather than a brace
around the abort, so the `if (running) abortAgentRun(t.assignedTo);`
marker that test_a_delete_stops_only_its_own_run.py pins does not move.

TWO — the night-shift poll (app.jsx ~1296). #391 swept the night-run XP
guard (`experienceRef.current.some(e => e.taskId === r.id)`) and filed it
SAFE for two reasons: "it runs inside the serialised poll above", and
"xpRecord enforces one-done-per-taskId at WRITE time". The first names the
wrong poll — the serialised one is the chain/wallet poll three thousand
lines away, and this one had no latch at all while being fired from three
places (mount, a 15s interval, every visibilitychange). The second is half
a backstop: xpRecord dedupes 'done' only, and `logActivity` dedupes
nothing. Driven with the poll lifted whole (its own scope, so a latch is
genuinely shared) and called twice 5ms apart: a FAILED overnight run went
into the résumé ledger TWICE, and a run of either ending filed TWO
notification rows. Fixed with the sibling poll's own idiom — `polling`
beside `stop`, released in a `finally`.

Run: python3 scripts/test_the_x_on_a_card_stopped_a_note_it_never_named.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
HARNESS = ROOT / 'scripts' / 'harness_delete_desk_race.mjs'
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
                return src[i:k + 1]
    raise AssertionError('unbalanced braces after ' + header)


def run_harness():
    out = subprocess.run(['node', str(HARNESS), str(APP)],
                         capture_output=True, text=True, timeout=180)
    if out.returncode != 0:
        print('  FAIL  harness did not run  — ' + (out.stderr or '')[-900:])
        FAILS.append('harness did not run')
        return {}
    rows = {}
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        rows[r.get('scenario')] = r
    return rows


def main():
    print('the ✕ on a card stopped a note it never named')
    app = APP.read_text(encoding='utf-8')
    bare = strip_comments(app)
    delete_fn = brace_lift(bare, 'const onDeleteTask = async (id) =>')

    # ── round 1: the delete door, structurally ──────────────────────────
    check('the delete door holds the desk it observed across the ask',
          re.search(r'const priorRun = t\.assignedTo \? '
                    r'agentAbortersRef\.current\.get\(t\.assignedTo\) : null;',
                    delete_fn) is not None,
          'the report needs the occupant AS OBSERVED, not the one that is '
          'there once the boss answers')
    check('...and the name it put in the dialog outlives the branch',
          delete_fn.index('const who =') < delete_fn.index('window.hqConfirm'),
          '`who` was declared inside the `if (running)` block, so nothing '
          'after the ask could say whose desk the dialog had described')
    check('the delete door reports a displacement, exactly once',
          delete_fn.count('displaceDeskNote(') == 1,
          'one door, one report — a second call would file the same note twice')
    check('...naming the deletion as what took the desk',
          re.search(r'displaceDeskNote\(t\.assignedTo, who, priorRun, '
                    r'`deleting "\$\{t\.title\}"`\)', delete_fn) is not None,
          'the sentence the boss reads has to say which gesture did it')
    check('...gated on the same `running` the abort is gated on',
          re.search(r'if \(running\) displaceDeskNote\(', delete_fn) is not None,
          'a delete that never aborts displaces nothing; reporting there '
          'would be the report telling its own lie')

    # The marker #394 was careful about, and this fix is careful about too.
    check('the pinned abort marker did not move',
          re.search(r'if \(running\) abortAgentRun\(t\.assignedTo\);', bare)
          is not None,
          'test_a_delete_stops_only_its_own_run.py pins this exact text; '
          'bracing it to fit the report in would have broken that test')
    check('the full in-flight witness is still what decides',
          re.search(r"const running = t\.status === 'doing' && !t\.blockedReason"
                    r' && !!t\.assignedTo\s*&& agentAbortersRef\.current\.has\('
                    r't\.assignedTo\);', bare) is not None,
          'this fix must not weaken #86/#a-delete-stops-only-its-own-run')

    # ── the load-bearing negative: the report must not re-open its own gap ─
    d_at = delete_fn.find('displaceDeskNote(')
    a_at = delete_fn.find('abortAgentRun(t.assignedTo)')
    check('the report observes and the abort acts with no await between them',
          -1 < d_at < a_at
          and re.search(r'\bawait\b', delete_fn[d_at:a_at]) is None,
          'the report reads the desk to decide whether it changed hands; an '
          'await here re-opens the very window it closes — the same property '
          '#394 pinned at the other two doors')

    # ── round 2: the night-shift poll's missing latch ───────────────────
    night = bare[bare.index('const [nightShiftPending, setNightShiftPending]'):]
    night = night[:night.index('const [workflows, setWorkflows]')]
    check('the night-shift poll declares a re-entrancy latch',
          'let stop = false, polling = false;' in night,
          'three triggers (mount, a 15s interval, every visibilitychange) and '
          'nothing serialising them; #391 filed this SAFE by citing the '
          "chain/wallet poll's latch, which is a different poll")
    check('...and refuses to start while one is already in flight',
          'if (document.hidden || stop || polling) return;' in night
          and re.search(r'if \(document\.hidden \|\| stop \|\| polling\) return;'
                        r'\s*polling = true;', night) is not None,
          'claimed on the statement after the test, with nothing between')
    check('...and releases in a `finally`, not at each return',
          re.search(r'finally \{ polling = false; \}', night) is not None,
          '#392\'s rule: a release written at each terminal point is one a '
          'later edit will miss, and a missed one here is a board that never '
          'updates again')
    check('the sibling poll it borrows the idiom from still has its own',
          'if (dead || polling || document.hidden) return;' in bare,
          'the chain/wallet poll is the precedent; if it ever loses its latch '
          'this comment stops being true')

    # ── behavior, through the real lifted source ────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — behavior checks need it')
    else:
        rows = run_harness()

        r = rows.get('delete-dialog-outlives-the-run', {})
        check('the dialog really did name the card, not the note',
              r.get('dialogNamedTheCard') is True, r.get('dialogs'))
        check("the waiting note did claim the desk inside the dialog's gap",
              r.get('samsNoteStarted') is True,
              'the race did not set up — the scenario proves nothing')
        check('the note the ✕ actually stopped is REPORTED, not silent',
              r.get('displacementReported') is True,
              [r.get('samsNoteEvicted'), r.get('chatLines'), r.get('transitions')])
        trs = r.get('transitions') or []
        check('...filed cancelled against its own record',
              any(t.get('state') == 'cancelled' and t.get('id') == 'msg_sam'
                  for t in trs), trs)
        check('...with a team-room line naming whose note it was',
              any("Sam's note" in (t or '') and 'took the desk' in (t or '')
                  for t in (r.get('chatLines') or [])),
              r.get('chatLines'))
        check('...and the boss still gets the deletion they asked for',
              r.get('cardDeleted') is True and r.get('abortFired') is True,
              [r.get('cardDeleted'), r.get('abortFired')])

        r = rows.get('delete-on-an-unchanged-desk', {})
        check('an unchanged desk gets no line at all',
              r.get('saidAnything') == [] and (r.get('transitions') or []) == [],
              [r.get('saidAnything'), r.get('transitions')])
        check('...and the card\'s own run is still the thing that stops',
              r.get('cardRunAborted') is True and r.get('cardDeleted') is True, r)

        r = rows.get('delete-declined', {})
        check('a declined delete keeps the card AND the note that took the desk',
              r.get('cardDeleted') is False and r.get('abortFired') is False
              and r.get('samsNoteDelivered') is True, r)
        check('...and says nothing, because nothing was displaced',
              r.get('displacementReported') is False, r.get('chatLines'))

        r = rows.get('night-poll-reentrancy-snag', {})
        check('two overlapping night polls file ONE snag on the résumé',
              r.get('xpCallsMade') == 1 and r.get('ledgerEntries') == 1,
              [r.get('xpCallsMade'), r.get('ledgerEntries'),
               "— xpRecord's write-time guard covers 'done' only, so a "
               'failed overnight run had no backstop at all'])
        check('...and ONE notification row',
              r.get('activityRows') == 1, r.get('activityText'))

        r = rows.get('night-poll-reentrancy-done', {})
        check('two overlapping night polls file ONE finished-run row',
              r.get('activityRows') == 1, r.get('activityText'))
        check('...and one XP call, not one deduped write behind two calls',
              r.get('xpCallsMade') == 1, r.get('xpCallsMade'))

        r = rows.get('night-poll-sequential', {})
        check('a poll started AFTER the first one ended still runs in full',
              r.get('boardRefreshes') == 2, r.get('boardRefreshes'))

    print()
    if FAILS:
        print(f'stale-observation sweep: {len(FAILS)} FAILED')
        for f in FAILS:
            print('   - ' + f)
        return 1
    print('stale-observation sweep: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
