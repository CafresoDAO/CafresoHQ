#!/usr/bin/env python3
"""A keyboard-shortcuts cheatsheet has no business on a phone — styles.css.

Measured at 375×812 while sweeping every mobile tab. `.shortcut-hud`'s
button (`.floppy-btn`) was costing three things and returning nothing:

  · 34×34, against a 44px touch minimum (Track 6 of
    docs/strategy/06-app-update-todo.md, still open).
  · Fixed at z-index 300 — above even the mobile tab bar (150) — and only
    10px from the CHAT tab button, so a thumb aiming for primary nav could
    take it instead.
  · Its entire payload is nine keyboard rows (⌘K, H, S, M, N, U, F, D, /).
    Every one needs a key a phone does not have.

Hidden rather than shrunk or relocated: there is no size or position at
which a list of keystrokes helps someone who cannot press them. Nothing is
lost — the shortcuts still fire when a keyboard is attached (this only hides
the cheatsheet, not the handlers), and the command palette stays reachable
on every viewport via its own FAB.

The desktop half is the real regression risk, so it is pinned here too: the
rule must stay scoped to the mobile breakpoint, and the HUD must keep its
unconditional desktop styling.

Run: python3 scripts/test_shortcut_hud_mobile.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / 'styles.css'
PANELS = ROOT / 'ui' / 'panels.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def mobile_blocks(css):
    """Every @media (max-width: 768px) block, concatenated. styles.css has
    ~23 of them, so grabbing only the first searches the wrong 700 lines —
    a trap this suite's sibling already fell into once."""
    out = []
    for m in re.finditer(r'@media \(max-width: 768px\)', css):
        depth, k = 0, css.index('{', m.start())
        while k < len(css):
            if css[k] == '{':
                depth += 1
            elif css[k] == '}':
                depth -= 1
                if depth == 0:
                    out.append(css[m.start():k + 1])
                    break
            k += 1
    return '\n'.join(out)


def main():
    print('shortcut HUD — hidden on phones, untouched on desktop')
    for p in (CSS, PANELS):
        if not p.is_file():
            print(f'  FAIL  missing {p}')
            return 1
    css = CSS.read_text(encoding='utf-8')
    panels = PANELS.read_text(encoding='utf-8')
    mob = mobile_blocks(css)
    check('found the mobile breakpoint blocks', bool(mob))

    # ── the fix ────────────────────────────────────────────────────────────
    check('.shortcut-hud is hidden at the mobile breakpoint',
          bool(re.search(r'\.shortcut-hud\s*\{[^}]*display:\s*none', mob)),
          'styles.css: a 34×34 control 10px from the CHAT tab, opening nine '
          'keystrokes a phone cannot press')

    # ── the desktop half, which is the thing that could regress ────────────
    desktop_rule = re.search(r'\n\.shortcut-hud \{([^}]*)\}', css)
    check('.shortcut-hud still has its unconditional desktop rule',
          bool(desktop_rule),
          'styles.css: hiding it everywhere would remove a working desktop '
          'affordance, which is not what was measured or intended')
    check("...and that desktop rule doesn't itself hide it",
          bool(desktop_rule) and 'display: none' not in desktop_rule.group(1),
          'styles.css: the hide belongs in the media query only')

    # ── the content that justifies hiding it is still keyboard-only ────────
    hud = panels[panels.find('<div className="shortcut-hud">'):]
    hud = hud[:hud.find('/* ------------ Toast')] if '/* ------------ Toast' in hud else hud[:3000]
    check('the HUD panel is still nothing but <kbd> rows',
          hud.count('<kbd>') >= 8 and 'shortcut-panel' in hud,
          'ui/panels.jsx: if this ever gains touch-usable content, hiding it '
          'on mobile stops being correct — revisit the media query')

    # ── the replacement discovery path must survive ────────────────────────
    check('the command palette FAB is not hidden on mobile',
          not re.search(r'\.palette-fab\s*\{[^}]*display:\s*none', mob),
          'styles.css: the palette is what a phone user reaches for instead '
          '— hiding both would remove discovery entirely')

    print()
    if FAILS:
        print(f'shortcut HUD: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('shortcut HUD: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
