#!/usr/bin/env python3
"""A stand-up whose closing summary TIMED OUT was recorded as the boss
having stopped it.

StandupModal's per-agent loop (features.jsx) is careful about exactly this
distinction: each coworker's turn gets its own `perAgent` AbortController,
and the catch tells the two apart —

    const userStopped = controller.signal.aborted;
    const timedOut = !userStopped && perAgent.signal.aborted;

The closing-summary pass right below it hung its 90s watchdog on the SAME
controller the ■ STOP button aborts:

    const sumTimeout = setTimeout(() => controller.abort(), STANDUP_TIMEOUT_MS);
    ...
    catch (err) { const stopped = controller.signal.aborted;

so `stopped` was true whether the boss pressed STOP or the watchdog fired,
and every surface downstream read that one flag. A local model taking over
90s to synthesise (STANDUP_TIMEOUT_MS is 90_000, and `isLocal` agents are
warned about as "may be slow" in this very modal) produced:

  · subtitle:  "reports in — no closing summary"
  · footer:    "you stopped this before the summary — RE-RUN for a full
                one, or ARCHIVE the reports as they are"
  · fullText(): "## Synthesis — stopped part-way" over "You stopped the
                stand-up before CafresoHQ finished the closing summary."
  · archive():  a DONE task on the board whose card face reads
                "...; you stopped it before the summary."

The last two OUTLIVE the modal. The office filed a record asserting an act
the boss never performed, and a boss reading it back a week later has no
way to tell it from a run they really did stop — while the true cause (the
brain never answered in time, i.e. RE-RUN may well hang again) is nowhere
on the record.

Fix: a `sumTimedOut` flag set by the watchdog before it aborts, so the
catch draws the same line the per-agent loop already draws, and the
timeout carries its own honest clause instead of borrowing the boss's.

Run: python3 scripts/test_standup_summary_timeout_is_not_blamed_on_the_boss.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURES = ROOT / 'features.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("A stand-up summary that timed out is not filed as 'you stopped it'")

    src = FEATURES.read_text(encoding='utf-8')

    # ---- the closing-summary pass, from setPhase('summarizing') to its finally
    m = re.search(r"setPhase\('summarizing'\);(.*?)\n\s*\}\s*finally\s*\{",
                  src, re.S)
    check("StandupModal's closing-summary pass is still there", m is not None)
    if m is None:
        return 1
    block = m.group(1)

    # ---- the watchdog must be distinguishable from the boss's STOP
    watchdog = re.search(r"const sumTimeout = setTimeout\((.*?), STANDUP_TIMEOUT_MS\);",
                         block, re.S)
    check('the summary watchdog is still armed', watchdog is not None)
    wd = watchdog.group(1) if watchdog else ''
    check('the watchdog records that IT fired, not just that something aborted '
          '(it shares `controller` with the ■ STOP button, so the abort flag '
          'alone cannot say which happened)',
          'sumTimedOut = true' in wd,
          'watchdog body: ' + wd.strip())

    # ---- the catch must not call a timeout "stopped"
    stopped = re.search(r"const stopped = ([^;]*);", block)
    check("the catch still computes `stopped`", stopped is not None)
    st = stopped.group(1) if stopped else ''
    check("`stopped` excludes the watchdog case (a timeout is not the boss "
          "pressing STOP — this is the same line the per-agent loop above "
          "already draws with its separate `perAgent` controller)",
          'sumTimedOut' in st,
          'stopped = ' + st.strip())

    # ---- and the timeout gets its own sentence, not the boss's and not a
    #      snagSentence() of an AbortError that says nothing about the wait
    snag = re.search(r"const snag = (.*?);\n", block, re.S)
    check('the catch still builds a snag sentence', snag is not None)
    sn = snag.group(1) if snag else ''
    check('a timed-out summary carries its own honest reason',
          'sumTimedOut' in sn, 'snag = ' + sn.strip())

    # ---- the record-writing surfaces still key off summaryFail === 'stopped',
    #      i.e. the fix has to hold at the flag, not by rewording downstream
    check("fullText() still writes the 'stopped part-way' heading only for "
          "summaryFail === 'stopped'",
          "if (summaryFail === 'stopped') {" in src)
    check("archive()'s card face still keys off the same value",
          "summaryFail === 'stopped' ? '; you stopped it before the summary.'" in src)

    # ---- the per-agent loop this borrows its rule from is untouched
    check('the per-agent loop still separates userStopped from timedOut',
          'const userStopped = controller.signal.aborted;' in src
          and 'const timedOut = !userStopped && perAgent.signal.aborted;' in src)

    print()
    if FAILS:
        print('FAILED: ' + ', '.join(FAILS))
        return 1
    print('All checks passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
