#!/usr/bin/env python3
"""The palette's "DM @agent" prefill vanished if chat was closed.

The command palette's "DM @agent" and "Recent chat" entries
(app/commands.jsx -> onDmAgent / onJumpToMessage in app.jsx) call
goTo('chat') and then dispatch cafresohq:set-active-thread +
cafresohq:prefill-composer in the same synchronous breath. The only
listeners for those events lived inside ChatPanel's mount effect
(ui/chat.jsx) — and ChatPanel is NOT mounted while the chat panel is
closed: ChatWindow returns a collapsed pill without chatPanel
(app/windows.jsx `if (!open)`), and the mobile inline view needs
activeView === 'chat', which goTo has only just requested. React
renders after the handler finishes, so both events fired into a window
with no listener and were lost. Chat opened on whatever thread it was
last on, composer empty — while the toast said "Composer ready for
@X". With the chat window already open everything worked, which is
exactly why it kept looking like it worked.

The fix gives the bridge memory: module-level listeners in ui/chat.jsx
(alive from import time) hold the last dispatch in _chatBridgePending;
ChatPanel replays it on mount, and a live-mounted panel's own handler
clears the slot so nothing ever replays twice.

This test lifts the real pending-buffer block and the real mount-effect
listener/replay code out of ui/chat.jsx and drives them in node:
  1. dispatch with no panel mounted, then mount  -> replayed once
  2. mount a second panel                        -> no double replay
  3. dispatch with a panel mounted               -> handled live, and a
     later fresh mount must NOT replay the stale value

Run: python3 scripts/test_palette_dm_survives_a_closed_chat_panel.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAT = ROOT / 'ui' / 'chat.jsx'
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
        raise SystemExit('node harness failed on source lifted from the real file')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('palette DM survives a closed chat panel '
          '(bridge events are held and replayed on mount)')

    src = CHAT.read_text(encoding='utf-8')

    if '_chatBridgePending' not in src:
        check('ui/chat.jsx has a pending buffer for the chat bridge '
              '(events dispatched while ChatPanel is unmounted are lost '
              'without one)', False, 'no _chatBridgePending in ui/chat.jsx')
        print()
        print('palette DM closed-chat: 1 FAILED — the bridge has no memory')
        return 1

    # The real module-level pending buffer + always-on listeners.
    pending_block = extract(src, 'const _chatBridgePending',
                            "_chatBridgePending.prefill = t;\n  });\n}")
    # The real mount-effect body: listeners + attach + replay.
    effect_body = extract(src, 'const onSet = (e) => {',
                          '\n    return () => {')
    effect_body = effect_body[:effect_body.rindex('return () => {')]

    check('mount effect replays a held thread', 'setActiveThread(_chatBridgePending.thread)' in effect_body,
          'replay code missing from the mount effect')

    harness = """
const listeners = {};
const window = {
  addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
  removeEventListener: (t, fn) => {
    const a = listeners[t] || []; const i = a.indexOf(fn); if (i >= 0) a.splice(i, 1);
  },
  dispatchEvent: (e) => { for (const fn of (listeners[e.type] || []).slice()) fn(e); },
};
class CustomEvent { constructor(type, opts) { this.type = type; this.detail = opts && opts.detail; } }

/* ---- lifted verbatim from ui/chat.jsx (module scope) ---- */
%s
/* ---- end lift ---- */

function mountPanel() {
  const calls = { threads: [], inputs: [] };
  const setActiveThread = (t) => calls.threads.push(t);
  const setInput = (t) => calls.inputs.push(t);
  const composerRef = { current: null };
  const requestAnimationFrame = (fn) => {};
  /* ---- lifted verbatim from ui/chat.jsx (ChatPanel mount effect) ---- */
%s
  /* ---- end lift ---- */
  return { calls, unmount: () => {
    window.removeEventListener('cafresohq:set-active-thread', onSet);
    window.removeEventListener('cafresohq:prefill-composer', onPrefill);
  } };
}

const out = {};

// 1. The palette case: chat CLOSED (no panel mounted), DM dispatches fire.
window.dispatchEvent(new CustomEvent('cafresohq:set-active-thread', { detail: 'direct' }));
window.dispatchEvent(new CustomEvent('cafresohq:prefill-composer', { detail: '@Aria ' }));
const p1 = mountPanel();               // chat opens -> panel mounts
out.replayThreads = p1.calls.threads.slice();  // expect ['direct']
out.replayInputs = p1.calls.inputs.slice();    // expect ['@Aria ']
p1.unmount();

// 2. A second fresh mount must not replay again.
const p2 = mountPanel();
out.secondMountThreads = p2.calls.threads.slice();  // expect []
out.secondMountInputs = p2.calls.inputs.slice();    // expect []

// 3. Live dispatch with a panel mounted: handled once, and a later fresh
//    mount must not resurrect it.
window.dispatchEvent(new CustomEvent('cafresohq:set-active-thread', { detail: 'project:p1' }));
window.dispatchEvent(new CustomEvent('cafresohq:prefill-composer', { detail: 'live text' }));
out.liveThreads = p2.calls.threads.slice();    // expect ['project:p1']
out.liveInputs = p2.calls.inputs.slice();      // expect ['live text']
p2.unmount();
const p3 = mountPanel();
out.staleThreads = p3.calls.threads.slice();   // expect []
out.staleInputs = p3.calls.inputs.slice();     // expect []

console.log(JSON.stringify(out));
""" % (pending_block, effect_body)

    out = run(harness)

    check('a DM dispatched while chat was closed selects the DIRECT '
          'thread once the panel mounts',
          out['replayThreads'] == ['direct'], out)
    check('a DM dispatched while chat was closed prefills the composer '
          'with the @-mention once the panel mounts',
          out['replayInputs'] == ['@Aria '], out)
    check('the replay is consumed — a second mount replays nothing',
          out['secondMountThreads'] == [] and out['secondMountInputs'] == [],
          out)
    check('a live dispatch with the panel mounted is handled exactly once',
          out['liveThreads'] == ['project:p1'] and out['liveInputs'] == ['live text'],
          out)
    check('a live-handled dispatch is not resurrected by a later mount',
          out['staleThreads'] == [] and out['staleInputs'] == [], out)

    print()
    if FAILS:
        print(f'palette DM closed-chat: {len(FAILS)} FAILED — '
              + ', '.join(FAILS[:5]))
        return 1
    print('palette DM closed-chat: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
