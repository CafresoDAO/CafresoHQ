#!/usr/bin/env python3
"""POST /fs/delete unlinked symlinks that live OUTSIDE CAFRESOHQ_ALLOWED_DIRS.

`fs_routes._fs_delete` validates the request path with `self._validate_path`,
which `.resolve()`s before whitelist-checking. For a symlink that means the
403 gate is asked about the link's DESTINATION, never about the link's own
location. The route then deletes the link at its unresolved path:

    link_path = _workspace_path(raw)
    is_link   = link_path.is_symlink()
    ...
    (link_path if is_link else target).unlink()

So a symlink parked anywhere on the host — `/usr/local/bin/node`, a link in
someone else's home — that merely POINTS at something inside the sandbox
passed the whitelist and was then removed at its out-of-sandbox location.
The delete door walked straight out of CAFRESOHQ_ALLOWED_DIRS.

`_fs_rename` already carries the twin guard and says why in its own comment
("a link living OUTSIDE the sandbox must not become movable just because its
target happens to sit inside"); the same reasoning was never applied to
delete, so the two mutation doors disagreed about where the sandbox ends.

Fix: when the requested path is a symlink, whitelist-check the LINK'S OWN
parent directory too, and 403 when that parent is outside the sandbox.

This test drives the real `fs_routes._fs_delete` (no reimplementation)
against real temp directories, with a `_validate_path` mirroring serve.py's:
  - a symlink outside the sandbox pointing in: must be REFUSED and must
    still exist afterwards (the vulnerability);
  - a symlink inside the sandbox pointing inside: still deleted, target
    spared (the fix must not regress ordinary symlink deletion);
  - a plain file inside the sandbox: still deleted.

Run: python3 scripts/test_fs_delete_never_removes_a_link_that_lives_outside_the_sandbox.py
"""
import io
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
    print('POST /fs/delete never removes a link that lives outside the sandbox')
    sys.path.insert(0, str(ROOT))
    import fs_routes  # noqa: E402
    import pathlib

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp).resolve()
        allowed_root = base / 'workspace'
        allowed_root.mkdir()
        outside = base / 'elsewhere'          # NOT in the allow-list
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
            """Mirrors serve.py's Handler._validate_path: anchor, resolve()
            (which dereferences symlinks), then whitelist-check."""

            def __init__(self, body: bytes):
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

        def delete(path):
            body = ('{"path": %r}' % str(path)).replace("'", '"').encode('utf-8')
            req = FakeSelf(body)
            fs_routes._fs_delete(req)
            return req.sent

        # ---- The vulnerability: link outside the sandbox, target inside ----
        inside_file = allowed_root / 'notes.txt'
        inside_file.write_text('inside the sandbox', encoding='utf-8')
        stray_link = outside / 'stray_link'
        stray_link.symlink_to(inside_file)

        code, payload = delete(stray_link)
        check('deleting a symlink that LIVES outside the sandbox is refused 403',
              code == 403, (code, payload))
        check('...and the out-of-sandbox link is still on disk — this is the '
              'actual escape: before the fix /fs/delete removed files outside '
              'CAFRESOHQ_ALLOWED_DIRS whenever they pointed back inside it',
              stray_link.is_symlink(),
              f'stray_link survived: {stray_link.is_symlink()}')
        check('...and the file it pointed at is untouched',
              inside_file.exists(), f'inside_file exists: {inside_file.exists()}')

        # ---- Same shape, but the link points at a DIRECTORY ---------------
        inside_dir = allowed_root / 'project'
        inside_dir.mkdir()
        (inside_dir / 'a.txt').write_text('a', encoding='utf-8')
        stray_dir_link = outside / 'stray_dir_link'
        stray_dir_link.symlink_to(inside_dir, target_is_directory=True)

        code2, payload2 = delete(stray_dir_link)
        check('a symlinked DIRECTORY outside the sandbox is refused too',
              code2 == 403, (code2, payload2))
        check('...and that link is still on disk',
              stray_dir_link.is_symlink(), 'stray_dir_link was removed')
        check('...and the real directory it pointed at survives',
              (inside_dir / 'a.txt').exists(), 'inside_dir was harmed')

        # ---- Regression guard: a link INSIDE the sandbox still deletes ----
        real_dir = allowed_root / 'keep' / 'important_data'
        real_dir.mkdir(parents=True)
        keeper = real_dir / 'keepme.txt'
        keeper.write_text('do not delete me', encoding='utf-8')
        good_link = allowed_root / 'link_to_keep'
        good_link.symlink_to(real_dir, target_is_directory=True)

        code3, payload3 = delete(good_link)
        check('a symlink inside the sandbox is still deleted (200)',
              code3 == 200, (code3, payload3))
        check('...the link itself is gone',
              not good_link.is_symlink() and not good_link.exists(),
              'good_link still present')
        check('...and its real target is spared',
              real_dir.is_dir() and keeper.exists(), 'real target harmed')

        # ---- Regression guard: a plain file still deletes -----------------
        plain = allowed_root / 'plain.txt'
        plain.write_text('x', encoding='utf-8')
        code4, payload4 = delete(plain)
        check('an ordinary file inside the sandbox is still deleted',
              code4 == 200 and not plain.exists(), (code4, payload4, plain.exists()))

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
