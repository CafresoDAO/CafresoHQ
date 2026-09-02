#!/usr/bin/env python3
"""Letting a coworker go left their research mission running.

Measured live on a fresh office, mission owned by Llama, then LET GO:

  BEFORE: the card read
          "RUNNING · (UNKNOWN) · 59M LEFT · next round in 28m · [STOP]"
          and the office counted it in "ACTIVE RESEARCH · 1 running".
          It would never run another round: the runner resolves the agent
          at fire time and bails. That is intervalMs away -- half an hour
          is an ordinary setting -- and when it finally happened the
          mission flipped to 'error' silently, with no line in the chat,
          no activity entry and no XP record, unlike every OTHER way a
          mission stops.
  AFTER:  "ERROR · (UNKNOWN) · warning: Llama was let go -- this mission
          has no researcher · [CLEAR]", "0 running", and the CEO says so.

Put through a reload instead of a dismissal the same mission read "paused
on reload -- resume to continue" over a RESUME button that could only ever
start a round with nobody to run it -- verified live by pressing it: the
card went straight back to RUNNING.

onDismiss purges tasks, approvals, projects and meetings for a leaving
coworker. Missions were the one thing it never touched, so every surface
downstream had to guess, and each guessed differently.
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

    Quote-aware, because this file's fix is explained in a comment that
    quotes the very strings the sweeps below look for -- a naive strip (or
    no strip) finds the documentation and reports the code is fine.
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


def block_from(src, opener):
    """Lift `opener` plus its balanced braces, from the real source."""
    i = src.index(opener)
    j = src.index('{', i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


APP_RAW = open(os.path.join(ROOT, 'app.jsx')).read()
APP = strip_js_comments(APP_RAW)


def main():
    # The strip has to actually bite: the fix is explained in a comment that
    # quotes the strings the sweeps look for, so a silent no-op would let
    # every check below pass on documentation. Measured against the file as
    # a whole rather than one phrase, so rewording a comment cannot fail
    # this and, more importantly, cannot quietly disarm it either.
    check("comment stripping removed every block comment",
          APP_RAW.count('/*') > 100 and APP.count('/*') == 0,
          f"{APP_RAW.count('/*')} raw, {APP.count('/*')} left")
    check("...without moving any line", len(APP) == len(APP_RAW),
          'offsets and line numbers below would be wrong')

    print("1. the close-out runs where every other trace is purged")
    try:
        dismiss = block_from(APP, 'const onDismiss = async (id) =>')
    except (ValueError, AssertionError) as e:
        print(f"FAILED: could not lift onDismiss ({e})")
        return 1
    check("onDismiss closes out the leaving coworker's missions",
          'strandedMissions' in dismiss and 'setMissions(' in dismiss,
          '— tasks, approvals, projects and meetings are all released here; '
          'a mission is the one that kept running')
    # Ordering: the close-out must read `missions` BEFORE setAgents drops
    # the agent, otherwise `leaving` still matches but the CEO line below
    # would be describing a roster that already changed under it.
    if 'strandedMissions' in dismiss and 'setAgents(' in dismiss:
        check("...and reads the mission list before the roster changes",
              dismiss.index('const strandedMissions') < dismiss.index('setAgents('))

    print("2. the close-out itself, lifted and run")
    try:
        decide = block_from(APP, 'const strandedMissions = missions.filter(')
        apply_blk = block_from(APP, 'if (strandedMissions.length) {')
    except (ValueError, AssertionError) as e:
        print(f"FAILED: could not lift the close-out ({e})")
        return 1
    # `decide` is a const declaration, not a block -- lift to its semicolon.
    decide = APP[APP.index('const strandedMissions = missions.filter('):]
    decide = decide[:decide.index(';') + 1]

    harness = """
function closeOut(missions, leaving, a) {
  let next = null;
  const setMissions = (fn) => { next = fn(missions); };
  %s
  %s
  // `next` stays null when setMissions was never called -- which is itself
  // the correct behaviour for a dismissal that stranded nothing, so the
  // result the caller reads is "what the list looks like afterwards".
  return { next, result: next || missions, stranded: strandedMissions.length };
}
const LEAVER = 'a1';
const mk = (o) => Object.assign({ id: 'm', agentId: 'a1', agentName: 'Llama',
  status: 'running', endedAt: null, pauseNote: null, lastError: '' }, o);
const run = (ms) => closeOut(ms, new Set([LEAVER]), { name: 'Llama' });

const running = run([mk({ id: 'r' })]);
const paused  = run([mk({ id: 'p', status: 'paused',
                          pauseNote: 'paused on reload \\u2014 resume to continue' })]);
const done    = run([mk({ id: 'd', status: 'done' })]);
const other   = run([mk({ id: 'o', agentId: 'a2' })]);
const quiet   = run([mk({ id: 'q', status: 'done' }), mk({ id: 'q2', agentId: 'a2' })]);
const noName  = run([mk({ id: 'n', agentName: null })]);
const kept    = run([mk({ id: 'k', status: 'paused', endedAt: 1234 })]);
const both    = run([mk({ id: 'b1' }), mk({ id: 'b2', status: 'paused' }),
                     mk({ id: 'b3', status: 'done' })]);

const one = (r) => r.result[0];
console.log(JSON.stringify({
  runningStatus: one(running).status,
  runningErr: one(running).lastError,
  runningEnded: !!one(running).endedAt,
  pausedStatus: one(paused).status,
  pausedNote: one(paused).pauseNote,
  doneStatus: one(done).status,
  doneUntouched: one(done) === null ? null : one(done).lastError,
  otherStatus: one(other).status,
  quietCalled: quiet.next !== null,
  quietCount: quiet.stranded,
  noNameErr: one(noName).lastError,
  keptEnded: one(kept).endedAt,
  bothCount: both.stranded,
  bothStatuses: both.next.map(m => m.status).join(','),
}));
""" % (decide, apply_blk)

    tmp = tempfile.mkdtemp(prefix='mission-strand-')
    r = {}
    try:
        p = os.path.join(tmp, 'c.mjs')
        with open(p, 'w') as fh:
            fh.write(harness)
        proc = subprocess.run([shutil.which('node') or 'node', p],
                              capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            print("  FAIL node harness errored: " + proc.stderr.strip()[:400])
            failures.append("node harness")
        else:
            r = json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if r:
        check("a running mission is closed out", r.get('runningStatus') == 'error',
              repr(r.get('runningStatus')))
        check("...naming who left, so the card is not just 'error'",
              'let go' in (r.get('runningErr') or ''), repr(r.get('runningErr')))
        check("...and stamped with when it stopped", r.get('runningEnded') is True)
        # The paused one is the RESUME dead-end: 'paused' is the only status
        # whose card offers a button that starts a round, and there is nobody
        # to run it.
        check("a PAUSED mission is closed out too, not left offering RESUME",
              r.get('pausedStatus') == 'error', repr(r.get('pausedStatus')))
        check("...and its stale 'resume to continue' note is cleared",
              r.get('pausedNote') is None, repr(r.get('pausedNote')))
        check("a finished mission is left alone -- it is history",
              r.get('doneStatus') == 'done' and not r.get('doneUntouched'))
        check("someone else's mission is untouched", r.get('otherStatus') == 'running')
        check("nothing is written when nothing was stranded",
              r.get('quietCalled') is False and r.get('quietCount') == 0)
        check("a mission with no recorded name falls back to the leaver's",
              'Llama' in (r.get('noNameErr') or ''), repr(r.get('noNameErr')))
        check("an existing endedAt is not overwritten -- it already stopped",
              r.get('keptEnded') == 1234, repr(r.get('keptEnded')))
        check("running and paused both count, done does not",
              r.get('bothCount') == 2 and r.get('bothStatuses') == 'error,error,done',
              repr(r.get('bothStatuses')))

    print("3. the boss is told, in words, once")
    # Every other way a mission stops announces itself. Lift the CEO line and
    # run it, because the thing that breaks a sentence like this is the
    # plural, and a regex over the template would never notice.
    try:
        say_blk = APP[APP.index('if (strandedMissions.length) {',
                                APP.index('has been let go.')):]
        say_blk = block_from(say_blk, 'if (strandedMissions.length) {')
    except (ValueError, AssertionError) as e:
        print(f"  FAIL could not lift the CEO line ({e})")
        failures.append('CEO line')
        say_blk = None

    if say_blk:
        h2 = """
const HQ = { uid: (p) => p + '1' };
function line(n) {
  const strandedMissions = new Array(n).fill(0);
  let said = [];
  const setChat = (fn) => { said = fn([]); };
  %s
  return said.length ? said[said.length - 1].text : null;
}
console.log(JSON.stringify({ one: line(1), three: line(3), none: line(0) }));
""" % say_blk
        tmp2 = tempfile.mkdtemp(prefix='mission-say-')
        r2 = {}
        try:
            p2 = os.path.join(tmp2, 's.mjs')
            with open(p2, 'w') as fh:
                fh.write(h2)
            proc2 = subprocess.run([shutil.which('node') or 'node', p2],
                                   capture_output=True, text=True, timeout=60)
            if proc2.returncode != 0:
                print("  FAIL CEO-line harness errored: " + proc2.stderr.strip()[:300])
                failures.append("CEO harness")
            else:
                r2 = json.loads(proc2.stdout.strip().splitlines()[-1])
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

        if r2:
            one, three = r2.get('one') or '', r2.get('three') or ''
            check("one stranded mission gets a singular sentence",
                  'mission ' in one and 'missions' not in one, repr(one))
            check("three get a plural one", '3 research missions' in three, repr(three))
            check("...and the plural agrees with itself",
                  'they have' in three and 'it has' not in three, repr(three))
            check("nothing is said when nothing stopped", r2.get('none') is None)
            # The notes are already in the vault. A boss reading "stopped"
            # with no more than that has every reason to think the round's
            # output went with it.
            check("the sentence says the written work survives",
                  'library' in one.lower() or 'vault' in one.lower(), repr(one))

    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures[:6]))
        return 1
    print("PASS: a mission does not outlive its researcher")
    return 0


if __name__ == '__main__':
    sys.exit(main())
