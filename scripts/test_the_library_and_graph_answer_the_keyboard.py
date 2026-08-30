#!/usr/bin/env python3
"""The Library tree, its search hits, and the graph's menus were mouse-only.

Before this pass, `views/vault.jsx`, `views/graph.jsx`, `views/misc.jsx`
and `views/terminal.jsx` contained not one `aria-` attribute or `role=`
between them (misc and terminal turned out to have nothing that needed
one — terminal's controls are real <button>s with visible text). The
parts that DID need one:

  - FolderTree (views/core.jsx) rendered every folder and file row as a
    <div onClick> — unreachable by Tab, silent to a screen reader, with
    folders indistinguishable from files;
  - the Library's search-hit rows (both the mobile and desktop variants
    in views/vault.jsx) were the same bare <div onClick>;
  - the minimized-graph restore pane was a full-pane <div onClick>
    labeled "(click to show)" that no keyboard could click;
  - the graph's node context menu and "Most influential" focus rows
    were clickable <div>s with no role and no key handling, and the
    graph's ✕ minimize button had no accessible name at all.

Every fixed row follows one recipe: a role (`treeitem`/`button`/
`menuitem`), `tabIndex={0}` so Tab reaches it, and an Enter/Space
keydown that preventDefaults and calls the same handler the click
calls. Decorative glyphs (chevrons, folder icons) are aria-hidden so a
reader says "Research, collapsed" and not "black down-pointing small
triangle open file folder Research".

Run: python3 scripts/test_the_library_and_graph_answer_the_keyboard.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('the Library and the graph answer the keyboard')
    core = strip_comments((ROOT / 'views' / 'core.jsx').read_text(encoding='utf-8'))
    vault = strip_comments((ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8'))
    graph = strip_comments((ROOT / 'views' / 'graph.jsx').read_text(encoding='utf-8'))

    # ── the tree ────────────────────────────────────────────────────────
    check('the tree root declares itself a tree',
          'role="tree" aria-label="Library files"' in core)
    check('folder rows are treeitems that announce open/closed',
          'role="treeitem" aria-expanded={isOpen} tabIndex={0}' in core)
    check('file rows are treeitems that announce the open file',
          'role="treeitem" aria-current={openPath === n.path || undefined} tabIndex={0}' in core)
    check('rows answer Enter and Space with the same handler as the click',
          core.count('onKeyDown={rowKeys(') == 2
          and "if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn(); }" in core,
          core.count('onKeyDown={rowKeys('))
    check('decorative glyphs are hidden from readers',
          'className="tree-chev" aria-hidden="true"' in core
          and 'className="tree-icon" aria-hidden="true"' in core)

    # ── the Library around the tree ─────────────────────────────────────
    check('both search inputs have an accessible name',
          vault.count('aria-label="Search the Library"') == 2,
          vault.count('aria-label="Search the Library"'))
    hit_rows = re.findall(
        r'className="tree-row tree-file" role="button" tabIndex=\{0\}', vault)
    check('both search-hit lists are keyboard-operable (mobile and desktop)',
          len(hit_rows) == 2, len(hit_rows))
    check('the minimized-graph restore pane is a real button now',
          'className="vault-graph-pane fullspan" role="button" tabIndex={0}' in vault,
          '— "(click to show)" must be clickable by keyboard too')
    # Any hit row or restore pane that gained a role must also have keys —
    # a focusable row that swallows Enter is worse than an unfocusable one.
    for label, hay, n in (
        ('hit rows', vault, 2 + 1),  # 2 hit lists + restore pane
    ):
        keyed = len(re.findall(
            r"onKeyDown=\{e=>\{ if \(e\.key==='Enter'\|\|e\.key===' '\) \{ e\.preventDefault\(\);", hay))
        check(f'every focusable {label} handles Enter/Space', keyed == n,
              [keyed, n])

    # ── the graph ───────────────────────────────────────────────────────
    check('the node context menu is a menu of menuitems',
          "role: 'menu', 'aria-label': 'Node actions'" in graph
          and "role: 'menuitem', tabIndex: 0" in graph)
    check('menu items and focus rows answer the keyboard',
          graph.count("if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault();") == 2,
          graph.count("if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault();"))
    check('the influential-node rows are buttons',
          "role: 'button', tabIndex: 0," in graph)
    check('the minimize button has a name',
          "'aria-label': 'Minimize graph'" in graph,
          '— a bare ✕ reads as "multiplication x"')

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
