#!/usr/bin/env python3
"""The Chat view's composer sat behind the fixed mobile tab bar — the
fourth time this exact selector-list-omission shape has been found.

The two mobile media-query blocks in styles.css that reserve bottom
clearance for the fixed `.mobile-tabbar` (base 72px, standalone/PWA
80px) name a fixed list of view-root classes. `renderViewBody`'s
`case 'chat':` (app.jsx) renders the mobile Chat tab as
`className="mobile-chat-view"` — one of only five primary destinations
on the mobile bottom tab bar (Chat, Office, Team, Library, Projects).

`.mobile-chat-view` WAS already in the standalone/PWA (80px) clearance
list — but never appeared in the base, ordinary-mobile-browser (72px)
list at all. So a user on a plain mobile browser tab (the overwhelmingly
more common case than an installed PWA) got no clearance on the Chat
view: `.mobile-chat-view` has no padding-bottom of its own (styles.css
~9312), and its composer is `position: sticky; bottom: 0` inside that
unpadded container (styles.css ~9228), so it sticks to the true bottom
of the viewport — directly under the fixed, `z-index: 150`,
`position: fixed; bottom: 0` `.mobile-tabbar` (styles.css ~7944). The
message input and send button were the part of the screen this covered;
installing the app to the home screen was the one way to accidentally
get it right.

Same shape as the three fixes before it (TeamView's reversed name,
Memory+Calendar's outright omission, VaultView/Library's omission) —
found by re-deriving the full list of primary mobile-tab root classes
from app.jsx's `renderViewBody` and diffing it against both clearance
lists, rather than trusting either list was complete.

Fix: added `.mobile-chat-view` to the base (72px) clearance selector
list in styles.css, mirroring its existing entry in the standalone
(80px) list.

Run: python3 scripts/test_chat_mobile_tabbar_clearance.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
CSS = ROOT / 'styles.css'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# Lifted verbatim from scripts/test_vault_mobile_tabbar_clearance.py, which
# established this pattern for the same bug shape — reused rather than
# reimplemented so the two tests parse the cascade identically.
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
    print("Chat's mobile view clears the fixed mobile tab bar")

    app = APP.read_text(encoding='utf-8')
    css = CSS.read_text(encoding='utf-8')
    blocks = mobile_blocks(css)
    check('found at least one max-width:768px block', bool(blocks))

    check('app.jsx still renders the mobile Chat tab as "mobile-chat-view"',
          '"mobile-chat-view"' in app,
          "app.jsx: if this class is renamed, the mobile clearance rules "
          "below have to follow it or the bug comes right back")

    base = next((b for b in blocks if 'calc(72px' in b and '.view,' in b), None)
    check('found the base-mobile clearance block (72px)', base is not None)
    if base is not None:
        check('.mobile-chat-view is in the base-mobile clearance selector list',
              selector_lists_naming(base, '.mobile-chat-view', r'padding-bottom:\s*calc\(72px'),
              "styles.css: without this, Chat — the app's primary mobile "
              "view — has its composer covered by the fixed tab bar on "
              "every plain mobile browser session")

    pwa = next((b for b in blocks if 'calc(80px' in b and '.mobile-chat-view' in b), None)
    check('found the standalone/PWA clearance block (80px)', pwa is not None)
    if pwa is not None:
        check('.mobile-chat-view is in the standalone/PWA clearance selector list too',
              selector_lists_naming(pwa, '.mobile-chat-view', r'padding-bottom:\s*calc\(80px'),
              'this one was already correct — a regression guard, not the fix')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
