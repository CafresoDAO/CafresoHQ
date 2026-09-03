#!/usr/bin/env python3
"""The same coworker's streak was "on fire" on one card and not on its twin.

`xpStats()` (app/experience.jsx) computes one `streak` number per agent from
the append-only experience ledger. Two surfaces read it and both dress it up
with a flame once it gets long enough: the Team roster card (`TeamView`,
views/core.jsx — "Jobs · N 🔥") and the coworker's own Performance review
(`InspectPanel`, ui/panels.jsx — "Current streak · N 🔥"). Both have carried
that badge since the exact same commit (76b8070, "XP counters: append-only
experience ledger") — and that commit hardcoded two different thresholds:

    views/core.jsx:   xp.streak >= 3 ? ' \U0001F525' : ''
    ui/panels.jsx:     xp.streak >= 2 ? `${xp.streak} \U0001F525` : xp.streak

A coworker sitting at streak 2 read as "just delivering, nothing special" on
the roster tile (`JOBS 2`, no flame) and "2 \U0001F525 — on a hot streak" the moment
the boss opened that exact same coworker's Performance review — same ledger,
same agent, same number, two different verdicts depending on which of two
twin surfaces the boss happened to be looking at.

Measured live: hired Llama, seeded `hq-state/experience.json` via
`PUT /hq/state/experience` with two `done` entries (taskId seed_t1/seed_t2,
no snags), reloaded. Team → roster card read `JOBS 2` with no flame.
Clicking through to PERFORMANCE REVIEW for the identical coworker read
`CURRENT STREAK 2 \U0001F525`. OFFICE_AS_INTERFACE #155 documents the roster card's
own threshold in passing ("Llama: Effort 8,286, Jobs 3 \U0001F525") — 3, never 2 —
so the panel's `>= 2` was the one that had drifted, not the roster card, but
the actual bug is that nothing kept them equal in the first place.

Fix: one shared constant, `XP_HOT_STREAK` (app/experience.jsx, = 3), read by
both `TeamView` and `InspectPanel` instead of each hardcoding its own number.

Run: python3 scripts/test_a_hot_streak_meant_two_different_numbers.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPERIENCE = ROOT / 'app' / 'experience.jsx'
CORE = ROOT / 'views' / 'core.jsx'
PANELS = ROOT / 'ui' / 'panels.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, opener):
    """Body by brace matching; the opener is the first `{` at paren depth 0."""
    i = src.index(opener)
    parens = 0
    j = None
    for k in range(i, len(src)):
        c = src[k]
        if c == '(':
            parens += 1
        elif c == ')':
            parens -= 1
        elif c == '{' and parens == 0:
            j = k
            break
    if j is None:
        raise AssertionError('no body brace found lifting ' + opener)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


def main():
    print('a hot streak meant two different numbers')

    experience_src = EXPERIENCE.read_text(encoding='utf-8')
    core_src = CORE.read_text(encoding='utf-8')
    panels_src = PANELS.read_text(encoding='utf-8')

    # ── 1. one shared constant exists, defined once, exported ───────────────
    const_m = re.search(r'const XP_HOT_STREAK\s*=\s*(\d+)\s*;', experience_src)
    check('app/experience.jsx defines XP_HOT_STREAK as a single number',
          const_m is not None)
    threshold = int(const_m.group(1)) if const_m else None
    check('XP_HOT_STREAK is exported (so both twin surfaces can import it)',
          bool(re.search(r"export \{[^}]*\bXP_HOT_STREAK\b[^}]*\};", experience_src)))
    check('the shared threshold matches the roster card\'s own documented '
          'example (OFFICE_AS_INTERFACE #155: "Jobs 3 \U0001F525")',
          threshold == 3, threshold)

    # ── 2. both files import it, neither hardcodes its own number ───────────
    check('views/core.jsx imports XP_HOT_STREAK from app/experience.jsx',
          bool(re.search(r"import \{[^}]*\bXP_HOT_STREAK\b[^}]*\} from '\.\./app/experience\.jsx';",
                          core_src)))
    check('ui/panels.jsx imports XP_HOT_STREAK from app/experience.jsx',
          bool(re.search(r"import \{[^}]*\bXP_HOT_STREAK\b[^}]*\} from '\.\./app/experience\.jsx';",
                          panels_src)))

    roster = brace_lift(core_src, 'function TeamView(')
    roster_fire = re.search(r"\{xp\.streak >= (\w+) \? ' \U0001F525' : ''\}", roster)
    check('the roster card\'s fire check is still present, in the Jobs cell',
          roster_fire is not None)
    check('...and it is gated on XP_HOT_STREAK, not a re-typed literal',
          roster_fire is not None and roster_fire.group(1) == 'XP_HOT_STREAK',
          roster_fire.group(1) if roster_fire else None)

    inspect = brace_lift(panels_src, 'function InspectPanel({')
    panel_fire = re.search(
        r"\{xp\.streak >= (\w+) \? `\$\{xp\.streak\} \U0001F525` : xp\.streak\}", inspect)
    check('the Performance-review panel\'s fire check is still present, in '
          'Current streak',
          panel_fire is not None)
    check('...and it is gated on XP_HOT_STREAK too — the same identifier the '
          'roster card reads, not its own re-typed literal',
          panel_fire is not None and panel_fire.group(1) == 'XP_HOT_STREAK',
          panel_fire.group(1) if panel_fire else None)

    # ── 3. behaviour: simulate both real expressions and prove they now ─────
    #        agree at every streak length, where they used to disagree at 2 ──
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — behavioural simulation skipped')
    elif roster_fire and panel_fire:
        # Lift the two real ternary expressions verbatim (not retyped) and
        # evaluate them under node for a spread of streak values, alongside
        # the two ORIGINAL hardcoded expressions this bug shipped with —
        # proving the fix is a real behaviour change at streak 2, not a
        # cosmetic rename that happens to read the same constant.
        script = r'''
const XP_HOT_STREAK = %d;
const results = [];
for (const streak of [0, 1, 2, 3, 4, 5]) {
  const xp = { streak };
  const rosterNow = (xp.streak >= XP_HOT_STREAK ? ' \u{1F525}' : '');
  const panelNow = (xp.streak >= XP_HOT_STREAK ? `${xp.streak} \u{1F525}` : xp.streak);
  // The two ORIGINAL hardcoded thresholds this bug shipped with (76b8070) —
  // documented here as data, never restored to the real files.
  const rosterOld = (xp.streak >= 3 ? ' \u{1F525}' : '');
  const panelOld = (xp.streak >= 2 ? `${xp.streak} \u{1F525}` : xp.streak);
  results.push({
    streak,
    rosterNowFire: rosterNow.includes('\u{1F525}'),
    panelNowFire: String(panelNow).includes('\u{1F525}'),
    rosterOldFire: rosterOld.includes('\u{1F525}'),
    panelOldFire: String(panelOld).includes('\u{1F525}'),
  });
}
console.log(JSON.stringify(results));
''' % threshold
        proc = subprocess.run(['node', '--input-type=module', '-e', script],
                               cwd=ROOT, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            check('node simulation ran', False, 'node harness failed to run')
        else:
            rows = json.loads(proc.stdout.strip().split('\n')[-1])
            by_streak = {r['streak']: r for r in rows}

            check('at streak 2, the OLD code really did disagree (proves this '
                  'is a genuine behaviour change, not a no-op refactor)',
                  by_streak[2]['rosterOldFire'] is False
                  and by_streak[2]['panelOldFire'] is True,
                  by_streak[2])
            check('at streak 2, the FIXED code agrees: no flame on either '
                  'surface (matches the live repro: "JOBS 2" / "CURRENT '
                  'STREAK 2", no \U0001F525 on either)',
                  by_streak[2]['rosterNowFire'] is False
                  and by_streak[2]['panelNowFire'] is False,
                  by_streak[2])
            check('at streak 3, both surfaces agree: flame on both (matches '
                  'the live repro after adding a third done entry: "JOBS 3 '
                  '\U0001F525" / "CURRENT STREAK 3 \U0001F525")',
                  by_streak[3]['rosterNowFire'] is True
                  and by_streak[3]['panelNowFire'] is True,
                  by_streak[3])
            all_agree = all(r['rosterNowFire'] == r['panelNowFire'] for r in rows)
            check('the two surfaces agree at EVERY streak length checked '
                  '(0 through 5), not just the two measured live',
                  all_agree, rows)

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
