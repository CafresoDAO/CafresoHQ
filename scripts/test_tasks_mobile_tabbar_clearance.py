#!/usr/bin/env python3
"""The Tasks board's last card sat underneath the mobile tab bar.

Measured live at 550×416 on the Tasks view (`views/core.jsx` TasksView,
`views/core.jsx:91` renders `<div className="view-tasks">`), with a task
assigned to a coworker so its action row (▶ START / → CHAT / 📋 ROOM,
`features.jsx:196-220`) was on screen:

  · `document.elementFromPoint` at the START button's own center resolved
    to `.mtab` (the fixed bottom tab bar), not the button — the button's
    `getBoundingClientRect()` placed it entirely behind the bar.
  · Root cause: the two mobile media-query blocks in styles.css that
    reserve bottom clearance for the fixed tab bar name an explicit list
    of content-view classes — `.view, .view-projects, .vault-view,
    .team-view` (base) and the same plus `.vault-view.unified,
    .mobile-chat-view` (taller standalone/PWA block). `.view-tasks` is a
    distinct class name from `.view` and was never in either list, so it
    was the one content surface with no reserved space at the bottom of
    its scroll range — `scrollIntoView({block:'center'})` cannot help,
    because the scroll container has nowhere to scroll TO.
  · With the fix's padding stripped back out live
    (`.view-tasks { padding-bottom: 0 !important }`), the hit-test at the
    button's center returned `.mtab` again, reproducing the exact bug;
    restoring it returned `.tc-action-btn.start`, and a real click through
    it moved the task to DOING and dispatched the coworker.

Same class of bug, same fix shape, as the already-pinned
`scripts/test_mobile_onboarding_layout.py` (checklist + coach-mark vs. the
same tab bar) — see docs/OFFICE_AS_INTERFACE.md, "The Tasks board's own
action row sat under the mobile tab bar — 2026-08-13".

Static checks — these are media queries in styles.css, not exported pure
functions (same constraint as the other views/*.jsx + styles.css suites in
this directory). The geometry itself was verified live in the browser.

Run: python3 scripts/test_tasks_mobile_tabbar_clearance.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / 'views' / 'core.jsx'
FEATURES = ROOT / 'features.jsx'
CSS = ROOT / 'styles.css'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def mobile_blocks(css):
    """Every @media (max-width: 768px) block, PLUS every
    `@media all and (display-mode: standalone)` block — the 80px PWA
    clearance rule lives under the standalone query, not another
    max-width:768px block, as a list (not concatenated — the base and
    standalone/PWA blocks carry DIFFERENT pixel offsets, and collapsing
    them together would let a check pass against either one without
    pinning both)."""
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


def rule_bodies(block, selector):
    """All bodies for `selector` in `block` — a selector list may repeat a
    class across more than one declared rule."""
    return re.findall(re.escape(selector) + r'\s*\{([^}]*)\}', block)


def any_rule_has(block, selector, pattern):
    return any(re.search(pattern, b) for b in rule_bodies(block, selector))


def selector_lists_naming(block, member, pattern):
    """True if some selector LIST containing `member` as one of its
    comma-separated parts has a rule body matching `pattern`.

    Deliberately not `member in block` — that would pass on a stray mention
    of `.view-tasks` anywhere in the block (e.g. a comment), which is
    exactly the kind of false-positive that let this bug through the first
    time: `.view-tasks` really did appear near these rules, in prose, while
    never being a selector.
    """
    for sel_match in re.finditer(r'([.\w,\s>*-]+)\{([^}]*)\}', block):
        selectors, body = sel_match.group(1), sel_match.group(2)
        parts = [p.strip() for p in selectors.split(',')]
        if member in parts and re.search(pattern, body):
            return True
    return False


def main():
    print('tasks board on mobile — the action row clears the fixed tab bar')
    for p in (CORE, FEATURES, CSS):
        if not p.is_file():
            print(f'  FAIL  missing {p}')
            return 1
    core = CORE.read_text(encoding='utf-8')
    features = FEATURES.read_text(encoding='utf-8')
    css = CSS.read_text(encoding='utf-8')
    blocks = mobile_blocks(css)
    check('found at least one max-width:768px block', bool(blocks))

    # ── the DOM shape this bug depends on ───────────────────────────────
    check('TasksView still renders its content as .view-tasks',
          bool(re.search(r'<div className="view-tasks">', core)),
          'views/core.jsx: if this class is renamed, the mobile clearance '
          'rules below have to follow it or the bug comes right back')
    check('the action row (START/CHAT/ROOM) still lives on the task card',
          'tc-action-btn start' in features and 'tc-actions' in features,
          'features.jsx: this is the row that pays for missing clearance — '
          'it is the last thing on the last card')

    # ── the actual fix: .view-tasks in BOTH clearance blocks ───────────
    base = next((b for b in blocks if 'calc(72px' in b and '.view,' in b), None)
    check('found the base-mobile clearance block (72px)', base is not None)
    if base is not None:
        check('.view-tasks is in the base-mobile clearance selector list',
              selector_lists_naming(base, '.view-tasks', r'padding-bottom:\s*calc\(72px'),
              'styles.css: `.view-tasks` is a DIFFERENT class from `.view` — '
              'the generic `.view` rule never matched it, so the Tasks view '
              'had zero reserved space above the tab bar')
        check('...and the offset still respects the iOS safe area',
              selector_lists_naming(base, '.view-tasks',
                                     r'padding-bottom:\s*calc\(72px\s*\+\s*env\(safe-area-inset-bottom\)'),
              'styles.css: a bare 72px would still run under the home '
              'indicator on notched phones')

    pwa = next((b for b in blocks if 'calc(80px' in b and '.mobile-chat-view' in b), None)
    check('found the standalone/PWA clearance block (80px)', pwa is not None)
    if pwa is not None:
        check('.view-tasks is in the standalone/PWA clearance selector list too',
              selector_lists_naming(pwa, '.view-tasks', r'padding-bottom:\s*calc\(80px'),
              'styles.css: the taller in-app tab bar (home indicator + extra '
              'padding) needs the same fix as the base block, independently — '
              'fixing only one leaves the other viewport class stranded')

    print()
    if FAILS:
        print(f'tasks board on mobile: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('tasks board on mobile: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
