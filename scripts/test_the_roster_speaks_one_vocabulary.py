#!/usr/bin/env python3
"""A tool id written into the roster has to be an id something reads.

Reproduced 2026-08-16 on a scratch office (127.0.0.1:9270, canned brain).
A non-elevated coworker asked for file and shell access, the boss pressed
APPROVE, and the office announced:

    🛡 Dee now has file and shell access. It applies from their next job.

The approval handler then wrote `'file'` and `'shell'` into her tools.
Neither is a TOOLS_CATALOG id — the catalog calls them `files` and `code` —
so app/cast.jsx, which drops any id with no CAN_DO entry, dropped both, and
her coworker card went on reading

    CAN USE   VAULT

for a coworker who had just been handed the machine. One approval, three
surfaces, and the only one that changed was the sentence.

The two strings were not inert either. They are printed raw where the
office describes a roster to something that is not a card:

    memory/hq-agents.md   "- Tools: vault, file, shell"
    hq-runtime.jsx:3604   the chief of staff's roster line
    hq-runtime.jsx:3840   `claimedRaw` in the hint channel

so the office told its own coworkers about a capability using two words no
screen in the product has ever printed.

The other elevation door — the 🛡 switch on the coworker's card — wrote no
tools at all, leaving the same card wrong by a different route. Both go
through app.jsx's `onUpdateAgent`, so the list is applied there, once.

Same family, one screen away: app.jsx's CLI-sync DEFS carried a full hire
spec (name, role, color, model, tools) of which the loop below it reads
exactly one key, `id` — and its dead `tools` was the last surviving copy of
the `'shell'` id that modals/hire.jsx's FRONT_DESK had already been
corrected off. A table that looks like a spec and is read for one key is a
table the next reader will trust for the other five.

So this suite holds:

  1. every literal tools list in the tree uses catalog ids and nothing else
  2. what the 🛡 switch grants is named in the catalog AND has words on the
     card — an id that grants silently is the defect, not the fix
  3. `onUpdateAgent` adds them on the way up and never strips on the way
     down (`files` is a legitimate ungranted claim — Dax's template)
  4. rosters already carrying the bogus pair are repaired

§5 (a wrong door is worse than a locked one — a card that omits a granted
capability is the boss's map of their own office being wrong) and §6 (the
office does not speak the machine's vocabulary at anyone, including its
own coworkers).
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
CAST = ROOT / 'app' / 'cast.jsx'

FAILS = []


def check(label, ok, detail=''):
    if ok:
        print(f'  ok    {label}')
    else:
        FAILS.append(label)
        print(f'  FAIL  {label}' + (f'  — {detail}' if detail else ''))


def section(src, start, end):
    a = src.find(start)
    if a < 0:
        return ''
    b = src.find(end, a)
    return src[a:b] if b > a else ''


def lift_block(src, opener):
    """Brace-match the arrow body at `opener` so the REAL code runs below,
    rather than being pattern-matched from a distance."""
    i = src.find(opener)
    return brace_from(src, src.find('{', i + len(opener) - 1)) if i >= 0 else ''


def lift_effect(src, marker):
    """The effect body CONTAINING `marker`, from its opening brace.

    Anchored on something inside it and walked backwards, because the
    interesting part of a migration is its early return — and an arm that
    neuters one (`if (true) return;`) leaves every line of the body in
    place for a static check to keep finding.
    """
    i = src.find(marker)
    if i < 0:
        return ''
    return brace_from(src, src.find('{', src.rfind('useEffectA(() => {', 0, i)))


def brace_from(src, j):
    if j < 0:
        return ''
    depth, k = 0, j
    while k < len(src):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[j:k + 1]
        k += 1
    return ''


def catalog_ids():
    blk = section(RUNTIME, 'const TOOLS_CATALOG = [', '];')
    return re.findall(r"id:\s*'([^']+)'", blk)


def elevation_ids():
    m = re.search(r"const ELEVATION_TOOL_IDS = \[([^\]]*)\]", RUNTIME)
    return re.findall(r"'([^']+)'", m.group(1)) if m else []


def run_node(src, cases):
    body = '\n'.join(ln for ln in src.split('\n')
                     if not ln.startswith('import ') and not ln.startswith('export '))
    p = subprocess.run(['node', '--input-type=module', '-e', body + '\n' + cases],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stdout)
        print(p.stderr[-1500:], file=sys.stderr)
        return None
    return json.loads(p.stdout.strip().split('\n')[-1])


def main():
    print('the roster speaks one vocabulary')

    IDS = catalog_ids()
    check('TOOLS_CATALOG is readable', len(IDS) >= 5,
          '— every check below is measured against it')
    ELEV = elevation_ids()

    # ── 1. no id in the tree that the catalog has never heard of ─────────
    # Repo-wide, because the point is that this cannot come back somewhere
    # else. `.claude/worktrees` is another session's checkout, not source.
    offenders = []
    for p in sorted(ROOT.rglob('*.jsx')):
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(('.claude/', 'node_modules/', 'dist-ui/')):
            continue
        text = p.read_text(encoding='utf-8')
        for m in re.finditer(r"tools:\s*\[([^\]]*)\]", text):
            inner = m.group(1)
            if not inner.strip():
                continue
            # Literal lists only. `tools: [...(a.tools||[]), x]` is a runtime
            # expression, and a check that guessed at it would be reading
            # punctuation, not ids.
            if re.search(r"[^\s'\",A-Za-z0-9_-]", inner):
                continue
            got = re.findall(r"'([^']*)'", inner)
            if len(got) != len([x for x in inner.split(',') if x.strip()]):
                continue
            for g in got:
                if g not in IDS:
                    offenders.append(f'{rel}:{text[:m.start()].count(chr(10)) + 1} {g!r}')
    check('every literal tools list uses catalog ids', not offenders,
          '— ' + '; '.join(offenders[:4]) + ' — an id nothing reads is '
          'dropped by every card and printed raw by hq-agents.md')

    # ── 2. what the switch grants is nameable, and named ─────────────────
    check('the elevation door has a tool list of its own',
          bool(ELEV),
          '— HQ.ELEVATION_TOOL_IDS is what stops each door inventing its own')
    check('...exported so every door reads the same one',
          re.search(r'TOOLS_CATALOG,\s*ELEVATION_TOOL_IDS', RUNTIME) is not None,
          '— app.jsx reaches it as HQ.ELEVATION_TOOL_IDS')
    check('...and every id in it is in the catalog',
          bool(ELEV) and all(t in IDS for t in ELEV),
          f'— {[t for t in ELEV if t not in IDS]} is what the approval handler '
          "used to mint on its own ('file', 'shell')")

    # The switch opens two doors, so the roster has to name two. A list that
    # says `files` alone would pass every check above and still leave a
    # coworker with the run of the shell and no card that says so — the
    # original bug, halved. What the flag actually opens is read out of
    # `toolsForAgent` rather than assumed, so if the grant ever widens this
    # pin is re-examined instead of quietly under-reporting.
    opens = section(RUNTIME, 'if (agent.elevated) {', '}')
    grants_files = 'file_read' in opens and 'file_write' in opens
    grants_shell = 'bash' in opens
    check('the flag still opens both file and shell tools',
          grants_files and grants_shell,
          f'— toolsForAgent: files={grants_files} shell={grants_shell}; the '
          'expectation below is derived from this branch')
    need = ({'files'} if grants_files else set()) | ({'code'} if grants_shell else set())
    check('...and the roster has a word for each of them',
          need <= set(ELEV),
          f'— missing {sorted(need - set(ELEV))}; "File & shell access" is the '
          'name on the door and the card has to be able to say both halves')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH — behavioural checks not run')
    else:
        # The end of the chain: cast.jsx is import-free by design, so the
        # card's own tables answer here. This is the check that would have
        # caught the shipped bug from the boss's side — the ids the switch
        # writes have to produce WORDS, not silence.
        card = run_node(CAST.read_text(encoding='utf-8'), '''
const ELEV = %s;
const R = {};
R.grantedElevated = grantedTools(['vault', ...ELEV], { elevated: true, vaultOn: true })
  .granted.map(g => g.id);
R.lockedWithout = grantedTools(['vault', ...ELEV], { elevated: false, vaultOn: true })
  .locked.map(g => g.id);
R.phrase = canDoPhrase(['vault', ...ELEV], { elevated: true, vaultOn: true });
R.phraseWithout = canDoPhrase(['vault'], { elevated: true, vaultOn: true });
console.log(JSON.stringify(R));
''' % json.dumps(ELEV))
        if card is None:
            check('the card can be asked about the elevation ids', False,
                  '— node could not run app/cast.jsx')
        else:
            check('an elevated coworker\'s card names every granted id',
                  all(t in card['grantedElevated'] for t in ELEV),
                  f"— card granted {card['grantedElevated']}, switch grants {ELEV}; "
                  "the shipped pair produced CAN USE VAULT and nothing else")
            check('...and a non-elevated one shows them locked, not missing',
                  all(t in card['lockedWithout'] for t in ELEV),
                  f"— {card['lockedWithout']}; §7 wants the route shown rather "
                  'than the row quietly shrinking')
            # Measured against the same card WITHOUT the elevation ids,
            # because "the phrase mentions files" is not the claim — the
            # claim is that granting elevation CHANGES what the card says.
            # The shipped pair left these two strings identical.
            check('...and the sentence under the name grows when they are granted',
                  card['phrase'] != card['phraseWithout']
                  and len(card['phrase']) > len(card['phraseWithout']),
                  f"— {card['phraseWithout']!r} without them, {card['phrase']!r} "
                  'with; the shipped pair produced the same sentence either way')

        # ── 3. the one place the doors meet ──────────────────────────────
        mapper = lift_block(APP, 'const onUpdateAgent = (id, patch) => setAgents(prev => prev.map(a =>')
        check('onUpdateAgent\'s mapper is liftable', bool(mapper),
              '— the two behavioural checks below run it')
        if mapper:
            out = run_node('', '''
const HQ = { ELEVATION_TOOL_IDS: %s };
const step = (a, id, patch) => %s;
const R = {};
R.up = step({ id: 'x', tools: ['web'], elevated: false }, 'x', { elevated: true }).tools;
R.down = step({ id: 'x', tools: ['web', 'files', 'code'], elevated: true }, 'x',
              { elevated: false }).tools;
R.unrelated = step({ id: 'x', tools: ['web'], elevated: true }, 'x', { recent: 'hi' }).tools;
R.other = step({ id: 'y', tools: ['web'], elevated: false }, 'x', { elevated: true }).tools;
R.noDupes = step({ id: 'x', tools: ['web', 'files'], elevated: false }, 'x',
                 { elevated: true }).tools;
console.log(JSON.stringify(R));
''' % (json.dumps(ELEV), mapper))
            if out is None:
                check('the mapper runs', False, '— node could not execute the lifted body')
            else:
                check('elevation turning on adds the ids',
                      all(t in out['up'] for t in ELEV),
                      f"— {out['up']}; the switch used to write none at all")
                check('...and turning it off leaves the claim alone',
                      all(t in out['down'] for t in ELEV),
                      f"— {out['down']}; `files` is a legitimate ungranted claim "
                      "(Dax's template carries it un-elevated) and the card "
                      'already gates it on the flag')
                check('...and an unrelated patch changes nothing',
                      out['unrelated'] == ['web'], f"— {out['unrelated']}")
                check('...and another coworker is untouched',
                      out['other'] == ['web'], f"— {out['other']}")
                check('...and an id already claimed is not doubled',
                      len(out['noDupes']) == len(set(out['noDupes'])),
                      f"— {out['noDupes']}")

    # No caller carries its own copy. The approval handler used to pass
    # `tools: newTools` alongside the flag, which is how the two doors came
    # to disagree in the first place.
    grants = re.findall(r'onUpdateAgent\([^)]*elevated:[^)]*\)', APP, re.S)
    check('no caller hands onUpdateAgent its own tools list',
          not any('tools' in g for g in grants),
          f'— {len(grants)} elevation call(s), one carries tools: the second '
          'copy is the drift')

    # ── 4. rosters that already have the bogus pair ──────────────────────
    # Run, not read. A repair pass is exactly the kind of code a static
    # check flatters: every line stays where it is and one `return` above
    # them decides whether any of it happens.
    mig = lift_effect(APP, "k('migrated_elevation_tool_ids_v1')")
    check('a repair pass exists for rosters already written', bool(mig),
          '— without it the fix reaches only offices that never used the '
          'feature; the pair is persisted in memory/agents.json')
    if mig and shutil.which('node'):
        got = run_node('', '''
const HQ = { ELEVATION_TOOL_IDS: %s };
const k = (s) => 'pfx:' + s;
let flag = null;
const localStorage = { getItem: () => flag, setItem: (_kk, v) => { flag = v; } };
let roster = [
  { id: 'dee', elevated: true,  tools: ['vault', 'file', 'shell'] },
  { id: 'nia', elevated: true,  tools: ['web'] },
  { id: 'dax', elevated: false, tools: ['files'] },
  { id: 'old', elevated: false, tools: ['web', 'file', 'shell'] },
];
const setAgents = (fn) => { roster = fn(roster); };
const migrate = () => %s;
migrate();
const by = (id) => roster.find(a => a.id === id).tools.slice().sort();
const R = { dee: by('dee'), nia: by('nia'), dax: by('dax'), old: by('old'), flag };

// Second office, already repaired once: the pass must not run again.
flag = null; roster = [{ id: 'dee', elevated: true, tools: ['vault'] }];
migrate();
flag = 'stale-but-set';
roster = [{ id: 'zed', elevated: true, tools: ['file'] }];
migrate();
R.skipped = roster[0].tools;
console.log(JSON.stringify(R));
''' % (json.dumps(ELEV), mig))
        if got is None:
            check('the repair pass runs', False, '— node could not execute it')
        else:
            check('...it swaps the minted pair for the catalog ids',
                  got['dee'] == sorted(['vault'] + ELEV),
                  f"— {got['dee']}; this is the roster the approval handler "
                  'actually wrote, on disk in memory/agents.json')
            check('...and gives them to anyone a silent door elevated',
                  got['nia'] == sorted(['web'] + ELEV),
                  f"— {got['nia']}; the 🛡 switch and the elevate-all "
                  'migration both predate the rule and wrote no tools')
            check('...and leaves an ungranted claim exactly as it was',
                  got['dax'] == ['files'],
                  f"— {got['dax']}; Dax claims files with no elevation and "
                  'that is a claim, not damage')
            check('...and strips the pair without granting anything',
                  got['old'] == ['web'],
                  f"— {got['old']}; the ids were wrong, the elevation was "
                  'never given, and inventing it here would be a grant the '
                  'boss never made')
            check('...and marks itself done so it runs once',
                  got['flag'] == '1' and got['skipped'] == ['file'],
                  f"— flag {got['flag']!r}; second pass left {got['skipped']}, "
                  'which should be untouched')

    # ── 5. the table that was read for one key ───────────────────────────
    defs = section(APP, 'const DEFS = {', '};')
    check('the CLI-sync DEFS is findable', bool(defs))
    check('...and carries only what the sync reads',
          'tools:' not in defs and 'model:' not in defs and 'role:' not in defs,
          '— the loop below it writes cliVersion, cliAuthed and recent, and '
          "reads `id`; the dead `tools` was the last copy of 'shell'")

    print()
    if FAILS:
        print(f'FAILED {len(FAILS)} check(s):')
        for f in FAILS:
            print('  · ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
