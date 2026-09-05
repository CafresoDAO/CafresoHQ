#!/usr/bin/env python3
"""A stand-up counted a coworker who never said a word as having reported.

features.jsx's StandupModal asks every coworker for a report in turn. A turn
has FOUR endings, and the modal already knows all four -- the per-agent loop
keeps the boss's STOP and the watchdog on separate AbortControllers precisely
so it can tell them apart:

  answered    the stream finished          text = what they said
  failed      the brain refused            text = '⚠ <snag>'      error true
  timed out   STANDUP_TIMEOUT_MS elapsed   text = buf + '…(timed out …)'
  stopped     the boss pressed STOP        text = buf + '…(stopped)'

`reported()` -- the one thing that counts them -- spelled only two of those
four: `r.text && !r.error`. The watchdog branch sets `error: false` on
purpose (a slow model is nobody's fault) and writes its label INTO `text`, so
the timed-out row satisfies both halves. A coworker whose local model never
loaded, who emitted zero tokens, was counted as having reported.

That count is not a modal ornament. archive() writes it into the `detail` of
a DONE task:

    End-of-day team stand-up — 3 of 3 reported.

filed on the board, read back days later with nothing left to check it
against, over a report body in which two of the three sections say only
"…(timed out — model too slow or unloaded)". The modal's own preflight
promises the opposite in so many words: "up to 45s before someone is counted
as not reporting".

The fix gives each row the ending it actually had (`outcome`) and counts the
one ending that means someone spoke -- and names the timeouts on the card,
because "1 of 3 reported" without a cause invites the boss to blame the two
coworkers for the machine.

This test lifts the REAL success block, the REAL catch block, and the REAL
counting expressions out of features.jsx and runs each ending through them.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}{(' -- ' + detail) if detail else ''}")
        failures.append(label)


def strip_js_comments(src):
    """Blank comment bodies, preserving newlines so offsets stay usable.

    Non-negotiable here: the fix is explained in a comment that quotes the
    old predicate verbatim, so an unstripped sweep would find the
    documentation of the bug and report the bug.
    """
    out, i, n, q = [], 0, len(src), None
    while i < n:
        c = src[i]
        if q:
            out.append(c)
            if c == '\\' and i + 1 < n:
                out.append(src[i + 1]); i += 2; continue
            if c == q:
                q = None
            i += 1
            continue
        if c in '"\'`':
            q = c; out.append(c); i += 1; continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2); j = n if j == -1 else j + 2
            out.append(''.join(x if x == '\n' else ' ' for x in src[i:j])); i = j; continue
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i); j = n if j == -1 else j
            out.append(' ' * (j - i)); i = j; continue
        out.append(c); i += 1
    return ''.join(out)


RAW = open(os.path.join(ROOT, 'features.jsx')).read()
SRC = strip_js_comments(RAW)


def lift(start_marker, end_marker, include_end=True):
    i = SRC.index(start_marker)
    j = SRC.index(end_marker, i)
    return SRC[i:(j + len(end_marker)) if include_end else j]


def main():
    # Prose, not a count: a handful of `/*` live inside string and regex
    # literals, which the stripper correctly leaves alone. What must be gone
    # is COMMENTARY -- §6 below greps for the old predicate, and this file's
    # own fix comment quotes it verbatim.
    check("comment stripping removed the commentary",
          'How many of the people who were asked' in RAW
          and 'How many of the people who were asked' not in SRC)
    check("...without moving any line", len(SRC) == len(RAW))

    print("1. the premise: the four endings really are distinguished upstream")
    check("the loop keeps a per-agent controller separate from the boss's STOP",
          'const perAgent = new AbortController();' in SRC
          and 'setTimeout(() => perAgent.abort(), STANDUP_TIMEOUT_MS)' in SRC)
    check("the watchdog row is deliberately NOT an error row",
          'error: !label' in SRC,
          "if this changes, the timeout no longer masquerades as a report")
    check("the preflight promises a timeout is counted as NOT reporting",
          'counted as not reporting' in SRC)
    check("the count is written into a DONE task's detail, not just the modal",
          re.search(r"detail: `End-of-day team stand-up[^`]*reported", SRC)
          is not None
          and re.search(r"status: 'done',", SRC) is not None)

    print("2. the endings, run through the real blocks lifted from features.jsx")
    try:
        success_blk = lift("const said = HQ.visibleReply(buf, a && a.name);",
                           "finished.push({ name: a.name, role: a.role, text: said });")
        catch_blk = lift("const userStopped = controller.signal.aborted;",
                         "setPhase('idle'); abortRef.current = null; return;")
        catch_blk += "\n        }\n"
        reported_fn = lift("const reported = () =>", "\n")
        timedout_fn = lift("const timedOut = () =>", "\n") \
            if "const timedOut = () =>" in SRC else ""
        detail_expr = lift("detail: `End-of-day team stand-up", ": '.'),")
    except ValueError as e:
        print(f"FAILED: could not lift the stand-up blocks ({e})")
        return 1

    check("the lifted success block is real code",
          'finished.push(' in success_blk and 'setReports(' in success_blk)
    check("the lifted catch block is real code",
          'timedOut' in catch_blk and 'setReports(' in catch_blk)
    check("a per-row ending field exists at all",
          'outcome' in reported_fn or 'outcome' in catch_blk,
          "no field distinguishes the four endings")

    detail_body = detail_expr[len("detail: "):].rstrip()
    if detail_body.endswith(','):
        detail_body = detail_body[:-1]

    harness = r"""
const HQ = { visibleReply: (b) => String(b || '') };
const snagSentence = (m) => 'couldn’t reach that brain';

function seed() {
  return [
    { agentId: 'a1', name: 'Ada', role: 'eng', text: '', streaming: true, error: false, outcome: null },
    { agentId: 'a2', name: 'Bo',  role: 'ops', text: '', streaming: true, error: false, outcome: null },
    { agentId: 'a3', name: 'Cy',  role: 'pm',  text: '', streaming: true, error: false, outcome: null },
  ];
}

/* Drive ONE agent's turn through the real blocks. `ending` picks which of
   the four happened; nothing else differs. */
function turn(reports, agentId, ending, buf) {
  const a = { id: agentId, name: 'x', role: 'r' };
  const finished = [];
  const setReports = (fn) => { const next = fn(reports); reports.length = 0; Array.prototype.push.apply(reports, next); };
  const setPhase = () => {};
  const abortRef = { current: null };
  const timeoutId = null;
  const onParentAbort = () => {};
  const controller = { signal: { aborted: ending === 'stopped', removeEventListener: () => {} } };
  const perAgent  = { signal: { aborted: ending === 'timeout' || ending === 'stopped' } };
  const err = new Error('OpenRouter 503');
  if (ending === 'reported') {
    SUCCESS_BLOCK
    return;
  }
  (function () {
    CATCH_BLOCK
  })();
}

function run(endings) {
  const reports = seed();
  const bufs = { reported: 'TODAY: shipped the thing.', error: '', timeout: '', stopped: 'TODAY: half a sen' };
  for (let i = 0; i < endings.length; i++) {
    turn(reports, 'a' + (i + 1), endings[i], bufs[endings[i]] || '');
    if (endings[i] === 'stopped') break;   // STOP returns out of the loop
  }
  const summaryFail = '';
  REPORTED_FN
  TIMEDOUT_FN
  return {
    rows: reports.map(r => ({ outcome: r.outcome, text: r.text, error: r.error, streaming: r.streaming })),
    reported: reported(),
    timedOut: typeof timedOut === 'function' ? timedOut() : null,
    detail: (DETAIL_EXPR),
  };
}

console.log(JSON.stringify({
  allReported:  run(['reported', 'reported', 'reported']),
  oneTimedOut:  run(['reported', 'timeout', 'reported']),
  allTimedOut:  run(['timeout', 'timeout', 'timeout']),
  oneFailed:    run(['reported', 'error', 'reported']),
  stoppedFirst: run(['stopped', 'reported', 'reported']),
}));
"""
    harness = (harness
               .replace('SUCCESS_BLOCK', success_blk)
               .replace('CATCH_BLOCK', catch_blk)
               .replace('REPORTED_FN', reported_fn)
               .replace('TIMEDOUT_FN', timedout_fn or 'const timedOut = null;')
               .replace('DETAIL_EXPR', detail_body))

    tmp = tempfile.mkdtemp(prefix='standup-endings-')
    r = {}
    try:
        p = os.path.join(tmp, 'h.mjs')
        with open(p, 'w') as fh:
            fh.write(harness)
        proc = subprocess.run([shutil.which('node') or 'node', p],
                              capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            print("  FAIL node harness errored: " + proc.stderr.strip()[:600])
            failures.append("node harness")
        else:
            r = json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if not r:
        print("FAILED: harness produced nothing")
        return 1

    print("3. each ending is its own fact")
    endings = {k: [row['outcome'] for row in v['rows']] for k, v in r.items()}
    check("a turn that finished is marked 'reported'",
          endings['allReported'] == ['reported', 'reported', 'reported'],
          repr(endings['allReported']))
    check("a turn the watchdog killed is marked 'timeout', not 'reported'",
          endings['oneTimedOut'][1] == 'timeout', repr(endings['oneTimedOut']))
    check("a turn the brain refused is marked 'error'",
          endings['oneFailed'][1] == 'error', repr(endings['oneFailed']))
    check("a turn the boss stopped is marked 'stopped'",
          endings['stoppedFirst'][0] == 'stopped', repr(endings['stoppedFirst']))
    check("...and so is every coworker still queued behind the STOP",
          endings['stoppedFirst'][1] == 'stopped'
          and endings['stoppedFirst'][2] == 'stopped',
          repr(endings['stoppedFirst']))
    check("no row is left bouncing 'typing' after a STOP",
          all(row['streaming'] is False for row in r['stoppedFirst']['rows']),
          repr(r['stoppedFirst']['rows']))

    print("4. THE COUNT: only the ending that means someone spoke")
    check("three real reports count as three",
          r['allReported']['reported'] == 3, repr(r['allReported']['reported']))
    check("A SILENT TIMED-OUT COWORKER IS NOT COUNTED AS HAVING REPORTED",
          r['oneTimedOut']['reported'] == 2,
          f"got {r['oneTimedOut']['reported']} of 3 -- rows "
          f"{endings['oneTimedOut']}")
    check("a stand-up where NOBODY answered counts zero",
          r['allTimedOut']['reported'] == 0,
          repr(r['allTimedOut']['reported']))
    check("a refused brain is not counted either (it never regressed)",
          r['oneFailed']['reported'] == 2, repr(r['oneFailed']['reported']))
    check("a stopped stand-up counts only whoever actually spoke",
          r['stoppedFirst']['reported'] == 0,
          repr(r['stoppedFirst']['reported']))

    print("5. what the DONE card on the board says a week later")
    check("the card is honest about how many spoke",
          '2 of 3 reported' in r['oneTimedOut']['detail'],
          repr(r['oneTimedOut']['detail']))
    check("...and does not read '3 of 3' over two silent coworkers",
          '3 of 3 reported' not in r['allTimedOut']['detail'],
          repr(r['allTimedOut']['detail']))
    check("...and names the machine as the cause, not the coworkers",
          'ran out of time' in r['allTimedOut']['detail'],
          repr(r['allTimedOut']['detail']))
    check("a clean stand-up's card gains no scare wording",
          r['allReported']['detail']
          == 'End-of-day team stand-up — 3 of 3 reported.',
          repr(r['allReported']['detail']))

    print("6. the old two-ending predicate is gone from the count")
    m = re.search(r'const reported = \(\) =>[^;]*;', SRC)
    check("reported() no longer counts by `text && !error`",
          m is not None and 'r.text' not in m.group(0),
          repr(m.group(0) if m else None))

    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures))
        return 1
    print("PASSED")
    return 0


if __name__ == '__main__':
    sys.exit(main())
