#!/usr/bin/env python3
"""InspectPanel kept showing a coworker's OLD tools, brain and color after
they were edited in Settings, for as long as the panel stayed open.

`#248` (docs/OFFICE_AS_INTERFACE.md) already named the root cause and chose
not to fix it: `app.jsx` holds the inspected coworker in its own state —

    const [inspect, setInspect] = useStateA(null);   // set once, by onInspect

and hands that captured object straight to the panel:

    {inspect && <InspectPanel agent={inspect} ... />}

`onUpdateAgent` is immutable (`const next = { ...a, ...patch };`), so an
edit in Settings — model, tools, color, File & shell access, even the name —
lands in the `agents` array as a brand-new object for that id. The `inspect`
object the panel is holding is a different, older reference and is never
reassigned, so every field the card renders straight off `agent` (Brain,
"Can use", the elevated banner, the sprite color, the name in the header)
keeps showing what the coworker looked like at the moment Inspect was
opened, not what Settings just saved.

`#248` fixed exactly one field this way: it noticed the job-description
textarea specifically reverting after a save, and patched THAT one reader
with a ref keyed by `agent.id`, closing with "Nothing upstream changed: the
snapshot stays a snapshot." Nothing else on the card got the same treatment.
Concretely: open Team, click a coworker to inspect them, open Settings ->
Roster in a second view (or after closing Team's own inspect focus) and
flip their Brain to a different model or untick a tool, save — the still-
open Inspect card carries on describing the coworker Settings just changed.

The very next modal in this same file, `FurnishModal`, already re-looks its
subject up in the live roster on every render instead of trusting the
captured object:

    agent={furnishFor ? (agents.find(x => x.id === furnishFor.id) || furnishFor) : null}

`InspectPanel` gets the frozen `inspect` object handed to it directly with
no equivalent lookup. This test extracts the actual `agent={...}` prop
`app.jsx` passes to `<InspectPanel .../>` (not a hand-copied duplicate) and
genuinely executes it under Node against a stale captured object plus a
live `agents` array that has since had that coworker's model, tools and
color all changed, confirming the extracted expression now resolves to the
freshly-edited record.

Run: python3 scripts/test_inspect_panel_reads_live_agents_not_a_frozen_snapshot.py
(skips the live-execution check if `node` isn't on PATH — the source-shape
checks still run everywhere)
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("InspectPanel's `agent` prop reads the live `agents` array, not the frozen `inspect` snapshot")

    src = APP.read_text(encoding='utf-8')

    m = re.search(
        r"<InspectPanel agent=\{(agents\.find\(x => x\.id === inspect\.id\) \|\| inspect|inspect)\}",
        src)
    check('found the <InspectPanel agent={...}> prop', m is not None)
    prop_expr = m.group(1) if m else ''

    check("the agent prop re-looks the coworker up in the live `agents` "
          "array (`agents.find(x => x.id === inspect.id) || inspect`), "
          "not the bare frozen `inspect` state — this is the actual "
          "regression",
          prop_expr == 'agents.find(x => x.id === inspect.id) || inspect',
          f'reads `{prop_expr}` instead')

    check('`inspect` is still set once, by onInspect, and not resynced '
          'from `agents` on every edit (this fix depends on that shape — '
          'it fixes the READ site, not the state itself)',
          'const onInspect = (a) => setInspect(a);' in src)

    # FurnishModal is the reference pattern this fix matches — confirm it's
    # still there, unchanged, a few lines below the InspectPanel mount.
    inspect_m = re.search(r"\{inspect && <InspectPanel agent=", src)
    check('<InspectPanel> mount site still present', inspect_m is not None)
    if inspect_m:
        window = src[inspect_m.end():inspect_m.end() + 2000]
        check('FurnishModal, right below, still re-looks its subject up in '
              'the live roster the same way (the pattern this fix copies)',
              'agents.find(x => x.id === furnishFor.id) || furnishFor' in window)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted '
          'line below)', has_node, 'skipping the live-execution check')

    if has_node and m:
        # The matched text is a JSX attribute value, not a standalone
        # statement — wrap it in a `const` the same way the extracted
        # `peers:` line is wrapped in
        # test_a_busy_desk_wait_stales_the_dm_roster.py, without hand-
        # copying the expression itself.
        line = f'const resolved = {prop_expr};'
        js = f"""
        // Captured the moment the boss clicked to inspect Vera — before
        // any Settings edit. This is the object `inspect` state is still
        // holding, unreassigned, for as long as the panel stays open.
        const inspect = {{ id: 'a_vera', name: 'Vera', role: 'Research',
                            model: 'anthropic:claude-3-haiku', color: 'blue',
                            tools: ['web'], elevated: false }};
        // Live roster by the time the card is re-rendered: the boss opened
        // Settings -> Roster and changed Vera's brain, granted her the
        // vault, and gave her File & shell access — a NEW object for the
        // same id, per onUpdateAgent's `{{ ...a, ...patch }}`.
        const agents = [
          {{ id: 'a_vera', name: 'Vera', role: 'Research',
             model: 'anthropic:claude-3-5-sonnet', color: 'crimson',
             tools: ['web', 'vault'], elevated: true }},
          {{ id: 'a_milo', name: 'Milo', role: 'Ops' }},
        ];
        {line}
        console.log(JSON.stringify(resolved));
        """
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the extracted line ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-500:])
        if r.returncode == 0:
            resolved = json.loads(r.stdout.strip().splitlines()[-1])
            check('the resolved agent carries the FRESHLY SAVED brain, not '
                  'the one from the moment Inspect was opened',
                  resolved.get('model') == 'anthropic:claude-3-5-sonnet',
                  resolved.get('model'))
            check('...the freshly saved color',
                  resolved.get('color') == 'crimson', resolved.get('color'))
            check('...the freshly saved tools (now includes vault)',
                  resolved.get('tools') == ['web', 'vault'], resolved.get('tools'))
            check('...the freshly saved File & shell access grant',
                  resolved.get('elevated') is True, resolved.get('elevated'))

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
