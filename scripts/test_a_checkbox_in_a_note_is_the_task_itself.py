#!/usr/bin/env python3
"""'- [ ] todo' rendered as a literal '[ ] todo' bullet.

The Library is where research and project notes are held, and a
checklist is one of their native shapes; the preview showed the
brackets as text. And a rendered checkbox that ignores clicks is a
picture of a task, not the task.

Now the renderer numbers each task in order of appearance
(data-task=N, skipping frontmatter and fenced code) and the Library
preview delegates clicks: togglePreviewTask walks the SOURCE with the
same rules, flips exactly the one mark byte on line N, and marks the
buffer dirty so the quiet autosave files it. Outside the Library the
box renders disabled. The wikilink door still opens through the same
combined handler. Verified live: click → source flip → autosave →
the [x] on disk, both directions, and the wikilink beside it still
navigates.

Run: python3 scripts/test_a_checkbox_in_a_note_is_the_task_itself.py
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


DOC = """---
title: t
---
- [ ] one
- [x] two

```
- [ ] not a task
```

* [ ] three
- plain
"""


def main():
    print('a checkbox in a note is the task itself')
    ide = (ROOT / 'views' / 'ide.jsx').read_text(encoding='utf-8')
    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')

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

    check('tasks render as checkboxes numbered in order',
          'data-task="0"' in r['lib'] and 'data-task="2"' in r['lib'], r['lib'])
    check('a fenced "- [ ]" is code, never a numbered task',
          'data-task="3"' not in r['lib']
          and '- [ ] not a task' in r['lib'])
    check('[x] is checked and struck through',
          'data-task="1" checked' in r['lib']
          and 'line-through' in r['lib'])
    check('the box is live in the Library, disabled elsewhere',
          'disabled' not in r['lib'] and r['ide'].count('disabled') == 3,
          r['ide'])
    check('a plain bullet is still a plain bullet',
          '<li>plain</li>' in r['lib'])

    # The walker, run against the same DOC: flipping task 2 must touch
    # only the '* [ ] three' line, not the fenced decoy above it.
    toggle = brace_lift(vault, 'const togglePreviewTask = (e) =>')
    tjs = ('let captured = null;\n'
           'const openNoteRef = {current: {content: ' + json.dumps(DOC)
           + ', binary: false, path: "n.md"}};\n'
           'const setOpenNote = (n) => { captured = n; };\n'
           + toggle + '\n'
           'const ev = (n) => ({target: {tagName: "INPUT",'
           ' getAttribute: (k) => k === "data-task" ? String(n) : null}});\n'
           'const handled = togglePreviewTask(ev(2));\n'
           'const notBox = togglePreviewTask({target: {tagName: "SPAN",'
           ' getAttribute: () => null}});\n'
           'console.log(JSON.stringify({handled, notBox,'
           ' content: captured && captured.content,'
           ' dirty: captured && captured.dirty}));')
    p2 = subprocess.run(['node', '-e', tjs], capture_output=True, text=True,
                        timeout=60)
    if p2.returncode != 0:
        print(p2.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed lifting togglePreviewTask')
    t = json.loads(p2.stdout.strip().split('\n')[-1])

    check('clicking box 2 flips its line and only its line',
          t['handled'] and t['dirty']
          and '* [x] three' in t['content']
          and '- [ ] one' in t['content']
          and '- [x] two' in t['content'], t['content'])
    check('...and the fenced decoy is untouched',
          t['content'] and '- [ ] not a task' in t['content'])
    check('a click that is not on a task box falls through to wikilinks',
          t['notBox'] is False)

    check('both preview panes route through the combined handler',
          vault.count('onClick={onPreviewClick} dangerouslySetInnerHTML')
          == 2,
          '— the checkbox AND the wikilink ride the same delegated click')
    check('the handler tries the task first, then the door',
          'if (togglePreviewTask(e)) return;' in vault
          and 'await openWikilink(e);' in vault)

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
