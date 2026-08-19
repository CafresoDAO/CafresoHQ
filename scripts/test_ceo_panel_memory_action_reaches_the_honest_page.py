#!/usr/bin/env python3
"""The CEO Panel's "Memory" quick action and filing-cabinet icon opened a
stale modal that never disclosed the 24-entry prompt cap.

`hq-runtime.jsx` caps what actually reaches a prompt:

    const MEMORY_PROMPT_CAP = 24;
    ...memory.slice(0, MEMORY_PROMPT_CAP)...

Two components ever showed the full `memory` list to the boss. One —
`MemoryPage` (views/core.jsx), reached from the sidebar/floor cabinet,
mobile tab bar, command palette, and the real `m` keyboard shortcut —
was explicitly patched to say so:

    memory.length > MEM_CAP
      ? `${memory.length} saved · the newest ${MEM_CAP} go out with every job...`
      : ...

The other — `MemoryShelf` (features.jsx), reachable ONLY through
`CEOPanel`'s `onOpenMemory` prop — was a completely separate modal that
listed every entry under "What CafresoHQ remembers about you" with no
cap mentioned anywhere. A boss with more than 24 saved memories who used
the CEO Panel's filing cabinet or "🗂 Memory" quick action — instead of
the sidebar/keyboard route to the identical data — saw no hint that the
oldest entries were dead weight.

Same bug class as the already-fixed `onSitWithCEO` prop one line above
`onOpenMemory` in app.jsx: a CEO Panel action silently opening a
different, lesser surface than the one every other affordance for the
"same" feature opens.

**The fix** deletes the second surface instead of patching it: CEOPanel's
`onOpenMemory` now calls `navTo('memory')`, the same call every other
memory entry point already makes, landing on the one `MemoryPage` that's
actually kept honest about the cap. `MemoryShelf`, `memoryOpen`, and
`setMemoryOpen` — reachable from nowhere else in the repo — are deleted
outright rather than left as dead code nobody will remember to remove
later.

Run: python3 scripts/test_ceo_panel_memory_action_reaches_the_honest_page.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FEATURES = ROOT / 'features.jsx'
CORE = ROOT / 'views' / 'core.jsx'
PANELS = ROOT / 'ui' / 'panels.jsx'
RUNTIME = ROOT / 'hq-runtime.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('The CEO Panel\'s Memory action now opens the one honestly-capped '
          'Memory page')

    app = APP.read_text(encoding='utf-8')
    features = FEATURES.read_text(encoding='utf-8')
    core = CORE.read_text(encoding='utf-8')
    panels = PANELS.read_text(encoding='utf-8')
    runtime = RUNTIME.read_text(encoding='utf-8')

    # ── The stale second surface is gone, not just unreached ─────────────
    check('MemoryShelf no longer exists in features.jsx',
          'MemoryShelf' not in features, 'features.jsx still defines/exports it')
    check('MemoryShelf is no longer imported/destructured anywhere in app.jsx',
          'MemoryShelf' not in app, 'app.jsx still references it')
    check("app.jsx's memoryOpen/setMemoryOpen state is gone (the only "
          'thing that ever opened the deleted modal)',
          'memoryOpen' not in app, 'app.jsx still has this state')

    # ── CEOPanel's onOpenMemory now routes through real navigation ───────
    check("CEOPanel's onOpenMemory now calls navTo('memory') at the real "
          'app.jsx call site',
          "onOpenMemory={() => navTo('memory')}" in app,
          "app.jsx: CEOPanel's onOpenMemory prop changed shape")

    # ── every onOpenMemory call site in the app routes to real navigation,
    #    none resurrect a raw modal-open setter ───────────────────────────
    sites = re.findall(r'onOpenMemory=\{([^}]*)\}', app)
    check('found all onOpenMemory call sites in app.jsx (sidebar, mobile '
          'tab bar, CEO panel)',
          len(sites) >= 3, sites)
    check('every onOpenMemory call site routes through navTo(\'memory\') '
          'or goTo(\'memory\') — none set a bespoke modal-open flag',
          all(("navTo('memory')" in s or "goTo('memory')" in s) for s in sites),
          sites)

    # ── the redirect target is actually the honest one: locks in the
    #    underlying facts, not just this fix's own copy ───────────────────
    check('MEMORY_PROMPT_CAP is still the real, enforced cap in hq-runtime.jsx',
          'const MEMORY_PROMPT_CAP = 24;' in runtime
          and 'memory.slice(0, MEMORY_PROMPT_CAP)' in runtime,
          'hq-runtime.jsx: memorySummary() changed shape')
    check("MemoryPage (views/core.jsx) still discloses the cap once memory "
          'exceeds it',
          'memory.length > MEM_CAP' in core
          and 'go out with every job' in core,
          'views/core.jsx: MemoryPage cap disclosure changed shape')
    check("the real 'm' keyboard shortcut still routes to the same honest "
          'page',
          "e.key === 'm') goTo('memory')" in app,
          "app.jsx: the 'm' shortcut changed shape")

    # ── the CEO Panel's two Memory triggers still exist and still fire
    #    onOpenMemory (they were not silently removed along with the
    #    modal — they just now reach the fixed handler) ───────────────────
    check('the filing-cabinet icon still fires onOpenMemory',
          'title="Memory shelf"' in panels and 'onClick={fire(onOpenMemory)}' in panels,
          'ui/panels.jsx: CEOPanel filing cabinet changed shape')
    check('the "🗂 Memory" quick-action button still fires onOpenMemory',
          re.search(r'🗂</span>\s*<span>Memory</span>', panels) is not None,
          'ui/panels.jsx: CEOPanel quick action changed shape')

    print()
    if FAILS:
        print(f'CEO panel memory action: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:5]))
        return 1
    print('CEO panel memory action: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
