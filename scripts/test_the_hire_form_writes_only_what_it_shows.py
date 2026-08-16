#!/usr/bin/env python3
"""A hire with every box unticked still landed holding `files`.

Measured live on office 9272, 2026-08-16, while verifying #121. Front desk
-> NEW HIRE -> untick all three boxes -> HIRE. The new coworker's roster
entry read `tools: ['files']`.

`files` is deliberately absent from that form's grid: `visibleToolsCatalog`
filters GRANTED_ELSEWHERE_TOOL_IDS = {'code','files'} because the real door
for file and shell access is the elevation switch, not a box here — the
decoy removal of #57/#117. But the form seeded its state with
['web','files'] and handed the whole array to `onHire`. So the claim was
written, was invisible on the hire form AND on the Roster card, and no
control in the product could take it back.

It grants nothing by itself — `toolsForAgent` still demands elevation — but
a claim is not inert. Every surface that describes a coworker's reach reads
it, and /who-can (#121, the run that caught this) duly printed for a
coworker whose boss ticked nothing:

    • Vera (Chief Research Goblin): research — nothing switched on yet;
      could work with your files once you switch on their file & shell access

That is #104 again: a card advertising what the shelf refused to promise.

The rule the fix installs is one sentence — the grid is the whole
vocabulary of this form, so an id it cannot SHOW is an id it must never
WRITE — and it belongs at every writer, because the seed was not the only
way in: a saved template and an OPENSWARM candidate both pour their own
`tools` array into the same state, and the candidate path drops elevation
on load while keeping the array.

Run: python3 scripts/test_the_hire_form_writes_only_what_it_shows.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('the hire form writes only what it shows')
    if not shutil.which('node'):
        print('SKIP — node not on PATH')
        return 0

    hire = (ROOT / 'modals' / 'hire.jsx').read_text(encoding='utf-8')
    settings = (ROOT / 'modals' / 'settings.jsx').read_text(encoding='utf-8')
    h_bare = strip_comments(hire)

    # ── the seed that caused it ─────────────────────────────────────────
    check('the form no longer seeds a hidden id',
          "['web','files']" not in h_bare and "['web', 'files']" not in h_bare,
          'the seed is what put files on a card nobody ticked')
    check('there is one choke point, and it is on the read',
          'const tools = formToolIds(toolsPicked);' in h_bare,
          'every consumer goes through `tools`, so filtering here filters everywhere')
    # The picked state is allowed exactly two mentions: the destructure that
    # creates it and the filter that launders it. A third is a consumer
    # reading round the choke point, which is the whole failure mode.
    check('…and nothing reads round it',
          h_bare.count('toolsPicked') == 2,
          [l.strip() for l in h_bare.splitlines() if 'toolsPicked' in l])
    check('the array handed to onHire is the filtered one',
          re.search(r'^\s*tools, model, temperature: temp,', h_bare, re.M) is not None,
          'onHire must not be given the picked state')
    check('the rule is stated where it is enforced, not restated per caller',
          h_bare.count('const formToolIds') == 1,
          'one vocabulary, one place')

    # ── the door that is genuinely elsewhere is still elsewhere ─────────
    check('files and code are still granted by the elevation switch, not a box',
          "GRANTED_ELSEWHERE_TOOL_IDS = new Set(['code', 'files'])" in settings,
          'if this set changes, the hidden-id rule changes with it')
    check('the elevated presets still carry their real ids',
          all(re.search(r"tools: \[[^\]]*'code'[^\]]*\][^\n]*elevated: true", ln)
              for ln in h_bare.splitlines() if "'code'" in ln and 'tools:' in ln),
          'filtering must not reach the detected-hire path, where they are earned')

    # ── drive the real filter against the real catalog ──────────────────
    m = re.search(r'const formToolIds = \(ids\) => \{.*?\n\};', h_bare, re.S)
    check('formToolIds lifts', bool(m))
    if not m:
        print('FAIL')
        return 1
    cat = re.search(r'const NEVER_WIRED_TOOL_IDS[^\n]*\n\s*'
                    r'const GRANTED_ELSEWHERE_TOOL_IDS[^\n]*\n\s*'
                    r'const visibleToolsCatalog = \(\) =>(?:[^\n]*\n)+?[^\n]*;',
                    strip_comments(settings))
    check('the visible catalog lifts', bool(cat))
    if not cat:
        print('FAIL')
        return 1

    js = ('const CATALOG = ' + json.dumps(cat.group(0)) + ';\n'
          + 'const FILTER = ' + json.dumps(m.group(0)) + ';\n'
          + r'''
/* The real TOOLS_CATALOG shape, and the real money gate the catalog reads. */
const HQ = { TOOLS_CATALOG: [
  { id: 'web',    label: 'Web Search' },
  { id: 'vault',  label: 'Vault Notes' },
  { id: 'img',    label: 'Image Gen' },
  { id: 'code',   label: 'Code Exec' },
  { id: 'files',  label: 'File Access' },
  { id: 'wallet', label: 'Wallet' },
  { id: 'email',  label: 'Email' },
  { id: 'cal',    label: 'Calendar' },
  { id: 'db',     label: 'Database' },
  { id: 'slack',  label: 'Slack' },
]};
let money = false;
const window = { hqMoneyOn: () => money };

const mod = new Function('HQ', 'window', CATALOG + FILTER
  + ' return { formToolIds, visibleToolsCatalog };')(HQ, window);
const { formToolIds, visibleToolsCatalog } = mod;

const shown = () => visibleToolsCatalog().map(t => t.id);

/* The measured seed, the two template paths, and a card the boss ticked. */
const out = {
  shownIds: shown(),
  measuredSeed: formToolIds(['web', 'files']),
  everythingUnticked: formToolIds([]),
  savedTemplate: formToolIds(['web', 'files', 'code']),
  candidate: formToolIds(['vault', 'files']),
  neverWired: formToolIds(['email', 'cal', 'db', 'slack']),
  realTicks: formToolIds(['web', 'vault', 'img']),
  junk: formToolIds(['shell', 'browser', '']),
  nullSafe: formToolIds(null),
};
/* The wallet box comes and goes with the money module: a tick taken while
   it was on must not survive into a hire made after it went off. */
money = true;
out.walletOn = formToolIds(['web', 'wallet']);
money = false;
out.walletOff = formToolIds(['web', 'wallet']);
console.log(JSON.stringify(out));
''')
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('the lifted filter runs', False, p.stderr.strip()[:400])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('the grid shows neither files nor code',
          'files' not in r['shownIds'] and 'code' not in r['shownIds'],
          r['shownIds'])
    check('the measured seed can no longer carry files through',
          r['measuredSeed'] == ['web'], r['measuredSeed'])
    check('a hire with every box unticked holds nothing at all',
          r['everythingUnticked'] == [], r['everythingUnticked'])
    check('a saved template cannot reintroduce the hidden pair',
          r['savedTemplate'] == ['web'], r['savedTemplate'])
    check('nor can a candidate whose elevation was dropped on load',
          r['candidate'] == ['vault'], r['candidate'])
    check('ids no box has ever shown are dropped too',
          r['neverWired'] == [] and r['junk'] == [],
          [r['neverWired'], r['junk']])
    check('what the boss actually ticked survives untouched',
          r['realTicks'] == ['web', 'vault', 'img'], r['realTicks'])
    check('a wallet tick is kept while the money module is on',
          r['walletOn'] == ['web', 'wallet'], r['walletOn'])
    check('…and does not outlive the box that granted it',
          r['walletOff'] == ['web'], r['walletOff'])
    check('a missing array is empty, not a crash', r['nullSafe'] == [], r['nullSafe'])

    if FAILS:
        print(f'FAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS))
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
