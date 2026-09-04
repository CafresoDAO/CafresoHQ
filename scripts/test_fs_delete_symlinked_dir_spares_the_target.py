#!/usr/bin/env python3
"""POST /fs/delete on a symlinked directory wiped the link's real target.

`fs_routes._fs_delete` resolves the request path through `self._validate_path`
(serve.py), which calls `.resolve()` — pathlib's own symlink dereferencing —
before returning. So the `target` the route ends up holding is already the
symlink's REAL destination, never the symlink itself: `target.is_symlink()`
on a resolved path is always False (the thing it points at isn't itself a
link). The route's own comment says otherwise:

    # Follow-the-link guard: a symlinked dir is unlinked (remove the
    # link), never rmtree'd (which would wipe the link's target).
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(str(target))
    else:
        target.unlink()

Because `target.is_symlink()` can never be True here, a symlinked directory
always takes the `shutil.rmtree(target)` branch — on the RESOLVED path, i.e.
the real directory the link points to. Deleting a symlink inside the sandbox
recursively destroys whatever real directory it points at (even one that
lives elsewhere in the same sandbox), instead of merely removing the link,
exactly the outcome the comment says is avoided.

Fix: check symlink-ness on the UNRESOLVED, anchored path (via the same
`_workspace_path` helper the read routes already use for anchoring, with no
resolve()) instead of the already-dereferenced `target`, and unlink THAT
path (not `target`) when it is a link, so only the link is removed and the
real directory it points to is untouched.

This test genuinely invokes the real `fs_routes._fs_delete` (not a
reimplementation), wiring a `_validate_path` that mirrors serve.py's own
(anchor, then `.resolve()`, then whitelist-check), against real temp
directories:
  - a symlinked directory elsewhere in the sandbox: deleting the link must
    leave the real target directory and its file intact, and the link
    itself must be gone.
  - a plain (non-symlinked) directory: unaffected, still rmtree'd for real,
    so the fix doesn't regress ordinary delete.

Run: python3 scripts/test_fs_delete_symlinked_dir_spares_the_target.py
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
    print("POST /fs/delete on a symlinked dir spares the link's real target")
    sys.path.insert(0, str(ROOT))
    import fs_routes  # noqa: E402
    import pathlib

    with tempfile.TemporaryDirectory() as tmp:
        allowed_root = Path(tmp).resolve()

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

        # ---- Symlinked directory: the real bug ---------------------------
        real_dir = allowed_root / 'keep' / 'important_data'
        real_dir.mkdir(parents=True)
        keeper = real_dir / 'keepme.txt'
        keeper.write_text('do not delete me', encoding='utf-8')

        link_dir = allowed_root / 'scratch'
        link_dir.mkdir()
        link_path = link_dir / 'link_to_keep'
        link_path.symlink_to(real_dir, target_is_directory=True)

        body = ('{"path": %r}' % str(link_path)).replace("'", '"').encode('utf-8')
        req = FakeSelf(body)
        fs_routes._fs_delete(req)
        code, payload = req.sent

        check('deleting the symlink returns 200 ok',
              code == 200, (code, payload))
        check("the link itself is gone",
              not link_path.is_symlink() and not link_path.exists(),
              f'link_path still present: {link_path.exists()}')
        check("the REAL target directory the link pointed to is untouched — "
              "this is the actual vulnerability: before the fix, deleting "
              "the link recursively wiped the directory it pointed at",
              real_dir.is_dir(), f'real_dir survives: {real_dir.is_dir()}')
        check("...and the file inside it survives",
              keeper.exists() and keeper.read_text(encoding='utf-8') == 'do not delete me',
              f'keeper exists: {keeper.exists()}')

        # ---- Plain directory: fix must not regress ordinary delete -------
        plain_dir = allowed_root / 'plain'
        plain_dir.mkdir()
        (plain_dir / 'x.txt').write_text('x', encoding='utf-8')
        body2 = ('{"path": %r}' % str(plain_dir)).replace("'", '"').encode('utf-8')
        req2 = FakeSelf(body2)
        fs_routes._fs_delete(req2)
        code2, payload2 = req2.sent
        check('a plain (non-symlinked) directory is still really deleted',
              code2 == 200 and not plain_dir.exists(), (code2, payload2, plain_dir.exists()))

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
