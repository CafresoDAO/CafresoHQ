#!/usr/bin/env python3
"""A second terminal tab must not be given the first tab's number.

views/terminal.jsx's ProjectTerminal opens every project — and the standalone
Terminal view — with ONE session already on the bar:

    [{ id: 's1', cli: 'hermes', sessionId: _uuid() }]

That seed record carried no `n`. `getLabel` names a lone tab plainly
("Hermes") and only starts numbering once a second tab of the same CLI
exists, at which point a session with no `n` falls back to its array
position + 1 — so the seed tab is number one.

`addSession` did not know that. Its ordinal was

    prev.filter(s => s.cli === cli).reduce((m, s) => Math.max(m, s.n || 0), 0) + 1

which counts only EXPLICIT ordinals, and the seed tab has none. So the
second Hermes tab was minted with n = 0 + 1 = 1 while the first tab was
already showing #1 from the index fallback, and the bar read:

    ☼ Hermes #1   ☼ Hermes #1

Two tabs, two separate PTYs, one name. Add a third and it read #1 · #1 · #2.
Nothing else on the row distinguishes them, and × closes by id, so the boss
picking "the other Hermes" had to guess.

This is a one-item seam by construction: at zero tabs there is nothing to
name, at one tab the label is bare "Hermes" and the bug is invisible, and it
only appears the moment a second tab exists.

Fix: seed the reduce with `same.length` — a session with no ordinal still
occupies one — and stamp `n: 1` on the seed record itself so a fresh floor
is exact rather than merely non-colliding.

Parts 1–3 drive the REAL addSession/getLabel/_nextSessionId, lifted verbatim
from views/terminal.jsx, under node across 0, 1 and 2+ tabs. Part 4 measures
the source so the seeded reduce cannot quietly go back to 0.

Run: python3 scripts/test_two_terminal_tabs_are_never_both_called_number_one.py
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
TERM = ROOT / 'views' / 'terminal.jsx'

FAILS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    print(f'  {"ok  " if cond else "FAIL"}  {label}'
          + (f' — {detail}' if detail and not cond else ''))
    if not cond:
        FAILS.append(label)


def brace_lift(src: str, opener: str) -> str:
    """The whole block starting at `opener`, by balancing braces."""
    i = src.index(opener)
    j = src.index('{', i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


def strip_comments(s: str) -> str:
    """Block and line comments out, so this file's own prose about the bad
    pattern can never be what the source scan below matches."""
    s = re.sub(r'/\*.*?\*/', ' ', s, flags=re.S)
    return re.sub(r'(?m)//.*$', '', s)


print('two terminal tabs are never both called number one')

src = TERM.read_text(encoding='utf-8')

# ── the real functions, lifted verbatim ─────────────────────────────────
add_session = brace_lift(src, 'const addSession = (cli) =>')
get_label = brace_lift(src, 'const getLabel = (session) =>')
next_id = brace_lift(src, 'const _nextSessionId = (existing) =>')
cli_name = re.search(r'const cliName = \(cli\) => [^\n]+', src).group(0)

# The seed session record the initialiser mints, lifted so a change to it
# (adding or dropping `n`) is exercised here rather than restated.
seed = re.search(
    r'useStoredV\(sessKey, \(\) => \{\s*return \[(\{[^\]]*?\})\];',
    src, flags=re.S)
if seed is None:
    check('the seed session literal is still findable', False,
          'useStoredV(sessKey, …) shape changed')
    print('\nFAILED')
    sys.exit(1)
seed_literal = seed.group(1)

if not shutil.which('node'):
    print('  SKIP  node not on PATH — running the source check only')
    result = None
else:
    js = f"""
let sessions = [];
const setSessions = (f) => {{ sessions = typeof f === 'function' ? f(sessions) : f; }};
const setActiveId = () => {{}};
const setAddMenuOpen = () => {{}};
let _n = 0;
const _uuid = () => 'uuid-' + (++_n);

{next_id}
{cli_name}
{add_session}
{get_label}

const labels = () => sessions.map(getLabel);

// 0 tabs — nothing to name, and nothing to crash on.
sessions = [];
const zero = labels();

// 1 tab — the office's own seed record, verbatim from the initialiser.
sessions = [{seed_literal}];
const one = labels();

// 2 tabs — the boss opens a second Hermes from the + menu.
addSession('hermes');
const two = labels();

// 3 tabs, and a second CLI alongside them.
addSession('hermes');
const three = labels();
addSession('claude');
addSession('claude');
const mixed = labels();

// A floor persisted BEFORE `n` existed: two unnumbered Hermes records.
sessions = [
  {{ id: 's1', cli: 'hermes', sessionId: 'a' }},
  {{ id: 's2', cli: 'hermes', sessionId: 'b' }},
];
addSession('hermes');
const legacy = labels();

// Closing a middle tab must not renumber the survivors.
sessions = [];
sessions = [{seed_literal}];
addSession('hermes');
addSession('hermes');
const beforeClose = labels();
sessions = sessions.filter(s => s !== sessions[1]);
const afterClose = labels();

console.log(JSON.stringify({{
  zero, one, two, three, mixed, legacy, beforeClose, afterClose,
}}));
"""
    with tempfile.NamedTemporaryFile('w', suffix='.mjs', delete=False) as fh:
        fh.write(js)
        path = fh.name
    proc = subprocess.run(['node', path], capture_output=True, text=True)
    pathlib.Path(path).unlink(missing_ok=True)
    if proc.returncode != 0:
        check('the lifted terminal helpers run under node', False,
              proc.stderr.strip()[:400])
        print('\nFAILED')
        sys.exit(1)
    result = json.loads(proc.stdout.strip().splitlines()[-1])

if result is not None:
    zero = result['zero']
    one = result['one']
    two = result['two']
    three = result['three']
    mixed = result['mixed']
    legacy = result['legacy']

    # ── 0 items ─────────────────────────────────────────────────────────
    check('0 tabs name nothing and raise nothing', zero == [], repr(zero))

    # ── 1 item — the seam's quiet half ──────────────────────────────────
    check('1 tab is named plainly, with no number at all',
          one == ['Hermes'], repr(one))

    # ── 2 items — the point ─────────────────────────────────────────────
    check('2 tabs get 2 different names',
          len(set(two)) == 2, repr(two))
    check('the second Hermes tab is not also called #1',
          two == ['Hermes #1', 'Hermes #2'], repr(two))

    # ── beyond ──────────────────────────────────────────────────────────
    check('3 tabs get 3 different names',
          len(set(three)) == 3, repr(three))
    check('a second CLI numbers from its own one',
          mixed[-2:] == ['Claude #1', 'Claude #2'], repr(mixed))
    check('a floor persisted before ordinals existed still names 3 tabs apart',
          len(set(legacy)) == 3, repr(legacy))

    # ── the invariant the original comment claimed ──────────────────────
    check('closing a middle tab does not renumber the survivors',
          result['afterClose'] == [result['beforeClose'][0],
                                   result['beforeClose'][2]],
          f"{result['beforeClose']} -> {result['afterClose']}")

# ── 4: the source, comments stripped ────────────────────────────────────
bare = strip_comments(src)
check('the new-tab ordinal is seeded from the seats already taken, not 0',
      re.search(r'reduce\(\(m, s\) => Math\.max\(m, s\.n \|\| 0\), same\.length\)', bare)
      is not None,
      'addSession still seeds its reduce with 0')
check('the seed session carries an ordinal of its own',
      re.search(r"id: 's1', cli: 'hermes', sessionId: _uuid\(\), n: 1", bare)
      is not None,
      "the { id: 's1' … } seed record dropped its n")

print()
if FAILS:
    print(f'FAILED — {len(FAILS)} check(s): ' + '; '.join(FAILS))
    sys.exit(1)
print('PASS')
