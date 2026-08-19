#!/usr/bin/env python3
"""Two more clipboard-copy sites gave no honest feedback — found by grepping
for `clipboard.writeText` repo-wide, exactly as task #38's own ledger entry
said to do before calling a clipboard-copy fix done.

**views/terminal.jsx**'s embedded terminal already has a correct, shared
`copyText()` helper (flashes '✓ copied' on success, 'copy blocked — check
browser permission' on failure) — used by the mouse-up-copies-selection
gesture a few lines below. But the Ctrl/Cmd+Shift+C keyboard shortcut
bypassed it entirely:

    navigator.clipboard.writeText(sel.trim()).catch(() => {});

A raw fire-and-forget write with a silent `.catch(() => {})` — the exact
anti-pattern this app has fixed five times now (three on 2026-08-19, plus
#38's two), sitting in the very same file as its own correct fix for a
different gesture on the same selection.

**features.jsx**'s StandupModal COPY MARKDOWN button was worse: no
feedback on success OR failure, and its catch block's own comment —
`/* fall back: select the textarea */` — described a fallback that was
never implemented; the catch body was empty. A boss who clicked it with
clipboard access blocked got total silence, with a comment lying about
what the code did if they'd gone and read it.

**The fix.** The keyboard-shortcut path now calls `copyText()` — the same
helper already correct one gesture over, so there is exactly one copy
implementation left in this file to keep honest. The stand-up modal now
has its own `copied` (null|true|false) state, surfaced in the same hint
strip that already gives real feedback for ARCHIVE, using the same
'✓ copied' / 'copy blocked — check browser permission' wording as
terminal.jsx's copyText for consistency across the app.

Run: python3 scripts/test_copy_shortcuts_that_skipped_the_honest_helper.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERMINAL = ROOT / 'views' / 'terminal.jsx'
FEATURES = ROOT / 'features.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract(text, start_marker, end_marker):
    i = text.index(start_marker)
    j = text.index(end_marker, i + len(start_marker))
    return text[i:j + len(end_marker)]


def run(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the real files')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('Copy shortcuts no longer skip the honest feedback helper')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    terminal = TERMINAL.read_text(encoding='utf-8')
    features = FEATURES.read_text(encoding='utf-8')

    # ── views/terminal.jsx: Ctrl/Cmd+Shift+C routes through copyText() ────
    handler = extract(terminal, 'term.attachCustomKeyEventHandler((ev) => {\n',
                       '\n    });')
    check('extracted the attachCustomKeyEventHandler callback', 'sel.trim()' in handler,
          'views/terminal.jsx shape changed')
    check("the raw fire-and-forget 'navigator.clipboard.writeText(...).catch"
          "(() => {})' is gone from this handler",
          'navigator.clipboard.writeText' not in handler, handler)
    check('the handler now calls the shared copyText() helper instead',
          'copyText(sel.trim())' in handler, handler)

    end_idx = handler.rindex('\n    }')
    callback_src = handler[handler.index('(ev)'):end_idx + len('\n    }')]

    def drive_terminal(write_text_impl):
        harness = """
let flash = '';
const doFlash = (msg) => { flash = msg; };
const copyText = async (text) => {
  try { await navigator.clipboard.writeText(text); doFlash('✓ copied'); }
  catch (_e) { doFlash('copy blocked — check browser permission'); }
};
const navigator = { clipboard: { writeText: %s } };
let cleared = false;
const term = {
  getSelection: () => 'hello world',
  hasSelection: () => true,
  clearSelection: () => { cleared = true; },
};
const handler = %s;
(async () => {
  const result = handler({ type: 'keydown', key: 'c', ctrlKey: true, shiftKey: false });
  await new Promise((r) => setTimeout(r, 0));
  console.log(JSON.stringify({ flash, cleared, result }));
})();
""" % (write_text_impl, callback_src)
        return run(harness)

    ok = drive_terminal('async () => {}')
    check('Ctrl+Shift+C on a successful write flashes the real success '
          "message ('✓ copied'), same as the mouse-up copy gesture",
          ok['flash'] == '✓ copied' and ok['cleared'] is True
          and ok['result'] is False, ok)

    fail = drive_terminal('async () => { throw new Error("denied"); }')
    check('Ctrl+Shift+C on a blocked write now surfaces the real failure '
          "message, not silence",
          fail['flash'] == 'copy blocked — check browser permission', fail)

    # ── features.jsx: COPY MARKDOWN gives real feedback ───────────────────
    copy_fn = extract(features, 'const copy = async () => {', '\n  };')
    check('extracted the StandupModal copy() function', 'writeText' in copy_fn,
          'features.jsx shape changed')
    check("the old aspirational comment claiming a textarea-select fallback "
          "that was never implemented is gone",
          'fall back: select the textarea' not in copy_fn, copy_fn)
    check('copy() now sets a real copied state on both success and failure, '
          'not silence on failure',
          'setCopied(true)' in copy_fn and 'setCopied(false)' in copy_fn, copy_fn)

    def drive_copy(write_text_impl):
        harness = """
let copied;
const setCopied = (v) => { copied = v; };
const setTimeout = () => {};
const navigator = { clipboard: { writeText: %s } };
const fullText = () => 'stand-up report';
const copy = %s;
(async () => {
  await copy();
  console.log(JSON.stringify({ copied }));
})();
""" % (write_text_impl, 'async ' + copy_fn[copy_fn.index('()'):])
        return run(harness)

    copy_ok = drive_copy('async () => {}')
    check('a successful COPY MARKDOWN click sets copied = true',
          copy_ok['copied'] is True, copy_ok)

    copy_fail = drive_copy('async () => { throw new Error("denied"); }')
    check('a blocked COPY MARKDOWN click sets copied = false (visible '
          'failure, not silence)',
          copy_fail['copied'] is False, copy_fail)

    # The hint strip (already gives real ARCHIVE feedback) now also
    # surfaces the real copy outcome, in the same wording used above.
    hint = extract(features, "<div className=\"hint\" style={{marginRight: 'auto'}}>{",
                    "'tap ARCHIVE to keep this on your task board'")
    check("the hint strip shows the real success wording ('✓ copied') "
          "when copy succeeded",
          "copied === true ? '✓ copied'" in hint, hint)
    check("the hint strip shows the real failure wording when copy failed, "
          "not just for the success case",
          "copied === false ? 'copy blocked" in hint, hint)

    print()
    if FAILS:
        print(f'copy-shortcut honesty: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:5]))
        return 1
    print('copy-shortcut honesty: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
