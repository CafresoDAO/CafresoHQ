#!/usr/bin/env python3
"""The CEO's HANDOFF_TO dispatch must run as the boss's streaming turn (ui/chat.jsx).

Bug: in ChatPanel's send(), every await on a coworker dispatch runs inside
setStreaming(true) ... finally setStreaming(false) — the room fan-out,
/brainstorm, the @mention fan-out, a handoff-mode send, and the CEO's
DM fan-out branch — EXCEPT the `if (ceoHandoff && onDispatchToAgent)`
branch. After the CEO turn's own setStreaming(false), that branch awaited
onDispatchToAgent(target, ...) with `streaming` false for the whole
dispatch. Two user-facing consequences:

  1. The composer's action row renders `streaming ? Stop : Send`, so the
     specialist's OPENING reply after "↪ Handed off to X. Talk to them
     directly" — carrying the whole brief, usually the longest turn of the
     exchange — streamed with no ■ Stop on screen. The stop plumbing was
     already alive for exactly this phase (abortRef is deliberately not
     cleared until end-of-turn, and onStopTurn scopes to the turn); the
     only button that reaches it was simply not rendered.

  2. Send stayed enabled, so a second send during that window started a
     new dispatch onto the specialist's still-busy desk — app.jsx's
     busy-desk wait loop assumes "the boss's own sends can't arrive here
     busy (the composer serializes them)", and this was the one gap in
     that serialization (the waiting note then even misattributes the
     boss's message as "the office's note").

Fix: the handoff branch now sets setStreaming(true) before its await and
clears it in a finally, exactly like the sibling DM fan-out branch below it.

This lifts the REAL ChatPanel source out of ui/chat.jsx (brace-balanced
extraction, model: scripts/test_workspace_terminal_key.py), isolates the
`if (ceoHandoff && onDispatchToAgent)` block brace-balanced, and checks the
structural invariant directly: setStreaming(true) before the await, and a
finally that calls setStreaming(false).
Run: python3 scripts/test_ceo_handoff_dispatch_keeps_stop_button_live.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'ui' / 'chat.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def balanced_span(src, start_of_open_brace):
    """Return src[open..close] for the brace opening at the given index."""
    depth = 0
    j = start_of_open_brace
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[start_of_open_brace:j + 1]
        j += 1
    return None


def extract_function(src, name):
    """Brace-balanced extraction of `function NAME(...) { ... }` — same
    technique as scripts/test_workspace_terminal_key.py. The (...) skip
    matters: ChatPanel destructures its props, so the first `{` after the
    name is the parameter object, not the body."""
    m = re.search(r'function\s+' + re.escape(name) + r'\s*\([^)]*\)\s*\{', src)
    if not m:
        return None
    body = balanced_span(src, m.end() - 1)
    return None if body is None else src[m.start():m.end() - 1] + body


def strip_comments(src):
    """Drop /* ... */ and // ... so prose about setStreaming can't satisfy
    (or fail) the checks — only executable code counts."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'(?<![:/])//[^\n]*', '', src)


def main():
    print('ChatPanel — CEO HANDOFF_TO dispatch keeps the Stop button live')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    text = SRC.read_text(encoding='utf-8')

    panel = extract_function(text, 'ChatPanel')
    check('ChatPanel extracted from ui/chat.jsx', panel is not None)
    if panel is None:
        print('\n1 failure(s)')
        return 1

    m = re.search(r'if\s*\(\s*ceoHandoff\s*&&\s*onDispatchToAgent\s*\)\s*\{', panel)
    check('found the `if (ceoHandoff && onDispatchToAgent)` branch', m is not None)
    if m is None:
        print('\nFAILED: %s' % FAILS)
        return 1
    block = balanced_span(panel, panel.find('{', m.start()))
    check('handoff branch brace-balanced', block is not None)
    if block is None:
        print('\nFAILED: %s' % FAILS)
        return 1
    code = strip_comments(block)

    # The dispatch this branch exists for must still be there — if it moved,
    # the extraction (and this test's premise) broke: hard fail, not a skip.
    disp = code.find('await onDispatchToAgent')
    check('handoff branch still awaits onDispatchToAgent', disp >= 0)

    # (1) The turn is marked streaming BEFORE the specialist's dispatch —
    # this is what puts ■ Stop on screen and disables the second Send.
    on = code.find('setStreaming(true)')
    check('setStreaming(true) present in the handoff branch', on >= 0)
    check('setStreaming(true) comes before the await', 0 <= on < disp,
          f'setStreaming(true) at {on}, await at {disp}')

    # (2) ...and is released whatever happens, in a finally — a failed
    # handoff must not leave the composer stuck on ■ Stop forever.
    fin = re.search(r'finally\s*\{[^{}]*setStreaming\(false\)', code)
    check('finally { setStreaming(false) } present in the handoff branch',
          fin is not None)

    # Decoy guard: the sibling DM fan-out branch's own pair must be intact —
    # a "fix" that moved the whole thing to one outer wrapper would pass the
    # checks above while silently changing the sibling's behaviour.
    ms = re.search(r'else\s+if\s*\(\s*ceoDms\.length\s*&&\s*onDispatchToAgent\s*\)\s*\{', panel)
    check('sibling `else if (ceoDms.length && ...)` branch still exists', ms is not None)
    if ms is not None:
        sib = strip_comments(balanced_span(panel, panel.find('{', ms.start())) or '')
        check('sibling DM fan-out branch keeps its own setStreaming(true)',
              'setStreaming(true)' in sib)
        check('sibling DM fan-out branch keeps its own setStreaming(false)',
              'setStreaming(false)' in sib)

    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'ceo handoff stop button: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
