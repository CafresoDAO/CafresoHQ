#!/usr/bin/env python3
"""A destructive confirm opened with focus already on its Delete button.

`DialogHost` (ui/feedback.jsx) autofocuses 30ms after the dialog mounts:

    if (req.kind === 'prompt' && inputRef.current) { …focus(); …select(); }
    else if (okRef.current) okRef.current.focus();

`okRef` is the OK button — and when the caller passes `{ danger: true }`
that button is literally labelled "Delete" (or "Stop all", or "Clear
all"). So the dialog arrived with the destructive action under the
boss's finger: one Enter or one Space, and it fires.

That is not a hypothetical keystroke. Every one of these confirms is
raised BY a key press or a click that a key press can repeat:

    app.jsx      `Delete "${t.title}"? Your coworker's work on it will be lost.`
    app.jsx      `${who} is working on "…" right now.\\n\\nDelete it and stop them?`
    app.jsx      `STOP ALL?…stop N coworkers mid-reply and pause M missions`
    features.jsx `Clear all receipts? Audit trail is lost.`
    commands.jsx `Delete workspace "…"?`  (run 30ms after Enter picked it
                  in the command palette)

Enter on a focused Delete control opens the dialog; keyboard auto-repeat
fires roughly 30 times a second, and a merely double-tapped Enter is
commoner still. Either way the second Enter arrives well after the 30ms
timer has moved focus onto the dialog's Delete button, activates it, and
the work is destroyed before the dialog has been on screen long enough
to read. The boss never saw the question they answered.

This is a different failure from #219. That one was about where an Enter
keydown was ROUTED once focus had already been moved to Cancel (the
`req.kind === 'confirm'` arm in `onKey` resolved TRUE from anywhere).
This one is about where focus LANDS in the first place — #219's fix made
Enter-on-Cancel safe, but nothing ever put focus on Cancel.

Fix: a `cancelRef`, and for a danger dialog focus Cancel rather than OK.
Enter then cancels (via the Cancel button's own onClick — exactly the
path #219 unblocked), and reaching Delete costs a deliberate Tab or a
click. `opts.hideCancel` dialogs have no Cancel, so they still focus OK.

The test executes the real extracted autofocus callback under Node with
ref stand-ins, rather than pattern-matching the source.

Run: python3 scripts/test_a_danger_dialog_does_not_open_under_the_delete_button.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEEDBACK = ROOT / 'ui' / 'feedback.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def paren_lift(src, header):
    """Return the full `header…)` statement, balanced on parentheses."""
    i = src.index(header)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '(':
            depth += 1
        elif src[j] == ')':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise ValueError('unbalanced parens for ' + header)


def main():
    print('A danger dialog does not open with focus on its Delete button')
    src = FEEDBACK.read_text(encoding='utf-8')

    check('the Cancel button carries a ref so focus can be put on it',
          'ref={cancelRef}' in src,
          'no cancelRef on the Cancel button — nothing can focus the safe way out')

    autofocus = paren_lift(src, 'const t = setTimeout(() => {')

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted callback)',
          has_node, 'skipping the live-execution check')
    if not has_node:
        print()
        if FAILS:
            print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
            return 1
        print('all checks passed')
        return 0

    js = """
    // Stand-ins: enough for the extracted autofocus callback to run for real.
    function scenario(kind, danger, hasCancel) {
      const focused = [];
      const mk = (name) => ({ name, focus() { focused.push(name); }, select() {} });
      const req = { kind, opts: { danger, hideCancel: !hasCancel } };
      const inputRef  = { current: kind === 'prompt' ? mk('input') : null };
      const okRef     = { current: mk(danger ? 'DELETE' : 'OK') };
      const cancelRef = { current: hasCancel ? mk('Cancel') : null };
      // Run the 30ms timer body immediately instead of waiting on it.
      const setTimeout = (fn) => { fn(); return 0; };
      __AUTOFOCUS__
      void t;
      return focused[0] || null;
    }

    console.log(JSON.stringify({
      dangerConfirm:        scenario('confirm', true,  true),
      plainConfirm:         scenario('confirm', false, true),
      dangerNoCancel:       scenario('confirm', true,  false),
      prompt:               scenario('prompt',  false, true),
    }));
    """.replace('__AUTOFOCUS__', autofocus)

    r = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=10)
    check('the extracted autofocus callback ran without a Node error',
          r.returncode == 0, (r.stderr or '').strip()[-800:])
    if r.returncode == 0:
        out = json.loads(r.stdout.strip().splitlines()[-1])
        check('a danger confirm opens with focus on Cancel, NOT on the '
              'destructive button — the regression: a held or double-tapped '
              'Enter destroyed the work before the dialog could be read',
              out['dangerConfirm'] == 'Cancel', out)
        check('a non-danger confirm still opens with focus on OK',
              out['plainConfirm'] == 'OK', out)
        check('a danger dialog with hideCancel (no Cancel button) still '
              'focuses OK — it has no other way out',
              out['dangerNoCancel'] == 'DELETE', out)
        check("a prompt still focuses its text input, not a button",
              out['prompt'] == 'input', out)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
