#!/usr/bin/env python3
"""Putting a note in a folder meant typing its full path into a dialog.

The Library is where documents get ORGANIZED, and the only move door
was ✎ rename — retype the path, spell the folder right. Every file
manager on earth does this with a drag.

Now a tree row is draggable and every folder row (and the tree's
ground, meaning the root) is a drop target. The payload rides a
custom MIME type so the drop-to-UPLOAD overlay — which listens for
real OS 'Files' — never mistakes an internal move for an upload, and
the dragover gate checks that type before claiming the drop.
moveByDrag reuses the same rename door as ✎: links follow, a
collision is refused before the round-trip, a dirty open source is
flushed first, and the open note's path follows its file. Verified
live: a root note dragged onto Research landed there with its links
intact, and dragging it onto the tree ground brought it back.

Run: python3 scripts/test_a_row_dragged_onto_a_folder_is_filed_there.py
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


MOVE_HARNESS = r'''
const calls = [];
const CafresoHQClient = { vaultRename: async (a, b) => { calls.push(['rename', a, b]); return { linksRewritten: 2, filesTouched: 1 }; } };
const say = (m, tone) => calls.push(['say', m, tone]);
const snag = (m, e) => calls.push(['snag', m]);
const refresh = async () => calls.push(['refresh']);
const files = [{ path: 'Research/brief.md' }, { path: 'Research/taken.md' }, { path: 'loose.md' }, { path: 'taken.md' }];
const openNoteRef = { current: { path: 'loose.md', dirty: true } };
const saveNoteRef = { current: async () => calls.push(['flush']) };
let opened = null;
const setOpenNote = (fn) => { opened = fn(openNoteRef.current); };

%s

(async () => {
  const out = {};
  calls.length = 0;
  await moveByDrag('loose.md', 'Research');
  out.move = calls.slice(); out.opened = opened;
  calls.length = 0;
  await moveByDrag('Research/brief.md', 'Research');   // already there
  out.same = calls.slice();
  calls.length = 0;
  await moveByDrag('taken.md', 'Research');            // Research/taken.md exists
  out.collide = calls.slice();
  console.log(JSON.stringify(out));
})();
'''

TREE_HARNESS = r'''
const useSV = (v) => [v, () => {}];
const moved = [];
const onMove = (s, f) => moved.push([s, f]);
%s
const out = {};
const mk = (types) => {
  const ev = { dataTransfer: { types, dropEffect: '', data: {},
      setData(t, v) { this.data[t] = v; }, getData(t) { return this.data[t] || ''; } },
    prevented: false, preventDefault() { this.prevented = true; }, stopPropagation() {} };
  return ev;
};
const dz = dropProps('Research');
const filesDrag = mk(['Files']);
dz.onDragOver(filesDrag);
out.filesIgnored = !filesDrag.prevented;
const ours = mk([_MOVE_T]);
dz.onDragOver(ours);
out.claimed = ours.prevented && ours.dataTransfer.dropEffect === 'move';
const dp = dragProps('loose.md');
out.draggable = dp.draggable === true;
const start = mk([_MOVE_T]);
dp.onDragStart(start);
start.dataTransfer.types = [_MOVE_T];
dz.onDrop(start);
const root = dropProps('');
dp.onDragStart(start);
root.onDrop(start);
out.moved = moved.slice();
console.log(JSON.stringify(out));
'''


def main():
    print('a row dragged onto a folder is filed there')
    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')
    core = (ROOT / 'views' / 'core.jsx').read_text(encoding='utf-8')

    fn = brace_lift(vault, 'const moveByDrag = async (src, destFolder) => {')
    p = subprocess.run(['node', '-e', MOVE_HARNESS % fn],
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    out = json.loads(p.stdout.strip().split('\n')[-1])

    mv = out['move']
    check('a drop files the row in the folder through the rename door',
          ['rename', 'loose.md', 'Research/loose.md'] in mv, mv)
    check('a dirty open source is flushed before it moves', ['flush'] in mv)
    check('the open note follows its file',
          out['opened'] and out['opened']['path'] == 'Research/loose.md',
          out['opened'])
    check('the receipt names the destination and the links that followed',
          any(c[0] == 'say' and 'Research' in c[1] and '2 links followed' in c[1]
              for c in mv), mv)
    check('dropping a file where it already lives is a quiet no-op',
          out['same'] == [], out['same'])
    check('a collision is refused before the round-trip',
          not any(c[0] == 'rename' for c in out['collide'])
          and any(c[0] == 'say' and c[2] == 'error' for c in out['collide']),
          out['collide'])

    i = core.index('const [dragOverF, setDragOverF]')
    j = core.index('const toggle = (path)')
    p2 = subprocess.run(['node', '-e', TREE_HARNESS % core[i:j]],
                        capture_output=True, text=True, timeout=60)
    if p2.returncode != 0:
        print(p2.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on the tree drag plumbing')
    t = json.loads(p2.stdout.strip().split('\n')[-1])

    check("an OS file drag is never claimed — that's the upload overlay's",
          t['filesIgnored'], t)
    check('an internal drag is claimed with a move cursor', t['claimed'])
    check('file rows are draggable and carry their path', t['draggable'])
    check('a drop hands (source, folder) to the mover — root included',
          t['moved'] == [['loose.md', 'Research'], ['loose.md', '']],
          t['moved'])

    check('both trees get the mover — except the bridge vault',
          vault.count('onMove={_bridge ? null : moveByDrag}') == 2)
    check('folder rows and the tree ground are the drop targets',
          '{...dropProps(n.path)}' in core and "{...dropProps('')}" in core
          and '{...dragProps(n.path)}' in core)

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
