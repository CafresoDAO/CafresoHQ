#!/usr/bin/env python3
"""publishOpen() claimed "link copied" before it had even tried to copy.

Reproduced by reading the source. `views/projects.jsx`'s `publishOpen()`,
on a successful canister publish, used to do:

    setPubMsg({ kind: 'public', url: r.url, text: 'Published — link copied.' });
    try { await navigator.clipboard.writeText(r.url); } catch (_e) {}

The claim was written into state BEFORE the clipboard write was even
attempted, and the write's own failure was silently swallowed by an
empty catch. A user whose clipboard write failed (permission denied,
insecure context, lost focus) saw "Published — link copied." and pasted
nothing — the exact bug class already fixed twice this same day in
views/graph.jsx's Share modal and ui/chat.jsx's copy buttons, in a third,
independent location.

Notably the very next branch in this same function already understood
the principle: the non-canister preview path has a comment reading
"Deliberately NOT copied. The clipboard is what turns 'I looked at a
local link' into 'I sent someone a dead link'" — the author cared about
this distinction and just didn't gate the canister-mode "copied" claim
on the actual write outcome.

Run: python3 scripts/test_published_link_copied_before_it_was_copied.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = (ROOT / 'views/projects.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("published — link copied, before it was copied")

    # `_publishOpen`, not `publishOpen`: `## 392` split the handler into a
    # synchronous double-click claim (`publishOpen`, what the button is
    # wired to) and the publish itself (`_publishOpen`), so the branches
    # this test is about now live in the inner half. The non-greedy match
    # would otherwise stop at the wrapper's own closing brace and find no
    # canister branch at all.
    fn = re.search(r"const _publishOpen = async \(\) => \{[\s\S]*?\n  \};", PROJECTS)
    check('found _publishOpen()', fn is not None)
    body = fn.group(0) if fn else ''

    canister = re.search(r"if \(r\.mode === 'canister'\) \{[\s\S]*?\n      \}", body)
    check('found the canister-mode branch', canister is not None)
    cblock = canister.group(0) if canister else ''

    check('the clipboard write is awaited BEFORE the "copied" claim is set, not after',
          re.search(r"await navigator\.clipboard\.writeText\(r\.url\);\s*\n\s*setPubMsg\(\{ kind: 'public', url: r\.url, text: 'Published — link copied\.' \}\);",
                     cblock) is not None,
          '— the claim must not be written before the write is attempted')
    catch_match = re.search(r"\} catch \(_e\) \{\s*\n\s*setPubMsg\(\{ kind: 'public', url: r\.url, text: '([^']*)' \}\);",
                             cblock)
    check('the catch branch sets a message that does NOT claim the link was copied',
          catch_match is not None and catch_match.group(1) != 'Published — link copied.')
    check('...but still carries the url, so the link stays available to copy by hand',
          re.search(r"catch \(_e\) \{\s*\n\s*setPubMsg\(\{ kind: 'public', url: r\.url,", cblock) is not None)

    # The url is rendered as a link whenever pubMsg.url is set, independent of kind/text —
    # confirms the failure path still gives the user a way to reach the link.
    check('the URL renders as a clickable link whenever pubMsg.url is set (not gated on success)',
          'pubMsg.url &&' in PROJECTS and '<a href={pubMsg.url}' in PROJECTS)

    # The sibling non-canister branch's "deliberately not copied" reasoning is untouched.
    check("the preview-mode branch's own honesty note is untouched",
          "Deliberately NOT copied." in body)

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
