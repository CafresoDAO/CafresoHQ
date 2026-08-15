#!/usr/bin/env python3
"""A sentence introducing work was enough to call the task done.

The office already gets the hard half right. A reply that is nothing but
tool markers strips to the empty string, and every surface reports it
honestly: SNAG, "came back with nothing", no XP, the card left in `doing`
with a reason.

One surviving line flipped all of it. Measured 2026-08-15 against a canned
brain returning exactly:

    Here is what I did:

    [VAULT_NEW: Research/colours.md]
    [MEMORY_WRITE: decisions/colours.md]

Both markers are stripped as stray — the runtime never acted on them — and
`cleanBuf` came out as the string "Here is what I did:". Non-empty, so
`produced` was true, and the sheet that landed in the cabinet read:

    # Primary colours
    *Delivered by Nova · 2026-08-15*
    ---
    Here is what I did:
    ---
    **Working**
    - Nothing opened, saved or looked up for this one.

A promise with nothing behind it, and eight lines below, the office's own
record contradicting it. Two true records of one run, disagreeing.

#51 made six surfaces read one boolean instead of certifying from a fact
that meant "there is nothing here". This is the boolean itself: the
derivation was `!!cleanBuf.trim()`, which measures LENGTH. `hasSubstance`
asks about content.

Run: python3 scripts/test_a_lead_in_is_not_the_work.py
"""
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
ART = (ROOT / 'app' / 'artifacts.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """The fix quotes the measured reply and the filed sheet in comments, so
    a bare search would find its own evidence."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def pure_source():
    """The real artifacts.jsx, lifted the way test_artifacts.py lifts it, so
    this measures the shipped function and not a restatement of it."""
    spec = importlib.util.spec_from_file_location(
        'ta', str(ROOT / 'scripts' / 'test_artifacts.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.pure_source()


def main():
    print('a lead-in is not the work')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    app = strip_comments(APP)

    # ── 1. one question, asked once ─────────────────────────────────────
    #
    # The point of #51 was that three decisions read one fact. If the fix for
    # #80 corrects the derivation in one place and leaves the other two
    # deriving it themselves, the office is back to two honest surfaces out
    # of three — the exact shape of #78 and #79, one layer up.
    check('the run asks whether anything has substance, not whether the '
          'string is long',
          re.search(r'const produced = hasSubstance\(cleanBuf\);', app),
          '— !!cleanBuf.trim() is true for "Here is what I did:"')
    check('...and nothing in the run re-derives that fact',
          not re.search(r'if \(cleanBuf\.trim\(\)\)', app),
          [re.findall(r'.*if \(cleanBuf\.trim\(\)\).*', app),
           '— the filing and the journal must read the answer'])
    check('the cabinet asks the same question',
          re.search(r'if \(!hasSubstance\(body\)\) return null;', ART),
          '— a sheet whose body is a promise is the empty run, filed')
    # Same predicate on the sibling journal gates. Leaving those on .trim()
    # would put a lead-in into a coworker's history while the task it came
    # from was correctly recorded as having produced nothing.
    check('the chat and dispatch journals ask it too',
          len(re.findall(r'if \(hasSubstance\(cleanBuf\)\) appendJournal\(', app)) >= 2,
          '— one predicate, every place the office asks "is there anything '
          'here"')

    # ── 2. the predicate itself, run for real ───────────────────────────
    js = pure_source() + r'''
const CASES = [
  // [label, text, expected]
  ['the measured reply, markers stripped',  'Here is what I did:',            false],
  ['a lead-in with a heading over it',      '# Summary\n\nWhat I did:',       false],
  ['a bare heading',                        '# Primary colours',              false],
  ['two lead-ins and nothing else',         'Here is what I did:\nSummary:',  false],
  ['empty',                                 '',                               false],
  ['whitespace only',                       '   \n\n  ',                      false],
  // Everything below must survive. A guard that eats real deliveries is a
  // worse defect than the one it replaces — #51 said the same about a card
  // parked with no reason.
  ['a real answer',                         'Red, yellow and blue.',          true],
  ['a lead-in WITH its content',            'Here is what I did:\nWrote the page.', true],
  ['a heading with a body',                 '# Colours\n\nRed and blue.',     true],
  ['a colon that is not at the end',        'Status: everything is filed.',   true],
  ['one word',                              'Done.',                          true],
  ['a bulleted list under a lead-in',       'What I did:\n- wrote the page',  true],
];
const out = {};
for (const [label, text, want] of CASES) out[label] = [hasSubstance(text), want];
console.log(JSON.stringify(out));
'''
    p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
    if p.returncode != 0:
        check('the predicate harness runs', False, p.stderr.strip()[:400])
    else:
        for label, (got, want) in json.loads(p.stdout).items():
            check('%s → %s' % (label, 'substance' if want else 'nothing'),
                  got == want, 'got %s' % got)

    # ── 3. and the sheet the boss opens ─────────────────────────────────
    #
    # The predicate could be right and the caller still file. Build the real
    # delivery for the measured reply and require that nothing is produced,
    # while a genuine answer to the same task still files.
    js2 = pure_source() + r'''
const task = {title: 'Primary colours', starter: null};
const agent = {name: 'Nova'};
const promise = buildDelivery(task, agent, 'Here is what I did:', []);
const real = buildDelivery(task, agent, 'Red, yellow and blue.', []);
console.log(JSON.stringify({
  promiseFiled: promise !== null,
  realFiled:    real !== null,
  // The one that DOES file must still carry the answer and the record.
  realBody:     !!(real && real.content.includes('Red, yellow and blue.')),
  realRecord:   !!(real && real.content.includes('Nothing opened, saved or looked up')),
}));
'''
    p2 = subprocess.run(['node', '-e', js2], capture_output=True, text=True)
    if p2.returncode != 0:
        check('the delivery harness runs', False, p2.stderr.strip()[:400])
    else:
        R = json.loads(p2.stdout)
        check('no sheet is filed for a promise',
              R['promiseFiled'] is False,
              '— the filed sheet put "Here is what I did:" above the office\'s '
              'own "Nothing opened, saved or looked up for this one."')
        check('a real answer still files', R['realFiled'], R)
        check('...with the answer in it', R['realBody'], R)
        check('...and the working record under it', R['realRecord'], R)

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
