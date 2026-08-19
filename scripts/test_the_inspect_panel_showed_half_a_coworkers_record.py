#!/usr/bin/env python3
"""InspectPanel showed Jobs and streak but never Snags — the roster card did.

Reproduced by reading the source: `xpStats()` (app/experience.jsx) always
computes `{ jobs, snags, streak, byKind, affinity, lastAt }` from the same
append-only ledger. The Team roster card (views/core.jsx TeamView) reads it
and shows a Snags row — deliberately conditional, only when `xp.snags > 0`,
with a comment explaining why: "a standing 'Snags 0' on every card is noise,
not reassurance."

InspectPanel (ui/panels.jsx), the other surface that reads the exact same
xpStats() result for the exact same agent, showed "Jobs completed" and
"Current streak" and stopped there. Snags was computed and simply never
rendered — not a wrong number, an absent one. A boss opening a coworker's
performance review (the panel's own subtitle) could see a streak had reset
without any way to see why, while the roster card two clicks away told the
truth about the same coworker.

Run: python3 scripts/test_the_inspect_panel_showed_half_a_coworkers_record.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PANELS = (ROOT / 'ui/panels.jsx').read_text(encoding='utf-8')
CORE = (ROOT / 'views/core.jsx').read_text(encoding='utf-8')
EXPERIENCE = (ROOT / 'app/experience.jsx').read_text(encoding='utf-8')
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
    print('the inspect panel showed half a coworker\'s record')

    # ── 0. xpStats really does compute snags — confirms this is a real,
    #        already-available fact, not something that needs new plumbing ──
    stats_fn = brace_lift(EXPERIENCE, 'function xpStats(ledger, agentId) {')
    check('xpStats() computes snags from the ledger',
          re.search(r'\bsnags\+\+', stats_fn) is not None
          and re.search(r'return \{ ?jobs, snags,', stats_fn) is not None)

    # ── 1. the roster card's Snags row is the reference pattern ─────────────
    roster = brace_lift(CORE, 'function TeamView(')
    roster_snags = re.search(
        r"\{xp\.snags > 0 && \([\s\S]*?<span className=\"lbl\">Snags</span>"
        r"[\s\S]*?\)\}", roster)
    check('roster card conditionally shows a Snags row (the pattern to match)',
          roster_snags is not None)

    # ── 2. InspectPanel now has the same row, same condition ────────────────
    inspect = brace_lift(PANELS, 'function InspectPanel({')
    check('InspectPanel still shows Jobs completed',
          re.search(r'<span className="lbl">Jobs completed</span>', inspect)
          is not None)
    check('InspectPanel still shows Current streak',
          re.search(r'<span className="lbl">Current streak</span>', inspect)
          is not None)
    inspect_snags = re.search(
        r"\{xp\.snags > 0 && \([\s\S]*?<span className=\"lbl\">Snags</span>"
        r"[\s\S]*?\)\}", inspect)
    check('InspectPanel now shows a Snags row, gated the same way as the roster card',
          inspect_snags is not None,
          '— a boss reading a performance review still could not tell why '
          'a streak had reset')
    if inspect_snags:
        block = inspect_snags.group(0)
        check('...bound to the same xp.snags value the roster card reads',
              'xp.snags' in block)
        check('...same "runs you stopped are not counted" honesty note as the roster row',
              'Runs you stopped yourself are not counted' in block)

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
