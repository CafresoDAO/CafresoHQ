#!/usr/bin/env python3
"""Focus Mode — the "1:1 WITH CAFRESOHQ / quiet room · no distractions"
overlay reached from the office sofa, the CEO Panel's "Sit 1:1", and the
`f` shortcut — rendered `chat.slice(-12)` with no thread filter at all.

`chat` (app.jsx) is the single, app-wide, cross-thread message array:
coworker-to-coworker DM relays, hire proposals, budget/depth-cap notices
and more all get pushed there tagged `thread: 'team'` (33+ separate call
sites in app.jsx), alongside `project:<id>`/`meeting:<id>` room traffic.
`FocusMode` showed all of it, unfiltered — the opposite of "no
distractions" the room's own copy promises. `ui/chat.jsx`'s own chat
panel already has the correct pattern for this (`visibleChat` filters by
`(m.thread || 'direct') === activeThread`); `FocusMode` never mirrored
it.

Compounding it, the avatar logic showed the CafresoHQ mascot sprite for
ANY non-user sender — including `from: 'agent'` messages, which really
do land in the (untagged, so effectively 'direct') thread by design: a
delegated task's reply (app.jsx, `setChat(prev => [...prev, ..., {
from: 'agent', name: ... }])` with no `thread` field) is a real
coworker speaking, not the CEO, and would have been drawn wearing the
CEO's own mascot icon inside a room titled "1:1 WITH CAFRESOHQ".

**The fix** filters to `(m.thread || 'direct') === 'direct'` before
slicing to the last 12, matching `ui/chat.jsx`'s own convention exactly,
and only shows the CafresoHQ sprite for `m.from === 'ceo'` — any other
non-user sender that legitimately lands in the direct thread gets a
generic first-letter avatar (same visual language as the existing user
"B" square) instead of the CEO's own icon.

Run: python3 scripts/test_focus_mode_quiet_room_showed_every_thread.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURES = ROOT / 'features.jsx'
CHAT = ROOT / 'ui' / 'chat.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the real file')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('Focus Mode\'s "quiet room" now shows only the direct thread, '
          'and only the CEO wears the CEO\'s icon')

    src = FEATURES.read_text(encoding='utf-8')
    chat_src = CHAT.read_text(encoding='utf-8')

    check('extracted the real filter+slice expression from FocusMode',
          "chat.filter(m => (m.thread || 'direct') === 'direct').slice(-12)" in src,
          'features.jsx: FocusMode render shape changed')
    check("FocusMode's avatar only Sprites the CEO, not every non-user sender",
          "m.from === 'ceo'\n                  ? <Sprite data=\"cafresohq\" scale={1}/>" in src,
          'features.jsx: avatar ternary shape changed')
    check('a non-user, non-ceo sender (e.g. an agent\'s delegated-task '
          'reply) now gets a generic letter avatar instead of the CEO\'s '
          'own mascot',
          "{(m.name || 'A').charAt(0).toUpperCase()}" in src,
          'features.jsx: fallback avatar branch missing')
    check('ui/chat.jsx\'s own visibleChat filter is still the (m.thread || '
          "'direct') === activeThread convention FocusMode now mirrors",
          "const t = m.thread || 'direct';" in chat_src and "return t === activeThread;" in chat_src,
          'ui/chat.jsx shape changed')

    # Drive the real filter expression lifted from the file, not a
    # reimplementation, against a representative mixed-thread mock chat.
    filter_expr = "m => (m.thread || 'direct') === 'direct'"
    check('the filter expression appears verbatim (so the harness below '
          'is really exercising the shipped code)',
          filter_expr in src, 'features.jsx: filter predicate text changed')

    def drive_filter():
        harness = """
const chat = [
  { id: 'm1', from: 'user', name: 'You', text: 'hey', thread: undefined },
  { id: 'm2', from: 'ceo', name: 'CafresoHQ', text: 'hi boss' },
  { id: 'm3', from: 'system', name: 'HQ', text: 'DM budget hit', thread: 'team' },
  { id: 'm4', from: 'agent', name: 'Nova · Research Analyst', text: 'shipped the report', thread: 'team' },
  { id: 'm5', from: 'agent', name: 'Kip · Engineer', text: 'reviewed the PR', thread: 'project:p1' },
  { id: 'm6', from: 'system', name: 'HQ', text: 'meeting note', thread: 'meeting:m1' },
  { id: 'm7', from: 'agent', name: 'Nova · Research Analyst', text: 'delegated task reply', thread: undefined },
];
const filtered = chat.filter(%s);
console.log(JSON.stringify(filtered.map(m => m.id)));
""" % filter_expr
        return run(harness)

    ids = drive_filter()
    check('team-thread messages (system budget notice, agent relay) are excluded',
          'm3' not in ids and 'm4' not in ids, ids)
    check('project/meeting-thread messages are excluded',
          'm5' not in ids and 'm6' not in ids, ids)
    check('the untagged user message and the ceo reply survive (the real '
          '1:1)',
          'm1' in ids and 'm2' in ids, ids)
    check('an untagged agent message (e.g. a delegated task\'s reply) still '
          'lands in direct by the app\'s own convention — this is exactly '
          'why the avatar fix (not just the thread filter) was needed',
          'm7' in ids, ids)

    print()
    if FAILS:
        print(f'focus mode thread leak: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:5]))
        return 1
    print('focus mode thread leak: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
