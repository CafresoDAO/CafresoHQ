#!/usr/bin/env python3
"""Chat's Copy buttons said "Copied" whether or not anything got copied.

Reproduced by reading the source. Both copy buttons in ui/chat.jsx — the
per-message Copy action and CodeBlock's copy button — called
`navigator.clipboard.writeText(...)` inside a synchronous try/catch and
then, unconditionally and immediately after, fired a "Copied" success
toast:

    try { navigator.clipboard.writeText(m.text); }
    catch(_e) {}
    if (window.cafresohqToast) window.cafresohqToast.success('Copied');

`writeText` returns a Promise. A synchronous try/catch around a call
whose result is never awaited only catches a synchronous throw (e.g.
`navigator.clipboard` being undefined) — it does nothing for an async
rejection, which is exactly how this API fails in an insecure context,
a popout window without clipboard-write permission (this app explicitly
supports popouts), or a denied permission prompt. The toast fired
regardless, so a user who hit a real failure was told "Copied" and then
pasted nothing.

This is the same bug class as #150 (views/graph.jsx's Share modal,
fixed 2026-08-19), which already carries the correct pattern in this
same codebase: await the write, only claim success inside the try that
follows it, and say something true on the catch path instead of staying
silent.

Run: python3 scripts/test_chat_copy_claimed_success_it_never_checked.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAT = (ROOT / 'ui/chat.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('chat copy claimed success it never checked')

    # ── 0. the old unconditional-toast pattern is gone everywhere in the file ──
    check('no bare unconditional "Copied" toast remains after a fire-and-forget write',
          not re.search(r"clipboard\.writeText\([^)]*\);\s*\n\s*catch\s*\([^)]*\)\s*\{\}\s*\n\s*if \(window\.cafresohqToast\) window\.cafresohqToast\.success\('Copied'\);", CHAT))

    # ── 1. per-message Copy button: awaits the write, toast is inside the try ──
    msg_btn = re.search(r'title="Copy" onClick=\{async \(\) => \{[\s\S]{0,600}?\}\}>📋</button>', CHAT)
    check('per-message Copy button handler found and is now async', msg_btn is not None)
    if msg_btn:
        block = msg_btn.group(0)
        check('...awaits navigator.clipboard.writeText',
              'await navigator.clipboard.writeText(m.text)' in block)
        check('...success toast only fires after a successful await, not unconditionally',
              re.search(r"await navigator\.clipboard\.writeText\(m\.text\);\s*\n\s*if \(window\.cafresohqToast\) window\.cafresohqToast\.success\('Copied'\);",
                         block) is not None)
        check('...catch branch tells the user it failed, rather than staying silent',
              re.search(r"catch \(_e\) \{\s*\n\s*if \(window\.cafresohqToast\) window\.cafresohqToast\.error\(", block)
              is not None)

    # ── 2. CodeBlock's copy(): same shape ────────────────────────────────────
    cb = re.search(r'const copy = async \(\) => \{[\s\S]{0,300}?\};', CHAT)
    check('CodeBlock copy() found and is now async', cb is not None)
    if cb:
        block = cb.group(0)
        check('...awaits navigator.clipboard.writeText',
              'await navigator.clipboard.writeText(body)' in block)
        check('...success toast only fires after a successful await, not unconditionally',
              re.search(r"await navigator\.clipboard\.writeText\(body\);\s*\n\s*if \(window\.cafresohqToast\) window\.cafresohqToast\.success\('Copied'\);",
                         block) is not None)
        check('...catch branch tells the user it failed, rather than staying silent',
              re.search(r"catch \(_\) \{\s*\n\s*if \(window\.cafresohqToast\) window\.cafresohqToast\.error\(", block)
              is not None)

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
