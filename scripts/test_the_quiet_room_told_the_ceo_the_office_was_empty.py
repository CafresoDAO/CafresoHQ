#!/usr/bin/env python3
"""The 1:1 quiet room told CafresoHQ that nobody had been hired.

`HQ.ceoStream` builds its own system prompt:

    const sys = system || (buildCeoSystem(agents || [], reg) + ...)

and `buildCeoSystem` opens with `rosterSummary(agents)`, which for an empty
or missing roster is the flat sentence **"No coworkers hired yet."**

Every ceoStream caller in the app passes a roster — ui/chat.jsx sends
`agents`, MeetingRoom sends `participants`, StandupModal sends `agents` —
except FocusMode's separately-written `send()`, which sent `{ chat, signal,
onHint }` and nothing else. So the one screen titled "1:1 WITH CAFRESOHQ",
the room a boss opens to think out loud with their chief of staff, is the
one conversation where the chief of staff has been told in its own system
prompt that the boss has hired nobody. Asked "who should take this?" or
"what is Vera working on?", it either denies a team the boss can see two
feet away or invents one. §4: the office reports what it knows, and it knew
— `agents` was sitting right there in app.jsx's render.

The roster is also what unlocks `dm_to` / `handoff_to` inside ceoStream, and
those markers are HOST-dispatched: ceoStream fires `onTool` and RETURNS,
expecting the caller to deliver. The quiet room has no dispatcher, so the
fix has to carry an `onTool` too — otherwise passing the roster would trade
a lie for a silent drop (truncated reply, nobody messaged, nothing said).

Fix (features.jsx, FocusMode): take an `agents` prop, pass it to ceoStream,
and collect routed DM/HANDOFF targets so an undeliverable hand-off gets one
honest sentence naming the Chat tab as the door. app.jsx passes `agents`.

Run: python3 scripts/test_the_quiet_room_told_the_ceo_the_office_was_empty.py
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
FEATURES = ROOT / 'features.jsx'
APP = ROOT / 'app.jsx'
RUNTIME = ROOT / 'hq-runtime.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('the 1:1 quiet room hands CafresoHQ the real roster')

    src = FEATURES.read_text(encoding='utf-8')
    runtime = RUNTIME.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')

    # --- the premise: an empty roster really is a claim about the office ---
    check('rosterSummary() still says "No coworkers hired yet." for an '
          'empty roster (the sentence the quiet room was sending)',
          'No coworkers hired yet.' in runtime)
    check('ceoStream still builds its system prompt from `agents` via '
          'buildCeoSystem',
          re.search(r'buildCeoSystem\(agents \|\| \[\]', runtime) is not None)

    fm = re.search(r"function FocusMode\(\{.*?\n\}\n", src, re.S)
    check('found FocusMode in features.jsx', fm is not None)
    body = fm.group(0) if fm else ''

    check('FocusMode takes an `agents` prop',
          re.search(r'function FocusMode\(\{[^)]*\bagents\b', body) is not None,
          'signature is: ' + body.splitlines()[0] if body else '')

    # Paren-matched, not regex-matched: the options object contains its own
    # `);` (the onTool arrow body), so a lazy regex stops halfway through it.
    def options_object(text, marker):
        i = text.find(marker)
        if i < 0:
            return None
        i += len(marker)
        j = text.find('{', i)
        if j < 0:
            return None
        depth = 0
        for k in range(j, len(text)):
            if text[k] == '{':
                depth += 1
            elif text[k] == '}':
                depth -= 1
                if depth == 0:
                    return text[j:k + 1]
        return None

    opts = options_object(body, 'HQ.ceoStream(text, flush,')
    check("found FocusMode's ceoStream options object", opts is not None)
    opts = opts or ''

    check('the quiet room sends the roster to ceoStream — without it the '
          'chief of staff is told "No coworkers hired yet." on the one '
          'screen dedicated to talking to it',
          re.search(r'(^|[\s{,])agents\s*(,|\}|$)', opts) is not None,
          'options passed: ' + ' '.join(opts.split()))

    # --- the consequence the fix must not create: a silent drop ---
    check('the roster unlocks dm_to/handoff_to for the CEO (so the quiet '
          'room now has to answer for them)',
          re.search(r'if \(\(agents \|\| \[\]\)\.length\) \{\s*\n?\s*ceoTools\.push\(TOOL_REGISTRY\.dm_to',
                    runtime) is not None)
    check('DM_TO is host-dispatched — ceoStream fires onTool and returns, '
          'it does not deliver anything itself',
          re.search(r"onTool\(\{ phase: 'dm'", runtime) is not None)
    check('FocusMode passes an onTool so a routed hand-off is not silently '
          'swallowed by a room with no dispatcher',
          'onTool' in opts, 'options passed: ' + ' '.join(opts.split()))
    check('an undeliverable hand-off gets one honest sentence naming the '
          'door out (§7), not silence',
          re.search(r'routed\.length', body) is not None
          and 'Chat tab' in body,
          'no note found in send()')

    fm_tag = re.search(r'<FocusMode\b.*?/>', app, re.S)
    check('found the <FocusMode> render in app.jsx', fm_tag is not None)
    check('app.jsx hands FocusMode the live roster',
          fm_tag is not None and 'agents={agents}' in fm_tag.group(0),
          'rendered as: ' + (' '.join(fm_tag.group(0).split()) if fm_tag else '?'))

    # --- live: run the real ceoStream option object against real helpers ---
    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted '
          'call below)', has_node, 'skipping the live-execution check')

    if has_node and opts:
        # rosterSummary + buildCeoSystem, verbatim in shape, fed by whatever
        # the REAL options object in features.jsx actually carries.
        js = """
        const agents = [
          { id: 'a1', name: 'Vera', role: 'Analyst', status: 'idle', tools: [] },
          { id: 'a2', name: 'Kip', role: 'Writer', status: 'idle', tools: [] },
        ];
        const text = 'who should take this?';
        const flush = () => {};
        const pending = [];
        const controller = { signal: {} };
        const routed = [];
        let seen = null;
        const HQ = { ceoStream: (p, f, o) => { seen = o; } };
        HQ.ceoStream(text, flush, %s);
        const roster = (seen && seen.agents && seen.agents.length)
          ? 'Your coworkers:\\n' + seen.agents.map(a => '- ' + a.name).join('\\n')
          : 'No coworkers hired yet.';
        console.log(JSON.stringify({ roster, hasOnTool: !!(seen && seen.onTool) }));
        """ % opts.strip()
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the extracted call ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-500:])
        if r.returncode == 0:
            out = json.loads(r.stdout.strip().splitlines()[-1])
            check("the system prompt the quiet room's CEO gets names the "
                  "boss's actual coworkers, not 'No coworkers hired yet.'",
                  out.get('roster', '').startswith('Your coworkers:'),
                  out.get('roster'))
            check('and a hand-off it routes has somewhere to be reported',
                  out.get('hasOnTool') is True)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
