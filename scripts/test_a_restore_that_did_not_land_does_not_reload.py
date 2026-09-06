#!/usr/bin/env python3
"""#402 — two places in the never-swept half of the client where the office
did the work, the work failed, and the boss's only evidence said it had
worked.

1. **modals/settings.jsx — Settings → OFFICE BACKUP → IMPORT.**
   `importOffice` restores the backup into localStorage and, for the
   thirteen keys that are ALSO mirrored to an hq-state/hq-memory file,
   PUTs the matching file. That PUT is the whole reason `OFFICE_FILE_BACKED`
   exists, and the map's own comment says why:

       "within the same reload this button triggers, the mount-fetch pulls
        the old file back over the just-written value and the 'restore'
        silently undoes itself with no error anywhere."

   The PUT was `fetch(…).catch(() => {})` — no `r.ok` check, the rejection
   swallowed, `Promise.allSettled`'s results discarded (they could not
   reject anyway), and `window.location.reload()` underneath it
   unconditionally. So the failure this code exists to prevent is exactly
   what a failure of this code produces, and it is invisible: **a reload is
   what success looks like.** The boss confirmed a danger dialog, watched
   the app reload, and got their OLD office back.

   Measured on the real lifted body against four responses — offline, 403,
   500, healthy: all four wrote 3 localStorage keys, attempted 2 PUTs,
   fired the reload, and left `notes: ['']`. Byte-identical.

2. **views/projects.jsx — the Classic conflict banner's Reload button.**
   The banner reads "⚠ Your coworker changed this file while you had
   edits."; `reloadOpenClassic` is what its Reload calls. The read was
   swallowed into `catch (_e) {}` and `setConflict(false)` sat OUTSIDE the
   try — so a failed reload dismissed the warning, left the stale buffer
   untouched, and said nothing. Dismissing the banner is the boss's ONLY
   signal, and it happened either way. Measured: office down →
   `bannerCleared: true, bufferContent: "MY OLD BUFFER", errsShown: []`.

Both fixes ADD a branch rather than split a function, per `## 395`'s
precedent.

Run: python3 scripts/test_a_restore_that_did_not_land_does_not_reload.py
(skips the live-execution checks if `node` isn't on PATH — the source-shape
checks still run everywhere)
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_JSX = ROOT / 'modals' / 'settings.jsx'
PROJECTS_JSX = ROOT / 'views' / 'projects.jsx'
STORAGE_JSX = ROOT / 'app' / 'storage.jsx'
HARNESS = ROOT / 'scripts' / 'harness_office_restore_mirror.mjs'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('A restore that did not land does not reload over itself — #402')

    settings_src = SETTINGS_JSX.read_text(encoding='utf-8')
    projects_src = PROJECTS_JSX.read_text(encoding='utf-8')
    storage_src = STORAGE_JSX.read_text(encoding='utf-8')
    has_node = bool(shutil.which('node'))

    # ── 1. the office-restore mirror ───────────────────────────────────
    print('\n1. modals/settings.jsx — the restore that reloaded over itself')

    check('the bare swallow on the mirror PUT is gone — the regression itself',
          '}).catch(() => {}));' not in settings_src)
    check('no `/hq/${...}` PUT anywhere in this file still resolves without '
          'an r.ok check',
          settings_src.count('/hq/${target.scope}/${target.name}') == 1
          and 'if (!r.ok) throw new Error(`HTTP ${r.status}' in settings_src)
    check('the reload is no longer unconditional — it is reached only after '
          'the stale-file branch has returned',
          re.search(r"if \(stale\.length\) \{.*?return;\s*\}\s*\}\s*"
                    r"setOfficeRetry\(null\);\s*window\.location\.reload\(\);",
                    settings_src, re.S) is not None)
    check('Promise.allSettled — which could never reject over handlers that '
          'always resolved — is gone in favour of results that are read',
          'Promise.allSettled(filePuts)' not in settings_src
          and 'await Promise.all(filePuts)).filter(Boolean)' in settings_src)
    check('the failure names the office as the subject (officeCause, not '
          'cleanCause: these PUTs go to the office\'s own backend)',
          'officeCause' in settings_src
          and "import { cleanCause, officeCause } from '../app/floor.jsx';" in settings_src)
    check('a retry affordance exists and is a real control, not only note '
          'text the next click clears',
          'retryOfficeRestore' in settings_src
          and 'TRY AGAIN' in settings_src
          and 'onClick={retryOfficeRestore}' in settings_src)
    check('the retry reloads only once nothing stale is left',
          re.search(r"setOfficeRetry\(null\);\s*window\.location\.reload\(\);\s*\};\s*"
                    r"const exportOffice", settings_src, re.S) is not None)
    check('app/storage.jsx (the sibling this fix copies) still checks r.ok on '
          'its own /hq/ PUT — the precedent has not drifted',
          'if (!r.ok) throw new Error(`HTTP ${r.status}`);' in storage_src)
    check('OFFICE_FILE_BACKED still covers every mirrored key, so the branch '
          'has something to be right about',
          settings_src.count("{ scope: 'state', name:") +
          # thirteen when this was written; `## 413.` added chat + workspaces
          settings_src.count("{ scope: 'memory', name:") == 15,
          settings_src.count("{ scope: 'state', name:") +
          settings_src.count("{ scope: 'memory', name:"))

    # ── 2. the Classic conflict banner ────────────────────────────────
    print('\n2. views/projects.jsx — the Reload that only removed the warning')

    check('reloadOpenClassic no longer swallows the read — the regression itself',
          'catch (_e) {}\n    setConflict(false);' not in projects_src)
    check('setConflict(false) now sits INSIDE the try, after the read landed',
          re.search(r"const reloadOpenClassic = async \(path\) => \{\s*"
                    r"setErr\(null\);\s*try \{[^}]*?fsReadText[\s\S]*?"
                    r"setConflict\(false\);\s*\}\s*catch \(e\) \{\s*setErr\(",
                    projects_src) is not None)
    check('the reason lands on `err`, which both Classic panes already render '
          'through officeCause beside the banner',
          projects_src.count("{err && <span className=\"proj-edit-err\">{officeCause(err)}</span>}") == 2)
    check('both Classic banners still route their Reload through this one '
          'function (so the fix covers both)',
          projects_src.count('onClick={() => reloadOpenClassic(openFile.path)}') == 2)

    # ── 3. driven, on the real bodies ─────────────────────────────────
    print('\n3. driven — the real lifted bodies under node')

    check('the harness that lifts both real bodies exists', HARNESS.exists())

    if has_node and HARNESS.exists():
        r = subprocess.run(['node', str(HARNESS), str(ROOT)],
                           capture_output=True, text=True)
        check('the harness runs clean', r.returncode == 0, r.stderr[-500:])
        rows = {}
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line.startswith('{'):
                continue
            o = json.loads(line)
            rows[o['scenario']] = o

        for name in ('offline', 'refused403', 'server500'):
            o = rows.get(name, {})
            check(f'{name}: the reload that would REVERT the restore does not fire',
                  o.get('reloaded') is False, o)
            check(f'{name}: the boss is told, in one honest sentence naming the '
                  f'files that would come back',
                  any('could not be written' in n
                      and 'would pull the old' in n
                      and 'state/tasks' in n for n in o.get('notes', [])),
                  o.get('notes'))
            check(f'{name}: a retry is offered over exactly the files that failed',
                  o.get('retryOffered') == 2
                  and sorted(o.get('staleFiles', [])) == ['memory/agents', 'state/tasks'],
                  o)

        check('the three failures give three DIFFERENT causes — they were '
              'byte-identical before',
              len({tuple(rows[n].get('whys', [])) for n in
                   ('offline', 'refused403', 'server500')}) == 3,
              {n: rows[n].get('whys') for n in ('offline', 'refused403', 'server500')})
        check('offline says the office is not answering',
              "the office isn't answering" in ' '.join(rows.get('offline', {}).get('whys', [])),
              rows.get('offline'))
        check('403 says the office is not allowed, not that it could not find it',
              "isn't allowed to touch that file" in ' '.join(rows.get('refused403', {}).get('whys', [])),
              rows.get('refused403'))

        h = rows.get('healthy', {})
        check('a healthy restore still reloads, still says nothing, and offers '
              'no retry — the fix costs the working path nothing',
              h.get('reloaded') is True
              and h.get('retryOffered') == 0
              and [n for n in h.get('notes', []) if n] == [],
              h)
        check('every scenario still wrote all 3 localStorage keys and attempted '
              'both mirror PUTs — reporting a failure must not cost the boss '
              'the restore they came for',
              all(rows[n].get('lsKeysWritten') == 3 and rows[n].get('putCount') == 2
                  for n in ('offline', 'refused403', 'server500', 'healthy')),
              {n: (rows[n].get('lsKeysWritten'), rows[n].get('putCount')) for n in rows
               if 'reload_' not in n})

        down = rows.get('reload_office_down', {})
        ok = rows.get('reload_healthy', {})
        check('Reload with the office down keeps the conflict banner up',
              down.get('bannerCleared') is False, down)
        check('Reload with the office down says why, instead of nothing',
              down.get('errsShown') not in (None, []), down)
        check('the stale buffer is still the stale buffer — the fix reports, '
              'it does not invent content',
              down.get('bufferContent') == 'MY OLD BUFFER', down)
        check('a healthy Reload still clears the banner and adopts the '
              "coworker's content, silently",
              ok.get('bannerCleared') is True
              and ok.get('bufferContent') == 'COWORKER CONTENT'
              and ok.get('errsShown') == [], ok)

    check('node is on PATH (needed to genuinely execute the two extracted '
          'bodies above)', has_node, 'skipped the live-execution checks')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
