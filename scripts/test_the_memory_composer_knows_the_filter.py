#!/usr/bin/env python3
"""A shelf that tells you to add one below has to file it where you are standing.

Reproduced 2026-09-03 on a live office (127.0.0.1:8892) holding one NOTE and
two PREF entries:

    filter PROJECT  ·  composer dropdown PREF (left over from an earlier add)
    shelf says      "No entries tagged PROJECT. Pick another tag above,
                     or add one below."
    type            "Apollo ships in Q4"  →  + REMEMBER

    result          the entry is filed as PREF, and the shelf silently
                    snaps back to ALL

Two separate wrongs from one root. The composer's `tag` was independent of
`filter`, so following the page's own instruction produced a MIS-TAGGED
entry — the dropdown's leftover value, not the tag the boss was standing in.
Then `submit`'s #154 mitigation noticed the new entry would be hidden by the
filter and cleared the filter to reveal it — correct in effect, but it threw
away the shelf the boss had set and gave no reason.

This is the #154 / #157 shape again: a surface with a filter and a create
control, where the create control does not know the filter exists. The
mitigation had been applied to the CONSEQUENCE (hide) and not to the CAUSE
(the control).

The fix makes the composer follow the filter, so the ordinary path files the
right tag and the reset never fires; and when the boss deliberately overrides
the dropdown, the reset says which filter it dropped and what was filed.

What this file holds:

  1. `submit` and the tag-row handler, LIFTED and EXECUTED under Node over
     scenarios including the measured one
  2. the invariant that survived from #154 — the entry the boss just made is
     always on screen afterwards — plus its new companion: the filter changes
     ONLY when the boss is told
  3. that the page says all of this out loud: the empty state names the tag
     it will file under, and the reset renders its disclosure

Run: python3 scripts/test_the_memory_composer_knows_the_filter.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / 'views' / 'core.jsx'
FAILS = []

TAGS = ['NOTE', 'PREF', 'PROJECT', 'PEOPLE', 'RULE', 'TONE']


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def component(src, name):
    m = re.search(r'^function %s\(' % re.escape(name), src, re.M)
    if not m:
        raise SystemExit('no `function %s(` in views/core.jsx' % name)
    nxt = src.find('\nfunction ', m.end())
    return src[m.start():nxt if nxt != -1 else len(src)]


def balanced(src, start):
    """The expression beginning at `start`, to its matching close."""
    depth = 0
    for j in range(start, len(src)):
        c = src[j]
        if c in '({[':
            depth += 1
        elif c in ')}]':
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
    raise SystemExit('unbalanced expression at %d' % start)


def lift(src, name, where):
    """`const <name> = …;` to its depth-0 semicolon. Located by NAME — a
    locator pinned to the body reports a rename as a regression and hands
    back an empty slice that satisfies any negative check (#159)."""
    m = re.search(r'\bconst %s = ' % re.escape(name), src)
    if not m:
        raise SystemExit('no `const %s = ` in %s' % (name, where))
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


def pill_handler(view):
    """The tag-row button's onClick, anchored on the pill's own className so
    it cannot pick up one of the dozen other onClicks in this component."""
    a = view.find("filter===t?'primary':'secondary'")
    if a == -1:
        raise SystemExit('the memory tag pills are no longer keyed on '
                         '`filter===t` — relocate this test')
    b = view.find('onClick=', a)
    if b == -1:
        raise SystemExit('the tag pill has no onClick')
    return balanced(view, view.index('{', b))[1:-1]


def main():
    print('The memory composer knows the filter')

    core = CORE.read_text(encoding='utf-8')
    view = component(core, 'MemoryPage')
    check('the MemoryPage component is findable', bool(view.strip()),
          'every check below would run against an empty slice')

    submit = lift(view, 'submit', 'MemoryPage')
    filtered = lift(view, 'filtered', 'MemoryPage')
    handler = pill_handler(view)

    # --- §1: driven ------------------------------------------------------
    # (label, ops, expected tag of the new entry, expected filter,
    #  expected dropped)
    SEED = [{'id': 'a', 'tag': 'NOTE', 'text': 'Invoices go out on the 1st'},
            {'id': 'b', 'tag': 'PREF', 'text': 'Keep replies short'}]

    CASES = [
        ('unfiltered, the composer is left alone',
         [['add', 'Apollo ships in Q4']], 'NOTE', 'ALL', None),

        ('THE MEASURED ONE: stand in PROJECT and follow the instruction',
         [['pick', 'PROJECT'], ['add', 'Apollo ships in Q4']],
         'PROJECT', 'PROJECT', None),

        ('...and the dropdown says so before the boss commits',
         [['pick', 'PROJECT']], None, 'PROJECT', None),

        ('a deliberate override still files what the boss chose',
         [['pick', 'PROJECT'], ['kind', 'RULE'], ['add', 'No weekend email']],
         'RULE', 'ALL', {'from': 'PROJECT', 'as': 'RULE'}),

        ('...and picking any tag afterwards clears the notice',
         [['pick', 'PROJECT'], ['kind', 'RULE'], ['add', 'x'],
          ['pick', 'NOTE']], 'RULE', 'NOTE', None),

        ('ALL is not a tag, so it leaves the composer where it was',
         [['pick', 'PEOPLE'], ['pick', 'ALL'], ['add', 'Dana runs ops']],
         'PEOPLE', 'ALL', None),

        ('re-filtering to the tag you are already on changes nothing',
         [['pick', 'PREF'], ['pick', 'PREF'], ['add', 'Short replies']],
         'PREF', 'PREF', None),

        ('an empty box adds nothing at all',
         [['pick', 'PROJECT'], ['add', '   ']], None, 'PROJECT', None),
    ]
    # Every tag has to work, not just the one that was measured.
    for t in TAGS:
        CASES.append(('standing in %s files a %s' % (t, t),
                      [['pick', t], ['add', 'entry for ' + t]], t, t, None))

    harness = '\n'.join([
        'const SEED = %s;' % json.dumps(SEED),
        'const OUT = [];',
        'for (const [label, ops] of CASES) {',
        '  let memory = SEED.map(m => ({...m}));',
        "  let filter = 'ALL', tag = 'NOTE', text = '', dropped = null;",
        '  const setFilter = v => filter = v;',
        '  const setTag = v => tag = v;',
        '  const setText = v => text = v;',
        '  const setDropped = v => dropped = v;',
        '  const onAdd = e => memory.unshift(e);',
        '  ' + submit,
        # The lifted attribute is the arrow ITSELF, closing over the pill's
        # `t`; it has to be called, not used as a body. A body-shaped wrapper
        # would silently make every `pick` a no-op and quietly turn this whole
        # section into a test of the unfixed code.
        '  const pick = (t) => (%s)();' % handler,
        # #154 asks whether the boss can see the entry THE MOMENT they make
        # it. Measuring at the end of the script instead would let a later
        # deliberate re-filter read as the app hiding their work.
        '  const shelf = () => { %s return filtered; };' % filtered,
        '  let added = null, visible = null;',
        '  for (const [kind, arg] of ops) {',
        "    if (kind === 'pick') pick(arg);",
        "    else if (kind === 'kind') setTag(arg);",
        '    else {',
        '      const before = memory.length;',
        '      text = arg; submit();',
        '      added = memory.length > before ? memory[0] : null;',
        '      if (added) visible = shelf().some(m => m.id === added.id);',
        '    }',
        '  }',
        '  OUT.push([label, {',
        '    addedTag: added && added.tag, filter, tag, dropped,',
        '    total: memory.length, visible,',
        '  }]);',
        '}',
        'console.log(JSON.stringify(OUT));',
    ])
    harness = 'const CASES = %s;\n' % json.dumps(
        [[c[0], c[1]] for c in CASES]) + harness

    proc = subprocess.run(['node', '--input-type=module', '-e', harness],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr.strip()[:2000])
        raise SystemExit('the lifted submit/handler did not run under node')
    got = json.loads(proc.stdout.strip().splitlines()[-1])

    for case, (_l, res) in zip(CASES, got):
        label, ops, want_tag, want_filter, want_dropped = case
        if want_tag is not None:
            check('%s — the tag it is filed under' % label[:60],
                  res['addedTag'] == want_tag,
                  'filed as %r, expected %r' % (res['addedTag'], want_tag))
        else:
            check('%s — nothing was filed' % label[:60],
                  res['addedTag'] is None and res['total'] == len(SEED),
                  'the shelf grew to %d' % res['total'])
        check('%s — the shelf the boss is left looking at' % label[:60],
              res['filter'] == want_filter,
              'filter is %r, expected %r' % (res['filter'], want_filter))
        check('%s — whether the boss was told' % label[:60],
              res['dropped'] == want_dropped,
              'dropped is %r, expected %r' % (res['dropped'], want_dropped))

    # --- §2: the two invariants, over every case -------------------------
    for case, (_l, res) in zip(CASES, got):
        if res['visible'] is None:
            continue
        check('%s — #154 still holds: the boss can see what they just made'
              % case[0][:52], res['visible'] is True,
              'the entry was filed and then hidden behind the filter — the '
              'exact loop #154 closed on the Tasks board')
        check('%s — the filter moves only when the boss is told'
              % case[0][:52],
              (res['filter'] == 'ALL' and res['dropped'] is not None)
              or res['dropped'] is None,
              'filter=%r dropped=%r — one of these changed without the other'
              % (res['filter'], res['dropped']))

    # --- §3: the page says it out loud -----------------------------------
    check('the composer still follows the filter when a tag is picked',
          re.search(r'setFilter\(t\)', handler) is not None
          and re.search(r"t !== 'ALL'.*setTag\(t\)", handler) is not None,
          'views/core.jsx: the tag pill no longer points the composer at the '
          'filter, so `add one below` files the dropdown leftover again — '
          'handler is %r' % handler.strip()[:160])
    check('...and the dropdown is what shows it, so nothing is decided '
          'behind the boss',
          re.search(r'<select value=\{tag\}', view) is not None,
          'views/core.jsx: the composer select is no longer bound to `tag`; '
          'the filter would now be followed invisibly')
    check('the filtered-empty state names the tag it will file under',
          re.search(r'No entries tagged \{filter\}[^<]*filed as \{filter\}',
                    view) is not None,
          'views/core.jsx: the empty state tells the boss to `add one below` '
          'without saying where it lands — the sentence that was wrong')
    check('the reset renders a reason rather than silently moving the shelf',
          re.search(r'\{dropped\.as\}', view) is not None
          and re.search(r'\{dropped\.from\}', view) is not None,
          'views/core.jsx: nothing prints `dropped` — the branch can compute '
          'a disclosure that never reaches the screen (the #161 escape)')
    check('...and `dropped` starts empty, so an untouched shelf says nothing',
          re.search(r'const \[dropped, setDropped\] = useSV\(null\)', view)
          is not None,
          'views/core.jsx: `dropped` is not initialised to null')
    check('the reset cannot fire without setting it',
          all('setDropped' in seg for seg in
              re.findall(r'\{[^{}]*setFilter\(\'ALL\'\)[^{}]*\}', submit))
          and "setFilter('ALL')" in submit,
          'views/core.jsx submit(): a `setFilter(\'ALL\')` clears the shelf '
          'without recording why — %r' % submit.strip()[:200])

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
