#!/usr/bin/env python3
"""A project folder that moved drew itself as a file called "Not a directory".

The Workspace file tree lists a project with the office's own DIR_LIST tool,
and that tool does not raise when the folder is gone. serve.py says so in
its own words next to the flag it sets instead: "a missing file or a path
that isn't a directory are ordinary answers to an ordinary question, so they
come back 200 with the explanation as the result ... every surface that
renders the event was reading 'there is a result' as 'it worked'."

The tree was one of those surfaces. Rename, move, or delete a project folder
on disk (or add a project whose path is a file) and the listing came back as
the single line

    Not a directory: /Users/…/projects/site

which parseDirEntries dutifully turned into ONE FILE ROW named after the
refusal. The boss saw a folder that still opened, holding one strangely
named file; clicking it produced a second, unrelated failure from the file
reader. Nothing on that screen said the folder was missing.

Meanwhile the tree already HAD the honest screen — the red "Couldn't read
this folder" sentence and its ↻ TRY AGAIN button, whose own comment names
"a folder that moved (ENOENT)" as the case it was written for. It was
unreachable for the commonest way a listing fails, because that failure
arrived as a 200. One level down, a subfolder whose listing failed was
cached as [] and drawn OPEN AND EMPTY — a claim about its contents.

This drives the real effect and the real loadSub, lifted from
views/ide.jsx, against a toolExec that fails the way the server actually
fails.

Run: python3 scripts/test_a_folder_that_moved_is_not_a_file_named_not_a_directory.py
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IDE = (ROOT / 'views' / 'ide.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Drop /* */ and // comments so our own prose can't satisfy a check."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'(?m)^\s*//.*$', '', src)


def lift(src, start, end):
    i = src.find(start)
    if i < 0:
        return None
    j = src.find(end, i)
    if j < 0:
        return None
    return src[i:j + len(end)]


PROBE_HEAD = r'''
const state = { entries: undefined, err: null, loading: false, subEntries: {} };
const setEntries = v => { state.entries = v; };
const setErr = v => { state.err = v; };
const setLoading = v => { state.loading = v; };
const setSubEntries = f => { state.subEntries = (typeof f === 'function') ? f(state.subEntries) : f; };
Object.defineProperty(globalThis, 'subEntries', { get: () => state.subEntries });
const officeCause = s => 'OFFICE(' + String(s) + ')';
const CASE = process.argv[2];
const calls = [];
const CafresoHQClient = {
  toolExec: async (tool, p, opts) => {
    calls.push(p);
    /* Exactly what serve.py answers for a path that is missing or not a
       directory: HTTP 200, ok:true, failed:true, refusal AS the result. */
    if (CASE === 'fail') { if (opts && opts.meta) opts.meta.failed = true; return 'Not a directory: ' + p; }
    return 'sub/\nnotes.md  (12 B)';
  },
};
const path = '/w/proj';
const refreshNonce = 0, retryNonce = 0;
'''

PROBE_TAIL = r'''
(async () => {
  EFFECT();
  await new Promise(r => setTimeout(r, 20));
  loadSub('/w/proj/sub');
  await new Promise(r => setTimeout(r, 20));
  const before = calls.length;
  loadSub('/w/proj/sub');          // re-open: a failed listing must retry
  await new Promise(r => setTimeout(r, 20));
  state.retried = calls.length > before;
  console.log(JSON.stringify(state));
})();
'''


def run(effect_src, sub_src, helpers, case):
    """Run the REAL effect body and the REAL loadSub, verbatim from the file."""
    inner = effect_src.split('React.useEffect(() => {', 1)[1]
    inner = inner[:inner.rindex('}, [path, refreshNonce, retryNonce]);')]
    js = (PROBE_HEAD + helpers + '\n' + sub_src + '\n'
          + 'const EFFECT = () => {' + inner + '};\n'
          + PROBE_TAIL)
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / 'probe.cjs').write_text(js, encoding='utf-8')
        p = subprocess.run([shutil.which('node') or 'node', str(tmp / 'probe.cjs'), case],
                           capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            return None, 'node: ' + (p.stderr.strip()[:400] or 'no output')
        return json.loads(p.stdout.strip().splitlines()[-1]), None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print('a folder that moved is not a file named "Not a directory"')

    if not shutil.which('node'):
        print('  SKIP  node not available — cannot run the real listing code')
        return 0

    effect = lift(IDE, 'React.useEffect(() => {\n    if (!path) return;',
                  '}, [path, refreshNonce, retryNonce]);')
    sub = lift(IDE, '  const loadSub = (subPath) => {', '\n  };')
    parse = lift(IDE, 'function parseDirEntries(text, basePath) {', '\n  return out;\n}')
    refusal = lift(IDE, 'function listingRefusal(text) {', '\n}')
    check('lifted the root listing effect from views/ide.jsx', effect is not None)
    check('lifted loadSub from views/ide.jsx', sub is not None)
    check('lifted parseDirEntries', parse is not None)
    check('a refusal translator exists for the 200-with-failed answer',
          refusal is not None,
          'listingRefusal() is missing — the tree has nothing to say when the '
          'tool refuses without raising')
    if FAILS:
        print()
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1

    helpers = parse + '\n' + refusal

    # ── the folder is gone: the tool answers 200 with its refusal ──────────
    bad, err = run(effect, sub, helpers, 'fail')
    check('the failing case ran', bad is not None, err)
    if bad is not None:
        rows = bad.get('entries') or []
        names = [r.get('name') for r in rows]
        check('no file row is invented out of the refusal text',
              not any('Not a directory' in str(n) for n in names),
              'the tree drew a file called %r' % (names[:1],))
        check('the tree shows nothing rather than a fabricated listing',
              not rows, names)
        check('the boss is told the folder could not be read',
              bool(bad.get('err')), 'err stayed null, so the "Couldn\'t read '
              'this folder" screen and its TRY AGAIN button never appear')
        msg = str(bad.get('err') or '')
        check('...in a sentence, not the tool\'s refusal verbatim',
              'Not a directory' not in msg, msg)
        check('...that names the path the boss has to go find',
              '/w/proj' in msg, msg)
        check('...and says what happened to it',
              re.search(r'renamed|moved|deleted', msg) is not None, msg)
        check('the loading spinner is cleared on the failure path',
              bad.get('loading') is False)

        kids = (bad.get('subEntries') or {}).get('/w/proj/sub')
        check('a subfolder that could not be read is not cached as empty',
              kids != [], 'an open, empty folder is a claim about its contents')
        check('...it carries the sentence instead',
              isinstance(kids, dict) and bool(kids.get('error')), kids)
        check('...and re-opening it asks again instead of trusting the failure',
              bad.get('retried') is True)

    # ── the ordinary case still works ─────────────────────────────────────
    good, err = run(effect, sub, helpers, 'ok')
    check('the succeeding case ran', good is not None, err)
    if good is not None:
        names = [r.get('name') for r in (good.get('entries') or [])]
        check('a real listing still parses into rows', names == ['sub', 'notes.md'], names)
        check('a real listing raises no error', good.get('err') is None, good.get('err'))
        check('a real subfolder listing is still stored as an array',
              isinstance((good.get('subEntries') or {}).get('/w/proj/sub'), list))

    # ── the tree must actually DRAW the failed subfolder's sentence ────────
    src = strip_comments(IDE)
    check('the render branch tells an array of children from a failure',
          'Array.isArray(kids)' in src,
          'a non-array kids value would be handed to renderEntries')
    check('...and prints the failure where the children would have been',
          re.search(r'kids\s*&&\s*!Array\.isArray\(kids\)[\s\S]{0,400}kids\.error', src)
          is not None)
    check('the whole-tree failure screen and its retry button are untouched',
          'Couldn’t read this folder' in src and '↻ TRY AGAIN' in src)
    check('the listing still passes meta so the flag can be read at all',
          src.count("toolExec('DIR_LIST'") == 2
          and src.count('{ meta }') >= 2, src.count('{ meta }'))

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
