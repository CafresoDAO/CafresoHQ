/* CafresoHQ — minimal service worker.
 * Network-first for the UI SHELL, with an offline fallback for navigations.
 * Nothing that reports CURRENT STATE is ever cached.
 *
 * Cross-origin scope: when the UI is served from an ICP canister and the API
 * lives in a separate container origin, this SW must NOT intercept the API
 * requests — they pass straight through to the network (with whatever
 * credentials the page set). The fetch handler early-returns for any request
 * whose origin isn't this SW's own origin, so it only ever manages the
 * same-origin UI shell.
 *
 * ── Why this is an ALLOWLIST ──────────────────────────────────────────────
 * It used to be a denylist: cache everything same-origin except a list of
 * known-live prefixes. That defaults to CACHING, so every endpoint added
 * after the list was written became cacheable silently. Driven for real on a
 * throwaway office (this worker had never once executed — hq.html unregisters
 * it on load), and the result was the worst thing found in this codebase all
 * day. With the server COMPLETELY DEAD:
 *
 *     GET /health                 → 200 {"status": "ok", …}
 *     GET /agent/drivers?probe=1  → 200 {"drivers": [ … ]}
 *     GET /missions/scheduled     → 200 {"schedules": [], …}
 *
 * The office reporting itself healthy while nothing is running. That defeats
 * the offline banner, the front desk's "your office isn't answering", and
 * every §7 route out at once — and it reintroduces the Tier-1 health
 * false-positive at the network layer, BELOW the app, where no amount of care
 * in the UI could detect it. A boss would see a working office and nothing
 * would work.
 *
 * So the default is now DON'T CACHE. Only the static shell is eligible:
 * hashed bundles, /assets/, and a handful of exact files. Anything new —
 * every future endpoint — is uncached unless someone deliberately adds it,
 * which is the direction a mistake should fall.
 */
const CACHE_NAME = 'cafresohq-shell-v4';
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

/* The only things worth keeping for an offline shell: files whose content is
   fixed for a given build. A hashed bundle name changes when the build does,
   so a stale one can never be served for a new build. */
const SHELL_EXACT = new Set(['/', '/hq.html', '/styles.css', '/manifest.webmanifest']);
const SHELL_PREFIXES = ['/assets/', '/dist-ui/', '/bundle/'];

function isShellAsset(url) {
  if (SHELL_EXACT.has(url.pathname)) return true;
  return SHELL_PREFIXES.some((p) => url.pathname.startsWith(p));
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  // Never intercept cross-origin requests (e.g. the container API when the UI is
  // canister-served) — let the browser handle them natively with page creds.
  if (url.origin !== self.location.origin) return;

  const navigating = req.mode === 'navigate';

  /* Anything that is not a shell asset and is not a page load goes straight to
     the network, uncached and un-intercepted. A failed API call must FAIL —
     the app has honest words for that — rather than be answered from a cache
     or, as the old fallback did, be handed `/hq.html` and leave the caller
     parsing a web page as JSON. */
  if (!navigating && !isShellAsset(url)) return;

  event.respondWith(
    fetch(req).then((res) => {
      if (res.ok && isShellAsset(url)) {
        const copy = res.clone();
        caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
      }
      return res;
    }).catch(() =>
      caches.match(req).then(hit => hit || (navigating ? caches.match('/hq.html') : Response.error()))
    )
  );
});
