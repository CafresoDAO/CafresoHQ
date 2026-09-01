#!/usr/bin/env python3
"""Chat's search deliberately looks across ALL threads (`visibleChat`'s
filter drops the `t === activeThread` check entirely when `searchQuery` is
set) — but quoteReply/startDM used to ignore which thread a search hit
actually came from. They just populated the composer via setInput with no
reference to `m.thread`, and Send always tags the new message with
`thread: activeThread` — whatever tab was active BEFORE the search.

Concrete failure: browsing DIRECT, searching "budget", finding a hit that
was actually said in `project:acme`, clicking quote-reply (↩) or DM (💬),
typing a note, hitting Send — the reply silently lands in DIRECT, not
project:acme. The project's own agents never see it; it shows up out of
context in DIRECT with no error and no visible sign of the mismatch.

The fix (`switchToMessageThread`) mirrors a pattern the file already used
correctly elsewhere — "Ask this again" scopes its own backward walk to
`m.thread || 'direct'` rather than the interleaved chat array — by
switching `activeThread` to the hit's own thread (and clearing the search
filter, so the view actually shows that thread instead of the cross-thread
result list) before touching the composer, or refusing with a toast if the
hit's thread has no composer at all (team/research are read-only).

Run: python3 scripts/test_chat_search_reply_targets_the_right_thread.py
"""
import re
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


def main():
    print("Chat's quote-reply/DM buttons target the search hit's own thread")

    src = CHAT.read_text(encoding='utf-8')

    check('search still deliberately looks across all threads '
          '(the precondition this bug depends on)',
          re.search(r"if \(searchQuery\.trim\(\)\) \{", src) is not None)

    m = re.search(r"const switchToMessageThread = \(\) => \{(.*?)\n          \};", src, re.S)
    check('switchToMessageThread helper exists', m is not None)
    helper = m.group(1) if m else ''

    check("it reads the hit's own thread (m.thread || 'direct'), not activeThread",
          "const targetThread = m.thread || 'direct';" in helper)
    check('it refuses (returns false) for the read-only team/research threads, '
          'which have no composer at all',
          re.search(
              r"targetThread === 'team' \|\| targetThread === 'research'",
              helper) is not None and 'return false;' in helper)
    check('it switches activeThread to the hit\'s thread when it differs',
          re.search(r"targetThread !== activeThread.*?setActiveThread\(targetThread\)",
                     helper, re.S) is not None)
    check('it clears the search filter on switch, so the view actually shows '
          'the destination thread instead of the cross-thread result list',
          "setSearchQuery('')" in helper)

    check('quoteReply calls switchToMessageThread and bails if it refuses',
          re.search(r"const quoteReply = \(\) => \{\s*\n\s*if \(!switchToMessageThread\(\)\) return;",
                     src) is not None)
    check('startDM calls switchToMessageThread and bails if it refuses',
          re.search(r"const startDM = \(\) => \{\s*\n\s*if \(m\.name && m\.from !== 'user'\) \{\s*\n"
                     r"\s*if \(!switchToMessageThread\(\)\) return;", src) is not None)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
