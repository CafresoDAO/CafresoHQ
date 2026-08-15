#!/usr/bin/env python3
"""A refused path still answered whether it exists.

The `/fs` read routes are deliberately keyless. `_KEY_PROTECTED_PREFIXES`
in serve.py says so in its own comment — only the /fs *mutation* prefixes
are key-gated, because the preview iframe fetches assets with no key, and
"the allowed-dirs boundary (enforced in every mode below) caps the read
routes instead."

So that boundary is the only one there is. At two doors it ran second, and
the checks in front of it answered with three different codes. Measured on
office 9262, 2026-08-15, sandbox = a temp workspace, CAFRESOHQ_API_KEY
CONFIGURED and no key supplied:

    GET  /fs/file?path=/etc/hosts      403   exists, is a file
    GET  /fs/file?path=/etc/zzz-nope   404   does not exist
    GET  /fs/file?path=/etc            400   exists, is a directory
    GET  /fs/browse?path=/etc          403   exists, is a directory
    GET  /fs/browse?path=/etc/hosts    400   exists, is not a directory
    POST /tools/exec                   401   key-gated, for contrast

Nothing was ever served. But the refusal is a reply, and three distinct
replies over an attacker-chosen path is an existence-and-type oracle for
the whole host, reachable by any caller that can reach the port.

`_fs_stat` already had the right order, as did collect / site / upload /
mkdir / rename / delete. Two doors of eight — both of the keyless ones.

The durable check is not "browse and file guard first". It is that NO
route consults the filesystem about a path before deciding it is allowed
to. A route added next month is covered without anyone reading this file.

Run: python3 scripts/test_a_refusal_does_not_answer.py
"""
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FS_RAW = (ROOT / 'fs_routes.py').read_text(encoding='utf-8')
SERVE_RAW = (ROOT / 'serve.py').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """The fix documents the measured 403/404/400 table in a comment, so a
    bare search would find its own evidence."""
    return re.sub(r'^\s*#.*$', '', src, flags=re.M)


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def code_of(url, method='GET'):
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def q(p):
    return urllib.parse.quote(str(p), safe='')


def main():
    print('a refusal does not answer')

    fs = strip_comments(FS_RAW)

    # ── 1. THE SWEEP: no route may probe before it guards ───────────────
    #
    # Read every route out of the module and walk it in source order,
    # recording each consultation of the allow-list and each consultation of
    # the filesystem. The first must not come after the second.
    #
    # Stated over ALL routes rather than the two that were wrong. Naming them
    # would pass a file whose next route repeats the defect, which is exactly
    # how this one survived: six routes had the right order and nothing
    # required the seventh and eighth to match.
    GUARD = re.compile(r'_within_allowed_dirs\(|self\._validate_path\(')
    PROBE = re.compile(r'\.is_dir\(\)|\.is_file\(\)|\.exists\(\)|\.iterdir\(\)'
                       r'|\.read_bytes\(\)|\.stat\(\)')
    # `\(self[^)]*\)` and not `\(self\)`: a route that gains a parameter must
    # stay IN the sweep. Pinning the exact signature is how #78's suite lost a
    # door — it stopped matching, so it left the list instead of failing it.
    # The coverage check below is the backstop for whatever this still misses.
    starts = [(m.start(), m.group(1))
              for m in re.finditer(r'^def (_fs_\w+)\(self[^)]*\):', fs, re.M)]
    check('the sweep found the fs routes',
          len(starts) >= 8,
          [len(starts), '— if the routes stop being module-level defs this '
           'suite silently stops checking anything'])

    offenders = []
    guarded = []
    for i, (pos, name) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(fs)
        body = fs[pos:end]
        g = GUARD.search(body)
        p = PROBE.search(body)
        if not p:
            continue          # nothing to leak
        if not g:
            # A route that touches the filesystem and never guards at all is
            # a worse version of this bug, so it is swept up here too.
            offenders.append((name, 'never guards'))
            continue
        guarded.append(name)
        if p.start() < g.start():
            offenders.append((name, 'probes at %d, guards at %d'
                              % (p.start(), g.start())))
    check('no fs route touches the filesystem before it checks the sandbox',
          not offenders,
          [offenders, '— the refusal becomes the answer: 403 for an existing '
           'file, 404 for an absent one, 400 for a directory'])
    check('...and the sweep actually looked at the doors that were wrong',
          {'_fs_browse', '_fs_file'} <= set(guarded),
          [sorted(guarded), '— if these two stop matching the route pattern '
           'they leave the sweep instead of failing it'])

    # The two keyless read doors are the reason this matters. If they ever
    # become key-protected the risk changes, and this suite should be re-read
    # rather than silently kept passing for the old reason.
    prefixes = SERVE_RAW[SERVE_RAW.index('_KEY_PROTECTED_PREFIXES = ('):]
    prefixes = prefixes[:prefixes.index(')\n')]
    check('the read routes are still keyless, which is why order is the whole '
          'boundary',
          "'/fs/browse'" not in prefixes and "'/fs/file'" not in prefixes
          and "'/fs/upload'" in prefixes,
          [prefixes, '— serve.py: "the allowed-dirs boundary caps the read '
           'routes instead"'])

    # ── 2. the in-sandbox sentences survive ─────────────────────────────
    #
    # #74 split "not a file" into "no such file" / "that is a folder" because
    # one string was answering two questions and the boss got the wrong one.
    # Withholding that INSIDE the sandbox would fix this bug by reintroducing
    # that one. Both must hold: specific inside, uniform outside.
    # `.index()` on a def line that changed shape RAISES, which crashes the
    # harness and proves nothing — the lesson #74 and #77 both taught, arriving
    # here in a third spelling. Locate by regex and fail loudly when absent.
    fm = re.search(r'^def _fs_file\(self[^)]*\):', fs, re.M)
    fbody = fs[fm.end():] if fm else ''
    nxt = re.search(r'^def _fs_\w+\(', fbody, re.M)
    fbody = fbody[:nxt.start()] if nxt else fbody
    check('the specific file/folder sentences are still there',
          bool(fm) and "'no such file'" in fbody
          and 'that is a folder, not a file' in fbody,
          '— #74; the fix is to reorder the guard, not to delete the answers')

    # ── 3. drive a real server with a key configured ────────────────────
    tmp = tempfile.mkdtemp(prefix='hqref-')
    ws = Path(tmp) / 'ws'
    (ws / 'sub').mkdir(parents=True)
    (ws / 'ok.txt').write_text('hi', encoding='utf-8')
    outside = Path(tmp) / 'outside'
    outside.mkdir()
    (outside / 'secret.txt').write_text('s', encoding='utf-8')

    port = free_port()
    env = dict(os.environ,
               CAFRESOHQ_ALLOWED_DIRS=str(ws),
               CAFRESOHQ_HQ_STATE_DIR=str(Path(tmp) / 'state'),
               # A key IS configured. The point is that these routes answer
               # anyway — they are not in the protected set.
               CAFRESOHQ_API_KEY='test-key-not-supplied-below',
               PORT=str(port))
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=str(ROOT),
                            env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT)
    base = 'http://127.0.0.1:%d' % port
    try:
        for _ in range(80):
            if code_of(base + '/fs/browse?path=' + q(ws)):
                break
            time.sleep(0.25)
        else:
            check('the server came up', False, 'never answered')
            return 1

        # The routes really are reachable with no key — otherwise everything
        # below would pass for the wrong reason (401 is uniform too).
        check('the read doors answer without a key',
              code_of(base + '/fs/file?path=' + q(ws / 'ok.txt')) == 200
              and code_of(base + '/tools/exec', 'POST') == 401,
              '— if these became key-gated, re-read this suite; a uniform 401 '
              'would make every check below vacuous')

        # THE ORACLE. Three states of a path outside the sandbox, each of
        # which used to have its own status code. They must be one code now.
        for route, cases in [
            ('/fs/file', [('an existing file',   outside / 'secret.txt'),
                          ('an absent path',     outside / 'zzz-nope'),
                          ('an existing dir',    outside)]),
            ('/fs/browse', [('an existing dir',  outside),
                            ('an existing file', outside / 'secret.txt'),
                            ('an absent path',   outside / 'zzz-nope')]),
            ('/fs/stat', [('an existing file',   outside / 'secret.txt'),
                          ('an absent path',     outside / 'zzz-nope'),
                          ('an existing dir',    outside)]),
        ]:
            seen = {}
            for label, target in cases:
                seen[label] = code_of(base + route + '?path=' + q(target))
            check('%s tells an outsider nothing about what is there' % route,
                  len(set(seen.values())) == 1 and 403 in set(seen.values()),
                  [seen, '— distinct codes over an attacker-chosen path are '
                   'an existence-and-type oracle for the whole host'])

        # A path that does not exist ANYWHERE, so no probe could succeed —
        # the answer must still be the same 403 and not a 400 from resolve().
        check('a nonsense path outside the sandbox reads the same',
              code_of(base + '/fs/file?path=' + q('/zz/qq/nope')) == 403,
              '— an outsider must not be able to distinguish "refused" from '
              '"malformed" either')

        # ── 4. and the boss still gets the specific answer inside ────────
        inside = {
            'a real file':        (q(ws / 'ok.txt'),      200),
            'an absent file':     (q(ws / 'gone.txt'),    404),
            'a folder':           (q(ws / 'sub'),         400),
        }
        for label, (target, want) in inside.items():
            got = code_of(base + '/fs/file?path=' + target)
            check('inside the sandbox, %s still answers %d' % (label, want),
                  got == want,
                  [got, '— #74: the boss clicking a ledger row is owed the '
                   'specific sentence; only outsiders get the flat refusal'])
        check('inside the sandbox, browse still distinguishes a non-directory',
              code_of(base + '/fs/browse?path=' + q(ws / 'ok.txt')) == 400
              and code_of(base + '/fs/browse?path=' + q(ws)) == 200,
              '— reordering must not flatten the answers the picker needs')
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
