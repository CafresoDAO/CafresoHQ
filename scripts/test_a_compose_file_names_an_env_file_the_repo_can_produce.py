#!/usr/bin/env python3
"""The worker's README told the tester to fill in a file its compose never reads.

`## 405.` walked the second setup path a beta tester hits — the standalone
search worker — from a `git archive` of the branch into an empty directory.

`search_worker_service/README.md` said, in one block:

    docker compose -f docker-compose.worker.yml up -d --build

    Required env (in `worker.env`, gitignored — same file convention as
    `docker-compose.local.yml`):

`docker-compose.worker.yml` declares `env_file: - worker-standalone.env`, and
its own header says, in as many words, that this is "a DIFFERENT file from
docker-compose.local.yml's `worker.env`" and explains why the two identities
are deliberately separate. So a tester following the README literally writes a
Brave key and a worker secret into `worker.env`, runs the compose command, and
Compose stops on a missing env file — for a file the README never named.

Underneath that: `.gitignore` ignores both `worker.env` and
`worker-standalone.env`, and neither had a committed `.example`. `.env.example`
existed for serve.py's `.env`; the two worker env files had no equivalent, so
the fresh clone contained no template, no list of required keys, and nothing to
copy. Every route into this path started from a file that did not exist.

WHAT THIS ASSERTS, as invariants over the whole repo rather than these two files:

  1. Every `env_file:` any compose file declares is producible from a fresh
     clone: the file is either committed, or a committed `<name>.example`
     sits beside it.
  2. Every `.example` template is free of anything that looks like a filled-in
     secret — a template that ships a real key is worse than no template.
  3. Any document that gives a `docker compose -f X` command does not, in the
     same breath, instruct the reader to fill in a *different* compose file's
     env file. Derived from the compose files themselves, so it holds for
     compose files and READMEs that do not exist yet.

Run: python3 scripts/test_a_compose_file_names_an_env_file_the_repo_can_produce.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, ok, why=''):
    print(('  ok   ' if ok else '  FAIL ') + name)
    if not ok:
        if why:
            print('         ' + why)
        FAILS.append(name)


def env_files_of(compose_path):
    """Every path named under an `env_file:` block. Deliberately textual —
    this must run with no yaml module and no docker installed."""
    names, in_block = [], False
    for raw in compose_path.read_text(encoding='utf-8').splitlines():
        line = raw.split('#', 1)[0].rstrip()
        if not line.strip():
            continue
        if re.match(r'^\s*env_file\s*:', line):
            in_block = True
            inline = line.split(':', 1)[1].strip()
            if inline and not inline.startswith('['):
                names.append(inline.strip('\'"'))
                in_block = False
            elif inline.startswith('['):
                names += [p.strip().strip('\'"')
                          for p in inline.strip('[]').split(',') if p.strip()]
                in_block = False
            continue
        if in_block:
            m = re.match(r'^\s*-\s*(.+)$', line)
            if m:
                names.append(m.group(1).strip().strip('\'"'))
            else:
                in_block = False
    return names


def tracked(rel):
    """Is this path in the index? A file present only because somebody's
    machine happens to have it is not something a fresh clone receives."""
    r = subprocess.run(['git', 'ls-files', '--error-unmatch', rel],
                       cwd=str(ROOT), capture_output=True, text=True)
    return r.returncode == 0


def main():
    print('every compose env file is producible from a fresh clone')

    composes = sorted(p for p in ROOT.glob('docker-compose*.y*ml'))
    check('there are compose files to check',
          bool(composes),
          'no docker-compose*.yml at the repo root — this test has lost its '
          'subject and should be re-aimed, not deleted')

    all_env = {}
    for c in composes:
        for name in env_files_of(c):
            all_env.setdefault(name, []).append(c.name)

    # ── 1. the tester can produce every one of them ──────────────────────────
    missing = []
    for name, users in sorted(all_env.items()):
        if tracked(name):
            continue
        if tracked(name + '.example'):
            continue
        missing.append('%s (needed by %s)' % (name, ', '.join(users)))
    check('every declared env_file is committed or has a committed .example',
          not missing,
          'a fresh clone has neither the file nor a template, so the compose '
          'command aborts on Compose\'s own words about a missing env file '
          'and nothing in the repo says what belongs in it: %s'
          % '; '.join(missing))

    # ── 2. no template ships a real value ───────────────────────────────────
    leaky = []
    for name in sorted(all_env):
        tmpl = ROOT / (name + '.example')
        if not tmpl.is_file():
            continue
        for i, line in enumerate(tmpl.read_text(encoding='utf-8').splitlines(), 1):
            if line.lstrip().startswith('#') or '=' not in line:
                continue
            key, _, val = line.partition('=')
            val = val.strip().strip('\'"')
            if not val:
                continue
            secretish = re.search(r'KEY|SECRET|TOKEN|PASS|PRINCIPAL', key, re.I)
            # A placeholder is empty or obviously a placeholder; anything else
            # under a secret-shaped name is presumed real and must not ship.
            placeholder = re.match(r'^<.*>$|^(your|changeme|xxx+|\.\.\.)', val, re.I)
            if secretish and not placeholder:
                leaky.append('%s.example:%d %s' % (name, i, key.strip()))
    check('no .example template carries a filled-in credential',
          not leaky,
          'these lines assign a non-placeholder value to a secret-shaped '
          'key: %s' % '; '.join(leaky))

    # ── 3. docs point at the env file their own compose command reads ───────
    wrong = []
    # `.claude/worktrees/` holds OTHER sessions' checkouts of this same repo;
    # sweeping them makes this verdict depend on what an unrelated hunt has on
    # disk (measured from the main checkout: one offending README became
    # nineteen). Only this tree's own documents are this tree's problem.
    docs = [p for p in ROOT.rglob('*.md')
            if not any(part in str(p) for part in
                       ('/node_modules/', '/.git/', '/.claude/worktrees/',
                        '/.dfx/'))]
    for doc in docs:
        try:
            text = doc.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        for c in composes:
            if ('-f %s' % c.name) not in text:
                continue
            mine = set(env_files_of(c))
            if not mine:
                continue
            others = {n for n in all_env if n not in mine}
            # Only the paragraph around each mention of the compose command —
            # a doc may legitimately discuss both files elsewhere.
            for m in re.finditer(re.escape('-f %s' % c.name), text):
                window = text[max(0, m.start() - 700):m.start() + 700]
                for other in others:
                    if not re.search(r'\b%s\b' % re.escape(other), window):
                        continue
                    if re.search(r'%s.{0,400}?%s'
                                 % (re.escape(other), re.escape('DIFFERENT')),
                                 window, re.S | re.I):
                        continue   # the doc is drawing the distinction on purpose
                    if any(re.search(r'%s\b' % re.escape(n), window) for n in mine):
                        continue   # the right one is named too; the mention is context
                    wrong.append('%s names %s beside `-f %s`, which reads %s'
                                 % (doc.relative_to(ROOT), other, c.name,
                                    ' + '.join(sorted(mine))))
    check('no doc sends a reader to the wrong compose env file',
          not wrong,
          'a tester who follows it literally fills in a file the command '
          'never reads: %s' % '; '.join(sorted(set(wrong))))

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
