#!/usr/bin/env python3
"""FocusMode's send() erased messages that landed since the last render.

`chat` is the single app-wide, cross-thread array (team-DM relays, project
and meeting rooms, background coworker streams all live in it, tagged only
by m.thread). FocusMode (features.jsx) captured the render-time snapshot
and then wrote it back whole:

    const pending = [...chat, userMsg];
    setChat(pending);              // <- replace, from a stale closure

React applies queued updates in order, but a VALUE update is a replace: any
functional append a background coworker made between FocusMode's last
render and the boss pressing SEND (an agent DM, a research line, a token
flush from another thread's stream — they arrive 30-100x/sec while
streaming) is evaluated first and then thrown away when the replace lands.
The message is gone from state, and the office persists `chat`, so it is
gone from the saved office too.

ui/chat.jsx's send() had this exact bug and carries the fix with its own
comment — "The state write is an APPEND — `[...chat, userMsg]` from a stale
closure used to replace the whole array, erasing anything that had landed
since the last render (agent DMs, research lines). An append cannot do
that, whatever it is holding." FocusMode's send() was written separately
and, as two other comments inside it already record for different halves of
that function, never inherited the sibling's fixes.

Fix: `setChat(p => [...p, userMsg])`. `pending` stays as built — it is only
the context snapshot handed to HQ.ceoStream, same split ui/chat.jsx makes.

Run: python3 scripts/test_focus_mode_send_appends_instead_of_replacing_chat.py
(skips the live-execution check if `node` isn't on PATH — the source-shape
checks still run everywhere)
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURES = ROOT / 'features.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("FocusMode send() appends the boss's message instead of replacing the whole chat array")

    src = FEATURES.read_text(encoding='utf-8')

    fm = re.search(r"function FocusMode\(\{.*?\n\}\n", src, re.S)
    check('found FocusMode in features.jsx', fm is not None)
    body = fm.group(0) if fm else ''

    pending_m = re.search(r"const pending = \[\.\.\.chat, userMsg\];", body)
    check('the model-context snapshot (`pending`) is still built from the '
          'render-time chat — that half is fine and stays', pending_m is not None)

    # The first setChat after `pending` is the state write under test.
    tail = body[pending_m.end():] if pending_m else ''
    write_m = re.search(r"setChat\(([^\n;]*)\);", tail)
    check('found the state write that lands the user message', write_m is not None)
    write_arg = write_m.group(1).strip() if write_m else ''

    check('the state write is a functional APPEND, not a whole-array '
          'replace from the stale closure (the regression: '
          '`setChat(pending)` erased anything a background coworker '
          'appended since the last render)',
          write_arg != 'pending' and 'userMsg' in write_arg and '=>' in write_arg,
          f'writes `setChat({write_arg})` instead')

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted '
          'write below)', has_node, 'skipping the live-execution check')

    if has_node and pending_m and write_m:
        # Re-enact React's update queue: a background coworker's functional
        # append is already queued/applied to live state when FocusMode's
        # write is processed. A value write replaces whatever is there; a
        # functional write reads it. Execute the REAL lines from the source.
        js = f"""
        // Live state: the boss's last question, plus a DM a background
        // coworker appended AFTER FocusMode's last render.
        let state = [
          {{ id: 'm1', from: 'user', name: 'You', text: 'earlier' }},
          {{ id: 'bg1', from: 'agent', name: 'Vera', text: 'research line', thread: 'direct' }},
        ];
        // FocusMode's render-time snapshot: it never saw bg1.
        const chat = [ state[0] ];
        const userMsg = {{ id: 'u2', from: 'user', name: 'You', text: 'hi' }};
        const setChat = (v) => {{ state = (typeof v === 'function') ? v(state) : v; }};

        {pending_m.group(0)}
        setChat({write_arg});

        console.log(JSON.stringify({{
          ids: state.map(m => m.id),
          contextIds: pending.map(m => m.id),
        }}));
        """
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the extracted lines ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-500:])
        if r.returncode == 0:
            import json
            out = json.loads(r.stdout.strip().splitlines()[-1])
            check("Vera's background message survives the boss pressing "
                  "SEND (before the fix the replace erased it from state "
                  "— and the office persists chat, so from disk too)",
                  out.get('ids') == ['m1', 'bg1', 'u2'], out.get('ids'))
            check('the model-context snapshot still ends with the new '
                  'user message (the fix must not change what the CEO '
                  'is sent)',
                  out.get('contextIds', [])[-1:] == ['u2'], out.get('contextIds'))

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
