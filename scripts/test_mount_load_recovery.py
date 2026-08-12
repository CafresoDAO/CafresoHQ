#!/usr/bin/env python3
"""Automatic loads must offer a way back — the rest of the Track 6 sweep.

Last pass established the criterion: a failure behind a control the boss just
pressed already HAS its way forward (that control), and adding a second one
would imply the first had stopped working. The gap is loads that run by
themselves, where there is no button at all. Settings' driver probe was the
first; sweeping the remaining mount-time loads found two more.

**views/ide.jsx — the file tree.** `if (err) return <div>Error: {err}</div>`
replaced the ENTIRE tree with a raw error dump, so a failed listing cost the
boss the files and the route back in one move. Its `refreshNonce` comes from
the parent and is only bumped after an upload, so nothing on that screen
could ask again.

**modals/base.jsx — ModelPicker.** On failure it silently substitutes a
STATIC list for the detected one. Proven live: forcing the probe to fail
showed `Codex CLI / Anthropic / Google` on a machine where the real list is
six groups including **Ollama (local)** — 28 options — so the boss's own
running brain vanishes from the picker while it still looks like a detected
list. §3.3 says the top of this list belongs to what the boss already has;
in fallback it belongs to three services they must go and buy. The only
signal was a `title` tooltip, which does not exist on touch.

Worse, its `refreshKey` prop is passed by NONE of its three call sites (hire,
providers, settings), so the refresh affordance existed in the code and could
never fire. Both now own an internal nonce instead of depending on a caller
that does not cooperate.

Run: python3 scripts/test_mount_load_recovery.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IDE = ROOT / 'views' / 'ide.jsx'
BASE = ROOT / 'modals' / 'base.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('mount-load recovery — a load nobody started still needs a door')
    for f in (IDE, BASE):
        if not f.is_file():
            print(f'  FAIL  missing {f}')
            return 1
    ide = IDE.read_text(encoding='utf-8')
    base = BASE.read_text(encoding='utf-8')

    # ── The file tree ───────────────────────────────────────────────────
    check('the file tree no longer dumps a raw error',
          not re.search(r'>Error: \{err\}<', ide),
          'views/ide.jsx: §7 forbids raw dumps, and this one replaced the whole tree')
    check('...it says what failed, in the office\'s words',
          'Couldn’t read this folder' in ide,
          'views/ide.jsx: "Error: ENOENT…" tells a boss nothing they can act on')
    check('...routed through cleanCause, not snagCause',
          'cleanCause' in ide and not re.search(r'\bsnagCause\s*\(', ide),
          'views/ide.jsx: a directory listing is the office\'s own file tools, not a '
          'brain — snagCause would blame the wrong component')
    check('...and offers a retry the tree itself owns',
          re.search(r'setRetryNonce\(n => n \+ 1\)', ide) is not None
          and 'TRY AGAIN' in ide,
          'views/ide.jsx: refreshNonce is the parent\'s and only bumps after an '
          'upload, so nothing on a failed screen could ask again')
    check('...wired into the fetch effect\'s deps',
          re.search(r'\}, \[path, refreshNonce, retryNonce\]\)', ide) is not None,
          'views/ide.jsx: a nonce the effect does not watch changes nothing')
    check('...and clears the error before retrying',
          re.search(r'setErr\(null\); setRetryNonce', ide) is not None,
          'views/ide.jsx: otherwise a successful retry leaves the red line above a '
          'working tree')

    # ── ModelPicker ─────────────────────────────────────────────────────
    check('the picker admits when it is showing a guess',
          'standard list' in base and 'may be missing from it' in base,
          'modals/base.jsx: the fallback swaps the DETECTED list for a static one — '
          'measured live, six groups incl. Ollama became three without it')
    check('...visibly, not only in a title tooltip',
          not re.search(r"title=\{error \?", base),
          'modals/base.jsx: a tooltip does not exist on touch and nobody hovers a '
          '<select>')
    check('...with a retry beside it',
          re.search(r'setRetryNonce\(n => n \+ 1\)', base) is not None
          and 'CHECK AGAIN' in base,
          'modals/base.jsx: knowing the list is wrong is only half an answer')
    check('...that the effect actually watches',
          re.search(r'\}, \[refreshKey, retryNonce\]\)', base) is not None,
          'modals/base.jsx: refreshKey alone could never fire — no call site passes it')
    check('...and that reports progress while probing',
          re.search(r'disabled=\{loading\}', base) is not None,
          'modals/base.jsx: this probe took >3s live; a button that looks inert for '
          'three seconds reads as broken')

    # ── The dead prop that started it: still dead, so the nonce matters ──
    callers = []
    for f in ROOT.rglob('*.jsx'):
        if 'node_modules' in str(f) or 'dist-ui' in str(f):
            continue
        for m in re.finditer(r'<ModelPicker\b[^>]*>', f.read_text(encoding='utf-8', errors='replace')):
            callers.append((f.name, 'refreshKey' in m.group(0)))
    check('ModelPicker has call sites, and the internal nonce is what saves them',
          len(callers) >= 3 and not any(passes for _n, passes in callers),
          f'{callers!r} — if a caller starts passing refreshKey that is fine, but the '
          'internal nonce must remain, because the others still do not')

    print()
    if FAILS:
        print(f'mount-load recovery: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('mount-load recovery: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
