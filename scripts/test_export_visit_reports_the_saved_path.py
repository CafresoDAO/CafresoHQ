#!/usr/bin/env python3
"""EXPORT_PDF/DOCX/PPTX silently filed under one name and reported another.

exporters.py's `_vault_binary_path` (used by all three binary exporters)
deliberately appends the format's own extension when a coworker's marker
path has none — "[EXPORT_PDF: Docs/report]" really gets saved to
`Docs/report.pdf`, not `Docs/report`. That's the same convenience
`_vault_resolve` already gives plain vault notes (see
scripts/test_vault_resolve.py: "no extension -> .md appended"), proven
directly against the real function below, and it is fine on its own.

hq-runtime.jsx never learned about it. The marker's tool-call loop detects
`[EXPORT_PDF: Docs/report]` and captures `call.arg = 'Docs/report'` — the
coworker's own, pre-correction text — straight off the regex match. The
export tool's `run()` calls the server, gets back the REAL saved path
(`r.path = 'Docs/report.pdf'`), builds a correct result string with it...
and then the two 'done' event emissions in the tool-execution loop
(agentStream's own and ceoStream's own — same shape, two copies) reported
`arg: call.arg` — the stale, extension-less name — not `r.path`.

That `arg` is not cosmetic. app/artifacts.jsx's `agentFiledPath` reads it
straight off the visit list to answer "did the coworker file this
themselves", and its answer becomes `task.artifactPath` — the field the
out-tray's "open latest", the first-delivery sheet's "Open it →", and (per
app.jsx's `recordToolReceipt`) the Receipts tray's own title and its
on-chain content hash all key off. Every one of those pointed at a vault
path nothing was ever written to, silently, on exactly the runs where a
coworker left the extension off — a boss opening the Receipts tray or
clicking "Open it →" on a PDF a coworker just made would find nothing
there, or (worse, on a shared/refilled vault) a different, unrelated file
that happened to sit at that bare name.

Fix: the three export tools' `run()` functions now stash the server's real
saved path on `_ctx.meta.filedAs`; the two 'done' emissions report
`meta.filedAs || call.arg` instead of `call.arg` alone, so a tool that
never sets `filedAs` (i.e. everything except these three) is unaffected.

Run: python3 scripts/test_export_visit_reports_the_saved_path.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HQ_RUNTIME = ROOT / 'hq-runtime.jsx'
ARTIFACTS = ROOT / 'app' / 'artifacts.jsx'
EXPORTERS = ROOT / 'exporters.py'

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = '') -> None:
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond and detail else ''))
    if not cond:
        FAILS.append(name)


# ── Root cause, proven against the real exporters.py (not reimplemented) ──
def check_server_side_extension_append():
    print('exporters.py really does save under a different name than it was asked for')
    sys.path.insert(0, str(ROOT))
    import exporters  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as td:
        exporters._vault_root = lambda: td
        exporters._vault_hidden_part = lambda rel: None
        out = exporters._vault_binary_path(None, 'Docs/report', ('.pdf',))
        check('a bare-slug PDF marker path gets .pdf appended on disk',
              out.name == 'report.pdf', out.name)
        out2 = exporters._vault_binary_path(None, 'Docs/report.pdf', ('.pdf',))
        check('a path that already carries the right extension is untouched',
              out2.name == 'report.pdf', out2.name)


# ── Balanced-delimiter extraction — same technique test_artifacts.py uses to
#    run real source under node rather than a hand-copied stand-in. ─────────
def _extract_balanced(src: str, start: int, open_ch: str, close_ch: str) -> str:
    depth, j = 0, start
    while j < len(src):
        if src[j] == open_ch:
            depth += 1
        elif src[j] == close_ch:
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
        j += 1
    raise AssertionError(f'unterminated block starting at {start}')


def _extract_tool(src: str, key: str) -> str:
    """The full `key: { ... }` object literal for one TOOLS entry."""
    marker = f'\n  {key}: {{'
    i = src.find(marker)
    if i == -1:
        raise AssertionError(f'{key} block not found in hq-runtime.jsx')
    brace_start = i + len(marker) - 1
    return _extract_balanced(src, brace_start, '{', '}')


def _extract_on_tool_call(src: str, head: str) -> str:
    """The exact `onTool({ ... })` call expression whose object literal
    contains `head` — used to pull out each of the two 'done' emissions
    (ceoStream's and agentStream's tool-execution loops) verbatim."""
    head_idx = src.find(head)
    if head_idx == -1:
        raise AssertionError('onTool(...) emission not found for: ' + head[:60])
    call_idx = src.rfind('onTool(', 0, head_idx)
    if call_idx == -1:
        raise AssertionError('no enclosing onTool( for: ' + head[:60])
    paren_start = call_idx + len('onTool')
    call_expr = _extract_balanced(src, paren_start, '(', ')')
    return 'onTool' + call_expr


def run_js(script: str):
    if not shutil.which('node'):
        return None
    proc = subprocess.run(['node', '--input-type=module', '-e', script],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main() -> int:
    print('EXPORT_PDF/DOCX/PPTX report the path they actually saved to')

    if not HQ_RUNTIME.is_file() or not ARTIFACTS.is_file() or not EXPORTERS.is_file():
        print('  FAIL  missing hq-runtime.jsx, app/artifacts.jsx or exporters.py')
        return 1

    check_server_side_extension_append()

    if not shutil.which('node'):
        print('  SKIP  node not on PATH — cannot exercise the JS half live')
        print()
        if FAILS:
            print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
            return 1
        print('all checks passed (server-side half only)')
        return 0

    hq_src = HQ_RUNTIME.read_text(encoding='utf-8')

    # Each extraction is guarded rather than left to crash the suite: a
    # missing `meta.filedAs || call.arg` fallback (the fix itself, reverted)
    # means the anchor text below simply isn't there any more, and that IS
    # the regression this test exists to catch — so it has to surface as a
    # named, readable check() failure, not a bare traceback.
    def extract_or_fail(label, fn, *args):
        try:
            return fn(*args)
        except AssertionError as e:
            check(label, False, str(e))
            return None

    # The real export_pdf tool object, verbatim — only the network boundary
    # (CafresoHQClient.exportPdf) is stubbed, standing in for the real HTTP
    # round-trip proven above: given no extension, the server hands back a
    # DIFFERENT `path` than it was called with.
    # Bound to a name so the harness can call `.run(...)` on it — the object
    # literal itself is untouched, real source.
    export_pdf_block = extract_or_fail(
        "export_pdf's tool object is present in hq-runtime.jsx's TOOLS table",
        _extract_tool, hq_src, 'export_pdf')

    # The two 'done' emissions — one per tool-execution loop (ceoStream's,
    # agentStream's). Anchored on text unique to each: only agentStream's
    # carries `cwd` alongside `failed` (ceoStream "runs its tools with no
    # working directory at all, so its events carry none" — its own comment,
    # a few lines above the emission). Anchoring ON the fix itself
    # (`meta.filedAs || call.arg`) means a revert to bare `call.arg` makes
    # the anchor vanish — exactly the failure this test is for.
    site_no_cwd = extract_or_fail(
        "ceoStream's 'done' emission still prefers meta.filedAs over call.arg",
        _extract_on_tool_call, hq_src,
        "arg: (meta.filedAs || call.arg), result,\n               failed: !!meta.failed,\n               echo:")
    site_with_cwd = extract_or_fail(
        "agentStream's 'done' emission (the cwd-carrying sibling) still prefers "
        "meta.filedAs over call.arg",
        _extract_on_tool_call, hq_src,
        "arg: (meta.filedAs || call.arg), result,\n               failed: !!meta.failed, cwd,\n               echo:")

    if export_pdf_block is None or site_no_cwd is None or site_with_cwd is None:
        print()
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    export_pdf_tool = 'const export_pdf = ' + export_pdf_block + ';'

    artifacts_src = '\n'.join(
        ln for ln in ARTIFACTS.read_text(encoding='utf-8').split('\n')
        if not ln.startswith('import ') and not ln.startswith('export '))

    script = f'''
const CafresoHQClient = {{
  // Stands in for the real HTTP round-trip only. What it returns is exactly
  // what the Python half of this test just proved the real server does:
  // append the extension when none was given, echo the path unchanged when
  // one already matches.
  exportPdf: async (path) => ({{
    path: /\\.pdf$/i.test(path) ? path : path + '.pdf',
    renderer: 'reportlab',
  }}),
}};

{export_pdf_tool}

{artifacts_src}

const R = {{}};

// ── export_pdf's run(): does it stash the server's real path? ───────────
const ctxWithExt = {{ meta: {{}} }};
R.resultTextHasExt = (await export_pdf.run('Docs/already.pdf', ctxWithExt, '# hi')).includes('Docs/already.pdf');
R.filedAsWhenExtGiven = ctxWithExt.meta.filedAs;

const ctxNoExt = {{ meta: {{}} }};
R.resultTextNoExt = await export_pdf.run('Docs/report', ctxNoExt, '# hi');
R.filedAsWhenExtMissing = ctxNoExt.meta.filedAs;

// ── the two 'done' emissions: do they prefer meta.filedAs over call.arg? ──
function toolEchoHead(name, arg) {{ return `${{name}}("${{arg}}")`; }}

{{
  const call = {{ tool: {{ name: 'EXPORT_PDF' }}, arg: 'Docs/report' }};
  const meta = {{ filedAs: 'Docs/report.pdf', failed: false }};
  const result = 'Saved PDF (reportlab) -> Docs/report.pdf';
  let emitted = null;
  function onTool(ev) {{ emitted = ev; }}
  {site_no_cwd};
  R.site1Fixed = emitted.arg;
}}
{{
  // A tool that never sets meta.filedAs (i.e. every non-export tool) must
  // see NO change: arg still falls back to call.arg.
  const call = {{ tool: {{ name: 'VAULT_NEW' }}, arg: 'Research/notes.md' }};
  const meta = {{ failed: false }};
  const result = 'Wrote 40 chars -> Research/notes.md';
  let emitted = null;
  function onTool(ev) {{ emitted = ev; }}
  {site_no_cwd};
  R.site1Unaffected = emitted.arg;
}}
{{
  const call = {{ tool: {{ name: 'EXPORT_PDF' }}, arg: 'Docs/report' }};
  const meta = {{ filedAs: 'Docs/report.pdf', failed: false }};
  const cwd = '/home/boss/project';
  const result = 'Saved PDF (reportlab) -> Docs/report.pdf';
  let emitted = null;
  function onTool(ev) {{ emitted = ev; }}
  {site_with_cwd};
  R.site2Fixed = emitted.arg;
}}
{{
  const call = {{ tool: {{ name: 'VAULT_APPEND' }}, arg: 'Research/notes.md' }};
  const meta = {{ failed: false }};
  const cwd = '/home/boss/project';
  const result = 'Appended 12 chars -> Research/notes.md';
  let emitted = null;
  function onTool(ev) {{ emitted = ev; }}
  {site_with_cwd};
  R.site2Unaffected = emitted.arg;
}}

// ── the end-to-end consequence: agentFiledPath (REAL, from app/artifacts.jsx) ──
// toolVisits.push({{ name: ev.name, arg: ev.arg, echo: ev.echo, failed: !!ev.failed }})
// is exactly the shape app.jsx builds from these 'done' events.
R.agentFiledPath_fixed = agentFiledPath([
  {{ name: 'EXPORT_PDF', arg: 'Docs/report.pdf', failed: false }},
]);
// What app.jsx used to hand agentFiledPath before this fix — the bare,
// pre-correction call.arg, on every run where the model skipped the
// extension. Shown here as the concrete consequence, not exercised as a
// live regression (that would require reverting the whole file).
R.agentFiledPath_preFixShape = agentFiledPath([
  {{ name: 'EXPORT_PDF', arg: 'Docs/report', failed: false }},
]);

console.log(JSON.stringify(R));
'''

    out = run_js(script)

    check('run() reports the server path unchanged when the marker already had .pdf',
          out['resultTextHasExt'])
    check('…and still stashes it on ctx.meta.filedAs',
          out['filedAsWhenExtGiven'] == 'Docs/already.pdf', out['filedAsWhenExtGiven'])
    check('run()\'s result text names the REAL saved file when the extension was missing',
          'Docs/report.pdf' in out['resultTextNoExt'], out['resultTextNoExt'])
    check('…and ctx.meta.filedAs carries that same corrected path back out',
          out['filedAsWhenExtMissing'] == 'Docs/report.pdf', out['filedAsWhenExtMissing'])

    check("ceoStream's 'done' emission reports the corrected path, not the stale marker text",
          out['site1Fixed'] == 'Docs/report.pdf', out['site1Fixed'])
    check('…and leaves a tool that never sets meta.filedAs alone (no regression)',
          out['site1Unaffected'] == 'Research/notes.md', out['site1Unaffected'])
    check("agentStream's 'done' emission (the cwd-carrying sibling) does the same",
          out['site2Fixed'] == 'Docs/report.pdf', out['site2Fixed'])
    check('…and is likewise a no-op for a tool that never sets meta.filedAs',
          out['site2Unaffected'] == 'Research/notes.md', out['site2Unaffected'])

    check('agentFiledPath (app/artifacts.jsx, real source) now resolves to the file '
          'that was actually written',
          out['agentFiledPath_fixed'] == 'Docs/report.pdf', out['agentFiledPath_fixed'])
    check('…which is exactly the name exporters.py saved under (tied back to the '
          'server-side proof above) — before this fix it would have been '
          f"{out['agentFiledPath_preFixShape']!r}, a path nothing was ever written to",
          out['agentFiledPath_fixed'] != out['agentFiledPath_preFixShape'])

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
