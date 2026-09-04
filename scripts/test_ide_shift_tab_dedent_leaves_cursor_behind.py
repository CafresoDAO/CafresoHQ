#!/usr/bin/env python3
"""Shift-Tab dedent in the IDE editor must move the cursor with the text
it removed (views/ide.jsx, IDEEditor's onKey).

Bug: the Tab (indent) branch explicitly restores the textarea selection
after inserting two spaces:

    onChange(next);
    requestAnimationFrame(() => {
      if (taRef.current) {
        taRef.current.selectionStart = taRef.current.selectionEnd = start + 2;
      }
    });

but the sibling Shift-Tab (dedent) branch only called onChange(...) and
never touched selectionStart/selectionEnd at all. A controlled textarea's
raw DOM selection offsets are left numerically unchanged by React when the
value prop updates (they are only clamped if they now exceed the new
length) — so after dedent removes leading spaces from lines at or before
the cursor, the old numeric offsets point further into the (now shorter)
text than the cursor logically should be. The cursor visibly drifts to the
right by however many characters were stripped ahead of it, corrupting
the selection: continued typing lands at the wrong column, and re-pressing
Shift-Tab or Tab operates on the wrong line boundary.

Fix: compute how many characters were actually removed ahead of `start`
and ahead of `end`, and reposition the selection accordingly, mirroring
the indent branch.

This lifts the real onKey handler out of views/ide.jsx (brace-balanced
extraction of the `const onKey = (e) => { ... }` arrow) and executes it in
node against a fake textarea/event harness, checking the selection
offsets it computes for a Shift-Tab dedent.
Run: python3 scripts/test_ide_shift_tab_dedent_leaves_cursor_behind.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'views' / 'ide.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def extract_arrow_const(src, name):
    """Brace-balanced extraction of `const NAME = (...) => { ... }`."""
    m = re.search(r'const\s+' + re.escape(name) + r'\s*=\s*\([^)]*\)\s*=>\s*\{', src)
    if not m:
        return None
    depth = 0
    j = m.end() - 1
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
        j += 1
    return None


def run_onkey(arrow_src, value, start, end):
    """Execute the lifted onKey(e) against a fake textarea + requestAnimationFrame
    harness, simulating a Shift-Tab keydown, and report the resulting selection."""
    js = (
        'let raf = [];\n'
        'function requestAnimationFrame(fn) { raf.push(fn); }\n'
        'const value = %s;\n'
        'let newValue = null;\n'
        'function onChange(v) { newValue = v; }\n'
        'const ta = { selectionStart: %d, selectionEnd: %d };\n'
        'const taRef = { current: ta };\n'
        '%s\n'
        'const e = {\n'
        '  key: "Tab", shiftKey: true,\n'
        '  target: ta,\n'
        '  preventDefault: () => {},\n'
        '};\n'
        'onKey(e);\n'
        'raf.forEach(fn => fn());\n'
        'console.log(JSON.stringify({\n'
        '  newValue, selectionStart: ta.selectionStart, selectionEnd: ta.selectionEnd,\n'
        '}));\n'
    ) % (json.dumps(value), start, end, arrow_src)
    r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
    if r.returncode != 0:
        return None, (r.stderr or r.stdout).strip()
    return json.loads(r.stdout.strip()), None


def main():
    print('IDE editor — Shift-Tab dedent keeps the cursor with the removed text')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    text = SRC.read_text(encoding='utf-8')

    body = extract_arrow_const(text, 'onKey')
    check('onKey extracted from views/ide.jsx', body is not None)
    if body is None:
        print()
        print('FAILED: %s' % FAILS)
        return 1

    # Two lines, only the second one indented; cursor sits at the end of the
    # second line, nothing selected (the common case: caret in a line,
    # Shift-Tab to outdent it — dedent only touches the current line since
    # `middle` runs from the cursor's line-start to `end`).
    value = '  foo\n  bar'
    # Position at end of "  bar" (end of string).
    start = end = len(value)

    out, err = run_onkey(body, value, start, end)
    check('onKey executes in node', out is not None, err or '')
    if out is None:
        print()
        print('FAILED: %s' % FAILS)
        return 1

    check('dedent stripped the leading spaces on the current line only',
          out['newValue'] == '  foo\nbar', f"newValue={out['newValue']!r}")

    # "  bar" (5 chars) dedents to "bar" (3 chars) => 2 chars removed ahead
    # of the original end-of-string cursor. The cursor must land at the new
    # end of the (now shorter) text — 9 — not at the stale raw offset (11,
    # which is what a browser leaves an untouched selectionStart/End at
    # across a controlled-value update, and is now past the end of the text).
    expected = len('  foo\nbar')
    check('selectionEnd follows the removed characters (lands at new text end)',
          out['selectionEnd'] == expected,
          f"selectionEnd={out['selectionEnd']} expected={expected} (stale raw offset would stay {start})")
    check('selectionStart follows the removed characters (lands at new text end)',
          out['selectionStart'] == expected,
          f"selectionStart={out['selectionStart']} expected={expected}")

    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'ide shift-tab dedent cursor: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
