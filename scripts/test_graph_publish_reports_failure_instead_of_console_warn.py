#!/usr/bin/env python3
"""The Library graph's "⤴ Share" (publish a public graph snapshot) button
silently swallowed failure.

`publish` (views/graph.jsx) POSTs the exported snapshot to
`/graph/publish` and, on success, opens a share modal with the link. On
failure it used to do only:

    } catch (err) { console.warn('publish graph:', err); }
    finally { setSharing(false); }

with no `res.ok` check at all — a 4xx/5xx response with a JSON body
still parsed fine via `res.json()`, so `if (j && j.viewerUrl)` was
simply false and the function fell through having done nothing. The
button flips from "Publishing…" back to "⤴ Share" with zero
indication anything went wrong: no toast, no banner, no chat message.
The boss can't tell "it silently failed" from "I forgot to click", and
will likely retry blindly or assume nothing happened when the server
actually rejected the request.

This is the same fire-and-forget-swallows-failure shape as the
already-fixed `decideExternal().catch(()=>{})` in app.jsx, but in a
different component untouched by that fix. It also breaks this
codebase's own established convention: views/projects.jsx's sibling
`publishOpen` (WorkspaceView's own "Publish" flow) has always reported
failure via `setPubMsg({ kind: 'err', text: 'Publish failed — ' +
officeCause(...) })` — `publish` here was the one publish flow that
didn't.

Found by a background hunt agent looking for other fire-and-forget
async calls that assume success, after `decideExternal` turned up the
same shape earlier this session.

Fix: `publish` now throws (and is caught) on `!res.ok`, and again when
the response is `ok` but carries no `viewerUrl` — both previously fell
through silently. The catch block now sets a new `shareError` state
(via `officeCause`, matching `publishOpen`'s own convention) instead of
only `console.warn`, and a small error banner renders when it's set,
with a Close button that clears it. Success path (shareUrl) is
unchanged.

Run: python3 scripts/test_graph_publish_reports_failure_instead_of_console_warn.py
(skips the live-execution checks if `node` isn't on PATH — the
source-shape checks still run everywhere)
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH_JSX = ROOT / 'views' / 'graph.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("The graph's Share/publish button reports failure instead of only console.warn")

    src = GRAPH_JSX.read_text(encoding='utf-8')

    check('officeCause is imported into graph.jsx (it was not before — '
          'this file had no error-reporting vocabulary of its own)',
          "import { officeCause } from '../app/floor.jsx';" in src)
    check('a `shareError` state slot exists',
          bool(re.search(r"const \[shareError, setShareError\] = useSV\(null\);", src)))

    fn_m = re.search(
        r"const publish = React\.useCallback\(async \(\) => \{\n(.*?)\n  \}, \[activePath\]\);",
        src, re.S)
    check('found publish', fn_m is not None)
    body = fn_m.group(1) if fn_m else ''

    check('publish now checks res.ok and throws on a bad HTTP status — '
          'the actual regression: this check did not exist at all before',
          'if (!res.ok)' in body)
    check('publish also throws when the response is ok but carries no '
          'viewerUrl (used to just silently fall through)',
          "throw new Error('the office did not hand back a link to share');" in body)
    check('the catch block sets shareError via officeCause instead of '
          'only console.warn — the boss now sees SOMETHING went wrong',
          'setShareError(officeCause(' in body and "console.warn('publish graph:', err)" in body)

    check('a failure banner renders when shareError is set, with a way '
          'to dismiss it',
          bool(re.search(r"shareError && React\.createElement\('div'", src))
          and "onClick: () => setShareError(null)" in src)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted '
          'publish logic below)', has_node, 'skipping the live-execution check')

    if has_node and fn_m:
        # Stand in for the refs/helpers publish() closes over.
        harness = f"""
        async function run() {{
          const officeCause = (m) => 'OFFICE: ' + m;
          const results = [];

          async function tryPublish(fetchImpl) {{
            let shareUrl = null, shareError = null, shareCopied = false, sharing = false;
            const setShareUrl = (v) => {{ shareUrl = v; }};
            const setShareError = (v) => {{ shareError = v; }};
            const setShareCopied = (v) => {{ shareCopied = v; }};
            const setSharing = (v) => {{ sharing = v; }};
            const engineRef = {{ current: {{ exportSnapshot: () => ({{ nodes: [], edges: [] }}) }} }};
            const sourceRef = {{ current: 'links' }};
            const scopeRef = {{ current: '__all__' }};
            const activePath = null;
            const titleFor = (p) => p;
            const fetch = fetchImpl;
            const navigator = {{ clipboard: {{ writeText: async () => {{}} }} }};
            const localStorage = {{ setItem: () => {{}} }};
            const window = {{ _API_BASE: '', dispatchEvent: () => {{}}, }};
            const CustomEvent = function (name) {{ this.name = name; }};
            const location = {{ origin: 'http://x' }};

            const publish = async () => {{
              {body}
            }};
            await publish();
            return {{ shareUrl, shareError, shareCopied }};
          }}

          // Case 1: non-2xx response with a JSON error body.
          results.push(['http_error', await tryPublish(async () => ({{
            ok: false, status: 500, json: async () => ({{ error: 'disk is full' }}),
          }}))]);

          // Case 2: network-level rejection.
          results.push(['network_error', await tryPublish(async () => {{ throw new Error('fetch failed'); }})]);

          // Case 3: ok response but no viewerUrl in the body.
          results.push(['no_viewer_url', await tryPublish(async () => ({{
            ok: true, status: 200, json: async () => ({{}}),
          }}))]);

          // Case 4: the happy path still works.
          results.push(['success', await tryPublish(async () => ({{
            ok: true, status: 200, json: async () => ({{ viewerUrl: '/g/abc123' }}),
          }}))]);

          console.log(JSON.stringify(results));
        }}
        run();
        """
        r = subprocess.run(['node', '-e', harness], capture_output=True, text=True)
        check('the extracted publish logic ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-800:])
        if r.returncode == 0:
            out = dict(json.loads(r.stdout.strip().splitlines()[-1]))
            check('a non-2xx response sets shareError (not just console.warn) '
                  'and never sets shareUrl',
                  out['http_error']['shareError'] and not out['http_error']['shareUrl'],
                  out['http_error'])
            check('a network-level failure sets shareError too',
                  out['network_error']['shareError'] and not out['network_error']['shareUrl'],
                  out['network_error'])
            check('a 200 response with no viewerUrl is now treated as a '
                  'failure and reported — before this fix it silently did '
                  'nothing at all',
                  out['no_viewer_url']['shareError'] and not out['no_viewer_url']['shareUrl'],
                  out['no_viewer_url'])
            check('the success path is unaffected: shareUrl is set and '
                  'shareError stays null',
                  out['success']['shareUrl'] == 'http://x/g/abc123'
                  and out['success']['shareError'] is None,
                  out['success'])

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
