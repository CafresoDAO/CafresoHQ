#!/usr/bin/env python3
"""A ledger row has to land where the work actually went — and say so.

The Workspace's activity ledger is captioned "click any line to jump to it".
Measured live on 2026-08-13, in a throwaway office with one project and a
real coworker on it, three of those lines could not keep that promise:

    wrote     Research/remote-work.md      ← a VAULT_NEW
    wrote     Slides/pitch.pptx            ← an EXPORT_PPTX

Neither is in this folder. Every EXPORT_* tool's own doc string says so —
"the server renders the actual file and saves it to the vault" — and vault
notes go to the filing cabinet by definition. The ledger filed both with the
same verb a real write into this directory uses, so on the boss's record of
"what your coworkers did to this folder" they read as changes to the folder.

Clicking them asked THIS project for a vault path:

    GET /fs/file?path=Research%2Fremote-work.md   → 404
    GET /fs/file?path=Slides%2Fpitch.pptx         → 404

and NOTHING appeared on screen either way, because the pane's one error slot
lived inside the `openFile ?` branch — mounted only when a file is already
open, which is exactly when these failures cannot happen. A dead click, by
construction invisible.

Three fixes, all pinned here:

1. WHAT THE ROW SAYS. Vault notes are `noted`, exports are `exported`, and
   only a real FILE_WRITE is `wrote`. Only a write pulses the tree and
   refreshes it — the other two point at a tree that will never contain them.

2. WHERE THE CLICK GOES. Rows carry `where` ('folder' | 'cabinet'). A cabinet
   row opens the cabinet, via the one owner of that two-step (app.jsx
   publishes `window.cafresohqOpenNote`) rather than a copy that would rot.

3. THE FAILURE IS VISIBLE. The error slot is hoisted out of the `openFile ?`
   branch, so a click that cannot open anything says why.

Making it visible immediately surfaced the next lie: the server answered two
different questions with one string, "not a file", so a row pointing at a
FOLDER was reported to the boss as "the office couldn't find that" — the
opposite of what happened, and with no fix in it. Split server-side, mapped
office-side, and the folder rule has to sit BEFORE the missing-file rule or
it never runs.

Run: python3 scripts/test_the_ledger_row_lands_where_the_work_went.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJ = ROOT / 'views' / 'projects.jsx'
APP = ROOT / 'app.jsx'
FLOOR = ROOT / 'app' / 'floor.jsx'
FS = ROOT / 'fs_routes.py'
CSS = ROOT / 'styles.css'
FAILS = []

BASE = '/home/boss/work/deck'


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


def brace_lift(src, header):
    """`header` plus its balanced `{ … }` body, verbatim from the file.

    Anchored on the DECLARATION, never on the expression under test — a lift
    anchored on the fix returns '' when the fix is removed, and a check that
    cannot find its subject is skipped rather than failed."""
    i = src.index(header)
    j = src.index('{', i + len(header) - 1)
    d, k = 0, j
    while k < len(src):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                break
        k += 1
    return src[i:k + 1]


def line_lift(src, header):
    """`header` through the end of its line.

    For one-line arrows whose first `{` belongs to an object literal partway
    in — brace_lift would stop at that literal's close and hand back half a
    statement that happens to parse."""
    i = src.index(header)
    return src[i:src.index('\n', i)]


def main():
    print("a ledger row lands where the work actually went")
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    proj = PROJ.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')
    floor = FLOOR.read_text(encoding='utf-8')
    fs = FS.read_text(encoding='utf-8')
    css = CSS.read_text(encoding='utf-8')

    # ── 1. what the row says, and what it pulses ─────────────────────────
    # The real handler, run for real: stubs record rather than assert, so a
    # rewrite that keeps the behaviour keeps passing.
    handler = brace_lift(proj, 'const onAgentTool = (e) => {')
    add = line_lift(proj, 'const addLedger = (verb, name, arg, where) =>')

    SCOPE = (
        "const isUnder = (p, base) => p === base || p.startsWith(base + '/');\n"
        "const joinPath = (d, n) => d.replace(/\\/+$/, '') + '/' + n;\n"
        "const shortPath = (p) => String(p || '');\n"
        "const projectRef = { current: { id:'p1', path: %s } };\n"
        % json.dumps(BASE)
        + "const openFileRef = { current: null };\n"
          "const followRef = { current: false };\n"
          "const rec = { rows: [], pulsed: [], refreshed: 0, opened: [], status: null };\n"
          "let LEDGER = [];\n"
          "const setLedger = (fn) => { LEDGER = fn(LEDGER); rec.rows = LEDGER; };\n"
          "const setAgentStatus = (s) => { rec.status = s; };\n"
          "const bumpIdle = () => {};\n"
          "const markPulse = (p) => rec.pulsed.push(p);\n"
          "const setTreeNonce = () => { rec.refreshed++; };\n"
          "const setConflict = () => {};\n"
          "const reloadOpen = () => {};\n"
          "const openPath = (p, o) => rec.opened.push([p, o]);\n")

    resolve = brace_lift(proj, 'const resolveInProject = (p, cwd) => {')

    def fire(name, arg):
        js = (SCOPE + resolve + '\n' + add + '\n' + handler + '\n'
              + "onAgentTool({ detail: { agentId:'a1', name:%s, phase:'done', "
                "arg:%s, cwd:%s } });\n"
                % (json.dumps(name), json.dumps(arg), json.dumps(BASE))
              + 'console.log(JSON.stringify(rec));')
        return run_js(js)

    wrote = fire('FILE_WRITE', 'index.html')
    noted = fire('VAULT_NEW', 'Research/remote-work.md')
    exported = fire('EXPORT_PPTX', 'Slides/pitch.pptx')
    ran = fire('BASH', 'npm test')

    check('a real write into this folder is filed as "wrote"',
          len(wrote['rows']) == 1 and wrote['rows'][0]['verb'] == 'wrote',
          wrote['rows'])
    check('a vault note is filed as "noted", not "wrote"',
          len(noted['rows']) == 1 and noted['rows'][0]['verb'] == 'noted',
          f"{noted['rows']} — the cabinet is not this folder, and the boss's "
          'record of what changed here must not say it is')
    check('an export is filed as "exported", not "wrote"',
          len(exported['rows']) == 1
          and exported['rows'][0]['verb'] == 'exported',
          f"{exported['rows']} — every EXPORT_* doc string: the server "
          '"saves it to the vault"')
    check('a shell command is still filed as "ran"',
          len(ran['rows']) == 1 and ran['rows'][0]['verb'] == 'ran',
          ran['rows'])

    check('a write row points at this folder',
          wrote['rows'][0].get('where') == 'folder', wrote['rows'])
    check('a note row points at the cabinet',
          noted['rows'][0].get('where') == 'cabinet',
          f"{noted['rows']} — without `where` the click has nothing to steer "
          'on and falls back to asking the project for a vault path')
    check('an export row points at the cabinet',
          exported['rows'][0].get('where') == 'cabinet', exported['rows'])
    check('a row with no destination given defaults to this folder',
          ran['rows'][0].get('where') == 'folder',
          f"{ran['rows']} — 'ran' rows pass no `where`; undefined would fail "
          "the cabinet test and the folder test both")

    check('only a real write pulses the file tree',
          wrote['pulsed'] and not noted['pulsed'] and not exported['pulsed'],
          {'wrote': wrote['pulsed'], 'noted': noted['pulsed'],
           'exported': exported['pulsed']})
    check('...and only a real write refreshes it',
          wrote['refreshed'] == 1 and noted['refreshed'] == 0
          and exported['refreshed'] == 0,
          'highlighting and re-reading a tree for a file that will never be '
          'in it is a claim about this folder that is not true')

    # ── 2. where the click goes ──────────────────────────────────────────
    click = brace_lift(proj, 'const onLedgerClick = (l) => {')
    CLICK_SCOPE = (
        "const rec = { term: false, opened: [], cabinet: [], toasts: [] };\n"
        "const setTermOpen = (v) => { rec.term = v; };\n"
        "const setTermMounted = () => {};\n"
        "const LSset = () => {};\n"
        "const openPath = (p) => rec.opened.push(p);\n"
        "const toast = (k, m) => rec.toasts.push([k, m]);\n")

    def clicked(row, cabinet=True):
        js = (CLICK_SCOPE
              + ("globalThis.window = { cafresohqOpenNote: (p) => rec.cabinet.push(p) };\n"
                 if cabinet else "globalThis.window = {};\n")
              + click + '\n'
              + 'onLedgerClick(%s);\n' % json.dumps(row)
              + 'console.log(JSON.stringify(rec));')
        return run_js(js)

    r_note = clicked({'kind': 'noted', 'where': 'cabinet',
                      'path': 'Research/remote-work.md'})
    r_exp = clicked({'kind': 'exported', 'where': 'cabinet',
                     'path': 'Slides/pitch.pptx'})
    r_write = clicked({'kind': 'wrote', 'where': 'folder',
                       'path': BASE + '/index.html'})
    r_ran = clicked({'kind': 'ran', 'where': 'folder', 'path': 'npm test'})
    r_nocab = clicked({'kind': 'noted', 'where': 'cabinet',
                       'path': 'Research/remote-work.md'}, cabinet=False)

    check('clicking a note opens the cabinet, not the project tree',
          r_note['cabinet'] == ['Research/remote-work.md']
          and not r_note['opened'],
          f'{r_note} — this is the measured 404: the project was asked for a '
          'path that is not in it')
    check('clicking an export opens the cabinet too',
          r_exp['cabinet'] == ['Slides/pitch.pptx'] and not r_exp['opened'],
          r_exp)
    check('clicking a write still opens the file in this tree',
          r_write['opened'] == [BASE + '/index.html']
          and not r_write['cabinet'], r_write)
    check('clicking a command still opens the terminal it ran in',
          r_ran['term'] is True and not r_ran['opened'], r_ran)
    check('a cabinet click with no cabinet to open says so',
          len(r_nocab['toasts']) == 1 and r_nocab['toasts'][0][0] == 'error',
          f'{r_nocab} — silence here is the original bug wearing a new '
          'coat: the row still goes nowhere, and still without a word')

    # The cabinet two-step has exactly one owner. A second implementation
    # would also have to re-implement the mount latch inside openVaultNote.
    check('app.jsx publishes the cabinet opener for other surfaces',
          re.search(r'window\.cafresohqOpenNote\s*=\s*openVaultNote', app),
          'the Workspace reaches the cabinet through app.jsx\'s own '
          'openVaultNote — copying `goTo` plus a bare event into a second '
          'file copies the latency latch with it, and that copy rots')
    check('...and takes it down with the component',
          re.search(r'delete window\.cafresohqOpenNote', app),
          'a global left behind after unmount points at a dead closure')

    # ── 3. the failure is visible ────────────────────────────────────────
    pane = proj[proj.index('const editorPane = () => ('):]
    pane = pane[:pane.index('\n  );')]
    slot = pane.find('className="ws-err"')
    gate = pane.find('{openFile ? (')
    check('the editor pane has an error slot at all', slot != -1,
          'every way this pane can fail to open a file needs somewhere to '
          'say so')
    check('the error slot is OUTSIDE the open-file branch',
          slot != -1 and gate != -1 and slot < gate,
          f'ws-err at {slot}, `openFile ?` at {gate} — mounted inside, the '
          'slot exists exactly when there is no failure to report, which is '
          'how a 404 on a ledger click showed the "Open a file from the '
          'tree" placeholder and nothing else')
    check('...and there is only one of it',
          pane.count('className="ws-err"') == 1,
          'two slots means one of them is the stale one')
    check('the error is put through the office cause table, not printed raw',
          re.search(r'\{err && <div className="ws-err">\{officeCause\(err\)\}',
                    pane),
          'the visible string here was "not a file" — the server\'s own '
          'wording, straight through to the boss')

    # ── 4. the server stops answering two questions with one string ──────
    check('the server no longer says "not a file"',
          "'not a file'" not in fs,
          'one string for "missing" and "is a directory" cannot be mapped to '
          'two sentences downstream, and the office picked the wrong one')
    check('a missing path is a 404 that says it is missing',
          fs.count("self._send_json(404, {'error': 'no such file'})") == 1
          and fs.count("self._send_json(404, {'ok': False, 'error': "
                       "'no such file'})") == 1,
          'both the file reader and the stat route')
    check('a directory is a 400 that says it is a directory',
          fs.count("'error': 'that is a folder, not a file'") == 2,
          'the folder IS found — 404 would be the opposite of true')

    # ── 5. the office says which, in the office's own voice ──────────────
    causes = brace_lift(floor, 'const OFFICE_CAUSES = [').rstrip()
    # brace_lift stops at the last object brace inside the array; take the
    # array literal by its own brackets instead.
    i = floor.index('const OFFICE_CAUSES = [')
    j = floor.index('\n];', i)
    causes = floor[i:j + 3]
    fn = brace_lift(floor, 'function officeCause(raw) {')
    sentence = run_js(
        causes + '\nconst cleanCause = (t) => "RAW:" + t;\n' + fn
        + '\nconsole.log(JSON.stringify({'
          'folder: officeCause("that is a folder, not a file"),'
          'missing: officeCause("no such file"),'
          'eisdir: officeCause("EISDIR: illegal operation on a directory")'
          '}));')
    check('a folder is reported as a folder, with the way forward in it',
          sentence['folder'] == "that's a folder — open one of the files "
                                'inside it',
          f"{sentence['folder']!r} — the measured wrong answer was \"the "
          'office couldn\'t find that\", about a folder that was found')
    check('...including the raw node spelling of it',
          sentence['eisdir'].startswith("that's a folder"),
          sentence['eisdir'])
    check('a missing file still reports as missing',
          sentence['missing'] == "the office couldn't find that — it may "
                                 'have been moved or renamed',
          f"{sentence['missing']!r} — the folder rule must not swallow this "
          'one on its way past')
    # Ordering is the whole mechanism: /not found|no such file/ matches the
    # folder string too, so a folder rule placed after it never runs.
    check('the folder rule is checked before the missing-file rule',
          causes.index('is a folder, not a file')
          < causes.index('no such file|enoent'),
          'first match wins; behind the generic rule this fix is dead code')

    # ── 6. the badge has to show the distinction on sight ────────────────
    # `wrote` has no rule of its own — it IS the base badge, so "does this
    # look like a write?" is a question about the base, not about a sibling.
    noted_css = re.search(r'\.ws-led\.k-noted \.v \{([^}]*)\}', css)
    base_css = re.search(r'\.ws-led \.v \{([^}]*)\}', css)
    base_bg = re.search(r'background: ([^;]+);', base_css.group(1)) if base_css else None
    noted_bg = re.search(r'background: ([^;]+);', noted_css.group(1)) if noted_css else None
    check('a "noted" badge has a colour of its own', noted_bg is not None,
          'with no rule, `noted` falls through to the base badge — the same '
          'sun colour a real write into this folder wears, and the one '
          'distinction the row exists to draw is invisible')
    check('...and it is not the write colour',
          noted_bg and base_bg
          and noted_bg.group(1).strip() != base_bg.group(1).strip(),
          f'noted {noted_bg and noted_bg.group(1)!r} vs base '
          f'{base_bg and base_bg.group(1)!r} — same colour, same claim, as '
          'far as the eye is concerned')

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
