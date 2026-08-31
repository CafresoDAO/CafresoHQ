#!/usr/bin/env python3
"""A failed stream rendered exactly like a healthy reply.

All three dispatch catches (the @mention path, the Delegate path, the
CEO path) mark a dead run's bubble `error: true` next to the
chatErrorText they splice in:

    ? { ...m, text: aborted ? ... : chatErrorText(err, ...), error: !aborted }

But nothing in ui/chat.jsx ever READ the flag. A bubble whose stream
died mid-run wore the same face as a finished answer — no visual
distinction at all — and the only retry in the product lived in the
Inbox modal, behind a filter, for registry messages whose cause was
marked retryable. In the transcript itself, the surface where the boss
actually watched the run die, the way forward was to re-type the ask.

The fix is two-part and deliberately small:

  - the bubble shows its state: `msg-error` on the message row and a
    red left border on the bubble, driven by the same `m.error` flag
    the catches already write;
  - a RETRY control under the error text refills the composer with the
    ask that failed — the previous user message in THIS thread, the
    same scoped scan "Ask this again" uses — and focuses the composer.
    It does NOT auto-send: the error text above it usually names a
    cause (a missing key, a rate limit) the boss may need to fix first,
    and re-firing into the same wall would be motion, not progress.

Run: python3 scripts/test_a_dead_run_looks_dead_and_offers_a_way_back.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('a dead run looks dead and offers a way back')
    chatui = strip_comments((ROOT / 'ui' / 'chat.jsx').read_text(encoding='utf-8'))
    app = strip_comments((ROOT / 'app.jsx').read_text(encoding='utf-8'))

    # ── the flag is still written by every catch ────────────────────────
    writes = len(re.findall(r'error: !aborted', app))
    check('all three dispatch catches still mark a dead run', writes == 3, writes)

    # ── and now it is read ──────────────────────────────────────────────
    check('the message row wears the flag',
          "${m.error ? ' msg-error' : ''}" in chatui,
          '— a dead run rendered exactly like a healthy reply')
    check('the bubble shows it too',
          "style={m.error ? {borderLeft:'3px solid var(--danger, #c0504d)'} : undefined}" in chatui)

    # ── the way back ────────────────────────────────────────────────────
    retry = re.search(r'\{m\.error && !m\.streaming \? \([\s\S]*?\) : null\}', chatui)
    check('the retry row exists, only on errored, settled bubbles', bool(retry))
    body = retry.group(0) if retry else ''
    check('it says plainly that the run failed',
          'this run failed' in body)
    check('RETRY refills the composer from THIS thread only',
          "const mThread = m.thread || 'direct';" in body
          and "(chat[i].thread || 'direct') === mThread" in body,
          '— an unscoped walk here is the exact defect class #44/#45 fixed')
    check('...and focuses the composer so Enter is the next keystroke',
          'composerRef.current.focus()' in body)
    check('...and does NOT auto-send',
          'agentStream' not in body and 'onSend' not in body and 'send(' not in body,
          '— the error names a cause the boss may need to fix first; '
          're-firing into the same wall is motion, not progress')

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
