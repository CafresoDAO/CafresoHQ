#!/usr/bin/env python3
"""A screenshot's zoom-in cursor promised a click nobody wired up.

BROWSER_SCREENSHOT embeds its PNG as a markdown image
(![alt](data:image/png;base64,...)), and ui/chat.jsx's MessageProse
renders it as a plain <img className="msg-image">, capped to the chat
column's width by styles.css's `max-width: 100%` on `.msg-image` so a
1280x800 capture doesn't blow out the layout.

That same CSS rule has carried `cursor: zoom-in` since the very first
commit (0721113, "Initial V0.01"), directly under a comment reading
"click to open at full size in a new tab" — a documented promise that
a capped, often-illegible screenshot can be seen at native resolution
on click. The <img> itself never carried an onClick anywhere in this
file's history (`git log -p` on both the pre-split ui.jsx and the
post-split ui/chat.jsx turns up exactly one place this element was ever
written, and it never had one). The cursor changed to a hand; nothing
happened underneath it.

Same bug shape as test_chat_copy_claimed_success_it_never_checked.py —
an affordance the UI visibly promises (a cursor style, a toast) that
the code never backed with the action it implies. Fixed the same way
the rest of this file already opens things in a new tab (views/graph.jsx,
views/terminal.jsx): `window.open(url, '_blank', 'noopener,noreferrer')`.

Run: python3 scripts/test_the_screenshot_zoom_cursor_was_a_dead_click.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAT = (ROOT / 'ui/chat.jsx').read_text(encoding='utf-8')
CSS = (ROOT / 'styles.css').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('the screenshot zoom cursor was a dead click')

    # ── 0. the promise this checks against is still there in the CSS ────
    # If a future edit drops the cursor/comment instead of the click, this
    # test should stop being about anything — sanity-check the premise.
    m = re.search(r'\.msg-image \{[^}]*\}', CSS)
    check('.msg-image still exists and still promises a zoom cursor',
          m is not None and 'cursor: zoom-in' in m.group(0))
    check('...and the comment above it still describes a click-to-open',
          'click to open at full size in a new tab' in CSS)

    # ── 1. the <img> that renders a chat-embedded screenshot ────────────
    img = re.search(
        r"<img key=\{'img'\+i\} src=\{b\.src\}[\s\S]{0,300}?/>",
        CHAT)
    check('MessageProse\'s screenshot <img> found', img is not None)
    if not img:
        print()
        print('1 check(s) failed:\n  - MessageProse\'s screenshot <img> found')
        return 1
    tag = img.group(0)

    check('the class is still msg-image (the CSS promise applies to this tag)',
          'className="msg-image"' in tag, tag)

    # ── 2. it is actually wired to open the full-size image ─────────────
    check('the <img> now carries an onClick handler',
          'onClick={' in tag, tag)
    check('...that opens b.src (the same data: URL the image itself renders)',
          re.search(r'onClick=\{[^}]*window\.open\(\s*b\.src\b', tag) is not None,
          tag)
    check('...as a new tab, not the same window',
          re.search(r"window\.open\([^)]*'_blank'", tag) is not None, tag)
    check('...without handing the new tab an opener back (same convention '
          'as views/graph.jsx and views/terminal.jsx\'s window.open calls)',
          re.search(r"window\.open\([^)]*noopener", tag) is not None, tag)

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
