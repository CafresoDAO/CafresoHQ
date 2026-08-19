#!/usr/bin/env python3
"""The Library's file panel could not open a PDF — only images got a real
preview; a filed PDF got a 📕 glyph, its kind/size, and a download link.

Reported directly: "Allow for the Library Editor to allow PDF view."

views/vault.jsx's FiledFilePanel (the pane that opens for anything the text
editor can't open — decks, PDFs, images, archives) special-cased images
(`isImage`) to render an <img> instead of a glyph, but PDFs fell through to
the generic "can't open this format — download it" branch even though
serve.py's /vault/file was already answering PDFs with
`content-disposition: inline` (_vault_inline_ok already allowlists
application/pdf) — the backend was ready, the frontend never used it.

Fixed by giving PDFs their own branch, the same technique views/ide.jsx's
FilePreview already uses for the Projects/IDE surface: an <iframe> pointed
at the file URL, with a compact name/size/download footer below it instead
of the centered glyph card.

Run: python3 scripts/test_library_pdf_view.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')
SERVE = (ROOT / 'serve.py').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('Library file panel: PDF gets a real preview, not just a glyph')

    check("FiledFilePanel detects the PDF kind",
          "const isPdf = kind === 'PDF';" in VAULT)

    check('a dedicated early-return branch renders the PDF, rather than '
          'falling into the generic glyph/download card',
          re.search(r"if\s*\(isPdf\)\s*\{", VAULT) is not None)

    check('the PDF branch embeds the file in an iframe pointed at the '
          'same /vault/file URL the download link and image preview use',
          '<iframe title={name} src={url}' in VAULT)

    check('the PDF branch still offers a download link (the fallback for '
          "anyone whose browser can't render it inline)",
          VAULT.count('⬇ DOWNLOAD') >= 2)

    check("the PDF branch shows the file's name and size, matching what "
          "the generic binary-file card already shows for every other kind",
          re.search(r"if\s*\(isPdf\)[\s\S]{0,900}\{name\}[\s\S]{0,200}_fileSize\(size\)", VAULT)
          is not None)

    check('the generic glyph/download branch (presentations, documents, '
          'spreadsheets, archives, …) is still intact for kinds that are '
          "genuinely not previewable — this fix should not have replaced "
          'it wholesale',
          "Filed in the Library. The editor can't open this format — download it to work on it." in VAULT)

    check('images still render as <img>, unaffected by the new PDF branch',
          'isImage\n        ? <img src={url}' in VAULT
          or re.search(r"isImage\s*\?\s*<img src=\{url\}", VAULT) is not None)

    # --- backend: the inline disposition this frontend fix depends on -----
    check('serve.py already serves application/pdf with '
          'content-disposition: inline (this fix only needed the frontend '
          'to use it — a regression here would silently break the iframe '
          'into a download-only response again)',
          "mime == 'application/pdf'" in SERVE)

    check('/vault/file computes disp from _vault_inline_ok and sends it as '
          'the content-disposition header',
          "disp = 'inline' if _vault_inline_ok(mime) else 'attachment'" in SERVE)

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
