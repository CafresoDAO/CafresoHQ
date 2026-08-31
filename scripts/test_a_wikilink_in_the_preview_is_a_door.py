#!/usr/bin/env python3
"""A [[wikilink]] in the Library preview was an inert chip.

The graph is BUILT from these links, renames rewrite them, the delete
confirm counts them — and clicking one did nothing: renderMarkdown
flattened [[target]] to a plain span.md-tag, cursor:auto, click
swallowed. Driven live before the fix: click landed, nothing opened.

Now renderMarkdown takes {wikilinks:true} (the Library preview only —
the IDE file preview has nothing to open into, so its chips stay
plain and un-clickable-looking) and emits span.md-wikilink carrying
data-wikilink=TARGET, alias and #heading stripped from the target,
alias shown as the text. vault.jsx delegates clicks on the preview:
resolve against the file list by full path or basename (±.md), open
the note, or say '"x" isn't in the Library yet.' for a dead link.
Verified live: path link navigates, [[note|alias]] shows the alias
and resolves the basename, dead link toasts, zero console errors.

Run: python3 scripts/test_a_wikilink_in_the_preview_is_a_door.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, opener):
    i = src.index(opener)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise SystemExit('unbalanced braces lifting ' + opener)


def main():
    print('a wikilink in the preview is a door')
    ide = (ROOT / 'views' / 'ide.jsx').read_text(encoding='utf-8')
    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')

    # ── behavior: run the real renderer in node ─────────────────────────
    fn = brace_lift(ide, 'function renderMarkdown(text, opts)')
    js = (fn + '\n' + 'console.log(JSON.stringify({'
          + 'on: renderMarkdown("see [[Research/x|the x note]] and [[plain#top]]", {wikilinks:true}),'
          + 'off: renderMarkdown("see [[Research/x|the x note]]")'
          + '}));')
    p = subprocess.run(['node', '-e', js], capture_output=True, text=True,
                       timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    r = json.loads(p.stdout.strip().split('\n')[-1])
    check('with wikilinks on, the span carries its target',
          'data-wikilink="Research/x"' in r['on'], r['on'])
    check('...the alias is what the reader sees',
          '>the x note</span>' in r['on'], r['on'])
    check('...a #heading is stripped from the target',
          'data-wikilink="plain"' in r['on'], r['on'])
    check('...and the cursor says door, with a title',
          'cursor:pointer' in r['on'] and 'Open in the Library' in r['on'])
    check('with wikilinks off (IDE preview), the chip stays plain',
          'md-wikilink' not in r['off'] and 'md-tag' in r['off'], r['off'])

    # ── structure: the Library preview opens the door ───────────────────
    check('both Library previews pass wikilinks:true and delegate clicks',
          vault.count('onClick={openWikilink} dangerouslySetInnerHTML='
                      '{{ __html: renderMarkdown(openNote.content, '
                      '{ wikilinks: true }) }}') == 2)
    handler = brace_lift(vault, 'const openWikilink = async (e) => {')
    check('the handler resolves by full path or basename, ±.md',
          "p === lower || p === lower + '.md'" in handler
          and "base === lower || base === lower + '.md'" in handler)
    check('a resolved link opens the note', 'openByPath(hit.path)' in handler)
    check('a dead link is said out loud, not swallowed',
          "isn't in the Library yet" in handler)

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
