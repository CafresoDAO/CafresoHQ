#!/usr/bin/env python3
"""The browser was running the previous build and nothing said so.

Measured 2026-08-14, verifying a fix to modals/settings.jsx on a freshly
started office: the Roster still rendered the old checkboxes. The corrected
file was provably being served —

    $ curl -s http://127.0.0.1:9251/modals/settings.jsx | grep -n GRANTED
    402:    .filter(t => !GRANTED_ELSEWHERE_TOOL_IDS.has(t.id))
    $ curl -sI http://127.0.0.1:9251/modals/settings.jsx | grep Cache
    Cache-Control: no-store, must-revalidate

— and there was no service worker and no cache. It took eight tool calls to
find the reason: nothing loads that file. hq.html carries an
<!--HQ_SCRIPTS--> placeholder which serve.py fills from
dist-ui/manifest.json, and the JSX is pre-transformed into that bundle by
scripts/build_ui_bundle.mjs. serve.py serves the bundle and never rebuilds
it, so the drive was exercising a build 22 minutes older than the edit.

A stale bundle is indistinguishable from a fix that did not work, which is
the worst shape a dev-loop failure can take: it accuses the change.

Two halves, and the second is the one that bites:

1. serve.py now says so — once at startup, and again as a console.warn in
   the page itself, because the log line is not where anyone is looking
   when they are asking "why didn't my change land".
2. The dependency set is EVERY .jsx, not the thirteen the builder names.
   APP_FILES are barrels; 45 of the 58 .jsx files in the tree are reached
   only through their imports. The builder's own --watch mode watched just
   those thirteen plus a NON-recursive watch on the root — so editing
   modals/settings.jsx or app/cast.jsx never triggered a rebuild while
   --watch printed "watching for changes…". A staleness check built on the
   named list would have inherited exactly the same blind spot and gone on
   reporting "fresh" for the files most likely to be edited.

Run: python3 scripts/test_the_bundle_says_when_it_is_stale.py
"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVE = ROOT / 'serve.py'
BUILDER = ROOT / 'scripts' / 'build_ui_bundle.mjs'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_block(src, after, keyword):
    """The body of the first `keyword {` following `after`, brace-matched.

    Proximity windows (`catch\\s*\\{[\\s\\S]{0,400}?…`) read whatever
    happens to sit nearby, including the next unrelated block. Counting
    braces bounds the search to the construct actually being asked about.
    """
    i = src.find(after)
    if i < 0:
        return None
    j = src.find(keyword, i)
    k = src.find('{', j) if j >= 0 else -1
    if k < 0:
        return None
    depth, end = 0, None
    for n in range(k, len(src)):
        if src[n] == '{':
            depth += 1
        elif src[n] == '}':
            depth -= 1
            if depth == 0:
                end = n
                break
    return src[k + 1:end] if end else None


def load_helpers():
    """Lift the three helpers out of serve.py and run them for real.

    serve.py cannot be imported (it binds a port and starts threads at
    module scope), so the functions are extracted by source. Extracted
    rather than restated, so a rewrite is measured here instead of
    quietly diverging.
    """
    src = SERVE.read_text(encoding='utf-8')
    ns = {'os': os}
    for fn in ('_ui_sources', '_ui_bundle_stale', '_ui_stale_sentence'):
        m = re.search(r'^def %s\(.*?(?=\n\ndef |\n\nclass )' % fn, src,
                      re.M | re.S)
        if not m:
            raise SystemExit('could not lift %s from serve.py' % fn)
        exec(compile(m.group(0), 'serve.py:' + fn, 'exec'), ns)
    return ns


def main():
    print('a stale UI bundle says so instead of looking like a broken fix')
    ns = load_helpers()

    # ── 1. the walk finds what the barrels hide ─────────────────────────
    found = ns['_ui_sources'](str(ROOT))
    rel = sorted(os.path.relpath(f, ROOT) for f in found)
    nested = [f for f in rel if os.sep in f]
    check('the source walk finds the real tree', len(rel) >= 40,
          f'{len(rel)} source file(s) — if this collapses the staleness '
          'check silently starts measuring nothing')
    check('...including the files the barrels import',
          len(nested) > len(rel) - len(nested),
          f'{len(nested)} of {len(rel)} are in subdirectories; the builder '
          'names only the 13 root barrels, and the nested ones are where '
          'the UI actually lives')
    for must in ('modals/settings.jsx', 'app/cast.jsx'):
        check(f'...such as {must}', must.replace('/', os.sep) in rel,
              'this exact file is the one whose edit went unnoticed')
    check('the walk skips build output and vendor code',
          not any('node_modules' in f or 'dist-ui' in f for f in rel),
          [f for f in rel if 'node_modules' in f or 'dist-ui' in f])

    # ── 2. the staleness verdict, run against a real directory ──────────
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, 'dist-ui'))
        os.makedirs(os.path.join(td, 'modals'))
        src = os.path.join(td, 'modals', 'settings.jsx')
        manifest = os.path.join(td, 'dist-ui', 'manifest.json')

        Path(src).write_text('x')
        Path(manifest).write_text('{}')
        os.utime(src, (1_700_000_000, 1_700_000_000))
        os.utime(manifest, (1_700_003_600, 1_700_003_600))   # built an hour later
        check('a bundle newer than every source is not called stale',
              ns['_ui_bundle_stale'](td) is None,
              ns['_ui_bundle_stale'](td))

        os.utime(src, (1_700_007_200, 1_700_007_200))        # edited an hour after that
        stale = ns['_ui_bundle_stale'](td)
        check('a source newer than the bundle is caught', stale is not None)
        check('...and the verdict names the file that moved',
              stale and stale[0].endswith('settings.jsx'), stale)
        check('...and how far behind the bundle is',
              stale and abs(stale[1] - 3600) < 2, stale)

        sentence = ns['_ui_stale_sentence'](stale) if stale else ''
        check('the warning names the command that fixes it',
              'node scripts/build_ui_bundle.mjs' in sentence, sentence)
        check('...and says which file is ahead of the build',
              'settings.jsx' in sentence, sentence)
        check('...and says plainly that this is the previous build',
              'previous build' in sentence, sentence)
        # §6: the reader here is a developer, but the rule that a message
        # states a fact and a way forward is the same one the office copy
        # follows. A bare "stale bundle" would pass a keyword check and
        # tell nobody what to do.
        check('...in a sentence, not a status word',
              len(sentence.split()) >= 12, sentence)

        # Missing manifest is a DIFFERENT failure with a different remedy —
        # _serve_hq_html 500s and names the build command. Reporting it as
        # "stale" would send someone to rebuild when they never built.
        os.remove(manifest)
        check('a bundle that was never built is not reported as stale',
              ns['_ui_bundle_stale'](td) is None,
              'never-built and out-of-date have different remedies')

    # ── 3. both callers are wired ───────────────────────────────────────
    # Parsed, not grepped. The first draft normalised serve.py by stripping
    # /* … */ before searching — which is meaningless in Python and, worse,
    # actively destructive: serve.py embeds CSS and JS in string literals,
    # so the non-greedy match ran from a comment in one embedded stylesheet
    # to a comment in another and deleted ~100KB of live code, including
    # the very lines under test. The check then reported the feature
    # missing. An AST walk cannot be fooled by a comment OR by a string.
    serve_src = SERVE.read_text(encoding='utf-8')
    tree = ast.parse(serve_src)

    def fn_named(name):
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        return None

    def calls_in(node):
        return {c.func.id for c in ast.walk(node)
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}

    def strings_in(node):
        return [s.value for s in ast.walk(node)
                if isinstance(s, ast.Constant) and isinstance(s.value, str)]

    serve_html = fn_named('_serve_hq_html')
    check('the page-serving path exists to check from', serve_html is not None)
    if serve_html:
        check('...and it asks whether the bundle is current',
              '_ui_bundle_stale' in calls_in(serve_html),
              sorted(calls_in(serve_html)))
        check('...and says so in the page, not only the log',
              any('console.warn' in s for s in strings_in(serve_html)),
              'the log line alone is not where someone debugging "my change '
              'did not land" is looking')
        check('...using the one shared sentence',
              '_ui_stale_sentence' in calls_in(serve_html),
              'two hand-written wordings drift apart; there is one sentence')

    # The banner lives inside the __main__ block, which is module-level
    # code rather than a function, so it is checked by walking the module
    # for the pairing instead of by name.
    banner = [n for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == '_ui_bundle_stale']
    check('the startup banner checks too', len(banner) >= 2,
          f'{len(banner)} call site(s) — the page and the banner are two '
          'different moments, and someone starting the server sees only one '
          'of them')

    # Measured on a real office (port 9252, 2026-08-15): the banner was
    # present, correct, and INVISIBLE. Python block-buffers stdout when it is
    # not a tty, and the request log comes from BaseHTTPRequestHandler on
    # stderr — so `nohup python3 serve.py > log` showed the traffic and never
    # the warning. "The line is in the code" is not the same claim as "the
    # line reaches the reader", which is the whole subject of this ticket.
    printed = [n for n in ast.walk(tree)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == 'print'
               and any('_ui_stale_sentence' == getattr(getattr(c, 'func', None), 'id', None)
                       for c in ast.walk(n))]
    check('the banner is printed at all', printed)
    check('...and flushed, so a redirected stdout still shows it',
          printed and all(any(k.arg == 'flush' and k.value.value is True
                              for k in p.keywords) for p in printed),
          'without flush=True the warning sits in a buffer under nohup, '
          'systemd, or Electron — every non-tty launch there is')

    # ── 4. the watcher covers the same set ──────────────────────────────
    b = BUILDER.read_text(encoding='utf-8')
    check('the watcher is recursive',
          re.search(r'fs\.watch\(ROOT,\s*\{\s*recursive:\s*true\s*\}', b),
          'a non-recursive watch on the root cannot see modals/ or app/ — '
          'and would not match them anyway, since the change surfaces as '
          '"modals", which does not end in .jsx')
    # Scoped to the catch block by brace-matching rather than by proximity.
    # A first draft asked only whether `listUiSources` and `fs.watch(d`
    # appeared somewhere in the file, and passed with the fallback gutted:
    # `listUiSources` still matched its own definition, and `fs.watch(d`
    # still matched a loop over a Set nothing put anything into. That is
    # this ticket's own defect wearing a different hat — a fallback that
    # is present, reported, and watches nothing.
    fallback = brace_block(b, 'fs.watch(ROOT, { recursive: true }', 'catch')
    check('...with a fallback where recursive watch is unavailable',
          fallback and 'listUiSources(' in fallback and 'fs.watch(d' in fallback,
          'recursive fs.watch is not supported on Linux; without a fallback '
          'the blind spot comes back for anyone not on macOS or Windows')
    check('...and the fallback watches the same set the check walks',
          fallback and re.search(r'listUiSources\(ROOT\)[\s\S]{0,60}?dirs\.add', fallback),
          'the directory set has to be FILLED from the source walk; a '
          'fallback that iterates an empty Set still logs that it is '
          'watching, which is the failure this whole ticket is about')

    # The two implementations of "what the bundle is built from" — one in
    # Python, one in JS — have to agree, or the warning and the rebuild
    # disagree about which edits count.
    if shutil.which('node'):
        js = ('%s\nconsole.log(listUiSources(%s).length);'
              % (re.search(r'function listUiSources[\s\S]*?\n\}', b).group(0),
                 json.dumps(str(ROOT))))
        js = "import fs from 'fs';\nimport path from 'path';\n" + js
        p = subprocess.run(['node', '--input-type=module', '-e', js],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        n_js = int(p.stdout.strip().split('\n')[-1]) if p.returncode == 0 else -1
        check('the builder and the server agree on the source set',
              n_js == len(found),
              f'node found {n_js}, python found {len(found)} — the warning '
              'and the rebuild would disagree about which edits count')
    else:
        print('  SKIP  node not on PATH (cross-language agreement)')

    print()
    if FAILS:
        print(f'stale bundle: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('stale bundle: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
