#!/usr/bin/env python3
""""binding for all UI copy" — §6's never-say list, enforced.

OFFICE_AS_INTERFACE §6 carries a translation table and calls it binding. It
has one stated exemption, quoted at the end of the same section: "Raw model
IDs, JSON, and driver names may appear in desktop-mode surfaces and settings
— never on the floor, the cards, or onboarding."

Swept the running app against that table: seven views plus the quick-hire
front desk came back clean, which says the discipline is real. The manual
"NEW HIRE →" form did not — it still had **TEMPERATURE · 0.40**, sitting in
the row between JOB DESCRIPTION and BRAIN, the two labels the ledger records
being fixed in its own §6 "pass three". The third banned term in the same
form survived that pass, probably because the hint under it ("0 = precise ·
1 = spicy") was already carrying the meaning.

§6 prescribes the replacement in the table row itself — "(hidden;
'creativity' dial behind Advanced if ever)" — and the placement was already
right: quick-hire, which is what a first run meets, has no such dial, so the
manual form IS the Advanced half. Only the word was wrong.

This guard checks SOURCE rather than the DOM, so it runs without a browser
and covers copy on paths a sweep might not open. Surfaces are split the way
§6 splits them.

Run: python3 scripts/test_jargon_table.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Files whose visible copy a non-guru meets on the core path.
GUARDED = [
    'modals/hire.jsx', 'modals/starter.jsx', 'modals/delivery.jsx',
    'ui/onboarding.jsx', 'ui/office.jsx', 'views/core.jsx',
]
# §6's own exemption: desktop-mode surfaces and settings.
EXEMPT = ['modals/settings.jsx', 'modals/providers.jsx', 'views/terminal.jsx', 'views/ide.jsx']

# The never-say column of §6's table. Matched only inside user-visible string
# literals and JSX text — never against identifiers, so `temp`, `setTemp` and
# `model` as a variable are all fine.
BANNED = [
    (r'system prompt', 'system prompt → job description'),
    (r'context window', 'context window → memory span'),
    (r'\btemperature\b', 'temperature → creativity (hidden / behind Advanced)'),
    (r'\bAPI[- ]?key\b', 'API key → subscription / sign-in'),
    (r'\bOAuth\b', 'OAuth → sign-in'),
    (r'\btool call\b', 'tool call → name the action itself'),
    (r'\binference\b', 'inference → working'),
]

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def visible_copy(src):
    """JSX text nodes and the string literals that become labels/hints/titles.

    Comments are stripped first: this file's own fix is explained in a comment
    that quotes the banned word, and a guard that trips on its own rationale
    is a guard people delete."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    src = re.sub(r'^\s*//.*$', '', src, flags=re.M)
    chunks = []

    # JSX text. The obvious pattern — >([^<>{}\n]+)< — rejects any node
    # containing an interpolation, which silently skipped the exact label this
    # suite was written for: `<label>TEMPERATURE · {temp.toFixed(2)}</label>`.
    # Caught by fire-testing: reverting that label failed only the specific
    # CREATIVITY check, never the general copy scan that should have owned it.
    # So: allow braces through, then drop the expressions and keep the prose.
    for raw in re.findall(r'>([^<>\n]{3,160})<', src):
        text = re.sub(r'\{[^{}]*\}', ' ', raw).strip()
        if len(text) >= 3:
            chunks.append(text)

    for q in ('"', "'", '`'):
        chunks += re.findall(q + r'([^' + q + r'\\\n]{3,120})' + q, src)
    return chunks


def main():
    print('§6 jargon table — never-say terms out of core-path copy')
    for rel in GUARDED:
        p = ROOT / rel
        if not p.is_file():
            check(f'{rel} exists', False)
            continue
        copy = visible_copy(p.read_text(encoding='utf-8'))
        hits = []
        for pat, fix in BANNED:
            for c in copy:
                if re.search(pat, c, re.I):
                    hits.append(f'{fix!r} in {c.strip()[:40]!r}')
                    break
        check(f'{rel}: no never-say terms in visible copy',
              not hits, '; '.join(hits[:2]))

    check('the exempt surfaces named by §6 still exist',
          all((ROOT / r).is_file() for r in EXEMPT),
          'if one moved, re-read §6 before assuming its copy is still exempt')

    # The specific regression this was written for.
    hire = (ROOT / 'modals/hire.jsx').read_text(encoding='utf-8')
    check('the hire form offers a CREATIVITY dial, not a temperature one',
          'CREATIVITY ·' in hire,
          'modals/hire.jsx: §6 names the replacement word in the same table '
          'row that bans the old one')
    check('...and the dial itself still works',
          'setTemp(parseFloat' in hire,
          'modals/hire.jsx: this was a rename, not a removal — the control is '
          'legitimate behind Advanced, only its label was banned')

    print()
    if FAILS:
        print(f'§6 jargon table: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('§6 jargon table: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
