#!/usr/bin/env python3
"""The Command Palette (Cmd/Ctrl-K) — the app-wide search/command bar wired
up in ui/feedback.jsx (`CommandPaletteProvider` + `PaletteUI`) and fed by
app/commands.jsx (`AppGlobalCommands`, which is where "search across
projects, tasks, memory, chat history, coworkers" actually lives: Navigation
entries per view, one 'DM @agent' entry per hired coworker, and a "Recent
chat" section the file's own comment calls out as doubling for chat search)
— attached its single `handleKey` function to onKeyDown on TWO nested
elements at once:

    <div className="oc-palette" ... onKeyDown={handleKey}>   <!-- outer dialog -->
      ...
      <input ... onKeyDown={handleKey} />                    <!-- focused element -->

A native keydown always bubbles, and neither handler called
stopPropagation. So every keystroke while the input had focus (the normal
case — PaletteUI autofocuses it 30ms after opening on desktop) ran
`handleKey` twice for the one physical keypress: once as the input's own
handler, then again as the bubbled copy reaching the outer div.

Effect on each branch of that function:
  - ArrowDown / ArrowUp: `setSelectedIdx` advanced by 2 instead of 1 per
    keypress. With an even-length results list this makes every
    odd-offset row unreachable by keyboard — arrowing down from row 0
    lands on 2, 4, 6, ... and row 1, 3, 5 can never be highlighted, so a
    user arrowing to a specific search result can be permanently unable to
    select it and has to fall back to the mouse.
  - Enter: `onPick(flatVisible[selectedIdx])` — so the selected command's
    own `run()` — fired twice per Enter press. Harmless for an idempotent
    navigation command, but for 'Delete workspace "X"…' (app/commands.jsx)
    that means `window.hqConfirm` popping twice, and for anything
    dispatching a one-shot event (onDmAgent's prefill-composer,
    onJumpToMessage, onStopAll, the "retry the most recent failed
    message" comms command) it means the side effect runs twice from a
    single Enter.
  - Escape: onClose() called twice — harmless here only because close()
    happens to be idempotent, not because the double-fire wasn't real.

Fix: the outer "oc-palette" dialog div is the right (and sufficient)
place for `handleKey` — a keydown on the input, the close button, or
anywhere else in the dialog still bubbles up to it, including on mobile
where the input is deliberately never autofocused. Removed the redundant
`onKeyDown={handleKey}` from the `<input>` so the handler runs exactly
once per physical keystroke, regardless of what has focus inside the
dialog.

This test lifts `PaletteUI` verbatim (brace-balanced, from the DECLARATION
so it can't be fooled by a copy under a different name) and:
  1. structurally confirms the fix — exactly one `onKeyDown={handleKey}`
     attachment survives, and it sits on the outer dialog element, not on
     the `<input>`;
  2. genuinely executes the extracted `handleKey` logic under Node,
     replaying it the SAME NUMBER OF TIMES the current wiring would fire
     it for one physical keystroke, and asserts the resulting cursor
     movement/onPick-call-count matches what a user actually sees (one
     step, one run) rather than the regressed doubled behavior.

Run: python3 scripts/test_a_palette_keystroke_is_heard_once.py
(skips the live-execution checks if `node` isn't on PATH — the
structural/extraction checks still run everywhere)
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
    """`header` plus its balanced `{ … }` body, verbatim from the file.

    Anchored on the DECLARATION, never on the expression under test."""
    i = src.index(header)
    j = src.index('{', i + len(header) - 1)
    d, k = 0, j
    while k < len(src):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                break
        k += 1
    return src[i:k + 1]


def main():
    print('Command Palette: one physical keystroke runs handleKey exactly once')

    src = FEEDBACK.read_text(encoding='utf-8')

    palette_ui = brace_lift(src, 'function PaletteUI({ query, setQuery, selectedIdx, setSelectedIdx, grouped, flatVisible, onPick, onClose }) {')
    check('found PaletteUI (brace-balanced, from its declaration)',
          bool(palette_ui), 'brace_lift did not find/close the function')

    # ── 1. Structural check: exactly one onKeyDown={handleKey} attachment ──
    attach_count = palette_ui.count('onKeyDown={handleKey}')
    check('handleKey is wired to onKeyDown exactly ONCE in the rendered '
          'dialog (was wired twice: once on the outer dialog div, once '
          'again on the <input> nested inside it — and a keydown bubbles, '
          'so both fired for a single keystroke)',
          attach_count == 1, f'found {attach_count} attachment(s)')

    # The surviving attachment must be on the outer dialog (identified by
    # aria-label="Command palette", present only on that element), not
    # merely present somewhere incidental.
    m_dialog = re.search(r'aria-label="Command palette"[\s\S]{0,80}?onKeyDown=\{handleKey\}', palette_ui)
    m_dialog_before = re.search(r'onKeyDown=\{handleKey\}[\s\S]{0,80}?aria-label="Command palette"', palette_ui)
    check('the surviving onKeyDown={handleKey} sits on the outer dialog '
          '(role="dialog" aria-label="Command palette"), which every '
          'keydown inside the palette bubbles up to regardless of focus',
          bool(m_dialog or m_dialog_before))

    # The <input ... /> block must NOT carry its own onKeyDown any more.
    m_input = re.search(r'<input\b[\s\S]*?/>', palette_ui)
    check('found the <input> element to inspect', m_input is not None)
    input_block = m_input.group(0) if m_input else ''
    check('the <input> no longer attaches its own onKeyDown handler '
          '(removing this — not the dialog\'s — is the fix: the dialog\'s '
          'handler still catches the same bubbled keydown either way)',
          'onKeyDown={' not in input_block,
          'the <input> block still contains an onKeyDown={...} prop')

    handle_key_src = brace_lift(palette_ui, 'const handleKey = (e) => {')
    check('found handleKey (brace-balanced)', bool(handle_key_src))

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted '
          'handleKey logic below)', has_node,
          'skipping live-execution checks on this platform')

    if has_node and handle_key_src:
        # Harness: replays a SINGLE physical keystroke by invoking the
        # extracted handleKey `attachCount` times — exactly what the real
        # DOM does when the same handler is attached at `attachCount`
        # levels of the bubble path. `attachCount` is read from the
        # structural check above, not hard-coded, so this genuinely tracks
        # the current wiring rather than assuming it's fixed.
        js = f"""
        const attachCount = {attach_count if attach_count > 0 else 2};
        function harness(key, listLen) {{
          let selectedIdx = 0;
          const picks = [];
          let closes = 0;
          const flatVisible = Array.from({{length: listLen}}, (_, i) => ({{ id: 'cmd' + i }}));
          const setSelectedIdx = (updater) => {{
            selectedIdx = typeof updater === 'function' ? updater(selectedIdx) : updater;
          }};
          const onPick = (cmd) => {{ picks.push(cmd && cmd.id); }};
          const onClose = () => {{ closes += 1; }};
          const e = {{ key, defaultPrevented: false, preventDefault() {{ this.defaultPrevented = true; }} }};
          {handle_key_src}
          // One physical keystroke, replayed once per bubble-path attachment.
          for (let i = 0; i < attachCount; i++) handleKey(e);
          return {{ selectedIdx, picks, closes }};
        }}
        const down5 = harness('ArrowDown', 5);
        const up5   = harness('ArrowUp', 5);
        const enter5 = harness('Enter', 5);
        const esc    = harness('Escape', 5);
        console.log(JSON.stringify({{ down5, up5, enter5, esc, attachCount }}));
        """
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the extracted handleKey logic ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-800:])
        if r.returncode == 0:
            out = json.loads(r.stdout.strip().splitlines()[-1])
            check('one ArrowDown keystroke moves the cursor by exactly one '
                  'row (0 -> 1), not two — a doubled-invocation regression '
                  'would land on row 2 and skip row 1 entirely',
                  out['down5']['selectedIdx'] == 1,
                  f"selectedIdx ended at {out['down5']['selectedIdx']} "
                  f"(attachCount={out['attachCount']})")
            check('one ArrowUp keystroke moves the cursor by exactly one '
                  'row backward (0 -> 4, wrapping), not two rows (0 -> 3)',
                  out['up5']['selectedIdx'] == 4,
                  f"selectedIdx ended at {out['up5']['selectedIdx']} "
                  f"(attachCount={out['attachCount']})")
            check('one Enter keystroke invokes onPick (so the selected '
                  "command's own run()) exactly once, not twice — a double "
                  'invocation double-fires whatever the picked command '
                  'does, e.g. popping a delete-workspace confirm dialog twice',
                  out['enter5']['picks'] == ['cmd0'],
                  f"picks={out['enter5']['picks']}")
            check('one Escape keystroke calls onClose exactly once',
                  out['esc']['closes'] == 1,
                  f"closes={out['esc']['closes']}")

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
