#!/usr/bin/env python3
"""The Library called itself empty while it was still being read.

Measured live on a fresh office (#142), the first-run payoff path:

  Llama filed Sites/simple-page-a-one-page-site-for-my-dog-walking-
  business.html. The FIRST DELIVERY sheet said "filed it in your cabinet"
  and named the path, over one button: "Open the page →".

  BEFORE: that button landed on
          "📓 Your Library is empty · Notes, research, decks, documents
          and images all live here — and your coworkers file their
          deliveries here too. · [➕ Write your first note]"
          The file was on disk the whole time. Six seconds later the tree
          showed it, with a Preview. The office contradicted itself on the
          one screen the whole first run pays off on.
  AFTER:  the loading screen holds until the listing has settled, so the
          first thing the boss reads is the file they were sent to open.

`views/vault.jsx` renders `!status` as the loading moment and `files.length
=== 0` as the empty state. Those are two different round trips: vaultStatus()
answers "is there a cabinet", vaultList() answers "what is in it". `refresh`
set status between them, so a resolved status over an unfilled `files` -- the
ordinary state of this view for the width of one fetch -- rendered as an
established fact.

The bridge branch of the same function always landed `files` first and never
showed this. Two orderings of one sequence in one function, one of them
wrong. The checks below run the real `refresh` under Node against a listing
that answers late, and assert on what the view would have rendered AT THAT
MOMENT -- not on the order of two statements, which is the detail rather than
the promise.
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
    """Blank comment bodies, keeping newlines so offsets stay usable.

    Quote-aware. This file's fix is explained in a comment that quotes the
    empty state's own words, so a naive strip finds the documentation and
    reports the code is fine.
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


def balanced(src, open_at):
    depth = 0
    for k in range(open_at, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return k
    raise AssertionError('unbalanced braces')


VAULT_RAW = open(os.path.join(ROOT, 'views', 'vault.jsx')).read()
VAULT = strip_js_comments(VAULT_RAW)


def main():
    # Measured across a REGION rather than by one phrase, so rewording a
    # comment can neither fail this nor quietly disarm it.
    #
    # The region, and not the whole file, because the stripper is quote-aware
    # and this file's JSX prose contains apostrophes: `The cabinet won't open`
    # at ~1383 opens a string that never closes, and the seven comments below
    # that line survive. Harmless and out of reach -- everything these checks
    # read (`refresh` at ~452, `emptyTreeState` at ~1220) is above it -- but
    # only if the measure says so out loud instead of being relaxed to a
    # threshold that would also pass on a stripper that had stopped working.
    cut = VAULT.index('const emptyTreeState')
    head_raw, head = VAULT_RAW[:cut], VAULT[:cut]
    check("comment stripping removed every block comment it is relied on for",
          head_raw.count('/*') > 30 and head.count('/*') == 0,
          f"{head_raw.count('/*')} raw, {head.count('/*')} left above the cut")
    check("...without moving any line", len(VAULT) == len(VAULT_RAW))

    print("1. the empty state is still what the view shows for an empty Library")
    # If this stops being true the harness below is measuring nothing, so it
    # is checked rather than assumed.
    check("`files.length === 0` is what renders the welcome",
          re.search(r"const emptyTreeState = files\.length === 0 \?", VAULT),
          '— the empty state is keyed on something else now')
    check("...and `!status` is what renders the loading moment",
          re.search(r"\n  if \(!status\) \{", VAULT))

    print("2. the real refresh, run against a listing that answers late")
    try:
        i = VAULT.index('const refresh = async () => {')
        body = VAULT[i:balanced(VAULT, VAULT.index('{', i)) + 1]
    except (ValueError, AssertionError) as e:
        print(f"FAILED: could not lift refresh ({e})")
        return 1

    # The whole point is WHEN each setter fires relative to the other, so the
    # harness records a frame on every state change and asks what the view
    # would have put on screen in each one. `_bridge` is null, exercising the
    # server branch -- the one that was wrong.
    harness = """
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function run(opts) {
  opts = opts || {};
  let status = null, files = [];
  const frames = [];
  const snap = () => frames.push({
    // Exactly the two conditions views/vault.jsx renders on.
    loading: !status,
    empty: !!status && status.configured && files.length === 0,
    n: files.length,
  });
  const setStatus = (v) => { status = v; snap(); };
  const setFiles  = (v) => { files = v;  snap(); };
  const setErr = () => {};
  const _bridge = null;
  const refreshGraph = () => {};
  const _refreshHits = async () => {};
  const bridgeSearch = async () => [];
  const _adaptBridgeFiles = (f) => f;
  const CafresoHQClient = {
    vaultStatus: async () => {
      if (opts.statusThrows) throw new Error('bridge down');
      return opts.status || { configured: true, exists: true, backend: 'fs' };
    },
    vaultList: async () => {
      // The gap the bug lived in: the listing is a SECOND round trip.
      await sleep(opts.listDelay === undefined ? 25 : opts.listDelay);
      if (opts.listThrows) throw new Error('could not list');
      return opts.files || [];
    },
  };
  %s
  await refresh();
  return { frames, endStatus: status, endFiles: files.length };
}

const FILED = [{ path: 'Sites/dog-walking.html', kind: 'page' }];

const filed    = await run({ files: FILED });
const slow     = await run({ files: FILED, listDelay: 120 });
const truly    = await run({ files: [] });
const noVault  = await run({ status: { configured: false } });
const listFail = await run({ files: FILED, listThrows: true });
const statFail = await run({ statusThrows: true });

const claimedEmpty = (r) => r.frames.some(f => !f.loading && f.empty);
const everShowed   = (r) => r.frames.some(f => !f.loading && !f.empty && f.n > 0);

console.log(JSON.stringify({
  filedClaimedEmpty:  claimedEmpty(filed),
  filedEverShowed:    everShowed(filed),
  slowClaimedEmpty:   claimedEmpty(slow),
  trulyClaimedEmpty:  claimedEmpty(truly),
  trulyEnd:           truly.endFiles,
  noVaultConfigured:  noVault.endStatus.configured,
  noVaultClaimedEmpty: claimedEmpty(noVault),
  listFailClaimedEmpty: claimedEmpty(listFail),
  listFailEnd:        listFail.endStatus ? listFail.endStatus.configured : null,
  statFailEnd:        statFail.endStatus ? statFail.endStatus.configured : null,
  filedEnd:           filed.endFiles,
}));
""" % body

    tmp = tempfile.mkdtemp(prefix='library-empty-')
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
        # THE bug: one file filed, and at no point may the view say there are
        # none. This is the frame the boss actually read after pressing
        # "Open the page →".
        check("a Library holding a delivery is never announced as empty",
              r.get('filedClaimedEmpty') is False,
              '— "Your Library is empty · Write your first note" over a file '
              'the delivery sheet just named')
        check("...and it does end up showing the file",
              r.get('filedEverShowed') is True and r.get('filedEnd') == 1)
        # Widening the gap is the honest stress: a bigger cabinet, a slower
        # disk, or the Obsidian REST / OCI backends make it much longer than
        # the 25ms that was enough to catch it live.
        check("...still not, when the listing is slow to come back",
              r.get('slowClaimedEmpty') is False)

        # The empty state must keep working. A fix that just never showed it
        # would trade a false claim for a blank screen, which #142's own
        # comment calls the worse of the two.
        check("a Library that really is empty still says so",
              r.get('trulyClaimedEmpty') is True and r.get('trulyEnd') == 0,
              '— the first-run welcome is the only door a new boss has')

        print("3. the failure paths still reach a screen")
        # Not the empty state: no cabinet has its own screen (`!status
        # .configured`), and reaching the welcome instead would invite the
        # boss to write a note there is nowhere to put.
        check("no cabinet configured goes to its own screen, not the welcome",
              r.get('noVaultConfigured') is False
              and r.get('noVaultClaimedEmpty') is False)
        # A listing that fails must not hang on the loading screen forever --
        # the error needs a rendered view to sit in.
        check("a listing that fails still resolves the view",
              r.get('listFailEnd') is True,
              '— status left null would hold the loading screen for good')
        # ...and having failed, "empty" is the honest reading: the office has
        # nothing to show and says so, with setErr's message above it.
        check("...and reports the nothing it has, rather than a stale tree",
              r.get('listFailClaimedEmpty') is True)
        check("an unreachable bridge resolves too",
              r.get('statFailEnd') is False)

    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures[:6]))
        return 1
    print("PASS: the Library calls itself empty only once it has looked")
    return 0


if __name__ == '__main__':
    sys.exit(main())
