#!/usr/bin/env python3
"""⌘V with a screenshot on the clipboard used to do nothing at all.

The Library editor is a textarea, and a textarea can't take an image —
so the single most common way a picture reaches a note (copy, paste)
was a silent no-op. Drag-drop filing existed; the paste door didn't.

Now onEditorPaste files every pasted file beside the open note
(vaultUpload grew a ?dir=), names anonymous clipboard images
"Pasted image <stamp>", and inserts a reference at the cursor built
from the path the server ACTUALLY saved (its answer key is `uploaded`,
and mistrusting that cost the first live run its insertion): an
![](embed) for images — angle form when the path has spaces — a
[[wikilink]] for anything else. Text-only pastes keep the browser
default. The bridge vault has no upload door, so there the paste is
refused out loud. Verified live: a synthetic clipboard PNG landed in
Research/, the embed appeared at the cursor, the preview rendered it.

Run: python3 scripts/test_a_pasted_screenshot_becomes_a_filed_embed.py
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, opener):
    i = src.index(opener)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise SystemExit('unbalanced braces lifting ' + opener)


HARNESS = r'''
%s;

const calls = [];
function mkEvent(files, at) {
  return {
    clipboardData: { files },
    target: { selectionStart: at },
    preventDefault() { calls.push(['prevent']); },
  };
}
class File {
  constructor(parts, name, opts) { this.name = name; this.type = (opts && opts.type) || ''; }
}
globalThis.File = File;

let _bridgeVal = null;
const _bridge = { get value() { return _bridgeVal; } };
const say = (msg, tone) => calls.push(['say', msg, tone]);
let uploadAnswer = null;
const uploadFiles = async (list, dir) => { calls.push(['upload', list.map(f => f.name), dir]); return uploadAnswer; };
const openNoteRef = { current: null };
const setOpenNote = (n) => calls.push(['set', n]);

(async () => {
  const out = {};

  // 1. text-only paste: default stands, nothing uploads
  calls.length = 0;
  await onEditorPasteT(null)(mkEvent([], 0));
  out.textOnly = calls.slice();

  // 2. bridge mode refuses out loud
  calls.length = 0;
  await onEditorPasteT({})(mkEvent([new File([], 'a.png', {type:'image/png'})], 0));
  out.bridge = calls.slice();

  // 3-5. the real path: anonymous image renamed+dated, filed beside the
  // note, reference built from the server's OWN saved path at the cursor
  calls.length = 0;
  openNoteRef.current = { path: 'Research/brief.md', content: 'HEAD tail' };
  uploadAnswer = { uploaded: [{ path: 'Research/Pasted image X.png' },
                              { path: 'Research/deck.pptx' }] };
  await onEditorPasteT(null)(mkEvent(
    [new File([], 'image.png', {type:'image/png'}),
     new File([], 'deck.pptx', {type:''})], 5));
  out.filed = calls.slice();

  // 6. no open note: filed to the root, nothing to insert into
  calls.length = 0;
  openNoteRef.current = null;
  uploadAnswer = { uploaded: [{ path: 'a.png' }] };
  await onEditorPasteT(null)(mkEvent([new File([], 'a.png', {type:'image/png'})], 0));
  out.noNote = calls.slice();

  console.log(JSON.stringify(out));
})();
'''


def main():
    print('a pasted screenshot becomes a filed embed')
    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')

    fn = brace_lift(vault, 'const onEditorPaste = async (e) => {')
    # the lifted handler closes over _bridge; parameterize it per-case
    fn = ('const onEditorPasteT = (b) => ' +
          fn.replace('const onEditorPaste = async (e) => {',
                     'async (e) => { const _bridge = b;', 1))
    p = subprocess.run(['node', '-e', HARNESS % fn], capture_output=True,
                       text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    out = json.loads(p.stdout.strip().split('\n')[-1])

    check('a text-only paste keeps the browser default',
          out['textOnly'] == [], out['textOnly'])
    br = out['bridge']
    check('the bridge vault refuses the paste out loud',
          ['prevent'] in br and any(c[0] == 'say' for c in br)
          and not any(c[0] == 'upload' for c in br), br)
    check("...and the refusal says Library, never vault",
          all('vault' not in c[1].lower() for c in br if c[0] == 'say'))

    filed = out['filed']
    up = next(c for c in filed if c[0] == 'upload')
    check('an anonymous clipboard image gets a dated name',
          up[1][0].startswith('Pasted image ') and up[1][0].endswith('.png'),
          up)
    check('a file with a real name keeps it', up[1][1] == 'deck.pptx', up)
    check("the upload lands beside the open note", up[2] == 'Research', up)
    st = next((c[1] for c in filed if c[0] == 'set'), None)
    check('the reference is built from the path the server saved — '
          'spacey embeds in angle form, non-images as wikilinks',
          st is not None and st['content'].startswith(
              'HEAD ![](<Research/Pasted image X.png>)\n'
              '[[Research/deck.pptx]]tail')
          and st['dirty'] is True, st)

    nn = out['noNote']
    check('no open note still files the paste, and never crashes',
          any(c[0] == 'upload' and c[2] == '' for c in nn)
          and not any(c[0] == 'set' for c in nn), nn)

    check('both editor textareas carry the paste door',
          vault.count('onPaste={onEditorPaste}') == 2)
    client = (ROOT / 'claude-client.jsx').read_text(encoding='utf-8')
    check('vaultUpload can aim at a folder',
          "'?dir=' + encodeURIComponent(dir)" in client)

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
