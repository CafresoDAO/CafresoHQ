#!/usr/bin/env python3
"""Filter the Long-term Memory shelf to a tag it has nothing under, and the
page says:

    No entries tagged RULE. Pick another tag above, **or add one below.**

The composer below is a separate control with its own tag, defaulting to
NOTE, and nothing tied the two together. Measured live on a real office:
following that instruction bumped the header from **1 ENTRY** to **2
ENTRIES**, cleared the box, showed nothing, and left the same sentence on
screen. Follow it twice and you have stacked up entries you cannot see.

That is the exact loop #154 fixed on the Tasks board, on a different shelf.
The fix is the same rule `addVisible` uses there, and the Calendar highlight
effect before it: whichever filter would hide the thing the boss just made,
drop it — only that one, and only when it would actually hide it.

Run: python3 scripts/test_the_memory_shelf_shows_what_you_just_saved.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / 'views' / 'core.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def component(src, name):
    """One top-level component body, located by NAME — never by its parameter
    list, the locator that turned an added prop into a test CRASH once
    already (see test_calendar_task_row_opens_the_right_card)."""
    m = re.search(r'^function %s\(' % re.escape(name), src, re.M)
    if not m:
        raise SystemExit('no top-level `function %s(` in views/core.jsx' % name)
    j = src.find('\nfunction ', m.end())
    return src[m.start():] if j == -1 else src[m.start():j]


def lift(src, name):
    """One indented `const <name> = ...;` to its depth-0 semicolon. Parens,
    braces and brackets are all counted — these bodies hold object literals
    and arrow functions."""
    m = re.search(r'^[ \t]*const %s = ' % re.escape(name), src, re.M)
    if not m:
        raise SystemExit('no `const %s = ` in MemoryPage' % name)
    depth = 0
    for j in range(m.start(), len(src)):
        c = src[j]
        if c in '({[':
            depth += 1
        elif c in ')}]':
            depth -= 1
        elif c == ';' and depth == 0:
            return src[m.start():j + 1]
    raise SystemExit('unterminated `const %s`' % name)


# (label, filter before, composer tag, text, expected filter after,
#  whether the entry must be reachable in the view after)
CASES = [
    ('the measured case: shelf filtered to RULE, composer at NOTE — the '
     'filter that hid it is dropped',
     'RULE', 'NOTE', 'remember this', 'ALL', True),
    ('the entry matches the filter: the view is left exactly as the boss '
     'set it', 'NOTE', 'NOTE', 'remember this', 'NOTE', True),
    ('the shelf was already showing everything: nothing to drop',
     'ALL', 'RULE', 'remember this', 'ALL', True),
    ('a different mismatch, same rule', 'PEOPLE', 'TONE', 'remember this',
     'ALL', True),
    ('an empty box saves nothing and moves nothing',
     'RULE', 'NOTE', '   ', 'RULE', False),
]


def main():
    print('The memory shelf shows what you just saved')

    src = CORE.read_text(encoding='utf-8')
    page = component(src, 'MemoryPage')

    # --- §1: the real submit, driven ----------------------------------
    # Only the React bindings are stubbed. `onAdd` records, `setFilter`
    # records, `setText` records — "which filter did the save drop?" is
    # precisely the question, so nothing that answers it is re-implemented.
    harness = '\n'.join([
        'const OUT = [];',
        'for (const c of CASES) {',
        '  const [label, filter0, tag, text] = c;',
        '  let filter = filter0, cleared = false;',
        '  const added = [];',
        '  const setFilter = (v) => { filter = v; };',
        '  const setText = (v) => { cleared = (v === ""); };',
        '  const onAdd = (m) => { added.push(m); };',
        '  ' + lift(page, 'submit'),
        '  submit();',
        '  OUT.push([label, filter, added, cleared]);',
        '}',
        'console.log(JSON.stringify(OUT));',
    ])
    harness = 'const CASES = %s;\n' % json.dumps(
        [[c[0], c[1], c[2], c[3]] for c in CASES]) + harness

    proc = subprocess.run(['node', '--input-type=module', '-e', harness],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr.strip()[:2000])
        raise SystemExit('the lifted submit did not run under node')
    got = json.loads(proc.stdout.strip().splitlines()[-1])

    for case, (_label, filter_after, added, cleared) in zip(CASES, got):
        label, _f0, tag, text, want_filter, want_saved = case
        check(label, filter_after == want_filter,
              'filter ended at %r, expected %r' % (filter_after, want_filter))
        if want_saved:
            check('  ...and it was actually saved, tagged %s' % tag,
                  len(added) == 1 and added[0].get('tag') == tag
                  and added[0].get('text') == text.strip() and cleared,
                  'added=%r cleared=%r' % (added, cleared))
        else:
            check('  ...and nothing was saved', not added and not cleared,
                  'added=%r cleared=%r' % (added, cleared))

    # The whole point, stated once: after the save, the entry is on screen.
    # Re-derived from the REAL filter expression rather than restated, so a
    # change to how `filtered` works cannot leave this passing by accident.
    fexpr = lift(page, 'filtered')
    vis = '\n'.join([
        'const OUT = [];',
        'for (const c of CASES) {',
        '  const [label, filterAfter, tag, text] = c;',
        '  const filter = filterAfter;',
        '  const memory = [{ id: "m1", tag, text, date: 1 }];',
        '  ' + fexpr,
        '  OUT.push([label, filtered.length]);',
        '}',
        'console.log(JSON.stringify(OUT));',
    ])
    vis = 'const CASES = %s;\n' % json.dumps(
        [[c[0], c[4], c[2], c[3].strip()] for c in CASES if c[5]]) + vis
    vproc = subprocess.run(['node', '--input-type=module', '-e', vis],
                           capture_output=True, text=True)
    if vproc.returncode != 0:
        print(vproc.stderr.strip()[:2000])
        raise SystemExit('the lifted filter did not run under node')
    for label, n in json.loads(vproc.stdout.strip().splitlines()[-1]):
        check('the saved entry is visible on the shelf the save left behind '
              '— %s' % label[:48], n == 1,
              'the shelf shows %d rows for it' % n)

    # --- §2: the premise ----------------------------------------------
    # If this sentence stops inviting the boss to add one below, the rule
    # above is answering a question nobody is being asked any more.
    check('the filtered-empty state still says "or add one below"',
          'Pick another tag above, or add one below.' in page,
          'views/core.jsx: the instruction this fix makes true has changed')
    check('the composer tag is genuinely independent of the filter — which '
          'is why the save has to reconcile them',
          re.search(r"const \[tag, setTag\] = useSV\('NOTE'\);", page)
          is not None
          and re.search(r"const \[filter, setFilter\] = useSV\('ALL'\);", page)
          is not None,
          'views/core.jsx: MemoryPage state shape changed')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
