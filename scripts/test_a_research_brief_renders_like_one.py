#!/usr/bin/env python3
"""Tables, blockquotes and rules fell through to the paragraph arm.

The Library is where research is held, and a research brief's native
shapes are the table, the pulled quote, and the section rule.
renderMarkdown knew headings, lists and code; a markdown table came
out as one <p> of pipes per row, '> quote' as a literal
greater-than paragraph, '---' as a paragraph of dashes.

Now the preview renders all three — inline styles, not styles.css
(the preview carries its own table the way it carries its own
wikilink cursor): a real <table> in an overflow-x wrapper so wide
data scrolls instead of breaking the pane, <blockquote> with inline
markdown still live inside it, <hr> for a rule. The rule check runs
BEFORE the list check or '- - -' reads as a bullet. Verified live:
table with 3 headers and 2 rows, quote with its bold intact, rule,
and the wikilink door all in one note.

Run: python3 scripts/test_a_research_brief_renders_like_one.py
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


DOC = """# Brief

> Key insight: **retention** beats hiring.
> Second line.

| Metric | 2025 |
|--------|-----:|
| Churn <b>x</b> | 12% |

---

- - -

- a real bullet
"""


def main():
    print('a research brief renders like one')
    ide = (ROOT / 'views' / 'ide.jsx').read_text(encoding='utf-8')
    fn = brace_lift(ide, 'function renderMarkdown(text, opts)')
    js = fn + '\nconsole.log(JSON.stringify(renderMarkdown(' + json.dumps(DOC) + ')));'
    p = subprocess.run(['node', '-e', js], capture_output=True, text=True,
                       timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    html = json.loads(p.stdout.strip().split('\n')[-1])

    check('a table is a <table>, not paragraphs of pipes',
          '<table class="md-table"' in html and '<th' in html
          and '<td' in html)
    check('...inside an overflow-x wrapper so wide data scrolls',
          'overflow-x:auto"><table' in html)
    check('...with cell text escaped like everything else',
          '&lt;b&gt;x&lt;/b&gt;' in html, html)
    check('a quote is a <blockquote> with inline markdown live inside',
          '<blockquote class="md-quote"' in html
          and '<strong>retention</strong>' in html)
    check("--- is a rule", '<hr class="md-hr"' in html)
    check("'- - -' is a rule too, never a bullet",
          html.count('<hr') == 2 and '<li>- -' not in html, html)
    check('a real bullet is still a bullet', '<li>a real bullet</li>' in html)

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
