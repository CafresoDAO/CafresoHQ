#!/usr/bin/env python3
"""One failed Library search used to replace the whole tree and editor.

Reproduced by reading the source. `views/vault.jsx`'s `search()` used to
route a failed query through the same `err` state that gates the entire
view:

    catch (e) { setErr(e.message); setHits([]); }

`err` is the SINGLE choke point (the file's own comment says so
explicitly) for the whole-cabinet "The cabinet won't open" screen — the
one that replaces the file tree, the open editor, everything, with a
full-page failure and a Retry button. That screen is correct for a
genuine vault-load failure (a bad `/vault/status`). It is not correct
for one search query timing out while the vault is open and working
fine — a boss mid-edit on a note, with the tree fully loaded, could lose
sight of both by typing a query that happened to fail.

The file already drew this exact distinction once, for saves — its own
comment on `saveNote` says: "Saving is tracked per-editor (inline chip)
and NEVER via the view-level `err` — a failed save used to replace the
whole vault view with an error screen, hiding the user's unsaved text."
`search()` never received the equivalent fix, and a `snag()` helper
(toast + officeCause, no view-nuking) already exists in this same file
for exactly this kind of scoped failure.

Run: python3 scripts/test_a_failed_search_closed_the_whole_cabinet.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT = (ROOT / 'views/vault.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('a failed search closed the whole cabinet')

    check('the snag() toast helper exists in this file (the pattern to reuse)',
          re.search(r"const snag = \(what, err\) => \{", VAULT) is not None)

    fn = re.search(r"const search = async \(\) => \{[\s\S]*?\n  \};", VAULT)
    check('found search()', fn is not None)
    body = fn.group(0) if fn else ''

    check('search() no longer calls setErr on failure',
          'setErr(e.message)' not in body,
          '— that call routes into the whole-cabinet failure screen')
    check('...it calls snag() instead, matching the pattern already used elsewhere in this file',
          re.search(r"catch \(e\) \{ snag\('Search failed', e\); setHits\(null\); \}", body)
          is not None)
    check('...and clears hits to null (falls back to the tree), not an empty array claiming 0 real results',
          'setHits([])' not in body)

    # The genuine whole-cabinet failure screen and its gate are untouched —
    # this fix must not weaken the real case (a failing vault LOAD).
    check('the whole-cabinet failure screen and its `err` gate are untouched',
          "The cabinet won't open" in VAULT and 'if (err) {' in VAULT)
    check("saveNote's own per-editor error handling (the precedent this fix follows) is untouched",
          re.search(r"NEVER via the view-level\s*\n\s*`err`", VAULT) is not None)

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
