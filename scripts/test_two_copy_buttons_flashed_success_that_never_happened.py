#!/usr/bin/env python3
"""Two "copy to clipboard" buttons claimed success no matter what actually
happened.

**graph-viewer.js** (the standalone vanilla-JS graph viewer, distinct from
the React views/graph.jsx) has a "Copy link to this node" button
(graph-viewer.html:322). Its click handler:

    try { await navigator.clipboard.writeText(link); }
    catch (_) { try { prompt('Copy link to this node:', link); } catch (__) {} }
    const prev = copyBtn.textContent;
    copyBtn.textContent = '✓';

...set the ✓ checkmark unconditionally — whether the write actually
succeeded, silently fell back to a native prompt() (which shows the link
for the user to select+copy themselves, but doesn't copy anything on its
own), or even that fallback's own prompt() call threw (swallowed by an
empty `catch (__) {}`, e.g. when prompt() is unavailable). Every one of
those paths flashed the same "it worked" signal.

This is the same "fire-and-forget clipboard write, unconditional success
claim" anti-pattern already fixed three times elsewhere in this app on
2026-08-19 (views/graph.jsx's Share modal, ui/chat.jsx's copy buttons,
views/projects.jsx's publishOpen()) — it survived here because it signals
success via `textContent = '✓'` rather than the string "Copied", and
lives in a separate non-React vanilla-JS file that a text grep for
"Copied" wouldn't reach.

**views/graph.jsx**'s "Copy embed" button, in the very same Share modal
already touched by one of those three prior fixes, had the weaker but
related problem: it gave NO feedback at all, success or failure —

    onClick: () => { try { navigator.clipboard.writeText(embed); } catch (_) {} }

— so a boss who clicked it while the browser blocked the write (no
user-activation, denied permission, insecure origin) got total silence
and no way to know the embed snippet wasn't on their clipboard.

**The fix**, in both places, only flashes a success indicator when the
write actually resolved — matching the shareCopied pattern already
established correctly one function up in the same views/graph.jsx file
(publish(), which sets shareCopied based on the real outcome).

Run: python3 scripts/test_two_copy_buttons_flashed_success_that_never_happened.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWER_JS = ROOT / 'graph-viewer.js'
GRAPH = ROOT / 'views' / 'graph.jsx'
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
    print('The graph "copy link" and "copy embed" buttons only claim success '
          'when the clipboard write actually happened')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    viewer_js = VIEWER_JS.read_text(encoding='utf-8')
    graph = GRAPH.read_text(encoding='utf-8')

    # ── graph-viewer.js "Copy link to this node" ─────────────────────────
    handler = extract(
        viewer_js,
        "if (copyBtn) copyBtn.addEventListener('click', async () => {",
        "\n  });",
    )
    check('extracted the gv-copy-link click handler', 'copyBtn.textContent' in handler,
          'graph-viewer.js shape changed')
    check('the handler now tracks a real `copied` outcome, not an unconditional ✓',
          'let copied = false' in handler and "copied = true" in handler, handler)

    def drive_viewer(write_text_impl, prompt_impl="() => {}"):
        harness = """
const pinned = 'node-1', hovered = null;
const trail = ['node-1'];
const location = { href: 'https://example.com/graph-viewer.html?focus=node-0' };
const navigator = { clipboard: { writeText: %s } };
const prompt = %s;
let copyBtn = { textContent: '⚲' };
const cb = async () => {
%s
};
(async () => {
  await cb();
  console.log(JSON.stringify({ textContent: copyBtn.textContent }));
})();
""" % (write_text_impl, prompt_impl, handler[handler.index('{') + 1:handler.rindex('}')])
        return run(harness)

    ok = drive_viewer('async () => {}')
    check('successful clipboard write still flashes ✓',
          ok['textContent'] == '✓', ok)

    fail_prompt_ok = drive_viewer(
        'async () => { throw new Error("denied"); }',
        '(msg, val) => val',
    )
    check('a failed write that falls back to a working prompt() no longer '
          'claims ✓ (prompt() shows the link for manual copy — it does not '
          'copy anything itself)',
          fail_prompt_ok['textContent'] == '⚠', fail_prompt_ok)

    fail_prompt_throws = drive_viewer(
        'async () => { throw new Error("denied"); }',
        '() => { throw new Error("prompt unavailable"); }',
    )
    check('a failed write whose prompt() fallback ALSO throws still resolves '
          "cleanly (doesn't crash the handler) and does not claim ✓",
          fail_prompt_throws['textContent'] == '⚠', fail_prompt_throws)

    # ── views/graph.jsx "Copy embed" ──────────────────────────────────────
    btn = extract(graph, "React.createElement('button', { onClick: async () => {\n"
                          "          const embed = ",
                  "'Copy failed' : 'Copy embed'),")
    check('extracted the Copy embed button', 'setEmbedCopied' in btn,
          'views/graph.jsx shape changed')
    check('Copy embed now sets embedCopied based on the real outcome, not '
          'silence either way',
          'setEmbedCopied(true)' in btn and 'setEmbedCopied(false)' in btn, btn)
    check('the label reflects a real failure state ("Copy failed"), not just '
          'success or the idle label',
          "'Copy failed'" in btn, btn)

    def drive_embed(write_text_impl):
        start = "onClick: async () => {\n"
        end = "\n        }, style: { ...ctrlStyle, cursor: 'pointer' } }, embedCopied"
        bi = graph.index(start) + len(start)
        bj = graph.index(end, bi)
        body = graph[bi:bj]
        harness = """
let embedCopied = null;
const setEmbedCopied = (v) => { embedCopied = v; };
const shareUrl = 'https://example.com/g/abc123';
const navigator = { clipboard: { writeText: %s } };
const setTimeout = () => {};
const onClick = async () => {
%s
};
(async () => {
  await onClick();
  console.log(JSON.stringify({ embedCopied }));
})();
""" % (write_text_impl, body)
        return run(harness)

    embed_ok = drive_embed('async () => {}')
    check('successful embed copy sets embedCopied = true',
          embed_ok['embedCopied'] is True, embed_ok)

    embed_fail = drive_embed('async () => { throw new Error("denied"); }')
    check('a blocked embed copy sets embedCopied = false (visible failure, '
          'not silence)',
          embed_fail['embedCopied'] is False, embed_fail)

    print()
    if FAILS:
        print(f'copy-button honesty: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:5]))
        return 1
    print('copy-button honesty: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
