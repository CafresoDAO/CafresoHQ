#!/usr/bin/env python3
"""app/worklog.jsx exists so a DONE card can say who finished a job and when.
Its own comment records that `completedAt` and `completedBy` "were both stamped
on the record by the done handler and read by nothing" -- the read side was then
built (features.jsx renders `✓ <name> finished this · <when>`). But only ONE of
the task-completion write sites ever carried the stamps.

Measured end-to-end on a fresh office against a real local model: Llama finished
a starter research brief, filed it to the cabinet, and its DONE card read a bare
"✓ finished" -- no name, no time -- because the path that actually completes the
great majority of tasks (a run that came back having produced something) never
stamped either field. After the fix the same run renders
"✓ Llama finished this · just now".

Two halves:

  1. Behaviour: finishedLabel is extracted from app/worklog.jsx and RUN under
     Node -- it must stay silent without a stamp (never guessing from createdAt)
     and produce a real label with one.
  2. Wiring: every site that moves a TASK into done must stamp completedAt.
     `applyStatus` is the task-status helper, so an `applyStatus(x, 'done')` is
     unambiguously a task completion; the stand-up card is built as a literal
     and is checked by name. Comments are stripped first -- the fix's own
     comments discuss `completedAt` at length, which would satisfy a naive
     proximity search and let a genuinely unstamped site pass.
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


def strip_comments(src):
    """Blank comment BODIES, preserving newlines so line numbers stay accurate.
    Quote-aware so string literals survive."""
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


def read(rel):
    return open(os.path.join(ROOT, rel)).read()


def main():
    # ---- 1. finishedLabel behaves -----------------------------------------
    print("1. finishedLabel behaves under Node")
    worklog = read('app/worklog.jsx')
    parts = []
    for fn in ('function durationLabel(', 'function finishedLabel('):
        i = worklog.find(fn)
        if i == -1:
            print(f"  FAIL {fn} not found in app/worklog.jsx")
            return 1
        j = worklog.index('{', i)
        depth = 0
        for k in range(j, len(worklog)):
            if worklog[k] == '{':
                depth += 1
            elif worklog[k] == '}':
                depth -= 1
                if depth == 0:
                    parts.append(worklog[i:k + 1]); break
    check("finishedLabel and durationLabel lifted from app/worklog.jsx",
          len(parts) == 2)

    consts = re.search(r'const MIN = [^;]+;', worklog)
    harness = (consts.group(0) if consts else '') + '\n' + '\n'.join(parts) + """
const NOW = 1000000000;
const out = {
  noStamp:      finishedLabel({ status: 'done', createdAt: NOW - 90000 }, NOW),
  nullStamp:    finishedLabel({ status: 'done', completedAt: null }, NOW),
  justNow:      finishedLabel({ completedAt: NOW - 1000 }, NOW),
  minutesAgo:   finishedLabel({ completedAt: NOW - 5 * 60000 }, NOW),
  hoursAgo:     finishedLabel({ completedAt: NOW - 3 * 3600000 }, NOW),
};
console.log(JSON.stringify(out));
"""
    tmp = tempfile.mkdtemp(prefix='worklog-')
    r = {}
    try:
        p = os.path.join(tmp, 'w.mjs')
        with open(p, 'w') as fh:
            fh.write(harness)
        proc = subprocess.run([shutil.which('node') or 'node', p],
                              capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            print("  FAIL node harness errored: " + proc.stderr.strip()[:300])
            failures.append("node harness")
        else:
            r = json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if r:
        check("says nothing without a stamp (never guesses from createdAt)",
              r.get('noStamp') is None, repr(r.get('noStamp')))
        check("says nothing for an explicitly cleared stamp",
              r.get('nullStamp') is None, repr(r.get('nullStamp')))
        check("a fresh finish reads 'just now' (no 'ago')",
              r.get('justNow') == 'just now', repr(r.get('justNow')))
        check("an older finish takes the 'ago'",
              isinstance(r.get('minutesAgo'), str) and r['minutesAgo'].endswith('ago'),
              repr(r.get('minutesAgo')))
        check("hours are labelled too",
              isinstance(r.get('hoursAgo'), str) and r['hoursAgo'].endswith('ago'),
              repr(r.get('hoursAgo')))

    # ---- 2. every task completion stamps ----------------------------------
    print("2. every site that finishes a task stamps completedAt")
    for rel in ('app.jsx', 'features.jsx'):
        raw = read(rel)
        clean = strip_comments(raw)
        for m in re.finditer(r"applyStatus\([^;]*?'done'", clean):
            line = clean[:m.start()].count('\n') + 1
            window = clean[m.start():m.start() + 420]
            check(f"{rel}:{line} applyStatus(...,'done') stamps completedAt",
                  'completedAt' in window,
                  ' '.join(window[:110].split()))

    # The stand-up card is built as an object literal, not via applyStatus.
    feats = strip_comments(read('features.jsx'))
    m = re.search(r"title: `Stand-up[\s\S]{0,2000}?\}\);", feats)
    check("the stand-up archive card was found", m is not None)
    if m:
        check("the stand-up card, archived straight into done, stamps completedAt",
              'completedAt' in m.group(0))

    # Guard the decoy: the fix's comments are full of the word being searched
    # for, so a version of this test that skipped stripping would pass blind.
    app_raw = read('app.jsx')
    i = app_raw.find("applyStatus(t, produced ? 'done' : 'doing')")
    check("comment stripping is doing real work here",
          i != -1 and app_raw[max(0, i - 1200):i].count('completedAt') >= 1
          and strip_comments(app_raw)[max(0, i - 1200):i].count('completedAt') == 0)

    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures[:6]))
        return 1
    print("PASS: a finished card can say who finished it and when")
    return 0


if __name__ == '__main__':
    sys.exit(main())
