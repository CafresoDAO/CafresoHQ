#!/usr/bin/env python3
"""Escape while typing threw away the draft.

The Modal shell's own header comment (modals/base.jsx) promises "Esc to
close (skips when typing in inputs/textareas)" — and the handler never
implemented the parenthesis. Escape closed unconditionally, from any
focused element.

Every dialog in the app rides this shell, so the blast radius is every
form: a boss half-way through the hire form's JOB DESCRIPTION who pressed
Esc — IME cancel, autocomplete dismiss, plain muscle memory from editors
where Esc means "leave this field" — lost the name, the role, the prompt,
the tool ticks and the creativity dial in one keystroke, with no confirm
and no way back (the [open]-reset effect wipes the state before the modal
can be reopened). Same for a workflow draft, a meeting-room setup, a
starter-task subject.

The fix implements the documented contract, no more: Escape is ignored
only while the target is a text-entry element (textarea, contenteditable,
or an input whose type takes typing). A checkbox, radio, range or button
is not "typing" — Esc from those still closes, and so do the CLOSE button,
the backdrop, and Esc once focus has left the field.

This test lifts the real `onKey` handler out of modals/base.jsx and runs
it in node with spy events — it executes the shipped code, not a
description of it.

Run: python3 scripts/test_escape_mid_typing_does_not_eat_the_draft.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = (ROOT / 'modals' / 'base.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Scan code, never prose — the fix's own comment quotes the contract."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
    """Body by brace matching, from the first `{` after the opener."""
    i = src.index(opener)
    depth = 0
    started = False
    for k in range(i, len(src)):
        if src[k] == '{':
            depth += 1
            started = True
        elif src[k] == '}':
            depth -= 1
            if started and depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


def node(js):
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=90)
    if p.returncode != 0:
        print(p.stdout)
        print(p.stderr[-1500:], file=sys.stderr)
        return None
    return json.loads(p.stdout.strip().split('\n')[-1])


def main():
    print('escape mid-typing does not eat the draft')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    src = strip_comments(BASE)
    onkey = brace_lift(src, 'const onKey = (e) => {')

    # The handler closes over dismissable/onClose/focusables/node/document —
    # hand each one in and get the real function back.
    js = r'''
const makeOnKey = (dismissable, onClose, focusables, node, document) => {
  ''' + onkey + r'''
  return onKey;
};

const press = (dismissable, target, extra = {}) => {
  let closed = 0, stopped = 0;
  const first = { focused: 0, focus() { this.focused++; } };
  const last  = { focused: 0, focus() { this.focused++; } };
  const onKey = makeOnKey(dismissable, () => { closed++; },
    () => [first, last], { focus() {} }, { activeElement: extra.active === 'last' ? last : first });
  onKey(Object.assign({
    key: 'Escape', shiftKey: false, target,
    stopPropagation() { stopped++; }, preventDefault() {},
  }, extra));
  return { closed, stopped, wrapped: first.focused };
};

const out = {
  textarea:        press(true, { tagName: 'TEXTAREA' }).closed,
  text_input:      press(true, { tagName: 'INPUT', type: 'text' }).closed,
  bare_input:      press(true, { tagName: 'INPUT' }).closed,
  editable:        press(true, { tagName: 'DIV', isContentEditable: true }).closed,
  checkbox:        press(true, { tagName: 'INPUT', type: 'checkbox' }).closed,
  range:           press(true, { tagName: 'INPUT', type: 'range' }).closed,
  button:          press(true, { tagName: 'BUTTON' }).closed,
  dialog_itself:   press(true, { tagName: 'DIV' }).closed,
  undismissable:   press(false, { tagName: 'BUTTON' }).closed,
  tab_still_wraps: press(true, { tagName: 'BUTTON' },
                         { key: 'Tab', active: 'last' }).wrapped,
};
console.log(JSON.stringify(out));
'''
    R = node(js)
    check('the handler lifts and runs at all', R is not None)
    if R is None:
        return 1

    # ── 1. typing is safe ────────────────────────────────────────────────
    check('Esc in a textarea does not close the modal',
          R['textarea'] == 0,
          '— a JOB DESCRIPTION draft died to one keystroke')
    check('...nor in a text input',
          R['text_input'] == 0,
          '— the hire form NAME, the workflow name, the meeting topic')
    check('...nor in an input with no declared type (type defaults to text)',
          R['bare_input'] == 0,
          '— most inputs in this app never set type=')
    check('...nor in a contenteditable',
          R['editable'] == 0)

    # ── 2. everything that is not typing still closes ────────────────────
    check('Esc from a checkbox still closes',
          R['checkbox'] == 1,
          '— a tick is not typing; the skip must not widen into Esc-never-works')
    check('...and from a range slider',
          R['range'] == 1)
    check('...and from a button',
          R['button'] == 1)
    check('...and from the dialog body itself',
          R['dialog_itself'] == 1)

    # ── 3. the neighbours are untouched ──────────────────────────────────
    check('dismissable=false still refuses Esc everywhere',
          R['undismissable'] == 0)
    check('the Tab focus trap still wraps last → first',
          R['tab_still_wraps'] == 1,
          '— the skip must live inside the Escape branch, not around the handler')

    print(('PASS' if not FAILS else f'{len(FAILS)} FAILURE(S): ' + ', '.join(FAILS)))
    return 0 if not FAILS else 1


if __name__ == '__main__':
    sys.exit(main())
