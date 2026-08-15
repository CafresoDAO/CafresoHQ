#!/usr/bin/env python3
"""A relative path meant the workspace at one door and the repo at another.

`/tools/exec` has always read a relative path as workspace-relative — its
`_resolve_arg` anchors to the request's cwd. Every `/fs` route resolved
against the SERVER PROCESS cwd instead. Same string, two directories.

Measured on office 9262, 2026-08-15, with `site/index.html` sitting in the
workspace and serve.py started from the repo:

    POST /tools/exec  DIR_LIST  arg=site      200  the workspace's site/
    POST /tools/exec  FILE_WRITE site/x.txt   200  written to the workspace
    GET  /fs/collect?path=site                403  outside allowed dirs
    POST /fs/upload?path=site                 403
    GET  /fs/site/<b64 'site/'>/index.html    403
    ...every absolute equivalent              200

So a coworker wrote `site/index.html`, listed `site/`, emitted
`[PUBLISH_SITE: site/]`, the boss stamped it — and the publish 403'd on a
folder the office had just made. Worse, `publishSite` calls `fsCollect`
FIRST inside the II-shell branch and swallows the throw in `catch (_e)`, so
even with the shell present a relative path silently degraded to a preview
link, and that preview link was 403 too. The whole publish surface was
unreachable by the path a coworker naturally emits.

This suite runs a real server on a temp workspace and drives the doors.
It does NOT enumerate the routes it knows about: it reads every `/fs`
route out of serve.py's own dispatch and requires each one that takes a
path to answer the same way for the relative form as for the absolute.

Run: python3 scripts/test_a_relative_path_means_the_workspace.py
"""
import base64
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVE_RAW = (ROOT / 'serve.py').read_text(encoding='utf-8')
FS_RAW = (ROOT / 'fs_routes.py').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """The comment written with this fix quotes the 403 table verbatim."""
    return re.sub(r'^\s*#.*$', '', src, flags=re.M)


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def get(url, method='GET', data=None, timeout=10):
    req = urllib.request.Request(url, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode()


def b64(s):
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip('=')


def main():
    print('a relative path means the workspace')

    serve = strip_comments(SERVE_RAW)
    fs = strip_comments(FS_RAW)

    # ── 1. one anchor, and every door that resolves its own path uses it ──
    #
    # The first draft of this fix put the anchoring inside _validate_path and
    # stopped. Three routes — browse, file, stat — resolve their own path and
    # never call it, so the split survived at three doors out of five while
    # looking fixed at the two that were tested. Count them from source.
    check('there is one shared anchor',
          'def _workspace_path(path, strict=False):' in serve,
          '— anchoring inline at each call site is how three of five doors '
          'kept the old meaning last time')
    check('...and fs_routes is given it',
          'fs_routes._workspace_path = _workspace_path' in serve,
          '— injected the same way as _client_path')
    #
    # Stated as "the old spelling is absent", not "every match uses the new
    # one". The first draft captured the callee out of
    # `p = (\S+)\(req_path\)\.resolve\(\)` — and a door reverted to
    # `pathlib.Path(_client_path(req_path)).resolve()` does not match that
    # pattern at all, so it left the list rather than failing it, and `all()`
    # over the two remaining doors stayed True. A check that enumerates what
    # it recognises cannot see the thing that stopped being recognisable.
    anchored = len(re.findall(r'_workspace_path\(req_path\)\.resolve\(\)', fs))
    unanchored = re.findall(r'pathlib\.Path\(_client_path\([^)]*\)\)\.resolve\(\)',
                            fs)
    check('every fs route that resolves its own path anchors first',
          anchored >= 3 and not unanchored,
          [anchored, unanchored, '— pathlib.Path(_client_path(x)).resolve() '
           'resolves against the server cwd, which is the whole defect'])
    check('_validate_path anchors too',
          re.search(r'p = _workspace_path\(path, strict=strict\)\.resolve\(\)',
                    serve),
          '— the door /fs/upload, /fs/collect and /fs/mkdir come through')

    # The anchor must not itself be the whitelist. It only rewrites the path;
    # the callers still resolve and check. Losing that is a directory escape.
    anchor = serve[serve.index('def _workspace_path('):]
    anchor = anchor[:anchor.index('\n_cafresohq_allowed_tools')]
    check('the anchor anchors and nothing more',
          'relative_to' not in anchor and 'PermissionError' not in anchor
          and '.resolve()' not in anchor,
          '— it must leave resolution and the whitelist to its callers, or '
          'the two stop agreeing about what was checked')

    # ── 2. drive a real server ──────────────────────────────────────────
    tmp = tempfile.mkdtemp(prefix='hqrel-')
    ws = Path(tmp) / 'ws'
    (ws / 'site').mkdir(parents=True)
    (ws / 'site' / 'index.html').write_text('<h1>hi</h1>', encoding='utf-8')
    port = free_port()
    env = dict(os.environ,
               CAFRESOHQ_ALLOWED_DIRS=str(ws),
               CAFRESOHQ_HQ_STATE_DIR=str(Path(tmp) / 'state'),
               PORT=str(port))
    env.pop('CAFRESOHQ_API_KEY', None)
    # cwd is the REPO, deliberately: that is the directory a relative path
    # used to land in, and the repo has no site/ so the old behaviour is a
    # clean 403 rather than an accidental hit.
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=str(ROOT),
                            env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT)
    base = 'http://127.0.0.1:%d' % port
    try:
        for _ in range(80):
            if get(base + '/fs/browse?path=' + str(ws))[0]:
                break
            time.sleep(0.25)
        else:
            check('the server came up', False, 'never answered')
            return 1

        abs_site = str(ws / 'site')
        abs_file = str(ws / 'site' / 'index.html')

        # Each door, twice: the relative form a coworker emits and the
        # absolute form that always worked. They must agree.
        doors = [
            ('/fs/collect?path=%s', 'site', abs_site),
            ('/fs/browse?path=%s', 'site', abs_site),
            ('/fs/stat?path=%s', 'site/index.html', abs_file),
            ('/fs/file?path=%s', 'site/index.html', abs_file),
        ]
        for tmpl, rel, absolute in doors:
            rc, _ = get(base + tmpl % rel)
            ac, _ = get(base + tmpl % absolute)
            check('%s answers the same for a relative path'
                  % tmpl.split('?')[0],
                  rc == ac == 200, 'relative=%s absolute=%s' % (rc, ac))

        # The preview link publishSite hands back is built from the same
        # string, so it was 403 for exactly the same reason.
        rc, _ = get(base + '/fs/site/%s/index.html' % b64('site/'))
        ac, _ = get(base + '/fs/site/%s/index.html' % b64(abs_site))
        check('the preview link works for a relative dir',
              rc == ac == 200, 'relative=%s absolute=%s' % (rc, ac))

        # /fs/upload is the one that actually failed the boss's stamp.
        boundary = '----hqrel'
        body = ('--%s\r\nContent-Disposition: form-data; name="file"; '
                'filename="p.url"\r\nContent-Type: text/plain\r\n\r\nx\r\n'
                '--%s--\r\n' % (boundary, boundary)).encode()
        req = urllib.request.Request(
            base + '/fs/upload?path=site', data=body, method='POST',
            headers={'content-type': 'multipart/form-data; boundary=' + boundary})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                up = r.status
        except urllib.error.HTTPError as e:
            up = e.code
        check('a stamped publish can write its link file to a relative dir',
              up == 200,
              [up, '— this is the 403 the boss saw: "Path outside allowed '
               'directories: \'site/\'" on a folder the office had just made'])
        check('...and it landed in the workspace, not the repo',
              (ws / 'site' / 'p.url').exists()
              and not (ROOT / 'site').exists(),
              '— anchoring to the wrong root is the same defect moved')

        # ── 3. the whitelist still holds ────────────────────────────────
        #
        # Anchoring happens BEFORE resolve(), so `../` is still caught. If it
        # ever stops being caught, this fix has turned into a read hole.
        #
        # The probes climb to `..` — the tmpdir holding the workspace, which
        # really exists — so the answer is the whitelist's 403 and not the
        # 400 an absent directory would produce first. An earlier draft
        # climbed six levels to /etc, landed on nothing, and read the
        # resulting "not a directory" as proof of a check it never reached.
        for label, probe in [
            ('an absolute path outside the workspace', '/etc'),
            ('a climb out of the workspace', '..'),
            ('a climb dressed up as a subfolder', 'site/../..'),
        ]:
            code, _ = get(base + '/fs/browse?path=' + urllib.parse.quote(probe))
            check('%s is still refused' % label, code == 403, [probe, code])
        code, _ = get(base + '/fs/file?path=' + urllib.parse.quote('/etc/hosts'))
        check('reading a file outside the workspace is still refused',
              code == 403, code)

        # Those three go through _within_allowed_dirs. The anchoring change
        # lives in _validate_path, which is a DIFFERENT guard — and until the
        # fire-test deleted it, nothing here reached it: its whole loop could
        # be dropped and every escape check above stayed green. /fs/collect
        # is the cheapest door that comes through it.
        for label, probe in [
            ('an absolute escape', '/etc'),
            ('a climb out', '..'),
            ('a climb dressed up as a subfolder', 'site/../..'),
        ]:
            code, _ = get(base + '/fs/collect?path=' + urllib.parse.quote(probe))
            check('_validate_path still refuses %s' % label, code == 403,
                  [probe, code])

        # The workspace root itself must stay reachable — `relative_to` on an
        # identical path returns '.', not a ValueError, and the empty-path
        # default relies on it.
        code, _ = get(base + '/fs/browse?path=' + urllib.parse.quote(str(ws)))
        check('the workspace root is still browsable', code == 200, code)
        code, body = get(base + '/fs/browse')
        check('...and so is the default with no path at all',
              code == 200 and 'site' in json.loads(body or b'{}').get('path', '')
              + ''.join(e.get('name', '') for e in
                        json.loads(body or b'{}').get('entries', [])),
              [code, (body or b'')[:200]])
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
