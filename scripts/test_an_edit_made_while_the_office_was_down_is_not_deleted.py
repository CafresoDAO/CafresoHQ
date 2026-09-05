#!/usr/bin/env python3
"""The reload deleted the edit the restart had already refused to save.

Measured 2026-09-05 (#408) against a real `python3 serve.py` on a scratch
office, by driving the REAL `useFileStored` out of app/storage.jsx under node
— test_durability_retry.py's note that "the hook cannot be driven headlessly"
is what this file exists to retire.

  file on disk        [{"id":"old","title":"yesterday"}]
  boss adds           {"id":"new","title":"the thing I just did"}
  ...while serve.py is restarting.  The 1500ms PUT fires into a dead port.
  warns               '[cafresohq] file save failed for state/tasks fetch failed'
  localStorage        holds BOTH tasks
  office comes back, boss reloads
  afterReload         [{"id":"old","title":"yesterday"}]
  fileAfterReload     [{"id":"old","title":"yesterday"}]

The edit was gone from both halves. A freshly reloaded tab is `untouched` and
not `dirty` by construction, so the mount fetch adopted the stale file and
then mirrored it back over the one copy that still had the work. The only
surface that ever mentioned the failure was a toast on the page the reload
destroyed.

The fix is a note in the same store as the value: a failed PUT (and a
pagehide flush that cannot know whether it landed) writes `<key>::unpaid`,
and the next mount reads it as "local is ahead of the file", heals disk from
localStorage, and clears it. A successful PUT clears it too, so a healthy
office never carries one.

This test asserts the INVARIANT, not the wording: after a write the server
refused, no subsequent reload may ever leave the office holding less than
what the boss last saw. Both stores are exercised — the plain ones that keep
theirs, and the mergeOnDirty ones (activity, messages) that take the union.

Run: python3 scripts/test_an_edit_made_while_the_office_was_down_is_not_deleted.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORAGE = ROOT / 'app' / 'storage.jsx'
FAILS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    print(('  ok    ' if cond else '  FAIL  ') + label
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(label)


# The harness lifts the real hook and runs it against a stub /hq/state server
# whose PUT can be switched off — the restart, without needing a restart.
HARNESS = r'''
import http from 'node:http';
import fs from 'node:fs';

// ── a stand-in for serve.py's /hq/<scope>/<name> door ──────────────────
let disk = null;            // what the file holds
let acceptPut = true;       // false = the office is down / the disk is full
const srv = http.createServer((req, res) => {
  if (req.method === 'GET') {
    res.writeHead(200, {'content-type':'application/json'});
    return res.end(JSON.stringify(disk));
  }
  let b = '';
  req.on('data', d => b += d);
  req.on('end', () => {
    if (!acceptPut) { res.writeHead(503); return res.end('{"error":"down"}'); }
    try { disk = JSON.parse(b); } catch (_e) {}
    res.writeHead(200, {'content-type':'application/json'});
    res.end('{"ok":true}');
  });
});
await new Promise(r => srv.listen(0, '127.0.0.1', r));
const BASE = 'http://127.0.0.1:' + srv.address().port;
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ── a localStorage the reload can carry across ────────────────────────
function makeStore(){
  const m = new Map();
  const t = { getItem: k => (m.has(k) ? m.get(k) : null),
              setItem: (k,v) => { m.set(k, String(v)); },
              removeItem: k => m.delete(k), clear: () => m.clear(), __m: m };
  return new Proxy(t, {
    ownKeys: () => [...m.keys()],
    getOwnPropertyDescriptor: () => ({ enumerable:true, configurable:true, value:undefined }),
    has: (o,p) => p in o || m.has(p),
    get: (o,p) => (p in o ? o[p] : m.get(p)),
  });
}

// ── just enough React for one component that holds one store ──────────
let hooks, idx, effects;
const React = {
  useState(init){ const i = idx++;
    if (!(i in hooks)) hooks[i] = { v: (typeof init === 'function' ? init() : init) };
    const c = hooks[i];
    return [c.v, u => { c.v = typeof u === 'function' ? u(c.v) : u; }]; },
  useRef(init){ const i = idx++; if (!(i in hooks)) hooks[i] = { current: init }; return hooks[i]; },
  useCallback(f){ return f; },
  useMemo(f){ return f(); },
  useEffect(f, deps){ const i = idx++; const p = hooks[i];
    const changed = !p || !deps || !p.deps || deps.length !== p.deps.length
      || deps.some((d,j) => !Object.is(d, p.deps[j]));
    if (changed) effects.push(() => { if (p && p.cleanup) p.cleanup(); hooks[i] = { deps, cleanup: f() }; }); },
};
globalThis.React = React;
globalThis.CHAT_CUT_NOTE = ''; globalThis.CHAT_GONE_NOTE = '';
globalThis.floorEmit = () => {}; globalThis.snagOpener = s => s;
globalThis.withRouteOut = s => s; globalThis.CafresoHQClient = {};
globalThis.CustomEvent = class { constructor(t,i){ this.type=t; this.detail=i&&i.detail; } };
globalThis.window = { _API_BASE: BASE, addEventListener: () => {},
  removeEventListener: () => {}, dispatchEvent: () => true };
globalThis.document = { hasFocus: () => true, visibilityState:'visible',
  addEventListener: () => {}, removeEventListener: () => {} };
console.warn = () => {};

// ── the real source ───────────────────────────────────────────────────
const src = fs.readFileSync(process.env.STORAGE_PATH, 'utf8');
const body = src.split('\n')
  .filter(l => !/^import\s/.test(l) && !/^export\s*\{/.test(l)).join('\n');
const mod = new Function('localStorage', 'sessionStorage',
  body + '\nreturn { useFileStored, mergeByIdCap };');

function page(ls, define){
  hooks = {};
  globalThis.window.localStorage = ls;
  const M = mod(ls, makeStore());
  let api;
  const render = () => { idx = 0; effects = []; api = define(M); for (const e of effects) e(); };
  render();
  return { api: () => api,
           tick: async ms => { for (let i = 0; i < Math.ceil(ms/50); i++) { await sleep(50); render(); } } };
}

const LS = 'k:tasks';
const R = {};

async function trial(mergeOnDirty){
  disk = [{ id:'old', title:'yesterday' }];
  acceptPut = true;
  const ls = makeStore();
  const ref = { current: [] };
  const opts = mergeOnDirty
    ? { mergeOnDirty: true }
    : {};
  const tf = mergeOnDirty ? (fetched => M0.mergeByIdCap(ref.current, fetched, 200)) : undefined;
  let M0 = null;
  const mk = (M) => { M0 = M;
    const [v, set] = M.useFileStored(LS, 'state', 'tasks', [],
      mergeOnDirty ? (fetched => M.mergeByIdCap(ref.current, fetched, 200)) : undefined, opts);
    ref.current = v;
    return { v, set }; };

  // session 1: sees the file, then edits while the office is DOWN
  const p1 = page(ls, mk);
  await p1.tick(700);
  const saw = JSON.stringify(p1.api().v);
  acceptPut = false;                                   // serve.py restarting
  p1.api().set(prev => [...prev, { id:'new', title:'the thing I just did' }]);
  await p1.tick(2600);                                 // the PUT fires and fails
  const lsAfter = ls.getItem(LS);
  acceptPut = true;                                    // the office is back

  // session 2: the boss reloads. Same browser, same localStorage.
  const p2 = page(ls, mk);
  await p2.tick(900);
  const afterReload = JSON.stringify(p2.api().v);
  await sleep(2200);                                   // let any heal PUT land
  const fileAfter = JSON.stringify(disk);

  return { saw, lsAfter, afterReload, fileAfter,
           unpaidLeft: ls.getItem(LS + '::unpaid') !== null };
}

R.plain = await trial(false);
R.merge = await trial(true);

// ── control: a HEALTHY office must not start carrying an unpaid note ──
{
  disk = []; acceptPut = true;
  const ls = makeStore();
  const p = page(ls, M => { const [v, set] = M.useFileStored(LS, 'state', 'tasks', []); return { v, set }; });
  await p.tick(700);
  p.api().set(prev => [...prev, { id:'fine', title:'ordinary work' }]);
  await p.tick(2600);
  R.healthy = { file: JSON.stringify(disk), unpaidLeft: ls.getItem(LS + '::unpaid') !== null };
}

srv.close();
console.log(JSON.stringify(R));
'''

MARK = 'the thing I just did'


def main() -> int:
    print('an edit made while the office was down is not deleted by the reload')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    if not STORAGE.exists():
        check('app/storage.jsx is where the hook lives', False, str(STORAGE))
        return 1

    proc = subprocess.run(
        ['node', '--input-type=module', '-e', HARNESS],
        cwd=str(ROOT), capture_output=True, text=True, timeout=180,
        env={**__import__('os').environ, 'STORAGE_PATH': str(STORAGE)})
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        check('the node harness runs the real hook', False, 'see stderr')
        return 1
    R = json.loads(proc.stdout.strip().split('\n')[-1])

    for kind in ('plain', 'merge'):
        t = R[kind]
        label = 'a plain store' if kind == 'plain' else 'a mergeOnDirty store'
        check(f'{label}: the session started from the file on disk',
              'yesterday' in t['saw'],
              f"{t['saw']!r} — if the mount fetch never landed the rest of "
              'this trial proves nothing')
        check(f'{label}: the refused write still reached localStorage',
              MARK in (t['lsAfter'] or ''),
              f"{t['lsAfter']!r} — localStorage is the only copy at this "
              'point; if it is not here there is nothing left to rescue')
        check(f'{label}: the reload does NOT delete it',
              MARK in t['afterReload'],
              f"{t['afterReload']!r} — THE BUG. A reloaded tab is untouched "
              'and not dirty, so without the unpaid note the mount fetch '
              'adopts the stale file and overwrites the one surviving copy')
        check(f'{label}: ...and disk is healed, not left behind',
              MARK in t['fileAfter'],
              f"{t['fileAfter']!r} — rescuing it into React state only moves "
              'the loss to the next browser; the heal has to reach the file')
        check(f'{label}: the note is spent once it is paid',
              t['unpaidLeft'] is False,
              'a note that is never cleared makes every future boot refuse '
              'the file, which is the opposite failure')

    check('a healthy office writes the file and carries no note',
          'ordinary work' in R['healthy']['file'] and R['healthy']['unpaidLeft'] is False,
          f"{R['healthy']!r} — the note must be evidence of a real failure, "
          'not a flag every write sets')

    # ── the wiring, so the note cannot be quietly detached from either end ──
    src = STORAGE.read_text(encoding='utf-8')
    check('the failed-PUT arm writes the note',
          "::unpaid', '1'" in src and 'file save failed for' in src,
          'app/storage.jsx — the catch that already warns must also record')
    check('the mount fetch reads it as "local is ahead"',
          src.count('unpaidRef.current') >= 3,
          'app/storage.jsx — a note nothing reads is not a fix. Three reads: '
          'the first-render load, the plain-store guard, and the mergeOnDirty '
          'heal')

    print()
    if FAILS:
        print(f'an edit made while the office was down: {len(FAILS)} FAILED')
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('an edit made while the office was down: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
