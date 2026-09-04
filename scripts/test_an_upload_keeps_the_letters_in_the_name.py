#!/usr/bin/env python3
"""An accented or non-Latin filename was destroyed before it was sanitized.

Both upload doors parse the multipart body with email.parser.BytesParser.
Its compat32 policy decodes header bytes as ASCII and runs get_filename()
through email.header, which replaces every 8-bit byte with U+FFFD. Browsers
send the picked filename as raw UTF-8, so the name upload_name() received
was already mojibake — and U+FFFD is not \\w, so the sanitizer turned it
into underscores. Reproduced before the fix, driving _fs_upload directly:

    picked  'résumé.txt'   filed as  'r_sum_.txt'
    picked  '报告.txt'      filed as  '_.txt'
    picked  '数据.txt'      filed as  '_ (2).txt'   (two different reports,
                                                    both now unreadable, and
                                                    only free_name kept the
                                                    second from replacing
                                                    the first)

The sanitizer was never at fault: _UPLOAD_UNSAFE's \\w class is unicode-aware
and keeps é and 报 as they are. fs_routes.part_filename now recovers the
original bytes through decode_header's 'unknown-8bit' chunk and re-reads the
parameter, and only when the parser actually reported loss — an ASCII name
and an RFC 2231 filename*= (which compat32 decodes correctly on its own) go
through untouched.

Run: python3 scripts/test_an_upload_keeps_the_letters_in_the_name.py
"""
import email.parser as ep
import io
import os
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def _part(raw_header_bytes):
    """One multipart part, built from a raw Content-Disposition header."""
    body = (b'--X\r\n' + raw_header_bytes + b'\r\n\r\nhi\r\n--X--\r\n')
    msg = ep.BytesParser().parsebytes(
        b'Content-Type: multipart/form-data; boundary=X\r\n\r\n' + body)
    return msg.get_payload()[0]


class _Handler:
    """The bit of serve.py's request handler _fs_upload actually touches."""

    def __init__(self, td, body, ctype, query=''):
        self.td = pathlib.Path(td)
        self.path = '/fs/upload?path=' + query
        self.rfile = io.BytesIO(body)
        self.headers = {'content-type': ctype,
                        'content-length': str(len(body))}
        self.out = None

    def _send_json(self, code, payload):
        self.out = (code, payload)

    def _validate_path(self, p, strict=False):
        rp = (pathlib.Path(p) if os.path.isabs(p) else self.td / p).resolve()
        try:
            rp.relative_to(self.td.resolve())
        except ValueError:
            raise PermissionError('outside allowed directories')
        return rp


def _multipart(names):
    boundary = b'XbndY'
    buf = b''
    for raw in names:
        buf += (b'--' + boundary + b'\r\n'
                b'Content-Disposition: form-data; name="file"; filename="'
                + raw + b'"\r\n'
                b'Content-Type: application/octet-stream\r\n\r\n'
                b'hi\r\n')
    buf += b'--' + boundary + b'--\r\n'
    return buf, 'multipart/form-data; boundary=' + boundary.decode()


def _upload(fs_routes, td, names):
    body, ctype = _multipart(names)
    h = _Handler(td, body, ctype)
    fs_routes._fs_upload(h)
    return h.out[1]


def main():
    print('an upload keeps the letters in the name')
    import fs_routes

    # ── the helper itself ───────────────────────────────────────────────
    check('an accented name survives the header parser',
          fs_routes.part_filename(
              _part(b'Content-Disposition: form-data; name="f"; '
                    b'filename="r\xc3\xa9sum\xc3\xa9.txt"')) == 'résumé.txt')
    check('a non-Latin name survives it too',
          fs_routes.part_filename(
              _part(b'Content-Disposition: form-data; name="f"; '
                    b'filename="\xe6\x8a\xa5\xe5\x91\x8a.txt"')) == '报告.txt')
    check('a plain ASCII name is untouched',
          fs_routes.part_filename(
              _part(b'Content-Disposition: form-data; name="f"; '
                    b'filename="notes.txt"')) == 'notes.txt')
    check('an RFC 2231 filename*= is not double-decoded',
          fs_routes.part_filename(
              _part(b'Content-Disposition: form-data; name="f"; '
                    b"filename*=UTF-8%27%27r%C3%A9.txt")) == 'ré.txt')
    check('a form field (no filename) still reports None',
          fs_routes.part_filename(
              _part(b'Content-Disposition: form-data; name="f"')) is None)

    # ── the sanitizer was never the problem ─────────────────────────────
    check('upload_name keeps é once the name reaches it intact',
          fs_routes.upload_name('résumé.txt')['name'] == 'résumé.txt')
    check('upload_name keeps 报 once the name reaches it intact',
          fs_routes.upload_name('报告.txt')['name'] == '报告.txt')

    # ── end to end through the Projects door ────────────────────────────
    saved_env = (fs_routes._client_path, fs_routes._workspace_path,
                 fs_routes._RUNTIME_ENV, fs_routes._cafresohq_allowed_dirs,
                 fs_routes._ALLOWED_DIRS_EXPLICIT,
                 fs_routes._within_allowed_dirs)
    try:
        with tempfile.TemporaryDirectory() as td:
            fs_routes._client_path = lambda p: p
            fs_routes._workspace_path = (
                lambda p, strict=False: pathlib.Path(p) if os.path.isabs(p)
                else pathlib.Path(td) / p)
            fs_routes._RUNTIME_ENV = 'local'
            fs_routes._cafresohq_allowed_dirs = (td,)
            fs_routes._ALLOWED_DIRS_EXPLICIT = True
            fs_routes._within_allowed_dirs = lambda p: True

            body = _upload(fs_routes, td,
                           ['résumé.txt'.encode('utf-8'),
                            '报告.txt'.encode('utf-8'),
                            '数据.txt'.encode('utf-8')])
            filed = [e['name'] for e in body.get('uploaded', [])]
            check('/fs/upload files the accented name as picked',
                  'résumé.txt' in filed, filed)
            check('/fs/upload files both non-Latin names as picked',
                  '报告.txt' in filed and '数据.txt' in filed, filed)
            check('nothing was filed under an underscored stand-in',
                  not any('_' in n for n in filed), filed)
            check('no name collapsed onto another',
                  len(set(filed)) == 3 and not body.get('failed'), body)
            on_disk = sorted(p.name for p in pathlib.Path(td).iterdir())
            check('the real filenames are what landed on disk',
                  on_disk == sorted(['résumé.txt', '报告.txt', '数据.txt']),
                  on_disk)
    finally:
        (fs_routes._client_path, fs_routes._workspace_path,
         fs_routes._RUNTIME_ENV, fs_routes._cafresohq_allowed_dirs,
         fs_routes._ALLOWED_DIRS_EXPLICIT,
         fs_routes._within_allowed_dirs) = saved_env

    # ── structure: the Library door asks the same function ──────────────
    serve = (ROOT / 'serve.py').read_text(encoding='utf-8')
    check('the Library door reads the name through part_filename',
          re.search(r'raw_name = fs_routes\.part_filename\(part\)', serve))
    check('the Library door no longer asks get_filename directly',
          'raw_name = part.get_filename()' not in serve)

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
