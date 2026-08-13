#!/usr/bin/env python3
""""Create your first Project" opened a dialog that spoke git and shell.

Step 5 of the office's own getting-started checklist is "Create your first
Project — your coworkers build docs, decks, code & sites here". Followed it
on a fresh office, exactly as a first-run boss would: the checklist's
"New Project →" button, then "Create your first project". Two things in the
dialog it opens were written for someone else.

The local-folder tab said, as the only guidance about which paths work:

    Path must be inside CAFRESOHQ_ALLOWED_DIRS for your coworkers to reach it.

An environment variable, named to a reader who has no way to look up its
value from inside the app — and false for the ordinary install besides,
because `_safe_path` skips the whitelist entirely when the runtime is local
and nothing was set explicitly. It invented a restriction and then named it
in a vocabulary the boss could not act on.

The GitHub tab was worse, because you reach it by making an ordinary typo.
Verbatim, off the live dialog:

    git clone failed (exit 128)
    Cloning into '/private/tmp/…/pj-space/repo'...
    remote: Repository not found.
    fatal: repository 'https://github.com/owner/repo/' not found

An exit code, an absolute path, "remote:", "fatal:" — and the only line
that tells the boss what to do is the third of four. Same class as the
vault's raw dumps, and the same fix.

`officeCause` alone was not the fix, which is the part worth keeping. Its
generic /not found/ rule answers "the office couldn't find that — it may
have been moved or renamed", which describes a file on this machine, not a
GitHub name that was mistyped or belongs to a private repo. So `repoCause`
runs a repository-subject table first and falls back to the office one —
the same "the patterns were right, the noun was wrong" split that
officeCause itself came from.

Run: python3 scripts/test_add_project_speaks_plainly.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOOR = ROOT / 'app' / 'floor.jsx'
PROJ = ROOT / 'views' / 'projects.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run_js(cases):
    text = FLOOR.read_text(encoding='utf-8')
    src = '\n'.join(ln for ln in text.split('\n')
                    if not ln.startswith('import ') and not ln.startswith('export '))
    proc = subprocess.run(['node', '--input-type=module', '-e', src + '\n' + cases],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('add project — the dialog says what happened in words the boss owns')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    # The fixture is the real thing: captured off the live dialog by
    # submitting "owner/repo" on a running office, not composed here.
    out = run_js(r'''
const R = {};
R.notFound = repoCause(`git clone failed (exit 128)
Cloning into '/private/tmp/x/pj-space/repo'...
remote: Repository not found.
fatal: repository 'https://github.com/owner/repo/' not found
`);
R.private   = repoCause('fatal: could not read Username for \'https://github.com\': terminal prompts disabled');
R.offline   = repoCause('fatal: unable to access \'https://github.com/a/b/\': Could not resolve host: github.com');
R.exists    = repoCause("fatal: destination path 'repo' already exists and is not an empty directory.");
R.viaOffice = repoCause('ETIMEDOUT');
R.officeSaysMoved = officeCause('remote: Repository not found.');
console.log(JSON.stringify(R));
''')

    # ── 1. nothing the boss cannot read ─────────────────────────────────
    SHRAPNEL = re.compile(
        r'exit \d+|fatal:|remote:|https?://|/[Uu]sers/|\bgit\b|\bstderr\b|\bexit code\b', re.I)
    for key in ('notFound', 'private', 'offline', 'exists'):
        check(f'{key}: no shell or git shrapnel reaches the dialog',
              not SHRAPNEL.search(out[key]), repr(out[key]))
        check(f'{key}: one line, not a transcript',
              '\n' not in out[key] and len(out[key]) <= 110, repr(out[key]))

    # ── 2. …and each one still says what to do ──────────────────────────
    # The absence checks above are satisfied by returning "something went
    # wrong". §7 wants the sentence to carry a way forward.
    check('a mistyped repo points at the name, not at a missing file',
          'owner and name' in out['notFound'] and 'private' in out['notFound'],
          repr(out['notFound']))
    check('a private repo names the sign-in, not a 401',
          'signed in' in out['private'] and 'GitHub' in out['private'],
          repr(out['private']))
    check('an unreachable network names the connection',
          'connection' in out['offline'], repr(out['offline']))
    check('a name collision says to pick another name',
          'different one' in out['exists'] or 'different name' in out['exists'],
          repr(out['exists']))

    # ── 3. the reason repoCause exists at all ───────────────────────────
    # If officeCause had been right for this, the correct fix was to call
    # it directly. It is not, and this is the proof — kept as a live
    # assertion so a later merge of the two tables has to argue with it.
    check('officeCause alone would have blamed a moved file',
          'moved or renamed' in out['officeSaysMoved'],
          f"{out['officeSaysMoved']!r} — if this ever stops being true, "
          'repoCause\'s whole justification changes and it should be re-read')
    check('...and repoCause does not repeat that mistake',
          'moved or renamed' not in out['notFound'], repr(out['notFound']))
    check('anything without a repository flavour still falls through',
          out['viaOffice'] == 'that took too long, so I stopped waiting — try again',
          f"{out['viaOffice']!r} — repoCause must be a layer over officeCause, "
          'not a replacement that drops its diagnoses')

    # ── 4. the call site ────────────────────────────────────────────────
    src = PROJ.read_text(encoding='utf-8')
    code = re.sub(r'/\*[\s\S]*?\*/', '', src)
    code = re.sub(r'(?m)^\s*//.*$', '', code)
    m = re.search(r'catch \(e2\) \{[\s\S]{0,900}?\n    \}', code)
    check('the clone catch is still there', bool(m), 'views/projects.jsx')
    body = m.group(0) if m else ''
    check('the dialog is handed a sentence, not the raw error',
          'setErr(repoCause(' in body and not re.search(r'setErr\(\(?e2\.message', body),
          repr(body[:160]))
    check('...and the raw text still reaches whoever is debugging',
          'console' in body and 'e2.detail' in body,
          'views/projects.jsx: a self-hosted install has a second reader — '
          'dropping stderr entirely trades one blind user for another')

    # ── 5. the local tab ────────────────────────────────────────────────
    # test_jargon_table.py owns the general rule now that views/projects.jsx
    # is guarded; this pins the specific sentence that started it.
    check('the path hint no longer names an environment variable',
          'CAFRESOHQ_ALLOWED_DIRS' not in re.sub(r'/\*[\s\S]*?\*/', '', src),
          'views/projects.jsx: outside a comment, this name is a dead end for '
          'the boss — and there is no restriction at all on a default local run')
    check('...and still tells the boss how to find a folder that works',
          re.search(r'Browse shows the ones your coworkers can open', src),
          'views/projects.jsx: Browse resolves through the same guard, so it is '
          'the one answer that is true in both local and restricted mode')

    print()
    if FAILS:
        print(f'add project: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('add project: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
