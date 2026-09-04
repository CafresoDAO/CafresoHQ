#!/usr/bin/env python3
"""Opening an .svg in the workspace ran its code in the office's own origin.

views/ide.jsx FilePreview rendered the svg arm as

    <div style={pad} dangerouslySetInnerHTML={{ __html: file.content }} />

— the raw bytes of a file on disk, injected into THIS document. An .svg is
markup, not a picture: <animate onbegin=…>, an <img onerror=…> that breaks
the HTML parser straight back out of foreign content, <a href="javascript:">
and a <style> block that can paint over the whole app all survive an
innerHTML insert. So one click on a file in the tree — a cloned repo's
asset, a coworker's deliverable, anything an agent downloaded — handed that
file arbitrary JS in the origin that holds the Internet Identity session,
the stored BYOK API keys and every cafresohq_* key in localStorage.

Every other untrusted-markup preview in the app already knew this: the two
HTML arms three lines above, and the Library's HtmlFramePreview, all render
into an iframe on an opaque origin and say so in their comments ("No
allow-same-origin — page markup can come from any hired coworker"). The svg
arm was the one that wasn't. It is an iframe now, sandbox="" — a picture
needs no script at all, so nothing is granted back.

Run: python3 scripts/test_an_svg_preview_is_a_picture_not_a_program.py
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


def arm(src, opener):
    """The source of one `if (kind === 'x')` arm of FilePreview."""
    i = src.index(opener)
    nxt = src.find("if (kind ===", i + len(opener))
    return src[i:nxt if nxt > 0 else len(src)]


def sandbox_of(frag):
    m = re.search(r'sandbox="([^"]*)"', frag)
    return None if m is None else m.group(1)


def main():
    print('an svg preview is a picture, not a program')
    ide = (ROOT / 'views' / 'ide.jsx').read_text(encoding='utf-8')

    svg = arm(ide, "if (kind === 'svg')")

    # ── the sink is gone ────────────────────────────────────────────────
    check('the svg preview no longer injects the file into this document',
          'dangerouslySetInnerHTML' not in svg, svg.strip()[:200])

    # ── and what replaced it is actually walled off ─────────────────────
    check('the svg preview is an iframe', '<iframe' in svg, svg.strip()[:200])
    sb = sandbox_of(svg)
    check('...that declares a sandbox at all', sb is not None, svg.strip()[:200])
    check('...granting nothing — a picture needs no script',
          sb == '', repr(sb))
    check('...so it can never be same-origin with the office',
          sb is not None and 'allow-same-origin' not in sb, repr(sb))
    check('...and it still shows the file the boss clicked',
          'srcDoc={file.content' in svg, svg.strip()[:200])

    # ── the neighbours that already got this right stay right ───────────
    html = arm(ide, "if (kind === 'html')")
    sandboxes = re.findall(r'sandbox="([^"]*)"', html)
    check('both HTML preview arms are still sandboxed',
          len(sandboxes) == 2, sandboxes)
    check('...and neither one is same-origin with the office',
          all('allow-same-origin' not in s for s in sandboxes), sandboxes)

    # ── nothing else in the file pipes raw file bytes into the DOM ──────
    # The markdown arm is fine: renderMarkdown() entity-escapes before it
    # looks for syntax. Any OTHER dangerouslySetInnerHTML fed straight from
    # file.content is the same bug wearing a different extension.
    raw = re.findall(r'dangerouslySetInnerHTML=\{\{\s*__html:\s*([^}]*)\}\}', ide)
    leaks = [r.strip() for r in raw if 'renderMarkdown' not in r]
    check('no preview arm hands raw file bytes to innerHTML', not leaks, leaks)

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
