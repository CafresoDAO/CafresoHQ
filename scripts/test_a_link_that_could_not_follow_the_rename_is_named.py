#!/usr/bin/env python3
"""A rename that stranded a [[link]] reported the same as one with no links.

#325 taught /vault/rename to walk the vault and make inbound [[wikilinks]]
follow a moved note, and the Library says so: "Moved — 2 links in 2 notes
followed the rename." The walk reads each note with a strict
`p.read_text(encoding='utf-8')` and answered anything it could not read or
write with a bare `continue`. So a note whose bytes aren't utf-8 — a .md
exported from Word, an old latin-1 archive, both of which the Library's own
upload door accepts — was skipped in silence, and so was a read-only one.
The receipt then said `linksRewritten: 1`, which is indistinguishable from
a vault where only one note ever linked here.

Worse, the office had already shown the boss that link: kg_builder's
_build_graph_fs reads the same note with errors='replace' and draws its
edge, so the Graph and the ⇐ linked-from row both list a backlink that the
rename then declines to move and declines to mention. Driven live before
the fix: three notes linked one note, the graph drew three edges, the
rename answered 200 {"linksRewritten": 1}, and two notes were left pointing
at a file that no longer exists with no message anywhere.

Now the pass collects every note it could not follow and the receipt names
them — `linksStranded` — and the Library says which notes still point at
the old name. A note it cannot decode is DETECTED the graph builder's way
(errors='replace') and still never written: writing that decoding back
would swap the boss's accents for U+FFFD to fix a link.

Run: python3 scripts/test_a_link_that_could_not_follow_the_rename_is_named.py
"""
import ast
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift_function(src, name):
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise SystemExit(f'{name} not found in serve.py')


LATIN1 = 'Notes from Jos\xe9: see [[old-note]] for the numbers.\n'.encode('latin-1')


# ── the pass itself, lifted out of serve.py ───────────────────────────────
def unit_checks(serve):
    print('=== the rewrite pass, on a vault it cannot fully rewrite ===')
    fn = lift_function(serve, '_vault_rewrite_wikilinks')
    with tempfile.TemporaryDirectory() as td:
        vault = pathlib.Path(td)
        (vault / 'Research').mkdir()
        (vault / 'linker-utf8.md').write_text('Also see [[old-note]].\n',
                                              encoding='utf-8')
        (vault / 'linker-latin1.md').write_bytes(LATIN1)
        (vault / 'linker-readonly.md').write_text('And [[old-note]] too.\n',
                                                  encoding='utf-8')
        (vault / 'unrelated.md').write_text('Nothing to do with it.\n',
                                            encoding='utf-8')
        os.chmod(vault / 'linker-readonly.md', 0o444)
        ns = {'pathlib': pathlib, 're': re, 'urllib': urllib,
              '_vault_root': str(vault)}
        exec(fn, ns)

        stranded = []
        links, files = ns['_vault_rewrite_wikilinks'](
            'Research/old-note.md', 'Archive/new-note.md', stranded)

        check('the note it can rewrite still follows the rename',
              (links, files) == (1, 1), (links, files))
        check('a note whose bytes are not utf-8 is named, not skipped',
              'linker-latin1.md' in stranded, stranded)
        check('a note it cannot write is named too',
              'linker-readonly.md' in stranded, stranded)
        check('a note with no inbound link is NOT named',
              'unrelated.md' not in stranded and 'linker-utf8.md' not in stranded,
              stranded)
        check('the undecodable note is left byte-for-byte alone',
              (vault / 'linker-latin1.md').read_bytes() == LATIN1,
              (vault / 'linker-latin1.md').read_bytes())
        check('...so no accent was traded for a replacement character',
              '�' not in (vault / 'linker-latin1.md')
              .read_bytes().decode('latin-1'))

        # the old two-value contract still holds for every existing caller
        stranded2 = []
        again = ns['_vault_rewrite_wikilinks'](
            'Research/old-note.md', 'Archive/new-note.md', stranded2)
        check('a second pass rewrites nothing and strands the same notes',
              again == (0, 0) and sorted(stranded2) ==
              ['linker-latin1.md', 'linker-readonly.md'], (again, stranded2))
        check('the out-list is optional — old call sites still work',
              ns['_vault_rewrite_wikilinks']('a.md', 'b.md') == (0, 0))
        os.chmod(vault / 'linker-readonly.md', 0o644)

    print()
    print('=== the receipt fragment ===')
    fn2 = lift_function(serve, '_vault_link_trouble')
    ns2 = {}
    exec(fn2, ns2)
    trouble = ns2['_vault_link_trouble']
    check('a clean rename adds nothing to the body', trouble([]) == {})
    check('stranded notes are sorted and deduped',
          trouble(['b.md', 'a.md', 'b.md']) ==
          {'linksStranded': ['a.md', 'b.md']}, trouble(['b.md', 'a.md', 'b.md']))
    check('a pass that fell over outright is carried too',
          trouble([], 'boom').get('linksError') == 'boom')


# ── live: the door a boss actually walks ──────────────────────────────────
def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def req(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data,
                               method='POST' if data else 'GET',
                               headers={'content-type': 'application/json'})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)


def boot(vault_root, state_dir, work_dir):
    port = free_port()
    env = dict(os.environ, PORT=str(port), CAFRESOHQ_VAULT=str(vault_root),
               CAFRESOHQ_HQ_STATE_DIR=str(state_dir),
               CAFRESOHQ_ALLOWED_DIRS=str(work_dir))
    for k in ('OCI_VAULT_NAMESPACE', 'OCI_VAULT_BUCKET', 'OCI_VAULT_PREFIX',
              'CAFRESOHQ_VAULT_BACKEND', 'CAFRESOHQ_OBSIDIAN_URL',
              'CAFRESOHQ_OBSIDIAN_KEY'):
        env.pop(k, None)
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=str(ROOT),
                            env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT)
    base = 'http://127.0.0.1:%d' % port

    def kill():
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    for _ in range(80):
        if req(base + '/missions/scheduled')[0] == 200:
            return base, kill
        time.sleep(0.25)
    kill()
    return None, (lambda: None)


def live_checks():
    print()
    print('=== /vault/rename, live ===')
    with tempfile.TemporaryDirectory() as td:
        vault = pathlib.Path(td) / 'vault'
        (vault / 'Research').mkdir(parents=True)
        state = pathlib.Path(td) / 'state'
        state.mkdir()
        work = pathlib.Path(td) / 'work'
        work.mkdir()
        (vault / 'linker-utf8.md').write_text('Also see [[old-note]].\n',
                                              encoding='utf-8')
        (vault / 'linker-latin1.md').write_bytes(LATIN1)
        (vault / 'Research' / 'old-note.md').write_text('# the numbers\n',
                                                        encoding='utf-8')
        base, kill = boot(vault, state, work)
        if not base:
            check('serve.py boots', False, 'never answered')
            return
        try:
            st, g = req(base + '/vault/graph')
            edges = [e for e in json.loads(g).get('edges', [])
                     if e.get('target') == 'Research/old-note.md']
            check('the graph draws BOTH backlinks — including the latin-1 one',
                  sorted(e['source'] for e in edges) ==
                  ['linker-latin1.md', 'linker-utf8.md'], edges)

            st, body = req(base + '/vault/rename',
                           {'from': 'Research/old-note.md',
                            'to': 'Archive/new-note.md'})
            res = json.loads(body)
            check('the move still succeeds', st == 200, (st, body))
            check('the link it could follow is counted',
                  res.get('linksRewritten') == 1, res)
            check('the link it could NOT follow is named in the receipt',
                  res.get('linksStranded') == ['linker-latin1.md'], res)
            check('the note really does still point at the old name',
                  '[[old-note]]' in (vault / 'linker-latin1.md')
                  .read_bytes().decode('latin-1'))

            # a rename with nothing in the way stays quiet
            (vault / 'plain.md').write_text('# plain\n', encoding='utf-8')
            st2, body2 = req(base + '/vault/rename',
                             {'from': 'plain.md', 'to': 'plain-2.md'})
            check('a rename with nothing stranded says nothing extra',
                  st2 == 200 and 'linksStranded' not in json.loads(body2)
                  and 'linksError' not in json.loads(body2), body2)
        finally:
            kill()


def ui_checks():
    print()
    print('=== the Library says it ===')
    jsx = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')
    check('the view reads linksStranded', 'linksStranded' in jsx)
    check('...and says which notes still point at the old name',
          'still point' in jsx, )
    check('...as a warning, not as part of the success line',
          re.search(r"still point[\s\S]{0,400}'warn'", jsx))
    check('both rename doors say it',
          jsx.count('sayStranded(res)') == 2, jsx.count('sayStranded(res)'))
    check('a rewrite pass that fell over is spoken too',
          'linksError' in jsx)


def main():
    print('a link that could not follow the rename is named')
    serve = (ROOT / 'serve.py').read_text(encoding='utf-8')
    check('the rename passes an out-list to the rewrite pass',
          re.search(r'_vault_rewrite_wikilinks\(\s*src, dst, stranded\)', serve))
    check('...and the folder arm shares the same list',
          re.search(r"d_rel \+ '/' \+ tail, stranded\)", serve))
    check('the swallowed continue is gone from the read half',
          not re.search(r"text = p\.read_text\(encoding='utf-8'\)\s*\n"
                        r"\s*except Exception:\s*\n\s*continue", serve))
    unit_checks(serve)
    live_checks()
    ui_checks()

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
