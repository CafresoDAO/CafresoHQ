#!/usr/bin/env node
// Lifts the REAL WorkspaceView `publishOpen`/`_publishOpen` and
// AddProjectModal `submitGithub`/`_submitGithub` function bodies out of
// views/projects.jsx (verbatim source text, brace-balanced extraction — no
// re-implementation) and drives them with stub dependencies to test whether
// two re-entrant calls (the shape of a fast double-click, or a duplicate
// synthetic click event landing before React has re-rendered) cause the
// real side effects to fire twice.
//
// `publishOpen` had NO in-flight guard at all: `setPubMsg({kind:'busy'})`
// is written and never read as one, and neither 🚀 Publish nor 🔗 Preview
// link carries a `disabled`. Two clicks were two `publishSite` calls
// unconditionally, independent of React's commit timing — unlike ## 388 /
// ## 389 / ## 390 / ## 391, which all needed a stale state read.
//
// `submitGithub` DOES carry `disabled={busy}`, which gates an ordinary
// second click (React 18 flushes the discrete `setBusy(true)` before the
// next task, and HTML refuses implicit submission through a disabled
// default button). What it cannot gate is a second submit in the SAME tick,
// before React commits — which is exactly what this harness fires.
//
// Usage: node harness_projects_publish_clone_race.mjs <path-to-projects.jsx>
// Prints one JSON object per line to stdout, one per scenario run.

import fs from 'node:fs';

const projectsPath = process.argv[2];
if (!projectsPath) { console.error('usage: harness_projects_publish_clone_race.mjs <views/projects.jsx>'); process.exit(2); }
const src = fs.readFileSync(projectsPath, 'utf8');

function extractBalanced(source, marker) {
  const start = source.indexOf(marker);
  if (start < 0) throw new Error('marker not found: ' + marker);
  const braceStart = source.indexOf('{', start + marker.length - 1);
  let depth = 0;
  for (let k = braceStart; k < source.length; k++) {
    const c = source[k];
    if (c === '{') depth++;
    else if (c === '}') {
      depth--;
      if (depth === 0) return source.slice(braceStart + 1, k);
    }
  }
  throw new Error('unbalanced braces for marker: ' + marker);
}

const bodyOf = (marker) => extractBalanced(src, marker);
const has = (marker) => src.indexOf(marker) >= 0;

/* ── publish ────────────────────────────────────────────────────────── */

const PUBLISH_PARAMS = [
  'openFile', 'setPubMsg', 'publicHostingReady', 'CafresoHQClient',
  'navigator', 'officeCause', 'publishingPathsRef', '_publishOpen',
];

function buildPublish() {
  // Post-fix the entry point is a thin claim-wrapper around `_publishOpen`;
  // pre-fix the whole body sits directly in `publishOpen` and the
  // `_`-prefixed marker is absent, so the harness calls the entry point
  // alone. Either way it is the REAL committed source that runs.
  const inner = has('const _publishOpen = async () => {')
    ? bodyOf('const _publishOpen = async () => {') : null;
  const outer = bodyOf('const publishOpen = async () => {');
  // eslint-disable-next-line no-new-func
  const mkInner = inner ? new Function(...PUBLISH_PARAMS, `return (async () => {${inner}});`) : null;
  // eslint-disable-next-line no-new-func
  const mkOuter = new Function(...PUBLISH_PARAMS, `return (async () => {${outer}});`);
  return { mkInner, mkOuter };
}

function publishWorld({ mode = 'canister', fail = false } = {}) {
  const calls = { publishSite: [], clipboard: [], pubMsg: [] };
  return {
    openFile: { path: '/proj/site/index.html', binary: false, content: '<h1>hi</h1>' },
    setPubMsg: (m) => { calls.pubMsg.push(m && m.kind); },
    publicHostingReady: () => mode === 'canister',
    CafresoHQClient: {
      // Real spend / a real upload. Resolves on a later macrotask so a
      // second re-entrant call lands while the first is genuinely still in
      // flight — the live shape.
      publishSite: (p) => new Promise((res, rej) => {
        calls.publishSite.push(p);
        setTimeout(() => {
          if (fail) rej(new Error('canister rejected the upload'));
          else res({ mode, url: mode === 'canister' ? 'https://x.icp0.io/' : 'http://localhost:8765/fs/site/abc' });
        }, 5);
      }),
    },
    navigator: { clipboard: { writeText: async (t) => { calls.clipboard.push(t); } } },
    officeCause: (m) => String(m || ''),
    publishingPathsRef: { current: new Set() },
    calls,
  };
}

async function runPublish(name, { times = 2, sequential = false, mode = 'canister', fail = false } = {}) {
  const w = publishWorld({ mode, fail });
  const { mkInner, mkOuter } = buildPublish();
  const innerFn = mkInner ? mkInner(...PUBLISH_PARAMS.map(m => (m === '_publishOpen' ? null : w[m]))) : null;
  const fn = mkOuter(...PUBLISH_PARAMS.map(m => (m === '_publishOpen' ? innerFn : w[m])));
  let threw = null;
  try {
    if (sequential) {
      for (let i = 0; i < times; i++) await fn();
    } else {
      // Re-entrant: fire N times back-to-back against ONE unchanged
      // snapshot, without awaiting between.
      const ps = [];
      for (let i = 0; i < times; i++) ps.push(fn());
      await Promise.all(ps);
    }
  } catch (e) { threw = String((e && e.stack) || e); }
  console.log(JSON.stringify({
    scenario: name, threw, mode, fail,
    publishSite: w.calls.publishSite.length,
    clipboard: w.calls.clipboard.length,
  }));
}

/* ── retry after a failed publish ───────────────────────────────────── */

async function runPublishRetryAfterFailure(name) {
  // The failure case matters most here: a publish that fails is exactly
  // when the boss clicks again, so the claim MUST have been released.
  const w = publishWorld({ mode: 'canister', fail: true });
  const { mkInner, mkOuter } = buildPublish();
  const innerFn = mkInner ? mkInner(...PUBLISH_PARAMS.map(m => (m === '_publishOpen' ? null : w[m]))) : null;
  const fn = mkOuter(...PUBLISH_PARAMS.map(m => (m === '_publishOpen' ? innerFn : w[m])));
  let threw = null;
  try {
    await fn();          // first attempt — fails inside publishSite
    await fn();          // the retry a real boss would make
  } catch (e) { threw = String((e && e.stack) || e); }
  console.log(JSON.stringify({
    scenario: name, threw, mode: 'canister', fail: true,
    publishSite: w.calls.publishSite.length,
    clipboard: w.calls.clipboard.length,
  }));
}

/* ── clone ──────────────────────────────────────────────────────────── */

const CLONE_PARAMS = [
  'repoUrl', 'repoName', 'shallow', 'setErr', 'setBusy', 'CafresoHQClient',
  'onCommit', 'repoCause', 'console', 'cloningUrlsRef', '_submitGithub',
];

function buildClone() {
  const inner = has('const _submitGithub = async () => {')
    ? bodyOf('const _submitGithub = async () => {') : null;
  const outer = bodyOf('const submitGithub = async (e) => {');
  // eslint-disable-next-line no-new-func
  const mkInner = inner ? new Function(...CLONE_PARAMS, `return (async () => {${inner}});`) : null;
  // eslint-disable-next-line no-new-func
  const mkOuter = new Function(...CLONE_PARAMS, `return (async (e) => {${outer}});`);
  return { mkInner, mkOuter };
}

function cloneWorld({ fail = false } = {}) {
  const calls = { cloneRepo: [], onCommit: [], err: [] };
  return {
    repoUrl: 'owner/repo',
    repoName: '',
    shallow: true,
    setErr: (m) => { if (m) calls.err.push(String(m)); },
    setBusy: () => {},
    CafresoHQClient: {
      // A real `git clone` on the server, into a real directory.
      cloneRepo: (o) => new Promise((res, rej) => {
        calls.cloneRepo.push(o.url);
        setTimeout(() => {
          if (fail) { const e = new Error('git clone failed (exit 128)'); e.detail = 'fatal: repository not found'; rej(e); }
          else res({ name: 'repo', path: '/pj-space/repo' });
        }, 5);
      }),
    },
    onCommit: (p) => { calls.onCommit.push(p && p.path); },
    repoCause: (m) => String(m || ''),
    console: { warn: () => {} },
    cloningUrlsRef: { current: new Set() },
    calls,
  };
}

function cloneFn(w) {
  const { mkInner, mkOuter } = buildClone();
  const innerFn = mkInner ? mkInner(...CLONE_PARAMS.map(m => (m === '_submitGithub' ? null : w[m]))) : null;
  return mkOuter(...CLONE_PARAMS.map(m => (m === '_submitGithub' ? innerFn : w[m])));
}

const fakeEvent = () => ({ preventDefault() { this.prevented = (this.prevented || 0) + 1; } });

async function runClone(name, { times = 2, sequential = false, fail = false } = {}) {
  const w = cloneWorld({ fail });
  const fn = cloneFn(w);
  let threw = null;
  try {
    if (sequential) {
      for (let i = 0; i < times; i++) await fn(fakeEvent());
    } else {
      const ps = [];
      for (let i = 0; i < times; i++) ps.push(fn(fakeEvent()));
      await Promise.all(ps);
    }
  } catch (e) { threw = String((e && e.stack) || e); }
  console.log(JSON.stringify({
    scenario: name, threw, fail,
    cloneRepo: w.calls.cloneRepo.length,
    onCommit: w.calls.onCommit.length,
  }));
}

async function runCloneRetryAfterFailure(name) {
  const w = cloneWorld({ fail: true });
  const fn = cloneFn(w);
  let threw = null;
  try {
    await fn(fakeEvent());     // first attempt — git clone fails
    await fn(fakeEvent());     // the retry the error box invites
  } catch (e) { threw = String((e && e.stack) || e); }
  console.log(JSON.stringify({
    scenario: name, threw, fail: true,
    cloneRepo: w.calls.cloneRepo.length,
    onCommit: w.calls.onCommit.length,
  }));
}

// A submit that is REFUSED by the claim must still have called
// preventDefault, or the blocked second event navigates the page away.
async function runClonePreventDefault(name) {
  const w = cloneWorld({});
  const fn = cloneFn(w);
  const events = [fakeEvent(), fakeEvent()];
  let threw = null;
  try { await Promise.all(events.map(ev => fn(ev))); }
  catch (e) { threw = String((e && e.stack) || e); }
  console.log(JSON.stringify({
    scenario: name, threw, fail: false,
    cloneRepo: w.calls.cloneRepo.length,
    onCommit: w.calls.onCommit.length,
    prevented: events.filter(ev => ev.prevented === 1).length,
  }));
}

/* ── scenarios ──────────────────────────────────────────────────────── */

const main = async () => {
  // The race: one click's worth of intent, two events.
  await runPublish('publish-double-click', { times: 2 });
  await runPublish('publish-triple-click', { times: 3 });
  // Sanity: a plain single publish still does exactly one publish.
  await runPublish('publish-single', { times: 1 });
  // The preview-link fallback is the same handler and the same door.
  await runPublish('publish-preview-double-click', { times: 2, mode: 'preview' });
  // Not over-blocked: once a publish has ENDED, publishing again must work.
  await runPublish('publish-again-after-finish', { times: 2, sequential: true });
  // ...including after a FAILED one, which is when the boss really retries.
  await runPublishRetryAfterFailure('publish-retry-after-failure');

  await runClone('clone-double-submit', { times: 2 });
  await runClone('clone-triple-submit', { times: 3 });
  await runClone('clone-single', { times: 1 });
  await runClone('clone-again-after-finish', { times: 2, sequential: true });
  await runCloneRetryAfterFailure('clone-retry-after-failure');
  await runClonePreventDefault('clone-refused-submit-still-prevented');
};

main().catch(e => { console.error(e); process.exit(1); });
