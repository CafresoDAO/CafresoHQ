#!/usr/bin/env python3
"""An export whose path named only a folder was filed as a hidden file.

Every binary export door — EXPORT_PPTX / EXPORT_DOCX / EXPORT_PDF and the
image/video generators — resolves its target through exporters.py's
`_vault_binary_path`, which asks `_vault_hidden_part` first: a dotted
segment is refused out loud, because every listing the Library keeps (fs,
oci and the REST walk alike) drops a dotted part, so filing there is a
green "Saved" over a file that has just left every list (#136/#137/#140).

That question was asked of the caller's string, and then the resolver
changed the string. A path with no extension gets the door's own appended:

    if not ext:
        rel = rel + allowed_ext[0]

Hand it `Slides/` — which is exactly what a coworker's EXPORT_* tool sends
when it means "put it in Slides" — and the resolver builds `Slides/.pptx`:
a file whose entire name is the extension, hidden on every backend, never
listed again. The escape check passes (it IS inside the vault), the parent
folder is created, `prs.save()` writes real bytes, and the door answers
200 with `{"path": "Slides/.pptx"}`. `.` and `..` land the same way, as
`..pptx` and `...pptx`.

Fix: ask `_vault_hidden_part` again about the name actually being filed,
right after the extension is appended, and refuse with a sentence that
names the real problem (no file name, only a folder).

Run: python3 scripts/test_an_export_to_a_folder_is_not_filed_where_no_one_can_see_it.py
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


def real_hidden_part(rel):
    """serve.py's `_vault_hidden_part`, verbatim in behaviour — the resolver
    is handed the real one at import time, so the test must use the real
    rule rather than a lambda that says None to everything."""
    for part in str(rel or '').replace('\\', '/').split('/'):
        part = part.strip()
        if part in ('', '.', '..'):
            continue
        if part.startswith('.'):
            return part
    return None


def premise_checks() -> None:
    """serve.py must still hand the resolver the real hidden-part rule, and
    still filter dotted parts out of its vault listing. If either stops
    being true the bug below stops being a bug — and this test should say
    so instead of quietly passing."""
    print('the premise: hidden really means invisible, and the door really asks')
    src = (ROOT / 'serve.py').read_text(encoding='utf-8')
    check('serve.py injects the real _vault_hidden_part into exporters',
          'exporters._vault_hidden_part = lambda rel: _vault_hidden_part(rel)'
          in src)
    check('…and _vault_hidden_part still flags a leading dot',
          real_hidden_part('Slides/.pptx') == '.pptx')
    check('…while a listing still drops any dotted part',
          "if any(part.startswith('.') for part in p.relative_to(root).parts):"
          in src)


def resolver_checks(exporters) -> None:
    print('the shared resolver, straight from exporters.py')
    with tempfile.TemporaryDirectory() as td:
        exporters._vault_root = lambda: td
        exporters._vault_hidden_part = real_hidden_part
        root = pathlib.Path(td).resolve()

        # ── The bug: a folder-shaped path becomes a hidden file ────────
        for asked in ('Slides/', '.', '..', 'Reports/Q3/'):
            try:
                got = exporters._vault_binary_path(None, asked, ('.pptx',))
            except ValueError as e:
                check(f'{asked!r} is refused rather than filed out of sight',
                      True)
                check(f'…and the refusal for {asked!r} says what is wrong',
                      'no file name' in str(e), str(e))
                continue
            rel_out = str(got.relative_to(root)).replace('\\', '/')
            check(f'{asked!r} is refused rather than filed out of sight',
                  False, f'resolved to {rel_out!r}')
            check(f'…and the refusal for {asked!r} says what is wrong',
                  False, 'no refusal at all')

        # ── What must keep working ────────────────────────────────────
        ok = exporters._vault_binary_path(None, 'Slides/q3', ('.pptx',))
        check('a real name with no extension still gets one appended',
              str(ok.relative_to(root)).replace('\\', '/') == 'Slides/q3.pptx',
              str(ok))
        ok2 = exporters._vault_binary_path(None, 'Reports/deck.pptx', ('.pptx',))
        check('a real name with the right extension still resolves',
              str(ok2.relative_to(root)).replace('\\', '/')
              == 'Reports/deck.pptx', str(ok2))
        ok3 = exporters._vault_binary_path(None, 'notes.and.dots/plan',
                                           ('.docx',))
        check('dots that are not leading are still none of our business',
              str(ok3.relative_to(root)).replace('\\', '/')
              == 'notes.and.dots/plan.docx', str(ok3))

        # The older refusals still speak their own sentence, unchanged.
        try:
            exporters._vault_binary_path(None, '.secret/q3', ('.pptx',))
            check('an already-dotted path is still refused as hidden', False)
        except ValueError as e:
            check('an already-dotted path is still refused as hidden',
                  'hidden files are not accepted' in str(e), str(e))
        try:
            exporters._vault_binary_path(None, '../outside/deck', ('.pptx',))
            check('a traversal is still refused as an escape', False)
        except ValueError as e:
            check('a traversal is still refused as an escape',
                  'escapes vault' in str(e), str(e))
        try:
            exporters._vault_binary_path(None, 'deck.txt', ('.pptx',))
            check('a wrong extension is still refused as one', False)
        except ValueError as e:
            check('a wrong extension is still refused as one',
                  'extension must be one of' in str(e), str(e))

        # Nothing was created on the way to any of those refusals.
        check('no folder was made for a path that was refused',
              not (root / 'Reports' / 'Q3').exists()
              and not (root / 'outside').exists())


def full_door_checks(exporters) -> None:
    """The whole EXPORT_DOCX door, receipt included. Only the python-docx
    boundary is stubbed (it is not installed on every office)."""
    print('the EXPORT_DOCX door end to end')

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

    try:
        with tempfile.TemporaryDirectory() as td:
            exporters._vault_root = lambda: td
            exporters._vault_hidden_part = real_hidden_part
            root = pathlib.Path(td).resolve()

            h = Handler({'path': 'Docs/', 'content': '# the quarterly report'})
            exporters._export_docx(h)
            code, r = h.resp
            check('the door refuses a folder-only path instead of saying 200',
                  code == 400, h.resp)
            check('…and no invisible deliverable was written',
                  not (root / 'Docs' / '.docx').exists(),
                  sorted(str(p.relative_to(root))
                         for p in root.rglob('*')))

            h2 = Handler({'path': 'Docs/report',
                          'content': '# the quarterly report'})
            exporters._export_docx(h2)
            code2, r2 = h2.resp
            check('a named deliverable still files and still reports its path',
                  code2 == 200 and r2.get('path') == 'Docs/report.docx',
                  h2.resp)
            check('…and the file the receipt names is one a listing would show',
                  (root / 'Docs' / 'report.docx').is_file()
                  and real_hidden_part(r2.get('path')) is None)
    finally:
        del sys.modules['docx']


def main() -> int:
    print('an export to a folder is not filed where no one can see it')
    import exporters  # noqa: PLC0415

    premise_checks()
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
