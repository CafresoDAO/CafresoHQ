#!/usr/bin/env python3
"""A message sent in the other tab is not erased by this one.

Measured 2026-09-06 (#418). `## 413` moved the chat from `useStored` to
`useFileStored` so the conversation could live on disk, and
`docs/BETA_READINESS.md` filed the cost as a beta gate: `useStored` carried
a cross-tab `storage`-event absorber and `useFileStored` did not. Two tabs
of the same office, both hydrated. The boss sends a message in tab B — it
reaches localStorage at once and the file 1.5s later. Tab A never hears
about it. The next thing tab A does — a message, a reply that streams in,
a rename — persists tab A's copy of the conversation over BOTH halves, and
tab B's message is gone from disk, from localStorage, and from every tab
that ever reloads.

This file drives the REAL hooks out of `app/storage.jsx` under node — the
same lift `## 413`'s guard uses — with TWO pages over ONE localStorage map,
each page holding its own `window` so a write in one page delivers a
`storage` event to the listeners of the other and never to its own, which
is exactly what a browser does. Against a stub `/hq/state/chat` door it
asserts:

  1. the gate: tab B's message survives tab A's next persist, in tab A's
     state, on disk, and in localStorage;
  2. the absorb does not ping-pong: two tabs settle after one exchange with
     a bounded number of writes, because an absorbed value is set into state
     and never persisted back;
  3. a reply streaming in tab A is not clobbered by tab B's copy of it — the
     other tab's localStorage carries `interrupted: true` on a record that is
     alive here, and a union that let theirs win on that id would stamp a
     cut-off note onto a reply that is still arriving. Ours wins while
     `streaming`; theirs wins the moment it is not, so the finished reply
     reaches tab B on tab A's finalize;
  4. the reload class `## 402` names is not reopened: a page reloaded after
     the exchange, and a brand-new browser, both read the whole conversation
     and neither writes a shorter one back;
  5. a `storage` event that lands BEFORE tab A's mount fetch resolves does
     not disturb `## 413`'s union — the history, the other tab's message and
     this tab's own keystroke all reach disk.

The negative control drives the same hook with the absorb detached and
requires the deletion to reproduce, so the gate check cannot pass by
accident.

Run: python3 scripts/test_a_message_sent_in_the_other_tab_is_not_erased_by_this_one.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORAGE = ROOT / 'app' / 'storage.jsx'
APP = ROOT / 'app.jsx'
FAILS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    print(('  ok    ' if cond else '  FAIL  ') + label
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(label)


HARNESS = r'''
import http from 'node:http';
import fs from 'node:fs';

let disk = null;
const WIRE = { puts: 0, bodies: [] };
const srv = http.createServer((req, res) => {
  if (req.method === 'GET') {
    return setTimeout(() => {
      res.writeHead(200, {'content-type':'application/json'});
      res.end(JSON.stringify(disk));
    }, 120);
  }
  let b = '';
  req.on('data', d => b += d);
  req.on('end', () => {
    WIRE.puts++; WIRE.bodies.push(b);
    try { disk = JSON.parse(b); } catch (_e) {}
    res.writeHead(200, {'content-type':'application/json'});
    res.end('{"ok":true}');
  });
});
await new Promise(r => srv.listen(0, '127.0.0.1', r));
const BASE = 'http://127.0.0.1:' + srv.address().port;
const sleep = ms => new Promise(r => setTimeout(r, ms));

/* One origin: a single Map, shared by every tab. Each TAB gets its own
   facade over it, and a write through one facade is announced — as a
   `storage` event, with the browser's shape — to every OTHER tab's window
   and never to its own. That asymmetry is the whole subject here. */
const ORIGIN = { m: new Map(), tabs: [], writes: 0 };
function makeWindow(){
  const ls = new Map();
  return {
    _API_BASE: BASE,
    addEventListener: (t, f) => { (ls.get(t) || ls.set(t, []).get(t)).push(f); },
    removeEventListener: (t, f) => { const a = ls.get(t) || []; const i = a.indexOf(f); if (i >= 0) a.splice(i, 1); },
    dispatchEvent: () => true,
    _fire: (t, e) => { for (const f of [...(ls.get(t) || [])]) f(e); },
  };
}
function makeFacade(win){
  const m = ORIGIN.m;
  const announce = (key, newValue, oldValue) => {
    ORIGIN.writes++;
    for (const t of ORIGIN.tabs) if (t !== win) t._fire('storage', { key, newValue, oldValue });
  };
  const t = { getItem: k => (m.has(k) ? m.get(k) : null),
              setItem: (k,v) => { const o = m.has(k) ? m.get(k) : null; m.set(k, String(v)); announce(k, String(v), o); },
              removeItem: k => { const o = m.has(k) ? m.get(k) : null; m.delete(k); announce(k, null, o); },
              clear: () => m.clear() };
  return new Proxy(t, {
    ownKeys: () => [...m.keys()],
    getOwnPropertyDescriptor: () => ({ enumerable:true, configurable:true, value:undefined }),
    has: (o,p) => p in o || m.has(p),
    get: (o,p) => (p in o ? o[p] : m.get(p)),
  });
}
function makeSession(){
  const m = new Map();
  return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k,v) => m.set(k, String(v)),
           removeItem: k => m.delete(k), clear: () => m.clear() };
}

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
globalThis.CHAT_CUT_NOTE = '(cut off)'; globalThis.CHAT_GONE_NOTE = '(nothing came back)';
globalThis.floorEmit = () => {}; globalThis.snagOpener = s => s;
globalThis.withRouteOut = s => s; globalThis.CafresoHQClient = {};
globalThis.CustomEvent = class { constructor(t,i){ this.type=t; this.detail=i&&i.detail; } };
globalThis.document = { hasFocus: () => true, visibilityState:'visible',
  addEventListener: () => {}, removeEventListener: () => {} };
console.warn = () => {};

const src = fs.readFileSync(process.env.STORAGE_PATH, 'utf8');
const body = src.split('\n')
  .filter(l => !/^import\s/.test(l) && !/^export\s*\{/.test(l)).join('\n');
/* `absorbChat` is this entry's own addition. A tree without it must still
   build, so the missing binding degrades into behavioural FAILs on the
   checks that need it rather than one ReferenceError that reports nothing. */
const mod = new Function('localStorage', 'sessionStorage',
  body + '\nreturn { useFileStored, persistableChat, mergeChat,'
       + '\n  absorbChat: (typeof absorbChat === "undefined" ? null : absorbChat) };');

const LS = 'cafresohq_hq_v1:chat';
const ABSORB = process.env.CHAT_ABSORB === '1';   // does app.jsx wire it?

/* A tab: its own window, its own module instance over its own facade, its
   own hook cells. `hooks` is swapped in around every render so two tabs can
   interleave. `safe: false` is the negative control — the same hook with
   the absorb detached, whatever the tree has. */
function tab({ safe = true } = {}){
  const win = makeWindow();
  ORIGIN.tabs.push(win);
  const own = {};
  const M = mod(makeFacade(win), makeSession());
  const mergeRef = { current: [] };
  let api;
  const render = () => {
    hooks = own; idx = 0; effects = []; globalThis.window = win;
    const opts = { persistTransform: M.persistableChat, mergeOnDirty: true };
    if (safe && ABSORB && M.absorbChat) opts.absorb = (theirs, mine) => M.absorbChat(mine, theirs);
    const [v, set] = M.useFileStored(LS, 'state', 'chat', [],
      (fetched) => M.mergeChat(mergeRef.current, fetched), opts);
    mergeRef.current = v;
    api = { v, set };
    for (const e of effects) e();
  };
  render();
  const T = { win, render, get v(){ return api.v; },
    send: (u) => { hooks = own; globalThis.window = win; api.set(u); render(); },
    tick: async ms => { for (let i = 0; i < Math.ceil(ms/25); i++) { await sleep(25); render(); } },
    close: () => { ORIGIN.tabs.splice(ORIGIN.tabs.indexOf(win), 1); } };
  return T;
}
/* Two tabs share the clock: a tick of both is what "the office sat there
   for a moment" means when the boss has two windows open. */
async function tickAll(tabs, ms){ for (let i = 0; i < Math.ceil(ms/25); i++) { await sleep(25); for (const t of tabs) t.render(); } }
const ids = xs => (Array.isArray(xs) ? xs : []).map(m => m && m.id).join(',');
const msg = (id, text) => ({ id, from:'user', name:'You', text, thread:'direct' });

const HISTORY = [
  msg('m1', 'what did we ship last week?'),
  { id:'m2', from:'ceo', name:'CafresoHQ', text:'The ckBAT proposal and the ledger sweep.', thread:'direct' },
  msg('m3', 'good. write that up for the board'),
];
const R = {};

// ── 1. the gate, and its control ─────────────────────────────────────
async function exchange(safe){
  ORIGIN.m.clear(); ORIGIN.tabs.length = 0; disk = HISTORY.slice();
  const A = tab({ safe }), B = tab({ safe });
  await tickAll([A, B], 700);                     // both hydrated
  B.send(prev => [...prev, msg('m4', 'sent from the other tab')]);
  await tickAll([A, B], 2000);                    // B's PUT lands
  const diskAfterB = ids(disk);
  A.send(prev => [...prev, msg('m5', 'sent from this tab')]);
  await tickAll([A, B], 2000);                    // A's PUT lands
  const writesBefore = ORIGIN.writes, putsBefore = WIRE.puts;
  const out = { diskAfterB, inA: ids(A.v), inB: ids(B.v), onDisk: ids(disk),
                inLS: ids(JSON.parse(ORIGIN.m.get(LS) || '[]')) };
  await tickAll([A, B], 3000);                    // the settle
  out.settleWrites = ORIGIN.writes - writesBefore;
  out.settlePuts = WIRE.puts - putsBefore;
  out.A = A; out.B = B;
  return out;
}
{
  const r = await exchange(true);
  R.gate = { ...r, A: undefined, B: undefined };

  // ── 4. the reload class, on the same origin and on a fresh one ──────
  const putsBefore = WIRE.puts;
  const A2 = tab();                                // tab A reloaded
  await tickAll([r.A, r.B, A2], 2600);
  R.reload = { inA2: ids(A2.v), onDisk: ids(disk), puts: WIRE.puts - putsBefore,
               shorter: WIRE.bodies.slice(putsBefore).some(b => JSON.parse(b).length < 5) };
  r.A.close(); r.B.close(); A2.close();
  ORIGIN.m.clear(); ORIGIN.tabs.length = 0;
  const F = tab();                                 // a brand-new browser
  await F.tick(700);
  R.fresh = ids(F.v);
  F.close();
}
{
  const r = await exchange(false);
  R.control = { inA: r.inA, onDisk: r.onDisk };
  r.A.close(); r.B.close();
}

// ── 3. a reply streaming in A while B writes ─────────────────────────
{
  ORIGIN.m.clear(); ORIGIN.tabs.length = 0; disk = HISTORY.slice();
  const A = tab(), B = tab();
  await tickAll([A, B], 700);
  A.send(prev => [...prev, { id:'r1', from:'ceo', name:'CafresoHQ', text:'', streaming:true, thread:'direct' }]);
  let raw = '';
  for (let i = 0; i < 30; i++) {
    raw += 'token' + i + ' ';
    A.send(prev => prev.map(m => m.id === 'r1' ? { ...m, text: raw } : m));
    await sleep(16); B.render();
    if (i === 15) { B.send(prev => [...prev, msg('m6', 'typed while A streams')]); A.render(); }
  }
  const midA = (A.v.find(m => m.id === 'r1') || {});
  const midB = (B.v.find(m => m.id === 'r1') || {});
  R.stream = { midA: { text: String(midA.text||''), streaming: !!midA.streaming, cut: String(midA.text||'').includes('(cut off)') },
               midB: { interrupted: !!midB.interrupted, text: String(midB.text||'') },
               m6InA: A.v.some(m => m.id === 'm6') };
  A.send(prev => prev.map(m => m.id === 'r1' ? { ...m, text: raw, streaming:false } : m));
  await tickAll([A, B], 2600);
  const endB = (B.v.find(m => m.id === 'r1') || {});
  R.stream.endB = { text: String(endB.text||''), streaming: !!endB.streaming, interrupted: !!endB.interrupted };
  R.stream.onDisk = ids(disk);
  A.close(); B.close();
}

// ── 5. a storage event before this tab's mount fetch resolves ────────
{
  ORIGIN.m.clear(); ORIGIN.tabs.length = 0; disk = HISTORY.slice();
  const B = tab();
  await B.tick(700);
  const A = tab();                                 // fetch in flight (120ms)
  B.send(prev => [...prev, msg('m7', 'sent while A was still loading')]);
  A.render();
  A.send(prev => [...prev, msg('m8', 'typed before A had the file')]);
  await tickAll([A, B], 2600);
  R.early = { inA: ids(A.v), onDisk: ids(disk) };
  A.close(); B.close();
}

srv.close();
console.log(JSON.stringify(R));
'''


def main() -> int:
    print('a message sent in the other tab is not erased by this one')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    for p in (STORAGE, APP):
        if not p.exists():
            check(f'{p.name} exists', False, str(p))
            return 1

    app = APP.read_text(encoding='utf-8')
    storage = STORAGE.read_text(encoding='utf-8')
    m = re.search(r"useFileStored\(k\('chat'\)[^;]*?\);", app, re.S)
    call = m.group(0) if m else ''
    wired = 'absorb:' in call
    print(f"  ..    app.jsx {'wires' if wired else 'does NOT wire'} the chat's cross-tab absorb")

    proc = subprocess.run(
        ['node', '--input-type=module', '-e', HARNESS],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        env={**os.environ, 'STORAGE_PATH': str(STORAGE), 'CHAT_ABSORB': '1' if wired else '0'})
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        check('the node harness runs the real hooks', False, 'see stderr')
        return 1
    R = json.loads(proc.stdout.strip().split('\n')[-1])

    g = R['gate']
    print(f"  ..    disk after B's send: [{g['diskAfterB']}]; after A's: [{g['onDisk']}]; "
          f"A holds [{g['inA']}]; settle: {g['settleWrites']} writes, {g['settlePuts']} PUTs")
    # ── 1. the gate ──────────────────────────────────────────────────────
    check("tab A absorbs the message tab B sent",
          'm4' in g['inA'].split(','),
          f"A holds [{g['inA']}] — the `storage` event fired in A and nothing "
          'listened; A is now holding a conversation that is missing a turn')
    check("...and A's next persist does not erase it from disk",
          g['onDisk'] == 'm1,m2,m3,m4,m5',
          f"disk [{g['onDisk']}] — THE GATE. B's PUT landed ({g['diskAfterB']}); "
          "A's PUT then wrote A's copy over it and m4 is gone from the file")
    check('...nor from localStorage',
          'm4' in g['inLS'].split(','),
          f"localStorage [{g['inLS']}] — the half B's message reached first")
    check('...and tab B has both, in order',
          g['inB'] == 'm1,m2,m3,m4,m5',
          f"B holds [{g['inB']}]")
    check('the negative control reproduces the erasure with the absorb detached',
          'm4' not in R['control']['onDisk'].split(','),
          f"disk [{R['control']['onDisk']}] — the same two tabs WITHOUT the absorb "
          'must lose m4, or the checks above pass for some other reason')

    # ── 2. no ping-pong ──────────────────────────────────────────────────
    check('two tabs settle after one exchange, no write storm',
          g['settleWrites'] == 0 and g['settlePuts'] == 0,
          f"{g['settleWrites']} localStorage writes and {g['settlePuts']} PUTs "
          'in the 3s after both PUTs landed — an absorbed value must be set '
          'into state and never persisted, or each tab re-announces the other '
          'forever')

    # ── 3. the live reply ────────────────────────────────────────────────
    s = R['stream']
    check("a reply streaming in A keeps streaming when B writes",
          s['midA']['streaming'] and not s['midA']['cut']
          and str(s['midA']['text']).endswith('token29 '),
          f"{s['midA']!r} — B's localStorage carries r1 with `interrupted: true`; "
          'letting theirs win on a record that is alive here stamps a cut-off '
          'note onto a reply still arriving, and freezes its text')
    check("...while B still learns what A is saying",
          str(s['midB']['text'] or '').startswith('token0') and s['m6InA'],
          f"{s['midB']!r}, m6 in A: {s['m6InA']} — the other direction: B "
          "reads A's frames and A reads B's message, at once")
    check("...and B gets the finished reply on A's finalize",
          str(s['endB']['text']).endswith('token29 ') and not s['endB']['streaming']
          and not s['endB']['interrupted'],
          f"{s['endB']!r} — theirs must win once ours is no longer streaming, "
          'or B keeps a cut-off marker on a reply that finished')
    check('...and disk has the history, the reply and the interleaved message',
          set(s['onDisk'].split(',')) == {'m1', 'm2', 'm3', 'r1', 'm6'},
          f"disk [{s['onDisk']}]")

    # ── 4. the reload class ──────────────────────────────────────────────
    r = R['reload']
    check('a tab reloaded after the exchange reads the whole conversation',
          r['inA2'] == 'm1,m2,m3,m4,m5',
          f"reloaded tab holds [{r['inA2']}]")
    check('...and writes nothing shorter back (the `## 402` class)',
          not r['shorter'] and r['onDisk'] == 'm1,m2,m3,m4,m5',
          f"{r['puts']} PUTs on reload, shorter body: {r['shorter']}, disk [{r['onDisk']}]")
    check('a brand-new browser gets all five',
          R['fresh'] == 'm1,m2,m3,m4,m5',
          f"fresh browser holds [{R['fresh']}]")

    # ── 5. before hydration ──────────────────────────────────────────────
    e = R['early']
    check("a storage event before A's mount fetch resolves does not disturb the union",
          set(e['inA'].split(',')) == {'m1', 'm2', 'm3', 'm7', 'm8'},
          f"A holds [{e['inA']}] — history, B's message and A's own keystroke")
    check('...and all of it reaches disk',
          set(e['onDisk'].split(',')) == {'m1', 'm2', 'm3', 'm7', 'm8'},
          f"disk [{e['onDisk']}]")

    # ── the wiring ───────────────────────────────────────────────────────
    check("app.jsx hands the chat an `absorb` that merges through the hook's own value",
          wired and re.search(r"absorb:\s*\(theirs,\s*mine\)\s*=>\s*absorbChat\(mine,\s*theirs\)", call) is not None,
          f'{call[:260]!r} — the absorb must read the value the HOOK holds, not '
          "chatMergeRef: a render-old ref drops this tab's own unrendered send")
    check('useFileStored listens for the other tab on its own key',
          "addEventListener('storage'" in storage[storage.find('function useFileStored'):]
          and 'e.key !== lsKey' in storage,
          "app/storage.jsx — no `storage` listener in useFileStored")
    check('absorbChat lets ours win only while streaming',
          'const absorbChat' in storage and 'ours.streaming ? ours : m' in storage,
          'app/storage.jsx — the shared-id rule that keeps a live reply alive')

    print()
    if FAILS:
        print(f'a message sent in the other tab is not erased by this one: {len(FAILS)} FAILED')
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('a message sent in the other tab is not erased by this one: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
