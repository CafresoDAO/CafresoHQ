#!/usr/bin/env python3
"""A dated or versioned deck title used to be read as a wrong extension.

Every binary export door — EXPORT_PPTX / EXPORT_DOCX / EXPORT_PDF and the
image/video generators — resolves its target through exporters.py's
`_vault_binary_path`, and that resolver asked `pathlib.Path(rel).suffix`
what the file type was. `.suffix` is not "the file's type", it is
"everything after the last dot", and a deliverable TITLE carries dots that
were never an extension:

    "Slides/Q3 v1.2 plan"       .suffix -> '.2 plan'
    "Decks/Meeting 2026.08.30"  .suffix -> '.30'

Both came back non-empty, so the resolver skipped its append-the-extension
arm and took the OTHER branch — the one for a caller who asked for the
wrong format — and refused: "extension must be one of ('.pptx',), got
.2 plan". A coworker's EXPORT_* on a dated or versioned title, which is
most of them, could not file its deck at all. Nothing landed in the
Library; the boss was told a deck had been made and had no deck.

serve.py's `_vault_resolve` learned this exact lesson for the note-write
doors and names these two very titles in its own comment ("`Q3 v1.2 plan`
has suffix '.2 plan'; `Meeting 2026.08.30` has '.30'"). The export doors
ride a different resolver and had never been told — the same shape as the
#141 note at the top of exporters.py, where five doors on a second
resolver had missed a question the write doors already asked.

Fix: a suffix only counts as a file type when it is SHAPED like one —
1-8 alphanumerics with at least one letter, the same pattern serve.py
uses. A real extension still qualifies and a genuinely wrong one is still
refused; a version number, a date fragment or anything with a space falls
through to the append arm like the bare title it is.

Run: python3 scripts/test_a_dotted_deck_title_is_not_a_file_extension.py
"""
from __future__ import annotations

import pathlib
import re
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


def _rel(root: str, p: pathlib.Path) -> str:
    return str(p.relative_to(pathlib.Path(root).resolve())).replace('\\', '/')


def resolver_checks(exporters) -> None:
    """The shared resolver, straight from exporters.py."""
    print('the shared resolver, straight from exporters.py')
    exporters._vault_hidden_part = lambda rel: None

    def resolve(rel, allowed=('.pptx',)):
        # #386 made _vault_binary_path CLAIM its answer on disk (a 0-byte
        # placeholder via fs_routes.claim_name), not just look it up — so a
        # fresh temp dir per call keeps this a test of the extension/dotted-
        # title logic, not of #386's own (separately tested) collision
        # behavior. Without this, resolving 'q3.pptx' then 'q3.PPTX' in the
        # same dir now legitimately collide on a case-insensitive filesystem
        # (both claim the same inode) and the second answer correctly bumps
        # to a numbered variant — that's the fix working, not a regression.
        with tempfile.TemporaryDirectory() as td:
            exporters._vault_root = lambda: td
            try:
                return _rel(td, exporters._vault_binary_path(None, rel, allowed))
            except ValueError as e:
                return 'REFUSED: ' + str(e)

    got = resolve('Slides/Q3 v1.2 plan')
    check('a versioned title keeps its dots and gains a real extension',
          got == 'Slides/Q3 v1.2 plan.pptx', got)

    got = resolve('Decks/Meeting 2026.08.30')
    check('a dated title is filed, not refused as ".30"',
          got == 'Decks/Meeting 2026.08.30.pptx', got)

    got = resolve('Docs/Q3 report v2', ('.docx',))
    check('…and the same holds at the EXPORT_DOCX extension',
          got == 'Docs/Q3 report v2.docx', got)

    got = resolve('Research/Findings 1.5', ('.pdf',))
    check('…and at the EXPORT_PDF one',
          got == 'Research/Findings 1.5.pdf', got)

    got = resolve('Media/Frame 2026.08.30', ('.png', '.jpg'))
    check('…and the generators take the first allowed type',
          got == 'Media/Frame 2026.08.30.png', got)

    # Nothing about the ordinary cases may move.
    got = resolve('Docs/report')
    check('a plain bare title still gains the extension',
          got == 'Docs/report.pptx', got)
    got = resolve('Slides/q3.pptx')
    check('a name that already carries the right extension is untouched',
          got == 'Slides/q3.pptx', got)
    got = resolve('Slides/q3.PPTX')
    check('…in either case',
          got == 'Slides/q3.PPTX', got)
    got = resolve('Notes/deck.7z')
    check('a genuinely wrong extension is still refused out loud',
          got.startswith('REFUSED:') and '.7z' in got, got)
    got = resolve('Notes/deck.docx')
    check('…including a neighbouring export format',
          got.startswith('REFUSED:') and '.docx' in got, got)
    got = resolve('v1.2/notes/deck')
    check('a dotted FOLDER never counted and still does not',
          got == 'v1.2/notes/deck.pptx', got)


def full_door_checks(exporters) -> None:
    """The whole EXPORT_DOCX door, receipt included, against a temp vault.
    Only the python-docx boundary is stubbed (it is not installed on every
    office); everything from body-parse to receipt is the real code."""
    print('the EXPORT_DOCX door end to end')

    class _FakeDoc:
        def __init__(self):
            self.lines = []

        def add_heading(self, text, level=1):
            self.lines.append(text)

        def add_paragraph(self, text, style=None):
            self.lines.append(text)

        def save(self, path):
            pathlib.Path(path).write_text('\n'.join(self.lines), encoding='utf-8')

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
            exporters._vault_hidden_part = lambda rel: None

            h = Handler({'path': 'Docs/Board update 2026.08.30',
                         'content': '# Board update\n- we shipped'})
            exporters._export_docx(h)
            code, body = h.resp
            check('the door answers 200 for a dated title', code == 200, h.resp)
            check('…with a receipt naming the .docx it filed',
                  body.get('path') == 'Docs/Board update 2026.08.30.docx',
                  body.get('path'))
            filed = pathlib.Path(td) / (body.get('path') or 'nope')
            check('…and the deliverable really is on disk under that name',
                  filed.is_file(), str(filed))
            check('…holding the content the coworker wrote',
                  filed.is_file()
                  and 'we shipped' in filed.read_text(encoding='utf-8'))
    finally:
        del sys.modules['docx']


def source_checks() -> None:
    """The naive read must not come back. Comments are stripped first —
    the explanation of the fix necessarily quotes the pattern it replaced,
    and a grep that could not tell the two apart would fail the fix."""
    print('the source, with its comments stripped')
    src = (ROOT / 'exporters.py').read_text(encoding='utf-8')
    code = '\n'.join(re.sub(r'#.*$', '', ln) for ln in src.splitlines())
    check('no naive .suffix read decides the file type any more',
          not re.search(r'\.suffix\s*\.lower\(\)', code),
          'exporters.py still calls .suffix.lower() directly')
    check('the extension-shape rule serve.py uses is present here too',
          '[A-Za-z0-9]{1,8}' in code,
          'no extension-shape guard found in exporters.py')


def main() -> int:
    print('a dotted deck title is not a file extension')
    import exporters  # noqa: PLC0415

    resolver_checks(exporters)
    full_door_checks(exporters)
    source_checks()

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
