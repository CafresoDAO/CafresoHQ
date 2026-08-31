#!/usr/bin/env python3
"""A CRLF note rendered its frontmatter as an <hr> and its tasks as text.

Windows-authored and agent-filed notes arrive with \r\n, and every
line-equality in the renderer — `line === '---'`, the task-box match —
failed against the trailing \r: the frontmatter block became a stray
horizontal rule plus bare text, and every checkbox rendered as a
literal "[ ]". Worse, the renderer and togglePreviewTask share their
task NUMBERING — if only one of them learned to skip a CRLF
frontmatter block, a task-looking line inside it would desync the
count and a click would flip the wrong line.

Now both normalize \r\n? to \n before walking (one regex, two owners,
same comment pointing each at the other), and a toggle writes the
note back LF-normalized. Verified live: a CRLF seed showed its
frontmatter and both checkboxes, clicking box 0 flipped "first task"
and the file came back LF.

Run: python3 scripts/test_a_windows_note_renders_like_any_other.py
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


# The frontmatter deliberately holds a task-LOOKING line: the seed that
# catches a walker whose frontmatter skip fails while the renderer's
# succeeds — numbering desyncs and a click flips the wrong line.
DOC = ('---\r\nitems:\r\n- [ ] not a task, yaml\r\n---\r\n\r\n'
       '# Windows note\r\n\r\n- [ ] first task\r\n- [x] second task\r\n')


def main():
    print('a windows note renders like any other')
    ide = (ROOT / 'views' / 'ide.jsx').read_text(encoding='utf-8')
    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')

    fn = brace_lift(ide, 'function renderMarkdown(text, opts)')
    js = (fn + '\nconsole.log(JSON.stringify({'
          + 'lib: renderMarkdown(' + json.dumps(DOC) + ', {wikilinks:true}),'
          + 'cr: renderMarkdown("a\\rb", {})}));')
    p = subprocess.run(['node', '-e', js], capture_output=True, text=True,
                       timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('CRLF frontmatter is a frontmatter block, not an <hr>',
          'md-frontmatter' in r['lib'] and 'md-hr' not in r['lib'], r['lib'])
    # (the yaml decoy INSIDE the frontmatter block still shows its
    # literal text — only the real task lines must become boxes)
    check('CRLF tasks are checkboxes, not literal brackets',
          r['lib'].count('data-task=') == 2
          and '[ ] first' not in r['lib'] and '[x] second' not in r['lib'],
          r['lib'])
    check('the yaml decoy is never numbered',
          'data-task="0"' in r['lib'] and 'data-task="2"' not in r['lib'])
    check('no \\r survives into the HTML', '\r' not in r['lib'])
    check('a lone \\r (old Mac) is a line break too',
          'a' in r['cr'] and 'b' in r['cr'] and '\r' not in r['cr'], r['cr'])

    # The walker against the same CRLF DOC: box 0 must flip "first task",
    # not the yaml decoy the renderer skipped.
    toggle = brace_lift(vault, 'const togglePreviewTask = (e) =>')
    tjs = ('let captured = null;\n'
           'const openNoteRef = {current: {content: ' + json.dumps(DOC)
           + ', binary: false, path: "n.md"}};\n'
           'const setOpenNote = (n) => { captured = n; };\n'
           + toggle + '\n'
           'const ev = (n) => ({target: {tagName: "INPUT",'
           ' getAttribute: (k) => k === "data-task" ? String(n) : null}});\n'
           'togglePreviewTask(ev(0));\n'
           'console.log(JSON.stringify({content: captured && captured.content,'
           ' dirty: captured && captured.dirty}));')
    p2 = subprocess.run(['node', '-e', tjs], capture_output=True, text=True,
                        timeout=60)
    if p2.returncode != 0:
        print(p2.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed lifting togglePreviewTask')
    t = json.loads(p2.stdout.strip().split('\n')[-1])

    check('clicking box 0 flips "first task", not the yaml decoy',
          t['dirty'] and t['content']
          and '- [x] first task' in t['content']
          and '- [ ] not a task, yaml' in t['content'], t['content'])
    check('the toggled note is written back LF-normalized',
          t['content'] and '\r' not in t['content'])

    check('both walks carry the same normalization',
          'text = String(text).replace(/\\r\\n?/g' in ide
          and "note.content.replace(/\\r\\n?/g, '\\n').split" in vault)

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
