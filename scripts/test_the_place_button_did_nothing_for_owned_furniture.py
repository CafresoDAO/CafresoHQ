#!/usr/bin/env python3
"""FurnishModal's PLACE button did nothing for items you already owned.

Reproduced by reading the source. `modals/collab.jsx`'s `FurnishModal`
gates its button's `disabled` prop as:

    disabled={!!busyId || isPlaced || (!canBuy && !isOwned)}

For an OWNED item, `!canBuy && !isOwned` is always false, so the button
stays clickable even with no chain connection (browsing-only mode) —
correctly, since re-placing something you already own is free and
needs no purchase.

But `buy()`, the handler that button calls, used to open with:

    if (!canBuy || busyId) return;

which bails out before ever checking whether the item was already
owned. So the one case the button's own `disabled` logic deliberately
left clickable — an owned item, no chain — was exactly the case where
clicking it did nothing at all: no error, no toast, no state change.
The UI promised an action the handler silently refused to perform.

Run: python3 scripts/test_the_place_button_did_nothing_for_owned_furniture.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLLAB = (ROOT / 'modals/collab.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('the PLACE button did nothing for owned furniture')

    fn = re.search(r"const buy = async \(item\) => \{[\s\S]*?\n  \};", COLLAB)
    check('found buy()', fn is not None)
    body = fn.group(0) if fn else ''

    check("buy()'s opening guard no longer bails on !canBuy unconditionally",
          not re.search(r"^\s*if \(!canBuy \|\| busyId\) return;", body, re.M))
    check('...it still bails on a concurrent action (busyId) right away',
          re.search(r"^\s*if \(busyId\) return;", body, re.M) is not None)
    check('ownership is checked before any canBuy gate',
          re.search(r"const alreadyOwned = owned\.includes\(key\);\s*\n", body) is not None)
    check('!canBuy now only blocks the NEW-purchase branch, nested inside `if (!alreadyOwned)`',
          re.search(r"if \(!alreadyOwned\) \{\s*\n\s*if \(!canBuy\) return;", body) is not None)

    # The free re-place for an owned item must still run unconditionally —
    # this fix must not accidentally gate it on anything new.
    check('the free re-place (onUpdate with decor) runs outside the !alreadyOwned block, for both paths',
          re.search(r"\n    \}\n    // Place it \(new or already-owned\): cosmetic state on the agent record\.\s*\n\s*onUpdate\(agent\.id, \{",
                     body) is not None)

    # The button's own disabled= logic — which already encoded the correct
    # intent — is untouched by this fix.
    check("the button's disabled= expression (the thing that exposed this bug) is untouched",
          "disabled={!!busyId || isPlaced || (!canBuy && !isOwned)}" in COLLAB)

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
