#!/usr/bin/env python3
"""_vault_resolve() must not clobber a real extension — serve.py.

Every path through /vault/note (VAULT_NEW/APPEND, VAULT_READ, and — the one
that actually surfaced this — app/artifacts.jsx's fileDelivery() filing a
"Simple page" starter task's deliverable) goes through this one function to
turn a boss-or-agent-supplied relative path into a real file on disk.

It used to force '.md' onto ANYTHING not already ending in '.md', including
paths that already had a perfectly good extension. buildDelivery() computes
`Sites/<slug>.html` for a page deliverable specifically because, per its own
comment, "html is written raw so it renders when opened" — and it landed on
disk as `Sites/<slug>.html.md`, which renders nowhere and (see the search
fix below) couldn't even be found again.

This is the ONE artifact format the whole product's front door produces:
08-north-star-real-product.md §3.6's five-minute flow — hire a coworker,
pick a starter task, "a real artifact lands in their vault" — and "Simple
page" is one of exactly three starter cards. Found by actually running that
exact flow against a fresh install and opening the delivered file.

Run: python3 scripts/test_vault_resolve.py
"""
from __future__ import annotations

import os
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f' — {detail}' if detail and not cond else ''))
    if not cond:
        FAILS.append(label)


def main() -> int:
    os.environ['GAP_CRON'] = '0'
    os.environ['NEWS_CRON'] = '0'
    os.environ['TOPICS_CRON'] = '0'
    os.environ.pop('SEARCH_WORKER', None)
    os.environ['CAFRESOHQ_HQ_STATE_DIR'] = tempfile.mkdtemp(prefix='vault-resolve-')
    os.chdir(ROOT)
    import serve

    print('=== a bare slug still gets .md — the common case is unchanged ===')
    p = serve._vault_resolve('Research/topic')
    check('no extension -> .md appended', p.name == 'topic.md', p.name)

    p = serve._vault_resolve('Daily/2026-04-25.md')
    check('.md stays .md, not doubled', p.name == '2026-04-25.md', p.name)

    print('=== a real extension survives — the actual bug ===')
    p = serve._vault_resolve('Sites/my-pottery-studio.html')
    check('.html stays .html, not Sites/my-pottery-studio.html.md',
          p.name == 'my-pottery-studio.html', p.name)

    p = serve._vault_resolve('Docs/notes.txt')
    check('an arbitrary real extension (.txt) is left alone too',
          p.name == 'notes.txt', p.name)

    print('=== a dotted FOLDER name must not be read as a file extension ===')
    p = serve._vault_resolve('Research/v1.2/notes')
    check('only the final path segment counts — the .2 in v1.2 is a folder, not a suffix',
          p.name == 'notes.md', str(p))

    print('=== traversal protection is unaffected by the extension change ===')
    try:
        serve._vault_resolve('../../../etc/passwd')
        check('a traversal path is rejected', False, 'no exception raised')
    except ValueError:
        check('a traversal path is rejected', True)

    print('=== local /vault/search covers .html deliverables too ===')
    src = (ROOT / 'serve.py').read_text(encoding='utf-8')
    search_block = src[src.find("if path == '/vault/search'"):]
    search_block = search_block[:search_block.find('\n\n\n')]
    # This used to grep for `root.rglob('*.html')`, which was the mechanism
    # of the day rather than the promise. Search now reads the one set of
    # openable extensions shared with /vault/list — the Library holds decks
    # and PDFs too, and three doors each carrying their own glob is what let
    # search return a hit for a file the file tree denied existed. The
    # promise is unchanged and is checked in two halves: search asks the
    # shared set, and a page is in it.
    check("search reads the shared list of openable types",
          '_VAULT_TEXT_EXT' in search_block,
          "serve.py: /vault/search carries its own glob again — the listing "
          "beside it reads _VAULT_TEXT_EXT, and two readers of one question "
          "is how they came to disagree in front of the boss")
    check(".html is on that list, so a page deliverable is findable",
          re.search(r"_VAULT_TEXT_EXT\s*=\s*frozenset\(\{[^}]*'\.html'", src) is not None,
          "serve.py: a page deliverable (the one non-.md format the front "
          "door's third starter card produces) is invisible to search again")

    print()
    if FAILS:
        print(f'vault resolve: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('vault resolve: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
