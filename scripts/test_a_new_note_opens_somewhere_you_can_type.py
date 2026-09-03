#!/usr/bin/env python3
"""The office asked for a note's name and gave nowhere to write it.

Measured live (#151) in the Library. Pressed +, answered "New note path"
with `Weekly plan`, and landed on a completely blank pane: no cursor, no
placeholder, no textarea in the DOM at all. Did the obvious next thing --
clicked in the empty space and typed a heading and a line -- then pressed
Save. The server took it:

    {"path": "Weekly plan.md", ..., "size": 0}

Every keystroke went nowhere, and the empty file was filed anyway.

The cause is that the Preview checkbox starts ON and is shared across every
note the room opens, and the preview branch renders INSTEAD of the textarea
-- there is no editor behind it. Preview an empty string and you get an empty
`<div class="vault-preview">`. So the pane a boss is sent to immediately
after naming a note is, by construction, a wall.

This is not only the moment of creation. `openByPath` on an already-empty
note -- including the zero-byte casualties the bug itself filed -- lands on
the same wall. So the rule is written once, about content rather than about
newness:

    `_nothingToPreview(content)` -> the pane opens on the editor.

Only ever OFF, never back on: a boss who unchecked Preview meant it, and an
empty note is no reason to overrule them in the other direction. This file
checks that direction explicitly, because getting it wrong would yank a
reader into a raw-markdown editor they did not ask for.

Runs the shipped `_nothingToPreview` under Node rather than restating it, and
holds the two call sites and the render branch to the shape that makes it
matter.

Run: python3 scripts/test_a_new_note_opens_somewhere_you_can_type.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / 'views' / 'vault.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift_const(src, name):
    """The source of one module-scope `const name = ...;`, to depth-0 `;`."""
    m = re.search(r'^const %s = ' % re.escape(name), src, re.M)
    if not m:
        return None
    depth, i = 0, m.end()
    while i < len(src):
        c = src[i]
        if c in '({[':
            depth += 1
        elif c in ')}]':
            depth -= 1
        elif c == ';' and depth == 0:
            return src[m.start():i + 1]
        i += 1
    return None


PROBE = r'''
const OUT = {};
// The measured case: newNote's buffer.
OUT.brandNew   = _nothingToPreview('');
// Every shape of "there is nothing on this page" -- a file the editor
// saved with a stray newline previews to nothing at all, same wall.
OUT.spaces     = _nothingToPreview('   ');
OUT.newlines   = _nothingToPreview('\n\n');
OUT.tabs       = _nothingToPreview('\t \n');
OUT.nullish    = _nothingToPreview(null);
OUT.undef      = _nothingToPreview(undefined);
// A note with something to show must NOT be dragged into the editor.
OUT.heading    = _nothingToPreview('# Weekly plan');
OUT.oneChar    = _nothingToPreview('x');
OUT.leadingWs  = _nothingToPreview('\n\n  # Later heading');
// Markdown that renders to very little is still not nothing -- a horizontal
// rule is a real note the boss wrote, and yanking them into raw markdown
// for it would be the same rudeness in reverse.
OUT.rule       = _nothingToPreview('---');
OUT.zeroChar   = _nothingToPreview('0');
console.log(JSON.stringify(OUT));
'''


def run_probe():
    src = VAULT.read_text(encoding='utf-8')
    body = lift_const(src, '_nothingToPreview')
    if body is None:
        return None, 'could not lift _nothingToPreview from views/vault.jsx'
    tmp = ROOT / '.note-preview-probe-tmp'
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        (tmp / 'probe.js').write_text(body + '\n\n' + PROBE, encoding='utf-8')
        p = subprocess.run([shutil.which('node') or 'node', str(tmp / 'probe.js')],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            return None, 'node: ' + p.stderr.strip()[:300]
        return json.loads(p.stdout.strip().splitlines()[-1]), None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def fn_body(src, name):
    """A `const name = async () => {` / `= () => {` body, brace-matched."""
    m = re.search(r'^\s*const %s = (?:async )?\([^)]*\) => \{' % re.escape(name),
                  src, re.M)
    if not m:
        return None
    depth, i = 0, m.end() - 1
    while i < len(src):
        if src[i] == '{':
            depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():i + 1]
        i += 1
    return None


def main():
    print('a new note opens somewhere you can type')
    if not shutil.which('node'):
        print('  SKIP  node not available — cannot run the real helper')
        return 0

    src = VAULT.read_text(encoding='utf-8')
    code = re.sub(r'/\*[\s\S]*?\*/', '', src)

    r, err = run_probe()
    if r is None:
        print('  FAIL  could not run the helper: ' + str(err))
        return 1

    print('1. what counts as nothing to preview')
    for key, why in (
        ('brandNew', "newNote's empty buffer — the measured case"),
        ('spaces', 'only spaces'),
        ('newlines', 'only newlines'),
        ('tabs', 'only whitespace'),
        ('nullish', 'no content at all'),
        ('undef', 'content not read yet'),
    ):
        check(f'the editor opens when there is {why}', r[key] is True,
              f'{key} = {r[key]!r}')

    print('2. a note with something on it is left in the preview')
    # The wrong direction is not symmetrical with the bug — it drops a
    # reader into raw markdown they never asked for. Worth more cases.
    for key, why in (
        ('heading', 'a heading'),
        ('oneChar', 'a single character'),
        ('leadingWs', 'a heading after blank lines'),
        ('rule', 'a horizontal rule and nothing else'),
        ('zeroChar', 'the character 0, which is falsy in the wrong hands'),
    ):
        check(f'the preview is kept for {why}', r[key] is False,
              f'{key} = {r[key]!r}')

    print('3. both doors into the pane use it')
    # newNote is where it was found; openByPath is where the already-filed
    # zero-byte notes come back through. A fix to only one leaves half the
    # casualties on the wall.
    new_body = fn_body(code, 'newNote')
    open_body = fn_body(code, 'openByPath')
    check('newNote drops into the editor',
          new_body is not None and '_nothingToPreview(' in new_body
          and 'setPreview(false)' in new_body,
          'views/vault.jsx newNote: the path prompt leads straight to the '
          'blank pane again')
    check('openByPath does too, for a note that is already empty',
          open_body is not None and '_nothingToPreview(' in open_body
          and 'setPreview(false)' in open_body,
          'views/vault.jsx openByPath: reopening an empty note lands on the '
          'same wall the bug filed it behind')
    check('neither ever turns Preview back ON',
          not re.search(r'setPreview\(true\)', code),
          'views/vault.jsx: forcing preview on would overrule a boss who '
          'deliberately unchecked it')

    print('4. why an empty preview is a wall and not just a blank')
    # The branch is exclusive: preview renders INSTEAD of the textarea.
    # If that ever became a split view, this whole bug stops existing and
    # this file should be reconsidered rather than kept passing.
    check('the preview still renders instead of the textarea, not beside it',
          code.count('<textarea className="vault-edit"') == 2
          and len(re.findall(r'\) : preview \? \(', code)) == 2,
          'views/vault.jsx: two panes (mobile + desktop) each pick ONE of '
          'preview or textarea — that exclusivity is what made an empty '
          'preview unreachable')
    check('the Preview checkbox is the same shared state both panes read',
          code.count('checked={preview} onChange={e=>setPreview(') == 2,
          'views/vault.jsx: one preference, two toolbars — a per-note '
          'toggle would be a different design and a different test')

    print()
    if FAILS:
        print(f'new note: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('new note: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
