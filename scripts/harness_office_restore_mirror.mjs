#!/usr/bin/env node
/* #402 — Settings → OFFICE BACKUP → IMPORT ("Replace office").
 *
 * `importOffice` writes every restored key into localStorage and, for the
 * thirteen keys that are ALSO mirrored to an hq-state/hq-memory file, PUTs
 * the matching file so the reload it triggers does not pull the OLD file
 * back over the just-restored value. That reason is written out in full in
 * the file's own OFFICE_FILE_BACKED comment:
 *
 *   "within the same reload this button triggers, the mount-fetch pulls the
 *    old file back over the just-written value and the 'restore' silently
 *    undoes itself with no error anywhere."
 *
 * The PUT that exists to prevent that had `.catch(() => {})` and no
 * `r.ok` check — so every way it can fail (offline, 403, 500, a 200 SPA
 * fallback on a host with no backend) resolved as if it had worked, and
 * `window.location.reload()` ran unconditionally. The failure this code was
 * written to prevent is exactly what a failure of this code produces, and
 * the boss is told nothing: a reload is what SUCCESS looks like.
 *
 * Drives the REAL brace-lifted body from modals/settings.jsx. No
 * re-implementation of anything under test.
 *
 * Usage: node harness_office_restore_mirror.mjs <repo-root> [scenario]
 * Prints one JSON object per line.
 */
import fs from 'node:fs';
import path from 'node:path';

const root = process.argv[2];
if (!root) { console.error('usage: harness_office_restore_mirror.mjs <repo-root> [scenario]'); process.exit(2); }
const src = fs.readFileSync(path.join(root, 'modals', 'settings.jsx'), 'utf8');

function stripComments(s) {
  return s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^[ \t]*\/\/.*$/gm, '');
}
const bare = stripComments(src);

/* Lift OFFICE_HQ_PREFIX … end of importOffice, verbatim. */
const START = 'const OFFICE_HQ_PREFIX';
const IMPORT_MARKER = 'const importOffice = async (e) => {';
const s0 = bare.indexOf(START);
if (s0 < 0) throw new Error('marker not found: ' + START);
const m0 = bare.indexOf(IMPORT_MARKER, s0);
if (m0 < 0) throw new Error('marker not found: ' + IMPORT_MARKER);
let depth = 0, end = -1;
for (let k = bare.indexOf('{', m0 + IMPORT_MARKER.length - 1); k < bare.length; k++) {
  const c = bare[k];
  if (c === '{') depth++;
  else if (c === '}') { depth--; if (depth === 0) { end = k + 1; break; } }
}
if (end < 0) throw new Error('unbalanced braces for importOffice');
const SEGMENT = bare.slice(s0, end);

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

/* Everything the segment closes over, stubbed. */
function makeRunner({ putResult, confirmAnswer = true }) {
  const log = { ls: {}, puts: [], notes: [], reloaded: false, retry: null };
  const localStorage = {
    _m: {},
    setItem(k, v) { log.ls[k] = v; },
    getItem(k) { return this._m[k] ?? null; },
  };
  const fetchStub = async (url, opts) => {
    log.puts.push({ url, method: opts && opts.method, body: opts && opts.body });
    return putResult(url);
  };
  const win = {
    _API_BASE: 'http://office.test',
    hqConfirm: async () => confirmAnswer,
    location: { reload: () => { log.reloaded = true; } },
  };
  const setNote = (t) => { log.notes.push(t); };
  const useRefM = () => ({ current: null });
  /* The real `const [officeRetry, setOfficeRetry] = useStateM(null)` is
     lifted with the rest of the segment; this is the React stub under it,
     recording what the component would have re-rendered with. */
  const useStateM = (init) => [
    (typeof init === 'function' ? init() : init),
    (v) => { log.retry = typeof v === 'function' ? v(log.retry) : v; },
  ];
  const officeCause = (raw) => {
    const t = String(raw || '');
    if (/failed to fetch|econnrefused|network ?error|load failed/i.test(t)) return "the office isn't answering — check it's still running";
    if (/\b5\d\d\b|internal server error/i.test(t)) return 'the office ran into trouble doing that — not something you did';
    if (/\b403\b|permission denied/i.test(t)) return "the office isn't allowed to touch that file";
    return t;
  };
  const apiBase = win._API_BASE;
  const body = SEGMENT + '\n; return importOffice(EV);';
  const fn = new AsyncFunction(
    'apiBase', 'localStorage', 'fetch', 'window', 'setNote',
    'useRefM', 'useStateM', 'officeCause', 'Blob', 'document', 'URL', 'EV',
    body);
  return async (EV) => {
    await fn(apiBase, localStorage, fetchStub, win, setNote,
      useRefM, useStateM, officeCause, class {}, { createElement: () => ({ click() {} }) },
      { createObjectURL: () => 'blob:x', revokeObjectURL() {} }, EV);
    return log;
  };
}

/* A minimal but REAL backup file: one file-backed key (tasks → state/tasks)
   and one purely-local key. */
const BACKUP = JSON.stringify({
  format: 'cafresohq-office-backup', version: 1,
  exportedAt: '2026-08-01T00:00:00.000Z',
  entries: {
    'cafresohq_hq_v1:tasks': JSON.stringify([{ id: 't1', title: 'restored task' }]),
    'cafresohq_hq_v1:agents': JSON.stringify([{ id: 'a1', name: 'Restored coworker' }]),
    'cafresohq:theme': 'wallstreet',
  },
});
const EV = { target: { files: [{ text: async () => BACKUP }], value: 'x' } };

const SCENARIOS = {
  /* The office is not running / the tab is offline. */
  async offline() {
    const run = makeRunner({ putResult: async () => { throw new TypeError('Failed to fetch'); } });
    return { scenario: 'offline', ...(await run(EV)) };
  },
  /* The office answers, and refuses. */
  async refused403() {
    const run = makeRunner({ putResult: async () => ({ ok: false, status: 403, statusText: 'Forbidden' }) });
    return { scenario: 'refused403', ...(await run(EV)) };
  },
  /* The office is up but the write blew up server-side. */
  async server500() {
    const run = makeRunner({ putResult: async () => ({ ok: false, status: 500, statusText: 'Internal Server Error' }) });
    return { scenario: 'server500', ...(await run(EV)) };
  },
  /* Everything actually worked — the control case. */
  async healthy() {
    const run = makeRunner({ putResult: async () => ({ ok: true, status: 200, statusText: 'OK' }) });
    return { scenario: 'healthy', ...(await run(EV)) };
  },
};

/* ── second finding, same class: views/projects.jsx `reloadOpenClassic` ──
   The Classic project editor's conflict banner reads "⚠ Your coworker
   changed this file while you had edits." and its Reload button calls
   `reloadOpenClassic`. That function swallowed the read into `catch (_e) {}`
   and cleared the banner OUTSIDE the try — so a failed reload dismissed the
   warning, left the stale buffer exactly as it was, and said nothing. The
   boss's evidence that the reload worked was the banner going away, which
   is the one thing that happened either way. */
const projSrc = stripComments(fs.readFileSync(path.join(root, 'views', 'projects.jsx'), 'utf8'));
const RC = 'const reloadOpenClassic = async (path) => {';
function liftFn(source, marker) {
  const i = source.indexOf(marker);
  if (i < 0) throw new Error('marker not found: ' + marker);
  let d = 0;
  for (let k = source.indexOf('{', i + marker.length - 1); k < source.length; k++) {
    if (source[k] === '{') d++;
    else if (source[k] === '}') { d--; if (d === 0) return source.slice(i, k + 1); }
  }
  throw new Error('unbalanced: ' + marker);
}
const RELOAD_SEG = liftFn(projSrc, RC);

async function runReload({ readResult, openPath = 'notes/plan.md' }) {
  const log = { err: [], conflict: 'still-true', buffer: { path: openPath, content: 'MY OLD BUFFER', dirty: false } };
  const setErr = (v) => { log.err.push(v); };
  const setConflict = (v) => { log.conflict = v; };
  const setOpenFile = (f) => { log.buffer = typeof f === 'function' ? f(log.buffer) : f; };
  const CafresoHQClient = { fsReadText: readResult };
  const fn = new AsyncFunction('CafresoHQClient', 'setErr', 'setConflict', 'setOpenFile', 'P',
    RELOAD_SEG + '\n; return reloadOpenClassic(P);');
  await fn(CafresoHQClient, setErr, setConflict, setOpenFile, openPath);
  return log;
}

const RELOAD_SCENARIOS = {
  async reload_office_down() {
    const l = await runReload({ readResult: async () => { throw new TypeError('Failed to fetch'); } });
    return { scenario: 'reload_office_down', bannerCleared: l.conflict === false,
      bufferContent: l.buffer && l.buffer.content, errsShown: l.err.filter(Boolean) };
  },
  async reload_healthy() {
    const l = await runReload({ readResult: async () => ({ content: 'COWORKER CONTENT', mtime: 2, hash: 'h2' }) });
    return { scenario: 'reload_healthy', bannerCleared: l.conflict === false,
      bufferContent: l.buffer && l.buffer.content, errsShown: l.err.filter(Boolean) };
  },
};

const want = process.argv[3];
const names = want ? [want] : Object.keys(SCENARIOS);
for (const n of names) {
  const r = await SCENARIOS[n]();
  console.log(JSON.stringify({
    scenario: r.scenario,
    putCount: r.puts.length,
    lsKeysWritten: Object.keys(r.ls).length,
    reloaded: r.reloaded,
    notes: r.notes,
    retryOffered: Array.isArray(r.retry) ? r.retry.length : 0,
    staleFiles: Array.isArray(r.retry) ? r.retry.map(s => s.where) : [],
    whys: Array.isArray(r.retry) ? [...new Set(r.retry.map(s => s.why))] : [],
  }));
}
for (const n of (want ? (RELOAD_SCENARIOS[want] ? [want] : []) : Object.keys(RELOAD_SCENARIOS))) {
  console.log(JSON.stringify(await RELOAD_SCENARIOS[n]()));
}
