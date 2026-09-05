#!/usr/bin/env python3
"""It printed "serving CafresoHQ on :8787", then "exec: python3: not found".

`## 405.` drove `Start-CafresoHQ.sh` on a machine with no `python3` on PATH.
Literal transcript of the script as it stood:

    [start] WARN hermes CLI not installed — /hermes will 502 until you install it
    [start] TIP: install mkcert for a browser-trusted local HTTPS cert →
            https://github.com/FiloSottile/mkcert  (without it, the cert is self-signed)
    [start] serving CafresoHQ on :8787  (loopback-only; serve.py prints the exact URL + scheme)
    ./Start-CafresoHQ.sh: line 86: exec: python3: not found

Two bugs in five lines.

ONE — the promise. The script announced a running office one line before the
shell announced that the office's entire backend could not be launched. It
already guarded `npm` with a `command -v` and a paragraph of advice; the
interpreter that runs serve.py, invoked bare on the last line, was guarded by
nothing. The tester's last word on the subject is the shell's, not the
product's: no version, no install command, no next step.

TWO — the cert sentence. "without it, the cert is self-signed" is false, and
false in the direction that matters. `serve.py`'s `_ensure_local_tls` is called
with `allow_selfsigned=_tls_forced`, and `_tls_forced` is only true under
`CAFRESOHQ_TLS_AUTO=1`. With no mkcert and no flag the branch is
`if not allow_selfsigned: return None, None, False` and the office stays on
plain HTTP. Measured on a cold tree with no mkcert installed:
`CafresoHQ -> http://localhost:8811/hq.html`. A tester told to expect a
self-signed cert goes looking for a certificate warning that never comes, and
one told the embed will work "after a one-time trust" is told wrong.

WHAT THIS ASSERTS, as invariants:

  1. Every external command the launcher invokes UNCONDITIONALLY — anything it
     `exec`s — has a `command -v` guard somewhere above it. Derived from the
     script's own text, so a new bare invocation is caught without this file
     being edited.
  2. Driven for real: with a PATH that has no `python3`, the launcher exits
     non-zero, names python3, offers somewhere to get it, and NEVER prints the
     "serving CafresoHQ on" promise.
  3. No document in the repo claims serve.py falls back to a self-signed cert
     while serve.py gates self-signed behind a flag. This one is derived from
     serve.py rather than pinned: it only fires while `allow_selfsigned` is
     wired to the forced flag, and it sweeps every .md and .sh in the tree, so
     a new doc repeating the old sentence is caught.

Run: python3 scripts/test_the_launcher_never_promises_a_server_it_cannot_start.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / 'Start-CafresoHQ.sh'
SERVE = ROOT / 'serve.py'
FAILS = []


def check(name, ok, why=''):
    print(('  ok   ' if ok else '  FAIL ') + name)
    if not ok:
        if why:
            print('         ' + why)
        FAILS.append(name)


def main():
    print('the launcher checks what it needs before it promises anything')
    sh = LAUNCHER.read_text(encoding='utf-8')

    # ── 1. every exec'd command is guarded above the line that runs it ───────
    guarded = set(re.findall(r'command -v\s+([A-Za-z0-9_.-]+)', sh))
    unguarded = []
    for m in re.finditer(r'^\s*exec\s+([A-Za-z0-9_.-]+)', sh, re.M):
        cmd = m.group(1)
        if cmd not in guarded:
            unguarded.append(cmd)
    check('every command the launcher execs is checked for first',
          not unguarded,
          'unguarded: %s — a bare invocation of a missing binary ends the '
          'launch on the shell\'s words, after the script has already told '
          'the tester the office is serving' % (', '.join(unguarded) or '-'))

    # ── 2. drive it: no python3 on PATH ─────────────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        binz = Path(td)
        # Everything the script needs to get as far as its own checks, minus
        # the one thing under test. dirname is deliberately included so the
        # cd-to-repo-root line works; python3 deliberately is not.
        for tool in ('sh', 'sed', 'grep', 'head', 'cat', 'dirname', 'pwd',
                     'curl', 'sleep', 'nohup', 'uname'):
            for d in ('/bin', '/usr/bin'):
                p = Path(d) / tool
                if p.exists():
                    try:
                        (binz / tool).symlink_to(p)
                    except OSError:
                        pass
                    break
        env = {'HOME': td, 'PATH': str(binz)}
        r = subprocess.run(['/bin/sh', str(LAUNCHER)], cwd=str(ROOT), env=env,
                           capture_output=True, text=True, timeout=120)
    out = (r.stdout or '') + (r.stderr or '')

    check('a missing python3 stops the launch',
          r.returncode != 0,
          'exit=%d — the script carried on past a prerequisite it cannot '
          'run without' % r.returncode)
    # Same LINE, not merely the same output. Driven from the main checkout the
    # DOTALL version of this passed on the unfixed script — `[start] WARN
    # hermes …` many lines above the shell's own `python3: not found` satisfied
    # it, which is precisely the arrangement this test exists to reject.
    check('the launcher, not the shell, says what is missing',
          re.search(r'^.*\[start\].*python3.*$', out, re.M | re.I),
          'nothing on a [start] line mentions python3; the only word on the '
          'subject is the shell\'s "not found": %r' % (out[-400:],))
    check('it says where to get python3',
          re.search(r'python\.org|brew install python|apt install python', out),
          'a first-run failure a tester cannot act on is the bug: %r'
          % (out[-400:],))
    check('it never claims to be serving',
          'serving CafresoHQ on' not in out,
          'the script announced a running office and then failed to start '
          'one — measured verbatim before this entry: %r' % (out[-400:],))

    # ── 3. nothing in the repo promises a self-signed fallback serve.py
    #      will not produce ────────────────────────────────────────────────
    serve = SERVE.read_text(encoding='utf-8')
    gated = re.search(r'allow_selfsigned\s*=\s*_tls_forced', serve)
    if not gated:
        print('  skip  self-signed copy (serve.py no longer gates it on the '
              'forced flag — re-read _ensure_local_tls\'s call site)')
    else:
        offenders = []
        for path in list(ROOT.rglob('*.md')) + list(ROOT.rglob('*.sh')):
            s = str(path)
            # `.claude/worktrees/` holds OTHER sessions' checkouts of this same
            # repo. Sweeping them turned one offending line into twenty-four
            # and made this suite's verdict depend on what an unrelated hunt
            # happens to have on disk. Measured from the main checkout, which
            # is the only place those directories exist.
            if any(part in s for part in
                   ('/node_modules/', '/.git/', '/dist-ui/',
                    '/.claude/worktrees/', '/.dfx/')):
                continue
            try:
                text = path.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            # Flatten first. The sentence that started all this was wrapped
            # across two shell-comment lines — "falls\n# back to a self-signed"
            # — so a line-oriented search reads the file and still misses it.
            # Prose that wraps is the normal case, not the exception.
            flat = re.sub(r'\s*\n\s*[#>*\-]*[ \t]*', ' ', text)
            for m in re.finditer(r'falls?\s+back\s+to\s+a\s+self-signed', flat):
                # A sentence that also names the flag is telling the truth
                # about the opt-in, not promising a default.
                window = flat[max(0, m.start() - 500):m.start() + 500]
                if 'CAFRESOHQ_TLS_AUTO' in window:
                    continue
                offenders.append('%s (…%s…)'
                                 % (path.relative_to(ROOT),
                                    flat[max(0, m.start() - 40):m.start() + 60]))
        check('no doc promises a self-signed fallback that will not happen',
              not offenders,
              'serve.py passes allow_selfsigned=_tls_forced, so with no '
              'mkcert and no CAFRESOHQ_TLS_AUTO=1 there is no HTTPS at all — '
              'these say otherwise: %s' % ', '.join(offenders))

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
