#!/usr/bin/env python3
"""TeamView's coworker-inbox side panel used to be an inline
`style={{width: 360, flexShrink: 0}}` div with no className, sitting inside
a flex row next to `.team-grid`. Neither of styles.css's mobile breakpoints
(`@media (max-width: 768px)`, `@media (max-width: 640px)`) could reach an
unclassed inline style, so opening the panel (via the 📥 INBOX toggle) on a
real phone viewport dragged the whole TeamView row into horizontal overflow
— and AgentInbox itself had no dismiss control, so the only way out was the
same toggle button that had just scrolled off-screen.

Found by a background hunt agent sweeping previously-uncovered mobile
layout (Library/Calendar/Team/Meetings were named as candidates).

Fix:
  - views/core.jsx: the wrapper div now uses `className="team-inbox-panel"`
    instead of an inline width/flexShrink style.
  - styles.css: `.team-inbox-panel` carries the desktop 360px width as a
    real, targetable rule; `@media (max-width: 768px)` widens it to 100%;
    `@media (max-width: 640px)` turns it into a fixed full-screen overlay
    (position: fixed; inset: 0) instead of a flex sibling fighting
    .team-grid for space.
  - AgentInbox gained an `onClose` prop, rendered as a ✕ button in its own
    header, and TeamView wires it to `setShowInbox(false)` — a way out that
    doesn't depend on a toggle button that may be off-screen.

Run: python3 scripts/test_team_inbox_panel_mobile_layout.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / 'views' / 'core.jsx'
CSS = ROOT / 'styles.css'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("TeamView's coworker-inbox panel is reachable at mobile widths and closable")

    core = CORE.read_text(encoding='utf-8')
    css = CSS.read_text(encoding='utf-8')

    check('AgentInbox accepts an onClose prop',
          re.search(r"function AgentInbox\(\{[^)]*onClose[^)]*\}\)", core) is not None)
    check('AgentInbox renders a close (✕) button when onClose is given',
          re.search(r"onClose && \(\s*<button[^>]*onClick=\{onClose\}", core) is not None)

    m = re.search(r"\{showInbox && \((.*?)\)\}\s*\n\s*</div>\s*\n\s*</div>", core, re.S)
    check('the inbox wrapper block is still present in TeamView', m is not None)
    wrapper = m.group(1) if m else ''

    check('the wrapper uses a real className instead of an inline '
          'width:360/flexShrink:0 style (which no media query could target)',
          'className="team-inbox-panel"' in wrapper)
    check('no inline width:360 style survives on the wrapper',
          'width: 360' not in wrapper)
    check('TeamView wires onClose to collapsing the panel (setShowInbox(false))',
          'onClose={() => setShowInbox(false)}' in wrapper)

    check('.team-inbox-panel carries the desktop 360px width as a real, '
          'targetable CSS rule',
          re.search(r"\.team-inbox-panel\s*\{[^}]*width:\s*360px", css) is not None)

    m768 = re.search(
        r"@media \(max-width: 768px\) \{.*?\.team-inbox-panel \{ width: 100%; \}.*?\n\}",
        css, re.S)
    check('the 768px breakpoint exists and widens .team-inbox-panel to 100%',
          m768 is not None)

    m640 = re.search(r"@media \(max-width: 640px\) \{(.*?)\n\}\n", css, re.S)
    check('the 640px breakpoint turns the panel into a fixed full-screen '
          'overlay (position: fixed) instead of a flex sibling of .team-grid',
          m640 is not None
          and re.search(r"\.team-inbox-panel\s*\{[^}]*position:\s*fixed[^}]*inset:\s*0",
                         m640.group(1), re.S) is not None)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
