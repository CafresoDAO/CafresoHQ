#!/usr/bin/env python3
"""The empty project invited the boss to take a thing the office couldn't give.

Driven live on office 9280, Workspace, one project, one hired coworker — the
free local hire, `elevated: false`, which is what a first-run machine has.
The Coworkers pane read:

    Nobody is on this project yet — add a coworker above to give them
    this folder.

One click on the only chip in the row, and the same slot read:

    Local Brain is on this project, but doesn't have file or shell access
    yet — so nothing they do will land in this folder. Settings → Roster
    turns it on, one coworker at a time.

The office knew before the click. `agents` is in scope, `elevated` is on every
one of them, and the branch directly below was already reading that flag —
#122 fixed the "share this folder & shell" claim and left the invitation above
it making the original promise.

Two separate wrong actors in one sentence. Assignment does not grant the
folder: FILE_*/DIR_*/BASH are gated on `agent.elevated` alone (hq-runtime,
"File/shell tools for elevated agents"), granted by the 🛡 switch on the
Roster card. And assignment does not decide what lands in THIS ledger either:
the `cafresohq:agentTool` handler files on where the work happened — `cwd`
under this project's path, or a path named inside it — and never asks who is
assigned. What assignment actually does is open the project's room: TALK ↗ is
disabled until `agentIds` is non-empty and ui/chat.jsx lists the thread on the
same condition.

So the invariant this suite pins is not a wording. It is that the sentence
shown BEFORE the click may not promise what the sentence shown AFTER the click
takes away — checked by rendering both from the shipped source, for every
roster shape, one click apart.

Run: python3 scripts/test_the_empty_project_offers_what_it_can_hand_over.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJ = ROOT / 'views' / 'projects.jsx'
CHAT = ROOT / 'ui' / 'chat.jsx'
FAILS = []

BASE = '/home/boss/work/site'

# The roster shapes a real office actually has. `elevated` is the only field
# that decides whether the folder can ever be handed over.
LOCAL = {'id': 'a_local', 'name': 'Local Brain', 'elevated': False}
KIP = {'id': 'a_kip', 'name': 'Kip', 'elevated': False}
NOOR = {'id': 'a_noor', 'name': 'Noor', 'elevated': False}
CLAUDE = {'id': 'a_claude', 'name': 'Claude', 'elevated': True}
SLOAN = {'id': 'a_sloan', 'name': 'Sloan', 'elevated': True}

ROSTERS = {
    'nobody hired': [],
    'one free local hire': [LOCAL],
    'two, neither elevated': [LOCAL, KIP],
    'three, none elevated': [LOCAL, KIP, NOOR],
    'one elevated': [CLAUDE],
    'one of each': [LOCAL, CLAUDE],
    'two elevated among three': [LOCAL, CLAUDE, SLOAN],
}

# Anything that reads as "doing this hands you the folder". The ticket's own
# literal is first; the rest are the same claim reworded, so a fix that only
# edits the string it was caught on does not pass.
PROMISES = [
    'give them this folder',
    'to give them the folder',
    'gives them this folder',
    'and the folder is theirs',
]
# What the NEXT screen says when the grant was never there.
RETRACTION = 'nothing they do will land in this folder'


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
                return src[i:k + 1]
        k += 1
    raise SystemExit('unbalanced braces lifting ' + header)


def main():
    proj = PROJ.read_text(encoding='utf-8')

    # The shipped decision, lifted whole: crew/handed/ready/nameList, then the
    # sentence itself. Both anchors are declarations that survive the fix
    # being reverted, which is what makes the fire-test meaningful.
    csrc = proj[proj.index('const crew = ((project && project.agentIds)'):
                proj.index('const ledgerEmpty = () => {')]
    esrc = brace_lift(proj, 'const ledgerEmpty = () => {')

    def sentence(agent_ids, roster):
        return run_js(
            'const project = ' + json.dumps({'id': 'p1', 'path': BASE,
                                             'agentIds': agent_ids}) + ';\n'
            + 'const agents = ' + json.dumps(roster) + ';\n'
            + csrc + esrc + '\nconsole.log(JSON.stringify(ledgerEmpty()));')

    print('the invitation and the retraction, one click apart')
    # ── 1. the ticket: no promise may be undone by the very next click ──────
    # Not "the before-text must warn about everyone" — a mixed roster can
    # honestly name the one coworker who does have access and leave the
    # others out. The two things it may not do are name somebody as capable
    # who is about to be refused, and stay quiet when NOBODY can.
    for label, roster in ROSTERS.items():
        before = sentence([], roster)
        for a in [x for x in roster if not x['elevated']]:
            after = sentence([a['id']], roster)
            if RETRACTION not in after:
                continue
            check(f'[{label}] "{a["name"]}" is not named as one whose work '
                  'will land here',
                  a['name'] not in before or 'file or shell access' in before,
                  f'before={before!r} after={after!r} — one click turns this '
                  'invitation into a denial for a coworker it had just held '
                  'up; `elevated` reads the same before the click as after it')
        if roster and not any(x['elevated'] for x in roster):
            check(f'[{label}] nobody on this roster can, and the empty state '
                  'says so before the click',
                  'file or shell access' in before
                  and 'Settings' in before and 'Roster' in before,
                  f'{before!r} — every chip in the row above will produce the '
                  'denial, and the office can see that while it renders them')

    # ── 2. the promise itself is gone, in every shape ───────────────────────
    for label, roster in ROSTERS.items():
        before = sentence([], roster)
        bad = [p for p in PROMISES if p in before]
        check(f'[{label}] the empty state does not say adding grants the folder',
              not bad,
              f'{bad} in {before!r} — assignment grants nothing; `elevated` '
              'does, from the 🛡 switch on the Roster card')
        check(f'[{label}] …and does not claim anyone shares it yet',
              'share' not in before,
              f'{before!r} — nobody is on the project; there is no one to '
              'share it with')

    # ── 3. each shape says the true thing it can say ────────────────────────
    none_hired = sentence([], ROSTERS['nobody hired'])
    check('with nobody hired, the boss is sent to hire, not to a row with no '
          'chips in it',
          'Team' in none_hired and 'above' not in none_hired,
          f'{none_hired!r} — the chip row directly above this reads "No '
          'coworkers hired yet"; "add a coworker above" points at nothing')

    one_local = sentence([], ROSTERS['one free local hire'])
    check('one non-elevated hire is named, and the missing access is stated '
          'up front',
          'Local Brain' in one_local and 'file or shell access' in one_local,
          f'{one_local!r} — this is the first-run case the ticket was found on')
    check('…and the invitation offers the room, which assignment does open',
          'room' in one_local,
          f"{one_local!r} — TALK ↗ is disabled until agentIds is non-empty, "
          'so there is a real reason to add somebody')

    two_flat = sentence([], ROSTERS['two, neither elevated'])
    check('with several non-elevated hires, none of them is named as the '
          'exception',
          'none of your coworkers' in two_flat
          and 'Local Brain' not in two_flat and 'Kip' not in two_flat,
          f'{two_flat!r} — naming two of two adds nothing but length; the '
          'fact is that the roster has no one who can')

    one_up = sentence([], ROSTERS['one elevated'])
    check('an elevated hire is named as the one whose work will show up',
          'Claude' in one_up and 'file & shell access' in one_up
          and 'has file & shell' in one_up,
          f'{one_up!r} — singular')
    check('…and the missing-access warning is NOT printed over them',
          'file or shell access' not in one_up
          and 'Settings' not in one_up,
          f'{one_up!r} — sending this boss to Roster is sending them to fix '
          'something already switched on')

    mixed = sentence([], ROSTERS['one of each'])
    check('with a mixed roster, only the one who can is named',
          'Claude' in mixed and 'Local Brain' not in mixed,
          f'{mixed!r} — naming the non-elevated hire here puts them behind a '
          'promise the office cannot keep for them')

    two_up = sentence([], ROSTERS['two elevated among three'])
    check('two who can read as two, and the third is not swept in',
          'Claude and Sloan' in two_up and 'have file & shell access' in two_up
          and 'Local Brain' not in two_up, two_up)

    # ── 4. the claims the sentence makes about other screens ────────────────
    print('\nthe doors this sentence names')
    chat = CHAT.read_text(encoding='utf-8')
    check('the project room really is gated on assignment',
          bool(re.search(r"\.filter\(p => Array\.isArray\(p\.agentIds\) "
                         r"&& p\.agentIds\.length > 0\)", chat)),
          'ui/chat.jsx — "adding a coworker opens this project\'s room" is '
          'only true while the thread list is filtered on agentIds')
    check('…and so is this pane\'s own TALK button',
          "disabled={(project.agentIds || []).length === 0}" in proj, 'projects.jsx')
    check('the ledger files on where the work happened, not on who is assigned',
          'const here = !!base && !!d.cwd && isUnder(d.cwd, base);' in proj
          and 'agentIds' not in brace_lift(proj, 'const onAgentTool = (e) => {'),
          'views/projects.jsx — if the handler ever starts filtering on the '
          'crew, "their work shows up here" changes meaning and this sentence '
          'has to be rewritten with it')

    # ── 5. the literal that started it, banned repo-wide ────────────────────
    # Block comments come out first. The ban is on what the PRODUCT says, and
    # the comment above the fix quotes the old sentence on purpose — a check
    # that cannot tell those apart makes the next person delete the record of
    # why the sentence changed in order to get the suite green.
    stale = [str(p.relative_to(ROOT)) for p in ROOT.glob('**/*.jsx')
             if 'node_modules' not in str(p)
             and 'give them this folder' in re.sub(
                 r'/\*.*?\*/', '', p.read_text(encoding='utf-8'), flags=re.S)]
    check('no surface anywhere still offers the folder for an assignment',
          not stale, stale)

    print()
    if FAILS:
        print(f'empty project: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('empty project: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
