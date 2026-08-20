#!/usr/bin/env python3
"""The command palette's "DM @agent" entries and "Recent chat" jump-to-
message entries (app/commands.jsx:137-153, one per hired coworker and one
per of the last 25 chat messages) called handlers in app.jsx that opened
the wrong view, wrote to a prefill channel nothing reads, and — in
desktop/windowed mode — actively closed an already-open chat panel right
before toasting a false "ready" claim.

`onDmAgent` called `goTo('visual')` — the Office floor view (`case
'visual'` in `renderViewBody`), NOT `case 'chat'` — then wrote
`localStorage.setItem(k('composer_prefill'), ...)`. A repo-wide grep for
`composer_prefill` turns up exactly that one line: nothing else in the
codebase reads it. The real, working prefill bridge is the
`cafresohq:prefill-composer` CustomEvent, dispatched by
`onAssignTaskToChat` (app.jsx) and consumed by `ui/chat.jsx`'s
`ChatPanel` listener, which calls `setInput(text)` and focuses the
composer.

`onJumpToMessage` had the same `goTo('visual')` mistake, with no
`cafresohq:set-active-thread` dispatch at all — so even once chat
correctly opens, the referenced message's own thread (`msg.thread`)
was never selected; `visibleChat` filters strictly by `activeThread`,
so a message from a project/meeting thread would not even be on
screen once the panel opened.

Worse: in desktop mode, `navTo`'s `'visual'` branch
(`if (view === 'visual') setChatWinOpen(false)`, with its own
"the office is the wallpaper" comment) exists specifically to CLOSE an
open chat panel when navigating to the office floor. So invoking "DM
@agent" while chat was already open actively closed it, then told the
boss the composer was ready. On narrow/mobile viewports the floating
`ChatWindow` never renders at all (gated on `!isNarrowViewport`), and
the full-screen chat view needs `activeView === 'chat'`, which
`goTo('visual')` never sets either.

**The fix** routes both handlers through `goTo('chat')` — the same verb
the app's own coach-mark ("Open chat" cta) and the Rail's `onOpenChat`
use, explicitly documented at app.jsx as "the one navigation verb" that
"routes chat correctly in BOTH modes" — plus the real
`cafresohq:set-active-thread`/`cafresohq:prefill-composer` events,
matching `onAssignTaskToChat` and `InspectPanel`'s `onMessage` exactly.
`onJumpToMessage` sets the active thread to `msg.thread || 'direct'`
(not just a hardcoded `'direct'`) so the referenced message is actually
on screen once chat opens.

Run: python3 scripts/test_command_palette_dm_opened_the_office_not_chat.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
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
    print('Command palette DM/jump-to-message now open chat, not the '
          'Office floor, and use the real prefill/thread bridge')

    app_src = APP.read_text(encoding='utf-8')
    chat_src = CHAT.read_text(encoding='utf-8')

    check('composer_prefill localStorage key is gone from app.jsx '
          '(dead channel nothing read)',
          'composer_prefill' not in app_src, 'still present somewhere')

    dm_fn = extract(app_src, 'onDmAgent={(agent) => {', '\n      }}')
    check('extracted onDmAgent handler', 'goTo' in dm_fn,
          'app.jsx shape changed')
    check("onDmAgent calls goTo('chat'), not goTo('visual')",
          "goTo('chat')" in dm_fn and "goTo('visual');" not in dm_fn, dm_fn)
    check('onDmAgent dispatches cafresohq:set-active-thread (direct)',
          "cafresohq:set-active-thread" in dm_fn and "detail: 'direct'" in dm_fn, dm_fn)
    check('onDmAgent dispatches the real cafresohq:prefill-composer event',
          'cafresohq:prefill-composer' in dm_fn, dm_fn)

    jump_fn = extract(app_src, 'onJumpToMessage={(msg) => {', '\n      }}')
    check('extracted onJumpToMessage handler', 'goTo' in jump_fn,
          'app.jsx shape changed')
    check("onJumpToMessage calls goTo('chat'), not goTo('visual')",
          "goTo('chat')" in jump_fn and "goTo('visual');" not in jump_fn, jump_fn)
    check("onJumpToMessage dispatches cafresohq:set-active-thread with the "
          "message's own thread, not a hardcoded 'direct'",
          "detail: msg.thread || 'direct'" in jump_fn, jump_fn)

    check('the real prefill-composer listener still exists in ui/chat.jsx',
          "addEventListener('cafresohq:prefill-composer'" in chat_src,
          'ui/chat.jsx shape changed')
    check('visibleChat still filters strictly by activeThread (confirms '
          'why the thread-select dispatch matters)',
          "t === activeThread" in chat_src, 'ui/chat.jsx shape changed')

    def drive(fn_src, event_name, arg_json):
        harness = """
const calls = { goTo: [], dispatched: [], toasts: [] };
const goTo = (v) => calls.goTo.push(v);
class CustomEvent { constructor(type, opts) { this.type = type; this.detail = opts && opts.detail; } }
const window = {
  dispatchEvent: (e) => calls.dispatched.push({ type: e.type, detail: e.detail }),
  cafresohqToast: { info: (msg, opts) => calls.toasts.push(msg) },
};
const handler = %s;
handler(%s);
console.log(JSON.stringify(calls));
""" % (fn_src, arg_json)
        return run(harness)

    dm_body = 'agent => {' + dm_fn[dm_fn.index('=> {') + len('=> {'):dm_fn.rindex('\n      }')] + '\n}'
    dm = drive(dm_body, 'cafresohq:prefill-composer', json.dumps({'name': 'Aria', 'id': 'a1'}))
    check('onDmAgent: navigates to chat exactly once',
          dm['goTo'] == ['chat'], dm)
    check('onDmAgent: sets active thread to direct',
          {'type': 'cafresohq:set-active-thread', 'detail': 'direct'} in dm['dispatched'], dm)
    check('onDmAgent: prefills the composer with the @-mention via the real event',
          {'type': 'cafresohq:prefill-composer', 'detail': '@Aria '} in dm['dispatched'], dm)
    check('onDmAgent: still toasts a ready message',
          len(dm['toasts']) == 1 and 'Aria' in dm['toasts'][0], dm)

    jump_body = 'msg => {' + jump_fn[jump_fn.index('=> {') + len('=> {'):jump_fn.rindex('\n      }')] + '\n}'
    jump_project = drive(jump_body, 'cafresohq:set-active-thread',
                         json.dumps({'name': 'Aria', 'text': 'shipped the fix', 'thread': 'project:p1'}))
    check('onJumpToMessage: navigates to chat exactly once',
          jump_project['goTo'] == ['chat'], jump_project)
    check("onJumpToMessage: selects the message's OWN thread "
          "(project:p1), not a hardcoded direct",
          {'type': 'cafresohq:set-active-thread', 'detail': 'project:p1'} in jump_project['dispatched'],
          jump_project)

    jump_untagged = drive(jump_body, 'cafresohq:set-active-thread',
                          json.dumps({'name': 'Aria', 'text': 'hey there'}))
    check('onJumpToMessage: an untagged (thread-less) message falls back '
          'to direct, matching visibleChat\'s own default',
          {'type': 'cafresohq:set-active-thread', 'detail': 'direct'} in jump_untagged['dispatched'],
          jump_untagged)

    print()
    if FAILS:
        print(f'command palette DM/jump: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:5]))
        return 1
    print('command palette DM/jump: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
