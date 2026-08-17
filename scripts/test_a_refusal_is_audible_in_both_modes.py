#!/usr/bin/env python3
"""The default mode swallowed a refused folder name; the legacy mode explained.

Driven live on the Workspace (the DEFAULT project mode): Files pane, ＋, type
`docs/notes`, OK. The dialog closes. No folder, no toast, no word — disk
checked, nothing created. The same keystrokes in the classic Projects view
answer out loud:

    Folder name can't contain slashes.

Both Workspace prompts ended in the same shape:

    if (!name || /[\\/\\\\]/.test(name)) return;

which files three different inputs under one silent return: an empty name
(the boss cancelling — a no-op is right), an unchanged name (same), and a
name the office REFUSED. A dialog that accepts input is itself a claim —
"this is a name I can use" — so the silence afterwards reads as success, and
the boss goes looking for a folder that was never made. The office had three
doors onto the same folder and three answers to a bad name: classic explains,
the upload door renames and says so (#137), and the default mode said
nothing at all.

The invariant this suite pins: a refusal is audible, and the two modes answer
the same input with the same words. A cancel stays silent — that is the boss
declining, not the office.

Run: python3 scripts/test_a_refusal_is_audible_in_both_modes.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJ = ROOT / 'views' / 'projects.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run_js(js):
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-1600:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(p.stdout.strip().split('\n')[-1])


def brace_lift(src, header, start=0):
    """`header` plus its balanced `{ … }` body, verbatim, from `start` on.

    Anchored on the DECLARATION, never on the fix: a lift anchored on the fix
    returns '' when the fix is removed, and a check that cannot find its
    subject is skipped rather than failed. `start` matters here because BOTH
    modes declare `newFolder` and `renameEntry` — first hit is Workspace,
    second is classic."""
    i = src.index(header, start)
    j = src.index('{', i + len(header) - 1)
    d, k = 0, j
    while k < len(src):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                return src[i:k + 1], k
        k += 1
    raise SystemExit('unbalanced braces lifting ' + header)


STUBS = """
const calls = [];
const toasts = [];
const project = { id: 'p1', path: '/home/boss/work/site' };
const C = {
  fsMkdir: async (p) => calls.push(['mkdir', p]),
  fsRename: async (a, b) => calls.push(['rename', a, b]),
};
const CafresoHQClient = C;
const fsOK = () => C;
const fsClient = () => C;
const joinPath = (a, b) => a.replace(/\\/+$/, '') + '/' + b;
const isUnder = (p, base) => p === base || p.indexOf(base + '/') === 0;
const toast = (tone, text) => toasts.push({ tone, text });
const snag = (label, e) => toasts.push({ tone: 'snag', text: label });
const setTreeNonce = () => {};
const setBusy = () => {};
const setErr = () => {};
const setOpenFile = () => {};
const openFileRef = { current: null };
const openFile = null;
globalThis.window = globalThis;
"""


def drive(fn_src, call, answer):
    """Run one lifted handler with the prompt answering `answer`."""
    js = (STUBS
          + f'window.hqPrompt = async () => {json.dumps(answer)};\n'
          + 'window.hqConfirm = async () => true;\n'
          + fn_src + '\n'
          + f'await {call};\n'
          + 'console.log(JSON.stringify({ calls, toasts }));')
    return run_js(js)


def main():
    src = PROJ.read_text(encoding='utf-8')

    ws_new, end = brace_lift(src, 'const newFolder = async () => {')
    cl_new, _ = brace_lift(src, 'const newFolder = async () => {', end)
    ws_ren, end = brace_lift(src, 'const renameEntry = async (entry) => {')
    cl_ren, _ = brace_lift(src, 'const renameEntry = async (entry) => {', end)

    ENTRY = ("{ name: 'notes.md', path: '/home/boss/work/site/notes.md', "
             "isDir: false }")

    print('the default mode, a bad name in hand')
    r = drive(ws_new, 'newFolder()', 'docs/notes')
    check('a slashed folder name is refused out loud',
          len(r['toasts']) == 1 and r['toasts'][0]['tone'] == 'error',
          f"{r} — this was the ticket: the dialog closed and nothing was "
          'said; the silence after an accepted input reads as success')
    check('...the refusal says what was wrong with it',
          r['toasts'] and 'slash' in r['toasts'][0]['text'].lower(),
          f"{r['toasts']} — 'error' with no reason is a light, not a sentence")
    check('...and nothing was created behind it',
          r['calls'] == [],
          f"{r['calls']} — a refusal that still runs the mkdir is worse than "
          'the silence was')

    r = drive(ws_ren, f'renameEntry({ENTRY})', 'a/b.md')
    check('a slashed rename is refused out loud, nothing renamed',
          len(r['toasts']) == 1 and r['toasts'][0]['tone'] == 'error'
          and 'slash' in r['toasts'][0]['text'].lower() and r['calls'] == [],
          r)

    print('\na cancel is not a refusal')
    for label, fn, call, ans in [
            ('an empty folder name stays a silent no-op', ws_new,
             'newFolder()', '   '),
            ('an unchanged rename stays a silent no-op', ws_ren,
             f'renameEntry({ENTRY})', 'notes.md')]:
        r = drive(fn, call, ans)
        check(label, r['toasts'] == [] and r['calls'] == [],
              f'{r} — the boss declining is not the office refusing; a toast '
              'here scolds a cancel')

    print('\nthe good path still works')
    r = drive(ws_new, 'newFolder()', 'docs')
    check('a clean name makes the folder and says so',
          r['calls'] == [['mkdir', '/home/boss/work/site/docs']]
          and any(t['tone'] == 'success' for t in r['toasts']), r)
    r = drive(ws_ren, f'renameEntry({ENTRY})', 'plan.md')
    check('a clean rename lands next to the old name and says so',
          r['calls'] == [['rename', '/home/boss/work/site/notes.md',
                          '/home/boss/work/site/plan.md']]
          and any(t['tone'] == 'success' for t in r['toasts']), r)

    print('\nboth modes, one voice')
    # The classic handlers run through the same stubs: same input, and the
    # sentence must be THE SAME SENTENCE, not merely both-audible. Two modes
    # explaining the same refusal in different words invite the boss to think
    # the rules differ between them.
    wf = drive(ws_new, 'newFolder()', 'docs/notes')['toasts']
    cf = drive(cl_new, 'newFolder()', 'docs/notes')['toasts']
    check('classic still refuses the slashed folder name out loud',
          len(cf) == 1 and cf[0]['tone'] == 'error'
          and 'slash' in cf[0]['text'].lower(),
          f'{cf} — this is the voice the fix borrowed; losing it re-opens '
          'the gap from the other side')
    check('and both modes refuse it in the same words',
          wf and cf and wf[0]['text'] == cf[0]['text'], f'ws={wf} classic={cf}')
    wr = drive(ws_ren, f'renameEntry({ENTRY})', 'a/b.md')['toasts']
    cr = drive(cl_ren, f'renameEntry({ENTRY})', 'a/b.md')['toasts']
    check('same for the rename refusal',
          wr and cr and len(cr) == 1 and cr[0]['tone'] == 'error'
          and wr[0]['text'] == cr[0]['text'], f'ws={wr} classic={cr}')

    print()
    if FAILS:
        print(f'audible refusal: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('audible refusal: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
