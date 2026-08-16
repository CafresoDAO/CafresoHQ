#!/usr/bin/env python3
"""/who-can rated a coworker who couldn't exactly like one who could.

Measured 2026-08-16. Two coworkers, both titled Research: Kip with Web
Search ticked, Vera with nothing ticked at all. `/who-can research`
returned

    • Vera (Research): research
    • Kip (Research): research

— the same shape, and Vera first. The skill words come from
`agentCapabilities`, which reads the job title and the elevation flag and
never once asks what the coworker has actually been granted, so the
office's answer to "who can do this" was a guess presented as a roster.

The other half was the dead end. With no match the toast read *No agent
claims "q". (Hire one or set capabilities on an existing agent.)* —
`agent.capabilities` is read in exactly one place and written NOWHERE:
not the hire form, not the Roster card (which patches model, temperature,
tools, toolFormat and elevated), not the backend, not a template. Of the
two ways out it offered, one was a control that does not exist. And the
input it really uses — the job title — is a `<select>` at hire with no
later edit, so a boss who took the advice had nothing to take it with.

The fix is the one the product already made three times: `grantedTools`
over `capabilityFacts` is its single answer to "what can this coworker
reach", and the comment exporting `capabilityFacts` says the surfaces
that describe a coworker's reach "must all ask the same question of the
same file that answers it for real". /who-can was a fourth such surface
that never asked. It asks now — injected, because app/agents.jsx and
app/cast.jsx are both import-free by design and run verbatim under node.

Run: python3 scripts/test_who_can_says_who_actually_can.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []

WIRE = 'whoCan(agents, q, a => grantedTools(a.tools, HQ.capabilityFacts(a)))'
DEAD_FIELD = 'set capabilities on an existing agent'
# The three surfaces that already ask the shared question. A fourth
# vocabulary is the thing this whole family of tickets keeps paying for.
REACH_PAIR = re.compile(r'grantedTools\(\s*(?:a|agent|sel|c)\.tools\s*,'
                        r'\s*(?:HQ\.)?capabilityFacts\(')


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('who-can says who actually can')
    if not shutil.which('node'):
        print('SKIP — node not on PATH')
        return 0

    agents_src = (ROOT / 'app' / 'agents.jsx').read_text(encoding='utf-8')
    cast_src = (ROOT / 'app' / 'cast.jsx').read_text(encoding='utf-8')
    cmds_src = (ROOT / 'app' / 'commands.jsx').read_text(encoding='utf-8')
    a_bare = strip_comments(agents_src)
    c_bare = strip_comments(cmds_src)

    # ── the field that never existed ────────────────────────────────────
    check('the dead-end no longer names a field nothing writes',
          DEAD_FIELD not in c_bare, 'the toast still sends the boss to `capabilities`')
    check('…and the dead read of that field is gone too',
          'agent.capabilities' not in a_bare,
          'a read with no writer is what made the advice sound real')
    # Belt and braces: if someone gives the field a door later, this check
    # is the one that should fail first, so the advice and the field go back
    # together. The word itself is not banned — it has two honest uses in
    # the product that are not an agent's field, and they are pinned here by
    # shape so that a THIRD use has to be looked at by a person:
    #   * the run prompt's prose, "Claimed capabilities: ...", which is
    #     about the tools one run was handed -- a different vocabulary;
    #   * `capabilities: caps`, the key on whoCan's OWN result object: the
    #     guess it just computed, not a record it wrote back to an agent.
    known = [re.compile(r'Claimed capabilities: \$\{'),
             re.compile(r'\bcapabilities: caps\b')]
    seen, unknown = [False] * len(known), []
    for p in sorted(ROOT.rglob('*.jsx')):
        rel = str(p.relative_to(ROOT))
        # `.claude/worktrees` is somebody else's checkout of this repo, not
        # the product; scanning it reports their work as ours.
        if rel.startswith('.claude') or 'node_modules' in rel or 'dist-ui' in rel:
            continue
        for n, line in enumerate(strip_comments(p.read_text(encoding='utf-8')).splitlines(), 1):
            if not re.search(r'(?<![\w$.])capabilities\s*:', line):
                continue
            hit = next((i for i, k in enumerate(known) if k.search(line)), None)
            if hit is None:
                unknown.append(f'{rel}:{n}')
            else:
                seen[hit] = True
    check('nothing in the product writes agent.capabilities', not unknown, unknown)
    # A pin that no longer matches anything is its own wrong door: it would
    # quietly wave through the next use of that spelling.
    check('…and both pinned non-agent uses are still there to pin',
          all(seen), [k.pattern for k, s in zip(known, seen) if not s])
    check('the dead end offers doors that do exist',
          'hire someone from the front desk' in c_bare and '@-mention' in c_bare,
          '§7 — an honest dead end still needs a way forward')
    check('…and says why the job title is not one of them',
          "can't be changed after" in c_bare,
          'the boss must not be sent to an edit that is not there')

    # ── the fourth surface asks the shared question ─────────────────────
    check('/who-can is handed the product\'s own reach reader',
          WIRE in c_bare, 'not the same pair the three other surfaces use')
    surfaces = {p.name: len(REACH_PAIR.findall(strip_comments(p.read_text(encoding='utf-8'))))
                for p in [ROOT / 'ui' / 'panels.jsx', ROOT / 'views' / 'core.jsx',
                          ROOT / 'app' / 'commands.jsx']}
    check('the other surfaces still ask it the same way',
          surfaces['panels.jsx'] >= 1 and surfaces['commands.jsx'] >= 1, surfaces)
    check('whoCan takes the reader rather than importing one',
          'function whoCan(agents, queryRaw, reachOf)' in a_bare
          and not re.search(r'^import ', a_bare, re.M),
          'app/agents.jsx is import-free by design and runs verbatim under node')

    # ── drive the real functions against the real tables ────────────────
    lift = a_bare[a_bare.index('const ROLE_CAPABILITY_MAP'):a_bare.index('export {')]
    cast_lift = cast_src[:cast_src.index('export {')]
    check('agents.jsx lifts', 'function whoCanLine' in lift)
    check('cast.jsx lifts whole', 'function grantedTools' in cast_lift)

    js = ('const CAST = ' + json.dumps(cast_lift) + ';\n'
          + 'const AGENTS = ' + json.dumps(lift) + ';\n'
          + r'''
const mod = new Function(CAST + AGENTS
  + ' return { whoCan, whoCanLine, agentCapabilities, grantedTools, CAN_DO };')();
const { whoCan, whoCanLine, agentCapabilities, grantedTools } = mod;

/* The measured pair, plus a coworker whose capability is real but switched
   off, one whose door is elevation, and — listed AFTER the switched-off one,
   so declaration order cannot be mistaken for ranking — a coworker with the
   same job title holding a live grant. */
const ROSTER = [
  { name: 'Vera',  role: 'Research', tools: [],           elevated: false },
  { name: 'Kip',   role: 'Research', tools: ['web'],      elevated: false },
  { name: 'Pixel', role: 'Designer', tools: ['img'],      elevated: false },
  { name: 'Otto',  role: 'Ops',      tools: ['files'],    elevated: true  },
  { name: 'Dot',   role: 'Designer', tools: ['web'],      elevated: false },
];
/* The REAL reader, with the facts the caller would have established. */
const facts = { canSearch: true, canMakeImages: false, vaultOn: false, moneyOn: false };
const reachOf = (a) => grantedTools(a.tools,
  Object.assign({}, facts, { elevated: !!a.elevated }));

const lines = (q, r) => whoCan(ROSTER, q, r).map(whoCanLine);

/* A fresh office with no Brave key: 'web' has a smaller true version, so
   Kip is still granted something. The unconfigured case is the one where
   the two coworkers are genuinely indistinguishable without reach. */
const noKey = (a) => grantedTools(a.tools,
  Object.assign({}, facts, { canSearch: false, elevated: !!a.elevated }));

console.log(JSON.stringify({
  research: lines('research', reachOf),
  researchNoKey: lines('research', noKey),
  design: lines('design', reachOf),
  shell: lines('shell', reachOf),
  absent: lines('research', undefined),
  throws: lines('research', () => { throw new Error('settings unreadable'); }),
  order: whoCan(ROSTER, 'research', reachOf).map(h => h.agent.name),
  designOrder: whoCan(ROSTER, 'design', reachOf).map(h => h.agent.name),
  orderAbsent: whoCan(ROSTER, 'research').map(h => h.agent.name),
  reachAbsentKey: whoCan(ROSTER, 'research').every(
    h => !Object.prototype.hasOwnProperty.call(h, 'reach')),
  capsIgnoreExplicitField: agentCapabilities(
    { role: 'Docs', capabilities: ['brain-surgery'] }),
}));
''')
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('the lifted resolver runs', False, p.stderr.strip()[:400])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('a coworker who can do it is named first',
          r['order'] == ['Kip', 'Vera'],
          'this is the measured bug: Vera, with nothing ticked, led the list')
    check('…and says what they can actually reach',
          any('Kip' in l and 'can search the web' in l for l in r['research']),
          r['research'])
    check('a coworker with nothing ticked says so',
          any('Vera' in l and 'nothing ticked on their card yet' in l
              for l in r['research']),
          r['research'])
    check('a real capability behind a switch gets its way forward, not a blank',
          any('Pixel' in l and 'could make images once you pick an image provider' in l
              for l in r['design']),
          r['design'])
    check('elevation reads as a reach, not just a skill word',
          any('Otto' in l and 'work with your files' in l for l in r['shell']),
          r['shell'])
    check('an office with no search key still ranks the grant above nothing',
          r['researchNoKey'][0].startswith('• Kip'), r['researchNoKey'])
    # A switched-off capability is a promise, not a reach. Counting it in the
    # ranking would rebuild the same false equivalence one notch quieter:
    # two Designers side by side, identical bullets bar the suffix, and the
    # one who cannot do it today listed first.
    check('a capability switched off does not rank like one switched on',
          r['designOrder'] == ['Dot', 'Pixel'],
          r['designOrder'])

    check('no reader → no claim about reach, and the order is left alone',
          r['absent'] == ['• Vera (Research): research', '• Kip (Research): research']
          and r['orderAbsent'] == ['Vera', 'Kip'] and r['reachAbsentKey'],
          'absent must never render as "they have nothing" — see cast.jsx')
    check('a reader that throws leaves the fact absent too',
          r['throws'] == r['absent'], r['throws'])
    check('an explicit capabilities array is not consulted',
          'brain-surgery' not in r['capsIgnoreExplicitField'],
          'the branch is gone; nothing writes the field')

    if FAILS:
        print(f'FAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS))
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
