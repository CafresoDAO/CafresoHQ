#!/usr/bin/env python3
"""Granting file & shell access told a boss it isolated the coworker from
DMs. It doesn't, on purpose.

Four surfaces made the same claim:

    modals/hire.jsx:693   (hire-form privilege checkbox hint)
        "...DMs blocked, missions opt-in, every action logged."
    modals/settings.jsx:1160  (Roster config panel, same wording)
        "Has file and shell access. DMs blocked, missions opt-in, every action logged."
    modals/settings.jsx:1168  (the window.hqConfirm dialog shown on the actual grant)
        "DMs from other agents will be blocked, missions require explicit
         authorization, and every tool call is logged."
    modals/hire.jsx:399  (the SEPARATE window.hqConfirm shown when building
    a custom agent from scratch, rather than hiring a detected one — found
    later, after the first three were already fixed; the original sweep's
    grep evidently never reached this second confirm dialog in the same
    file)
        "· Inter-agent DMs cannot reach them (only your direct dispatches will)."

app.jsx's dispatchToAgent does the opposite, deliberately:

    /* DM-chain to elevated agents is allowed — teammates can collaborate with
       privileged peers (e.g. Selvin for code audits). A brief system note is
       added to the team thread so the boss can see the handoff. */
    if (dmFrom && agent.elevated) {
      setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
        text: `(${dmFrom.name} → ${agent.name}: handing over, with file and shell access)`,
        thread: 'team' }]);
    }

Nothing after that returns or refuses — dispatch falls straight through to
the normal send path. The `DM_TO` tool itself (hq-runtime.jsx) carries
`requires: () => true`, no elevation gate. And when a boss DENIES
elevation, the system prompt's own fallback instruction tells the declined
agent to route around it exactly this way:

    `...or [DM_TO] an elevated teammate who can do it for you, or [ACK: blocked: …]...`

This isn't an oversight in the dispatch code — it's a deliberate design
(the comment names the use case: "Selvin for code audits") that the
elevation-grant copy simply never caught up to. A boss reading the confirm
dialog before clicking "Grant access" — the one place this claim matters
most, since it's the moment they're deciding whether to trust a coworker
with file/shell access — was told a false safety boundary.

**The fix** rewrites the false clause in all four places to describe the
real one: DMs are still possible, and each handoff is announced in the
Team thread rather than happening invisibly. The other two clauses on the
same line ("missions opt-in" / "every action logged") were verified true
and left alone — missions.jsx:1007 (`if (isElevated && !elevatedAuth)
return;`) and app.jsx's elevated-audit-trail block are both real.

The fourth surface's false claim ("cannot reach them") used different
words than the first three ("blocked" / "will be blocked") — different
enough that the original `FALSE_CLAIM` regex below didn't match it, which
is exactly why grepping for "blocked" once and fixing every hit it found
still missed this one. The pattern is widened alongside the fix so a
fifth rephrasing of the same false claim doesn't get the same free pass.

Run: python3 scripts/test_elevation_copy_matches_the_dm_boundary.py
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HIRE = (ROOT / 'modals/hire.jsx').read_text(encoding='utf-8')
SETTINGS = (ROOT / 'modals/settings.jsx').read_text(encoding='utf-8')
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
RUNTIME = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


FALSE_CLAIM = re.compile(
    r'DMs?\s+(?:blocked|from other agents will be blocked|cannot reach|can\'t reach)'
    r'|(?:cannot|can\'t)\s+reach\s+them\b',
    re.I)


def main():
    print('Elevation copy: the DM claim matches what dispatch actually does')

    # ── 1. the false claim is gone everywhere it used to be made ─────────
    for label, text in [('modals/hire.jsx', HIRE), ('modals/settings.jsx', SETTINGS)]:
        m = FALSE_CLAIM.search(text)
        check("%s makes no 'DMs blocked' claim" % label, m is None,
              m and text[max(0, m.start() - 60):m.end() + 20])

    check('hire.jsx\'s hint describes the real boundary instead',
          'Reachable by teammate DMs' in HIRE and 'noted in Team' in HIRE, HIRE[:0])
    check('settings.jsx\'s roster sub-line matches',
          'Reachable by teammate DMs' in SETTINGS, SETTINGS[:0])
    check('settings.jsx\'s grant-access confirm dialog matches',
          'Teammates can still send them DMs' in SETTINGS
          and 'noted in the Team thread' in SETTINGS, SETTINGS[:0])

    # hire.jsx has TWO separate places that make this claim — the privilege
    # hint (line 693, checked above) and a second, independent
    # window.hqConfirm shown when building a custom agent from scratch
    # (line ~399). Both need the honest text; a count check catches either
    # one silently reverting, not just the pair collectively containing it
    # somewhere.
    check('both of hire.jsx\'s own DM-boundary claims were fixed, not just one',
          HIRE.count('Reachable by teammate DMs') == 2,
          'found %d — the custom-agent-build confirm dialog is a second, '
          'separate call site from the privilege-checkbox hint; fixing one '
          'does not fix the other' % HIRE.count('Reachable by teammate DMs'))
    check('...and the custom-build confirm dialog specifically carries the '
          'honest bullet',
          '· Reachable by teammate DMs — each handoff is noted in the Team thread.'
          in HIRE, HIRE[:0])

    # The two OTHER clauses on the same line are true — verify they
    # survived the rewrite rather than getting dropped along with the
    # false one. rindex(), not index(): HIRE now carries the fixed claim
    # TWICE (line ~399 and line 693) and this check is specifically about
    # the privilege-hint line (693, the later of the two in the file) —
    # index() would grab the custom-build dialog's own true-but-differently-
    # worded mission clause instead and fail on unrelated wording.
    check('...and both keep the two TRUE claims on the same line',
          all('missions opt-in' in s or 'missions require explicit authorization' in s
              for s in [HIRE[HIRE.rindex('Reachable by teammate DMs'):HIRE.rindex('Reachable by teammate DMs') + 120],
                        SETTINGS[SETTINGS.index('Reachable by teammate DMs'):SETTINGS.index('Reachable by teammate DMs') + 120]])
          and 'every action logged' in HIRE and 'every action logged' in SETTINGS
          and 'every tool call is logged' in SETTINGS,
          'the fix must correct the false clause without silently dropping '
          'the two adjacent claims that are actually true')

    # ── 2. the code reality the new copy describes ────────────────────────
    allow_block_m = re.search(
        r'if \(dmFrom && agent\.elevated\) \{\s*'
        r'setChat\(prev => \[\.\.\.prev, \{ id: HQ\.uid\(\'m\'\), from: \'system\', name: \'HQ\',\s*'
        r"text: `\(\$\{dmFrom\.name\} → \$\{agent\.name\}: handing over, with file and shell access\)`,\s*"
        r"thread: 'team' \}\]\);\s*\}",
        APP)
    check('dispatchToAgent still allows (and announces) a DM to an elevated '
          'agent — this is what the new copy claims; if this ever becomes a '
          'refusal, the copy just fixed here would go false the other way',
          allow_block_m is not None, APP[:0])

    check('...and nothing between that block and the send path returns early '
          '(an early return here would silently turn "allowed" back into '
          '"blocked" without this test file\'s static check above catching it)',
          allow_block_m and 'return;' not in APP[allow_block_m.end():allow_block_m.end() + 400],
          APP[allow_block_m.end():allow_block_m.end() + 200] if allow_block_m else '')

    check('DM_TO carries no elevation gate in the tool registry',
          re.search(r"dm_to:\s*\{[^}]*?requires:\s*\(\)\s*=>\s*true", RUNTIME, re.S) is not None,
          'a `requires` gate keyed on agent.elevated appearing here would be '
          'the other half of actually implementing the claim this ticket '
          'just removed — fine to add, but the copy would need to flip back')

    check('the denied-elevation fallback still points agents at exactly this '
          'path, corroborating it\'s a designed feature and not dead code',
          '[DM_TO] an elevated teammate who can do it for you' in APP, APP[:0])

    # ── 3. the mechanism, run for real: the allow-and-announce block alone ──
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the mechanism check needs it')
    elif not allow_block_m:
        check('mechanism check runs', False, 'could not locate the block to lift')
    else:
        block_src = allow_block_m.group(0)
        js = r'''
function drive(dmFrom, agent) {
  const chat = [];
  const HQ = { uid: (p) => p + '_x' };
  const setChat = (fn) => { chat.push(...fn([]).map(x => x)); };
''' + '  ' + block_src + r'''
  return chat;
}
console.log(JSON.stringify({
  elevatedDm: drive({ name: 'Nova' }, { name: 'Selvin', elevated: true }),
  nonElevatedDm: drive({ name: 'Nova' }, { name: 'Kip', elevated: false }),
  bossDispatch: drive(null, { name: 'Selvin', elevated: true }),
}));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=15)
        if p.returncode != 0:
            check('the mechanism harness runs', False, p.stderr.strip()[:400])
        else:
            out = __import__('json').loads(p.stdout)
            check('a teammate DM to an elevated coworker is allowed and announced',
                  len(out['elevatedDm']) == 1
                  and 'Nova → Selvin' in out['elevatedDm'][0]['text']
                  and out['elevatedDm'][0]['thread'] == 'team',
                  out['elevatedDm'])
            check('a DM to a NON-elevated coworker gets no such note (nothing '
                  'to announce — the elevation itself is the newsworthy part)',
                  out['nonElevatedDm'] == [], out['nonElevatedDm'])
            check('a boss dispatch (not a peer DM) to an elevated coworker is '
                  'silent too — dmFrom is what makes this a handoff',
                  out['bossDispatch'] == [], out['bossDispatch'])

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
