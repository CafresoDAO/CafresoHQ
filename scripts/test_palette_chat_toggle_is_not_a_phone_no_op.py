#!/usr/bin/env python3
"""The palette's chat entry described a window a phone never has.

`AppGlobalCommands` (app/commands.jsx) registers a `tog.chat` command,
shown on the Projects and Library views:

    label: chatWinOpen ? 'Close chat window' : 'Open chat window',
    run:   () => setChatWinOpen(v => !v),

`chatWinOpen` only means anything where the floating <ChatWindow> is
mounted, and app.jsx mounts it behind `!isNarrowViewport` (a 768px media
query):

    {(desktopMode || activeView !== 'chat') && !isNarrowViewport && (
      <ChatWindow open={chatWinOpen} setOpen={setChatWinOpen} ... />
    )}

So on a phone the setter flips a flag nothing renders — a silent no-op.
This is the same trap the RAIL was already moved off this very setter to
avoid; app.jsx says so in as many words: "navTo, not setChatWinOpen — it
already routes chat correctly in BOTH modes (desktop opens the floating
panel, narrow switches the view), so the rail can't drift from the rest
of the app." The palette was the surface still drifting.

Worse than a dead entry: `chatWinOpen` is `useStored(k('chatWinOpen'),
true)` — persisted, default TRUE. So on a phone sitting on Projects the
palette normally read **"Close chat window"**, over a chat that was not
on screen, and running it "closed" the flag. The boss was offered a close
verb for a thing they could not see and never offered an open one.

Fix: the entry takes `chatWindowMounted` (app.jsx passes
`!isNarrowViewport`, the same gate the window itself uses). It offers
"Close chat window" only where that window exists; otherwise it offers
"Open chat" and routes through `navigate` — navTo, the one verb that
opens chat in both modes.

This test executes the real `tog.chat` object literal lifted verbatim
from app/commands.jsx under node, in three viewport/state combinations.

Run: python3 scripts/test_palette_chat_toggle_is_not_a_phone_no_op.py
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMANDS = ROOT / 'app' / 'commands.jsx'
APP = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract_literal(src, marker):
    """Return the balanced { ... } object literal that starts at `marker`."""
    i = src.find(marker)
    if i < 0:
        return None
    depth = 0
    for j in range(i, len(src)):
        c = src[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    return None


def main():
    print("the palette's chat entry is not a silent no-op on a phone")

    src = COMMANDS.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')

    lit = extract_literal(src, "{ id: 'tog.chat',")
    check("the tog.chat command literal is still findable in app/commands.jsx",
          lit is not None, 'app/commands.jsx: no `{ id: \'tog.chat\',`')
    if lit is None:
        print(f'{len(FAILS)} FAILED')
        return 1

    # The window's own mount gate, quoted so this test fails loudly if the
    # premise (a phone has no floating chat window) ever stops being true.
    check("app.jsx still mounts <ChatWindow> only on a wide viewport "
          "(`!isNarrowViewport`) — the premise of this bug",
          re.search(r"activeView !== 'chat'\)\s*&&\s*!isNarrowViewport", app)
          is not None,
          'app.jsx: ChatWindow mount gate changed shape')

    check("app.jsx hands the palette that same gate as chatWindowMounted",
          re.search(r"chatWindowMounted=\{!isNarrowViewport\}", app) is not None,
          'app.jsx: chatWindowMounted prop not passed to AppGlobalCommands')

    check("chatWindowMounted is listed in the useCommands deps array, so "
          "rotating a tablet across 768px re-registers the entry",
          re.search(r"useCommands\(cmds, \[(.*?)\]\);", src, re.S)
          and re.search(r"\bchatWindowMounted\b",
                        re.search(r"useCommands\(cmds, \[(.*?)\]\);",
                                  src, re.S).group(1)) is not None,
          'app/commands.jsx: deps array missing chatWindowMounted')

    harness = """
const RESULTS = [];
function build(activeView, chatWinOpen, chatWindowMounted) {
  const calls = { navigate: [], setChatWinOpen: [] };
  const navigate = (v) => calls.navigate.push(v);
  const setChatWinOpen = (v) => calls.setChatWinOpen.push(
    typeof v === 'function' ? 'updater' : v);
  const cmd = %s;
  return { cmd, calls, navigate, setChatWinOpen };
}

// 1. A phone (no floating window) sitting on Projects, with the PERSISTED
//    chatWinOpen === true it ships with.
{
  const { cmd, calls } = build('projects', true, false);
  cmd.run();
  RESULTS.push({ case: 'phone', label: cmd.label,
                 visible: cmd.when === true, calls });
}
// 2. A desktop with the floating window mounted AND open — close is real.
{
  const { cmd, calls } = build('projects', true, true);
  cmd.run();
  RESULTS.push({ case: 'desktop-open', label: cmd.label,
                 visible: cmd.when === true, calls });
}
// 3. A desktop with the window mounted and closed — open it.
{
  const { cmd, calls } = build('vault', false, true);
  cmd.run();
  RESULTS.push({ case: 'desktop-closed', label: cmd.label,
                 visible: cmd.when === true, calls });
}
console.log(JSON.stringify(RESULTS));
""" % lit

    tmp = Path(tempfile.mkdtemp())
    try:
        f = tmp / 'chat_toggle.mjs'
        f.write_text(harness, encoding='utf-8')
        proc = subprocess.run(['node', str(f)], capture_output=True, text=True)
        check('the tog.chat literal runs under node',
              proc.returncode == 0, (proc.stderr or '').strip()[:400])
        if proc.returncode != 0:
            print(f'{len(FAILS)} FAILED')
            return 1
        res = {r['case']: r for r in json.loads(proc.stdout)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    phone = res['phone']
    check('the entry is still offered on Projects/Library',
          phone['visible'] and res['desktop-closed']['visible'], res)

    check("on a phone the entry does NOT offer to close a window that "
          "isn't mounted",
          'Close' not in phone['label'],
          f"label was {phone['label']!r} with chatWinOpen persisted true")
    check("on a phone it offers to OPEN chat instead",
          'Open' in phone['label'], phone['label'])
    check("on a phone running it routes through navigate('chat') — the "
          "verb that switches to the chat view in narrow mode",
          phone['calls']['navigate'] == ['chat'], phone['calls'])
    check("...and does not just flip the flag nothing renders",
          phone['calls']['setChatWinOpen'] == [], phone['calls'])

    d_open = res['desktop-open']
    check('on a desktop with the window open the entry still says Close',
          d_open['label'] == 'Close chat window', d_open['label'])
    check('...and closing still goes through setChatWinOpen (explicitly '
          'false, not a blind toggle)',
          d_open['calls']['setChatWinOpen'] == [False]
          and d_open['calls']['navigate'] == [], d_open['calls'])

    d_closed = res['desktop-closed']
    check('on a desktop with the window closed the entry says Open',
          'Open' in d_closed['label'] and 'Close' not in d_closed['label'],
          d_closed['label'])
    check("...and opening goes through navigate('chat') there too, so one "
          'verb serves both modes',
          d_closed['calls']['navigate'] == ['chat']
          and d_closed['calls']['setChatWinOpen'] == [], d_closed['calls'])

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
