#!/usr/bin/env python3
"""The office made a folder on the boss's disk and did not say so.

Measured live (#149) on the first-run path, at step 5 of the office's own
getting-started checklist: "New Project →", "Create your first project",
Local folder. Typed a name and a path that does not exist. The dialog closed
and the office said

    ✓ Added project "Alpaca site"

which is the same sentence, letter for letter, as pointing at a folder that
was already there. Checked the disk afterwards: the directory had been
created, in $HOME, seconds earlier. Nothing on screen had mentioned it.

`commitProject` calls `/fs/mkdir` best-effort before filing the project, and
that is deliberate -- without it a first-time boss lands on "Not a directory"
with no way forward (see the comment above the second call site). The defect
is not the create, it is the silence. `/fs/mkdir` is `parents=True`, so a
typo like ~/Documnets/site creates the whole chain, and the FILES tree then
renders it empty, which is indistinguishable from a correct-but-empty
project. The one fact that separates "I opened your folder" from "I made you
a new one" is in the response already -- `existed: true` when the folder was
there, absent when the server created it -- and BOTH commit sites threw it
away.

So the fix reads it and says so, in the same toast, in one sentence that
names the path, because a typo is only catchable if the boss can read back
what was actually made.

This runs BOTH halves for real: the shipped `_addProjectMkdir` and
`_addedProjectSay` under Node against a stub client, and the shipped
`_fs_mkdir` route against a real temp directory, so the `existed` contract
the front end now depends on cannot drift without this file noticing.

Run: python3 scripts/test_the_office_says_when_it_made_you_a_folder.py
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJ = ROOT / 'views' / 'projects.jsx'
FS = ROOT / 'fs_routes.py'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift(src, name):
    """The source of one top-level `const name = ...;` arrow, brace-matched.

    Both helpers are module-scope consts in views/projects.jsx precisely so
    the two commit sites share one implementation -- and so this file can run
    that implementation rather than a copy of it.
    """
    m = re.search(r'^const %s = ' % re.escape(name), src, re.M)
    if not m:
        return None
    depth, i = 0, m.end()
    while i < len(src):
        c = src[i]
        if c in '({[':
            depth += 1
        elif c in ')}]':
            depth -= 1
        elif c == ';' and depth == 0:
            return src[m.start():i + 1]
        i += 1
    return None


PROBE = r'''
const OUT = {};
const stub = (reply) => ({ fsMkdir: async (p) => (typeof reply === 'function' ? reply(p) : reply) });

const run = async () => {
  // The measured case: the server created it, so no `existed` comes back.
  OUT.created = await _addProjectMkdir(
    stub({ ok: true, path: '/Users/you/Documnets/site' }), '/Users/you/Documnets/site', 'local');
  // The folder was already there.
  OUT.existed = await _addProjectMkdir(
    stub({ ok: true, path: '/Users/you/repo', existed: true }), '/Users/you/repo', 'local');
  // A refusal, or a server that is not there. Nothing may be claimed.
  OUT.refused = await _addProjectMkdir(
    { fsMkdir: async () => { throw new Error('403'); } }, '/etc/nope', 'local');
  OUT.notOk = await _addProjectMkdir(stub({ ok: false }), '/Users/you/x', 'local');
  OUT.noClient = await _addProjectMkdir(null, '/Users/you/x', 'local');
  // A GitHub clone makes its own directory server-side; this step must not
  // claim that one.
  OUT.github = await _addProjectMkdir(
    stub({ ok: true, path: '/Users/you/repo' }), '/Users/you/repo', 'github:owner/repo');
  // The server resolved the path it actually made; that is what gets named.
  OUT.resolved = await _addProjectMkdir(
    stub({ ok: true, path: '/Users/you/RESOLVED' }), 'relative/site', 'local');

  OUT.sayMade = _addedProjectSay('Alpaca site', OUT.created);
  OUT.sayPlain = _addedProjectSay('Alpaca site', null);
  console.log(JSON.stringify(OUT));
};
run();
'''


def run_probe():
    src = PROJ.read_text(encoding='utf-8')
    pieces = []
    for name in ('_addProjectMkdir', '_addedProjectSay'):
        body = lift(src, name)
        if body is None:
            return None, 'could not lift %s from views/projects.jsx' % name
        pieces.append(body)
    tmp = ROOT / '.addproj-probe-tmp'
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        (tmp / 'probe.js').write_text('\n\n'.join(pieces) + '\n\n' + PROBE,
                                      encoding='utf-8')
        p = subprocess.run([shutil.which('node') or 'node', str(tmp / 'probe.js')],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            return None, 'node: ' + p.stderr.strip()[:300]
        return json.loads(p.stdout.strip().splitlines()[-1]), None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_server_contract():
    """The `existed` flag the front end now depends on, from the real route.

    Imports fs_routes and drives `_fs_mkdir` against a temp directory with a
    minimal stand-in for serve.py's handler. If the route stops distinguishing
    the two cases, the sentence above becomes a guess, and no amount of
    front-end testing would show it.
    """
    sys.path.insert(0, str(ROOT))
    import fs_routes
    base = Path(tempfile.mkdtemp(prefix='hq-mkdir-'))
    try:
        fs_routes._within_allowed_dirs = lambda p: True

        class H:
            def __init__(self, body):
                self._body = body
                self.sent = None

            def _fs_mutate_ok(self):
                return True

            def _fs_json_body(self):
                return self._body

            def _validate_path(self, raw):
                return Path(raw)

            def _send_json(self, code, obj):
                self.sent = (code, obj)

        existing = base / 'already-here'
        existing.mkdir()
        h1 = H({'path': str(existing)})
        fs_routes._fs_mkdir(h1)

        fresh = base / 'deep' / 'nested' / 'new'
        h2 = H({'path': str(fresh)})
        fs_routes._fs_mkdir(h2)
        return h1.sent, h2.sent, fresh.is_dir()
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main():
    print('the office says when it made you a folder')
    if not shutil.which('node'):
        print('  SKIP  node not available — cannot run the real helpers')
        return 0

    r, err = run_probe()
    if r is None:
        print('  FAIL  could not run the helpers: ' + str(err))
        return 1

    print('1. the fact the office was throwing away')
    check('a folder the server created comes back named',
          r['created'] == '/Users/you/Documnets/site',
          f"{r['created']!r} — /fs/mkdir omits `existed` when it made one, "
          'and that is the whole signal')
    check('a folder that was already there does not',
          r['existed'] is None,
          f"{r['existed']!r} — `existed: true` means the boss's own folder "
          'was opened, and saying "the office made one" would be a lie')
    check('the path named is the one the server resolved',
          r['resolved'] == '/Users/you/RESOLVED',
          f"{r['resolved']!r} — a relative path is anchored server-side, so "
          'the typed string is not necessarily what exists on disk')

    print('2. nothing is claimed that was not done')
    # The direction that matters most: a wrong "the office made one" sends the
    # boss looking for a folder that is not there.
    for key, why in (
        ('refused', 'the door said no'),
        ('notOk', 'the server answered but did not say ok'),
        ('noClient', 'there is no client to ask'),
        ('github', 'cloneRepo made that directory, not this step'),
    ):
        check(f'no folder is claimed when {why}',
              r[key] is None, f'{key} = {r[key]!r}')

    print('3. the sentence')
    made, plain = r['sayMade'], r['sayPlain']
    check('the ordinary case is unchanged',
          plain == 'Added project "Alpaca site"', repr(plain))
    check('the created case says a folder was made',
          made != plain and 'made one' in made, repr(made))
    check('...and names it, so a typo is legible',
          '/Users/you/Documnets/site' in made,
          f'{made!r} — "a folder was created" without the path is a fact the '
          'boss cannot check')
    # #145's rule: one clause, one em-dash. Two of them reads as two failures.
    check('one sentence, one em-dash',
          made.count('—') == 1 and made.count('.') == 1, repr(made))
    # §6's jargon table. This sentence is boss-facing, on the first-run path.
    check('no jargon in the sentence the boss reads',
          not re.search(r'mkdir|parents=|errno|ENOENT|fs/|\bdir\b|path required',
                        made, re.I),
          repr(made))

    print('4. the server contract the sentence rests on')
    sent1, sent2, made_on_disk = check_server_contract()
    check('an existing folder answers existed: true',
          sent1 and sent1[0] == 200 and sent1[1].get('existed') is True,
          repr(sent1))
    check('a created folder answers without it',
          sent2 and sent2[0] == 200 and 'existed' not in sent2[1],
          f'{sent2!r} — if the route starts sending `existed: false` here, '
          'the front end reads it as truthy-absent and goes quiet again')
    check('...and really did create it, parents and all',
          made_on_disk is True,
          'fs_routes._fs_mkdir: parents=True is why a typo costs a whole '
          'chain of directories, which is why the silence mattered')

    print('5. both commit sites, one implementation')
    # The bug was in two places at once. A third call site that re-inlines
    # `await client.fsMkdir(path)` would be silent again, and this suite
    # would go on passing.
    src = PROJ.read_text(encoding='utf-8')
    code = re.sub(r'/\*[\s\S]*?\*/', '', src)
    check('both commit sites go through the shared helper',
          code.count('_addProjectMkdir(') == 2,  # both are calls: the
          # definition is `const _addProjectMkdir = async (...)`, with no
          # paren against the name, so it does not count itself.
          f"{code.count('_addProjectMkdir(')} call sites — expected exactly "
          'the two commit steps')
    check('...and neither still calls fsMkdir straight through',
          not re.search(r'commitProject[\s\S]{0,400}?\bawait\s+\w*\.?fsMkdir\(',
                        code),
          'views/projects.jsx: an inline mkdir in a commit step is a create '
          'this file cannot see')
    check('both toasts go through the shared sentence',
          code.count('_addedProjectSay(') == 2,
          f"{code.count('_addedProjectSay(')} call sites — expected exactly "
          'the two toasts')

    print()
    if FAILS:
        print(f'made you a folder: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('made you a folder: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
