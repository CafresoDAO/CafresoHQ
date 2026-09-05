#!/usr/bin/env python3
"""The README's commands must not reach into directories this repo doesn't have.

`#295`'s audit found that a fresh clone can't follow its own quickstart and
fixed the build steps, but deliberately left the three `frontend/` references
alone, calling the choice between repointing and deleting them a decision
rather than a typo. It is a decision — but leaving them was the one option
that could not be right: `frontend/` was deleted in `8dbcc6f` (the SvelteKit
app moved to the sibling `cafreso-pages` repo), and the very FIRST command
under "Local development" was `npm --prefix frontend install`. A beta tester
following the file top to bottom hits an ENOENT before any of the corrected
steps, and nothing on the page says the directory is gone or where it went.

This test holds the general rule rather than the one path: every `cd <dir>`
and `npm --prefix <dir>` in a README fenced block must name a directory that
exists here, or explicitly point outside the checkout with `../`.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
fails = []


def ok(label, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + label
          + (('  — ' + str(detail)) if detail and not cond else ''))
    if not cond:
        fails.append(label)


readme = (ROOT / 'README.md').read_text()

# Only the runnable parts. Prose may name `frontend/` historically — and now
# does, to explain where it went — but a command block is instructions.
blocks = re.findall(r'```(?:bash|sh)\n(.*?)```', readme, re.S)
ok('the README has runnable command blocks', bool(blocks))
cmds = '\n'.join(blocks)

targets = set(re.findall(r'--prefix\s+(\S+)', cmds))
targets |= set(re.findall(r'(?:^|\n|&&\s*)cd\s+([^\s;&|]+)', cmds))

for t in sorted(targets):
    if t.startswith('../') or t.startswith('/') or '$' in t or '<' in t:
        # Deliberately outside this checkout, or a placeholder. Fine.
        continue
    ok('a command block targets %r, which exists' % t,
       (ROOT / t).exists(), 'no such directory in this repo')

# The specific regression: the deleted directory is never a command target.
ok('no command block reaches into the deleted frontend/ directory',
   'frontend' not in targets,
   [c.strip() for c in cmds.split('\n') if 'frontend' in c and
    ('--prefix' in c or c.strip().startswith('cd '))])

# ...and a reader who remembers `frontend/` is told where it went, so the
# fix is a redirection rather than a silent deletion.
ok('the README says where the frontend actually lives now',
   'cafreso-pages' in readme, 'no pointer to the sibling repo')

print()
if fails:
    print('FAILED %d check(s): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('the README never sends you into a deleted directory: all checks passed')
