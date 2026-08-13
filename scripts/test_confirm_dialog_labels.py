#!/usr/bin/env python3
"""A dangerous confirm dialog must not just borrow the word "Delete".

`window.hqConfirm(message, opts)` (ui/feedback.jsx) renders its OK button as
`opts.okLabel || (opts.danger ? 'Delete' : 'OK')` — a sensible default for the
common case, since most `danger: true` confirms genuinely are deletions, and
the API's own doc comment uses `hqConfirm('Delete "x"?', {danger: true})` as
the canonical example.

But `danger: true` is also the right choice whenever a confirm needs RED
button styling for a high-consequence action that is NOT a deletion — "stop
everything mid-reply", "grant shell access", "hire with shell access",
"replace the coworker's in-progress work". Any call site that reaches for
`danger: true` for the styling, without also passing `okLabel`, silently
inherits the word "Delete" on a button that does something else entirely.

Found live: driving the ROSTER panel's elevation toggle, the dialog read
"Grant Llama COMPUTER ACCESS? ... Continue?" with a button reading
**"Delete"** — the single most consequential confirmation in the app (real
shell/file access) mislabeled as if it destroyed something. The identical
bug was in `modals/hire.jsx`'s hire-with-elevation dialog (a near-identical
question, "Continue?", same missing okLabel) — one bug, landed twice by two
different call sites copying the same shape. Two more instances used
"Clear all" language with a "Delete" button (receipts, notifications), and
one used "STOP ALL?" with a "Delete" button, and one displaced an in-progress
task ("Start X instead?") with a "Delete" button.

The check: for every `danger: true` confirm, EITHER an explicit `okLabel` is
present, OR the dialog's own message already contains the word "Delete" —
in which case the default is coherent with what the dialog itself is asking.
This is deliberately not "message starts with Delete" (a real, correct call
site's message can lead with other text and still say "Delete" partway
through, e.g. "X is working on Y. Delete it and stop them?") — CONTAINS is
the right bar, checked against every current call site with zero false
positives in either direction.

Run: python3 scripts/test_confirm_dialog_labels.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOBS = ['*.jsx', 'app/*.jsx', 'ui/*.jsx', 'modals/*.jsx', 'views/*.jsx']

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def find_calls(src):
    """Every `window.hqConfirm(...)` call, as (start, full_call_text)."""
    calls = []
    for m in re.finditer(r'window\.hqConfirm\(', src):
        start = m.end()
        depth = 1
        i = start
        while i < len(src) and depth > 0:
            if src[i] == '(':
                depth += 1
            elif src[i] == ')':
                depth -= 1
            i += 1
        calls.append((m.start(), src[m.start():i]))
    return calls


def main():
    print('confirm dialogs — a danger button must match what it actually does')
    total = 0
    checked_files = 0
    for pattern in GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            src = path.read_text(encoding='utf-8')
            calls = find_calls(src)
            if not calls:
                continue
            checked_files += 1
            for start, call in calls:
                if 'danger' not in call or not re.search(r'danger\s*:\s*true', call):
                    continue
                total += 1
                line = src.count('\n', 0, start) + 1
                has_ok_label = bool(re.search(r'okLabel\s*:', call))
                # Only the MESSAGE (before the options object) should license the
                # default — search just the portion before the trailing `{`.
                opts_start = call.rfind('{')
                message_part = call[:opts_start] if opts_start != -1 else call
                mentions_delete = 'delete' in message_part.lower()
                # The message argument is sometimes a bare variable (e.g. a `msg`
                # built a few lines above, per-branch, then passed by name) rather
                # than an inline template literal — the word "Delete" then lives
                # in that assignment, not in the call text itself. Follow it back:
                # find the LAST `const <name> =` / `let <name> =` before this call
                # in the same file and fold its RHS (up to the next top-level `;`)
                # into the same check.
                var_m = re.search(r'hqConfirm\(\s*([A-Za-z_$][A-Za-z0-9_$]*)\s*,', message_part)
                if not mentions_delete and var_m:
                    var_name = var_m.group(1)
                    assign_re = re.compile(
                        r'\b(?:const|let)\s+' + re.escape(var_name) + r'\s*=')
                    last_assign = None
                    for am in assign_re.finditer(src, 0, start):
                        last_assign = am
                    if last_assign:
                        semi = src.find(';', last_assign.end())
                        rhs = src[last_assign.end():semi if semi != -1 else last_assign.end() + 400]
                        mentions_delete = 'delete' in rhs.lower()
                ok = has_ok_label or mentions_delete
                check(f'{path.relative_to(ROOT)}:{line}',
                      ok,
                      "danger:true with no okLabel, and the dialog's own message "
                      "never says \"Delete\" — it will render a \"Delete\" button "
                      "on an action that isn't one")

    check('at least one danger:true confirm exists to check', total > 0,
          'expected several — the check found none, which means the scan '
          'itself is broken, not that the codebase is clean')
    check('scanned more than one file', checked_files > 3, checked_files)

    print()
    if FAILS:
        print(f'confirm dialog labels: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:5]))
        return 1
    print(f'confirm dialog labels: all {total} danger-styled confirms checked, all clean')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
