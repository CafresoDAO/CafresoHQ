#!/usr/bin/env python3
"""Settings search told a boss "Usage this session … since load"; the panel
one click away says something else entirely.

modals/settings.jsx has two independent surfaces that both describe the same
number (`usageTokens`, which is app.jsx's `totalTokens` — ceoTokens plus the
sum of every coworker's `tokens`, file-backed and cumulative since hire, not
per-session):

  1. AccountTab's own "Usage so far" row (the panel a boss actually reads),
     already corrected — per the comment above it — from "Usage this
     session" / "tokens your crew has spent since load" (a false span: the
     number survives a reload byte for byte, so "since load" undersells it
     and "this session" is flatly wrong) to "Usage so far" / "tokens your
     crew has spent since you hired them".

  2. SETTINGS_INDEX, the separate array that powers the Settings search box
     (type "usage" or "session" into Settings and it surfaces a result
     card with its own label + hint, independent of whatever the target
     panel currently renders). This entry was NOT touched by the AccountTab
     fix — it still read label:'Usage this session',
     hint:'tokens your crew has spent since load' — so a boss who searched
     Settings for "usage" saw the wrong span RIGHT NEXT TO a link to the
     panel that gives the right one. Two surfaces, one number, two
     descriptions — the exact class of bug this file's own history
     documents for the number itself (roster card / Situation Wall / HUD
     all summing tokens differently before officeEffort was unified onto
     `totalTokens`), just one layer up, in the copy instead of the math.

Reproduced live: built the UI bundle, ran serve.py rooted in this worktree
(a separate ad hoc instance on its own port — the shared dev checkout in
this session runs several concurrent agents' serve.py/build processes
against the same repo path, so the named preview config intermittently
served a DIFFERENT worktree's dist-ui; confirmed via `lsof -a -p <pid> -d
cwd` and switched to an explicitly-rooted instance to get a clean read),
opened Settings, and typed "since load" into the search box. Before the
fix: one result, "Usage this session" / "tokens your crew has spent since
load", tab ACCOUNT. Clicking through landed on a panel reading "Usage so
far" / "tokens your crew has spent since you hired them" — a live,
visible contradiction one click apart. After the fix (rebuilt, same
server): the search result itself now reads "Usage so far" / "tokens your
crew has spent since you hired them", matching the panel exactly.

Fix: modals/settings.jsx's SETTINGS_INDEX entry for the Usage row now
carries the identical label/hint the panel does, instead of a
hand-duplicated (and since-drifted) copy. `kw` keeps 'session'/'since
load' as search keywords — old muscle memory should still find the
result — without those words being asserted as the current fact in the
label or hint a boss actually reads.

This test lifts BOTH real strings — the SETTINGS_INDEX entry and the
AccountTab JSX row — straight out of modals/settings.jsx by regex, and
fails if they ever drift apart again (independent of which one is
"right"), plus pins that the label/hint text specifically has dropped the
old wrong span.

Run: python3 scripts/test_settings_search_usage_matches_account_panel.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / 'modals' / 'settings.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract_index_usage_entry(src):
    """The real `{ tab:'account', label:'...Usage...', hint:'...', kw:'...' }`
    literal from SETTINGS_INDEX — found by its own shape wherever it sits in
    the array, not by a fixed line/position, so reordering the array can't
    silently stop this test from finding it."""
    m = re.search(
        r"\{\s*tab:'account',\s*label:'([^']*[Uu]sage[^']*)',"
        r"\s*hint:'([^']*)',\s*kw:'([^']*)'\s*\}",
        src)
    return m.groups() if m else None


def extract_account_tab_usage_row(src):
    """The real `<div className="lbl">Usage...</div><div className="sub">
    ...</div>` row from AccountTab's JSX — the panel a boss actually reads
    when they click through."""
    m = re.search(
        r'<div className="lbl">(Usage[^<]*)</div>'
        r'<div className="sub">([^<]*)</div>',
        src)
    return m.groups() if m else None


def main():
    print('Settings search "Usage" result matches the AccountTab panel it links to')
    src = SETTINGS.read_text(encoding='utf-8')

    index_entry = extract_index_usage_entry(src)
    check('SETTINGS_INDEX has a tab:\'account\' entry whose label mentions '
          '"usage" (the search-box result a boss searching "usage" sees)',
          index_entry is not None)

    panel_row = extract_account_tab_usage_row(src)
    check('AccountTab renders a "lbl"/"sub" row whose label starts with '
          '"Usage" (the panel that entry links to)', panel_row is not None)

    if not (index_entry and panel_row):
        print('\n2 FAILED — cannot locate one or both surfaces to compare')
        return 1

    idx_label, idx_hint, idx_kw = index_entry
    panel_label, panel_sub = panel_row

    check('search result label == panel label (same surface, one truth)',
          idx_label == panel_label,
          f'index={idx_label!r} panel={panel_label!r}')
    check('search result hint == panel sub-line (same surface, one truth)',
          idx_hint == panel_sub,
          f'index={idx_hint!r} panel={panel_sub!r}')

    # ── the specific old-wrong-span regression, pinned ────────────────────
    for bad in ('this session', 'since load'):
        check(f'search result label does not (re)claim {bad!r}',
              bad not in idx_label.lower(), idx_label)
        check(f'search result hint does not (re)claim {bad!r}',
              bad not in idx_hint.lower(), idx_hint)
        check(f'panel label does not (re)claim {bad!r}',
              bad not in panel_label.lower(), panel_label)
        check(f'panel sub-line does not (re)claim {bad!r}',
              bad not in panel_sub.lower(), panel_sub)

    # kw is allowed — arguably supposed — to still carry the old phrasing,
    # so old muscle-memory searches ("usage this session") still land here.
    # It is not shown to the boss as a fact, only matched against silently.
    check('kw still makes the entry reachable by the old "session" search '
          'term (search discoverability preserved even though the label/'
          'hint text was corrected)', 'session' in idx_kw)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
