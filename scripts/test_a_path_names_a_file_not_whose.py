#!/usr/bin/env python3
"""The office reported three different destinations with one sentence.

`work/preferences.md` can mean the coworker's own private notes, the boss's
filing cabinet, or a file in the boss's project on disk. Until this change
all three rendered identically on every surface the office speaks through:

    📝 Saved work/preferences.md

The expensive version of this is already in the ledger: a coworker asked to
build a file "in the Site Check project folder" wrote it into its own notes,
described it in words that sounded like the project, and the floor repeated
the ambiguous path back in the office's own voice — the one voice the boss
is entitled to trust over the coworker's. The prompt half of that (the memory
layout no longer suggests `projects/`) is pinned by
test_memory_layout_isnt_the_boss_projects.py. This is the reporting half.

The same ambiguity exists on the read side and between the two searches:
`[SEARCH: gold]` goes to the web and `[VAULT_SEARCH: gold]` goes through the
boss's own filing cabinet, and both used to say "Looked up gold".

Run: python3 scripts/test_a_path_names_a_file_not_whose.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOOR = ROOT / 'app' / 'floor.jsx'
RT = ROOT / 'hq-runtime.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run_js(cases):
    text = FLOOR.read_text(encoding='utf-8')
    src = '\n'.join(ln for ln in text.split('\n')
                    if not ln.startswith('import ') and not ln.startswith('export '))
    proc = subprocess.run(['node', '--input-type=module', '-e', src + '\n' + cases],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('a path names a file — the office also has to name whose')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    out = run_js(r'''
const P = 'work/preferences.md';
const R = {};
R.mem   = visitLine('MEMORY_WRITE', P, 'past');
R.vault = visitLine('VAULT_NEW',    P, 'past');
R.file  = visitLine('FILE_WRITE',   P, 'past');
R.memRead   = visitLine('MEMORY_READ', P, 'past');
R.memFail   = visitLine('MEMORY_WRITE', P, 'fail');
R.webSearch = visitLine('SEARCH',       'gold', 'past');
R.vaultSearch = visitLine('VAULT_SEARCH', 'gold', 'past');
R.unknown   = visitLine('SOME_NEW_TOOL', P, 'past');
R.act = toolActivity({ id: 'a1', name: 'Nova' },
                     { name: 'MEMORY_WRITE', arg: P, failed: false }).text;
console.log(JSON.stringify(R));
''')

    # ── 1. the same path, three destinations, three sentences ────────────
    trio = [out['mem'], out['vault'], out['file']]
    check('one path written three ways reads three ways',
          len(set(trio)) == 3,
          f'{trio!r} — this is the whole defect: identical office voice for '
          "the coworker's private notes, the boss's cabinet and the boss's "
          'project on disk')
    check('a memory write says it went to their own notes',
          out['mem'] == 'Saved work/preferences.md in their notes', out['mem'])
    check('a cabinet write says the cabinet',
          out['vault'] == 'Saved work/preferences.md in the cabinet', out['vault'])
    check('a project write says the project',
          out['file'] == 'Saved work/preferences.md in the project', out['file'])

    # ── 2. reads get it too ─────────────────────────────────────────────
    # "which budget.md did they read" is the same question as "where did it
    # go", and a read that names no place is as ambiguous as a write.
    check('a read names the place as well',
          out['memRead'] == 'Opened work/preferences.md in their notes',
          out['memRead'])

    # ── 3. a trip that failed does not claim to have got there ──────────
    # "Couldn't save x in their notes" reads as a save attempted at a place
    # and failing there. The honest shape for a trip that never happened is
    # the one with no destination in it.
    check('a failed trip names no destination',
          out['memFail'] == "Couldn't save work/preferences.md"
          and 'notes' not in out['memFail'],
          out['memFail'])

    # ── 4. the two searches stop sounding alike ─────────────────────────
    check('a web search and a cabinet search are told apart',
          out['webSearch'] != out['vaultSearch'],
          f"{out['webSearch']!r} vs {out['vaultSearch']!r} — one leaves the "
          "building and one goes through the boss's own files")
    check('...and the web one invents no location',
          out['webSearch'] == 'Looked up gold', out['webSearch'])

    # ── 5. nothing is invented for a tool we don't know ─────────────────
    # The table's whole value is that the boss can trust it. A guessed
    # destination is worse than none, which is the same reasoning
    # VISIT_DEFAULT already follows for the verb.
    # (The VERB here is 'Saved', not the modest default — "SOME_NEW_TOOL"
    # contains NEW, which VISIT_WORDS matches. That is the existing verb
    # table doing its documented thing and is not this test's business; what
    # is checked is that no PLACE was guessed.)
    check('an unrecognised tool gets no destination at all',
          out['unknown'] == 'Saved work/preferences.md'
          and not re.search(r'\bin (their|the)\b', out['unknown']),
          out['unknown'])

    # ── 6. the activity feed carries it, not just the chat ──────────────
    # The feed is what the boss scrolls a day later, when the chat context
    # that made the path obvious is gone.
    check('the activity row names the place too',
          out['act'] == 'saved work/preferences.md in their notes', out['act'])

    # ── 7. the words are the product's, not new ones ────────────────────
    # Three new nouns for three places the UI already names would be a
    # fourth vocabulary, which is the problem §6 exists to stop.
    src = FLOOR.read_text(encoding='utf-8')
    m = re.search(r'const VISIT_WHERE = \[[\s\S]*?\n\];', src)
    check('the destination table is still one table', bool(m), 'app/floor.jsx')
    table = m.group(0) if m else ''
    for word in ('their notes', 'the cabinet', 'the project'):
        check(f'"{word}" is the word used',
              word in table,
              'app/floor.jsx: these are the nouns the rest of the office '
              'already uses; a synonym here makes the boss learn two names '
              'for one place')

    # ── 8. the claim about exports is checked, not assumed ──────────────
    # EXPORT_*/GENERATE_* are grouped with VAULT_* on the grounds that they
    # write to the vault. If that ever stops being true the grouping is a
    # lie, so read it back off the tool registry rather than trusting the
    # comment next to it.
    rt = RT.read_text(encoding='utf-8')
    for tool in ('EXPORT_PPTX', 'GENERATE_IMAGE'):
        blk = re.search(r"name: '" + tool + r"'[\s\S]{0,900}?\n    \},", rt)
        body = blk.group(0) if blk else ''
        check(f'{tool} really does write to the cabinet',
              'library' in body.lower(),
              f'hq-runtime.jsx: {tool} is filed under "in the cabinet" in '
              'app/floor.jsx — if it stopped saving to the vault, that line '
              'now tells the boss the wrong place')

    print()
    if FAILS:
        print(f'a path names whose: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('a path names whose: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
