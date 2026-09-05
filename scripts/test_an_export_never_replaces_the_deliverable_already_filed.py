#!/usr/bin/env python3
"""An export to an already-filed name used to destroy the first deliverable.

Every binary export door — EXPORT_PPTX / EXPORT_DOCX / EXPORT_PDF and the
image/video generators — resolves its target through exporters.py's
`_vault_binary_path`, and that resolver handed back the existing file's own
path whenever the name was already taken. `prs.save()` / `doc.save()` /
`write_bytes()` then wrote straight over it, and the receipt said 200 with
the same path as last time — Sloan exporting `Slides/q3.pptx` twice, or two
coworkers converging on the same conventional name, silently replaced the
first deck with the second. The boss's Library showed one file where two
deliverables had been made, and nothing anywhere said so.

The office already has a rule for exactly this, in exactly these words:
fs_routes.free_name — "a name already filed steps aside — never silently
replaced" — which both upload doors adopted after upload deck.pptx twice
ate the first copy the same way. The export doors never asked it.

Fix: `_vault_binary_path` now side-steps an existing name via
fs_routes.free_name ('report (2).pptx', …). The receipt already derives its
path from the resolved target, and the export tools carry that real path
out on `_ctx.meta.filedAs` (#180/#202), so the sidestep is announced in the
same channel a corrected extension already is.

Run: python3 scripts/test_an_export_never_replaces_the_deliverable_already_filed.py
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = '') -> None:
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond and detail else ''))
    if not cond:
        FAILS.append(name)


def resolver_checks(exporters) -> None:
    print('the shared resolver, straight from exporters.py')
    with tempfile.TemporaryDirectory() as td:
        exporters._vault_root = lambda: td
        exporters._vault_hidden_part = lambda rel: None

        first = exporters._vault_binary_path(None, 'Slides/q3.pptx', ('.pptx',))
        check('a fresh name resolves to itself',
              first.name == 'q3.pptx', first.name)
        check('…and the name is claimed on disk the instant it is resolved '
              '(#386 — no gap for a second resolver to land in)',
              first.is_file(), 'not created yet')

        first.write_bytes(b'the first deck')
        second = exporters._vault_binary_path(None, 'Slides/q3.pptx', ('.pptx',))
        check('a name already filed steps aside instead of being handed back',
              second != first, str(second))
        check('…to the same sidestep spelling the upload doors use',
              second.name == 'q3 (2).pptx', second.name)
        check('…in the same folder (no escape, no re-filing elsewhere)',
              second.parent == first.parent, str(second.parent))

        second.write_bytes(b'the second deck')
        third = exporters._vault_binary_path(None, 'Slides/q3.pptx', ('.pptx',))
        check('a third export keeps counting rather than eating (2)',
              third.name == 'q3 (3).pptx', third.name)

        # #386 claims the name atomically (O_CREAT|O_EXCL) the moment it is
        # resolved, closing the race two concurrent exports used to have —
        # so `third` above is no longer a "would-be" name still free for the
        # taking, it is ALREADY an empty file on disk the instant
        # _vault_binary_path returned it, exactly as if it had been written.
        # A fourth resolution has to count past it too.
        bare = exporters._vault_binary_path(None, 'Slides/q3', ('.pptx',))
        check('the appended-extension spelling collides with the same names too',
              bare.name == 'q3 (4).pptx', bare.name)


def full_door_checks(exporters) -> None:
    """The whole EXPORT_DOCX door, receipt included, against a temp vault.
    Only the python-docx boundary is stubbed (it is not installed on every
    office); everything from body-parse to receipt is the real code."""
    print('the EXPORT_DOCX door end to end')

    saved: dict = {}

    class _FakeDoc:
        def __init__(self):
            self.lines = []

        def add_heading(self, text, level=1):
            self.lines.append(text)

        def add_paragraph(self, text, style=None):
            self.lines.append(text)

        def save(self, path):
            pathlib.Path(path).write_text('\n'.join(self.lines),
                                          encoding='utf-8')
            saved['path'] = path

    fake_docx = types.ModuleType('docx')
    fake_docx.Document = _FakeDoc
    sys.modules['docx'] = fake_docx

    class Handler:
        _vault_binary_path = exporters._vault_binary_path

        def __init__(self, body):
            self._body = body
            self.resp = None

        def _read_json_body(self):
            return self._body

        def _send_json(self, code, obj):
            self.resp = (code, obj)

    with tempfile.TemporaryDirectory() as td:
        exporters._vault_root = lambda: td
        exporters._vault_hidden_part = lambda rel: None

        h1 = Handler({'path': 'Docs/report.docx', 'content': '# the first report'})
        exporters._export_docx(h1)
        code1, r1 = h1.resp
        check('the first export files under the asked-for name',
              code1 == 200 and r1.get('path') == 'Docs/report.docx', h1.resp)

        h2 = Handler({'path': 'Docs/report.docx', 'content': '# the second report'})
        exporters._export_docx(h2)
        code2, r2 = h2.resp
        check('the second export still succeeds', code2 == 200, h2.resp)
        check('…but files beside the first, never over it',
              r2.get('path') == 'Docs/report (2).docx', r2.get('path'))

        first_file = pathlib.Path(td) / 'Docs' / 'report.docx'
        check('the first deliverable still holds its own content',
              first_file.read_text(encoding='utf-8') == 'the first report',
              first_file.read_text(encoding='utf-8'))

        receipt_file = pathlib.Path(td) / (r2.get('path') or '')
        check('the receipt names a file that really exists on disk',
              receipt_file.is_file(), str(receipt_file))
        check('…holding the second export, so nothing was lost either way',
              receipt_file.is_file()
              and receipt_file.read_text(encoding='utf-8') == 'the second report')

    del sys.modules['docx']


def main() -> int:
    print('an export never replaces the deliverable already filed')
    import exporters  # noqa: PLC0415

    resolver_checks(exporters)
    full_door_checks(exporters)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
