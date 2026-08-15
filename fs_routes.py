"""Filesystem-browser routes — extracted from serve.py.

The /fs/* endpoints behind the Projects path picker: browse, read, stat,
upload, mkdir/rename/delete, and the static site server. Plain functions
taking serve.py's request handler as `self`, bound onto its Handler class.

SECURITY: every path goes through self._validate_path (Handler's, unchanged)
and _within_allowed_dirs. _fs_site additionally runs strict validation for
any non-loopback peer — see _site_sandbox_ok in serve.py. serve.py injects
_client_path and _RUNTIME_ENV after import; the allowlist itself is read off
the handler so a config reload can't leave a stale copy here.
"""
import base64
import json
import mimetypes
import os
import pathlib
import shutil
import time
import urllib.parse

# Injected by serve.py right after import.
_client_path = None
# Anchors a relative path to the workspace root before it is resolved. The
# three routes below that resolve their OWN path (browse / file / stat) must
# use it rather than pathlib.Path(_client_path(x)) — otherwise a relative path
# means the workspace at the doors that go through _validate_path and the
# server's cwd at these three, which is the split #78 was about.
_workspace_path = None
_RUNTIME_ENV = 'local'
_cafresohq_allowed_dirs = ()
_ALLOWED_DIRS_EXPLICIT = False
_within_allowed_dirs = None

# ---- Filesystem browser (used by Projects path picker) ---------------
def _fs_browse(self):
    """GET /fs/browse?path=<dir>
    Returns a directory listing for the path picker popup.
    In container mode: restricted to CAFRESOHQ_ALLOWED_DIRS subtrees.
    In local mode: any readable path is allowed.
    Response: {path, parent, entries:[{name, type:'dir'|'file', path}]}
    """
    qs = urllib.parse.urlparse(self.path).query
    params = urllib.parse.parse_qs(qs)
    req_path = (params.get('path') or [''])[0].strip()

    # Default starting location: first allowed dir → home → cwd
    if not req_path:
        if _cafresohq_allowed_dirs:
            req_path = _cafresohq_allowed_dirs[0]
        else:
            try:
                req_path = str(pathlib.Path.home())
            except Exception:
                req_path = os.getcwd()

    try:
        p = _workspace_path(req_path).resolve()
    except Exception as e:
        return self._send_json(400, {'error': f'invalid path: {e}'})

    if not p.is_dir():
        return self._send_json(400, {'error': 'not a directory'})

    # Only browse within allowed dirs — enforced in EVERY mode (was
    # container-only, which left local/BYO reads unbounded).
    if not _within_allowed_dirs(p):
        return self._send_json(403, {
            'error': 'path is outside CAFRESOHQ_ALLOWED_DIRS',
            'allowed': _cafresohq_allowed_dirs,
        })

    try:
        raw = list(p.iterdir())
    except PermissionError:
        return self._send_json(403, {'error': 'permission denied'})
    except Exception as e:
        return self._send_json(500, {'error': f'listing failed: {e}'})

    # Build entries — guard each is_dir() individually because Windows
    # junction points / reparse points can raise ValueError for some paths.
    entries = []
    for item in raw:
        if item.name.startswith('.'):
            continue
        try:
            is_dir = item.is_dir()
        except Exception:
            continue  # skip inaccessible / broken entries silently
        entries.append({
            'name': item.name,
            'type': 'dir' if is_dir else 'file',
            'path': str(item),
        })
    # Dirs first, then files, both alphabetical
    entries.sort(key=lambda e: (e['type'] != 'dir', e['name'].lower()))

    parent = str(p.parent) if str(p.parent) != str(p) else None
    return self._send_json(200, {
        'path':    str(p),
        'parent':  parent,
        'entries': entries,
    })

def _fs_collect(self):
    """GET /fs/collect?path=<dir>
    Walk a built-site directory and return every file as base64 + a guessed
    content-type, so the authenticated shell can upload the site to the
    cafresohq_state canister's site host (Publish-to-Canister). Same
    allowed-dirs guard as the other /fs endpoints (via _validate_path), so
    it can't read outside the sandbox. Skips hidden/.url files and files
    larger than the canister's ~2 MiB per-file cap (reported in `skipped`).
    Response: {root, files:[{path, contentType, size, b64}], skipped:[...]}
    """
    import mimetypes, base64
    qs = urllib.parse.urlparse(self.path).query
    req_path = (urllib.parse.parse_qs(qs).get('path') or [''])[0].strip()
    if not req_path:
        return self._send_json(400, {'error': 'path required'})
    try:
        root = self._validate_path(req_path)
    except PermissionError as e:
        return self._send_json(403, {'error': str(e)})
    except Exception as e:
        return self._send_json(400, {'error': f'invalid path: {e}'})
    if not root.is_dir():
        return self._send_json(400, {'error': 'not a directory'})

    MAX_FILE = 2_000_000       # matches cafresohq_state MAX_SITE_FILE_BYTES
    MAX_FILES = 300            # sanity cap on a single publish
    files, skipped = [], []
    for dirpath, dirnames, filenames in os.walk(root):
        # prune hidden dirs (node_modules-style publishing is out of scope for MVP)
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for name in filenames:
            if name.startswith('.') or name.lower().endswith('.url'):
                continue
            full = pathlib.Path(dirpath) / name
            try:
                rel = full.relative_to(root).as_posix()
                size = full.stat().st_size
            except Exception:
                continue
            if size > MAX_FILE:
                skipped.append({'path': rel, 'reason': 'over 2 MiB'})
                continue
            if len(files) >= MAX_FILES:
                skipped.append({'path': rel, 'reason': 'file limit reached'})
                continue
            ctype = mimetypes.guess_type(name)[0] or 'application/octet-stream'
            if ctype.startswith('text/') or ctype in ('application/javascript', 'application/json'):
                ctype = ctype + '; charset=utf-8'
            try:
                data = full.read_bytes()
            except Exception as e:
                skipped.append({'path': rel, 'reason': str(e)})
                continue
            files.append({
                'path': rel,
                'contentType': ctype,
                'size': size,
                'b64': base64.b64encode(data).decode('ascii'),
            })
    return self._send_json(200, {'root': str(root), 'files': files, 'skipped': skipped})

def _fs_file(self):
    """GET /fs/file?path=<file>
    Serve a single file's raw bytes with a guessed content-type, INLINE so the
    browser renders it directly — the enabler for the artifact preview pane
    (HTML / PDF / image / SVG built by an agent). Read-only. Same allowed-dirs
    gate as /fs/browse (container mode), so it can't traverse outside the
    sandbox. Capped at 50 MiB to keep a runaway file from hanging the preview.
    """
    import mimetypes
    qs = urllib.parse.urlparse(self.path).query
    req_path = (urllib.parse.parse_qs(qs).get('path') or [''])[0].strip()
    if not req_path:
        return self._send_json(400, {'error': 'path required'})
    try:
        p = _workspace_path(req_path).resolve()
    except Exception as e:
        return self._send_json(400, {'error': f'invalid path: {e}'})
    # "not a file" answered two different questions with one string, and the
    # surfaces that print it could only relay the ambiguity: a boss clicking a
    # ledger row for a folder was told the office "couldn't find that". Say
    # which it is; the reader's cause table maps each to its own sentence.
    if not p.exists():
        return self._send_json(404, {'error': 'no such file'})
    if not p.is_file():
        return self._send_json(400, {'error': 'that is a folder, not a file'})
    # Serve only within CAFRESOHQ_ALLOWED_DIRS — every mode (was container-
    # only, which exposed unauthenticated arbitrary file read in local/BYO).
    if not _within_allowed_dirs(p):
        return self._send_json(403, {'error': 'path is outside CAFRESOHQ_ALLOWED_DIRS',
                                     'allowed': _cafresohq_allowed_dirs})
    try:
        if p.stat().st_size > 50 * 1024 * 1024:
            return self._send_json(413, {'error': 'file too large to preview (>50 MiB)'})
        data = p.read_bytes()
    except PermissionError:
        return self._send_json(403, {'error': 'permission denied'})
    except Exception as e:
        return self._send_json(500, {'error': f'read failed: {e}'})
    ctype = mimetypes.guess_type(str(p))[0] or 'application/octet-stream'
    import hashlib as _hl
    fhash = _hl.sha1(data).hexdigest()[:16]
    try:
        fmtime = int(p.stat().st_mtime)
    except Exception:
        fmtime = 0
    self.send_response(200)
    self.send_header('Content-Type', ctype)
    self.send_header('Content-Length', str(len(data)))
    self.send_header('Content-Disposition', 'inline; filename="%s"' % p.name.replace('"', ''))
    # Conflict-safety: the editor captures these on read and re-checks before
    # saving / on an agent write, so co-editing never silently clobbers.
    self.send_header('X-File-Mtime', str(fmtime))
    self.send_header('X-File-Hash', fhash)
    self.send_header('Access-Control-Expose-Headers', 'X-File-Mtime, X-File-Hash')
    self.send_header('Cache-Control', 'no-store')
    self.end_headers()
    try:
        self.wfile.write(data)
    except Exception:
        pass

def _fs_stat(self):
    """GET /fs/stat?path=<file>  ->  {ok, mtime, hash, size}
    Cheap conflict-check for the editor (no content body): compare against the
    X-File-Mtime / X-File-Hash captured at read time before saving or on an
    agent write, so co-editing never silently clobbers. Same allowed-dirs
    guard as /fs/file; hash matches /fs/file's (sha1, first 16 hex)."""
    import hashlib as _hl
    qs = urllib.parse.urlparse(self.path).query
    req_path = (urllib.parse.parse_qs(qs).get('path') or [''])[0].strip()
    if not req_path:
        return self._send_json(400, {'error': 'path required'})
    try:
        p = _workspace_path(req_path).resolve()
    except Exception as e:
        return self._send_json(400, {'error': f'invalid path: {e}'})
    if not _within_allowed_dirs(p):
        return self._send_json(403, {'error': 'path is outside CAFRESOHQ_ALLOWED_DIRS'})
    if not p.exists():
        return self._send_json(404, {'ok': False, 'error': 'no such file'})
    if not p.is_file():
        return self._send_json(400, {'ok': False, 'error': 'that is a folder, not a file'})
    try:
        st = p.stat()
        h = _hl.sha1(p.read_bytes()).hexdigest()[:16]
    except Exception as e:
        return self._send_json(500, {'error': str(e)})
    return self._send_json(200, {'ok': True, 'mtime': int(st.st_mtime), 'hash': h, 'size': st.st_size})

def _fs_site(self):
    """GET /fs/site/<b64root>/<relpath>
    Serve a multi-file site from a directory so an agent-built page's
    RELATIVE refs (<link href=styles.css>, <script src=app.js>, <img
    src=assets/x.png>) resolve — the preview pane points an iframe at
    index.html here and the browser fetches every sibling/sub-asset back
    through the same /fs/site/<b64root>/ prefix. <b64root> is urlsafe
    base64 of the absolute site root; <relpath> is resolved under it.

    This route is NOT behind CAFRESOHQ_API_KEY, so its own boundary is the
    only one: off-loopback callers get strict _validate_path, which requires
    an explicit CAFRESOHQ_ALLOWED_DIRS sandbox and refuses the local-mode
    skip. Loopback callers keep the relaxed local rules so previewing a site
    outside the sandbox still works while developing.

    Read-only, embeddable (no X-Frame-Options), 50 MiB/file cap. An empty
    relpath or a directory falls back to index.html.
    """
    import base64, mimetypes
    rest = self.path[len('/fs/site/'):]
    rest = rest.split('?', 1)[0].split('#', 1)[0]
    if '/' in rest:
        b64root, relpath = rest.split('/', 1)
    else:
        b64root, relpath = rest, ''
    if not b64root:
        return self._send_json(400, {'error': 'site root required'})
    # This route is deliberately NOT behind CAFRESOHQ_API_KEY (the preview
    # iframe fetches assets keyless), so it must carry its own boundary:
    # an explicit allowed-dirs sandbox, or a loopback caller.
    _strict = not self._site_sandbox_ok()
    if _strict and not _cafresohq_allowed_dirs:
        return self._send_json(403, {'error':
            'site preview requires CAFRESOHQ_ALLOWED_DIRS when served off-loopback'})
    try:
        pad = '=' * (-len(b64root) % 4)
        root = base64.urlsafe_b64decode(b64root + pad).decode('utf-8')
    except Exception as e:
        return self._send_json(400, {'error': f'bad site root: {e}'})
    rel = urllib.parse.unquote(relpath).strip('/')
    if not rel:
        rel = 'index.html'
    try:
        root_p = self._validate_path(root, strict=_strict)
    except PermissionError as e:
        return self._send_json(403, {'error': str(e)})
    except Exception as e:
        return self._send_json(400, {'error': f'invalid root: {e}'})
    try:
        target = self._validate_path(str(root_p / rel), strict=_strict)
    except PermissionError as e:
        return self._send_json(403, {'error': str(e)})
    except Exception as e:
        return self._send_json(400, {'error': f'invalid path: {e}'})
    if target.is_dir():
        try:
            target = self._validate_path(str(target / 'index.html'), strict=_strict)
        except Exception:
            return self._send_json(404, {'error': 'no index.html in directory'})
    if not target.is_file():
        return self._send_json(404, {'error': 'not found'})
    try:
        if target.stat().st_size > 50 * 1024 * 1024:
            return self._send_json(413, {'error': 'file too large to preview (>50 MiB)'})
        data = target.read_bytes()
    except PermissionError:
        return self._send_json(403, {'error': 'permission denied'})
    except Exception as e:
        return self._send_json(500, {'error': f'read failed: {e}'})
    ctype = mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
    self.send_response(200)
    self.send_header('Content-Type', ctype)
    self.send_header('Content-Length', str(len(data)))
    self.send_header('Cache-Control', 'no-store')
    self.end_headers()
    try:
        self.wfile.write(data)
    except Exception:
        pass

def _fs_upload(self):
    """POST /fs/upload?path=<dir>   (multipart/form-data)
    Drop files into a project's working tree so the agents (FILE_READ /
    DIR_LIST) and the preview pane can immediately use them — the
    user-facing half of the "share files with agents" loop. Writes into
    the REAL filesystem, guarded by the same CAFRESOHQ_ALLOWED_DIRS
    whitelist as FILE_WRITE (via _validate_path), so it can't escape the
    sandbox. Filenames are flattened + sanitized; the target dir is created
    if missing; 50 MiB cap per request. ?path= defaults to the first
    allowed dir.
    """
    # Same enable-gate as /tools/exec FILE_WRITE: allow in unrestricted
    # local dev, otherwise require an explicit allow-list.
    _unrestricted_local = (_RUNTIME_ENV == 'local' and not _ALLOWED_DIRS_EXPLICIT)
    if not _cafresohq_allowed_dirs and not _unrestricted_local:
        return self._send_json(503, {'error': 'CAFRESOHQ_ALLOWED_DIRS not set — upload disabled'})

    ctype = self.headers.get('content-type', '')
    if 'multipart/form-data' not in ctype:
        return self._send_json(400, {'error': 'expected multipart/form-data'})
    length = int(self.headers.get('content-length', 0) or 0)
    if length <= 0:
        return self._send_json(400, {'error': 'empty upload'})
    if length > 50 * 1024 * 1024:
        return self._send_json(413, {'error': 'upload too large (50 MiB max)'})

    qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
    raw_dir = (qs.get('path') or [''])[0].strip()
    if not raw_dir:
        raw_dir = _cafresohq_allowed_dirs[0] if _cafresohq_allowed_dirs else os.getcwd()
    try:
        target_dir = self._validate_path(raw_dir)
    except PermissionError as e:
        return self._send_json(403, {'error': str(e)})
    except Exception as e:
        # Malformed path (e.g. embedded null byte) — resolve() raises
        # ValueError. Mirror _fs_browse/_fs_file: clean 400, not a dropped
        # connection.
        return self._send_json(400, {'error': f'invalid path: {e}'})
    if target_dir.exists() and not target_dir.is_dir():
        return self._send_json(400, {'error': 'target path is not a directory'})

    raw = self.rfile.read(length)
    import email.parser as _ep
    import re as _re
    msg = _ep.BytesParser().parsebytes(
        b'Content-Type: ' + ctype.encode('latin-1', 'replace') + b'\r\n\r\n' + raw)
    if not msg.is_multipart():
        return self._send_json(400, {'error': 'bad multipart body'})

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return self._send_json(500, {'error': f'mkdir failed: {e}'})

    saved, errors = [], []
    for part in msg.get_payload():
        fname = part.get_filename()
        if not fname:
            continue
        # Flatten any path components, then strip anything but a safe set.
        fname = fname.replace('\\', '/').split('/')[-1]
        fname = _re.sub(r'[^\w .()\[\]\-]+', '_', fname).strip()
        if not fname or fname.startswith('.'):
            continue
        dest = (target_dir / fname).resolve()
        # Defense-in-depth: re-assert the whitelist on the final path even
        # though a sanitized basename can't traverse.
        try:
            self._validate_path(str(dest))
        except PermissionError:
            errors.append({'path': fname, 'error': 'outside allowed dirs'})
            continue
        data = part.get_payload(decode=True) or b''
        try:
            dest.write_bytes(data)
            saved.append({'path': str(dest), 'name': fname, 'size': len(data)})
        except Exception as e:
            errors.append({'path': fname, 'error': str(e)})
    if not saved and errors:
        return self._send_json(500, {'error': errors[0]['error'], 'failed': errors})
    return self._send_json(200, {'uploaded': saved, 'count': len(saved),
                                 'dir': str(target_dir),
                                 **({'failed': errors} if errors else {})})

# ---- Working-tree file manager (mkdir / rename / delete) -------------
# All three share FILE_WRITE's posture: open in unrestricted local dev,
# else confined to CAFRESOHQ_ALLOWED_DIRS via _validate_path (resolve +
# .relative_to). They make the container feel like an OS the user owns.
def _fs_mutate_ok(self):
    _unrestricted_local = (_RUNTIME_ENV == 'local' and not _ALLOWED_DIRS_EXPLICIT)
    if not _cafresohq_allowed_dirs and not _unrestricted_local:
        self._send_json(503, {'error': 'CAFRESOHQ_ALLOWED_DIRS not set — file ops disabled'})
        return False
    return True

def _fs_json_body(self):
    length = int(self.headers.get('content-length', 0) or 0)
    try:
        return json.loads(self.rfile.read(length).decode('utf-8') or '{}')
    except Exception:
        return None

def _fs_mkdir(self):
    """POST /fs/mkdir  {path}  — create a folder in the working tree."""
    if not self._fs_mutate_ok():
        return
    req = self._fs_json_body()
    if req is None:
        return self._send_json(400, {'error': 'bad json'})
    raw = (req.get('path') or '').strip()
    if not raw:
        return self._send_json(400, {'error': 'path required'})
    try:
        target = self._validate_path(raw)
    except PermissionError as e:
        return self._send_json(403, {'error': str(e)})
    except Exception as e:
        return self._send_json(400, {'error': f'invalid path: {e}'})
    if target.exists():
        if target.is_dir():
            return self._send_json(200, {'ok': True, 'path': str(target), 'existed': True})
        return self._send_json(409, {'error': 'a file with that name exists'})
    try:
        target.mkdir(parents=True, exist_ok=True)
    except (NotADirectoryError, FileExistsError) as e:
        return self._send_json(409, {'error': f'cannot create folder here: {e}'})
    except Exception as e:
        return self._send_json(500, {'error': str(e)})
    return self._send_json(200, {'ok': True, 'path': str(target)})

def _fs_rename(self):
    """POST /fs/rename  {from, to}  — rename/move within the working tree."""
    if not self._fs_mutate_ok():
        return
    req = self._fs_json_body()
    if req is None:
        return self._send_json(400, {'error': 'bad json'})
    src = (req.get('from') or '').strip()
    dst = (req.get('to') or '').strip()
    if not src or not dst:
        return self._send_json(400, {'error': 'from and to required'})
    try:
        sp = self._validate_path(src)
        dp = self._validate_path(dst)
    except PermissionError as e:
        return self._send_json(403, {'error': str(e)})
    except Exception as e:
        return self._send_json(400, {'error': f'invalid path: {e}'})
    if not sp.exists():
        return self._send_json(404, {'error': 'source not found'})
    # Never move a workspace root itself (parallels _fs_delete; matters when
    # more than one allowed dir is configured).
    roots = {str(pathlib.Path(d).resolve()) for d in _cafresohq_allowed_dirs}
    if str(sp) in roots:
        return self._send_json(403, {'error': 'refusing to move a workspace root'})
    if dp.exists():
        return self._send_json(409, {'error': 'target already exists'})
    try:
        dp.parent.mkdir(parents=True, exist_ok=True)
        os.replace(str(sp), str(dp))
    except (NotADirectoryError, FileExistsError) as e:
        return self._send_json(409, {'error': f'cannot move there: {e}'})
    except Exception as e:
        return self._send_json(500, {'error': str(e)})
    return self._send_json(200, {'ok': True, 'from': str(sp), 'to': str(dp)})

def _fs_delete(self):
    """POST /fs/delete  {path}  — delete a file or directory (recursive)."""
    if not self._fs_mutate_ok():
        return
    req = self._fs_json_body()
    if req is None:
        return self._send_json(400, {'error': 'bad json'})
    raw = (req.get('path') or '').strip()
    if not raw:
        return self._send_json(400, {'error': 'path required'})
    try:
        target = self._validate_path(raw)
    except PermissionError as e:
        return self._send_json(403, {'error': str(e)})
    except Exception as e:
        return self._send_json(400, {'error': f'invalid path: {e}'})
    if not target.exists() and not target.is_symlink():
        return self._send_json(404, {'error': 'not found'})
    # Never delete an allowed-dir root itself.
    roots = {str(pathlib.Path(d).resolve()) for d in _cafresohq_allowed_dirs}
    if str(target) in roots:
        return self._send_json(403, {'error': 'refusing to delete a workspace root'})
    try:
        # Follow-the-link guard: a symlinked dir is unlinked (remove the
        # link), never rmtree'd (which would wipe the link's target).
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(str(target))
        else:
            target.unlink()
    except Exception as e:
        return self._send_json(500, {'error': str(e)})
    return self._send_json(200, {'ok': True, 'deleted': str(target)})

