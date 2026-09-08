#!/usr/bin/env python3
"""Build smoke check: the manifest is complete, its files exist, and both
HTML injectors agree.

`hq.html` carries a `<!--HQ_SCRIPTS-->` placeholder that is substituted from
dist-ui/manifest.json by TWO independent code paths — scripts/ui_manifest.py
(used by scripts/build_hq_ui.py for the asset canister) and an inlined copy in
serve.py (used for local/Electron, inlined so a frozen build needs no scripts/
directory beside the exe). A manifest change that updates only one of them
breaks the other silently, and only at page load.

This asserts, after `npm run build`:
  * every expected manifest key is present and non-empty
  * every referenced file actually exists in dist-ui/
  * the placeholder is still in hq.html
  * both injectors emit every hashed asset

Run: python3 scripts/check_bundle.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist-ui'

REQUIRED_LISTS = ('vendor', 'vendorCss', 'app')
REQUIRED_STRS = ('graphEngine', 'analyticsWorker')

fails: list[str] = []


def check(label: str, ok: bool, detail: str = '') -> None:
    print(f'  {"ok  " if ok else "FAIL"}  {label}' + (f' — {detail}' if detail and not ok else ''))
    if not ok:
        fails.append(label)


def main() -> int:
    mpath = DIST / 'manifest.json'
    if not mpath.is_file():
        print(f'FAIL: {mpath} missing — run `npm run build` first')
        return 1
    manifest = json.loads(mpath.read_text(encoding='utf-8'))

    print('=== manifest shape ===')
    for key in REQUIRED_LISTS:
        val = manifest.get(key)
        check(f'{key} is a non-empty list', isinstance(val, list) and bool(val), repr(val))
    for key in REQUIRED_STRS:
        val = manifest.get(key)
        check(f'{key} is a non-empty string', isinstance(val, str) and bool(val), repr(val))

    print('=== referenced files exist ===')
    refs: list[str] = []
    for key in REQUIRED_LISTS:
        refs.extend(v for v in (manifest.get(key) or []) if isinstance(v, str))
    refs.extend(v for k in REQUIRED_STRS
                if isinstance(v := manifest.get(k), str) and v)
    for ref in refs:
        check(f'{ref} exists', (DIST / ref).is_file())

    print('=== both injectors substitute the placeholder ===')
    sys.path.insert(0, str(ROOT / 'scripts'))
    import ui_manifest  # noqa: E402

    html = (ROOT / 'hq.html').read_text(encoding='utf-8')
    check('hq.html still has the placeholder', ui_manifest.PLACEHOLDER in html)

    canister_html = ui_manifest.inject(html, manifest)
    check('canister injector consumed the placeholder',
          ui_manifest.PLACEHOLDER not in canister_html)
    missing = [r for r in refs if r not in canister_html]
    check('canister injector emits every hashed asset', not missing, f'missing {missing}')

    # serve.py's inlined copy. Import with the crons disabled so no background
    # threads start, and from ROOT because the tagger resolves dist-ui/ against
    # the working directory.
    import os                                                # noqa: E402
    os.environ.setdefault('GAP_CRON', '0')
    os.environ.setdefault('NEWS_CRON', '0')
    os.environ.setdefault('TOPICS_CRON', '0')
    os.environ.pop('SEARCH_WORKER', None)
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    try:
        import serve  # noqa: E402
    except Exception as e:                                   # pragma: no cover
        check('serve.py imports', False, str(e)[:200])
        return 1 if fails else 0

    tagger = getattr(serve.Handler, '_hq_manifest_tags', None)
    if tagger is None:
        check('serve.py exposes _hq_manifest_tags', False,
              'renamed? update this check and scripts/ui_manifest.py together')
    else:
        # Unbound, and it reads the manifest from cwd itself — self is unused.
        local_tags = tagger(None)
        missing_local = [r for r in refs if r not in local_tags]
        check('serve.py injector emits every hashed asset',
              not missing_local, f'missing {missing_local}')

        # serve.py's tagger adds exactly ONE line the canister injector never
        # emits: `window._TERMINAL_CWD`, the standalone Terminal tab's cwd —
        # meaningless for a pure asset canister with no pty behind it, so
        # scripts/ui_manifest.py correctly has no equivalent. That is a
        # deliberate one-line difference (see serve.py's _cafresohq_terminal_cwd
        # comment), not drift — a byte-for-byte compare here would fail on
        # every run, on every machine, forever. Strip that one line, by
        # pattern (not position — a manifest change could move where it
        # lands) before asserting the rest still agree exactly.
        local_lines = local_tags.splitlines(keepends=True)
        cwd_lines = [ln for ln in local_lines if 'window._TERMINAL_CWD=' in ln]
        check('serve.py emits exactly one terminal-cwd line',
              len(cwd_lines) == 1, cwd_lines)
        local_tags_comparable = ''.join(
            ln for ln in local_lines if 'window._TERMINAL_CWD=' not in ln)
        check('both injectors agree, apart from the local-only terminal cwd',
              local_tags_comparable == ui_manifest.render_tags(manifest),
              'the inlined copy in serve.py has drifted from scripts/ui_manifest.py')

    print()
    if fails:
        print(f'{len(fails)} check(s) FAILED')
        return 1
    print('bundle check: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
