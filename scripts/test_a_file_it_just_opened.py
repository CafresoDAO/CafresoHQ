#!/usr/bin/env python3
"""The office warned the boss about a file it had just opened.

Measured live 2026-08-15, office 9261, task "Vendor pick", a canned brain and
one vault read. This is the office's own Working record, two consecutive
lines, about one file:

    - Opened Research/vendors.md in the cabinet
    - `Research/vendors.md` is named above, but nothing was written to the
      cabinet on this run — this sheet is the only file it produced.

The second line is the "named a path, wrote nothing" guard from #50, and it
was asking half of its own question. It checked whether anything had been
WRITTEN and never whether this path had been READ. On a read the two facts it
calls a contradiction are not one: nothing was written because nothing needed
to be, and the file it says is not there is the file the office had open a
moment earlier, by its own record, one line above.

The guard's own comment names the stake: "a miss costs the caveat; a false
alarm calls an honest coworker a liar, which is the more expensive mistake."
This was that mistake, with the visit log sitting right there disproving it.

Two things this pins beyond the read case:

  - a trip that FAILED does not suppress. A read that could not open the file
    is evidence FOR the note, not against it, and the same `failed` flag that
    fixes the Working record's tense decides it here.
  - any tool, not only the cabinet ones. `FILE_WRITE src/index.js` hit the
    identical false alarm, because the write went to the workspace rather
    than the vault. What the office actually knows is narrower than the tool
    taxonomy: it touched this exact path this run and the trip arrived.

And the structure, because #82 is #81's shape again: `unfiledPath` and the
delivery sheet's footer each carried their own copy of "named, and nothing
wrote it", and both copies had the same half-question in them. One rule, one
place, two wordings.

Run: python3 scripts/test_a_file_it_just_opened.py
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_artifacts import run_js  # noqa: E402
from test_a_promised_file_was_never_written import brace_lift  # noqa: E402

RUNTIME = ROOT / 'hq-runtime.jsx'
ARTIFACTS = ROOT / 'app' / 'artifacts.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# The reply the measured run produced, near enough: a coworker that read one
# vault note and named it. `claimedPaths` reads the shape, so the sentence
# around it does not matter — what matters is that the path is named and the
# visit log says the office opened it.
READ = 'I checked the vendor list.\nSource: Research/vendors.md'
GHOST = 'I saved the summary to Research/ghost.md for you.'

# name, text, visits, must the note fire?
CASES = [
    # ── the measured defect ───────────────────────────────────────────────
    ('a path the office read is not a path that is missing',
     READ, [{'name': 'VAULT_READ', 'arg': 'Research/vendors.md'}], False),
    ('...however the visit log spells the case',
     READ, [{'name': 'VAULT_READ', 'arg': 'research/VENDORS.md'}], False),
    ('...and however it spells the prefix',
     READ, [{'name': 'VAULT_READ', 'arg': './Research/vendors.md'}], False),

    # ── the note's actual job, which must survive all of this ─────────────
    ('a path named and never touched is still contradicted',
     GHOST, [], True),
    ('...even on a run that read something else',
     GHOST, [{'name': 'VAULT_READ', 'arg': 'Research/vendors.md'}], True),
    ('...and only the untouched one is named',
     'Read Research/vendors.md, saved Research/ghost.md.',
     [{'name': 'VAULT_READ', 'arg': 'Research/vendors.md'}], True),
    # The suppression is a path match, not a filename match. Case and the
    # leading `./` are normalised because those are spellings of one path;
    # a different folder is a different file, and treating `vendors.md` as
    # proof of `Reports/vendors.md` would be the false-silence version of
    # this same defect.
    ('a same-named file in another folder is a different file',
     'Saved to Reports/vendors.md.',
     [{'name': 'VAULT_READ', 'arg': 'Research/vendors.md'}], True),

    # ── a trip that did not arrive is evidence for the note ───────────────
    ('a read that FAILED does not vouch for the file',
     READ, [{'name': 'VAULT_READ', 'arg': 'Research/vendors.md', 'failed': True}],
     True),

    # ── any tool, because the office knows the path, not the taxonomy ─────
    ('a workspace write is a file that is there',
     'Patched it — see src/index.md for the change.',
     [{'name': 'FILE_WRITE', 'arg': 'src/index.md'}], False),
    ('a workspace read is too',
     'Source: docs/notes.md', [{'name': 'FILE_READ', 'arg': 'docs/notes.md'}],
     False),
    ('the private notes folder still is not the cabinet',
     'I noted it in Agents/Nova/facts.md.',
     [{'name': 'MEMORY_WRITE', 'arg': 'Agents/Nova/facts.md'}], False),

    # ── what #50 pinned, unchanged ────────────────────────────────────────
    ('a cabinet write anywhere silences the note',
     GHOST, [{'name': 'VAULT_NEW', 'arg': 'Research/other.md'}], False),
    ('a run with no visit log accuses nobody',
     GHOST, None, False),
    ('a reply naming no path says nothing',
     'Red, yellow and blue.', [], False),
    ('a URL is still not a filing claim',
     'See https://example.com/docs/report.md.',
     [{'name': 'BROWSER_FETCH', 'arg': 'https://example.com/docs/report.md'}],
     False),
]


def main():
    print('a file it just opened')
    runtime = RUNTIME.read_text(encoding='utf-8')
    artifacts = ARTIFACTS.read_text(encoding='utf-8')

    # ── one rule, one place ──────────────────────────────────────────────
    #
    # #81's lesson, arriving a second time in the same week: two doors, each
    # with its own copy of one rule, disagreeing about the half nobody
    # updated. These pins are the cheap half of not repeating it.
    check('the detection is written once',
          len(re.findall(r'^function unwrittenPaths\(', artifacts, re.M)) == 1,
          'the subtraction "named, minus what the office touched" is the '
          'rule; a second copy of it is what #82 was')
    check('...and the chat note reads it',
          re.search(r'\(unwrittenFn \|\| unwrittenPaths\)\(text, visits\)', runtime),
          'unfiledPath used to call claimedPaths and agentFiledPath itself '
          'and do the subtraction inline')
    check('...and so does the filed sheet',
          re.search(r'const promised = unwrittenPaths\(body, visits\);', artifacts),
          "buildDelivery's footer had the second copy, and it is the surface "
          'that outlives the session')
    # Neither door may quietly grow its own copy back. Comments are stripped
    # first: this file's own explanation of the defect names both functions,
    # and a bare search would find the documentation and call it code.
    code = re.sub(r'/\*[\s\S]*?\*/', '', runtime)
    check('...and neither door does the subtraction itself any more',
          'claimedPaths' not in code and 'agentFiledPath' not in code,
          'hq-runtime should reach for the shared answer, not the two halves '
          'it used to combine by hand')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH for the behavioural arms')
        return 1 if FAILS else 0

    # run_js already prepends artifacts.jsx, so only the runtime half is
    # lifted in — pulling artifacts twice declares every helper twice.
    scope = brace_lift(runtime, 'function unfiledPath(')
    js = 'const R = {};\n' + '\n'.join(
        'R[%s] = unfiledPath(%s, %s);' % (json.dumps(n), json.dumps(t), json.dumps(v))
        for n, t, v, _f in CASES) + '\nconsole.log(JSON.stringify(R));'
    r = run_js(scope + '\n' + js)
    for name, _t, _v, fires in CASES:
        got = r[name]
        check(name, bool(got) == fires,
              ('fired: ' + str(got)) if got else 'silent, and it should not be')

    # ── and the sheet, in its own words ──────────────────────────────────
    #
    # Same detection, different sentence, and the sheet is the copy the boss
    # still has next week. This is the exact pair of lines that were measured
    # contradicting each other.
    build = ('const T = { title: "Vendor pick" }, A = { name: "Vera" };\n'
             'const V = [{ name: "VAULT_READ", arg: "Research/vendors.md" }];\n'
             'const R = {};\n'
             'R.read = buildDelivery(T, A, %s, V).content;\n'
             'R.ghost = buildDelivery(T, A, %s, []).content;\n'
             'console.log(JSON.stringify(R));'
             % (json.dumps(READ), json.dumps(GHOST)))
    b = run_js(build)
    check('the sheet reports the visit',
          'Opened Research/vendors.md in the cabinet' in b['read'],
          b['read'])
    check('...and no longer contradicts itself on the next line',
          'is named above' not in b['read'],
          'these were the two consecutive lines this ticket was measured '
          'from:\n' + b['read'])
    check('...and still contradicts a file nobody wrote',
          '`Research/ghost.md` is named above' in b['ghost'],
          b['ghost'])

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
