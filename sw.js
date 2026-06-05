/* CafresoAI — minimal service worker.
 * Network-first for everything (so chat/streaming endpoints always go live),
 * with an offline shell fallback for the main HTML when offline.
 * Stream endpoints (/openclaw/stream, /codex/stream, /claudecode/stream,
 * /oca/, /lmstudio/, /ollama/, /vault/, /tools/) are NEVER cached.
 *
 * Cross-origin scope: when the UI is served from an ICP canister and the API
 * lives in a separate container origin, this SW must NOT intercept the API
 * requests — they pass straight through to the network (with whatever
 * credentials the page set). The fetch handler early-returns for any request
 * whose origin isn't this SW's own origin, so it only ever manages the
 * same-origin UI shell.
 */
const CACHE_NAME = 'openclaw-shell-v2';
const SHELL_URLS = [
  '/hq.html',
  '/styles.css',
  '/manifest.webmanifest',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      cache.addAll(SHELL_URLS).catch(() => {})
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

const NEVER_CACHE_PREFIXES = [
  '/openclaw/', '/codex/', '/claudecode/', '/oca/', '/lmstudio/', '/ollama/',
  '/vault/', '/tools/', '/projects/', '/approvals/', '/hq/', '/brave/',
  '/terminal/',
];

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  // Never intercept cross-origin requests (e.g. the container API when the UI is
  // canister-served) — let the browser handle them natively with page creds.
  if (url.origin !== self.location.origin) return;
  if (NEVER_CACHE_PREFIXES.some(p => url.pathname.startsWith(p))) return;

  event.respondWith(
    fetch(req).then((res) => {
      // Stash a copy of successful same-origin GETs for offline fallback.
      if (res.ok && url.origin === self.location.origin) {
        const copy = res.clone();
        caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
      }
      return res;
    }).catch(() =>
      caches.match(req).then(hit => hit || caches.match('/hq.html'))
    )
  );
});
