#!/usr/bin/env python3
"""One truncated write, told to the boss twice, the second time wrongly.

Measured live (#144, office 8847). The CEO's own brain was offline and the
office said so well -- "Llama is still working, though -- @mention them and
they can pick this up." Taking that advice, Llama answered:

    I've saved a note to start building my memory with
    [MEMORY_WRITE: decisions/intro.md].

An opener with no closer. Underneath the bubble, stacked:

    _(nothing was saved to their memory -- they started the note and stopped
      partway, so it is not there however it was described above. Ask them to
      save it again.)_
    _(`decisions/intro.md` is named above, but they never wrote it to the
      cabinet on this run -- ask them to file it if you need it.)_

One fact, twice, and the second wrong twice over. It describes a different
failure ("never wrote it" against "started and stopped partway"), so a boss
counting problems counts two; and it names the CABINET for a path that was
never headed there. MEMORY_WRITE goes to the coworker's own notes folder,
which is precisely why app/artifacts.jsx's CABINET_WRITE leaves the MEMORY_*
markers out -- "not a deliverable for the boss". So its closing advice asked
the boss to chase a file into a drawer it was never going into.

`unsentBlocks` owns the truncated-marker story and tells it accurately.
`unfiledPath` is about a filename promised IN PROSE with no file behind it --
its own section head says so. A path inside `[MEMORY_WRITE: ...]` is machine
syntax, not a promise in the boss's words, so it is no longer counted.

The narrowness matters in one direction: a coworker who says "saved to
Research/x.md" in prose AND emits a truncated marker for it has still made
the claim the boss read, so that note must survive. Both directions are
checked below, against the real functions lifted from the app.
"""
import json
import os
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


def lift(src, name):
    i = src.index('function %s(' % name)
    j = src.index('{', i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + name)


def const(src, decl):
    i = src.index(decl)
    return src[i:src.index(';\n', i) + 1]


RT = open(os.path.join(ROOT, 'hq-runtime.jsx')).read()
AR = open(os.path.join(ROOT, 'app', 'artifacts.jsx')).read()

HARNESS = """
%s

const M = `I've saved a note to start building my memory with [MEMORY_WRITE: decisions/intro.md].`;
const P = `I saved the brief to Research/plan.md and filed it for you.`;
const B = `Saved to Research/plan.md — [VAULT_NEW: Research/plan.md]`;
const CLOSED = `Filed it. [VAULT_NEW: Research/plan.md]body[/VAULT_NEW]`;
const TWO = `Notes in [MEMORY_WRITE: decisions/a.md] and the brief in Reports/b.md.`;
const NONE = `Nothing to report today.`;

console.log(JSON.stringify({
  markerOnlyPath:  unfiledPath(M, [], unwrittenPaths),
  markerOnlyBlock: unsentBlocks(M, []),
  prosePath:       unfiledPath(P, [], unwrittenPaths),
  bothPath:        unfiledPath(B, [], unwrittenPaths),
  closedBlock:     unsentBlocks(CLOSED, []),
  twoPath:         unfiledPath(TWO, [], unwrittenPaths),
  nonePath:        unfiledPath(NONE, [], unwrittenPaths),
  unknowable:      unfiledPath(M, null, unwrittenPaths),
}));
"""


def main():
    pieces = [const(AR, 'const CABINET_WRITE ='), const(AR, 'const CLAIMED_PATH =')]
    for n in ('claimedPaths', 'agentFiledPath', 'normVisitPath', 'unwrittenPaths'):
        pieces.append(lift(AR, n))
    # `unfiledPath` alone: its marker scan is inline precisely so that the
    # five other suites that lift it by name keep working. Lifting a helper
    # here that they cannot see would hide the breakage this file caused.
    for n in ('unsentBlocks', 'unfiledPath'):
        pieces.append(lift(RT, n))

    tmp = tempfile.mkdtemp(prefix='one-note-')
    r = {}
    try:
        p = os.path.join(tmp, 'c.mjs')
        with open(p, 'w') as fh:
            fh.write(HARNESS % '\n'.join(pieces))
        proc = subprocess.run([shutil.which('node') or 'node', p],
                              capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            print("  FAIL node harness errored: " + proc.stderr.strip()[:400])
            failures.append('node harness')
        else:
            r = json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if not r:
        return 1

    print("1. the truncated write is reported once, by the guard that knows it")
    # THE bug. Both notes render under one bubble, so this is what the boss read.
    check("a path named only inside a marker gets no second note",
          r['markerOnlyPath'] is None,
          repr(r['markerOnlyPath']) + ' — stacked under the marker note, this '
          'reads as a second, different failure')
    check("...and the marker guard still tells the boss what happened",
          r['markerOnlyBlock'] and 'stopped partway' in r['markerOnlyBlock'],
          '— suppressing the duplicate must not leave the failure unreported')
    # The wrong-drawer half: whatever survives must not be sent to the cabinet
    # for a memory write. Checked through the note, not the vocabulary, so a
    # reworded note still has to get the destination right.
    check("...so nothing tells the boss to file a memory note in the cabinet",
          'cabinet' not in (r['markerOnlyPath'] or ''),
          '— MEMORY_WRITE goes to the coworker\'s own notes; CABINET_WRITE '
          'excludes it for exactly that reason')

    print("2. the promise this note exists for is untouched")
    check("a filename promised in prose is still called out",
          r['prosePath'] and 'Research/plan.md' in r['prosePath'],
          repr(r['prosePath']) + ' — this is the whole point of the note')
    # The narrowing must not become a loophole: emitting a truncated marker
    # for a path you ALSO claimed in prose would otherwise buy silence.
    check("...including when a truncated marker names it too",
          r['bothPath'] and 'Research/plan.md' in r['bothPath'],
          repr(r['bothPath']) + ' — the prose claim is what the boss read')
    check("a path in prose survives alongside one that is marker-only",
          r['twoPath'] and 'Reports/b.md' in r['twoPath']
          and 'decisions/a.md' not in r['twoPath'],
          repr(r['twoPath']) + ' — the filter is per path, not per reply')

    print("3. the quiet cases stay quiet")
    check("a reply naming no path says nothing", r['nonePath'] is None)
    check("a properly closed marker is not reported as truncated",
          r['closedBlock'] is None, repr(r['closedBlock']))
    # Unchanged contract, re-checked because the filter runs before it would
    # have mattered: a path that cannot count what it opened knows nothing.
    check("an unknowable visit log stays silent", r['unknowable'] is None)

    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures[:6]))
        return 1
    print("PASS: one failure reaches the boss as one note")
    return 0


if __name__ == '__main__':
    sys.exit(main())
