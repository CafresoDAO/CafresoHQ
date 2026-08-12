#!/usr/bin/env python3
""""Error / NetworkError when attempting to fetch resource." — views/vault.jsx.

That was the WHOLE screen a boss got when the vault couldn't reach the
office: the literal dev word "Error" as a heading, the raw browser exception
under it, and no button anywhere. It also REPLACES the file tree, so the one
surface §3.6 calls "the cabinet" vanishes and a stack-trace fragment stands
in its place.

Three §7 breaches in one view — raw dump, dev vocabulary, and no way
forward — on the same underlying outage that the app's own topbar banner
already answers well ("Your office is offline… then hit Retry"). Driven live
by failing /vault/status.

Now: an office-language heading, the cause through the shared `snagCause`
classifier, a line making clear the files are not lost, and a working
"↻ Try again". Classified at the RENDER rather than at the five `setErr()`
call sites, because the render is the single choke point they all pass
through — one honest sentence covers every one of them, and `err` keeps the
raw cause for debugging.

Run: python3 scripts/test_vault_error_screen.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'views' / 'vault.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("vault error screen — the cabinet fails in office words, with a way out")
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    src = SRC.read_text(encoding='utf-8')

    start = src.find('  if (err) {')
    check('the err branch still exists', start >= 0)
    if start < 0:
        print('\nvault error screen: FAILED')
        return 1
    block = src[start:start + 1400]

    # ── §7: no raw dump ────────────────────────────────────────────────────
    check('the raw cause is classified, not printed',
          'snagCause(err)' in block,
          "views/vault.jsx: `{err}` put the browser's own exception text on "
          'screen — the exact §7 breach this branch used to commit')
    check('the bare {err} interpolation is gone',
          not re.search(r'\{err\}', block),
          'views/vault.jsx: rendering err directly re-opens the raw dump')

    # ── §6: office vocabulary, not dev vocabulary ──────────────────────────
    check('the heading is not the dev word "Error"',
          not re.search(r'empty-title[^>]*>\s*Error\s*<', block),
          'views/vault.jsx: §6 — "Error" is not a word the office speaks')
    check('...and says what failed in office terms',
          "The cabinet won't open" in block,
          'views/vault.jsx: §3.6 calls this surface the cabinet')

    # ── §7: every failure offers a way forward ─────────────────────────────
    check('the screen offers a retry control',
          'Try again' in block,
          'views/vault.jsx: §7 — a failure with no button is a dead end, and '
          'this one replaces the whole file tree')
    check('...and that control actually re-runs refresh()',
          bool(re.search(r'onClick=\{\(\) => \{[^}]*refresh\(\)', block)),
          'views/vault.jsx: a Try again that does not retry is worse than none')
    check('...and clears the error state so the retry can render',
          'setErr(null)' in block,
          'views/vault.jsx: leaving err set would keep this screen up even '
          'after a successful refresh')

    # ── honesty: the boss should know their files are not gone ─────────────
    check('it says the files are still safe',
          'files are safe' in block,
          'views/vault.jsx: an unreachable cabinet reads as a LOST cabinet '
          'unless the screen says otherwise')

    print()
    if FAILS:
        print(f'vault error screen: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('vault error screen: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
