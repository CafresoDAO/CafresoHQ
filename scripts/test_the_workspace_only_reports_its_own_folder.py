#!/usr/bin/env python3
"""The Workspace reported other people's work as its own.

Watched live on a fresh office at onboarding step 5. One project, selected,
with NOBODY assigned to it. The pane said so:

    Nobody is on this project yet — add a coworker above …

Then a single FILE_WRITE of `index.html`, from a coworker who was not on this
project and was not in this folder, replaced that sentence with:

    wrote  does-not-exist-yet/index.html

titled with this project's absolute path. Nothing was written here. Clicking
the row opens a file that never existed. A WEB_SEARCH from the same coworker
flipped the pip to "coworker working…" while the pane's own empty state still
read "Nobody is on this project yet" — two claims about the same project,
contradicting each other in the same frame.

Every coworker in the office broadcasts on one `cafresohq:agentTool` bus. The
handler read `name`, `phase`, `arg` and `failed`, and never asked WHERE the
work happened — then `resolveInProject` finished the job by joining any
relative path onto THIS project's root. That does not locate a file; it
invents one.

The fix is upstream of the guess: `cwd` — the directory the coworker was
actually standing in — now rides on the tool event, so the question is
answerable instead of assumed. Work belongs to this project when it happened
in this folder: either that is where they were working, or they named a path
inside it outright.

**Second claim, same pane.** The empty ledger read "Your coworkers share this
folder & shell" for ANY crew. File and shell tools are handed out on
`agent.elevated` alone (hq-runtime, "File/shell tools for elevated agents") —
and Llama, the free local hire the front desk offers on a clean machine,
comes with `elevated: false`. So a first-run boss with exactly one coworker
was told they shared the folder and the shell, when they shared neither and
never would, and the empty ledger underneath looked like patience rather than
a setting nobody had turned on.

Run: python3 scripts/test_the_workspace_only_reports_its_own_folder.py
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
RUNTIME = ROOT / 'hq-runtime.jsx'
FAILS = []

BASE = '/home/boss/work/site'
ELSEWHERE = '/home/boss/work/other'


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

    Anchored on the DECLARATION, never on the expression under test: a lift
    anchored on the fix returns '' when the fix is removed, and a check that
    cannot find its subject is skipped rather than failed. That mistake has
    been made twice in this suite already."""
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


def main():
    print("the workspace may only report work done in its own folder")
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    proj = PROJ.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')
    runtime = RUNTIME.read_text(encoding='utf-8')

    # ── 1. the event carries WHERE, all the way down ─────────────────────
    # Behavioural, not a grep: build the real detail object the office
    # broadcasts and look for the directory in it.
    emit = brace_lift(app, "floorEmit('tool', {")
    detail = run_js(
        "const ev = { phase:'done', name:'FILE_WRITE', arg:'index.html', "
        "failed:false, cwd:%s };\n" % json.dumps(BASE)
        + "const agent = { id:'a_llama', name:'Llama', color:'#888' };\n"
        + "let out = null; const floorEmit = (k, d) => { out = d; };\n"
        # brace_lift stops at the object's closing brace; the call needs its
        # own paren back.
        + emit + ');\n'
        + 'console.log(JSON.stringify(out));')
    check('the office broadcast says which folder the work happened in',
          detail.get('cwd') == BASE,
          f'{detail!r} — every listener downstream is ABOUT one folder; '
          'without this they can only guess, and the guess was "mine"')
    check('...and still says who and whether it worked',
          detail.get('agentId') == 'a_llama' and detail.get('failed') is False,
          detail)

    # The runtime is what puts it there. Anchored on the call that has always
    # been here; the claim is that `cwd` is now among what it sends.
    hop = runtime[runtime.index('async function agentStream'):]
    hop = hop[:hop.index('function resolveModel')]
    # Brace-matched, not regex-sliced: the done call's `echo` is a template
    # literal carrying `${toolEchoHead(…)}`, so a paren- or line-bounded
    # pattern stops in the middle of it and reads as "no such call".
    n_start = hop.count("onTool({ phase: 'start'")
    n_done = hop.count("onTool({ phase: 'done'")
    start_call = brace_lift(hop, "onTool({ phase: 'start'") if n_start == 1 else ''
    done_call = brace_lift(hop, "onTool({ phase: 'done'") if n_done == 1 else ''
    check('the runtime puts the working directory on the start event',
          n_start == 1 and re.search(r'\bcwd\b', start_call) is not None,
          f'{n_start} start call(s): {start_call!r}')
    check('...and on the done event',
          n_done == 1 and re.search(r'\bcwd\b', done_call) is not None,
          f'{n_done} done call(s): {done_call!r}')

    # ── 2. resolveInProject, run for real ────────────────────────────────
    resolve = brace_lift(proj, 'const resolveInProject = (p, cwd) => {')
    SCOPE = (
        "const isUnder = (p, base) => p === base || p.startsWith(base + '/') "
        "|| p.startsWith(base + '\\\\');\n"
        "const joinPath = (dir, name) => { const d = String(dir || ''); "
        "const sep = (d.includes('\\\\') && !d.includes('/')) ? '\\\\' : '/'; "
        "return d.replace(/[\\/\\\\]+$/, '') + sep + name; };\n"
        "const projectRef = { current: { id:'p1', path: %s, agentIds: ['a_llama'] } };\n"
        % json.dumps(BASE))

    def resolved(arg, cwd):
        return run_js(SCOPE + resolve + '\nconsole.log(JSON.stringify('
                      + f'resolveInProject({json.dumps(arg)}, '
                      + f'{json.dumps(cwd) if cwd is not None else "undefined"})));')

    check('a relative path resolves against the folder it was typed in',
          resolved('index.html', BASE) == BASE + '/index.html',
          'the ordinary case: a coworker in this project writes index.html')
    check('...and only that folder',
          resolved('index.html', ELSEWHERE) == '',
          'joining another project\'s relative write onto this root is how a '
          'row claiming this folder changed got filed for a file that was '
          'never here')
    check('...with no folder at all, it resolves to nothing',
          resolved('index.html', None) == '',
          'no working directory means nothing can be located — "assume mine" '
          'is a guess wearing a path')
    check('an absolute path inside the project is taken as given',
          resolved(BASE + '/src/app.js', None) == BASE + '/src/app.js',
          'naming a path in this folder outright needs no cwd')
    check('an absolute path outside it is not',
          resolved(ELSEWHERE + '/src/app.js', BASE) == '',
          'this pane speaks for one folder')

    # ── 3. the real handler, fed real events ─────────────────────────────
    handler = brace_lift(proj, 'const onAgentTool = (e) => {')
    HSCOPE = SCOPE + resolve + '\n' + """
const rec = { pip: [], ledger: [], pulse: [], opened: [], tree: 0 };
const setAgentStatus = (s) => rec.pip.push(s);
const bumpIdle = () => {};
const markPulse = (p) => { if (p) rec.pulse.push(p); };
const setTreeNonce = () => { rec.tree++; };
const addLedger = (verb, name, arg) => rec.ledger.push({ verb, arg });
const openFileRef = { current: null };
const followRef = { current: true };
const reloadOpen = (p) => rec.opened.push(p);
const setConflict = () => {};
const openPath = (p) => rec.opened.push(p);
"""

    def fire(events):
        return run_js(HSCOPE + handler
                      + '\n' + json.dumps(events)
                      + '.forEach(d => onAgentTool({ detail: d }));\n'
                      + 'console.log(JSON.stringify(rec));')

    mine = fire([{'phase': 'done', 'name': 'FILE_WRITE', 'arg': 'index.html',
                  'failed': False, 'agentId': 'a_llama', 'cwd': BASE}])
    check('work in this folder is reported',
          [l['arg'] for l in mine['ledger']] == [BASE + '/index.html'],
          mine['ledger'])
    check('...the pip says somebody is working',
          'working' in mine['pip'], mine['pip'])
    check('...the tree refreshes and the file pulses',
          mine['tree'] >= 1 and BASE + '/index.html' in mine['pulse'], mine)
    check('...and Follow along opens what they wrote',
          mine['opened'] == [BASE + '/index.html'], mine['opened'])

    theirs = fire([{'phase': 'done', 'name': 'FILE_WRITE', 'arg': 'index.html',
                    'failed': False, 'agentId': 'a_someone', 'cwd': ELSEWHERE}])
    check('a write in someone else\'s folder is not filed here',
          theirs['ledger'] == [],
          f"{theirs['ledger']} — the row is titled with THIS project's "
          'absolute path, so it claims a file in this folder changed')
    check('...it does not claim a coworker is working on this project',
          theirs['pip'] == [], theirs['pip'])
    check('...and Follow along does not chase it',
          theirs['opened'] == [] and theirs['pulse'] == [], theirs)

    nowhere = fire([{'phase': 'start', 'name': 'WEB_SEARCH', 'arg': 'anything',
                     'agentId': 'a_someone'}])
    check('a search with no folder in play leaves this project alone',
          nowhere['pip'] == [] and nowhere['ledger'] == [],
          f'{nowhere} — this is what put "coworker working…" on a project '
          'that also said "Nobody is on this project yet"')

    ran = fire([{'phase': 'done', 'name': 'BASH', 'arg': 'npm test',
                 'failed': False, 'agentId': 'a_llama', 'cwd': BASE},
                {'phase': 'done', 'name': 'BASH', 'arg': 'npm test',
                 'failed': False, 'agentId': 'a_someone', 'cwd': ELSEWHERE}])
    check('a command run in this folder is filed, one run elsewhere is not',
          [l['verb'] for l in ran['ledger']] == ['ran'],
          f"{ran['ledger']} — BASH names a command, not a path; the only "
          'thing that places it is the directory it ran in')

    failed = fire([{'phase': 'done', 'name': 'FILE_WRITE', 'arg': 'index.html',
                    'failed': True, 'agentId': 'a_llama', 'cwd': BASE}])
    check('a write that failed is still not filed as a write',
          failed['ledger'] == [],
          'pinned from the pass before this one — a failed write filed as '
          '"wrote index.html" claims the file changed')

    # ── 4. the pane promises only what the crew can actually do ──────────
    csrc = proj[proj.index('const crew = ((project && project.agentIds)'):
                proj.index('const ledgerEmpty = () => {')]
    esrc = brace_lift(proj, 'const ledgerEmpty = () => {')

    def copy_for(agent_ids, roster):
        return run_js(
            'const project = ' + json.dumps({'id': 'p1', 'path': BASE,
                                             'agentIds': agent_ids}) + ';\n'
            + 'const agents = ' + json.dumps(roster) + ';\n'
            + csrc + esrc + '\nconsole.log(JSON.stringify(ledgerEmpty()));')

    LLAMA = {'id': 'a_llama', 'name': 'Llama', 'elevated': False}
    KIP = {'id': 'a_kip', 'name': 'Kip', 'elevated': False}
    CLAUDE = {'id': 'a_cli_claude', 'name': 'Claude', 'elevated': True}

    nobody = copy_for([], [LLAMA])
    # Tested on `share`, not on the word `shell`. The empty state now says
    # OUT LOUD that a non-elevated roster has no file or shell access (#138) —
    # the opposite of promising one — and a check that reads the noun rather
    # than the claim calls that a regression. What may not appear here is the
    # promise: "shares this folder & shell", with nobody on the project.
    check('with nobody on it, the pane does not promise a shared shell',
          'share' not in nobody and 'Nobody is on this project' in nobody,
          nobody)

    one = copy_for(['a_llama'], [LLAMA])
    check('a coworker without file access is named, not spoken for',
          'Llama' in one and 'file or shell access' in one
          and 'share' not in one,
          f'{one!r} — this is the first-run case: the free local hire the '
          'front desk offers comes with elevated:false')
    check('...and the boss is told where to change it',
          'Settings' in one and 'Roster' in one, one)
    check('...in the singular',
          "is on this project" in one and "doesn't" in one, one)

    two = copy_for(['a_llama', 'a_kip'], [LLAMA, KIP])
    check('two of them read as two',
          'Llama and Kip' in two and 'are on this project' in two
          and "don't" in two, two)

    mixed = copy_for(['a_llama', 'a_cli_claude'], [LLAMA, CLAUDE])
    check('with one who does have access, only they are promised',
          'Claude shares this folder & shell' in mixed
          and 'Llama' not in mixed,
          f'{mixed!r} — naming Llama here would put them behind a promise '
          'the office cannot keep for them')
    check('...and the ledger still says what will appear',
          'writes, runs, and exports appear here' in mixed, mixed)

    print()
    if FAILS:
        print(f'workspace: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('workspace: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
