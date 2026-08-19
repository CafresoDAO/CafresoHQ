#!/usr/bin/env python3
"""The Graph's Share modal said "Copied to your clipboard" even when it wasn't.

Reproduced by reading the source. `publish()` (views/graph.jsx) POSTs the
snapshot, gets back a `viewerUrl`, and then does:

    try { await navigator.clipboard.writeText(full); } catch (_) {}

`navigator.clipboard.writeText` can reject for reasons that have nothing to
do with the publish itself — no user-activation context, an insecure
origin, a denied permission, focus lost to another window — and the empty
`catch (_) {}` swallowed every one of them. The modal that opens right
after unconditionally read:

    "Anyone with this link can view this graph (read-only). Copied to
    your clipboard."

A boss who hit Share, got a real failure, and then read "Copied to your
clipboard" had every reason to alt-tab into some other app and hit paste
— and paste nothing, or paste whatever was on the clipboard before. The
one thing on screen claiming success had no connection to whether the
write actually happened.

Run: python3 scripts/test_the_share_modal_promised_a_copy_it_never_made.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH = (ROOT / 'views/graph.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('the Share modal promised a copy it never made')

    # ── 0. the clipboard write really is unguarded fire-and-forget upstream —
    #        confirms this is a real gap, not a hypothetical one ─────────────
    pub = re.search(r"const publish = React\.useCallback\(async \(\) => \{[\s\S]*?\n  \}, \[activePath\]\);", GRAPH)
    check('found the publish() callback', pub is not None)
    body = pub.group(0) if pub else ''

    # ── 1. a state flag now tracks whether the write actually succeeded ────
    check('shareCopied state exists',
          re.search(r"const \[shareCopied, setShareCopied\] = useSV\(", GRAPH) is not None)
    check('publish() resets shareCopied before each attempt',
          re.search(r"setSharing\(true\);\s*\n\s*setShareCopied\(false\);", body) is not None,
          '— a stale true from a previous publish must not survive into a failed one')
    check('publish() sets shareCopied(true) only inside the try that follows a successful write',
          re.search(r"await navigator\.clipboard\.writeText\(full\); setShareCopied\(true\); \}",
                     body) is not None)
    check('...and sets shareCopied(false) in the catch, not just silently swallowing the error',
          re.search(r"catch \(_\) \{ setShareCopied\(false\); \}", body) is not None,
          '— an empty catch here is exactly how the false claim happened')

    # ── 2. the modal copy is now conditional on that flag, not hardcoded ────
    modal = re.search(r"Public graph published[\s\S]{0,400}", GRAPH)
    check('found the share-modal text block', modal is not None)
    mblock = modal.group(0) if modal else ''
    check('the modal no longer states "Copied to your clipboard" unconditionally',
          "'Anyone with this link can view this graph (read-only). Copied to your clipboard.'"
          not in GRAPH,
          '— that string must not appear as a bare literal any more')
    check('...it branches on shareCopied instead',
          'shareCopied ?' in mblock and "'Copied to your clipboard.'" in mblock)
    check('...and tells the truth on the failure path — the link is still usable, just not auto-copied',
          re.search(r"shareCopied \? 'Copied to your clipboard\.' : '[^']*blocked[^']*'", mblock)
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
