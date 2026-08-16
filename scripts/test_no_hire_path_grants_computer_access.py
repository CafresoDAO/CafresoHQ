#!/usr/bin/env python3
"""File and shell access is granted by the boss, never by a hire button.

modals/hire.jsx states the rule at `loadTpl`: "elevated never flows from a
template — operator must re-opt-in deliberately." Both single-hire paths
obey it by forcing the switch off. The shelf's ⚡SEED SWARM tile did not: it
spread `...tpl` into the new agent and carried the templates' `elevated:
true` straight onto the roster.

Measured live on office 9261, 2026-08-16. The tile's confirm read "Hire 5
openswarm-style specialists: Dax, Sloan, Quill, Pixel, Atlas?" — the names
and nothing else — and three of the five arrived able to read and write
files and run shell commands on the machine. Hiring those same three one at
a time grants that zero times, and the only control that does grant it is a
danger-styled "Grant X COMPUTER ACCESS?" walk on the coworker's own card.

Guards:
  · the bulk path pins the flag off, AFTER the spread, so a template
    cannot reach past it
  · no template carries the flag at all
  · the single-hire paths still force it off and never read it from a
    template
  · the one control that grants it still asks first, in those words
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'hq-runtime.jsx'
HIRE = ROOT / 'modals' / 'hire.jsx'
SETTINGS = ROOT / 'modals' / 'settings.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def strip_comments(src):
    """Block comments only — this file's prose says "elevated" a lot, and a
    check that cannot tell a note from a field would pass or fail on the
    wording rather than on the code."""
    return re.sub(r'/\*[\s\S]*?\*/', '', src)


def brace_lift(src, header):
    i = src.index(header)
    j = src.index('{', i + len(header) - 1)
    d = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                return src[i:k + 1]
    raise ValueError('unbalanced: ' + header)


def main():
    print('no hire path grants computer access')
    for p in (RUNTIME, HIRE, SETTINGS):
        if not p.is_file():
            print(f'  FAIL  missing {p}')
            return 1
    runtime = RUNTIME.read_text(encoding='utf-8')
    hire = HIRE.read_text(encoding='utf-8')
    settings = SETTINGS.read_text(encoding='utf-8')

    spawn = brace_lift(runtime, 'function spawnOpenswarmRoster(existingAgents, addAgent, model) {')
    roster = runtime[runtime.index('const OPENSWARM_ROSTER = ['):runtime.index('function spawnOpenswarmRoster')]

    # ── the bulk path ─────────────────────────────────────────────────────
    check('the bulk hire pins the flag off', 'elevated: false,' in spawn,
          'spawnOpenswarmRoster spread ...tpl and carried the template value')
    # Order matters more than presence: `{elevated: false, ...tpl}` would read
    # identically to a skim and grant access exactly as before.
    check('...and pins it AFTER the spread, where the template cannot reach past it',
          spawn.index('...tpl') < spawn.index('elevated: false,'),
          'an elevated:false ABOVE the spread is overwritten by it')

    # ── the templates ─────────────────────────────────────────────────────
    check('no candidate template carries the flag',
          not re.search(r'(?m)^\s*elevated\s*:', strip_comments(roster)),
          'Dax, Sloan and Quill each set elevated: true; the shelf card read '
          'them too, so the pitch promised files a hire would not have')

    # ── the single-hire paths still obey the stated rule ──────────────────
    check('the stated rule is still written down where it is obeyed',
          'elevated never flows from a template' in hire)
    check('every hire-form entry point forces the switch off',
          hire.count('setElevated(false)') >= 3,
          'blank form, saved template, and candidate card')
    check('no hire-form path reads elevation off what it is loading',
          not re.search(r'setElevated\(\s*(t|tpl|tmpl|c|cand)\b', hire),
          'setElevated(tpl.elevated) would be the same defect on the other path')
    # The rule is "re-opt-in deliberately", not "never" — the form's own
    # checkbox is the deliberate part, and a suite that banned every
    # setElevated call would be asking for the capability to be removed.
    check('...but the operator can still tick it on the form themselves',
          re.search(r'setElevated\(e\.target\.checked\)', hire) is not None)

    # ── the one real door ─────────────────────────────────────────────────
    # Scoped to the switch's own handler, not the file. Both of the first two
    # checks here passed a mutation that made the walk unreachable (`if
    # (false)`) and one that dropped `danger: true`, because settings.jsx has
    # other confirms and other danger dialogs: a substring anywhere in a
    # 1500-line file says nothing about what this control does.
    check('the office has exactly one control that turns it on',
          settings.count('update({ elevated: !sel.elevated })') == 1,
          'a second one would need its own walk')
    sw = "<div className={`pxswitch ${sel.elevated?'on':''}`} onClick={async ()=>{"
    grant = settings[settings.index(sw):settings.index('update({ elevated: !sel.elevated })')]
    check('the walk is on the path, not merely in the file',
          'if (!sel.elevated) {' in grant,
          'the confirm has to gate the flip, not sit beside it')
    check('...and a refusal stops the grant',
          re.search(r'\)\)\)\s*return;', grant) is not None)
    check('granting it still asks, in those words',
          'COMPUTER ACCESS?' in grant and 'danger: true' in grant, grant[-200:])
    check('...and still says what it means in plain language',
          'read/write files and run shell commands on this machine' in grant)

    # ── drive it ──────────────────────────────────────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
    else:
        # The lifted function closes over whatever OPENSWARM_ROSTER is in
        # scope, so the harness supplies a hostile one: a template that DOES
        # set the flag is the case the belt-and-braces exists for, and the
        # real roster (asserted flagless above) cannot exercise it.
        prelude = '''
let _n = 0;
const uid = () => 'a_' + (++_n);
const OPENSWARM_ROSTER = [
  { name: 'Elevator', tools: ['files'], elevated: true, model: 'ollama:x' },
  { name: 'Plain',    tools: ['vault'], model: 'ollama:x' },
  { name: 'Parked',   tools: ['files'], elevated: true, parked: true, model: 'ollama:x' },
  { name: 'Dupe',     tools: ['vault'], model: 'ollama:x' },
];
'''
        cases = '''
const R = {};
let added = [];
R.count = spawnOpenswarmRoster([], a => added.push(a), 'lmstudio:canned-brain');
R.names = added.map(a => a.name);
R.elevated = added.map(a => !!a.elevated);
R.keptTools = added.map(a => (a.tools || []).join('+'));
R.brains = added.map(a => a.model);
// A roster that already has one of them does not get a second.
added = [];
R.dupeCount = spawnOpenswarmRoster([{ name: 'dupe' }], a => added.push(a));
R.dupeNames = added.map(a => a.name);
// No override hands back the template's own brain.
R.tplBrain = added[0] && added[0].model;
console.log(JSON.stringify(R));
'''
        proc = subprocess.run(['node', '--input-type=module', '-e', prelude + spawn + cases],
                              cwd=ROOT, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            raise SystemExit('node harness failed to run')
        out = json.loads(proc.stdout.strip().split('\n')[-1])

        check('a template that sets the flag still cannot grant it',
              out['elevated'] == [False, False, False],
              str(list(zip(out['names'], out['elevated']))))
        check('the parked template is still skipped',
              out['names'] == ['Elevator', 'Plain', 'Dupe'] and out['count'] == 3,
              str(out['names']))
        check('...and the claim list is untouched — only the grant is refused',
              out['keptTools'] == ['files', 'vault', 'vault'], str(out['keptTools']))
        check('the shelf brain still overrides every template',
              out['brains'] == ['lmstudio:canned-brain'] * 3, str(out['brains']))
        check('a name already on the roster is not hired twice',
              out['dupeNames'] == ['Elevator', 'Plain'] and out['dupeCount'] == 2,
              str(out['dupeNames']))
        check('no override keeps the template brain',
              out['tplBrain'] == 'ollama:x', str(out['tplBrain']))

    print()
    if FAILS:
        print(f'{len(FAILS)} check(s) failed')
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
