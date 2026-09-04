#!/usr/bin/env python3
"""POST /fs/rename on a symlink moved the file the link POINTED AT.

`fs_routes._fs_rename` resolves the source path through `self._validate_path`
(serve.py), which calls `.resolve()` — pathlib's own symlink dereferencing.
So the `sp` the route ends up holding is never the symlink itself; it is the
link's REAL destination. The route then did:

    os.replace(str(sp), str(dp))

which moves that real destination. Rename a shortcut in the working-tree file
manager and the actual folder it points to is torn out of its own home and
dropped at the new name, while the shortcut the boss clicked is left behind
dangling. #226 fixed exactly this dereference trap in `_fs_delete` (and left a
comment about it there); `_fs_rename`, two functions up, still had it.

Fix: read link-ness off the UNRESOLVED, anchored path (`_workspace_path` with
no resolve(), the same anchoring the read routes use) and `os.replace` THAT
path when it is a link, so only the link moves. A link whose own location is
outside the sandbox is whitelist-checked separately — `sp` proves only where a
link points, not where it lives — and a dangling link becomes renamable rather
than 404, since it does exist as a link.

This test genuinely invokes the real `fs_routes._fs_rename` (not a
reimplementation), wiring a `_validate_path` that mirrors serve.py's own
(anchor, then `.resolve()`, then whitelist-check), against real temp dirs:
  - a symlinked directory: renaming the link must leave the real target
    directory and its file exactly where they were, and the link must appear
    under the new name still pointing at that target.
  - a plain file: unaffected, still really moved, so ordinary rename is not
    regressed.
  - a symlink that LIVES outside the sandbox but points inside must stay
    refused (the fix must not open a new door).

Run: python3 scripts/test_fs_rename_symlink_moves_the_link_not_its_target.py
"""
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('POST /fs/rename on a symlink moves the link, not its target')
    sys.path.insert(0, str(ROOT))
    import fs_routes  # noqa: E402
    import pathlib

    with tempfile.TemporaryDirectory() as tmp:
        allowed_root = Path(tmp).resolve() / 'workspace'
        allowed_root.mkdir()
        outside = Path(tmp).resolve() / 'outside'
        outside.mkdir()

        def _workspace_path(path, strict=False):
            p = pathlib.Path(path)
            if not p.is_absolute():
                p = allowed_root / p
            return p

        fs_routes._client_path = lambda p: p
        fs_routes._workspace_path = _workspace_path
        fs_routes._RUNTIME_ENV = 'container'   # force the whitelist ON
        fs_routes._ALLOWED_DIRS_EXPLICIT = True
        fs_routes._cafresohq_allowed_dirs = (str(allowed_root),)

        class FakeSelf:
            """Mirrors serve.py's Handler._validate_path closely enough to
            exercise the real resolve()-dereferences-symlinks behavior the
            bug depends on."""

            def __init__(self, payload):
                body = json.dumps(payload).encode('utf-8')
                self.headers = {'content-length': str(len(body))}
                self.rfile = io.BytesIO(body)
                self.sent = None

            def _send_json(self, code, payload):
                self.sent = (code, payload)

            def _validate_path(self, path, strict=False):
                p = _workspace_path(path, strict=strict).resolve()
                for d in fs_routes._cafresohq_allowed_dirs:
                    try:
                        p.relative_to(pathlib.Path(d).resolve())
                        return p
                    except ValueError:
                        continue
                raise PermissionError(f'Path outside allowed directories: {path!r}')

            def _fs_mutate_ok(self):
                return fs_routes._fs_mutate_ok(self)

            def _fs_json_body(self):
                return fs_routes._fs_json_body(self)

        # ---- Symlinked directory: the real bug ---------------------------
        real_dir = allowed_root / 'keep' / 'important_data'
        real_dir.mkdir(parents=True)
        keeper = real_dir / 'keepme.txt'
        keeper.write_text('do not move me', encoding='utf-8')

        scratch = allowed_root / 'scratch'
        scratch.mkdir()
        link_path = scratch / 'shortcut'
        link_path.symlink_to(real_dir, target_is_directory=True)
        renamed = scratch / 'shortcut_renamed'

        req = FakeSelf({'from': str(link_path), 'to': str(renamed)})
        fs_routes._fs_rename(req)
        code, payload = req.sent

        check('renaming the symlink returns 200 ok', code == 200, (code, payload))
        check('the REAL directory the link pointed to has NOT moved — this is '
              'the actual bug: before the fix, renaming the shortcut tore the '
              'real folder out of its home',
              real_dir.is_dir(), f'real_dir still at original location: {real_dir.is_dir()}')
        check('...and the file inside it survives in place',
              keeper.exists() and keeper.read_text(encoding='utf-8') == 'do not move me',
              f'keeper exists: {keeper.exists()}')
        check('the link now lives under the new name',
              renamed.is_symlink(), f'renamed.is_symlink(): {renamed.is_symlink()}')
        check('...and still points at the real directory',
              renamed.is_symlink()
              and renamed.resolve() == real_dir.resolve(),
              f'target: {renamed.resolve() if renamed.is_symlink() else None}')
        check('the old link name is gone',
              not link_path.is_symlink() and not link_path.exists(),
              f'old link present: {link_path.is_symlink()}')

        # ---- Plain file: fix must not regress ordinary rename -------------
        plain = allowed_root / 'notes.md'
        plain.write_text('hello', encoding='utf-8')
        plain_dst = allowed_root / 'notes-renamed.md'
        req2 = FakeSelf({'from': str(plain), 'to': str(plain_dst)})
        fs_routes._fs_rename(req2)
        code2, payload2 = req2.sent
        check('a plain file is still really renamed',
              code2 == 200 and plain_dst.exists() and not plain.exists()
              and plain_dst.read_text(encoding='utf-8') == 'hello',
              (code2, payload2, plain_dst.exists(), plain.exists()))

        # ---- A link living OUTSIDE the sandbox stays refused --------------
        inside_target = allowed_root / 'inside_target.txt'
        inside_target.write_text('inside', encoding='utf-8')
        outside_link = outside / 'sneaky'
        outside_link.symlink_to(inside_target)
        req3 = FakeSelf({'from': str(outside_link),
                         'to': str(allowed_root / 'stolen')})
        fs_routes._fs_rename(req3)
        code3, payload3 = req3.sent
        check('a symlink that LIVES outside the sandbox is refused even though '
              'it points inside',
              code3 == 403 and outside_link.is_symlink(),
              (code3, payload3, outside_link.is_symlink()))
        check('...and nothing was moved for it',
              inside_target.exists() and not (allowed_root / 'stolen').exists(),
              (inside_target.exists(), (allowed_root / 'stolen').exists()))

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
