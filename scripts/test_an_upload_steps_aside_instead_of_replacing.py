#!/usr/bin/env python3
"""Uploading a file that already existed silently destroyed the old one.

Both upload doors — /vault/upload (the Library) and /fs/upload (the
Projects working tree) — ended in a bare write_bytes at the picked
name. Upload deck.pptx twice and the first deck.pptx is gone, no
warning, no message, no undo. Reproduced live before the fix: FIRST
VERSION uploaded, SECOND VERSION uploaded under the same name, only
SECOND VERSION survived.

Now fs_routes.free_name gives a collision the first free variant —
name, 'stem (2).ext', 'stem (3).ext', … — and both doors report the
sidestep through the receipt's existing renamedFrom channel, so the
boss reads '"dupe.txt" was filed as "dupe (2).txt".' in the same
sentence style a sanitized name already gets. Verified live on both
doors and in the Library UI toast. rest/oci vault backends keep their
backends' own overwrite semantics (no per-part existence round-trip).

Run: python3 scripts/test_an_upload_steps_aside_instead_of_replacing.py
"""
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('an upload steps aside instead of replacing')
    import fs_routes

    # ── behavior: the helper itself ─────────────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        taken = lambda c: (d / c).exists()
        check('a free name passes through untouched',
              fs_routes.free_name('deck.pptx', taken) == ('deck.pptx', False))
        (d / 'deck.pptx').write_text('v1')
        check('a collision steps to (2)',
              fs_routes.free_name('deck.pptx', taken) == ('deck (2).pptx', True))
        (d / 'deck (2).pptx').write_text('v2')
        check('...and keeps counting past every taken variant',
              fs_routes.free_name('deck.pptx', taken) == ('deck (3).pptx', True))
        (d / 'Makefile').write_text('all:')
        check('an extensionless name steps aside too',
              fs_routes.free_name('Makefile', taken) == ('Makefile (2)', True))
        (d / 'archive.tar.gz').write_text('x')
        check('only the last suffix is treated as the extension',
              fs_routes.free_name('archive.tar.gz', taken)
              == ('archive.tar (2).gz', True))

    # ── structure: both doors actually ask it ───────────────────────────
    fs_src = (ROOT / 'fs_routes.py').read_text(encoding='utf-8')
    serve = (ROOT / 'serve.py').read_text(encoding='utf-8')
    check('the Projects door asks before writing',
          re.search(r'free_name\(fname,[\s\S]{0,80}target_dir / c\)\.exists', fs_src))
    check('the Library door asks before writing (fs backend)',
          'fs_routes.free_name(' in serve and '_vault_resolve(' in
          serve[serve.index('fs_routes.free_name('):serve.index('fs_routes.free_name(') + 400])
    check('a sidestep reaches the receipt on the Projects door',
          re.search(r"renamedFrom'\] or collided", fs_src))
    check('a sidestep reaches the receipt on the Library door',
          re.search(r"renamedFrom'\] or collided", serve))
    check('the receipt sentence still exists to carry it',
          'was filed as' in (ROOT / 'app' / 'floor.jsx').read_text(encoding='utf-8'))

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
