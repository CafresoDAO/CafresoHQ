#!/usr/bin/env python3
"""The chat composer's Delegate ("HAND OFF TO…") button is reachable from
Direct, any project room, and any meeting room — `ui/chat.jsx` only gates
it off for `'team'`/`'research'` (`isReadOnly`). But `app.jsx`'s
`onDelegate` handler had no idea which room it was invoked from:

  - It scanned the ENTIRE cross-thread `chat` array for "the boss's last
    message" (the empty-composer fallback), not just the active room's —
    so delegating from a project/meeting room with an empty composer
    could hand off unrelated text typed earlier in Direct.
  - It pushed the hand-off's own confirmation bubble and the coworker's
    reply with no `thread` field at all — which `ui/chat.jsx`'s own
    `visibleChat` filter (`(m.thread || 'direct') === activeThread`)
    treats as `'direct'` — so a hand-off made from a project/meeting room
    only ever showed up under the Direct tab.
  - The DM-continuation dispatch hardcoded `originThread: 'direct'`, so
    even a depth-cap failure notice for DMs the delegated coworker sent
    would misfile into Direct instead of the room the hand-off actually
    happened in.

`ui/chat.jsx` already has the correct pattern for this exact class of
bug, one screen away, on the "Ask this again" button: "Scan only THIS
message's thread — the chat array interleaves all threads, so an
unscoped walk could grab a user prompt from a different room." This is
the same gap the previous ledger entry (Focus Mode) asked to be grepped
for elsewhere — `onDelegate` is exactly that "other component."

**The fix** threads `activeThread` through the one call site
(`ui/chat.jsx`'s picker) into `onDelegate(a, typed, thread)`, which
resolves `const t = thread || 'direct'` and uses it to scope the
last-user scan and tag every message the hand-off creates (the
confirmation bubble, the coworker's reply, the "nothing to hand off
yet" notice, the "run was stopped" notice, and the "no such teammate"
notice), and passes `originThread: t` instead of a hardcoded `'direct'`
to the DM-continuation dispatch.

Run: python3 scripts/test_delegate_button_was_thread_blind.py
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


def run(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the real file')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('The Delegate button now knows which room it was invoked from')

    app_src = APP.read_text(encoding='utf-8')
    chat_src = CHAT.read_text(encoding='utf-8')

    check("ui/chat.jsx's picker now passes activeThread to onDelegate",
          'const ok = await onDelegate(a, typed, activeThread);' in chat_src,
          'ui/chat.jsx: picker call site changed shape')

    check('onDelegate now accepts a thread argument',
          'const onDelegate = async (a, typed, thread) => {' in app_src,
          'app.jsx: onDelegate signature changed')
    check("onDelegate resolves it with the same (|| 'direct') fallback "
          "convention as everywhere else in the app",
          "const t = thread || 'direct';" in app_src, 'app.jsx shape changed')

    check("the empty-composer fallback now scans only the active thread, "
          "not the whole cross-thread chat array",
          "const lastUser = [...chat].reverse().find(m => m.from === 'user' "
          "&& !m.delegated && (m.thread || 'direct') === t);" in app_src,
          'app.jsx: lastUser scan changed shape')

    for label, needle in [
        ('the hand-off confirmation bubble',
         "delegated: true, text: `(delegated \"${brief}\" to ${a.name})`, thread: t }"),
        ("the coworker's streaming reply",
         "name: `${a.name} · ${a.role}`, text: '', streaming: true, thread: t }"),
        ('the "nothing to hand off yet" notice',
         "then pick them again.)`, thread: t }"),
        ('the "run was stopped" notice',
         "not sent: the run was stopped.)`, thread: t }"),
        ('the "no such teammate" notice',
         "but no such teammate is hired)`, thread: t }"),
    ]:
        check(f'{label} is tagged with the resolved thread',
              needle in app_src, 'app.jsx: message shape changed — ' + needle)

    check('the DM-continuation dispatch passes originThread: t, not a '
          "hardcoded 'direct'",
          'originThread: t, originAgentId: a.id, parentMessageId: messageId' in app_src,
          'app.jsx: dispatchToAgent call changed shape')
    check("the old hardcoded originThread: 'direct' is gone from this call",
          "originThread: 'direct', originAgentId: a.id, parentMessageId: messageId"
          not in app_src,
          'app.jsx: old hardcode still present')

    check('ui/chat.jsx\'s "Ask this again" precedent this fix mirrors is '
          'still in place',
          "const mThread = m.thread || 'direct';" in chat_src,
          'ui/chat.jsx shape changed')

    # Drive the real (lifted, not reimplemented) lastUser-scan expression
    # against a mock cross-thread chat array.
    scan_expr = ("[...chat].reverse().find(m => m.from === 'user' "
                 "&& !m.delegated && (m.thread || 'direct') === t)")
    check('the scan expression appears verbatim (so the harness below is '
          'really exercising the shipped code)',
          scan_expr in app_src, 'app.jsx: lastUser scan text changed')

    def drive(t):
        harness = """
const chat = [
  { id: 'm1', from: 'user', name: 'You', text: 'old direct ask', thread: undefined },
  { id: 'm2', from: 'user', name: 'You', text: 'delegated wrapper', delegated: true, thread: 'project:p1' },
  { id: 'm3', from: 'user', name: 'You', text: 'the real project ask', thread: 'project:p1' },
  { id: 'm4', from: 'agent', name: 'Nova · Research Analyst', text: 'a reply', thread: 'project:p1' },
];
const t = %s;
const lastUser = %s;
console.log(JSON.stringify(lastUser ? lastUser.id : null));
""" % (json.dumps(t), scan_expr)
        return run(harness)

    direct_result = drive('direct')
    check('scanning with t=direct finds the direct-thread message, not '
          'the project one',
          direct_result == 'm1', direct_result)

    project_result = drive('project:p1')
    check('scanning with t=project:p1 finds the real project ask, '
          'skipping the delegated-wrapper message in the same thread',
          project_result == 'm3', project_result)

    print()
    if FAILS:
        print(f'delegate thread-blindness: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:5]))
        return 1
    print('delegate thread-blindness: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
