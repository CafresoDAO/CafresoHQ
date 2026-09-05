#!/usr/bin/env python3
"""The Library graph's LOAD failed silently — the exact swallow that
`## 392`'s sibling fix had already removed from `publish` in the very
same file.

`GraphView`'s mount effect (views/graph.jsx) resolved the data source and
mounted sigma on it. On failure it did only:

    } catch (e) { console.warn('graph load:', e); setLoading(false); }

`setLoading(false)` takes the "Loading graph…" hint off the canvas and
nothing replaces it. The boss is left looking at an empty black box —
which is ALSO exactly what a brand-new office with an empty library looks
like, so there is no way to tell "the office is down" from "you have not
written anything yet". Every failure this catch swallows is one the boss
would act on if they were told: `CafresoHQClient.vaultGraph()` throwing
because the office restarted, a 500 out of `/vault/graph`, or
`'concept builder unavailable'` thrown by `loadData` itself when the
co-occurrence builder is missing.

And there is a second, quieter half — a failure path that reports
success. `mountData` returns `null` when `window.CafresoGraphEngine` is
absent (the engine is a separate <script>, emitted by
scripts/ui_manifest.py only `if manifest.get('graphEngine')`), and the
effect's response to that was a bare `if (!eng) return;` AFTER a
`setLoading(false)`. Nothing threw, so nothing was caught; the load
reported itself done and the map was never drawn.

The third: `window.CafresoHQGraph.refresh`, which views/vault.jsx:450
fires after a note write, ended in `catch (_) {}`. A refresh that failed
left the map showing a shape the library no longer has, silently.

The file already owned the right surface. Line ~561 carries the comment
"Publish failure — was silently swallowed to console.warn before." — an
earlier hunt fixed the PUBLISH swallow here and left the LOAD swallow,
twelve lines above it, in the identical `console.warn` shape.

Fix: a `loadError` state, set from `officeCause(...)` on the catch and to
a plain sentence on the missing-engine path, rendered by the same card
shape `shareError` uses, with "Try again" (bumping `reloadTick`, in the
effect's deps) and "Close". Cleared at the top of every load.

Run: python3 scripts/test_a_graph_that_failed_to_load_says_so.py
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


def brace_lift(src, opener):
    """Return the text between the braces of the block that `opener` opens.
    Brace-balanced extraction of the REAL committed source — never a
    re-implementation. Same rule every harness in this series uses."""
    i = src.find(opener)
    if i < 0:
        return None
    i = src.index('{', i + len(opener) - 1)
    d = 0
    j = i
    while j < len(src):
        if src[j] == '{':
            d += 1
        elif src[j] == '}':
            d -= 1
            if d == 0:
                return src[i + 1:j]
        j += 1
    return None


def main():
    print('A graph that failed to load says so, instead of showing an empty canvas')

    src = GRAPH_JSX.read_text(encoding='utf-8')

    # ── Round 1: structural ────────────────────────────────────────────
    check('a `loadError` state slot exists (the twin of shareError)',
          bool(re.search(r"const \[loadError, setLoadError\] = useSV\(null\);", src)))
    check('a `reloadTick` state slot exists, so the card can offer a retry '
          'that is not a full page reload',
          bool(re.search(r"const \[reloadTick, setReloadTick\] = useSV\(0\);", src)))

    # The effect's own prologue (the two setters + the clear) sits OUTSIDE the
    # async IIFE that does the work, so it is pinned against the raw source;
    # `body` below is the IIFE, which is what the harness actually drives.
    check('the load effect CLEARS loadError before starting, so a retry '
          'that works does not leave the old error card up',
          'let cancelled = false;\n    setLoading(true);\n    setLoadError(null);' in src)

    body = brace_lift(src, 'React.useEffect(() => {\n    let cancelled = false;\n    setLoading(true);')
    check('found the load/mount effect', body is not None)
    body = body or ''
    check('the catch sets loadError via officeCause instead of only '
          'console.warn — the regression itself',
          'setLoadError(officeCause(' in body and "console.warn('graph load:', e)" in body)
    check('the missing-engine path (mountData -> null) now reports too; it '
          'used to be a bare `if (!eng) return;` on a load that had already '
          'said it finished',
          bool(re.search(r"if \(!eng\) \{ setLoadError\(", body)))
    check("refresh()'s catch no longer swallows into `catch (_) {}`",
          'catch (_) {}' not in body.split('refresh:')[-1].split('};')[0]
          if 'refresh:' in body else False)
    check('the effect re-runs on reloadTick, or "Try again" is a dead button',
          '}, [source, scope, reloadTick]);' in src)
    check('a failure card renders when loadError is set, with both a retry '
          'and a way to dismiss it',
          bool(re.search(r"loadError && React\.createElement\('div'", src))
          and 'onClick: () => setReloadTick(n => n + 1)' in src
          and 'onClick: () => setLoadError(null)' in src)
    check('the publish card that was fixed first is still there — this fix '
          'is additive, not a re-route of the existing one',
          bool(re.search(r"shareError && React\.createElement\('div'", src))
          and 'setShareError(officeCause(' in src)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted load '
          'effect below)', has_node, 'skipping the live-execution checks')

    # ── Rounds 2-5: the REAL extracted effect body ─────────────────────
    if has_node and body:
        harness = """
        async function run() {
          const officeCause = (m) => 'OFFICE: ' + m;
          const results = [];

          // Drive the REAL lifted effect body once, with the collaborators it
          // closes over stubbed to produce one specific failure (or success).
          async function runLoad({ loadData, engineOk = true }) {
            let loading = true, loadError = null, mounted = 0, reloadTick = 0;
            const setLoading = (v) => { loading = v; };
            const setLoadError = (v) => { loadError = v; };
            const setReloadTick = (f) => { reloadTick = typeof f === 'function' ? f(reloadTick) : f; };
            const containerRef = { current: {} };
            const engineRef = { current: null };
            // The real mountData contract: null when the engine script is absent.
            const mountData = (g) => {
              if (!engineOk) return null;
              mounted++;
              engineRef.current = { focusNode: () => {} };
              return engineRef.current;
            };
            const window = {};
            const console = { warn: () => {} };

            const body = async () => {
              LIFTED_BODY
            };
            body();
            // let the async IIFE inside settle
            await new Promise(r => setTimeout(r, 5));
            return { loading, loadError, mounted, hqGraph: !!window.CafresoHQGraph, window };
          }

          // Case 1: the office is down — vaultGraph() rejects.
          results.push(['office_down', await runLoad({
            loadData: async () => { throw new Error('Failed to fetch'); },
          })]);

          // Case 2: the concept builder is missing — loadData's own throw.
          results.push(['no_builder', await runLoad({
            loadData: async () => { throw new Error('concept builder unavailable'); },
          })]);

          // Case 3: data arrived, but the engine <script> never loaded.
          //         Nothing throws. This is the report-success path.
          results.push(['no_engine', await runLoad({
            loadData: async () => ({ nodes: [], edges: [] }),
            engineOk: false,
          })]);

          // Case 4: the happy path is untouched.
          const ok = await runLoad({ loadData: async () => ({ nodes: [{ id: 'a' }], edges: [] }) });
          results.push(['success', { loading: ok.loading, loadError: ok.loadError, mounted: ok.mounted, hqGraph: ok.hqGraph }]);

          // Case 5: a refresh (fired by the vault after a note write) that
          //         fails must speak too, instead of `catch (_) {}`.
          let refreshErr = null;
          {
            let calls = 0;
            let loadError = null;
            const setLoading = () => {};
            const setLoadError = (v) => { loadError = v; };
            const setReloadTick = () => {};
            const containerRef = { current: {} };
            const engineRef = { current: null };
            const mountData = () => ({ focusNode: () => {} });
            const window = {};
            const console = { warn: () => {} };
            const loadData = async () => {
              calls++;
              if (calls === 1) return { nodes: [], edges: [] };
              throw new Error('Failed to fetch');
            };
            const body = async () => {
              LIFTED_BODY
            };
            body();
            await new Promise(r => setTimeout(r, 5));
            await window.CafresoHQGraph.refresh();
            refreshErr = loadError;
          }
          results.push(['refresh_failed', { loadError: refreshErr }]);

          console.log(JSON.stringify(results));
        }
        run();
        """
        # `let cancelled` and the two opening setters are consumed by the
        # brace_lift opener above, so put them back before the lifted tail.
        lifted = ('let cancelled = false;\n    setLoading(true);\n' + body)
        harness = harness.replace('LIFTED_BODY', lifted)
        r = subprocess.run(['node', '-e', harness], capture_output=True, text=True)
        check('the extracted load effect ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-900:])
        if r.returncode == 0:
            out = dict(json.loads(r.stdout.strip().splitlines()[-1]))
            check('an unreachable office sets loadError and stops claiming to '
                  'be loading — before this fix the boss got a blank canvas '
                  'and nothing else',
                  bool(out['office_down']['loadError'])
                  and out['office_down']['loading'] is False,
                  out['office_down'])
            check('a missing concept builder is reported rather than swallowed',
                  bool(out['no_builder']['loadError']),
                  out['no_builder'])
            check('a missing graph ENGINE is reported — the path where nothing '
                  'threw at all and the load reported success over a map that '
                  'was never drawn',
                  bool(out['no_engine']['loadError'])
                  and out['no_engine']['mounted'] == 0
                  and out['no_engine']['loading'] is False,
                  out['no_engine'])
            check('the happy path is unaffected: the engine mounts once, '
                  'loadError stays null, the window handle is published',
                  out['success']['mounted'] == 1
                  and out['success']['loadError'] is None
                  and out['success']['loading'] is False
                  and out['success']['hqGraph'] is True,
                  out['success'])
            check('a FAILED refresh (the vault fires one after every note '
                  'write) reports instead of `catch (_) {}`',
                  bool(out['refresh_failed']['loadError']),
                  out['refresh_failed'])

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
