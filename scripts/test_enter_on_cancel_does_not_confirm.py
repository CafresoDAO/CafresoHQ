#!/usr/bin/env python3
"""Pressing Enter on a confirm dialog's Cancel button confirmed instead.

`DialogHost.onKey` (ui/feedback.jsx) handled Enter with the condition
`(req.kind === 'prompt' || e.target === okRef.current || req.kind === 'confirm')`.
The last arm made the branch fire for ANY Enter anywhere inside a confirm
dialog — including when focus sat on the Cancel button. The keydown
bubbles from the focused button up to the dialog div's onKeyDown BEFORE
the browser performs the button's default Enter activation (its click),
so `done(okValue())` settled the promise with `true` first; the Cancel
button's own `done(false)` arrived at an already-resolved promise and
was silently ignored.

User-visible result: Tab to Cancel, press Enter — the "decline" keyboard
path on a `{ danger: true }` dialog ("Delete "x"?") resolved TRUE and the
caller deleted anyway. The one dialog whose whole job is to offer a safe
way out had no working keyboard route to it besides Escape.

Fix: when the Enter keydown's target is a button other than the OK
button, onKey steps aside and lets that button's native activation (its
onClick) resolve the dialog.

This test extracts the real `onKey` from ui/feedback.jsx and executes it
under Node with minimal stand-ins (a fake HTMLButtonElement, a
once-only promise resolve), replaying the true event order: bubbled
keydown first, then the button's default-action click.

Run: python3 scripts/test_enter_on_cancel_does_not_confirm.py
"""
import json
import re
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


def brace_lift(src, header):
    """Return src from header through the matching close of its first '{'."""
    i = src.index(header)
    j = src.index('{', i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise ValueError('unbalanced braces for ' + header)


def main():
    print("Enter on a confirm dialog's Cancel button cancels, it does not confirm")
    src = FEEDBACK.read_text(encoding='utf-8')

    on_key_src = brace_lift(src, 'const onKey = (e) => {')
    check("the unconditional `req.kind === 'confirm'` arm is gone from the "
          "Enter branch — with it, Enter ANYWHERE in a confirm dialog "
          "resolved OK, Cancel button included",
          "req.kind === 'confirm')" not in on_key_src)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted onKey)',
          has_node, 'skipping the live-execution check')
    if not has_node:
        print()
        if FAILS:
            print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
            return 1
        print('all checks passed')
        return 0

    # onKey is arrow-assigned: strip the `const onKey =` so we can embed it.
    on_key_fn = on_key_src[len('const onKey ='):].strip()

    js = f"""
    // Stand-ins: enough for the extracted onKey to run for real under Node.
    // A promise resolve function fires once — later calls are ignored,
    // exactly the semantics that made this bug silent.
    class HTMLButtonElement {{}}
    globalThis.HTMLButtonElement = HTMLButtonElement;

    function scenario(kind, focusTarget, draftValue) {{
      let resolved = null;                      // first settle wins
      const settle = (v) => {{ if (resolved === null) resolved = {{ v }}; }};
      const req = {{ kind, resolve: settle, opts: {{ danger: true }} }};
      const draft = draftValue;
      const okBtn = new HTMLButtonElement();
      const cancelBtn = new HTMLButtonElement();
      const okRef = {{ current: okBtn }};
      const done = (result) => {{ const r = req.resolve; /* setReq(null) */ r(result); }};
      const cancelValue = req.kind === 'prompt' ? null : false;
      const okValue = () => req.kind === 'prompt' ? draft : true;
      const onKey = {on_key_fn};

      const target = focusTarget === 'cancel' ? cancelBtn
                   : focusTarget === 'ok' ? okBtn
                   : {{}};                        // prompt <input> — not a button
      // 1) the Enter keydown, bubbled from the focused element to the dialog
      onKey({{ key: 'Enter', target, stopPropagation() {{}}, preventDefault() {{}} }});
      // 2) the browser's default Enter activation on a focused button: click.
      //    (onKey never preventDefaults Enter, so this always follows.)
      if (target === cancelBtn) done(cancelValue);
      else if (target === okBtn) done(okValue());
      return resolved && resolved.v;
    }}

    console.log(JSON.stringify({{
      enterOnCancel: scenario('confirm', 'cancel'),
      enterOnOk:     scenario('confirm', 'ok'),
      enterInPrompt: scenario('prompt', 'input', 'typed-name'),
    }}));
    """
    r = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=10)
    check('the extracted onKey ran without a Node error',
          r.returncode == 0, (r.stderr or '').strip()[-800:])
    if r.returncode == 0:
        out = json.loads(r.stdout.strip().splitlines()[-1])
        check('Enter with focus on Cancel resolves FALSE — the regression: it '
              'used to resolve TRUE, performing the very deletion the boss '
              'was declining',
              out['enterOnCancel'] is False, out)
        check('Enter with focus on the OK button still resolves TRUE',
              out['enterOnOk'] is True, out)
        check("Enter in a prompt's text input still resolves the draft",
              out['enterInPrompt'] == 'typed-name', out)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
