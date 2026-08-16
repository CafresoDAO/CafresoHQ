#!/usr/bin/env python3
"""When a coworker reaches for a tool, the hint names the door that is SHUT.

Some claims have two doors: the checkbox on the coworker's card, and a
connection on another screen. `toolsForAgent` needs both, so a ticked box
and a missing tool means the OTHER door is the shut one — and the hint that
sends the boss to Settings → Roster in that case costs them a trip, a
pointless toggle, and their trust in the hint. 'img' was fixed for this.
'vault' was not, although the office already knew the answer: CEO_DOORS
sends the chief of staff to Settings → Connections for the same family.

Measured 2026-08-16 on office 9261, canned brain on 9236. Kip, tools
['web','vault'], Markdown Vault box TICKED, vault backend switched to
OBSIDIAN REST with Obsidian closed. Two halves of one system prompt:

    You are Kip, the Deep Research specialist. … synthesize into a
    research note saved to Research/<topic>.md via [VAULT_NEW].

    Claimed capabilities: web, vault. Of these, the following are wired up
    for real execution: BROWSER_FETCH, ACK, SPAWN_SUBAGENT, HIRE_AGENT,
    HIRE_ASSISTANT, REQUEST_ELEVATION, DM_TO, PEER_JOURNAL. ONLY invoke
    these exact tools …

He obeyed the first half. What the boss read:

    _(Kip reached for Vault Notes, which they don't have — turn it on from
      their card in Settings → Roster, or @-mention a coworker who already
      has it.)_

The box was on. Settings → Connections → MARKDOWN VAULT was the shut door
and went unnamed.

Guards, written per DOOR rather than per sentence, so a third two-door
claim cannot be added with the Roster copy:
  · every second door has a predicate, a place in the emit guard, and a
    standalone sentence of its own
  · that sentence names its own screen and never the Roster
  · the coworker path and the chief-of-staff path name the SAME screen for
    the same family — the asymmetry was the whole defect
  · an unknown box is not a ticked box (the CEO's one-argument call)
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_the_front_desk_sells_what_exists import brace_lift  # noqa: E402

RUNTIME = ROOT / 'hq-runtime.jsx'

FAILS = []

# claim id -> (the screen its second door is on,
#              the predicate that says "the box is ticked, so THAT door is
#              the shut one", and the any() wrapper the emit guard calls)
#
# The generalising half. Adding a two-door claim means adding a row, and a
# row cannot be satisfied by a sentence that sends the boss to the Roster.
# Names spelled out rather than derived from the claim id: a rule like
# "capitalise it" would have quietly matched nothing the day someone named
# the third one after the screen instead of the box.
SECOND_DOORS = {
    'img':   ('Settings → Media',       'claimNeedsMediaDoor', 'claimHitsMediaDoor'),
    'vault': ('Settings → Connections', 'claimNeedsVaultDoor', 'claimHitsVaultDoor'),
}


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('the hint names the door that is shut')
    code = RUNTIME.read_text(encoding='utf-8')
    note = brace_lift(code, 'function reachedForNote(')
    labels = brace_lift(code, 'function claimLabels(')
    ceo_doors = re.search(r'const CEO_DOORS = \{[\s\S]*?\};', code).group(0)
    templates = re.findall(r'`_\(([^`]*)\)_`', note)
    # Scoped to the condition, not the file. `claimHitsVaultDoor(missing,
    # agent)` also appears inside reachedForNote itself, so a file-wide
    # substring test reported the guard intact while the fire arm had
    # deleted it — the boss heard nothing at all about the reach, which is
    # the quietest way this can break.
    gm = re.search(r'if \((claimLabels\(missing, agent\)[\s\S]{0,300}?)\) \{'
                   r'\s*\n\s*emit\(reachedForNote\(missing, agent\)\);', code)
    guard = gm.group(1) if gm else ''

    # ── 1. every second door is wired through all three places ───────────
    for claim, (screen, pred, hits) in sorted(SECOND_DOORS.items()):
        check(f"'{claim}' has a predicate for its second door",
              f'function {pred}(' in code,
              'without it claimLabels cannot tell a shut box from a shut '
              'connection, and names the box either way')
        check(f"...which reads the '{claim}' box off the agent",
              re.search(r"indexOf\('%s'\)" % claim,
                        brace_lift(code, f'function {pred}(')) is not None,
              'an unticked box IS the shut door; this predicate is only '
              'about the case where it is already on')
        check(f"...and claimLabels drops '{claim}' names when it is ticked",
              f'{pred}(n, agent)' in labels,
              'a name that survives here gets printed, and the sentence '
              'that prints it routes to the Roster')
        # Silent, not wrong, is the failure mode: claimLabels having dropped
        # the name, an absent door leaves the guard false and the boss hears
        # nothing at all about a reach that happened.
        check(f"...and the emit guard asks about '{claim}'",
              f'{hits}(missing, agent)' in guard,
              'claimLabels drops the name, so without this the sentence is '
              'never reached and the reply stands uncorrected')
        # ...and it has to be the sentence for THIS door alone. Requiring
        # only "names the screen, not the Roster" is satisfied by the
        # combined both-doors-open sentence, so deleting the single-door
        # one left this green — the node arm caught it, the static check
        # did not, and a static check that needs a sibling to be sound is
        # not doing its job.
        others = [d for c, (d, _p, _h) in SECOND_DOORS.items()
                  if c != claim] + ['Settings → Roster']
        standalone = [t for t in templates
                      if screen in t and 'already on' in t
                      and not any(o in t for o in others)]
        check(f"...and has a sentence for a box that is already on ({screen})",
              standalone,
              [templates, f'— the sentence has to exist for the case the '
               f'ticket is about; the phrase "{screen}" appearing as a '
               'clause on the Roster sentence is not that case'])

    check('the wrote-prose-anyway branch still has a guard to read',
          guard, '— the shape moved; every door check above is vacuous '
          'until this regex finds the condition again')

    # ── 2. the two paths agree about the vault ───────────────────────────
    # The defect in one line: the office knew the right screen on the path
    # where the speaker has no card, and said the wrong one on the path
    # where they do.
    m = re.search(r"vault:\s*'([^']+)'", ceo_doors)
    check('the chief of staff has a vault door',
          m is not None, ceo_doors)
    if m:
        check('...and the coworker sentence names the same screen',
              any(m.group(1) in t and 'already on' in t for t in templates),
              [m.group(1), templates])

    # ── 3. the box is named off the catalog, not typed out ───────────────
    check('the vault sentence reads its box label off the catalog',
          "toolClaimLabel('VAULT_NEW')" in note,
          'the label is printed on the checkbox by TOOLS_CATALOG; a second '
          'copy here is a rewording away from naming a box nobody can see')

    # ── 4. drive the sentences ───────────────────────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
    else:
        js = "const TOOLS_CATALOG = [{id:'web',label:'Web Search'},"
        js += "{id:'vault',label:'Vault Notes'},{id:'img',label:'Image Gen'}];\n"
        js += re.search(r'const ELEVATION_DOOR = .*?;', code).group(0) + '\n'
        js += re.search(r'const TOOL_CLAIM_GROUPS = \[[\s\S]*?\];', code).group(0) + '\n'
        for fn in ('function toolClaimGroup(', 'function toolClaimLabel(',
                   'function claimNeedsMediaDoor(', 'function claimHitsMediaDoor(',
                   'function claimNeedsVaultDoor(', 'function claimHitsVaultDoor(',
                   'function claimLabels(', 'function reachedForNote('):
            js += brace_lift(code, fn) + '\n'
        js += r'''
const KIP    = { name: 'Kip',   tools: ['web', 'vault'] };
const MARGE  = { name: 'Marge', tools: ['web'] };
const PIXEL  = { name: 'Pixel', tools: ['img', 'vault'] };
const R = {
  // The reproduced reach: box on, connection down.
  ticked:    reachedForNote(['VAULT_NEW'], KIP),
  // The other half of the same claim family.
  exported:  reachedForNote(['EXPORT_PDF'], KIP),
  // Box off — the Roster IS the shut door, and this must not change.
  unticked:  reachedForNote(['VAULT_NEW'], MARGE),
  // One reply, two kinds of door.
  both:      reachedForNote(['BASH', 'VAULT_NEW'], KIP),
  // Two second doors at once.
  twoOpen:   reachedForNote(['GENERATE_IMAGE', 'VAULT_NEW'], PIXEL),
  // Nothing with a door behind it: another note owns this event.
  silentLbl: claimLabels(['MEMORY_WRITE', 'ACK'], KIP),
  silentHit: claimHitsVaultDoor(['MEMORY_WRITE', 'ACK'], KIP),
  // The CEO's one-argument call: unknown boxes are not ticked boxes.
  unknown:   claimLabels(['VAULT_NEW']),
  dropped:   claimLabels(['VAULT_NEW'], KIP),
  kept:      claimLabels(['VAULT_NEW'], MARGE),
};
console.log(JSON.stringify(R));
'''
        p = subprocess.run(['node', '--input-type=module', '-e', js],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            print(p.stdout)
            print(p.stderr[-1500:], file=sys.stderr)
            raise SystemExit('node harness failed on source lifted from hq-runtime')
        R = json.loads(p.stdout.strip().split('\n')[-1])

        check('a ticked box sends the boss to Connections',
              'Settings → Connections' in R['ticked']
              and 'Settings → Roster' not in R['ticked'], R['ticked'])
        check("...and does not say they don't have it",
              "which they don't have" not in R['ticked'], R['ticked'])
        check('...and names the box as the checkbox prints it',
              'Vault Notes box is already on' in R['ticked'], R['ticked'])
        check('the exports ride the same claim, so the same door',
              'Settings → Connections' in R['exported']
              and 'Settings → Roster' not in R['exported'], R['exported'])
        check('an UNticked box still points at the Roster',
              'Settings → Roster' in R['unticked']
              and 'Vault Notes' in R['unticked'], R['unticked'])
        # Both doors in one sentence, because both are shut: the shell has
        # no box to tick and the vault has no connection.
        check('a reply that hits both kinds names both screens',
              'Settings → Roster' in R['both']
              and 'Settings → Connections' in R['both'], R['both'])
        check('two open boxes and two shut connections is one sentence',
              'Settings → Media' in R['twoOpen']
              and 'Settings → Connections' in R['twoOpen']
              and 'Settings → Roster' not in R['twoOpen'], R['twoOpen'])
        check('markers with no door stay silent',
              R['silentLbl'] == '' and R['silentHit'] is False,
              [R['silentLbl'], R['silentHit'],
               '— unsentHandoff and unsentBlocks own those, on the same buffer'])
        check('an unknown roster still gets the label',
              R['unknown'] == 'Vault Notes', repr(R['unknown']))
        check('...while a known-ticked one is dropped',
              R['dropped'] == '', repr(R['dropped']))
        check('...and a known-unticked one is kept',
              R['kept'] == 'Vault Notes', repr(R['kept']))

    print()
    if FAILS:
        print(f'{len(FAILS)} check(s) failed')
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
