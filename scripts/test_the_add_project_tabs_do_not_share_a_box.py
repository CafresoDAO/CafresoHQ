#!/usr/bin/env python3
"""The Add Project dialog has two tabs, and they were sharing two pieces of
state that mean different things on each side.

Measured live on a fresh office, on the surface the getting-started checklist
opens at step 5:

  1. `name`. On the Local tab it is the project's DISPLAY NAME. On the GitHub
     tab it is "Local folder name (optional)" — a directory that gets created
     on disk — with the placeholder "auto from URL if blank". Typing
     "My Website" on the Local tab and crossing over pre-filled it here, so
     the box was no longer blank and the documented default never applied.
     Cloning facebook/react would have landed in `MyWebsite` (the server
     strips the space), and the office would have looked like it chose that.

  2. `err`. Hitting Add on an empty Local form and switching tabs left
     **"path required"** sitting under the GitHub form — which has no path
     field at all and never asked for one. The other direction is worse: a
     clone failure ("that repo doesn't exist or is private") reads as a
     verdict on the folder you are about to type.

Fix, one file (views/projects.jsx): the GitHub tab's folder name gets its own
`repoName` state, seeded empty (`prefillName` is a project name too, and this
field's documented default is the URL); and both tab buttons clear `err`,
because a complaint has to stay with the question it answers.

Run: python3 scripts/test_the_add_project_tabs_do_not_share_a_box.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / 'views' / 'projects.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def component(src, name):
    """One top-level component body, located by NAME — never by its parameter
    list, which is exactly the locator that turned an added prop into a test
    CRASH once already (see test_calendar_task_row_opens_the_right_card)."""
    m = re.search(r'^function %s\(' % re.escape(name), src, re.M)
    if not m:
        raise SystemExit('no top-level `function %s(` in views/projects.jsx' % name)
    j = src.find('\nfunction ', m.end())
    return src[m.start():] if j == -1 else src[m.start():j]


def lift(src, name):
    """One indented `const <name> = ...;` to its depth-0 semicolon.

    Parens, braces AND brackets are counted: these bodies hold object
    literals, arrow functions and try/catch blocks.
    """
    m = re.search(r'^[ \t]*const %s = ' % re.escape(name), src, re.M)
    if not m:
        raise SystemExit('no `const %s = ` in AddProjectModal' % name)
    depth = 0
    for j in range(m.start(), len(src)):
        c = src[j]
        if c in '({[':
            depth += 1
        elif c in ')}]':
            depth -= 1
        elif c == ';' and depth == 0:
            return src[m.start():j + 1]
    raise SystemExit('unterminated `const %s`' % name)


# (label, local name, local path, repo url, github folder name, expected
#  folder passed to cloneRepo — None means "left to the URL", '__none__'
#  means the clone must not happen at all)
CASES = [
    ('local name typed, github box left alone: the clone keeps its documented '
     'default and derives the folder from the URL',
     'My Website', '', 'facebook/react', '', None),
    ('github box typed: that is the folder, and it is the only thing that '
     'can be', '', '', 'facebook/react', 'react-fork', 'react-fork'),
    ('both typed: the folder is the one typed on the folder field',
     'My Website', '', 'facebook/react', 'react-fork', 'react-fork'),
    ('no repo: nothing is cloned at all',
     'My Website', '', '', 'react-fork', '__none__'),
]

# CHANGED by #308. These two expectations were the literal strings
# `name required` and `path required` — the raw state-variable vocabulary
# this dialog's own sibling hint carries a long comment against, so the
# assertion was pinning the defect in place: any rewrite into office words
# would have failed here. What this test is actually about is WHICH form the
# complaint belongs to, not which words it uses, so the expectation is now a
# pattern that says the complaint is about the name / about the path.
LOCAL_CASES = [
    ('empty form', '', '', r'(?i)\bneeds a name\b', None),
    ('name only', 'My Website', '', r'(?i)\bBrowse\b.*folder|folder.*\bBrowse\b', None),
    ('name and path', 'My Website', '/Users/you/site', None, 'My Website'),
]


def main():
    print('The Add Project tabs stop sharing a box')

    src = PROJECTS.read_text(encoding='utf-8')
    modal = component(src, 'AddProjectModal')

    # --- §1: the github submit, driven --------------------------------
    harness = '\n'.join([
        'const OUT = [];',
        'for (const c of CASES) {',
        '  const [label, name, path, repoUrl, repoName] = c;',
        '  let cloned = null, committed = null, errored = null;',
        '  const shallow = true;',
        '  const setErr = (v) => { errored = v; };',
        '  const setBusy = () => {};',
        '  const repoCause = (raw) => raw;',
        '  const onCommit = (p) => { committed = p; };',
        '  const CafresoHQClient = { cloneRepo: async (a) => { cloned = a;',
        '    return { name: a.name || "react", path: "/tmp/" + (a.name || "react") }; } };',
        # `## 392` gave this submit a double-submit claim: `submitGithub` is
        # now a synchronous ref-claim wrapper around `_submitGithub`, which
        # holds the body this test drives. Both halves are lifted, and the
        # ref the wrapper claims is handed in here — without it the lifted
        # source throws ReferenceError before any case runs.
        '  const cloningUrlsRef = { current: new Set() };',
        '  ' + lift(modal, '_submitGithub'),
        '  ' + lift(modal, 'submitGithub'),
        '  await submitGithub(null);',
        '  OUT.push([label, cloned, committed, errored]);',
        '}',
        'console.log(JSON.stringify(OUT));',
    ])
    harness = 'const CASES = %s;\n' % json.dumps(
        [[c[0], c[1], c[2], c[3], c[4]] for c in CASES]) + harness

    proc = subprocess.run(['node', '--input-type=module', '-e', harness],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr.strip()[:2000])
        raise SystemExit('the lifted github submit did not run under node')
    got = json.loads(proc.stdout.strip().splitlines()[-1])

    for case, (_label, cloned, _committed, errored) in zip(CASES, got):
        expect = case[5]
        if expect == '__none__':
            check(case[0], cloned is None and errored is not None,
                  'cloned=%r errored=%r' % (cloned, errored))
        else:
            check(case[0],
                  cloned is not None and cloned.get('name') == expect,
                  'cloneRepo got name=%r, expected %r' % (
                      (cloned or {}).get('name'), expect))

    # The local display name must never reach the clone call. This is the
    # whole bug in one assertion.
    first = got[0]
    check('the project\'s display name never becomes a directory on disk',
          (first[1] or {}).get('name') is None,
          'cloneRepo received name=%r from the Local tab\'s Name field'
          % (first[1] or {}).get('name'))

    # --- §2: the local submit still works -----------------------------
    lharness = '\n'.join([
        'const OUT = [];',
        'for (const c of LOCAL) {',
        '  const [label, name, path] = c;',
        '  let committed = null, errored = null;',
        '  const setErr = (v) => { errored = v; };',
        '  const onCommit = (p) => { committed = p; };',
        '  ' + lift(modal, 'submitLocal'),
        '  submitLocal(null);',
        '  OUT.push([label, committed, errored]);',
        '}',
        'console.log(JSON.stringify(OUT));',
    ])
    lharness = 'const LOCAL = %s;\n' % json.dumps(
        [[c[0], c[1], c[2]] for c in LOCAL_CASES]) + lharness
    lproc = subprocess.run(['node', '--input-type=module', '-e', lharness],
                           capture_output=True, text=True)
    if lproc.returncode != 0:
        print(lproc.stderr.strip()[:2000])
        raise SystemExit('the lifted local submit did not run under node')
    lgot = json.loads(lproc.stdout.strip().splitlines()[-1])

    for (label, _n, _p, want_err, want_name), (_l, committed, errored) in zip(
            LOCAL_CASES, lgot):
        if want_err:
            check('local: %s → a complaint about that field' % label,
                  isinstance(errored, str)
                  and re.search(want_err, errored) is not None,
                  'got %r, wanted /%s/' % (errored, want_err))
        else:
            check('local: %s files the project under the name that was typed'
                  % label,
                  committed is not None and committed.get('name') == want_name
                  and committed.get('source') == 'local',
                  'got %r' % (committed,))

    # --- §3: the two boxes are two states -----------------------------
    check('the github folder field reads repoName',
          'value={repoName} onChange={e => setRepoName(e.target.value)}' in modal,
          'views/projects.jsx: the github folder input changed binding')
    check('the local name field still reads name',
          'value={name} onChange={e => setName(e.target.value)}' in modal,
          'views/projects.jsx: the local name input changed binding')
    check('repoName is seeded empty — prefillName is a PROJECT name, and this '
          'field\'s documented default is the URL',
          re.search(r"const \[repoName, setRepoName\] = useSV\(''\);", modal)
          is not None,
          'views/projects.jsx: repoName is seeded from something')
    check('the placeholder still promises the URL default it can now keep',
          'placeholder="auto from URL if blank"' in modal,
          'views/projects.jsx: the promise this fix restores is gone')

    # --- §4: the complaint stays with its own form --------------------
    tabs = re.findall(r"onClick=\{\(\) => \{ setErr\(null\); setTab\('(\w+)'\); \}\}",
                      modal)
    check('both tab buttons clear the error on the way out',
          sorted(tabs) == ['github', 'local'],
          'tab buttons that clear err: %r' % (tabs,))

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
