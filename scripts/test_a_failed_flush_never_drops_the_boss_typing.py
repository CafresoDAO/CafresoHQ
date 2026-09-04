#!/usr/bin/env python3
"""A failed dirty-buffer flush must stop the editor leaving the note — views/vault.jsx.

Bug: every path that leaves an open note (openByPath's two branches,
closeNote, newNote's fresh-buffer seed, openWikilink's dead-link create)
flushed a dirty buffer with `await saveNoteRef.current({ quiet: true })`
and then moved on unconditionally. saveNote catches its own errors — a
failed save only sets the '⚠ Retry save' chip, it never throws — so a
flush that FAILED (server down, network blip) resolved exactly like a
clean one, and the caller went on to replace or drop the buffer holding
the only copy of the boss's unsaved typing. openByPath even wiped the
Retry chip with its own setSaveState(''). Silent, total loss of typed
text on the single most ordinary gesture in the room: clicking another
note. (newNote and the dead-wikilink create were worse still — they
seeded a new buffer over a dirty one with no flush at all.)

Fix: `flushBeforeLeave()` in VaultView — flush, then look at the verdict.
Dirty survives a failed save (saveNote clears it only on success), so
"still dirty afterwards" IS the verdict: true → move on, false → stay on
the note, say so out loud, leave the Retry chip standing. All five leave
paths route through it; the mobile ✕ only switches panes when closeNote
answers true.

This test extracts the REAL `flushBeforeLeave` from views/vault.jsx
(brace-balanced extraction) and executes it via Node against stub refs —
a save that fails (dirty stays), a save that succeeds (dirty clears), a
clean buffer, and no buffer — then checks structurally that every leave
path actually routes through it.

Run: python3 scripts/test_a_failed_flush_never_drops_the_boss_typing.py
(the live-execution checks are skipped if `node` isn't on PATH — the
source-shape checks still run everywhere)
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'views' / 'vault.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract_arrow_const(src, name):
    """Brace-balanced extraction of `const NAME = async () => { ... };` —
    same technique the other views/*.jsx suites use to lift a closure."""
    m = re.search(r'const ' + re.escape(name) + r'\s*=\s*async \(\) => \{', src)
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
                return src[m.start():j + 1] + ';'
        j += 1
    return None


def extract_between(src, start_marker, end_marker):
    i = src.find(start_marker)
    if i == -1:
        return ''
    j = src.find(end_marker, i)
    return src[i:j if j != -1 else len(src)]


def main():
    print('vault flush-before-leave — a failed flush never drops the typing')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    src = SRC.read_text(encoding='utf-8')

    body = extract_arrow_const(src, 'flushBeforeLeave')
    check('flushBeforeLeave extracted from views/vault.jsx', body is not None)
    if body is None:
        print('\n1 failure(s)')
        return 1

    # ---- Structural: every leave path routes through the verdict ----
    open_by_path = extract_between(src, 'const openByPath = async (path) => {',
                                   '\n  /* Saving is tracked per-editor')
    check("openByPath's binary branch gates on flushBeforeLeave's verdict",
          open_by_path.count('if (!(await flushBeforeLeave())) return') >= 2,
          'both the binary branch and the text branch must stop on a failed flush')
    check('openByPath no longer fire-and-hopes the quiet save directly',
          'await saveNoteRef.current({ quiet: true })' not in open_by_path)

    close_note = extract_between(src, 'const closeNote = async () => {',
                                 '\n  /* File management')
    check('closeNote gates on the verdict and reports whether it closed',
          'if (!(await flushBeforeLeave())) return false' in close_note
          and 'return true' in close_note)
    check('the mobile ✕ only leaves the editor pane when closeNote answers true',
          re.search(r"if \(await closeNote\(\)\) setVaultTab\('tree'\)", src) is not None)

    new_note = extract_between(src, 'const newNote = async () => {',
                               '\n  /* First-run:')
    check('newNote flushes (and can stay) before seeding a fresh buffer',
          'if (!(await flushBeforeLeave())) return' in new_note)
    wiki = extract_between(src, 'const openWikilink = async (e) => {',
                           '\n  /* A checkbox in the preview')
    check("openWikilink's dead-link create flushes before replacing the buffer",
          'if (!(await flushBeforeLeave())) return' in wiki)

    # ---- Behavioral: run the real helper via Node against stub refs ----
    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted helper)',
          has_node, 'skipping the live-execution checks')
    if has_node:
        js = """
        async function run(note, saveImpl) {
          const openNoteRef = { current: note };
          const toasts = [];
          let saves = 0;
          const saveNoteRef = { current: async (opts) => { saves++; await saveImpl(openNoteRef); } };
          const say = (text, kind) => toasts.push({ text, kind });
          __BODY__
          const verdict = await flushBeforeLeave();
          return { verdict, saves, toasts, dirty: openNoteRef.current && openNoteRef.current.dirty };
        }
        (async () => {
          const failed = await run({ path: 'a.md', content: 'typed', dirty: true },
                                   async (ref) => { /* save failed: dirty survives */ });
          const clean  = await run({ path: 'a.md', content: 'typed', dirty: true },
                                   async (ref) => { ref.current = { ...ref.current, dirty: false }; });
          const idle   = await run({ path: 'a.md', content: 'typed', dirty: false }, async () => {});
          const none   = await run(null, async () => {});
          console.log(JSON.stringify({ failed, clean, idle, none }));
        })();
        """.replace('__BODY__', body)
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the extracted flushBeforeLeave ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-500:])
        if r.returncode == 0:
            out = json.loads(r.stdout.strip().splitlines()[-1])
            check('a flush that FAILED answers false — the leave must not happen',
                  out['failed']['verdict'] is False, out['failed'])
            check('the refused leave says so out loud (an error toast, not silence)',
                  any(t['kind'] == 'error' for t in out['failed']['toasts']),
                  out['failed']['toasts'])
            check('the dirty buffer is still standing after the refused leave',
                  out['failed']['dirty'] is True, out['failed'])
            check('a flush that SUCCEEDED answers true and raises no toast',
                  out['clean']['verdict'] is True and not out['clean']['toasts'],
                  out['clean'])
            check('a clean buffer passes straight through without saving',
                  out['idle']['verdict'] is True and out['idle']['saves'] == 0,
                  out['idle'])
            check('no open note passes straight through without saving',
                  out['none']['verdict'] is True and out['none']['saves'] == 0,
                  out['none'])

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
