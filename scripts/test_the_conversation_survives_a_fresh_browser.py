#!/usr/bin/env python3
"""Every conversation the office ever had lived in one browser's localStorage.

Measured 2026-09-05 (#413). `app.jsx:189` was `useStored`, not
`useFileStored`, so there was no `hq-state/chat.json` and never had been.
#408's durability map recorded it as `freshKept: false` and left it as the
largest gap: a tester who clears site data, opens a second browser, or picks
up a different device keeps their tasks, their roster, their Library and
their message registry — and loses every conversation they have ever had.

This file drives the REAL hooks out of `app/storage.jsx` under node — the
same lift #408 used to retire `test_durability_retry.py`'s "cannot be driven
headlessly" note — against a stub `/hq/<scope>/<name>` door, and asserts
three separate things:

  1. the conversation survives a FRESH ORIGIN (the fix);
  2. the swap did not open a NEW hole. useFileStored's mount fetch has a
     "keep theirs" guard that is correct for a snapshot and catastrophic for
     a log: one keystroke inside the ~300ms before the fetch resolves used to
     discard the fetched history AND replay the one-message local chat over
     the file. `mergeOnDirty` + `mergeChat` is what makes the swap safe, and
     the negative control here drives the swap WITHOUT them and requires the
     deletion to reproduce — so this check cannot pass by accident;
  3. the wire cost stayed bounded. Measured against a real `python3 serve.py`
     on :9418 with a real 1024-token reply at 40 tok/s over a 118-message
     transcript: 1027 setter calls, ONE PUT, 53.7 KB, 19.9 ms. The 1500ms
     debounce is re-armed by every token frame, so nothing reaches the wire
     while a reply streams. The check is an invariant (a whole reply costs a
     handful of PUTs, not one per frame), so removing the debounce fails it.

Also covers the two smaller rows on the same map: saved workspaces
(`app.jsx:619`) and the composer draft (`ui/chat.jsx:90`, the only row a
PLAIN RELOAD eats). The draft is asserted to be localStorage-only on
purpose — see the note at its call site.

Run: python3 scripts/test_the_conversation_survives_a_fresh_browser.py
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
CHAT_UI = ROOT / 'ui' / 'chat.jsx'
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
let acceptPut = true;
const WIRE = { puts: 0, putBytes: 0 };
const srv = http.createServer((req, res) => {
  if (req.method === 'GET') {
    /* A real mount fetch resolves in 100-300ms (#408 measured it, and the
       comment at useFileStored's hydratedRef says the same). The keystroke
       race below is only a race at all if the GET takes long enough for a
       browser to commit a render inside it, so the stub takes 120ms rather
       than answering on the same tick. */
    return setTimeout(() => {
      res.writeHead(200, {'content-type':'application/json'});
      res.end(JSON.stringify(disk));
    }, 120);
  }
  let b = '';
  req.on('data', d => b += d);
  req.on('end', () => {
    if (!acceptPut) { res.writeHead(503); return res.end('{"error":"down"}'); }
    WIRE.puts++; WIRE.putBytes += Buffer.byteLength(b);
    try { disk = JSON.parse(b); } catch (_e) {}
    res.writeHead(200, {'content-type':'application/json'});
    res.end('{"ok":true}');
  });
});
await new Promise(r => srv.listen(0, '127.0.0.1', r));
const BASE = 'http://127.0.0.1:' + srv.address().port;
const sleep = ms => new Promise(r => setTimeout(r, ms));

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
globalThis.window = { _API_BASE: BASE, addEventListener: () => {},
  removeEventListener: () => {}, dispatchEvent: () => true };
globalThis.document = { hasFocus: () => true, visibilityState:'visible',
  addEventListener: () => {}, removeEventListener: () => {} };
console.warn = () => {};

const src = fs.readFileSync(process.env.STORAGE_PATH, 'utf8');
const body = src.split('\n')
  .filter(l => !/^import\s/.test(l) && !/^export\s*\{/.test(l)).join('\n');
/* `mergeChat` is this entry's own addition, so a tree WITHOUT the fix has no
   such binding and a bare reference here throws at module-build time — the
   whole run dies on stderr and reports nothing about the other seventeen
   checks. #404 caught two checks doing exactly that. Resolve it defensively
   so a missing union degrades into behavioural FAILs on the checks that need
   it, with everything else still measured. */
const mod = new Function('localStorage', 'sessionStorage',
  body + '\nreturn { useStored, useFileStored, persistableChat, chatOnLoad, capChatFair,'
       + '\n  mergeChat: (typeof mergeChat === "undefined" ? null : mergeChat) };');

function page(ls, define){
  hooks = {};
  globalThis.window.localStorage = ls;
  const M = mod(ls, makeStore());
  let api;
  const render = () => { idx = 0; effects = []; api = define(M); for (const e of effects) e(); };
  render();
  return { M, api: () => api, render,
           tick: async ms => { for (let i = 0; i < Math.ceil(ms/25); i++) { await sleep(25); render(); } } };
}

const LS = 'cafresohq_hq_v1:chat';
const R = {};

/* Which hook app.jsx ACTUALLY wires the chat to, read out of app.jsx rather
   than transcribed here. Transcribing it is what makes a harness check pass
   in a tree that does not have the fix — the measurement then proves only
   that the harness author can type. `CHAT_HOOK` comes from a regex over
   app.jsx, so reverting the call site turns the headline check below from a
   pass into the exact loss it is named after. `mergeRef` stands in for
   chatMergeRef — a ref declared BEFORE the hook, because the transform is
   called from inside the useState initializer where a later `const` is
   still in TDZ. */
const CHAT_HOOK = process.env.CHAT_HOOK;   // 'useFileStored' | 'useStored'
function mountChat(ls, { safe = true } = {}){
  const mergeRef = { current: [] };
  return page(ls, M => {
    /* `safe: false` is the negative control on the MECHANISM — it always
       drives the file-backed hook without the union, whatever app.jsx is
       wired to, so it keeps proving the union is load-bearing even in a tree
       that has not been swapped yet. */
    if (safe && CHAT_HOOK !== 'useFileStored') {
      /* The office as it stands: localStorage only, no file at all. */
      const [v, set] = M.useStored(LS, [], M.persistableChat, M.chatOnLoad);
      mergeRef.current = v;
      return { v, set };
    }
    const [v, set] = (safe && M.mergeChat)
      ? M.useFileStored(LS, 'state', 'chat', [],
          (fetched) => M.mergeChat(mergeRef.current, fetched),
          { persistTransform: M.persistableChat, mergeOnDirty: true })
      /* the negative control: the same swap WITHOUT the union. */
      : M.useFileStored(LS, 'state', 'chat', [], M.chatOnLoad,
          { persistTransform: M.persistableChat });
    mergeRef.current = v;
    return { v, set };
  });
}

const HISTORY = [
  { id:'m1', from:'user', name:'You', text:'what did we ship last week?', thread:'direct' },
  { id:'m2', from:'ceo',  name:'CafresoHQ', text:'The ckBAT proposal and the ledger sweep.', thread:'direct' },
  { id:'m3', from:'user', name:'You', text:'good. write that up for the board', thread:'direct' },
];

// ── 1. a FRESH ORIGIN: no localStorage at all, the conversation on disk ──
{
  disk = HISTORY; acceptPut = true;
  const p = mountChat(makeStore());            // brand new browser
  await p.tick(700);
  R.fresh = JSON.stringify(p.api().v);
}

// ── 2. the pre-hydration keystroke. Safe wiring, then the control. ───────
async function keystrokeRace(safe){
  disk = HISTORY; acceptPut = true;
  const ls = makeStore();
  const p = mountChat(ls, { safe });
  // the boss types before the mount fetch resolves (~300ms in the browser;
  // here the very first render, which is strictly harder)
  p.api().set(prev => [...prev, { id:'typed', from:'user', name:'You',
                                  text:'are you there?', thread:'direct' }]);
  /* The commit React performs within a frame of a setter. app.jsx assigns
     chatMergeRef DURING this render, so the merge ref is current before the
     120ms GET above can resolve. Without it the union runs against a stale
     ref and silently drops the word just typed — which is exactly the
     window `## 413.` flags as its weakest verdict. */
  p.render();
  await p.tick(900);
  const inState = JSON.stringify(p.api().v);
  await sleep(2200);                            // let any replay PUT land
  return { inState, onDisk: JSON.stringify(disk) };
}
R.raceSafe = await keystrokeRace(true);
R.raceControl = await keystrokeRace(false);

// ── 3. wire cost of a real reply. rAF cadence, 1500ms debounce. ─────────
{
  disk = []; acceptPut = true;
  const ls = makeStore();
  const p = mountChat(ls);
  await p.tick(600);
  WIRE.puts = 0; WIRE.putBytes = 0;
  p.api().set(prev => [...prev, { id:'r1', from:'ceo', name:'CafresoHQ',
                                  text:'', streaming:true, thread:'direct' }]);
  let raw = '';
  const FLUSHES = 300;                          // ~5s of stream at 60Hz
  for (let i = 0; i < FLUSHES; i++) {
    raw += 'token' + i + ' ';
    p.api().set(prev => prev.map(m => m.id === 'r1' ? { ...m, text: raw } : m));
    await sleep(16);
  }
  p.api().set(prev => prev.map(m => m.id === 'r1' ? { ...m, text: raw, streaming:false } : m));
  const midStreamPuts = WIRE.puts;
  await p.tick(2600);
  R.stream = { flushes: FLUSHES, midStreamPuts, totalPuts: WIRE.puts,
               kb: +(WIRE.putBytes/1024).toFixed(1),
               landedOnDisk: JSON.stringify(disk).indexOf('token299') !== -1 };
}

// ── 4. an answer the page did not outlive: the interrupted marker path ──
{
  disk = []; acceptPut = true;
  const ls = makeStore();
  const p = mountChat(ls);
  await p.tick(600);
  p.api().set(prev => [...prev, { id:'r2', from:'ceo', name:'CafresoHQ',
                                  text:'half an ans', streaming:true, thread:'direct' }]);
  await p.tick(2600);                           // the PUT lands mid-stream
  R.cutFile = JSON.stringify(disk);
  const p2 = mountChat(makeStore());            // fresh browser, same disk
  await p2.tick(700);
  R.cutRead = JSON.stringify(p2.api().v);
}

// ── 5. saved workspaces on a fresh origin ───────────────────────────────
{
  disk = [{ id:'ws.mine', name:'Deep work', state:{ activeView:'vault' } }];
  acceptPut = true;
  const p = page(makeStore(), M => {
    const [v, set] = M.useFileStored('cafresohq_hq_v1:savedWorkspaces', 'state', 'workspaces', []);
    return { v, set };
  });
  await p.tick(700);
  R.workspaces = JSON.stringify(p.api().v);
}

srv.close();
console.log(JSON.stringify(R));
'''


def main() -> int:
    print('the conversation survives a fresh browser')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    for p in (STORAGE, APP, CHAT_UI):
        if not p.exists():
            check(f'{p.name} exists', False, str(p))
            return 1

    # Which hook app.jsx actually wires the chat to. The harness drives THAT
    # one, so the behavioural checks below measure the office rather than a
    # transcription of the fix into the test file.
    app_src = APP.read_text(encoding='utf-8')
    hook = 'useFileStored' if re.search(r"useFileStored\(k\('chat'\)", app_src) else 'useStored'
    print(f'  ..    app.jsx wires the chat to {hook}')

    proc = subprocess.run(
        ['node', '--input-type=module', '-e', HARNESS],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        env={**os.environ, 'STORAGE_PATH': str(STORAGE), 'CHAT_HOOK': hook})
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        check('the node harness runs the real hooks', False, 'see stderr')
        return 1
    R = json.loads(proc.stdout.strip().split('\n')[-1])

    # ── the fix ──────────────────────────────────────────────────────────
    check('a brand-new browser gets the conversation back',
          'what did we ship last week?' in R['fresh']
          and 'write that up for the board' in R['fresh'],
          f"{R['fresh'][:200]!r} — THE BUG #408 measured as freshKept:false. "
          'If this is empty the chat is still localStorage-only and clearing '
          'site data loses every conversation the office ever had')

    # ── the hole the swap could open, and the control that proves it real ──
    check('a keystroke before the fetch lands does not discard the history',
          'what did we ship last week?' in R['raceSafe']['inState']
          and 'are you there?' in R['raceSafe']['inState'],
          f"{R['raceSafe']['inState'][:200]!r} — the union has to keep BOTH "
          'halves: the file the office already had and the word just typed')
    check('...and does not then delete the file',
          'what did we ship last week?' in R['raceSafe']['onDisk'],
          f"{R['raceSafe']['onDisk'][:200]!r} — rescuing it into state only "
          'moves the loss to the next browser; #232\'s replay writes state '
          'back over disk, so a discarded fetch becomes a deleted file')
    check('the negative control reproduces the deletion without the union',
          'what did we ship last week?' not in R['raceControl']['onDisk'],
          f"{R['raceControl']['onDisk'][:200]!r} — the same swap WITHOUT "
          'mergeOnDirty+mergeChat must lose the history, or the two checks '
          'above are passing for some reason other than the union')

    # ── the cost ─────────────────────────────────────────────────────────
    s = R['stream']
    check('a streaming reply does not reach the wire per frame',
          s['midStreamPuts'] == 0,
          f"{s['midStreamPuts']} PUTs during {s['flushes']} token frames — "
          'the 1500ms debounce is re-armed by every frame, so a reply that '
          'is still arriving must cost nothing on the wire')
    check('a whole reply costs a handful of PUTs, not one per token',
          s['totalPuts'] <= 3,
          f"{s['totalPuts']} PUTs for {s['flushes']} frames ({s['kb']} KB) — "
          'measured on a real serve.py: ONE. An invariant, not a pin: if '
          'this climbs toward the frame count the debounce is gone and the '
          'office will stutter on every token')
    check('the streamed answer is what actually lands on disk',
          s['landedOnDisk'],
          'the last token never reached the file — a file-backed chat that '
          'only ever stores the placeholder is not a durable conversation')

    # ── the interrupted marker still works through the file ──────────────
    check('a reply the page outlived is marked on disk, not silently blank',
          '"interrupted":true' in R['cutFile'],
          f"{R['cutFile'][:200]!r} — persistableChat translates `streaming` "
          'into `interrupted`; if the write filter is not wired the record '
          'goes to disk as an ordinary finished message')
    check('...and the next browser reads it as a cut-off answer',
          '(cut off)' in R['cutRead'] or '(nothing came back)' in R['cutRead'],
          f"{R['cutRead'][:200]!r} — chatOnLoad has to run on the FETCHED "
          'side too, or a fresh browser shows a coworker name over a blank '
          'bubble with nothing saying the answer was severed')

    check('saved workspaces survive a fresh origin',
          'Deep work' in R['workspaces'],
          f"{R['workspaces']!r} — a layout the boss deliberately named and "
          'saved is authored content, not a preference')

    # ── the wiring, so none of the above can be quietly detached ─────────
    app = APP.read_text(encoding='utf-8')
    storage = STORAGE.read_text(encoding='utf-8')
    ui = CHAT_UI.read_text(encoding='utf-8')

    m = re.search(r"useFileStored\(k\('chat'\)[^;]*?\);", app, re.S)
    check('the chat is wired to useFileStored at all',
          m is not None and "useStored(k('chat')" not in app,
          "app.jsx — `useStored(k('chat'), …)` is the bug; there is no "
          'hq-state/chat.json while it stands')
    call = m.group(0) if m else ''
    # The argument-order trap #408 wrote down: useStored takes the WRITE
    # filter third and the READ scrub fourth; useFileStored takes the read
    # transform FIFTH and the write filter in options. Backwards, and
    # persistableChat's `interrupted` stamp lands on live replies.
    check('the write filter is in options, not the positional transform slot',
          'persistTransform: persistableChat' in call
          and not re.search(r"'chat',\s*HQ\.INITIAL_CHAT,\s*persistableChat", call),
          f'{call[:240]!r} — the argument-order trap. useFileStored\'s fifth '
          'positional argument is the READ scrub; passing persistableChat '
          'there stamps `interrupted` onto replies that are still streaming')
    check('the chat carries mergeOnDirty',
          'mergeOnDirty: true' in call,
          f'{call[:240]!r} — without it the mount fetch discards the whole '
          'fetched conversation the moment anything edits early, and the '
          'negative control above shows what that costs')
    check('mergeChat exists and runs the load scrub on the fetched side',
          'const mergeChat' in storage and 'chatOnLoad(fetched)' in storage,
          'app/storage.jsx — the union must spend the `interrupted` marker '
          'on records that came from disk, and only on those')
    check('the merge ref is declared before the hook that closes over it',
          app.find('const chatMergeRef') != -1
          and app.find('const chatMergeRef') < app.find("useFileStored(k('chat')"),
          'app.jsx — the transform is called from inside useFileStored\'s '
          'useState initializer, so a ref declared after it is in TDZ; the '
          'ReferenceError is swallowed by that initializer\'s own catch and '
          'the office silently seeds an empty conversation')

    check('the composer draft survives a reload',
          '_DRAFT_KEY' in ui and 'localStorage.getItem(_DRAFT_KEY)' in ui,
          'ui/chat.jsx — a bare useState(\'\') loses a half-typed prompt on '
          'the commonest event there is')
    check('...and is cleared rather than stored empty',
          'localStorage.removeItem(_DRAFT_KEY)' in ui,
          'ui/chat.jsx — a sent message must leave nothing behind')
    check('...and is deliberately NOT file-backed',
          '_DRAFT_KEY' not in storage and 'draft' not in call.lower(),
          'a sentence still being typed is a fact about this keyboard, not '
          'a record; syncing it would restore a fragment mid-word on a '
          'second device')

    print()
    if FAILS:
        print(f'the conversation survives a fresh browser: {len(FAILS)} FAILED')
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('the conversation survives a fresh browser: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
