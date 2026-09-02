#!/usr/bin/env python3
"""useFileStored's debounced disk write silently swallowed failure —
the single persistence chokepoint for nearly every durable entity in
the app (agents, tasks, projects, memory/context, receipts, missions,
workflows, meetings, messages, windows…), all backed by this one hook.

`persist()` (app/storage.jsx) writes to localStorage immediately (and
already reports failure there — `cafresohq:storage-error`, caught and
toasted by app.jsx) and then, debounced 1.5s, PUTs the same value to
disk via serve.py's `/hq/<scope>/<name>` route. That second write used
to be:

    fetch(`${window._API_BASE || ''}/hq/${fileScope}/${fileName}`, {
      method: 'PUT', ...
    }).catch(() => {});

No `res.ok` check, and the network-failure case was discarded outright.
Concrete failure scenario: the boss hires an agent, edits a task,
whatever — localStorage updates instantly so the UI looks fine. If the
PUT fails (server mid-restart, disk full, a permissions hiccup), the
on-disk file silently keeps its old contents with zero user-visible
warning. The NEXT time that file is read (a fresh session/browser, or
this same session's own mount-fetch merge logic a few lines above)
adopts the stale file over local state — the edit just reverts, with
no error ever having been shown to explain why.

Found by a background hunt agent looking for other instances of the
fire-and-forget-swallows-failure shape already fixed twice this session
(`decideExternal` in app.jsx, `publish()` in views/graph.jsx) — this is
the highest-blast-radius instance, since nearly every entity type in
the app goes through this one function.

Fix: the PUT now checks `res.ok` and dispatches the SAME
`cafresohq:storage-error` window event the localStorage failure a few
lines above already uses — but tagged `target: 'file'` so app.jsx's
existing listener (which throttles to one toast per 10s and already
handles the localStorage case) can say something honest and distinct:
"⚠ Office file save failed — this change may not survive a reload
elsewhere", instead of the localStorage-specific wording, which would
be actively wrong here (localStorage did NOT fail).

Run: python3 scripts/test_file_persist_reports_failure_instead_of_silent_drop.py
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
STORAGE_JSX = ROOT / 'app' / 'storage.jsx'
APP_JSX = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("useFileStored's disk-write failures are reported, not silently dropped")

    storage_src = STORAGE_JSX.read_text(encoding='utf-8')
    app_src = APP_JSX.read_text(encoding='utf-8')

    persist_m = re.search(
        r"const persist = React\.useCallback\(\(v\) => \{\n(.*?)\n  \}, \[lsKey, fileScope, fileName, sensitive, persistTransform\]\);",
        storage_src, re.S)
    check('found persist', persist_m is not None)
    persist_body = persist_m.group(1) if persist_m else ''

    write_m = re.search(r"writeRef\.current = setTimeout\(\(\) => \{\n(.*?)\n    \}, 1500\);", persist_body, re.S)
    check('found the debounced disk-write setTimeout body', write_m is not None)
    write_body = write_m.group(1) if write_m else ''

    check('the disk PUT no longer ends in a bare, argument-less '
          '.catch(() => {}) that discards the error — the actual '
          'regression (the fix comment quotes that old shape, so this '
          'checks for the actual catch handler, not the comment)',
          write_body and '.catch(err => {' in write_body)
    check('the disk PUT now checks res.ok and throws on a bad status',
          write_body and 'if (!r.ok) throw new Error' in write_body)
    check('a failed disk write dispatches cafresohq:storage-error tagged '
          "target: 'file' — reusing the SAME event the localStorage "
          'failure above already uses, so app.jsx\'s one existing '
          'listener/toast-throttle handles both',
          write_body and "target: 'file'" in write_body
          and 'cafresohq:storage-error' in write_body)

    check("app.jsx's storage-error handler branches on target === 'file' "
          "before falling through to the localStorage-specific wording "
          "(which would be actively wrong for a disk-write failure — "
          "localStorage did not fail)",
          "e.detail && e.detail.target === 'file'" in app_src
          and 'Office file save failed' in app_src)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted '
          'disk-write logic below)', has_node, 'skipping the live-execution check')

    if has_node and write_body:
        js = f"""
        async function run() {{
          async function tryWrite(fetchImpl) {{
            const events = [];
            const window = {{
              dispatchEvent: (e) => {{ events.push({{ type: e.type, detail: e.detail }}); }},
              _API_BASE: '',
            }};
            const CustomEvent = function (type, opts) {{ this.type = type; this.detail = opts && opts.detail; }};
            const console = {{ warn: () => {{}} }};
            const fetch = fetchImpl;
            const fileScope = 'state', fileName = 'tasks', lsKey = 'cafresohq_hq_v1:tasks';
            const out = {{ a: 1 }};

            await new Promise((resolve) => {{
              const body = async () => {{
                {write_body}
                resolve();
              }};
              body();
            }});
            // give the fetch chain's microtasks a tick to settle
            await new Promise(r => setTimeout(r, 10));
            return events;
          }}

          const results = {{}};
          results.http_error = await tryWrite(async () => ({{ ok: false, status: 500 }}));
          results.network_error = await tryWrite(async () => {{ throw new Error('fetch failed'); }});
          results.success = await tryWrite(async () => ({{ ok: true, status: 200 }}));
          console.log(JSON.stringify(results));
        }}
        run();
        """
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the extracted disk-write logic ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-800:])
        if r.returncode == 0:
            out = json.loads(r.stdout.strip().splitlines()[-1])
            check('a non-2xx disk-write response dispatches a storage-error '
                  'event tagged target=file — this is exactly the silent '
                  'failure this fix closes',
                  len(out['http_error']) == 1
                  and out['http_error'][0]['type'] == 'cafresohq:storage-error'
                  and out['http_error'][0]['detail'].get('target') == 'file',
                  out['http_error'])
            check('a network-level failure dispatches the same event',
                  len(out['network_error']) == 1
                  and out['network_error'][0]['detail'].get('target') == 'file',
                  out['network_error'])
            check('a successful write dispatches no error event at all',
                  len(out['success']) == 0, out['success'])

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
