#!/usr/bin/env python3
"""The command palette's Help section ("Cmd/Ctrl-K" → "Keyboard shortcuts")
used to pop its own toast:

    'Cmd/Ctrl-K — palette · / — graph filter · Esc — close · ⌘P — graph palette'

Two of those four claims never existed anywhere in the app:

    - "/ — graph filter": no keydown listener exists in views/graph.jsx at
      all. The real global `/` handler (app.jsx) focuses the chat
      composer — a different feature, doing something else, in a view
      that doesn't even need to be open.
    - "⌘P — graph palette": no 'p'/'P'/KeyP key handler exists anywhere
      in the repo. Pressing it does nothing.

Meanwhile the app already has a correct, always-in-sync shortcuts
surface — ShortcutHud (ui/panels.jsx), toggled by the real ⌘K handler
(app.jsx) — whose own entries were all verified against real `e.key ===
...` branches. The palette's toast was a second, hand-maintained list
that had drifted from the first one, most likely left behind when a
graph command-palette / lasso-select feature was removed from
views/graph.jsx without anyone updating this toast (an old worktree
snapshot still shows the removed graph-view footer hint "⌘P palette").

**The fix** stops hand-maintaining a second shortcuts list. `help.shortcuts`
now calls a new `onShortcuts` prop, wired in app.jsx to open the same
ShortcutHud panel the real ⌘K shortcut opens — the one list that's
actually kept honest against the key handlers, because they live in the
same file and a stale entry there would be caught by inspection, not
hidden in an unrelated toast string.

Run: python3 scripts/test_shortcuts_command_matches_real_shortcuts.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMANDS = ROOT / 'app' / 'commands.jsx'
APP = ROOT / 'app.jsx'
PANELS = ROOT / 'ui' / 'panels.jsx'
GRAPH = ROOT / 'views' / 'graph.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract(text, start_marker, end_marker):
    i = text.index(start_marker)
    j = text.index(end_marker, i + len(start_marker))
    return text[i:j + len(end_marker)]


def run(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the real files')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print("The palette's Keyboard shortcuts entry no longer invents shortcuts")
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    commands = COMMANDS.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')
    panels = PANELS.read_text(encoding='utf-8')
    graph = GRAPH.read_text(encoding='utf-8')

    # ── 1. help.shortcuts now defers to onShortcuts, driven for real ─────
    entry = extract(commands, "{ id: 'help.shortcuts',", '\n    },')
    check('extracted the help.shortcuts command entry', "run:" in entry,
          'app/commands.jsx shape changed')
    # The two fabricated claims and the old toast string must be gone from
    # THIS command's own object literal specifically — not just "somewhere
    # in the file" (this file's own explanatory comment, a few lines above
    # the object, legitimately quotes the old false claims as history, so
    # a whole-file substring check would false-positive on the fix's own
    # commentary).
    check("'graph filter' claim is gone from the command itself",
          'graph filter' not in entry, entry)
    check("'graph palette' claim is gone from the command itself",
          'graph palette' not in entry, entry)
    check("the old hand-written toast string is gone from the command itself",
          'Cmd/Ctrl-K — palette' not in entry, entry)

    entry_obj = entry[:-1] if entry.rstrip().endswith(',') else entry
    harness = """
let called = 0, toasted = false;
const onShortcuts = () => { called++; };
const window = { cafresohqToast: { info: () => { toasted = true; } } };
const cmd = %s;
cmd.run();
console.log(JSON.stringify({ called, toasted, label: cmd.label, section: cmd.section }));
""" % entry_obj
    R = run(harness)
    check('clicking "Keyboard shortcuts" now calls onShortcuts()',
          R['called'] == 1, R)
    check('...and does NOT pop a toast anymore (no second, driftable list)',
          R['toasted'] is False, R)
    check('label/section are unchanged (still findable the same way in the '
          'palette)',
          R['label'] == 'Keyboard shortcuts' and R['section'] == 'Help', R)

    # ── 3. onShortcuts is threaded through: destructured, in the dep array,
    #        and wired at the real call site to the real ⌘K state ─────────
    check('onShortcuts is destructured from AppGlobalCommands\' props',
          # Distinguished from the dependency-array check below by what
          # follows onShortcuts, — `anyBusy,` only appears after it in the
          # props destructuring, not in the dependency array (which is
          # followed by `agents,`). A looser regex matched either
          # occurrence and stayed green when only ONE of the two was
          # reverted — caught by this file's own fire-test.
          re.search(r'onStopAll,\s*\n\s*onShortcuts,\s*\n\s*anyBusy,', commands) is not None,
          'app/commands.jsx: prop destructuring changed shape')
    check('onShortcuts is in the useCommands dependency array (or the '
          'command would run stale/closed-over-undefined after a re-render)',
          re.search(r'onStopAll,\s*\n\s*onShortcuts,\s*\n\s*agents,', commands) is not None,
          'app/commands.jsx: dependency array changed shape')
    check('app.jsx wires onShortcuts to the SAME state ⌘K already toggles',
          'onShortcuts={() => setShortcutsOpen(true)}' in app,
          'app.jsx: AppGlobalCommands call site changed shape')

    # ── 4. the redirect target is actually correct: ShortcutHud's own
    #        entries are all real, and the two retired claims are still
    #        retired (locks the underlying facts, not just the copy) ──────
    check('ShortcutHud (the redirect target) still exists with its real '
          'entries intact',
          '<kbd>⌘K</kbd><span>Toggle shortcuts</span>' in panels
          and '<kbd>/</kbd><span>Focus chat</span>' in panels,
          'ui/panels.jsx: ShortcutHud changed shape')
    hud_keys = re.findall(r'<kbd>([^<]+)</kbd><span>', panels[panels.index('SHORTCUTS'):panels.index('SHORTCUTS') + 1200])
    check('every key ShortcutHud advertises maps to a real handler in '
          "app.jsx's onKey (⌘K is checked separately, it toggles the HUD "
          'itself)',
          all(k == '⌘K' or re.search(r"e\.key === '%s'" % re.escape(k.lower()), app)
              for k in hud_keys),
          hud_keys)
    # What the removed "/ — graph filter" claim would need is a DOCUMENT-
    # level keydown listener (a slash typed anywhere on the graph view) or
    # a '/'-key handler. Element-level onKeyDown props that activate a
    # focused menu item on Enter/Space are keyboard accessibility, not a
    # shortcut — they cannot see a '/' typed outside their own element, so
    # they cannot make the old claim true. Pin the two things that could.
    check('views/graph.jsx still has no global keydown listener — the '
          '"/ — graph filter" claim would need one and never had one',
          "addEventListener('keydown'" not in graph
          and 'addEventListener("keydown"' not in graph,
          'views/graph.jsx now has a global keydown listener — if a real '
          'graph filter shortcut was added, this test (and the fix above) '
          'should be revisited, not just this one check loosened')
    check("...and none of its element-level key handlers looks at '/'",
          not re.search(r"key === '/'|key === \"/\"", graph),
          "a '/'-branch inside an element handler would be the shortcut "
          'sneaking back in under the accessibility flag')
    check('...and its element-level handlers are activation only '
          '(Enter/Space), which a shortcut cannot ride',
          all("'Enter'" in m or '"Enter"' in m
              for m in re.findall(r'onKeyDown: \(ev\) => \{[^\n]*', graph)),
          re.findall(r'onKeyDown: \(ev\) => \{[^\n]*', graph))
    check("no 'p'/'P'/KeyP handler exists anywhere in app.jsx — the "
          '"⌘P — graph palette" claim never had one either',
          not re.search(r"e\.key\.toLowerCase\(\) === 'p'|e\.key === 'p'|e\.key === 'P'|code === 'KeyP'", app),
          '')
    check("app.jsx's real '/' handler focuses the chat composer, matching "
          "ShortcutHud's own '/ — Focus chat' entry (not a graph filter)",
          "e.key === '/'" in app
          and re.search(r"e\.key === '/'\)[^\n]*composer textarea", app) is not None,
          'app.jsx: the / handler changed shape')

    print()
    if FAILS:
        print(f'shortcuts command: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:5]))
        return 1
    print('shortcuts command: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
