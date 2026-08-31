#!/usr/bin/env python3
"""Dropping a file on the Library handed it to the browser.

The Library is where artifacts get filed, and dragging one onto it is
the filing gesture everyone tries first. Nothing handled the drop, so
the browser default fired: the whole app navigated away to the dropped
file — unsaved keystrokes and all. Reproduced by design (no
onDrop/onDragOver existed anywhere in the vault).

Now both Library roots preventDefault whenever files are dragged over
them — in EVERY backend, because the navigation is the trap even where
upload isn't — arm a "Drop to file" overlay, and file the drop through
the same uploadFiles/receipt path the 📤 button uses. The bridge vault
has no upload door, so there the drop is refused out loud. A
text-selection drag (no Files in types) is ignored entirely. Verified
live: dragover arms the overlay and prevents default, the drop lands
the file on disk with a "Filed 1 file" receipt, the overlay disarms.

Run: python3 scripts/test_a_dropped_file_is_filed_not_followed.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('a dropped file is filed, not followed')
    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')

    # ── the handlers, run as written ────────────────────────────────────
    i = vault.index('const _dragHasFiles')
    j = vault.index('const dropZoneProps')
    handlers = vault[i:j]
    js = ('let armed = false, uploaded = null, said = null;\n'
          'let _bridge = false;\n'
          'let dropArmed = false;\n'
          'const setDropArmed = (v) => { armed = v; };\n'
          'const uploadFiles = async (l) => { uploaded = l; };\n'
          'const say = (m, t) => { said = [m, t]; };\n'
          + handlers + '\n'
          'const ev = (types, files) => { let prevented = false; return {\n'
          '  dataTransfer: {types, files: files || [], dropEffect: ""},\n'
          '  preventDefault: () => { prevented = true; },\n'
          '  get prevented() { return prevented; }};};\n'
          '(async () => {\n'
          '  const textDrag = ev(["text/plain"]);\n'
          '  onDragOver(textDrag);\n'
          '  const fileDrag = ev(["Files"]);\n'
          '  onDragOver(fileDrag);\n'
          '  const armedAfterOver = armed;\n'
          '  const fileDrop = ev(["Files"], ["F1"]);\n'
          '  await onDrop(fileDrop);\n'
          '  const fsResult = {uploaded, armedAfterDrop: armed};\n'
          '  _bridge = true; uploaded = null;\n'
          '  const bridgeDrop = ev(["Files"], ["F2"]);\n'
          '  await onDrop(bridgeDrop);\n'
          '  console.log(JSON.stringify({\n'
          '    textPrevented: textDrag.prevented,\n'
          '    filePrevented: fileDrag.prevented,\n'
          '    armedAfterOver, fsResult,\n'
          '    dropPrevented: fileDrop.prevented,\n'
          '    bridgePrevented: bridgeDrop.prevented,\n'
          '    bridgeUploaded: uploaded, bridgeSaid: said && said[1]}));\n'
          '})();')
    p = subprocess.run(['node', '-e', js], capture_output=True, text=True,
                       timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('a text-selection drag is ignored entirely',
          r['textPrevented'] is False)
    check('a file drag is claimed from the browser and arms the overlay',
          r['filePrevented'] is True and r['armedAfterOver'] is True)
    check('the drop is prevented — the app never navigates away',
          r['dropPrevented'] is True)
    check('...and files through the shared upload path',
          r['fsResult']['uploaded'] == ['F1'], r['fsResult'])
    check('...then the overlay disarms',
          r['fsResult']['armedAfterDrop'] is False)
    check('the bridge vault still swallows the navigation',
          r['bridgePrevented'] is True)
    check('...but refuses the filing out loud instead of silently',
          r['bridgeUploaded'] is None and r['bridgeSaid'] == 'info')

    # ── wiring: both roots are drop zones with the hint inside ──────────
    check('both Library roots spread the drop-zone props',
          '"vault-mobile" {...dropZoneProps}' in vault
          and '"vault-layout-3col" {...dropZoneProps}' in vault)
    check('...and both hold the overlay hint',
          vault.count('{dropHint}') == 2)
    check('the 📤 button and the drop share one receipt path',
          'await uploadFiles(list);' in vault
          and vault.count('CafresoHQClient.vaultUpload(') == 1)

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
