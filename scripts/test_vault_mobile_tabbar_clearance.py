#!/usr/bin/env python3
"""The Library (vault) view's last file rows / note text sat behind the
fixed mobile tab bar — the one primary mobile tab missed when the
tab-bar-clearance rule was written for its siblings.

The two mobile media-query blocks in styles.css that reserve bottom
clearance for the fixed `.mobile-tabbar` (base 72px, standalone/PWA
80px) name a fixed list of view-root classes. `VaultView`'s actual
mobile root (`views/vault.jsx`) renders `className="vault-mobile"` —
not `.vault-view`/`.view-vault`, which are confirmed dead/unused class
names left over from a prior rendering path (see the earlier ledger
entry on Memory/Calendar). `.vault-mobile` never appeared in either
clearance list at all, so Library — one of only five primary
destinations on the mobile bottom tab bar (Chat, Office, Team, Library,
Projects) — was the one sibling that never got its clearance, even
though Team and Projects (rendered right alongside it on the same tab
bar) did.

Found by a background hunt agent sweeping previously-unswept areas,
after this exact selector-list-omission shape had already recurred
twice (TeamView's reversed name, then Memory+Calendar's omission).

Fix: added `.vault-mobile` to both clearance selector lists in
styles.css, mirroring the Memory/Calendar fix exactly.

Run: python3 scripts/test_vault_mobile_tabbar_clearance.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / 'views' / 'vault.jsx'
CSS = ROOT / 'styles.css'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def mobile_blocks(css):
    out = []
    for m in re.finditer(
        r'@media \(max-width: 768px\)|@media all and \(display-mode: standalone\)', css
    ):
        i = m.start()
        depth, k = 0, css.index('{', i)
        while k < len(css):
            if css[k] == '{':
                depth += 1
            elif css[k] == '}':
                depth -= 1
                if depth == 0:
                    out.append(css[i:k + 1])
                    break
            k += 1
    return out


def selector_lists_naming(block, member, pattern):
    """True if some selector LIST containing `member` as one of its
    comma-separated parts has a rule body matching `pattern`. Deliberately
    not `member in block` — a stray textual mention (e.g. in a comment)
    must not pass."""
    for sel_match in re.finditer(r'([.\w,\s>*-]+)\{([^}]*)\}', block):
        selectors, body = sel_match.group(1), sel_match.group(2)
        parts = [p.strip() for p in selectors.split(',')]
        if member in parts and re.search(pattern, body):
            return True
    return False


def main():
    print("Library's mobile view clears the fixed mobile tab bar")

    vault = VAULT.read_text(encoding='utf-8')
    css = CSS.read_text(encoding='utf-8')
    blocks = mobile_blocks(css)
    check('found at least one max-width:768px block', bool(blocks))

    check('VaultView still renders its mobile root as "vault-mobile"',
          '"vault-mobile"' in vault,
          'views/vault.jsx: if this class is renamed, the mobile '
          'clearance rules below have to follow it or the bug comes '
          'right back')

    base = next((b for b in blocks if 'calc(72px' in b and '.view,' in b), None)
    check('found the base-mobile clearance block (72px)', base is not None)
    if base is not None:
        check('.vault-mobile is in the base-mobile clearance selector list',
              selector_lists_naming(base, '.vault-mobile', r'padding-bottom:\s*calc\(72px'))

    pwa = next((b for b in blocks if 'calc(80px' in b and '.mobile-chat-view' in b), None)
    check('found the standalone/PWA clearance block (80px)', pwa is not None)
    if pwa is not None:
        check('.vault-mobile is in the standalone/PWA clearance selector list too',
              selector_lists_naming(pwa, '.vault-mobile', r'padding-bottom:\s*calc\(80px'),
              'fixing only one block leaves the other viewport class stranded')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
