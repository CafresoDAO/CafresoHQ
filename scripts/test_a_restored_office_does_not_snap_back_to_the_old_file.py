#!/usr/bin/env python3
"""Restoring an office backup silently undid itself, within the same reload
that was supposed to bring it back.

Most of what OFFICE BACKUP claims to restore — team roster, tasks, projects,
missions, meetings, workflows, the agent message registry, memory/context,
receipts, pins, the experience log, the activity log, open windows — is NOT
purely a localStorage value. Each of those goes through app/storage.jsx's
useFileStored, which also mirrors to a server-side hq-state/hq-memory file
and, on every mount, fetches that file and adopts it whenever this session
hasn't dirtied the value yet (see useFileStored's mount effect). A tab that
just reloaded because of an import has dirtied nothing: dirtyRef starts
false. So the mount-fetch pulls whatever the OLD file still holds — the
office as it stood BEFORE the restore — straight back over the value
importOffice just wrote, and does it again in a second `localStorage.setItem`
for good measure. The boss sees "Restore ... reloads the app", the reload
happens, and the task list / roster / mission board are exactly what they
were a moment ago. Nothing in the UI ever says so.

The export was never the problem — everything under the cafresohq
prefixes really does get written into the backup file. The bug is that
importOffice only ever wrote the localStorage half of a file-backed key,
so there was always a stale file left for the very next hydration to
reassert. It reproduces with no cross-machine step at all: add a task,
export, delete the task, import the very same file, reload — the deleted
task is back, because the file on THIS server was never touched.

Fixed by giving importOffice the same lsKey -> (scope, name) map
app/storage.jsx's useFileStored call sites already define, and PUTting each
file-backed entry to its mirrored /hq/<scope>/<name> before reloading —
awaited, so the reload can't race ahead of the write. File and localStorage
agree by the time the mount-fetch runs, so there is nothing stale left for
it to adopt.

Verified two ways below: a structural diff catching drift between the new
map in modals/settings.jsx and the real useFileStored call sites in
app.jsx (so a future new file-backed key can't silently fall through the
same hole), and a behavioral run of the real, lifted importOffice against
a mocked fetch/localStorage/window, checked for the exact PUT targets and
for the reload actually waiting on them.

Run: python3 scripts/test_a_restored_office_does_not_snap_back_to_the_old_file.py
"""
import json
import re
import shutil
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


def strip_comments(src):
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
    i = src.index(opener)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise SystemExit('unbalanced braces lifting ' + opener)


HARNESS = r'''
const order = [];
const fetchCalls = [];
const localStorage = { store: {}, setItem(k, v) { this.store[k] = v; } };
const window = {
  hqConfirm: async () => true,
  location: { reload: () => { order.push('reload'); } },
};
const fetch = (url, opts) => {
  order.push('fetch:start:' + url);
  fetchCalls.push({ url, opts });
  return new Promise((resolve) => setTimeout(() => {
    order.push('fetch:settled:' + url);
    resolve({ ok: true });
  }, 5));
};
const apiBase = 'http://TESTAPI';
let noteCalls = [];
const setNote = (n) => { noteCalls.push(n); };

%s

(async () => {
  const entries = {
    'cafresohq_hq_v1:theme': '"dark"',
    'cafresohq_hq_v1:tasks': '[{"id":1,"title":"Ship it"}]',
    'cafresohq_hq_v1:projects': '[{"id":"p1"}]',
    // The realistic current shape: memory's key is ks()-scoped, so a real
    // export from a live, slugged office carries the office's slug as a
    // suffix, not the bare name the map's keys are written under.
    'cafresohq_hq_v1:memory:1a2b3c4d5e6f7890': '{"notes":"hi"}',
    'cafresohq_hq_v1:totallyUnknownFutureKey': '{"x":1}',
    'cafresohq_client_v1': JSON.stringify({ model: 'x', openrouterKey: 'sk-LEAK' }),
    'cafresohq_agent_keys_v1': '{"smuggled":"blob"}',
  };
  const file = {
    text: async () => JSON.stringify({
      format: 'cafresohq-office-backup', version: 1,
      exportedAt: '2026-01-01T00:00:00.000Z', entries,
    }),
  };
  const e = { target: { files: [file], value: 'x' } };
  await importOffice(e);
  console.log(JSON.stringify({ order, fetchCalls, store: localStorage.store, noteCalls }));
})();
'''


def main():
    print('a restored office does not snap back to the old file')
    settings = (ROOT / 'modals' / 'settings.jsx').read_text(encoding='utf-8')
    settings_nc = strip_comments(settings)
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')

    # ── the map exists and is consulted before the reload ───────────────
    check('OFFICE_FILE_BACKED exists',
          'const OFFICE_FILE_BACKED = {' in settings_nc)
    check('importOffice looks up OFFICE_FILE_BACKED before reloading',
          re.search(r'importOffice[\s\S]*?OFFICE_FILE_BACKED\[[\s\S]*?window\.location\.reload\(\);', settings_nc))
    check('the file-backed PUT is awaited, not fired-and-forgotten',
          re.search(r'await Promise\.allSettled\(filePuts\);\s*\n\s*window\.location\.reload\(\);', settings_nc))
    check('the PUT targets the mirrored hq endpoint',
          "fetch(`${apiBase}/hq/${target.scope}/${target.name}`" in settings_nc
          and "method: 'PUT'" in settings_nc)

    # ── no drift against the real useFileStored call sites ──────────────
    # This is the actual failure mode a future edit could reintroduce: add
    # a fourteenth useFileStored(k('whatever'), scope, name, ...) call in
    # app.jsx and forget the mirror here. Diff against app.jsx itself,
    # not a hand-copied assumption, so that drift is what fails.
    #
    # `ks?` — memory's call site is useFileStored(ks('memory'), ...), not
    # k('memory'): a shared hq.cafreso.com origin serves every office split
    # only by URL path, and localStorage is scoped by origin, so the Memory
    # Shelf's cache used to leak between two offices opened in one browser.
    # ks() suffixes the key with the office's own slug to stop that. A
    # regex that only matched literal k(...) would silently stop counting
    # memory as a real call site the moment that fix landed — which is
    # exactly what happened here until this line grew the `?`.
    call_re = re.compile(
        r"useFileStored\(\s*ks?\('(\w+)'\)\s*,\s*'(\w+)'\s*,\s*'(\w+)'")
    real = {m.group(1): {'scope': m.group(2), 'name': m.group(3)}
            for m in call_re.finditer(app)}
    check('found the real useFileStored call sites in app.jsx to diff against',
          len(real) >= 13, sorted(real))
    check("memory's call site is counted even though it's ks(...), not k(...)",
          'memory' in real and real.get('memory') == {'scope': 'memory', 'name': 'context'},
          real.get('memory'))

    if not shutil.which('node'):
        print('  SKIP  node not on PATH — map + behavior checks need it')
    else:
        map_js = brace_lift(settings_nc, 'const OFFICE_FILE_BACKED = {')
        p = subprocess.run(
            ['node', '-e', map_js + '\nconsole.log(JSON.stringify(OFFICE_FILE_BACKED));'],
            capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            check('OFFICE_FILE_BACKED evaluates', False, p.stderr.strip()[:300])
        else:
            mapped = json.loads(p.stdout.strip().split('\n')[-1])
            check('every real useFileStored key is mirrored, scope and name exact',
                  mapped == real, {'app.jsx': real, 'settings.jsx': mapped})

        # ── behavior: the real, lifted importOffice, driven end to end ──
        pieces = []
        for opener in (
            "const OFFICE_HQ_PREFIX = 'cafresohq_hq_v1:';",
            "const OFFICE_EXPORT_PREFIXES = [",
            "const OFFICE_EXPORT_BLOCKED = [",
            "const OFFICE_FILE_BACKED = {",
            "const _scrubClientBlob = (raw) => {",
            "const importOffice = async (e) => {",
        ):
            if opener.rstrip().endswith('{') and not opener.rstrip().endswith('};'):
                pieces.append(brace_lift(settings_nc, opener))
            else:
                i = settings_nc.index(opener)
                j = settings_nc.index(';', i) + 1
                pieces.append(settings_nc[i:j])
        js = '\n'.join(pieces)
        p = subprocess.run(['node', '-e', HARNESS % js],
                            capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            print(p.stderr[-1200:], file=sys.stderr)
            check('the lifted importOffice runs against a mocked backend', False,
                  p.stderr.strip()[:300])
        else:
            out = json.loads(p.stdout.strip().split('\n')[-1])
            urls = sorted(c['url'] for c in out['fetchCalls'])

            check('the restored tasks are pushed to their mirrored file',
                  'http://TESTAPI/hq/state/tasks' in urls, urls)
            check('...with the exact restored body, not re-derived',
                  next((c['opts']['body'] for c in out['fetchCalls']
                        if c['url'] == 'http://TESTAPI/hq/state/tasks'), None)
                  == '[{"id":1,"title":"Ship it"}]')
            check('the restored projects are pushed to their mirrored file',
                  'http://TESTAPI/hq/state/projects' in urls, urls)
            check("a ks()-scoped memory key (memory:<slug>) still resolves to hq/memory/context",
                  'http://TESTAPI/hq/memory/context' in urls, urls)
            check('exactly the three file-backed entries were pushed — no more, no fewer',
                  len(urls) == 3, urls)
            check('a purely-local pref (theme) triggers no server write',
                  not any('theme' in u for u in urls), urls)
            check('a key with no file-backed mapping triggers no server write',
                  not any('totallyUnknownFutureKey' in u for u in urls), urls)
            check('the scrubbed client blob triggers no server write',
                  not any('client' in u for u in urls), urls)
            check('the blocked secret store was never even considered',
                  'cafresohq_agent_keys_v1' not in out['store'])

            # ── the actual bug: does reload wait for the writes? ────────
            settle_positions = [i for i, ev in enumerate(out['order'])
                                 if ev.startswith('fetch:settled:')]
            reload_positions = [i for i, ev in enumerate(out['order'])
                                 if ev == 'reload']
            check('reload happened exactly once',
                  len(reload_positions) == 1, out['order'])
            check('reload fires only AFTER every mirrored file finished writing '
                  '— this is the fix: a restore that reloads before its own '
                  'PUTs land is indistinguishable from one that never PUT at all',
                  len(settle_positions) == 3
                  and reload_positions
                  and reload_positions[0] > max(settle_positions),
                  out['order'])

        # ── backward compat: a backup exported BEFORE the ks()-scoping fix
        # carries the bare 'cafresohq_hq_v1:memory' key (no slug suffix at
        # all). The fallback in importOffice's lookup must still resolve
        # that, not just the newly-scoped form exercised above — a boss
        # restoring an old backup file must not lose this either. Reuses
        # the exact same lifted importOffice (`js`), a fresh mocked backend,
        # and just one entry so the assertion stays a single clean fact.
        old_format_harness = HARNESS.replace(
            "'cafresohq_hq_v1:theme': '\"dark\"',\n"
            "    'cafresohq_hq_v1:tasks': '[{\"id\":1,\"title\":\"Ship it\"}]',\n"
            "    'cafresohq_hq_v1:projects': '[{\"id\":\"p1\"}]',\n"
            "    // The realistic current shape: memory's key is ks()-scoped, so a real\n"
            "    // export from a live, slugged office carries the office's slug as a\n"
            "    // suffix, not the bare name the map's keys are written under.\n"
            "    'cafresohq_hq_v1:memory:1a2b3c4d5e6f7890': '{\"notes\":\"hi\"}',\n"
            "    'cafresohq_hq_v1:totallyUnknownFutureKey': '{\"x\":1}',",
            "'cafresohq_hq_v1:memory': '{\"notes\":\"old-format backup\"}',")
        assert old_format_harness != HARNESS, 'old_format_harness edit did not match — HARNESS template drifted'
        p2 = subprocess.run(['node', '-e', old_format_harness % js],
                             capture_output=True, text=True, timeout=60)
        if p2.returncode != 0:
            check('the lifted importOffice runs on an old-format (bare "memory") backup',
                  False, p2.stderr.strip()[:300])
        else:
            out2 = json.loads(p2.stdout.strip().split('\n')[-1])
            urls2 = sorted(c['url'] for c in out2['fetchCalls'])
            check("an OLD backup's bare 'memory' key (no slug suffix) still resolves to hq/memory/context",
                  'http://TESTAPI/hq/memory/context' in urls2, urls2)

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
