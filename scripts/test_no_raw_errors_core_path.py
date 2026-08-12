#!/usr/bin/env python3
"""Core-path views must not put a raw exception on screen (§7).

§7: "Raw error dumps — every failure is one honest sentence plus 'try again /
ask differently / pick another coworker.'" §6 grants ONE exemption, in as
many words: "Raw model IDs, JSON, and driver names may appear in desktop-mode
surfaces and settings — never on the floor, the cards, or onboarding."

So this is not a blanket ban, and a blanket check would be wrong. It encodes
the actual rule: the surfaces a non-guru meets on the core path get no raw
`e.message`; the surfaces the docs explicitly park for developers do.

GUARDED (core path):
  views/vault.jsx    — §3.6 "the cabinet"; every delivery lands here
  views/projects.jsx — onboarding step 5, with a button on the Getting
                       Started checklist
  views/core.jsx     — Team/Calendar/Inbox

EXEMPT, by the rules above rather than by convenience:
  views/terminal.jsx  — north star §5 parks the PTY for devs in desktop mode
  views/ide.jsx       — code editor, same desktop-mode surface
  modals/settings.jsx — "…and settings", named in the §6 sentence

Found by sweeping for the shape after fixing it in the vault: the same raw
`{err}` / `'… failed: ' + e.message` pattern existed in five more files, and
the useful part was working out which of them the product's own rules
actually forbid it in.

Run: python3 scripts/test_no_raw_errors_core_path.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GUARDED = ['views/vault.jsx', 'views/projects.jsx', 'views/core.jsx']
EXEMPT = ['views/terminal.jsx', 'views/ide.jsx', 'modals/settings.jsx']

# A raw cause reaching user-visible text. Deliberately narrow: it looks for
# the exception object being concatenated or interpolated into a message,
# not for the words "error" or "failed", which are fine on their own.
RAW_IN_MESSAGE = re.compile(
    r"""(?x)
    (?:toast|alert)\s*\([^)]*?(?:e|er|e2|err|error)\s*\.\s*message   # toast('error', '…' + e.message
  | \+\s*\(\s*(?:e|er|e2|err|error)\s*\.\s*message                   # '…' + (e.message || e)
  | \$\{\s*(?:e|er|e2|err|error)\s*\.\s*message                      # `… ${e.message}`
    """)

# A raw err STATE rendered straight into JSX, without passing the classifier.
RAW_ERR_RENDER = re.compile(r'\{\s*err\s*\}')

# Two narrow, reasoned exemptions inside an otherwise-guarded file. Both are
# in the Add-Project dialog, whose `err` does NOT hold an exception:
#   · validation copy the code writes itself ('name required', 'path required')
#   · the clone failure, which deliberately appends git's own stderr on a
#     second line (hence the whiteSpace:'pre-wrap' on that element) — "repository
#     not found" / "Permission denied (publickey)" is the actionable part, and
#     snagCause would take the first line only and cap it at 90 chars.
# Keyed on the className so it cannot silently widen to other renders.
ALLOWED_RAW_ERR_RENDER = 'addproj-err'

# A cause on its way INTO the classifier is the fix, not the bug. Without this
# the guard flags the very helpers that implement it.
ROUTED = re.compile(r'snag(?:Cause|Sentence)\s*\(')

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(s):
    return re.sub(r'/\*[\s\S]*?\*/', '', s)


def main():
    print('§7 raw errors — banned on the core path, allowed where the docs say')
    ok = True
    for rel in GUARDED:
        p = ROOT / rel
        if not p.is_file():
            check(f'{rel} exists', False)
            ok = False
            continue
        src = strip_comments(p.read_text(encoding='utf-8'))

        hits = []
        for m in RAW_IN_MESSAGE.finditer(src):
            # Look at the whole statement, not the match: a cause being handed
            # TO snagCause reads the same locally as one being pasted into a
            # sentence, and only the surrounding line tells them apart.
            line_start = src.rfind('\n', 0, m.start()) + 1
            line_end = src.find('\n', m.end())
            stmt = src[line_start:line_end if line_end > 0 else len(src)]
            if ROUTED.search(stmt):
                continue
            hits.append(stmt.strip()[:60])
        check(f'{rel}: no raw exception concatenated into a message',
              not hits,
              f'{len(hits)} site(s), e.g. {hits[:2]} — route it through '
              f'snagCause() with your own subject and verb, as the vault does')

        renders = []
        for m in RAW_ERR_RENDER.finditer(src):
            line_start = src.rfind('\n', 0, m.start()) + 1
            line_end = src.find('\n', m.end())
            stmt = src[line_start:line_end if line_end > 0 else len(src)]
            if ALLOWED_RAW_ERR_RENDER in stmt:
                continue
            renders.append(stmt.strip()[:60])
        check(f'{rel}: no bare {{err}} rendered into the UI',
              not renders,
              f'{len(renders)} site(s), e.g. {renders[:2]} — classify at the '
              f'render, the one choke point every setErr() passes through')

    # The exemption is a rule, not an oversight — assert the files it names
    # still exist, so a rename cannot silently widen the ban's blast radius.
    for rel in EXEMPT:
        check(f'{rel} still present (documented raw-error exemption)',
              (ROOT / rel).is_file(),
              'if this moved, revisit whether the exemption still applies to '
              'wherever its code went')

    print()
    if FAILS:
        print(f'§7 raw errors: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:4]))
        return 1
    print('§7 raw errors: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
