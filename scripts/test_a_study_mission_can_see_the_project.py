#!/usr/bin/env python3
"""A project-study mission fetched its file tree from the wrong address.

`runMissionIteration` (missions.jsx) opens a project-study round by listing
the project directory so the prompt can tell the coworker WHICH files exist
to read. It did that with a hard-coded, page-root request:

    const res = await fetch('/tools/exec', { ... DIR_LIST ... });
    const data = await res.json();
    if (data.ok) { ...build fileTree... }

The office's API is not at the page root. `_API_BASE` (claude-client.jsx)
resolves to '/u/<slug>' when Caddy serves the office behind the gateway, and
to an entirely different ORIGIN when the UI is on the ICP canister and the
shell injects `?api=https://hq.cafreso.com/u/<slug>`. Every other tool call
in the office goes through `CafresoHQClient.toolExec`, which prefixes that
base — hq-runtime.jsx's FILE_READ, DIR_LIST, FILE_WRITE and BASH all do.
This one call site did not, so on every hosted deployment the POST landed on
a path that isn't the API: 404 (or an HTML error page, whose .json() throws
into the swallowing `catch (_e) {}`). Either way `fileTree` stayed empty and
`buildProjectStudyPrompt` rendered its fallback:

    Project file tree (top-level):
      (could not list files)

...to an agent whose brief that same prompt states as "Read 1-3 files to
understand how something works" — every round, for the whole mission. A
study mission that cannot see the project writes the night away guessing.

The same `if (data.ok)` carried the second half of the defect: DIR_LIST
SOFT-fails. serve.py answers a bad path with `ok: True, failed: True,
result: 'Not a directory: <path>'` (the coworker needs that text to
recover), so the old check accepted the error sentence and listed it to the
agent as if it were a file in the tree.

Fix: route the listing through `CafresoHQClient.toolExec('DIR_LIST', path,
{ meta })` — the same client every other tool call uses, so it inherits the
API base — and consult `meta.failed` so a soft failure yields no tree
instead of a fabricated one.

This test (a) checks no bare root-relative /tools/exec fetch remains in
missions.jsx, (b) extracts the REAL fileTree block from the source and
EXECUTES it in node against stubs: a `fetch` that fails the test if it is
touched at all, and a `CafresoHQClient.toolExec` that records its arguments
and can be made to soft-fail.

Run: python3 scripts/test_a_study_mission_can_see_the_project.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MISSIONS = ROOT / 'missions.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('a project-study mission can actually see the project')
    if not MISSIONS.is_file():
        check('missions.jsx exists', False, str(MISSIONS))
        return 1
    src = MISSIONS.read_text(encoding='utf-8')
    # Prose about the old call (this fix leaves a note explaining it) is not
    # the old call. Judge the CODE.
    code = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    code = re.sub(r'(^|\s)//[^\n]*', r'\1', code)

    # ── 1. The regression itself: no page-root API request anywhere ──────
    check("missions.jsx never fetches a root-relative '/tools/exec' — that "
          "address is only correct when _API_BASE happens to be '', i.e. "
          "localhost dev, and silently wrong on every hosted deployment",
          not re.search(r"fetch\(\s*['\"]/tools/", code),
          'found a hard-coded page-root tool call')

    check("the project file tree is listed through CafresoHQClient.toolExec"
          "('DIR_LIST', ...) — the one client that carries _API_BASE, the "
          "same one hq-runtime.jsx's own DIR_LIST tool uses",
          bool(re.search(
              r"CafresoHQClient\.toolExec\(\s*'DIR_LIST'\s*,\s*mission\.projectPath",
              src)))

    check("the listing consults the soft-failure flag (meta.failed) — "
          "DIR_LIST answers a bad path with ok:true and 'Not a directory: "
          "<path>' as the RESULT, which the old `if (data.ok)` listed to "
          "the agent as a filename",
          bool(re.search(r'if \(!meta\.failed\)', src)))

    check("buildProjectStudyPrompt still has its honest fallback for a "
          "genuinely unlistable path (this fix must not paper over a real "
          "failure with a fake tree)",
          "'  (could not list files)'" in src)

    # ── 2. Execute the real extracted block ──────────────────────────────
    block = re.search(
        r'  let fileTree = \[\];\n'
        r'  if \(mission\.type === .project-study. && mission\.projectPath\) \{\n'
        r'.*?\n'
        r'  \}\n',
        src, re.S)
    check('the fileTree block extracts cleanly from runMissionIteration',
          block is not None)
    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the block)',
          has_node, 'skipping the live-execution check')

    if block and has_node:
        body = block.group(0)
        js = """
        async function drive(opts) {
          const calls = [];
          let bareFetch = false;
          const fetch = async () => { bareFetch = true; throw new Error('no'); };
          const CafresoHQClient = {
            toolExec: async (tool, arg, o) => {
              calls.push({ tool, arg });
              if (o && o.meta) o.meta.failed = !!opts.softFail;
              return opts.listing;
            },
          };
          const mission = { type: 'project-study', projectPath: '/srv/proj' };
        __BODY__
          return { calls, bareFetch, fileTree };
        }
        (async () => {
          const good = await drive({ listing: 'src/\\nREADME.md  (12 B)', softFail: false });
          const bad  = await drive({ listing: 'Not a directory: /srv/proj', softFail: true });
          console.log(JSON.stringify({ good, bad }));
        })();
        """.replace('__BODY__', body)
        proc = subprocess.run([shutil.which('node'), '-e', js],
                              capture_output=True, text=True, timeout=30)
        check('the extracted block runs under node',
              proc.returncode == 0, (proc.stderr or '').strip()[:300])
        if proc.returncode == 0:
            out = json.loads(proc.stdout.strip().splitlines()[-1])
            good, bad = out['good'], out['bad']

            check('it never reaches for a bare fetch() — the page-root '
                  'request is gone, not merely relocated',
                  not good['bareFetch'] and not bad['bareFetch'])

            check("it calls toolExec('DIR_LIST', <the mission's project "
                  "path>) exactly once",
                  good['calls'] == [{'tool': 'DIR_LIST', 'arg': '/srv/proj'}],
                  good['calls'])

            check('a real listing still parses into the tree, directories '
                  'flagged — the fix must not break the working case',
                  good['fileTree'] == [{'name': 'src', 'isDir': True},
                                       {'name': 'README.md  (12 B)',
                                        'isDir': False}],
                  good['fileTree'])

            check("a SOFT failure (ok:true + 'Not a directory: …') yields NO "
                  "tree, instead of handing the agent the error sentence as "
                  "a filename",
                  bad['fileTree'] == [], bad['fileTree'])

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), '; '.join(FAILS)))
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
