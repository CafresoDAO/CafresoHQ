#!/usr/bin/env python3
"""The "Can use" row shows the GRANT, not the stored claim.

Two surfaces describe what a hired coworker can reach — the TeamView card
(views/core.jsx) and the inspect panel (ui/panels.jsx) — and both printed
`agent.tools` verbatim under a tooltip calling it "what this coworker is
allowed to reach". `agent.tools` is the claim the boss ticked (or that a
template minted for them); the grant is `toolsForAgent`, which reads four
other facts before it hands anything over.

Measured 2026-08-16 by hiring Dax off the candidate shelf: shelf card said
"Can work with your files and read your notes", coworker card said FILES
VAULT DB. `db` is wired to nothing anywhere, `files` needs an elevation the
hire flow had just switched off, and Settings → Roster — the door that same
tooltip names — shows neither.

Guards, in order:
  · both surfaces render from grantedTools(), never from the raw list
  · one reader of the four facts (hq-runtime, beside the grant), not a copy
    per surface
  · one tooltip string, not one per surface
  · no template mints a tool id the cast tables cannot name
  · grantedTools itself: drops the unwired, locks the unswitched, keeps the
    smaller true version, and says nothing about facts it could not read
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAST = ROOT / 'app' / 'cast.jsx'
CORE = ROOT / 'views' / 'core.jsx'
PANELS = ROOT / 'ui' / 'panels.jsx'
RUNTIME = ROOT / 'hq-runtime.jsx'
HIRE = ROOT / 'modals' / 'hire.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def run_js(cases_js):
    """Same node-under-python harness the other cast suites use: strip the
    import/export lines and run the file verbatim."""
    text = CAST.read_text(encoding='utf-8')
    src = '\n'.join(ln for ln in text.split('\n')
                    if not ln.startswith('import ') and not ln.startswith('export '))
    proc = subprocess.run(['node', '--input-type=module', '-e', src + '\n' + cases_js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def tool_arrays(src):
    """Every `tools: ['a','b']` literal in a source file, flattened."""
    out = []
    for m in re.finditer(r"tools:\s*\[([^\]]*)\]", src):
        out.extend(re.findall(r"'([^']+)'", m.group(1)))
    return out


def main():
    print('the card lists what the runtime grants')
    for p in (CAST, CORE, PANELS, RUNTIME, HIRE):
        if not p.is_file():
            print(f'  FAIL  missing {p}')
            return 1
    cast = CAST.read_text(encoding='utf-8')
    core = CORE.read_text(encoding='utf-8')
    panels = PANELS.read_text(encoding='utf-8')
    runtime = RUNTIME.read_text(encoding='utf-8')
    hire = HIRE.read_text(encoding='utf-8')

    # ── the two surfaces render the grant ─────────────────────────────────
    check('the card asks grantedTools for the row',
          'grantedTools(a.tools, HQ.capabilityFacts(a))' in core,
          'views/core.jsx must not build the row from a.tools directly')
    check('the panel asks grantedTools for the row',
          'grantedTools(agent.tools, HQ.capabilityFacts(agent))' in panels,
          'ui/panels.jsx must not build the row from agent.tools directly')
    # The exact shapes that shipped the defect. Not a blanket ban on touching
    # `a.tools` — the tooltip on the shelf still joins it, legitimately.
    check('the card no longer maps the raw claim into chips',
          '(a.tools||[]).map' not in core and '(a.tools || []).map' not in core)
    check('the panel no longer maps the raw claim into chips',
          '(agent.tools||[]).map' not in panels and '(agent.tools || []).map' not in panels)
    check('the card gates the row on what it will actually show',
          'if (!reach.granted.length && !reach.locked.length) return null;' in core,
          'gating on a.tools.length again would render an empty chip strip')
    check('the panel gates the row on what it will actually show',
          'if (!reach.granted.length && !reach.locked.length) return null;' in panels)
    check('both surfaces import grantedTools from the cast',
          'grantedTools' in core.split('\n')[5] or 'grantedTools' in core[:600],
          'must come from app/cast.jsx, not be re-implemented')
    check('the panel imports the runtime it now asks for facts',
          "import { HQ } from '../hq-runtime.jsx';" in panels)

    # ── locked capabilities keep a route (§7) ─────────────────────────────
    check('the card dims locked chips instead of dropping them',
          'reach.locked.map' in core and 'opacity: 0.45' in core)
    check('the panel dims locked chips instead of dropping them',
          'reach.locked.map' in panels and 'opacity: 0.45' in panels)
    check('a locked chip carries its unlock sentence',
          core.count('l.unlock ?') == 1 and panels.count('l.unlock ?') == 1,
          'the door is the whole point of showing a locked chip at all')
    check('a locked chip is legible as off without the tooltip',
          "· off" in core and "· OFF" in panels)

    # ── one reader, one tooltip ───────────────────────────────────────────
    check('the fact reader lives beside the grant',
          'function capabilityFacts(subject) {' in runtime
          and runtime.index('function capabilityFacts(subject) {') < runtime.index('async function toolsForAgent('))
    check('capabilityFacts is exported on HQ', re.search(r'\n  capabilityFacts,\n', runtime) is not None)
    check('the hire modal no longer keeps a private copy',
          'function capabilityFacts(t) {' not in hire and 'HQ.capabilityFacts(t)' in hire)
    check('the shelf still passes the facts to canDoPhrase',
          re.search(r'canDoPhrase\(t\.tools,\s*capabilityFacts\(t\)\)', hire) is not None)
    for fact, expr in (('canSearch', 'TOOL_REGISTRY.search.requires()'),
                       ('canMakeImages', 's.imageProvider'),
                       ('moneyOn', 'icpWalletEnabled()')):
        seg = runtime[runtime.index('function capabilityFacts(subject) {'):runtime.index('async function toolsForAgent(')]
        check(f'{fact} is read with the runtime\'s own expression', expr in seg,
              f'the card and toolsForAgent must not compute {fact} two ways')
    check('the tooltip has one home',
          cast.count('What this coworker is allowed to reach') == 1
          and 'What this coworker is allowed to reach' not in core
          and 'What this coworker is allowed to reach' not in panels)
    check('both surfaces use the shared tooltip',
          'CAN_USE_TIP' in core and 'CAN_USE_TIP' in panels)
    check('the dimmed-chip legend appears only when something is dimmed',
          core.count('reach.locked.length ? CAN_USE_OFF_TIP') == 1
          and panels.count('reach.locked.length ? CAN_USE_OFF_TIP') == 1)

    # ── nothing mints a claim the tables cannot name ──────────────────────
    can_do = set(re.findall(r'^  (\w+):', cast[cast.index('const CAN_DO = {'):cast.index('const CAN_DO_NEEDS')],
                            re.M))
    check('CAN_DO was found to compare against', len(can_do) >= 5, str(sorted(can_do)))
    roster = runtime[runtime.index('const OPENSWARM_ROSTER = ['):runtime.index('function spawnOpenswarmRoster')]
    bad_tpl = sorted(set(t for t in tool_arrays(roster) if t not in can_do))
    check('no candidate template mints an unnameable tool id', not bad_tpl,
          f'these reach nothing and the card cannot describe them: {bad_tpl}')
    bad_hire = sorted(set(t for t in tool_arrays(hire) if t not in can_do))
    check('no hire preset mints an unnameable tool id', not bad_hire, str(bad_hire))
    check('db is gone from the Data Analyst template', "'db'" not in roster,
          'the id that shipped on Dax\'s card as a promise')
    check('email and cal are gone from the assistant template',
          "'email'" not in roster and "'cal'" not in roster)
    check('the roster comment no longer calls them wired',
          not re.search(r"Tools currently wired[^*]*'email'", roster))

    # ── grantedTools itself ───────────────────────────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — static checks only')
    else:
        out = run_js(r'''
const R = {};
const ids = (xs) => xs.map(x => x.id);
// A boss with a Brave key, no image provider, money off, no elevation.
const PLAIN = { canSearch: true, canMakeImages: false, moneyOn: false, elevated: false };

// The shipped defect, exactly: Vera's minted claim list.
let r = grantedTools(['web','email','cal','vault'], PLAIN);
R.veraGranted = ids(r.granted); R.veraLocked = ids(r.locked);

// Dax as hired: files without the switch, db behind nothing.
r = grantedTools(['files','vault','db'], PLAIN);
R.daxGranted = ids(r.granted); R.daxLocked = ids(r.locked);
R.daxUnlock = (r.locked[0] || {}).unlock || '';

// Same coworker after the boss flips 🛡 File & shell access.
r = grantedTools(['files','vault','db'], { ...PLAIN, elevated: true });
R.daxElevated = ids(r.granted); R.daxElevatedLocked = ids(r.locked);

// No Brave key: 'web' keeps the smaller true version rather than vanishing.
r = grantedTools(['web'], { ...PLAIN, canSearch: false });
R.webNoKey = ids(r.granted); R.webNoKeySay = (r.granted[0] || {}).say || '';
R.webNoKeyLocked = ids(r.locked);

// A provider that IS set.
r = grantedTools(['img'], { ...PLAIN, canMakeImages: true });
R.imgOn = ids(r.granted);
// …and one that is not.
r = grantedTools(['img'], PLAIN);
R.imgOffLocked = ids(r.locked); R.imgUnlock = (r.locked[0] || {}).unlock || '';
// …and a settings store that could not be read at all: absent, not false.
r = grantedTools(['img'], { elevated: false });
R.imgUnknownGranted = ids(r.granted); R.imgUnknownLocked = ids(r.locked);

r = grantedTools(['wallet'], PLAIN);
R.walletLocked = ids(r.locked);

R.dupes = ids(grantedTools(['vault','vault','web','vault'], PLAIN).granted);
R.emptyG = ids(grantedTools(undefined, PLAIN).granted);
R.emptyL = ids(grantedTools(undefined, PLAIN).locked);
R.junk = ids(grantedTools(['shell','sql','email'], PLAIN).granted)
           .concat(ids(grantedTools(['shell','sql','email'], PLAIN).locked));
console.log(JSON.stringify(R));
''')
        check('the never-wired ids contribute nothing',
              out['veraGranted'] == ['web', 'vault'] and out['veraLocked'] == [],
              str(out['veraGranted']) + ' / ' + str(out['veraLocked']))
        check('a file claim without elevation is locked, not granted',
              out['daxGranted'] == ['vault'] and out['daxLocked'] == ['files'],
              str(out['daxGranted']) + ' / ' + str(out['daxLocked']))
        check('the locked file chip names the switch by its printed label',
              'file & shell access' in out['daxUnlock'], out['daxUnlock'])
        check('elevation moves files across, and db stays nowhere',
              sorted(out['daxElevated']) == ['files', 'vault'] and out['daxElevatedLocked'] == [])
        check('web with no key keeps the smaller true capability',
              out['webNoKey'] == ['web'] and out['webNoKeyLocked'] == []
              and out['webNoKeySay'] == 'read a web page you name', out['webNoKeySay'])
        check('img with a provider is granted', out['imgOn'] == ['img'])
        check('img without one is locked and names the provider',
              out['imgOffLocked'] == ['img'] and 'image provider' in out['imgUnlock'], out['imgUnlock'])
        check('an unreadable settings store says nothing about img at all',
              out['imgUnknownGranted'] == [] and out['imgUnknownLocked'] == [],
              'absent is "we could not find out", never "you have not set it up"')
        check('wallet with money off is locked', out['walletLocked'] == ['wallet'])
        check('a repeated claim is listed once', out['dupes'] == ['vault', 'web'], str(out['dupes']))
        check('no tools at all is not an error', out['emptyG'] == [] and out['emptyL'] == [])
        check('ids with nothing behind them are dropped from both lists',
              out['junk'] == [], str(out['junk']))

    print()
    if FAILS:
        print(f'{len(FAILS)} check(s) failed')
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
