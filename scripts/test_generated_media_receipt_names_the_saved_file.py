#!/usr/bin/env python3
"""GENERATE_IMAGE/GENERATE_VIDEO receipts named a file that was never written.

#180 fixed exactly this bug for the three EXPORT_* tools: exporters.py's
`_vault_binary_path` appends the format's own extension when a coworker's
marker path has none, so `[GENERATE_IMAGE: Images/logo]` really saves to
`Images/logo.png` — and the tool-call loop's 'done' event reported
`call.arg`, the pre-correction marker text, unless the tool's `run()`
stashed the server's real path on `_ctx.meta.filedAs`.

The fix stopped at the export trio. But app/artifacts.jsx's CABINET_WRITE
regex counts GENERATE_IMAGE and GENERATE_VIDEO as cabinet writes too, so
`agentFiledPath` reads their visit `arg` to set `task.artifactPath` — the
field behind the out-tray's "open latest", the first-delivery sheet's
"Open it →", and the Receipts tray's title and on-chain content hash. On
every run where a coworker left the extension off a media marker (the
GENERATE_IMAGE doc itself only *suggests* "Images/concept.png"), all of
those pointed at `Images/logo`, a vault path nothing was ever written to,
while the image sat at `Images/logo.png`.

Fix: `generate_image`/`generate_video`'s `run()` now stash `r.path` on
`_ctx.meta.filedAs`, exactly like the export trio — the two 'done'
emissions already prefer `meta.filedAs || call.arg` since #180.

Run: python3 scripts/test_generated_media_receipt_names_the_saved_file.py
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
    print('exporters.py really does save media under a different name than asked')
    sys.path.insert(0, str(ROOT))
    import exporters  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as td:
        exporters._vault_root = lambda: td
        exporters._vault_hidden_part = lambda rel: None
        img = exporters._vault_binary_path(
            None, 'Images/logo', ('.png', '.jpg', '.jpeg', '.webp'))
        check('a bare-slug image marker path gets .png appended on disk',
              img.name == 'logo.png', img.name)
        vid = exporters._vault_binary_path(
            None, 'Videos/demo', ('.mp4', '.mov', '.webm'))
        check('a bare-slug video marker path gets .mp4 appended on disk',
              vid.name == 'demo.mp4', vid.name)


# ── Balanced-delimiter extraction — same technique as
#    test_export_visit_reports_the_saved_path.py / test_artifacts.py. ───────
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
    print('GENERATE_IMAGE/GENERATE_VIDEO report the path they actually saved to')

    if not HQ_RUNTIME.is_file() or not ARTIFACTS.is_file() or not EXPORTERS.is_file():
        print('  FAIL  missing hq-runtime.jsx, app/artifacts.jsx or exporters.py')
        return 1

    check_server_side_extension_append()

    # The visit-side premise, off the real source: CABINET_WRITE must count
    # the two media tools, or none of the downstream stakes exist.
    artifacts_full = ARTIFACTS.read_text(encoding='utf-8')
    m = re.search(r'const CABINET_WRITE = /(.+)/i;', artifacts_full)
    check('app/artifacts.jsx CABINET_WRITE counts GENERATE_IMAGE and GENERATE_VIDEO '
          'as cabinet writes',
          bool(m) and 'GENERATE_IMAGE' in m.group(1) and 'GENERATE_VIDEO' in m.group(1),
          m.group(1) if m else 'CABINET_WRITE not found')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH — cannot exercise the JS half live')
        print()
        if FAILS:
            print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
            return 1
        print('all checks passed (server-side half only)')
        return 0

    hq_src = HQ_RUNTIME.read_text(encoding='utf-8')

    def extract_or_fail(label, fn, *args):
        try:
            return fn(*args)
        except AssertionError as e:
            check(label, False, str(e))
            return None

    gen_img_block = extract_or_fail(
        "generate_image's tool object is present in hq-runtime.jsx's TOOLS table",
        _extract_tool, hq_src, 'generate_image')
    gen_vid_block = extract_or_fail(
        "generate_video's tool object is present in hq-runtime.jsx's TOOLS table",
        _extract_tool, hq_src, 'generate_video')
    if gen_img_block is None or gen_vid_block is None:
        print()
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1

    artifacts_src = '\n'.join(
        ln for ln in artifacts_full.split('\n')
        if not ln.startswith('import ') and not ln.startswith('export '))

    script = f'''
const CafresoHQClient = {{
  // Stands in for the real HTTP round-trip only. What it returns is exactly
  // what the Python half of this test just proved the real server does:
  // append the format's first allowed extension when none was given, echo
  // the path unchanged when one already matches.
  generateImage: async (path) => ({{
    path: /\\.(png|jpe?g|webp)$/i.test(path) ? path : path + '.png',
    provider: 'openai',
  }}),
  generateVideo: async (path) => ({{
    path: /\\.(mp4|mov|webm)$/i.test(path) ? path : path + '.mp4',
    provider: 'fal',
  }}),
}};

const generate_image = {gen_img_block};
const generate_video = {gen_vid_block};

{artifacts_src}

const R = {{}};

// ── generate_image's run(): does it stash the server's real path? ────────
const imgCtxNoExt = {{ meta: {{}} }};
R.imgResultNoExt = await generate_image.run('Images/logo', imgCtxNoExt, 'a logo');
R.imgFiledAsNoExt = imgCtxNoExt.meta.filedAs ?? null;

const imgCtxExt = {{ meta: {{}} }};
await generate_image.run('Images/logo.png', imgCtxExt, 'a logo');
R.imgFiledAsExt = imgCtxExt.meta.filedAs ?? null;

// ── generate_video's run(): same question ────────────────────────────────
const vidCtxNoExt = {{ meta: {{}} }};
R.vidResultNoExt = await generate_video.run('Videos/demo', vidCtxNoExt, 'a demo');
R.vidFiledAsNoExt = vidCtxNoExt.meta.filedAs ?? null;

// ── the end-to-end consequence: agentFiledPath (REAL, from app/artifacts.jsx)
// fed the visit shape the 'done' emission builds since #180:
// arg = meta.filedAs || call.arg.
R.filedPathWithFix = null;
R.filedPathWithFix = agentFiledPath([
  {{ name: 'GENERATE_IMAGE', arg: imgCtxNoExt.meta.filedAs || 'Images/logo', failed: false }},
]);

console.log(JSON.stringify(R));
'''

    out = run_js(script)

    check("generate_image run()'s result text names the REAL saved file when the "
          'extension was missing',
          'Images/logo.png' in out['imgResultNoExt'], out['imgResultNoExt'])
    check('…and ctx.meta.filedAs carries that corrected path back out',
          out['imgFiledAsNoExt'] == 'Images/logo.png', out['imgFiledAsNoExt'])
    check('…and still stashes it when the marker already had an extension',
          out['imgFiledAsExt'] == 'Images/logo.png', out['imgFiledAsExt'])
    check("generate_video run() stashes the corrected path on ctx.meta.filedAs too",
          out['vidFiledAsNoExt'] == 'Videos/demo.mp4', out['vidFiledAsNoExt'])
    check("…and its result text names that same file",
          'Videos/demo.mp4' in out['vidResultNoExt'], out['vidResultNoExt'])
    check('agentFiledPath (app/artifacts.jsx, real source) now resolves to the '
          'file exporters.py actually wrote',
          out['filedPathWithFix'] == 'Images/logo.png', out['filedPathWithFix'])

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
