#!/usr/bin/env python3
"""A pasted screenshot's upload can outlive the note it was pasted into.

onEditorPaste (views/vault.jsx) captures `note = openNoteRef.current` before
`await uploadFiles(...)`, then re-reads `cur = openNoteRef.current` after the
await to build the embed/wikilink at the cursor. Re-reading `cur` is
deliberate — it means a keystroke typed into the SAME note while the upload
was in flight isn't clobbered. But nothing else blocks the Library's tree
while an upload is in flight (only the Save button is gated on `busy`), so a
boss can click a different note — openByPath swaps openNoteRef.current — or
close this one — closeNote sets it null — before the paste's own upload
resolves. The old guard (`if (!saved.length || !note) return;`) only asked
"was a note open when the paste STARTED", using the stale `note` reference,
and never checked whether `cur` was still that same note:

  - note closed mid-upload: `cur` is null, and `cur.content` on the next
    line threw — the pasted file was filed in the Library (uploadFiles had
    already run) but the reference was lost with an uncaught exception.
  - note switched mid-upload: `cur` is a DIFFERENT, currently-open note, and
    the embed/wikilink was spliced into ITS content at `at`'s offset — a
    note that never asked for it, using a cursor position measured in a
    buffer it was never typed into.

Fixed by checking `cur.path === note.path` (and `cur` itself) before
building the reference, so a note that moved out from under the upload is
left alone — the file still lands in the Library, only the in-editor
reference is skipped. The already-good "concurrent same-note edit" case
(case 3 below) keeps working: fresh `cur.content` still wins over the
content captured pre-upload.

Run: python3 scripts/test_a_paste_upload_does_not_outlive_its_note.py
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

const _bridge = null;
const say = (msg, tone) => calls.push(['say', msg, tone]);
const openNoteRef = { current: null };
const setOpenNote = (n) => calls.push(['set', n]);

// The mock upload resolves the way a real fetch does — AFTER the caller has
// already moved on — but crucially it mutates openNoteRef.current itself
// before returning, which is exactly the ordering a real race produces:
// whatever else runs during the await (a tree click, a close) happens
// before onEditorPaste's own `await` resumes.
let uploadAnswer = null;
let duringUpload = null;   // fn(openNoteRef) run "while the upload is in flight"
const uploadFiles = async (list, dir) => {
  calls.push(['upload', list.map(f => f.name), dir]);
  if (duringUpload) duringUpload(openNoteRef);
  return uploadAnswer;
};

(async () => {
  const out = {};

  // 1. Note closed mid-upload (closeNote → openNoteRef.current = null)
  // while a paste-triggered upload for it was still in flight.
  calls.length = 0;
  openNoteRef.current = { path: 'Research/brief.md', content: 'HEAD tail' };
  uploadAnswer = { uploaded: [{ path: 'Research/Pasted image X.png' }] };
  duringUpload = (ref) => { ref.current = null; };
  let threw = null;
  try {
    await onEditorPasteT(null)(mkEvent(
      [new File([], 'image.png', { type: 'image/png' })], 5));
  } catch (e) { threw = String(e && e.message || e); }
  out.closedMidUpload = { calls: calls.slice(), threw };

  // 2. Note SWITCHED mid-upload — a different note is open by the time the
  // upload resolves. The switched-to note's content must come back untouched.
  calls.length = 0;
  const noteA = { path: 'Research/brief.md', content: 'HEAD tail' };
  const noteB = { path: 'Other/note.md', content: 'UNRELATED CONTENT' };
  openNoteRef.current = noteA;
  uploadAnswer = { uploaded: [{ path: 'Research/Pasted image X.png' }] };
  duringUpload = (ref) => { ref.current = noteB; };
  await onEditorPasteT(null)(mkEvent(
    [new File([], 'image.png', { type: 'image/png' })], 5));
  out.switchedMidUpload = { calls: calls.slice(), noteBAfter: { ...noteB } };

  // 3. Sanity: typing INTO THE SAME note while its own upload is in flight
  // still lands the reference in the freshest content (the behavior the
  // re-read of `cur` exists for), same path throughout.
  calls.length = 0;
  const noteC = { path: 'Research/brief.md', content: 'HEAD tail' };
  openNoteRef.current = noteC;
  uploadAnswer = { uploaded: [{ path: 'Research/Pasted image X.png' }] };
  duringUpload = (ref) => {
    ref.current = { path: noteC.path, content: 'HEAD typed-more tail', dirty: true };
  };
  await onEditorPasteT(null)(mkEvent(
    [new File([], 'image.png', { type: 'image/png' })], 5));
  out.sameNoteConcurrentEdit = calls.slice();

  duringUpload = null;

  console.log(JSON.stringify(out));
})();
'''


def main():
    print('a paste upload does not outlive its note')
    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')

    fn = brace_lift(vault, 'const onEditorPaste = async (e) => {')
    fn = ('const onEditorPasteT = (b) => ' +
          fn.replace('const onEditorPaste = async (e) => {',
                     'async (e) => { const _bridge = b;', 1))
    p = subprocess.run(['node', '-e', HARNESS % fn], capture_output=True,
                       text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    out = json.loads(p.stdout.strip().split('\n')[-1])

    closed = out['closedMidUpload']
    check("closing the note mid-upload doesn't crash the paste handler",
          closed['threw'] is None, closed)
    check('…and never calls setOpenNote once the note underneath is gone',
          not any(c[0] == 'set' for c in closed['calls']), closed['calls'])

    switched = out['switchedMidUpload']
    check("switching notes mid-upload never touches the newly-open note",
          not any(c[0] == 'set' for c in switched['calls']), switched['calls'])
    check('…and the note the boss switched to keeps its own content verbatim',
          switched['noteBAfter']['content'] == 'UNRELATED CONTENT', switched)

    same = out['sameNoteConcurrentEdit']
    st = next((c[1] for c in same if c[0] == 'set'), None)
    check('typing in the SAME note during its own upload still gets the '
          'reference spliced into the freshest content',
          st is not None and st['content'] ==
          'HEAD ![](<Research/Pasted image X.png>)typed-more tail'
          and st['dirty'] is True, st)

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
