#!/usr/bin/env python3
"""Chat's swipe-to-DM action (mobile: swipe left on a coworker's bubble,
tap the 💬 action) inserted the coworker's full display LABEL into the
composer instead of their bare name — e.g. "@Nano · Generalist " instead
of "@Nano ". app.jsx builds agent-authored chat messages with
`name: `${agent.name} · ${agent.role}`` (the label shown under the
bubble), but `startDM` in ui/chat.jsx read that same `m.name` straight
into the @-mention it inserts.

Downstream this didn't just look ugly: `send()` resolves mentions via
HQ.extractAllMentions(text, agents.map(a => a.name)), whose roster is
bare names only. "@Nano · Generalist ..." matches "@Nano" as a valid
mention (nothing requires the character right after the name to be
anything but whitespace) but everything from "· Generalist" onward —
including the literal word "Generalist" — became the delivered message
body. So the DM routed correctly, but every message sent this way
arrived prefixed with a stray role fragment. Found by a background hunt
agent scanning the Projects/Workspace and Chat surfaces (this session's
next-least-scrutinized areas after Team/Settings/Office), confirmed by
tracing m.name's construction in app.jsx and extractAllMentions's actual
parse behavior on the corrupted string.

The fix: `startDM` now looks up the dispatching agent by `m.agentId`
(already set alongside `name` at message-construction time in app.jsx)
in the `agents` prop `ChatPanel` already receives, and mentions
`agent.name` — the bare name — instead of the display label. A fallback
(`String(m.name).split(' · ')[0]`) covers the case where `agentId`
isn't resolvable, so a message from an agent no longer on the roster
still degrades to a plausible bare name instead of an unresolvable
mention.

Verified live UI interaction was blocked this tick by a stuck browser
pane (screenshots rendered, but every click/computer action timed out
with "Browser pane is currently hidden" regardless of viewport preset
or re-selecting the tab) — an environment issue unrelated to this
change, not something this fix caused. Verified instead by static
inspection: confirmed ChatPanel receives `agents` as a prop, confirmed
`m.agentId` is set as a sibling of `m.name` at every agent-dispatch call
site in app.jsx, and confirmed no other call site of `startDM` still
uses `m.name` directly.

Run: python3 scripts/test_chat_swipe_dm_uses_bare_name.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAT = ROOT / 'ui' / 'chat.jsx'
APP = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("Chat's swipe-to-DM inserts the bare agent name, not the display label")

    chat = CHAT.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')

    m = re.search(r"const startDM = \(\) => \{(.*?)\n\s*\};", chat, re.S)
    check('startDM is still defined in ui/chat.jsx', m is not None,
          'ui/chat.jsx: startDM closure not found — rewritten or moved?')
    body = m.group(1) if m else ''

    check('startDM looks up the dispatching agent by m.agentId in the '
          'agents roster (the same prop lookup pattern used elsewhere '
          "in this file, e.g. agents.filter(a => ids.includes(a.id)))",
          re.search(r"agents\.find\(\s*a\s*=>\s*a\.id\s*===\s*m\.agentId\s*\)", body) is not None,
          body)
    check('...and mentions the bare `agent.name`, not the raw m.name '
          'display label ("Nano · Generalist")',
          re.search(r"@\$\{bareName\}", body) is not None
          and 'target.name' in body,
          body)
    check('...with a fallback that strips " · <role>" from m.name if the '
          'agent id can\'t be resolved (message from a departed coworker), '
          'so it degrades gracefully instead of mentioning garbage',
          "split(' · ')[0]" in body,
          body)
    check('startDM no longer inserts the raw m.name straight into the @-mention',
          not re.search(r"`@\$\{m\.name\}", body),
          'ui/chat.jsx: startDM still uses the raw display label')

    check("app.jsx's agent-dispatch message objects still set agentId "
          "alongside the `name` display label (the field startDM's fix "
          "depends on)",
          re.search(r"name:\s*`\$\{agent\.name\}[^`]*`,[^}]*agentId:\s*agent\.id", app) is not None,
          "app.jsx: dispatch message no longer pairs name + agentId")

    check('ChatPanel still receives `agents` as a prop (what the fixed '
          'startDM looks the sender up in)',
          re.search(r"function ChatPanel\(\{[^}]*\bagents\b", chat) is not None,
          'ui/chat.jsx: ChatPanel signature no longer destructures agents')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
