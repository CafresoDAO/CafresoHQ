#!/usr/bin/env python3
"""A whole folder could never be moved — the rename door couldn't see it.

_vault_resolve force-appends '.md' to any extensionless path, so
POST /vault/rename {"from": "Drawer", ...} looked for Drawer.md and
answered "source not found" — every time, on every folder, forever.
And even reaching the move (os.replace happily relocates a directory)
would have broken every [[Drawer/alpha]] path link in the Library:
the rewriter only knew how to follow ONE file.

Now the fs arm resolves an extensionless non-note source as a
directory (a note named exactly like the folder still wins), refuses
a move into the folder's own subtree BEFORE mkdir plants the target
inside the source, and rewrites links once per moved file. The
rewriter grew an identity guard: a folder move keeps every basename,
so [[alpha]] matches its old variants but rewrites to identical text
— that's not a "followed" link and must not churn the file's mtime.
Client-side, folder rows drag like file rows; a folder hovered over
itself or its children refuses the claim (the ground below claims
instead, and its highlight is what the boss sees), and moveByDrag
maps a deep open note's path through the moved prefix. Verified
live: Drawer dragged onto Research answered "Moved 2 files to
Research — 2 links followed" and citer.md read [[Research/Drawer/alpha]].

Run: python3 scripts/test_a_folder_moves_as_one_drawer.py
"""
import ast
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import threading
import urllib.parse

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
const CafresoHQClient = { vaultRename: async (a, b) => { calls.push(['rename', a, b]); return { linksRewritten: 2, filesTouched: 1, folder: true, moved: 2 }; } };
const say = (m, tone) => calls.push(['say', m, tone]);
const snag = (m, e) => calls.push(['snag', m]);
const refresh = async () => calls.push(['refresh']);
const files = [
  { path: 'Drawer/alpha.md' }, { path: 'Drawer/sub/inner.md' },
  { path: 'taken/y.md' }, { path: 'Research/taken/z.md' },
];
const openNoteRef = { current: { path: 'Drawer/sub/inner.md', dirty: true } };
const saveNoteRef = { current: async () => calls.push(['flush']) };
let opened = null;
const setOpenNote = (fn) => { opened = fn(openNoteRef.current); };

%s

(async () => {
  const out = {};
  calls.length = 0;
  await moveByDrag('Drawer', 'Research');
  out.move = calls.slice(); out.opened = opened;
  calls.length = 0;
  await moveByDrag('Drawer', 'Drawer/sub');       // into its own subtree
  out.self = calls.slice();
  calls.length = 0;
  await moveByDrag('taken', 'Research');          // Research/taken/ exists
  out.collide = calls.slice();
  console.log(JSON.stringify(out));
})();
'''

# mkTree() re-runs the lifted slice over shared state cells — the test's
# stand-in for a React re-render, which is what refreshes the closures
# dropProps captured dragSrc into.
TREE_HARNESS = r'''
const _cells = []; let _ci = 0;
const useSV = (v) => { const i = _ci++; if (_cells.length <= i) _cells.push(v);
  return [_cells[i], (nv) => { _cells[i] = nv; }]; };
const moved = [];
const onMove = (s, f) => moved.push([s, f]);
function mkTree() { _ci = 0;
%s
  return { dragProps, dropProps, _MOVE_T };
}
const mk = (types) => ({ dataTransfer: { types, dropEffect: '', data: {},
    setData(t, v) { this.data[t] = v; }, getData(t) { return this.data[t] || ''; } },
  prevented: false, preventDefault() { this.prevented = true; }, stopPropagation() {} });
const t1 = mkTree();
const startEv = mk([t1._MOVE_T]);
t1.dragProps('Drawer').onDragStart(startEv);
const t2 = mkTree();                       // re-render after dragstart
const out = {};
const overSelf = mk([t2._MOVE_T]);
t2.dropProps('Drawer').onDragOver(overSelf);
out.selfClaimed = overSelf.prevented;
const overChild = mk([t2._MOVE_T]);
t2.dropProps('Drawer/sub').onDragOver(overChild);
out.childClaimed = overChild.prevented;
const overOther = mk([t2._MOVE_T]);
t2.dropProps('Research').onDragOver(overOther);
out.otherClaimed = overOther.prevented && overOther.dataTransfer.dropEffect === 'move';
const overGround = mk([t2._MOVE_T]);
t2.dropProps('').onDragOver(overGround);
out.groundClaimed = overGround.prevented;
t2.dropProps('Drawer').onDrop(startEv);    // self-drop: payload gate
out.selfDropped = moved.slice();
t2.dropProps('Research').onDrop(startEv);
out.dropped = moved.slice();
t1.dragProps('Drawer').onDragEnd();
const t3 = mkTree();
const after = mk([t3._MOVE_T]);
t3.dropProps('Drawer').onDragOver(after);
out.clearedAfterEnd = after.prevented;
console.log(JSON.stringify(out));
'''


def main():
    print('a folder moves as one drawer')
    serve = (ROOT / 'serve.py').read_text(encoding='utf-8')
    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')
    core = (ROOT / 'views' / 'core.jsx').read_text(encoding='utf-8')

    # ── server: resolvers + rewriter, lifted and run against a temp vault ──
    tree = ast.parse(serve)
    # #385 routed _vault_rewrite_wikilinks's write through _vault_write_local,
    # serialised by the module-level _vault_write_lock — lift both too and
    # give the namespace a real lock, or the rewriter can't find either name.
    want = ('_vault_resolve', '_vault_resolve_dir', '_vault_write_local',
            '_vault_rewrite_wikilinks')
    segs = {n.name: ast.get_source_segment(serve, n) for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name in want}
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / 'Drawer').mkdir()
        (root / 'Drawer' / 'alpha.md').write_text('# Alpha')
        (root / 'Drawer' / 'inner.md').write_text('Sibling: [[Drawer/alpha]]')
        (root / 'citer.md').write_text(
            'See [[Drawer/alpha|the alpha]] and by name [[alpha]].')
        ns = {'pathlib': pathlib, 're': re, 'urllib': urllib, 'os': os,
              'threading': threading, '_vault_write_lock': threading.Lock(),
              '_vault_root': str(root)}
        exec('\n\n'.join(segs[k] for k in want), ns)

        check("an extensionless note path still defaults to '.md'",
              str(ns['_vault_resolve']('Drawer')).endswith('Drawer.md'))
        check('the dir spelling resolves to the directory itself',
              ns['_vault_resolve_dir']('Drawer')
              == (root / 'Drawer').resolve())
        try:
            ns['_vault_resolve_dir']('../outside')
            check('the dir spelling keeps traversal protection', False)
        except ValueError:
            check('the dir spelling keeps traversal protection', True)

        # identity guard: a rewrite that changes nothing touches nothing
        before = (root / 'citer.md').stat().st_mtime_ns
        r0 = ns['_vault_rewrite_wikilinks']('Drawer/lone.md', 'Other/lone.md')
        check('an identity rewrite counts zero and churns no mtime',
              r0 == (0, 0)
              and (root / 'citer.md').stat().st_mtime_ns == before, r0)

        # the folder move itself, per-file — exactly what the fs arm runs
        (root / 'Research').mkdir()
        os.replace(str(root / 'Drawer'), str(root / 'Research' / 'Drawer'))
        links = touched = 0
        for f in sorted((root / 'Research' / 'Drawer').rglob('*')):
            if f.is_file():
                tail = f.relative_to(root / 'Research' / 'Drawer').as_posix()
                r2, t2 = ns['_vault_rewrite_wikilinks'](
                    'Drawer/' + tail, 'Research/Drawer/' + tail)
                links += r2
                touched += t2
        citer = (root / 'citer.md').read_text()
        inner = (root / 'Research' / 'Drawer' / 'inner.md').read_text()
        check('a path link follows the drawer, alias kept',
              '[[Research/Drawer/alpha|the alpha]]' in citer, citer)
        check('a basename link was never folder-bound and stands',
              '[[alpha]]' in citer, citer)
        check("the drawer's own internal links follow too",
              '[[Research/Drawer/alpha]]' in inner, inner)
        check('the receipt counts changed links only, one per change',
              (links, touched) == (2, 2), (links, touched))

    # ── the fs arm's folder plumbing, pinned where it can't be executed ──
    check('the arm resolves an extensionless non-note source as a folder',
          '_vault_resolve_dir(src)' in serve and 's_dir.is_dir()' in serve)
    check("a folder source resolves its destination without the '.md' default",
          '_vault_resolve_dir(dst) if s_path.is_dir()' in serve)
    check('a move into the own subtree is refused before mkdir digs the hole',
          'cannot move a folder into itself' in serve
          and serve.index('cannot move a folder into itself')
          < serve.index('d_path.parent.mkdir'))
    check('a folder answer says so, with the moved count',
          "'folder': True, 'moved': moved," in serve)

    # ── client: moveByDrag understands a folder payload ──
    fn = brace_lift(vault, 'const moveByDrag = async (src, destFolder) => {')
    p = subprocess.run(['node', '-e', MOVE_HARNESS % fn],
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    out = json.loads(p.stdout.strip().split('\n')[-1])

    mv = out['move']
    check('a dropped folder rides the same rename door',
          ['rename', 'Drawer', 'Research/Drawer'] in mv, mv)
    check('a dirty note deep inside the drawer is flushed first',
          ['flush'] in mv)
    check("the open note's path maps through the moved prefix",
          out['opened'] and out['opened']['path'] == 'Research/Drawer/sub/inner.md',
          out['opened'])
    check('the receipt counts files moved, not just the folder',
          any(c[0] == 'say' and c[1].startswith('Moved 2 files to Research')
              for c in mv), mv)
    check('a folder never moves into its own subtree',
          not any(c[0] == 'rename' for c in out['self'])
          and any(c[0] == 'say' and c[2] == 'error' for c in out['self']),
          out['self'])
    check('a folder collision is refused by resident prefix, not exact path',
          not any(c[0] == 'rename' for c in out['collide'])
          and any(c[0] == 'say' and c[2] == 'error' for c in out['collide']),
          out['collide'])

    # ── client: tree rows — folders drag, self-drops fall through ──
    i = core.index('const [dragOverF, setDragOverF]')
    j = core.index('const toggle = (path)')
    p2 = subprocess.run(['node', '-e', TREE_HARNESS % core[i:j]],
                        capture_output=True, text=True, timeout=60)
    if p2.returncode != 0:
        print(p2.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on the tree drag plumbing')
    t = json.loads(p2.stdout.strip().split('\n')[-1])

    check('a folder hovered over itself refuses the claim',
          not t['selfClaimed'], t)
    check('…and over its own children', not t['childClaimed'])
    check('another folder still claims with a move cursor', t['otherClaimed'])
    check('the ground still claims (that highlight is the answer shown)',
          t['groundClaimed'])
    check('a self-drop falls through instead of erroring',
          t['selfDropped'] == [], t['selfDropped'])
    check('a real drop still hands (source, folder) to the mover',
          t['dropped'] == [['Drawer', 'Research']], t['dropped'])
    check('dragend clears the gate for the next drag', t['clearedAfterEnd'])

    check('folder rows are draggable rows too',
          '{...dropProps(n.path)}\n            {...dragProps(n.path)}' in core)

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
