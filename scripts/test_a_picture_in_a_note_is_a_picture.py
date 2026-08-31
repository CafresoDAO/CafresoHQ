#!/usr/bin/env python3
"""![alt](src) rendered as a stray '!' and a text link.

The Library holds artifacts — screenshots, charts, an uploaded
dot.png beside the note that cites it — and the preview's inline pass
only knew [text](url), so an image came out as '!' plus a link, and a
vault-relative src pointed nowhere. /vault/file already answers
images inline (sandboxed, svg excluded); the renderer just never
asked.

Now images are replaced BEFORE links: in the Library preview
(opts.wikilinks) a bare relative src routes through
/vault/file?path=…; absolute http(s):/data:/rooted srcs stand as
written everywhere. No loading="lazy" — with no intrinsic size the
img lays out 0×0, never intersects the viewport, and never loads;
caught live (complete:false forever, while a fresh Image() loaded
the same URL instantly). Verified live: the uploaded png renders at
its natural size in the note, no stray '!', plain links untouched.

Run: python3 scripts/test_a_picture_in_a_note_is_a_picture.py
"""
import json
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


DOC = ('![shot "q"](Research/dot.png) and ![ext](https://x.io/a.png) '
       'and a [plain](https://x.io) link.')


def main():
    print('a picture in a note is a picture')
    ide = (ROOT / 'views' / 'ide.jsx').read_text(encoding='utf-8')
    fn = brace_lift(ide, 'function renderMarkdown(text, opts)')
    js = (fn + '\nconsole.log(JSON.stringify({'
          + 'lib: renderMarkdown(' + json.dumps(DOC) + ', {wikilinks:true}),'
          + 'ide: renderMarkdown(' + json.dumps(DOC) + ')}));')
    p = subprocess.run(['node', '-e', js], capture_output=True, text=True,
                       timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('a vault-relative image routes through /vault/file (Library)',
          'src="/vault/file?path=Research%2Fdot.png"' in r['lib'], r['lib'])
    check('...but stands as written outside the Library',
          'src="Research/dot.png"' in r['ide'], r['ide'])
    check('an absolute URL stands as written everywhere',
          'src="https://x.io/a.png"' in r['lib']
          and 'src="https://x.io/a.png"' in r['ide'])
    check("no stray '!' survives",
          '!<a' not in r['lib'] and '!<a' not in r['ide'], r['lib'])
    check('a plain link is still a link',
          '<a href="https://x.io">plain</a>' in r['lib'])
    check('a quote in the alt text cannot break the attribute',
          'alt="shot &quot;q&quot;"' in r['lib'], r['lib'])
    check('no loading="lazy" (0×0 layout means it never loads)',
          'loading="lazy"' not in r['lib'])
    check('the image is capped to the pane', 'max-width:100%' in r['lib'])

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
