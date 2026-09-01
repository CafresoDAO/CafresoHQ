#!/usr/bin/env python3
"""The reportlab PDF-export fallback silently corrupted note text
containing "&" or "<"/">".

`_export_pdf` (exporters.py) tries weasyprint first (fine — it converts
markdown to HTML via the `markdown` library, which escapes properly),
then falls back to reportlab when weasyprint/markdown aren't installed.
The reportlab path fed each line's raw, unescaped text straight into
`reportlab.platypus.Paragraph(text, style)` — but `Paragraph` parses its
input as reportlab's own small XML-like markup language (recognizing
`<b>`, `<i>`, `<font>`, `&entities;`, etc.). Unescaped user text isn't
rejected, it's silently mangled:

  - "Q&A session notes"          -> "Q&A; session notes" (stray `;`
                                     injected — "&A " looked like a
                                     malformed entity)
  - "Use the <TODO> tag here"    -> "Use the  tag here" (the entire
                                     "<TODO>" token silently swallowed
                                     as an unrecognized markup tag)

`doc.build(story)` raises no exception either way, so the handler still
returns 200 with `{'renderer': 'reportlab'}` — a user exporting any note
with an ampersand ("R&D", "Terms & Conditions") or an angle-bracketed
placeholder/comparison ("<TODO>", "x < 5") on a machine with only
reportlab installed (not weasyprint) gets a PDF that reports success
but has silently corrupted or missing text, discoverable only by
actually reading the exported file.

Found by a background hunt agent sweeping previously-unswept areas
(Night Shift, search, hire/onboarding, export/publish, other approval
kinds, chat delegate/handoff, calendar recurrence, vault graph, wallet
flows).

Fix: every `Paragraph(...)` call in the reportlab fallback now escapes
its text through `xml.sax.saxutils.escape()` first (after the heading/
bullet-marker prefix is stripped, before it reaches `Paragraph`).

reportlab isn't installed in this dev environment (this bug only
manifests on a machine where it's the only PDF backend available), so
this test checks the fix's shape directly in source, the same
convention every other test here uses when the runtime dependency
itself isn't present to exercise live.

Run: python3 scripts/test_pdf_export_escapes_reportlab_markup.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORTERS = ROOT / 'exporters.py'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('The reportlab PDF fallback escapes note text before handing it to Paragraph()')

    src = EXPORTERS.read_text(encoding='utf-8')

    m = re.search(r"def _export_pdf\(self\):(.*?)\n(?=def |\Z)", src, re.S)
    check('_export_pdf is still present', m is not None)
    body = m.group(1) if m else ''

    check('the reportlab fallback path is still present '
          '(the weasyprint path above it already escapes correctly '
          'via the markdown library, so this fix targets the fallback only)',
          "# Path B — reportlab" in body)

    check('xml.sax.saxutils.escape is imported alongside the other '
          'reportlab-only imports, so it is only pulled in when this '
          'fallback path actually runs',
          "from xml.sax.saxutils import escape as _xml_escape" in body)

    for label, pattern in [
        ('Title (# heading)', r"Paragraph\(_xml_escape\(s\[2:\]\.strip\(\)\), styles\['Title'\]\)"),
        ('Heading2 (## heading)', r"Paragraph\(_xml_escape\(s\[3:\]\.strip\(\)\), styles\['Heading2'\]\)"),
        ('Heading3 (### heading)', r"Paragraph\(_xml_escape\(s\[4:\]\.strip\(\)\), styles\['Heading3'\]\)"),
        ('bulleted line', r"Paragraph\('• ' \+ _xml_escape\(re\.sub\(r'\^\\s\*\[-\*•\]\\s\+', '', s\)\), styles\['BodyText'\]\)"),
        ('plain body-text line', r"Paragraph\(_xml_escape\(s\.strip\(\)\), styles\['BodyText'\]\)"),
    ]:
        check(f'the {label} branch escapes its text before Paragraph()',
              bool(re.search(pattern, body)))

    # Only count Paragraph(...) calls in actual code lines (skip the
    # explanatory comment above, which also contains the literal text
    # "Paragraph()" and would otherwise false-positive here).
    code_lines = [ln for ln in body.splitlines() if not ln.strip().startswith('#')]
    code_body = '\n'.join(code_lines)
    bad_calls = re.findall(r"Paragraph\((?!_xml_escape|'•\s*'\s*\+\s*_xml_escape)[^)]", code_body)
    check('no Paragraph(...) call in this function still passes raw, '
          'unescaped text (a bare Paragraph(s...) or Paragraph(\'• \' + '
          're.sub(...)) with no _xml_escape wrapper would be the '
          'regression coming back)',
          not bad_calls, bad_calls)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
