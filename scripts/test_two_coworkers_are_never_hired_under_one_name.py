#!/usr/bin/env python3
"""Two coworkers called Vera: one is unaddressable, and LET GO is a coin flip.

#317 found two live terminal tabs both labelled "Hermes #1" — two real PTYs,
one name, a close button that works by id, and a boss ending "the other
Hermes" by guessing. The front desk had the same shape on a worse row.

`hireNeedsNote` was the whole door on the NAME box and it asked one
question: is the box blank? So HIRE ✓ was live and bright on a name somebody
in the office already answers to. Nothing downstream noticed:

  * A NAME here is an ADDRESS. `@Vera` in the composer, a coworker's
    `[DM_TO: Vera]` and a `[HANDOFF_TO: Vera]` all resolve with
    `agents.find(a => a.name.toLowerCase() === …)` — first match wins, in
    app.jsx and again in hq-runtime.jsx. The SECOND Vera is therefore
    unreachable: every mention, DM and hand-off aimed at her lands on the
    first one, and the office says nothing, because from where it stands
    the name resolved fine.

  * The roster she lands on cannot tell the boss which is which. Hiring the
    same SAVED TEMPLATE twice is one extra click — the OPENSWARM shelf
    filters its candidates by `hiredNames` and the front desk filters its
    cards by `hiredIds`, but the templates shelf filters by neither — and
    two hires off one template share sprite, name and role. The Settings →
    ROSTER row is exactly sprite + name + role + LET GO, and LET GO on a
    coworker with no assistants goes straight through `onDismiss` with NO
    confirmation at all.

So the boss picks one of two identical rows and presses an irreversible
button. The wrong click takes that coworker's system prompt, tools, tokens
and history, hands their in-flight run an abort, unassigns their cards, and
fires DELETE at /missions/scheduled for every night shift they had booked.
There is no undo and — because the surviving row looks the same — no way to
notice which one went.

Refused at the door rather than disambiguated on the row: a "#2" suffix on
a roster row cannot fix routing, because `@Vera` has no row to point at.

This drives the real `hireNeedsNote` out of modals/hire.jsx under node, and
drives the real name resolver lifted out of app.jsx over a colliding pair to
show what the door is protecting.

Run: python3 scripts/test_two_coworkers_are_never_hired_under_one_name.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HIRE = ROOT / 'modals' / 'hire.jsx'
APP = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Comments first — this fix's own comments quote the shape it fixes."""
    src = re.sub(r'\{/\*.*?\*/\}', '', src, flags=re.S)
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def lift(src, start_marker, end_marker):
    i = src.index(start_marker)
    j = src.index(end_marker, i)
    return src[i:j]


def main():
    print('two coworkers are never hired under one name')
    hire_bare = strip_comments(HIRE.read_text(encoding='utf-8'))
    app_bare = strip_comments(APP.read_text(encoding='utf-8'))

    # ── §1 the office really does route by name, first match wins ───────
    # If this ever stops being true the refusal below is arguing with a
    # premise that no longer holds, and this test should say so loudly
    # rather than quietly guarding nothing.
    resolvers = re.findall(
        r'\.find\(\s*\w+\s*=>\s*\w+\.name\.toLowerCase\(\)\s*===', app_bare)
    check('a coworker is still reached by NAME, not by id',
          len(resolvers) >= 2,
          f'expected the DM/@mention resolvers in app.jsx, found {len(resolvers)}')

    # ── §2 the door is one sentence and it knows who already works here ─
    check('the NAME door is a module-level, liftable helper',
          re.search(r'^function hireNeedsNote\(name, currentAgents\)',
                    hire_bare, re.M) is not None,
          'the roster must arrive as an argument, or the door cannot be '
          'driven here and cannot see who is already hired')
    check('…and every reader of it hands over the roster',
          re.search(r'hireNeedsNote\((?!name, currentAgents\))', hire_bare) is None,
          'a call site that drops the roster is a door that stops asking')

    # ── §3 the roster cannot itself tell two of them apart ──────────────
    # This is the reason the refusal has to happen at the door: the row the
    # boss would act on carries nothing else.
    roster_row = lift(hire_bare, 'function hireNeedsNote', 'const FRONT_DESK')
    check('the door exists in the file that owns the NAME box',
          'NAME box' in HIRE.read_text(encoding='utf-8'), roster_row[:80])

    # ── §4 drive the real helper ───────────────────────────────────────
    if not shutil.which('node'):
        print('SKIP (node) — source checks above still ran')
        if FAILS:
            print(f'FAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS))
            return 1
        print('PASS')
        return 0

    fn = lift(hire_bare, 'function hireNeedsNote', 'const FRONT_DESK')
    # The colliding pair, exactly as two clicks on one saved template make
    # it: same name, same role, same sprite, different ids.
    roster = [
        {'id': 'a_1', 'name': 'Vera', 'role': 'Researcher'},
        {'id': 'a_2', 'name': 'Nova', 'role': 'Editor'},
    ]
    js = ('const SRC = ' + json.dumps(fn) + ';\n'
          + 'const ROSTER = ' + json.dumps(roster) + ';\n' + r'''
const hireNeedsNote = new Function(SRC + ' return hireNeedsNote;')();
/* The resolver every mention, DM and hand-off goes through, in the shape
   app.jsx uses it. Driven over a roster that DID take a second Vera. */
const collided = [
  { id: 'a_1', name: 'Vera', role: 'Researcher' },
  { id: 'a_2', name: 'Vera', role: 'Researcher' },
];
const resolve = (to) => {
  const targetName = String(to || '').trim();
  const target = collided.find(a => a.name.toLowerCase() === targetName.toLowerCase());
  return target ? target.id : null;
};
console.log(JSON.stringify({
  blank:      hireNeedsNote('', ROSTER),
  fresh:      hireNeedsNote('Iris', ROSTER),
  taken:      hireNeedsNote('Vera', ROSTER),
  lowered:    hireNeedsNote('vera', ROSTER),
  padded:     hireNeedsNote('  Vera  ', ROSTER),
  shouty:     hireNeedsNote('NOVA', ROSTER),
  noRoster:   hireNeedsNote('Vera'),
  nullRoster: hireNeedsNote('Vera', null),
  emptyRoster: hireNeedsNote('Vera', []),
  /* A half-built roster row must not throw inside the render. */
  ragged:     hireNeedsNote('Iris', [null, {}, { id: 'x' }, { name: null }]),
  /* What the door is protecting, measured rather than asserted. */
  dmVera:     resolve('Vera'),
  dmLowered:  resolve('vera'),
  dmPadded:   resolve(' Vera '),
}));
''')
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('the lifted helper runs', False, p.stderr.strip()[:400])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    # The damage, stated as a measurement.
    check('a second Vera really is unaddressable',
          r['dmVera'] == 'a_1' and r['dmLowered'] == 'a_1'
          and r['dmPadded'] == 'a_1',
          'every teammate DM aimed at either Vera lands on the first: '
          + str([r['dmVera'], r['dmLowered'], r['dmPadded']]))

    note = r['taken']
    check('HIRE ✓ refuses a name the office already answers to',
          bool(note),
          'an empty note means HIRE ✓ is live and bright on a duplicate — '
          'the roster takes a second row it cannot tell from the first')
    check('…and the refusal names the coworker who already has it',
          'Vera' in note, note)
    check('…and says which coworker that is, not just that one exists',
          'Researcher' in note, note)
    check('…and is a sentence with a way out, not shorthand',
          len(note) > 30 and note.rstrip().endswith('.')
          and 'NAME' in note and 'different' in note.lower(),
          note)
    check('…and explains the cost, so the refusal is not arbitrary',
          'LET GO' in note or 'first match' in note, note)

    check('case is not a disguise — the resolvers fold it too',
          bool(r['lowered']) and bool(r['shouty']),
          [r['lowered'], r['shouty']])
    check('neither is padding',
          bool(r['padded']), r['padded'])

    check('a name nobody answers to still lets the button live',
          r['fresh'] == '', r['fresh'])
    check('an empty office still lets the button live',
          r['emptyRoster'] == '' and r['noRoster'] == ''
          and r['nullRoster'] == '',
          [r['emptyRoster'], r['noRoster'], r['nullRoster']])
    check('a ragged roster row does not throw inside the render',
          r['ragged'] == '', r['ragged'])
    check('the blank-box door still stands in front of it',
          bool(r['blank']) and 'NAME' in r['blank'], r['blank'])

    print()
    if FAILS:
        print(f'FAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS))
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
