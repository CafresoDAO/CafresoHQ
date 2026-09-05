#!/usr/bin/env python3
"""#291 — the twin of #254.

`#254` closed the `.svg` preview hole in `views/ide.jsx` and, sweeping that
file for other `dangerouslySetInnerHTML` sinks, excused exactly one:
"renderMarkdown is the one allowed source: it entity-escapes before it looks
for syntax". That is true of the TEXT it emits and false of the ATTRIBUTES.
`esc` inside `renderMarkdown` escapes `&`, `<` and `>` and NOT `"`, which is
why every other attribute the function writes carries its own
`.replace(/"/g, '&quot;')` — the `![[embed]]` src and alt, the `[[wikilink]]`
target, the `![](src)` src and alt. The markdown-link arm was the odd one
out: `'<a href="$2">$1</a>'`, the URL interpolated raw.

So `[x](" onmouseover="…)` in any `.md` file on disk closed the href and hung
an event handler on the anchor, and `[x](javascript:…)` did it with no quote
at all — arbitrary JS in the origin `#254` enumerated (the II session, the
BYOK keys, every `cafresohq_*` key), through the two previews `#254` was
about: the IDE's `FilePreview` (`views/ide.jsx:661`) and the Library note
preview (`views/vault.jsx:1658`/`:1740`), both `dangerouslySetInnerHTML`.

This test lifts the SHIPPED `renderMarkdown` out of `views/ide.jsx` by
brace-matching and runs it under Node, so what is checked is the real
function and not a re-implementation of it.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDE = os.path.join(ROOT, 'views', 'ide.jsx')

failures = []
checks = 0


def check(name, cond, detail=''):
    global checks
    checks += 1
    if cond:
        print('  ok   %s' % name)
    else:
        print('  FAIL %s%s' % (name, ('  — ' + detail) if detail else ''))
        failures.append(name)


RE_PREV = '(,=:[!&|?{};+~^*%<>'


def strip_comments(src):
    """Remove /* */ and // comments so this file's OWN explanatory prose
    (which quotes the vulnerable `href="$2"` spelling verbatim) cannot make a
    correct fix look like the bug, and so a commented-out escape cannot make
    a broken one look fixed.

    Regex literals are skipped whole, because `replace(/"/g, …)` — which this
    very file uses five times — otherwise opens a double-quoted string that
    swallows the next hundred lines, comments included."""
    out = []
    i = 0
    n = len(src)
    prev = ''
    while i < n:
        c = src[i]
        if c in '"\'`':
            q = c
            out.append(c)
            i += 1
            while i < n:
                if src[i] == '\\':
                    out.append(src[i:i + 2])
                    i += 2
                    continue
                out.append(src[i])
                if src[i] == q:
                    i += 1
                    break
                i += 1
            prev = q
            continue
        if c == '/' and src[i + 1:i + 2] == '*':
            j = src.find('*/', i + 2)
            i = (j + 2) if j != -1 else n
            out.append(' ')
            continue
        if c == '/' and src[i + 1:i + 2] == '/':
            j = src.find('\n', i)
            i = j if j != -1 else n
            out.append(' ')
            continue
        if c == '/' and prev in RE_PREV:
            out.append(c)
            i += 1
            in_class = False
            while i < n:
                if src[i] == '\\':
                    out.append(src[i:i + 2])
                    i += 2
                    continue
                out.append(src[i])
                if src[i] == '[':
                    in_class = True
                elif src[i] == ']':
                    in_class = False
                elif src[i] == '/' and not in_class:
                    i += 1
                    break
                i += 1
            prev = '/'
            continue
        out.append(c)
        if not c.isspace():
            prev = c
        i += 1
    return ''.join(out)


def extract_function(src, name):
    """Brace-match `function name(...) {...}` in COMMENT-FREE source, skipping
    over string and regex literals — `replace(/"/g, …)` would otherwise open
    a string that never closes, and `/\\{/` would unbalance the count."""
    m = re.search(r'function\s+' + re.escape(name) + r'\s*\(', src)
    assert m, 'no %s in views/ide.jsx' % name
    depth = 0
    j = src.index('{', m.end())
    prev = '('
    while j < len(src):
        ch = src[j]
        if ch in '"\'`':
            q = ch
            j += 1
            while j < len(src):
                if src[j] == '\\':
                    j += 2
                    continue
                if src[j] == q:
                    break
                j += 1
            prev = q
        elif ch == '/' and prev in RE_PREV:
            j += 1                      # a regex literal, not division
            in_class = False
            while j < len(src):
                if src[j] == '\\':
                    j += 2
                    continue
                if src[j] == '[':
                    in_class = True
                elif src[j] == ']':
                    in_class = False
                elif src[j] == '/' and not in_class:
                    break
                j += 1
            prev = '/'
        else:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return src[m.start():j + 1]
            if not ch.isspace():
                prev = ch
        j += 1
    raise AssertionError('unbalanced %s' % name)


raw = open(IDE, encoding='utf-8').read()
# Comments are stripped BEFORE anything looks at the code, so this test file's
# own explanatory prose above — which quotes the vulnerable `href="$2"`
# spelling verbatim — and the fix's own comment in views/ide.jsx (which does
# the same) cannot make a correct fix read as the bug. A commented-out escape
# likewise cannot make a broken one read as fixed.
fn = extract_function(strip_comments(raw), 'renderMarkdown')
bare = fn

# ---- 1. the source-level shape: the raw-interpolation spelling is gone ----
check('the link arm no longer interpolates the URL straight into href',
      'href="$2"' not in bare and "href=\\\"$2\\\"" not in bare,
      'views/ide.jsx still builds <a href="$2">')

# ---- 2. behaviour: run the shipped function under Node -------------------
CASES = [
    # (name, markdown, must_not_appear_in_html, must_appear_in_html)
    # The payload's own text survives — escaped — INSIDE the href value; what
    # must not survive is its power to end the attribute, so the assertion is
    # on the escaped spelling, not on the absence of the word.
    ('quote breaks out of href',
     '[x](" onmouseover="alert(1))', [], ['href="&quot; onmouseover=&quot;']),
    ('javascript: URL is defused',
     '[x](javascript:alert(1))', ['href="javascript:'], []),
    ('JAVASCRIPT: in caps is defused',
     '[x](JaVaScRiPt:alert(1))', ['javascript:', 'JaVaScRiPt:'], []),
    ('a tab inside the scheme does not smuggle it through',
     '[x](java\tscript:alert(1))', ['script:alert'], []),
    ('vbscript: URL is defused',
     '[x](vbscript:msgbox(1))', ['href="vbscript:'], []),
    ('a plain https link still works',
     '[docs](https://example.com/a?b=1)',
     ['&quot;'], ['href="https://example.com/a?b=1"', '>docs<']),
    ('a relative link still works',
     '[note](./sub/other.md)', [], ['href="./sub/other.md"']),
]

runner = r'''
%s
const cases = %s;
const out = cases.map(c => renderMarkdown(c[1], {}));
console.log(JSON.stringify(out));
''' % (fn, json.dumps([[c[0], c[1]] for c in CASES]))

tmpdir = tempfile.mkdtemp(prefix='hq291-')
try:
    path = os.path.join(tmpdir, 'r.mjs')
    open(path, 'w', encoding='utf-8').write(runner)
    proc = subprocess.run([shutil.which('node') or 'node', path],
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        check('the shipped renderMarkdown runs under Node', False,
              proc.stderr.strip()[:400])
        rendered = None
    else:
        rendered = json.loads(proc.stdout.strip().splitlines()[-1])
        check('the shipped renderMarkdown runs under Node', True)
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

if rendered is not None:
    for (name, md, banned, needed), html in zip(CASES, rendered):
        low = html.lower()
        bad = [b for b in banned if b.lower() in low]
        missing = [g for g in needed if g not in html]
        check(name, not bad and not missing,
              'html=%r banned-present=%r missing=%r' % (html[:200], bad, missing))

    # Structural invariant, stronger than any single payload: every anchor
    # this function emits is exactly `<a href="…">` with a quote-free value.
    # If a URL can end the attribute, some tag stops matching this and the
    # extra attributes — an on*= handler among them — become visible here.
    anchors = [t for h in rendered for t in re.findall(r'<a\b[^>]*>', h)]
    stray = [t for t in anchors if not re.fullmatch(r'<a href="[^"]*">', t)]
    check('every emitted anchor is exactly <a href="…"> and nothing else',
          anchors and not stray, 'anchors=%r stray=%r' % (anchors[:6], stray))

# ---- 3. the neighbours stay escaped (this is a whole-family rule) --------
attr_writes = bare.count("replace(/\"/g, '&quot;')")
check('every attribute site in renderMarkdown quote-escapes (>=5)',
      attr_writes >= 5, 'found %d' % attr_writes)

print('\n%d/%d checks passed' % (checks - len(failures), checks))
sys.exit(1 if failures else 0)
